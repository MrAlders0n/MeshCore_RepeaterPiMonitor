from __future__ import annotations

import glob
import hashlib
import logging
import os
import shutil
import subprocess
import threading
import time

import config
from collector import radio_gpio
from database import models

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

    # Enter bootloader mode via GPIO double-pulse reset
    _set_state("flashing", "Entering bootloader mode...")
    _append_log("Entering bootloader mode via GPIO...")
    try:
        radio_gpio.bootloader_mode()
        _append_log("Bootloader mode triggered.")
    except Exception as e:
        _append_log(f"ERROR: Failed to enter bootloader mode: {e}")
        _set_state("error", "GPIO bootloader failed")
        _restart_services(poller)
        _cleanup(fw_path)
        _append_log("Done.")
        return

    # Wait for the DFU serial port to re-appear after USB re-enumeration
    port = models.get_setting("flash_serial_port", config.FLASH_SERIAL_PORT)
    _set_state("flashing", "Waiting for DFU port...")
    _append_log(f"Waiting for {port} to appear...")
    dfu_port = _wait_for_port(port, timeout=15)
    if not dfu_port:
        _append_log(f"ERROR: {port} did not appear within 15 seconds.")
        _set_state("error", "DFU port not found")
        _restart_services(poller)
        _cleanup(fw_path)
        _append_log("Done.")
        return
    _append_log(f"DFU port ready: {dfu_port}")

    # Run adafruit-nrfutil (no --touch since we entered bootloader via GPIO)
    _set_state("flashing", "Flashing firmware...")
    _append_log(f"Flashing firmware on {dfu_port}...")
    cmd = [
        "adafruit-nrfutil", "--verbose", "dfu", "serial",
        "--package", fw_path,
        "-p", dfu_port,
        "-b", "115200",
        "--singlebank",
    ]
    _append_log(f"Running: {' '.join(cmd)}")

    flash_failed = False
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        output_lines = []
        for line in proc.stdout:
            line = line.rstrip("\n")
            _append_log(line)
            output_lines.append(line)
            if "%" in line:
                _set_state("flashing", line.strip())
        proc.wait(timeout=300)

        # Check for errors in output — adafruit-nrfutil can return 0 on failure
        output_text = "\n".join(output_lines)
        has_error = ("Failed to upgrade" in output_text
                     or "Serial port could not be opened" in output_text
                     or "NordicSemiException" in output_text)

        if proc.returncode != 0 or has_error:
            _append_log(f"ERROR: Flash failed (exit code {proc.returncode})")
            _set_state("error", "Flash failed")
            flash_failed = True
        else:
            _append_log("Firmware flash completed successfully!")
            _set_state("done", "Flash complete")
    except subprocess.TimeoutExpired:
        proc.kill()
        _append_log("ERROR: Flash process timed out (300s)")
        _set_state("error", "Timeout")
        flash_failed = True
    except FileNotFoundError:
        _append_log("ERROR: adafruit-nrfutil not found. Is it installed?")
        _set_state("error", "adafruit-nrfutil not found")
        flash_failed = True
    except Exception as e:
        _append_log(f"ERROR: {e}")
        _set_state("error", str(e))
        flash_failed = True

    _restart_services(poller)
    _cleanup(fw_path)
    _append_log("Done.")


def _wait_for_port(port: str, timeout: int = 15) -> str | None:
    """Wait for a serial port path to exist. Returns the path or None."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if os.path.exists(port):
            return port
        # Also check for wildcard match in case the device ID changes slightly
        parent = os.path.dirname(port)
        if os.path.isdir(parent):
            matches = glob.glob(os.path.join(parent, "*nRF52*"))
            if matches:
                return matches[0]
        time.sleep(1)
    return None


def _restart_services(poller):
    """Restart external services and the collector poller."""
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

    _append_log("Restarting collector poller...")
    try:
        poller.start()
        _append_log("Collector restarted.")
    except Exception as e:
        _append_log(f"Warning restarting collector: {e}")


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
