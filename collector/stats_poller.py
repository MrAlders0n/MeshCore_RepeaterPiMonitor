from __future__ import annotations

import logging
import os
import threading
import time

import config

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from database import models
from database.retention import purge_old_data
from database.schema import init_db
from collector.packet_parser import parse_info_line, decode_advert
from collector.serial_reader import SerialReader
from collector.startup import collect_device_info

logger = logging.getLogger(__name__)


class StatsPoller:
    def __init__(self):
        self.reader = SerialReader()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_poll: float = 0
        self._poll_count: int = 0
        self._error_count: int = 0

    @property
    def status(self) -> dict:
        return {
            "serial_connected": self.reader.connected,
            "serial_port": config.SERIAL_PORT,
            "last_poll": self._last_poll,
            "poll_count": self._poll_count,
            "error_count": self._error_count,
            "running": self._thread is not None and self._thread.is_alive(),
        }

    def start(self):
        self._stop_event.clear()
        self.reader.set_packet_callback(self._on_packet)
        self._thread = threading.Thread(target=self._run, daemon=True, name="stats-poller")
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)
        self.reader.disconnect()

    def _run(self):
        self._connect_with_retry()

        if self.reader.connected:
            collect_device_info(self.reader)

        while not self._stop_event.is_set():
            ts = models.aligned_ts()

            # Pi health — always collect (no serial needed)
            self._poll_pi_health(ts)

            if not self.reader.connected:
                self._connect_with_retry()

            if self.reader.connected:
                try:
                    self._poll_serial(ts)
                    self._last_poll = time.time()
                    self._poll_count += 1
                except Exception:
                    logger.exception("Error during poll cycle")
                    self._error_count += 1

            # Purge old data once per cycle
            try:
                conn = init_db(config.DB_PATH)
                purge_old_data(conn)
                conn.close()
            except Exception:
                logger.exception("Error during retention purge")

            self._wait_next_cycle()

    def _connect_with_retry(self):
        for attempt in range(3):
            if self.reader.connect():
                return
            logger.warning("Connection attempt %d failed, retrying...", attempt + 1)
            time.sleep(5)

    def _wait_next_cycle(self):
        next_ts = models.aligned_ts(time.time() + config.POLL_INTERVAL_SECS)
        while not self._stop_event.is_set():
            remaining = next_ts - time.time()
            if remaining <= 0:
                break
            self._stop_event.wait(min(remaining, 5))
            self.reader.read_background_lines()

    def _poll_serial(self, ts: int):
        # stats-core
        data = self.reader.send_command_json("stats-core")
        if data:
            models.insert_stats_core(
                ts,
                battery_mv=data.get("battery_mv"),
                uptime_secs=data.get("uptime_secs"),
                errors=data.get("errors"),
                queue_len=data.get("queue_len"),
            )

        # stats-radio
        data = self.reader.send_command_json("stats-radio")
        if data:
            models.insert_stats_radio(
                ts,
                noise_floor=data.get("noise_floor"),
                tx_air_secs=data.get("tx_air_secs"),
                rx_air_secs=data.get("rx_air_secs"),
                last_rssi=data.get("last_rssi"),
                last_snr=data.get("last_snr"),
            )

        # stats-packets
        data = self.reader.send_command_json("stats-packets")
        if data:
            models.insert_stats_packets(
                ts,
                recv_total=data.get("recv_total"),
                sent_total=data.get("sent_total"),
                recv_errors=data.get("recv_errors"),
                fwd_total=data.get("fwd_total"),
                fwd_errors=data.get("fwd_errors"),
                direct_dups=data.get("direct_dups"),
                flood_dups=data.get("flood_dups"),
            )

        # stats-extpower (only when using INA3221 power source)
        if models.get_setting("power_source", "ina3221") != "ina3221":
            return
        data = self.reader.send_command_json("stats-extpower")
        if data:
            channels = []
            for ch_num in range(1, 4):
                v_mv = data.get(f"ch{ch_num}_voltage_mv")
                i_ma = data.get(f"ch{ch_num}_current_ma")
                v = v_mv / 1000.0 if v_mv is not None else None
                i = i_ma if i_ma is not None else None
                p = (v_mv * i_ma / 1000.0) if v_mv is not None and i_ma is not None else None
                channels.append({"voltage": v, "current": i, "power": p})
            models.insert_stats_extpower(ts, channels)

    def _poll_pi_health(self, ts: int):
        if not HAS_PSUTIL:
            return
        try:
            cpu_pct = psutil.cpu_percent(interval=1)
            load_1, load_5, load_15 = os.getloadavg()
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()

            cpu_temp = None
            temps = psutil.sensors_temperatures()
            if temps:
                for key in ("cpu_thermal", "cpu-thermal", "coretemp"):
                    if key in temps and temps[key]:
                        cpu_temp = temps[key][0].current
                        break

            disk = psutil.disk_usage("/")
            disk_io = psutil.disk_io_counters()
            net_io = psutil.net_io_counters()
            uptime = int(time.time() - psutil.boot_time())
            proc_count = len(psutil.pids())

            models.insert_stats_pi_health(
                ts,
                cpu_percent=cpu_pct,
                load_1=round(load_1, 2),
                load_5=round(load_5, 2),
                load_15=round(load_15, 2),
                mem_used_mb=round(mem.used / 1048576, 1),
                mem_total_mb=round(mem.total / 1048576, 1),
                mem_percent=mem.percent,
                swap_used_mb=round(swap.used / 1048576, 1),
                swap_total_mb=round(swap.total / 1048576, 1),
                cpu_temp=cpu_temp,
                disk_used_gb=round(disk.used / 1073741824, 2),
                disk_total_gb=round(disk.total / 1073741824, 2),
                disk_percent=disk.percent,
                disk_read_bytes=disk_io.read_bytes if disk_io else None,
                disk_write_bytes=disk_io.write_bytes if disk_io else None,
                net_bytes_sent=net_io.bytes_sent if net_io else None,
                net_bytes_recv=net_io.bytes_recv if net_io else None,
                uptime_secs=uptime,
                process_count=proc_count,
            )
        except Exception:
            logger.exception("Error collecting Pi health metrics")

    def _on_packet(self, info_line: str, raw_hex: str | None):
        parsed = parse_info_line(info_line)
        if not parsed:
            return

        ts = int(time.time())

        # Log every packet
        models.insert_packet(
            ts,
            direction=parsed["direction"],
            pkt_type=parsed["type"],
            route=parsed["route"],
            snr=parsed["snr"],
            rssi=parsed["rssi"],
            score=parsed["score"],
            hash_=parsed["hash"],
            raw_hex=raw_hex,
        )

        # Decode adverts (type=4) for neighbor tracking
        # Only Repeaters (2) and Room Servers (3) count as neighbors
        if parsed["type"] == 4 and raw_hex:
            advert = decode_advert(raw_hex)
            if advert and advert["device_role"] in (2, 3):
                # Only track direct (0-hop) RX adverts as neighbors
                if parsed["direction"] == "RX" and parsed["route"] == "D":
                    models.upsert_neighbor(
                        pubkey_prefix=advert["pubkey_prefix"],
                        name=advert["name"],
                        device_role=advert["device_role_name"],
                        last_seen=ts,
                        last_snr=parsed["snr"],
                        last_rssi=parsed["rssi"],
                        lat=advert["lat"],
                        lon=advert["lon"],
                    )
                    models.insert_neighbor_sighting(
                        models.aligned_ts(ts),
                        advert["pubkey_prefix"],
                        snr=parsed["snr"],
                        rssi=parsed["rssi"],
                    )
                    logger.info(
                        "Neighbor: %s (%s) SNR=%s lat=%s lon=%s",
                        advert["name"], advert["device_role_name"],
                        parsed["snr"], advert["lat"], advert["lon"],
                    )
