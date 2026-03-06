import os
import platform
import subprocess
import threading
import time

from flask import Blueprint, jsonify, request, current_app
from werkzeug.utils import secure_filename

import config
from database import models
from collector import firmware_flasher
from collector import radio_gpio
from collector.sensors import bq24074_sensor

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

MANAGED_SERVICES = ["mctomqtt", "SerialMux", "RepeaterWatch"]

api = Blueprint("api", __name__, url_prefix="/api/v1")


def _hours():
    try:
        return int(request.args.get("hours", 24))
    except (TypeError, ValueError):
        return 24


@api.route("/device")
def device_info():
    info = models.get_device_info()
    core = models.query_stats_core(hours=1)
    uptime = core[-1]["uptime_secs"] if core else None
    pk = info.get("public_key", "")
    # pubkey_prefix: first 4 hex chars (2 bytes) for map label
    pubkey_prefix = pk[:4].upper() if pk else ""
    lat = None
    lon = None
    try:
        lat = float(info["lat"]) if "lat" in info else None
        lon = float(info["lon"]) if "lon" in info else None
    except (ValueError, TypeError):
        pass
    return jsonify({
        "name": info.get("name", "Unknown"),
        "firmware": info.get("firmware", "Unknown"),
        "board": info.get("board", "Unknown"),
        "radio_config": info.get("radio_config", "Unknown"),
        "public_key": pk,
        "pubkey_prefix": pubkey_prefix,
        "lat": lat,
        "lon": lon,
        "uptime_secs": uptime,
    })


@api.route("/stats/battery")
def stats_battery():
    rows = models.query_stats_core(_hours())
    return jsonify({
        "timestamps": [r["ts"] for r in rows],
        "battery_mv": [r["battery_mv"] for r in rows],
    })


@api.route("/stats/radio")
def stats_radio():
    rows = models.query_stats_radio(_hours())
    return jsonify({
        "timestamps": [r["ts"] for r in rows],
        "noise_floor": [r["noise_floor"] for r in rows],
        "tx_air_secs": [r["tx_air_secs"] for r in rows],
        "rx_air_secs": [r["rx_air_secs"] for r in rows],
        "last_rssi": [r["last_rssi"] for r in rows],
        "last_snr": [r["last_snr"] for r in rows],
    })


@api.route("/stats/packets")
def stats_packets():
    rows = models.query_stats_packets(_hours())
    return jsonify({
        "timestamps": [r["ts"] for r in rows],
        "recv_total": [r["recv_total"] for r in rows],
        "sent_total": [r["sent_total"] for r in rows],
        "recv_errors": [r["recv_errors"] for r in rows],
        "fwd_total": [r["fwd_total"] for r in rows],
        "fwd_errors": [r["fwd_errors"] for r in rows],
        "direct_dups": [r["direct_dups"] for r in rows],
    })


@api.route("/stats/power")
def stats_power():
    rows = models.query_stats_extpower(_hours())
    return jsonify({
        "timestamps": [r["ts"] for r in rows],
        "ch0_voltage": [r["ch0_voltage"] for r in rows],
        "ch0_current": [r["ch0_current"] for r in rows],
        "ch0_power": [r["ch0_power"] for r in rows],
        "ch1_voltage": [r["ch1_voltage"] for r in rows],
        "ch1_current": [r["ch1_current"] for r in rows],
        "ch1_power": [r["ch1_power"] for r in rows],
        "ch2_voltage": [r["ch2_voltage"] for r in rows],
        "ch2_current": [r["ch2_current"] for r in rows],
        "ch2_power": [r["ch2_power"] for r in rows],
    })


@api.route("/stats/airtime")
def stats_airtime():
    rows = models.query_airtime(_hours())
    return jsonify({
        "timestamps": [r["ts"] for r in rows],
        "tx_pct": [r["tx_pct"] for r in rows],
        "rx_pct": [r["rx_pct"] for r in rows],
    })


