from __future__ import annotations

import sqlite3
import threading
import time

import config


_local = threading.local()
_db_path = None


def init(db_path: str):
    global _db_path
    _db_path = db_path


def _conn() -> sqlite3.Connection:
    c = getattr(_local, "conn", None)
    if c is None:
        c = sqlite3.connect(_db_path, check_same_thread=False)
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA busy_timeout=5000")
        c.row_factory = sqlite3.Row
        _local.conn = c
    return c


def aligned_ts(epoch: float | None = None) -> int:
    t = int(epoch or time.time())
    return (t // 300) * 300


# ── Device info ──────────────────────────────────────────────

def set_device_info(key: str, value: str):
    _conn().execute(
        "INSERT OR REPLACE INTO device_info (key, value) VALUES (?, ?)",
        (key, value),
    )
    _conn().commit()


def get_device_info() -> dict:
    rows = _conn().execute("SELECT key, value FROM device_info").fetchall()
    return {r["key"]: r["value"] for r in rows}


# ── Settings ────────────────────────────────────────────────

def get_setting(key: str, default: str | None = None) -> str | None:
    row = _conn().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(key: str, value: str):
    _conn().execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, value),
    )
    _conn().commit()


def get_all_settings() -> dict:
    rows = _conn().execute("SELECT key, value FROM settings").fetchall()
    return {r[0]: r[1] for r in rows}


# ── Stats inserts ────────────────────────────────────────────

def insert_stats_core(ts: int, battery_mv, uptime_secs, errors, queue_len):
    _conn().execute(
        "INSERT OR REPLACE INTO stats_core (ts, battery_mv, uptime_secs, errors, queue_len) "
        "VALUES (?, ?, ?, ?, ?)",
        (ts, battery_mv, uptime_secs, errors, queue_len),
    )
    _conn().commit()


def insert_stats_radio(ts: int, noise_floor, tx_air_secs, rx_air_secs,
                       last_rssi=None, last_snr=None):
    _conn().execute(
        "INSERT OR REPLACE INTO stats_radio (ts, noise_floor, tx_air_secs, rx_air_secs, last_rssi, last_snr) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (ts, noise_floor, tx_air_secs, rx_air_secs, last_rssi, last_snr),
    )
    _conn().commit()


def insert_stats_packets(ts: int, recv_total, sent_total, recv_errors,
                         fwd_total, fwd_errors, direct_dups, flood_dups=None,
                         direct_tx=None, flood_tx=None,
                         direct_rx=None, flood_rx=None):
    _conn().execute(
        "INSERT OR REPLACE INTO stats_packets "
        "(ts, recv_total, sent_total, recv_errors, fwd_total, fwd_errors, "
        "direct_dups, flood_dups, direct_tx, flood_tx, direct_rx, flood_rx) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (ts, recv_total, sent_total, recv_errors, fwd_total, fwd_errors,
         direct_dups, flood_dups, direct_tx, flood_tx, direct_rx, flood_rx),
    )
    _conn().commit()


def insert_stats_extpower(ts: int, channels: list[dict]):
    vals = []
    for i in range(3):
        ch = channels[i] if i < len(channels) else {}
        vals.extend([ch.get("voltage"), ch.get("current"), ch.get("power")])
    _conn().execute(
        "INSERT OR REPLACE INTO stats_extpower "
        "(ts, ch0_voltage, ch0_current, ch0_power, "
        "ch1_voltage, ch1_current, ch1_power, "
        "ch2_voltage, ch2_current, ch2_power) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (ts, *vals),
    )
    _conn().commit()


def insert_packet(ts: int, direction, pkt_type, route, snr, rssi, score, hash_,
                   raw_hex: str | None = None):
    _conn().execute(
        "INSERT INTO packet_log (ts, direction, pkt_type, route, snr, rssi, score, hash, raw_hex) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (ts, direction, pkt_type, route, snr, rssi, score, hash_, raw_hex),
    )
    _conn().commit()


