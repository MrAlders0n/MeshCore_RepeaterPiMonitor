from __future__ import annotations

import logging
import math
import threading
import time

import config
from database import models
from collector.sensors import ina3221_sensor, bme280_sensor, lis2dw12_sensor, bq24074_sensor
from collector.sensors.as3935_sensor import AS3935

logger = logging.getLogger(__name__)

# Polling intervals (seconds)
POLL_TICK = 5          # Base loop tick
POWER_INTERVAL = 10    # INA3221 every 10s
ENV_INTERVAL = 60      # BME280 every 60s
ACCEL_INTERVAL = 5     # LIS2DW12 every 5s


def _aligned(t: float, interval: int) -> int:
    """Align epoch time to interval boundary."""
    return (int(t) // interval) * interval


class SensorPoller:
    def __init__(self):
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._as3935 = AS3935(irq_gpio=config.AS3935_IRQ_GPIO)
        self._sensor_status: dict[str, dict] = {
            "ina3221": {"ok": False, "last_error": None},
            "bme280": {"ok": False, "last_error": None},
            "lis2dw12": {"ok": False, "last_error": None},
            "as3935": {"ok": False, "last_error": None},
            "bq24074": {"ok": False, "last_error": None},
        }

    @property
    def status(self) -> dict:
        return {
            "running": self._thread is not None and self._thread.is_alive(),
            "sensors": dict(self._sensor_status),
        }

    def start(self):
        self._stop_event.clear()
        self._as3935.init()
        self._sensor_status["as3935"]["ok"] = self._as3935.available

        # Log sensor library availability at startup
        self._sensor_status["ina3221"]["ok"] = ina3221_sensor.HAS_INA3221
        self._sensor_status["bme280"]["ok"] = bme280_sensor.HAS_BME280
        self._sensor_status["lis2dw12"]["ok"] = lis2dw12_sensor.HAS_LIS2DW12
        self._sensor_status["bq24074"]["ok"] = bq24074_sensor.HAS_BQ24074

        available = []
        missing = []
        for name, mod in [("ina3221", ina3221_sensor), ("bme280", bme280_sensor),
                          ("lis2dw12", lis2dw12_sensor), ("bq24074", bq24074_sensor)]:
            flag = getattr(mod, "HAS_" + name.upper(), False)
            (available if flag else missing).append(name)
        if self._as3935.available:
            available.append("as3935")
        else:
            missing.append("as3935")

        logger.info("SensorPoller starting — available: [%s], missing: [%s]",
                     ", ".join(available) or "none",
                     ", ".join(missing) or "none")
        logger.info("Intervals: power=%ds, env=%ds, accel=%ds",
                     POWER_INTERVAL, ENV_INTERVAL, ACCEL_INTERVAL)

        self._thread = threading.Thread(target=self._run, daemon=True, name="sensor-poller")
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)
        self._as3935.cleanup()

    def _run(self):
        logger.info("SensorPoller thread started")
        try:
            self._run_loop()
        except Exception:
            logger.exception("SensorPoller thread crashed")

    def _run_loop(self):
        last_power = 0
        last_env = 0
        last_accel = 0
        cycle = 0

        while not self._stop_event.is_set():
            now = time.time()

            # INA3221 + BQ24074 — every 10s
            if now - last_power >= POWER_INTERVAL:
                self._poll_power(now)
                self._poll_bq24074(now)
                last_power = now

            # LIS2DW12 — every 5s
            if now - last_accel >= ACCEL_INTERVAL:
                self._poll_accel(now)
                last_accel = now

            # BME280 — every 60s
            if now - last_env >= ENV_INTERVAL:
                self._poll_env(now)
                last_env = now

            # AS3935 — drain events every tick, adaptive noise floor
            self._store_lightning_events()
            self._as3935.maybe_lower_noise_floor()

            # Log summary every 5 minutes
            cycle += 1
            if cycle % (300 // POLL_TICK) == 0:
                logger.info("SensorPoller alive — power=%s bme=%s accel=%s as3935=%s bq24074=%s",
                            self._sensor_status["ina3221"]["ok"],
                            self._sensor_status["bme280"]["ok"],
                            self._sensor_status["lis2dw12"]["ok"],
                            self._sensor_status["as3935"]["ok"],
                            self._sensor_status["bq24074"]["ok"])

            # Sleep until next tick
            elapsed = time.time() - now
            sleep = max(0, POLL_TICK - elapsed)
            if sleep > 0:
                self._stop_event.wait(sleep)

    def _poll_power(self, now: float):
        try:
            data = ina3221_sensor.read()
            if data is not None:
                ts = _aligned(now, POWER_INTERVAL)
                models.insert_sensor_power(
                    ts,
                    ch0_v=data["ch0_voltage"],
                    ch0_i=data["ch0_current"],
                    ch0_p=data["ch0_power"],
                    ch1_v=data["ch1_voltage"],
                    ch1_i=data["ch1_current"],
                    ch1_p=data["ch1_power"],
                    ch2_v=data.get("ch2_voltage"),
                    ch2_i=data.get("ch2_current"),
                    ch2_p=data.get("ch2_power"),
                )
                self._sensor_status["ina3221"]["ok"] = True
            else:
                self._sensor_status["ina3221"]["ok"] = False
        except Exception as e:
            self._sensor_status["ina3221"]["last_error"] = str(e)
            logger.exception("INA3221 poll error")

    def _poll_bq24074(self, now: float):
        try:
            data = bq24074_sensor.read_status()
            if data is not None:
                ts = _aligned(now, POWER_INTERVAL)
                models.insert_bq24074_status(
                    ts,
                    charging=data["charging"],
                    pgood=data["power_good"],
                )
                self._sensor_status["bq24074"]["ok"] = True
            else:
                self._sensor_status["bq24074"]["ok"] = False
        except Exception as e:
            self._sensor_status["bq24074"]["last_error"] = str(e)
            logger.exception("BQ24074 poll error")

    def _poll_env(self, now: float):
        try:
            data = bme280_sensor.read()
            if data is not None:
                ts = _aligned(now, ENV_INTERVAL)
                models.insert_sensor_env(
                    ts,
                    temperature=data["temperature"],
                    humidity=data["humidity"],
                    pressure=data["pressure"],
                )
                self._sensor_status["bme280"]["ok"] = True
            else:
                self._sensor_status["bme280"]["ok"] = False
        except Exception as e:
            self._sensor_status["bme280"]["last_error"] = str(e)
            logger.exception("BME280 poll error")

    def _poll_accel(self, now: float):
        try:
            data = lis2dw12_sensor.read()
            if data is not None:
                ts = _aligned(now, ACCEL_INTERVAL)
                models.insert_sensor_accel(
                    ts,
                    vib_avg=data["magnitude"],
                    vib_peak=data["magnitude"],
                    tilt_avg=data["tilt"],
                    x_avg=data["x"],
                    y_avg=data["y"],
                    z_avg=data["z"],
                )
                self._sensor_status["lis2dw12"]["ok"] = True
            else:
                self._sensor_status["lis2dw12"]["ok"] = False
        except Exception as e:
            self._sensor_status["lis2dw12"]["last_error"] = str(e)
            logger.exception("LIS2DW12 poll error")

    def _store_lightning_events(self):
        events = self._as3935.drain_events()
        for evt in events:
            try:
                models.insert_lightning_event(
                    ts=evt["ts"],
                    event_type=evt["event_type"],
                    distance_km=evt["distance_km"],
                    energy=evt["energy"],
                )
            except Exception:
                logger.exception("Failed to store lightning event")
