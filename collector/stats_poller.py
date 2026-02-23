from __future__ import annotations

import logging
import threading
import time

import config
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
            if not self.reader.connected:
                self._connect_with_retry()
                if not self.reader.connected:
                    self._stop_event.wait(30)
                    continue

            try:
                self._poll_all()
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

    def _poll_all(self):
        ts = models.aligned_ts()

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
            )

        # stats-extpower
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