def upsert_neighbor(pubkey_prefix: str, name: str | None, device_role: str | None,
                    last_seen: int, last_snr: float | None, last_rssi: float | None,
                    lat: float | None, lon: float | None):
    _conn().execute(
        "INSERT OR REPLACE INTO neighbors "
        "(pubkey_prefix, name, device_role, last_seen, last_snr, last_rssi, lat, lon) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (pubkey_prefix, name, device_role, last_seen, last_snr, last_rssi, lat, lon),
    )
    _conn().commit()


def insert_neighbor_sighting(ts: int, pubkey_prefix: str,
                             snr: float | None = None, rssi: float | None = None):
    _conn().execute(
        "INSERT OR REPLACE INTO neighbor_sightings (ts, pubkey_prefix, snr, rssi) "
        "VALUES (?, ?, ?, ?)",
        (ts, pubkey_prefix, snr, rssi),
    )
    _conn().commit()


def delete_old_neighbors(max_age_hours: int) -> int:
    """Delete neighbors not seen in the last *max_age_hours* hours."""
    cutoff = int(time.time()) - max_age_hours * 3600
    conn = _conn()
    conn.execute(
        "DELETE FROM neighbor_sightings WHERE pubkey_prefix IN "
        "(SELECT pubkey_prefix FROM neighbors WHERE last_seen < ?)",
        (cutoff,),
    )
    cur = conn.execute("DELETE FROM neighbors WHERE last_seen < ?", (cutoff,))
    conn.commit()
    return cur.rowcount


# ── Queries ──────────────────────────────────────────────────

def _clamp_hours(hours: int) -> int:
    return max(1, min(hours, config.MAX_QUERY_HOURS))


def _since(hours: int) -> int:
    return aligned_ts() - _clamp_hours(hours) * 3600


def query_stats_core(hours: int = 24) -> list[dict]:
    rows = _conn().execute(
        "SELECT ts, battery_mv, uptime_secs, errors, queue_len "
        "FROM stats_core WHERE ts >= ? ORDER BY ts",
        (_since(hours),),
    ).fetchall()
    return [dict(r) for r in rows]


def query_stats_radio(hours: int = 24) -> list[dict]:
    rows = _conn().execute(
        "SELECT ts, noise_floor, tx_air_secs, rx_air_secs, last_rssi, last_snr "
        "FROM stats_radio WHERE ts >= ? ORDER BY ts",
        (_since(hours),),
    ).fetchall()
    return [dict(r) for r in rows]


def query_stats_packets(hours: int = 24) -> list[dict]:
    rows = _conn().execute(
        "SELECT ts, recv_total, sent_total, recv_errors, fwd_total, fwd_errors, "
        "direct_dups, flood_dups, direct_tx, flood_tx, direct_rx, flood_rx "
        "FROM stats_packets WHERE ts >= ? ORDER BY ts",
        (_since(hours),),
    ).fetchall()
    return [dict(r) for r in rows]


def query_packet_dups(hours: int = 24) -> list[dict]:
    rows = _conn().execute(
        "SELECT ts, direct_dups, flood_dups, recv_errors "
        "FROM stats_packets WHERE ts >= ? ORDER BY ts",
        (_since(hours),),
    ).fetchall()
    result = []
    prev = None
    for r in rows:
        row = dict(r)
        if prev is not None:
            dd = max(0, (row["direct_dups"] or 0) - (prev["direct_dups"] or 0))
            fd = max(0, (row["flood_dups"] or 0) - (prev["flood_dups"] or 0))
            re = max(0, (row["recv_errors"] or 0) - (prev["recv_errors"] or 0))
            result.append({"ts": row["ts"], "dups_direct": dd, "dups_flood": fd, "rx_errors": re})
        prev = row
    return result