@api.route("/packets/activity")
def packets_activity():
    h = _hours()
    bucket = request.args.get("bucket_minutes", 15, type=int)
    rows = models.query_packets_activity(h, bucket)

    # If packet_log has no data, fall back to stats_packets deltas
    if not rows:
        rows = models.query_packets_activity_from_stats(h)
        return jsonify({
            "timestamps": [r["bucket"] for r in rows],
            "tx_direct": [r["tx_direct"] for r in rows],
            "tx_flood": [r["tx_flood"] for r in rows],
            "rx_direct": [r["rx_direct"] for r in rows],
            "rx_flood": [r["rx_flood"] for r in rows],
            "dups_direct": [0] * len(rows),
            "dups_flood": [0] * len(rows),
            "rx_errors": [r["rx_errors"] for r in rows],
            "total": [r["total"] for r in rows],
        })

    dups = models.query_packet_dups(h)
    dup_by_ts = {}
    for d in dups:
        dup_by_ts[d["ts"]] = d
    dup_timestamps = sorted(dup_by_ts.keys())
    def find_dups(bucket_ts):
        dd = 0
        fd = 0
        re = 0
        for dts in dup_timestamps:
            if dts <= bucket_ts:
                dd = dup_by_ts[dts]["dups_direct"]
                fd = dup_by_ts[dts]["dups_flood"]
                re = dup_by_ts[dts]["rx_errors"]
            else:
                break
        return dd, fd, re
    dups_direct_list = []
    dups_flood_list = []
    rx_errors_list = []
    for r in rows:
        dd, fd, re = find_dups(r["bucket"])
        dups_direct_list.append(dd)
        dups_flood_list.append(fd)
        rx_errors_list.append(re)
    return jsonify({
        "timestamps": [r["bucket"] for r in rows],
        "tx_direct": [r["tx_direct"] for r in rows],
        "tx_flood": [r["tx_flood"] for r in rows],
        "rx_direct": [r["rx_direct"] for r in rows],
        "rx_flood": [r["rx_flood"] for r in rows],
        "dups_direct": dups_direct_list,
        "dups_flood": dups_flood_list,
        "rx_errors": rx_errors_list,
        "total": [r["total"] for r in rows],
    })


@api.route("/packets/recent")
def packets_recent():
    limit = request.args.get("limit", 50, type=int)
    rows = models.query_packets_recent(limit)
    return jsonify(rows)


@api.route("/neighbors")
def neighbors():
    rows = models.query_neighbors()
    return jsonify(rows)


@api.route("/neighbors/history")
def neighbors_history():
    rows = models.query_neighbor_history(_hours())
    return jsonify({
        "timestamps": [r["ts"] for r in rows],
        "count": [r["count"] for r in rows],
    })


@api.route("/status")
def status():
    poller = current_app.config.get("poller")
    poller_status = poller.status if poller else {"running": False}
    return jsonify({
        **poller_status,
        "db_size_bytes": models.db_size_bytes(),
    })


@api.route("/stats/pi/health")
def stats_pi_health():
    rows = models.query_stats_pi_health(_hours())
    return jsonify({
        "timestamps":     [r["ts"] for r in rows],
        "cpu_percent":    [r["cpu_percent"] for r in rows],
        "load_1":         [r["load_1"] for r in rows],
        "load_5":         [r["load_5"] for r in rows],
        "load_15":        [r["load_15"] for r in rows],
        "mem_used_mb":    [r["mem_used_mb"] for r in rows],
        "mem_total_mb":   [r["mem_total_mb"] for r in rows],
        "mem_percent":    [r["mem_percent"] for r in rows],
        "swap_used_mb":   [r["swap_used_mb"] for r in rows],
        "swap_total_mb":  [r["swap_total_mb"] for r in rows],
        "cpu_temp":       [r["cpu_temp"] for r in rows],
        "disk_used_gb":   [r["disk_used_gb"] for r in rows],
        "disk_total_gb":  [r["disk_total_gb"] for r in rows],
        "disk_percent":   [r["disk_percent"] for r in rows],
        "uptime_secs":    [r["uptime_secs"] for r in rows],
        "process_count":  [r["process_count"] for r in rows],
    })


