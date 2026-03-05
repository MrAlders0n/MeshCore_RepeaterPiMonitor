from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:
    import board
    import adafruit_ina3221
    HAS_INA3221 = True
except ImportError:
    HAS_INA3221 = False


def read() -> dict | None:
    """Read INA3221 at 0x40. Returns ch0 (battery) and ch1 (load) data."""
    if not HAS_INA3221:
        return None

    for attempt in range(3):
        try:
            i2c = board.I2C()
            ina = adafruit_ina3221.INA3221(i2c, address=0x40)
            return {
                "ch0_voltage": round(ina.bus_voltage(0), 4),
                "ch0_current": round(ina.current(0), 2),
                "ch0_power": round(ina.bus_voltage(0) * ina.current(0), 2),
                "ch1_voltage": round(ina.bus_voltage(1), 4),
                "ch1_current": round(ina.current(1), 2),
                "ch1_power": round(ina.bus_voltage(1) * ina.current(1), 2),
            }
        except Exception:
            if attempt == 2:
                logger.exception("INA3221 read failed after 3 attempts")
    return None