def query_packets_activity_from_stats(hours: int = 24) -> list[dict]:
    """Derive per-interval packet counts from cumulative stats_packets counters."""
    rows = _conn().execute(
        "SELECT ts, direct_tx, flood_tx, direct_rx, flood_rx, recv_errors "
        "FROM stats_packets WHERE ts >= ? ORDER BY ts",
        (_since(hours),),
    ).fetchall()
    result = []
    prev = None
    for r in rows:
        row = dict(r)
        if prev is not None:
            dtx = max(0, (row["direct_tx"] or 0) - (prev["direct_tx"] or 0))
            ftx = max(0, (row["flood_tx"] or 0) - (prev["flood_tx"] or 0))
            drx = max(0, (row["direct_rx"] or 0) - (prev["direct_rx"] or 0))
            frx = max(0, (row["flood_rx"] or 0) - (prev["flood_rx"] or 0))
            re = max(0, (row["recv_errors"] or 0) - (prev["recv_errors"] or 0))
            result.append({
                "bucket": row["ts"],
                "tx_direct": dtx,
                "tx_flood": ftx,
                "rx_direct": drx,
                "rx_flood": frx,
                "rx_errors": re,
                "total": dtx + ftx + drx + frx,
            })
        prev = row
    return result


def query_stats_extpower(hours: int = 24) -> list[dict]:
    rows = _conn().execute(
        "SELECT ts, ch0_voltage, ch0_current, ch0_power, "
        "ch1_voltage, ch1_current, ch1_power, "
        "ch2_voltage, ch2_current, ch2_power "
        "FROM stats_extpower WHERE ts >= ? ORDER BY ts",
        (_since(hours),),
    ).fetchall()
    return [dict(r) for r in rows]


def query_packets_recent(limit: int = 50) -> list[dict]:
    rows = _conn().execute(
        "SELECT id, ts, direction, pkt_type, route, snr, rssi, score, hash, raw_hex "
        "FROM packet_log ORDER BY id DESC LIMIT ?",
        (min(limit, 500),),
    ).fetchall()
    return [dict(r) for r in rows]


def query_packets_activity(hours: int = 24, bucket_minutes: int = 15) -> list[dict]:
    bucket_secs = max(bucket_minutes, 1) * 60
    since = _since(hours)
    rows = _conn().execute(
        "SELECT (ts / ?) * ? AS bucket, "
        "SUM(CASE WHEN direction='TX' AND route IN ('D','TD') THEN 1 ELSE 0 END) AS tx_direct, "
        "SUM(CASE WHEN direction='TX' AND route IN ('F','TF') THEN 1 ELSE 0 END) AS tx_flood, "
        "SUM(CASE WHEN direction='RX' AND route IN ('D','TD') THEN 1 ELSE 0 END) AS rx_direct, "
        "SUM(CASE WHEN direction='RX' AND route IN ('F','TF') THEN 1 ELSE 0 END) AS rx_flood, "
        "COUNT(*) AS total "
        "FROM packet_log WHERE ts >= ? "
        "GROUP BY bucket ORDER BY bucket",
        (bucket_secs, bucket_secs, since),
    ).fetchall()
    return [dict(r) for r in rows]


