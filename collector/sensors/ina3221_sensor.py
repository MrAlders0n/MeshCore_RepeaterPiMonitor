from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

try:
    import board
    import adafruit_ina3221
    HAS_INA3221 = True
except ImportError:
    HAS_INA3221 = False
    logger.info("INA3221: adafruit_ina3221 or board library not available")

# Persistent instance — INA3221 needs settling time after init
_ina = None


def _get_ina():
    global _ina
    if _ina is None:
        i2c = board.I2C()
        _ina = adafruit_ina3221.INA3221(i2c, address=0x40, enable=[0, 1, 2])
        time.sleep(1)  # Allow first conversion cycle to complete
        logger.info("INA3221 initialized at 0x40, all channels enabled")
    return _ina


def read() -> dict | None:
    """Read INA3221 at 0x40. Returns ch0 (battery), ch1 (load), ch2 (solar) data."""
    if not HAS_INA3221:
        return None

    for attempt in range(3):
        try:
            ina = _get_ina()
            ch0_v = ina[0].bus_voltage
            ch0_i = ina[0].current
            ch1_v = ina[1].bus_voltage
            ch1_i = ina[1].current
            ch2_v = ina[2].bus_voltage
            ch2_i = ina[2].current
            return {
                "ch0_voltage": round(ch0_v, 4),
                "ch0_current": round(ch0_i, 2),
                "ch0_power": round(ch0_v * ch0_i, 2),
                "ch1_voltage": round(ch1_v, 4),
                "ch1_current": round(ch1_i, 2),
                "ch1_power": round(ch1_v * ch1_i, 2),
                "ch2_voltage": round(ch2_v, 4),
                "ch2_current": round(ch2_i, 2),
                "ch2_power": round(ch2_v * ch2_i, 2),
            }
        except Exception:
            _ina = None  # Reset on error so next attempt reinitializes
            if attempt == 2:
                logger.exception("INA3221 read failed after 3 attempts")
    return None