@api.route("/stats/pi/disk-io")
def stats_pi_disk_io():
    devices = models.query_disk_io(_hours())
    # Only use per-device data if at least one device has computed deltas
    if any(d["timestamps"] for d in devices.values()):
        return jsonify({"devices": devices})
    # Fallback to aggregate data from pi_health table
    rows = models.query_pi_disk_io(_hours())
    return jsonify({
        "devices": {
            "all": {
                "timestamps": [r["ts"] for r in rows],
                "read_kbs":   [r["read_kbs"] for r in rows],
                "write_kbs":  [r["write_kbs"] for r in rows],
            }
        }
    })


@api.route("/stats/pi/network-io")
def stats_pi_network_io():
    rows = models.query_pi_network_io(_hours())
    return jsonify({
        "timestamps": [r["ts"] for r in rows],
        "sent_kbs":   [r["sent_kbs"] for r in rows],
        "recv_kbs":   [r["recv_kbs"] for r in rows],
    })


@api.route("/stats/pi/snapshot")
def stats_pi_snapshot():
    if not HAS_PSUTIL:
        return jsonify({"error": "psutil not installed"}), 501

    cpu_pct = psutil.cpu_percent(interval=0)
    per_cpu = psutil.cpu_percent(interval=0, percpu=True)
    load_1, load_5, load_15 = os.getloadavg()
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()

    cpu_temp = None
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            for key in ("cpu_thermal", "cpu-thermal", "coretemp"):
                if key in temps and temps[key]:
                    cpu_temp = temps[key][0].current
                    break
    except (AttributeError, OSError):
        pass

    disk = psutil.disk_usage("/")
    uptime = int(time.time() - psutil.boot_time())
    proc_count = len(psutil.pids())

    # Top 10 processes by memory
    top_procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            info = p.info
            top_procs.append({
                "pid": info["pid"],
                "name": info["name"],
                "cpu_percent": round(info["cpu_percent"] or 0, 1),
                "memory_percent": round(info["memory_percent"] or 0, 1),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    top_procs.sort(key=lambda x: x["memory_percent"], reverse=True)
    top_procs = top_procs[:10]

    return jsonify({
        "cpu_percent": cpu_pct,
        "per_cpu": per_cpu,
        "load_1": round(load_1, 2),
        "load_5": round(load_5, 2),
        "load_15": round(load_15, 2),
        "mem_used_mb": round(mem.used / 1048576, 1),
        "mem_total_mb": round(mem.total / 1048576, 1),
        "mem_percent": mem.percent,
        "swap_used_mb": round(swap.used / 1048576, 1),
        "swap_total_mb": round(swap.total / 1048576, 1),
        "cpu_temp": cpu_temp,
        "disk_used_gb": round(disk.used / 1073741824, 2),
        "disk_total_gb": round(disk.total / 1073741824, 2),
        "disk_percent": disk.percent,
        "uptime_secs": uptime,
        "process_count": proc_count,
        "top_processes": top_procs,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "hostname": platform.node(),
            "python": platform.python_version(),
        },
    })


# ── Settings ──────────────────────────────────────────────

SETTINGS_DEFAULTS = {
    "power_source": "ina3221",
    "ina_solar_channel": "ch1",
    "ina_repeater_channel": "ch0",
    "flash_serial_port": config.FLASH_SERIAL_PORT,
}

SETTINGS_ALLOWED = {
    "power_source": ["onboard", "ina3221"],
    "ina_solar_channel": ["ch0", "ch1", "ch2"],
    "ina_repeater_channel": ["ch0", "ch1", "ch2"],
}

SETTINGS_FREETEXT = {"flash_serial_port"}


@api.route("/settings")
def get_settings():
    stored = models.get_all_settings()
    result = {}
    for key, default in SETTINGS_DEFAULTS.items():
        result[key] = stored.get(key, default)
    return jsonify(result)


@api.route("/settings", methods=["PUT"])
def put_settings():
    data = request.get_json(force=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Expected JSON object"}), 400
    for key, value in data.items():
        if key in SETTINGS_FREETEXT:
            if not isinstance(value, str) or not value.strip():
                return jsonify({"error": f"Invalid value for {key}: must be non-empty string"}), 400
        elif key in SETTINGS_ALLOWED:
            if value not in SETTINGS_ALLOWED[key]:
                return jsonify({"error": f"Invalid value for {key}: {value}"}), 400
        else:
            return jsonify({"error": f"Unknown setting: {key}"}), 400
        models.set_setting(key, value)
    return jsonify({"status": "ok"})


@api.route("/firmware/flash", methods=["POST"])
def firmware_flash():
    # Check if a flash is already in progress
    current = firmware_flasher.get_status()
    if current["state"] == "flashing":
        return jsonify({"error": "Flash already in progress"}), 409

    if "firmware" not in request.files:
        return jsonify({"error": "No firmware file provided"}), 400

    expected_hash = request.form.get("sha256", "").strip()
    if not expected_hash or len(expected_hash) != 64:
        return jsonify({"error": "Invalid SHA256 hash (expected 64 hex chars)"}), 400

    fw_file = request.files["firmware"]
    if not fw_file.filename or not fw_file.filename.endswith(".zip"):
        return jsonify({"error": "Firmware file must be a .zip"}), 400

    # Save uploaded file
    upload_dir = config.FIRMWARE_UPLOAD_DIR
    os.makedirs(upload_dir, exist_ok=True)
    filename = secure_filename(fw_file.filename)
    fw_path = os.path.join(upload_dir, filename)
    fw_file.save(fw_path)

    # Verify hash before starting flash
    if not firmware_flasher.verify_sha256(fw_path, expected_hash):
        os.remove(fw_path)
        return jsonify({"error": "SHA256 hash mismatch"}), 400

    # Kick off flash in background thread
    poller = current_app.config.get("poller")
    firmware_flasher.flash_firmware(fw_path, expected_hash, poller)

    return jsonify({"status": "started"})


@api.route("/firmware/status")
def firmware_status():
    return jsonify(firmware_flasher.get_status())


# ── Service Management ───────────────────────────────────

def _get_service_info(name):
    try:
        result = subprocess.run(
            ["systemctl", "show", name,
             "--property=ActiveState,ActiveEnterTimestampMonotonic"],
            capture_output=True, text=True, timeout=5,
        )
        props = {}
        for line in result.stdout.strip().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                props[k] = v

        active = props.get("ActiveState", "") == "active"
        uptime_secs = None
        if active:
            mono_us = int(props.get("ActiveEnterTimestampMonotonic", "0"))
            if mono_us > 0:
                # Read system monotonic clock to compute uptime
                now_mono = time.clock_gettime(time.CLOCK_MONOTONIC)
                uptime_secs = max(0, int(now_mono - mono_us / 1_000_000))
        return {"name": name, "active": active, "uptime_secs": uptime_secs}
    except Exception:
        return {"name": name, "active": False, "uptime_secs": None}


@api.route("/services")
def list_services():
    return jsonify([_get_service_info(s) for s in MANAGED_SERVICES])


@api.route("/services/<name>/start", methods=["POST"])
def start_service(name):
    if name not in MANAGED_SERVICES:
        return jsonify({"error": "Unknown service"}), 400

    def do_start():
        subprocess.run(["systemctl", "start", name], timeout=30)

    threading.Timer(1.0, do_start).start()
    return jsonify({"status": "ok"})


@api.route("/services/<name>/stop", methods=["POST"])
def stop_service(name):
    if name not in MANAGED_SERVICES:
        return jsonify({"error": "Unknown service"}), 400
    if name == "RepeaterWatch":
        return jsonify({"error": "Cannot stop RepeaterWatch"}), 400

    def do_stop():
        subprocess.run(["systemctl", "stop", name], timeout=30)

    threading.Timer(1.0, do_stop).start()
    return jsonify({"status": "ok"})


@api.route("/services/<name>/restart", methods=["POST"])
def restart_service(name):
    if name not in MANAGED_SERVICES:
        return jsonify({"error": "Unknown service"}), 400

    def do_restart():
        subprocess.run(["systemctl", "restart", name], timeout=30)

    # Delay so the HTTP response sends before we potentially kill ourselves
    threading.Timer(1.0, do_restart).start()
    return jsonify({"status": "ok"})


@api.route("/system/reboot", methods=["POST"])
def system_reboot():
    def do_reboot():
        subprocess.run(["systemctl", "reboot"], timeout=10)

    threading.Timer(2.0, do_reboot).start()
    return jsonify({"status": "rebooting"})


# ── Sensor Endpoints ──────────────────────────────────

@api.route("/stats/sensors/power")
def stats_sensor_power():
    return jsonify(models.query_sensor_power(_hours()))


@api.route("/stats/sensors/env")
def stats_sensor_env():
    return jsonify(models.query_sensor_env(_hours()))


@api.route("/stats/sensors/accel")
def stats_sensor_accel():
    return jsonify(models.query_sensor_accel(_hours()))


@api.route("/stats/sensors/lightning")
def stats_sensor_lightning():
    return jsonify(models.query_lightning_events(_hours()))


@api.route("/stats/sensors/lightning/summary")
def stats_sensor_lightning_summary():
    return jsonify(models.query_lightning_summary(_hours()))


@api.route("/stats/sensors/bq24074")
def stats_sensor_bq24074():
    return jsonify(models.query_bq24074_status(_hours()))


@api.route("/bq24074/status")
def bq24074_live_status():
    data = bq24074_sensor.read_status()
    if data is None:
        return jsonify({"error": "BQ24074 not available"}), 501
    return jsonify(data)


@api.route("/bq24074/charging", methods=["POST"])
def bq24074_charging():
    if not bq24074_sensor.HAS_BQ24074:
        return jsonify({"error": "BQ24074 not available"}), 501
    data = request.get_json(force=True)
    enabled = data.get("enabled", True)
    bq24074_sensor.set_charging_enabled(enabled)
    return jsonify({"status": "ok", "enabled": enabled})


@api.route("/sensors/status")
def sensors_status():
    sp = current_app.config.get("sensor_poller")
    if sp:
        return jsonify(sp.status)
    return jsonify({"running": False, "sensors": {}})


@api.route("/radio/reset", methods=["POST"])
def radio_reset():
    poller = current_app.config.get("poller")

    def do_reset():
        try:
            if poller:
                poller.stop()
            radio_gpio.reset_radio()
            time.sleep(2)  # wait for radio to boot
        finally:
            if poller:
                poller.start()

    threading.Thread(target=do_reset, daemon=True).start()
    return jsonify({"status": "ok"})


@api.route("/radio/bootloader", methods=["POST"])
def radio_bootloader():
    poller = current_app.config.get("poller")

    def do_bootloader():
        if poller:
            poller.stop()
        radio_gpio.bootloader_mode()

    threading.Thread(target=do_bootloader, daemon=True).start()
    return jsonify({"status": "ok"})


def _list_serial_by_id():
    """Return the set of symlink names in /dev/serial/by-id/."""
    by_id = "/dev/serial/by-id"
    if not os.path.isdir(by_id):
        return set()
    return set(os.listdir(by_id))


def _device_info(name):
    """Return dict with symlink name and resolved path."""
    path = os.path.realpath(os.path.join("/dev/serial/by-id", name))
    return {"name": name, "path": path}


@api.route("/radio/usb")
def radio_usb_status():
    pin = config.USB_RELAY_GPIO_PIN
    try:
        result = subprocess.run(
            ["pinctrl", "get", str(pin)],
            capture_output=True, text=True, timeout=5,
        )
        output = result.stdout.strip().lower()
        enabled = "hi" in output
        return jsonify({"enabled": enabled})
    except Exception as e:
        return jsonify({"enabled": False, "error": str(e)})


@api.route("/radio/usb", methods=["POST"])
def radio_usb_toggle():
    data = request.get_json(force=True)
    enable = data.get("enabled", True)
    pin = config.USB_RELAY_GPIO_PIN
    level = "dh" if enable else "dl"

    before = _list_serial_by_id()

    try:
        subprocess.run(
            ["pinctrl", "set", str(pin), "op", level],
            capture_output=True, text=True, timeout=5, check=True,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # Wait for USB enumeration and detect new device
    device = None
    if enable:
        for _ in range(6):
            time.sleep(1)
            after = _list_serial_by_id()
            new = after - before
            if new:
                device = _device_info(next(iter(new)))
                break

    return jsonify({"status": "ok", "enabled": enable, "device": device})
