from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
import threading

import config

logger = logging.getLogger(__name__)

# Thread-safe flash state
_lock = threading.Lock()
_state: dict = {"state": "idle", "log": [], "progress": ""}


def get_status() -> dict:
    with _lock:
        return dict(_state)


def _set_state(state: str, progress: str = ""):
    with _lock:
        _state["state"] = state
        _state["progress"] = progress


def _append_log(line: str):
    with _lock:
        _state["log"].append(line)


def _reset_state():
    with _lock:
        _state["state"] = "idle"
        _state["log"] = []
        _state["progress"] = ""


def verify_sha256(path: str, expected: str) -> bool:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest().lower() == expected.lower()


def flash_firmware(fw_path: str, expected_hash: str, poller) -> None:
    """Run firmware flash in a background thread."""
    t = threading.Thread(
        target=_flash_worker,
        args=(fw_path, expected_hash, poller),
        daemon=True,
        name="firmware-flash",
    )
    t.start()


def _flash_worker(fw_path: str, expected_hash: str, poller) -> None:
    _reset_state()
    _set_state("flashing", "Verifying firmware hash...")
    _append_log("Verifying SHA256 hash...")

    if not verify_sha256(fw_path, expected_hash):
        _set_state("error", "SHA256 mismatch")
        _append_log("ERROR: SHA256 hash does not match expected value.")
        _cleanup(fw_path)
        return

    _append_log("SHA256 verified OK.")

    # Stop collector thread to release serial port
    _set_state("flashing", "Stopping collector...")
    _append_log("Stopping collector poller...")
    try:
        poller.stop()
        _append_log("Collector stopped.")
    except Exception as e:
        _append_log(f"Warning stopping collector: {e}")

    # Stop external services
    _set_state("flashing", "Stopping SerialMux and mctomqtt...")
    for svc in ("SerialMux", "mctomqtt"):
        _append_log(f"Stopping {svc}...")
        try:
            result = subprocess.run(
                ["sudo", "systemctl", "stop", svc],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                _append_log(f"Warning: systemctl stop {svc}: {result.stderr.strip()}")
            else:
                _append_log(f"{svc} stopped.")
        except Exception as e:
            _append_log(f"Warning stopping {svc}: {e}")

    # Run adafruit-nrfutil
    port = config.FLASH_SERIAL_PORT
    _set_state("flashing", "Flashing firmware...")
    _append_log(f"Flashing firmware on {port}...")
    cmd = [
        "adafruit-nrfutil", "--verbose", "dfu", "serial",
        "--package", fw_path,
        "-p", port,
        "-b", "115200",
        "--singlebank",
        "--touch", "1200",
    ]
    _append_log(f"Running: {' '.join(cmd)}")

    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        for line in proc.stdout:
            line = line.rstrip("\n")
            _append_log(line)
            if "%" in line:
                _set_state("flashing", line.strip())
        proc.wait(timeout=300)

        if proc.returncode == 0:
            _append_log("Firmware flash completed successfully!")
            _set_state("done", "Flash complete")
        else:
            _append_log(f"ERROR: Flash process exited with code {proc.returncode}")
            _set_state("error", f"Exit code {proc.returncode}")
    except subprocess.TimeoutExpired:
        proc.kill()
        _append_log("ERROR: Flash process timed out (300s)")
        _set_state("error", "Timeout")
    except FileNotFoundError:
        _append_log("ERROR: adafruit-nrfutil not found. Is it installed?")
        _set_state("error", "adafruit-nrfutil not found")
    except Exception as e:
        _append_log(f"ERROR: {e}")
        _set_state("error", str(e))

    # Restart services regardless of outcome
    _append_log("Restarting services...")
    for svc in ("SerialMux", "mctomqtt"):
        _append_log(f"Starting {svc}...")
        try:
            result = subprocess.run(
                ["sudo", "systemctl", "start", svc],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                _append_log(f"Warning: systemctl start {svc}: {result.stderr.strip()}")
            else:
                _append_log(f"{svc} started.")
        except Exception as e:
            _append_log(f"Warning starting {svc}: {e}")

    # Restart collector poller
    _append_log("Restarting collector poller...")
    try:
        poller.start()
        _append_log("Collector restarted.")
    except Exception as e:
        _append_log(f"Warning restarting collector: {e}")

    _cleanup(fw_path)
    _append_log("Done.")


def _cleanup(fw_path: str):
    try:
        if os.path.exists(fw_path):
            os.remove(fw_path)
    except OSError:
        pass
    try:
        upload_dir = config.FIRMWARE_UPLOAD_DIR
        if os.path.isdir(upload_dir):
            shutil.rmtree(upload_dir, ignore_errors=True)
    except OSError:
        pass