def query_neighbors() -> list[dict]:
    rows = _conn().execute(
        "SELECT n.pubkey_prefix, n.name, n.device_role, n.last_seen, "
        "n.last_snr, n.last_rssi, n.lat, n.lon, "
        "AVG(s.snr) AS avg_snr, AVG(s.rssi) AS avg_rssi, COUNT(s.ts) AS sighting_count "
        "FROM neighbors n "
        "LEFT JOIN neighbor_sightings s ON n.pubkey_prefix = s.pubkey_prefix "
        "GROUP BY n.pubkey_prefix "
        "ORDER BY n.last_seen DESC"
    ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["avg_snr"] = round(d["avg_snr"], 1) if d["avg_snr"] is not None else None
        d["avg_rssi"] = round(d["avg_rssi"], 1) if d["avg_rssi"] is not None else None
        result.append(d)
    return result


def query_neighbor_history(hours: int = 24) -> list[dict]:
    since = _since(hours)
    rows = _conn().execute(
        "SELECT ts, COUNT(DISTINCT pubkey_prefix) AS count "
        "FROM neighbor_sightings WHERE ts >= ? "
        "GROUP BY ts ORDER BY ts",
        (since,),
    ).fetchall()
    return [dict(r) for r in rows]


def query_airtime(hours: int = 24) -> list[dict]:
    rows = _conn().execute(
        "SELECT ts, tx_air_secs, rx_air_secs "
        "FROM stats_radio WHERE ts >= ? ORDER BY ts",
        (_since(hours),),
    ).fetchall()
    result = []
    prev = None
    for r in rows:
        row = dict(r)
        if prev is not None:
            dt = row["ts"] - prev["ts"]
            if dt > 0:
                tx_delta = (row["tx_air_secs"] or 0) - (prev["tx_air_secs"] or 0)
                rx_delta = (row["rx_air_secs"] or 0) - (prev["rx_air_secs"] or 0)
                result.append({
                    "ts": row["ts"],
                    "tx_pct": round(max(0, tx_delta) / dt * 100, 2),
                    "rx_pct": round(max(0, rx_delta) / dt * 100, 2),
                })
        prev = row
    return result


def insert_stats_pi_health(ts: int, cpu_percent, load_1, load_5, load_15,
                           mem_used_mb, mem_total_mb, mem_percent,
                           swap_used_mb, swap_total_mb, cpu_temp,
                           disk_used_gb, disk_total_gb, disk_percent,
                           disk_read_bytes, disk_write_bytes,
                           net_bytes_sent, net_bytes_recv,
                           uptime_secs, process_count):
    _conn().execute(
        "INSERT OR REPLACE INTO stats_pi_health "
        "(ts, cpu_percent, load_1, load_5, load_15, "
        "mem_used_mb, mem_total_mb, mem_percent, swap_used_mb, swap_total_mb, "
        "cpu_temp, disk_used_gb, disk_total_gb, disk_percent, "
        "disk_read_bytes, disk_write_bytes, net_bytes_sent, net_bytes_recv, "
        "uptime_secs, process_count) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (ts, cpu_percent, load_1, load_5, load_15,
         mem_used_mb, mem_total_mb, mem_percent, swap_used_mb, swap_total_mb,
         cpu_temp, disk_used_gb, disk_total_gb, disk_percent,
         disk_read_bytes, disk_write_bytes, net_bytes_sent, net_bytes_recv,
         uptime_secs, process_count),
    )
    _conn().commit()


def query_stats_pi_health(hours: int = 24) -> list[dict]:
    rows = _conn().execute(
        "SELECT ts, cpu_percent, load_1, load_5, load_15, "
        "mem_used_mb, mem_total_mb, mem_percent, swap_used_mb, swap_total_mb, "
        "cpu_temp, disk_used_gb, disk_total_gb, disk_percent, "
        "disk_read_bytes, disk_write_bytes, net_bytes_sent, net_bytes_recv, "
        "uptime_secs, process_count "
        "FROM stats_pi_health WHERE ts >= ? ORDER BY ts",
        (_since(hours),),
    ).fetchall()
    return [dict(r) for r in rows]


def query_pi_disk_io(hours: int = 24) -> list[dict]:
    rows = _conn().execute(
        "SELECT ts, disk_read_bytes, disk_write_bytes "
        "FROM stats_pi_health WHERE ts >= ? ORDER BY ts",
        (_since(hours),),
    ).fetchall()
    result = []
    prev = None
    for r in rows:
        row = dict(r)
        if prev is not None:
            dt = row["ts"] - prev["ts"]
            if dt > 0:
                read_delta = (row["disk_read_bytes"] or 0) - (prev["disk_read_bytes"] or 0)
                write_delta = (row["disk_write_bytes"] or 0) - (prev["disk_write_bytes"] or 0)
                result.append({
                    "ts": row["ts"],
                    "read_kbs": round(max(0, read_delta) / dt / 1024, 2),
                    "write_kbs": round(max(0, write_delta) / dt / 1024, 2),
                })
        prev = row
    return result


