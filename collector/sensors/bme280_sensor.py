from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:
    import board
    from adafruit_bme280 import basic as adafruit_bme280
    HAS_BME280 = True
except ImportError:
    HAS_BME280 = False


def read() -> dict | None:
    """Read BME280 at 0x77. Returns temperature (C), humidity (%), pressure (hPa)."""
    if not HAS_BME280:
        return None

    for attempt in range(3):
        try:
            i2c = board.I2C()
            bme = adafruit_bme280.Adafruit_BME280_I2C(i2c, address=0x77)
            return {
                "temperature": round(bme.temperature, 2),
                "humidity": round(bme.relative_humidity, 2),
                "pressure": round(bme.pressure, 2),
            }
        except Exception:
            if attempt == 2:
                logger.exception("BME280 read failed after 3 attempts")
    return None