def insert_disk_io(ts: int, device: str, read_bytes: int, write_bytes: int):
    _conn().execute(
        "INSERT OR REPLACE INTO stats_disk_io "
        "(ts, device, read_bytes, write_bytes) VALUES (?, ?, ?, ?)",
        (ts, device, read_bytes, write_bytes),
    )
    _conn().commit()


DISK_IO_DEVICES = ("mmcblk0", "sda")


def query_disk_io(hours: int = 24) -> dict:
    """Return per-device disk IO rates as {device: {timestamps, read_kbs, write_kbs}}."""
    placeholders = ",".join("?" for _ in DISK_IO_DEVICES)
    rows = _conn().execute(
        "SELECT ts, device, read_bytes, write_bytes "
        f"FROM stats_disk_io WHERE ts >= ? AND device IN ({placeholders}) "
        "ORDER BY device, ts",
        (_since(hours), *DISK_IO_DEVICES),
    ).fetchall()

    # Group rows by device
    by_device: dict[str, list] = {}
    for r in rows:
        d = dict(r)
        by_device.setdefault(d["device"], []).append(d)

    result = {}
    for device, dev_rows in by_device.items():
        timestamps = []
        read_kbs = []
        write_kbs = []
        prev = None
        for row in dev_rows:
            if prev is not None:
                dt = row["ts"] - prev["ts"]
                if dt > 0:
                    rd = (row["read_bytes"] or 0) - (prev["read_bytes"] or 0)
                    wd = (row["write_bytes"] or 0) - (prev["write_bytes"] or 0)
                    timestamps.append(row["ts"])
                    read_kbs.append(round(max(0, rd) / dt / 1024, 2))
                    write_kbs.append(round(max(0, wd) / dt / 1024, 2))
            prev = row
        result[device] = {
            "timestamps": timestamps,
            "read_kbs": read_kbs,
            "write_kbs": write_kbs,
        }
    return result


def query_pi_network_io(hours: int = 24) -> list[dict]:
    rows = _conn().execute(
        "SELECT ts, net_bytes_sent, net_bytes_recv "
        "FROM stats_pi_health WHERE ts >= ? ORDER BY ts",
        (_since(hours),),
    ).fetchall()
    result = []
    prev = None
    for r in rows:
        row = dict(r)
        if prev is not None:
            dt = row["ts"] - prev["ts"]
            if dt > 0:
                sent_delta = (row["net_bytes_sent"] or 0) - (prev["net_bytes_sent"] or 0)
                recv_delta = (row["net_bytes_recv"] or 0) - (prev["net_bytes_recv"] or 0)
                result.append({
                    "ts": row["ts"],
                    "sent_kbs": round(max(0, sent_delta) / dt / 1024, 2),
                    "recv_kbs": round(max(0, recv_delta) / dt / 1024, 2),
                })
        prev = row
    return result


# ── Sensor inserts ───────────────────────────────────────────

def insert_sensor_power(ts: int, ch0_v, ch0_i, ch0_p, ch1_v, ch1_i, ch1_p,
                         ch2_v=None, ch2_i=None, ch2_p=None):
    _conn().execute(
        "INSERT OR REPLACE INTO stats_sensor_power "
        "(ts, ch0_voltage, ch0_current, ch0_power, "
        "ch1_voltage, ch1_current, ch1_power, "
        "ch2_voltage, ch2_current, ch2_power) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (ts, ch0_v, ch0_i, ch0_p, ch1_v, ch1_i, ch1_p, ch2_v, ch2_i, ch2_p),
    )
    _conn().commit()


def insert_sensor_env(ts: int, temperature, humidity, pressure):
    _conn().execute(
        "INSERT OR REPLACE INTO stats_sensor_env "
        "(ts, temperature, humidity, pressure) VALUES (?, ?, ?, ?)",
        (ts, temperature, humidity, pressure),
    )
    _conn().commit()


def insert_sensor_accel(ts: int, vib_avg, vib_peak, tilt_avg, x_avg, y_avg, z_avg):
    _conn().execute(
        "INSERT OR REPLACE INTO stats_sensor_accel "
        "(ts, vib_avg, vib_peak, tilt_avg, x_avg, y_avg, z_avg) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (ts, vib_avg, vib_peak, tilt_avg, x_avg, y_avg, z_avg),
    )
    _conn().commit()


def insert_lightning_event(ts: int, event_type: int, distance_km, energy):
    _conn().execute(
        "INSERT INTO sensor_lightning_events "
        "(ts, event_type, distance_km, energy) VALUES (?, ?, ?, ?)",
        (ts, event_type, distance_km, energy),
    )
    _conn().commit()


# ── Sensor queries ───────────────────────────────────────────

def query_sensor_power(hours: int = 24) -> dict:
    rows = _conn().execute(
        "SELECT ts, ch0_voltage, ch0_current, ch0_power, "
        "ch1_voltage, ch1_current, ch1_power, "
        "ch2_voltage, ch2_current, ch2_power "
        "FROM stats_sensor_power WHERE ts >= ? ORDER BY ts",
        (_since(hours),),
    ).fetchall()
    return {
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
    }


def query_sensor_env(hours: int = 168) -> dict:
    rows = _conn().execute(
        "SELECT ts, temperature, humidity, pressure "
        "FROM stats_sensor_env WHERE ts >= ? ORDER BY ts",
        (_since(hours),),
    ).fetchall()
    return {
        "timestamps": [r["ts"] for r in rows],
        "temperature": [r["temperature"] for r in rows],
        "humidity": [r["humidity"] for r in rows],
        "pressure": [r["pressure"] for r in rows],
    }


def query_sensor_accel(hours: int = 24) -> dict:
    rows = _conn().execute(
        "SELECT ts, vib_avg, vib_peak, tilt_avg, x_avg, y_avg, z_avg "
        "FROM stats_sensor_accel WHERE ts >= ? ORDER BY ts",
        (_since(hours),),
    ).fetchall()
    return {
        "timestamps": [r["ts"] for r in rows],
        "vib_avg": [r["vib_avg"] for r in rows],
        "vib_peak": [r["vib_peak"] for r in rows],
        "tilt_avg": [r["tilt_avg"] for r in rows],
        "x_avg": [r["x_avg"] for r in rows],
        "y_avg": [r["y_avg"] for r in rows],
        "z_avg": [r["z_avg"] for r in rows],
    }


def query_lightning_events(hours: int = 720) -> list[dict]:
    rows = _conn().execute(
        "SELECT id, ts, event_type, distance_km, energy "
        "FROM sensor_lightning_events WHERE ts >= ? ORDER BY ts DESC",
        (_since(hours),),
    ).fetchall()
    return [dict(r) for r in rows]


def query_lightning_summary(hours: int = 24) -> list[dict]:
    since = _since(hours)
    rows = _conn().execute(
        "SELECT (ts / 3600) * 3600 AS hour, event_type, COUNT(*) AS count "
        "FROM sensor_lightning_events WHERE ts >= ? "
        "GROUP BY hour, event_type ORDER BY hour",
        (since,),
    ).fetchall()
    return [dict(r) for r in rows]


# ── BQ24074 charger ──────────────────────────────────────────

def insert_bq24074_status(ts: int, charging: bool, pgood: bool):
    _conn().execute(
        "INSERT OR REPLACE INTO stats_bq24074 (ts, charging, pgood) "
        "VALUES (?, ?, ?)",
        (ts, int(charging), int(pgood)),
    )
    _conn().commit()


def query_bq24074_status(hours: int = 24) -> dict:
    rows = _conn().execute(
        "SELECT ts, charging, pgood "
        "FROM stats_bq24074 WHERE ts >= ? ORDER BY ts",
        (_since(hours),),
    ).fetchall()
    return {
        "timestamps": [r["ts"] for r in rows],
        "charging": [r["charging"] for r in rows],
        "pgood": [r["pgood"] for r in rows],
    }


def db_size_bytes() -> int:
    import os
    try:
        return os.path.getsize(_db_path)
    except OSError:
        return 0
