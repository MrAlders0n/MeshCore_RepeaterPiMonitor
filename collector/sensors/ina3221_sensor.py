from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:
    import board
    import adafruit_ina3221
    HAS_INA3221 = True
except ImportError:
    HAS_INA3221 = False
    logger.info("INA3221: adafruit_ina3221 or board library not available")


def read() -> dict | None:
    """Read INA3221 at 0x40. Returns ch0 (battery) and ch1 (load) data."""
    if not HAS_INA3221:
        return None

    for attempt in range(3):
        try:
            i2c = board.I2C()
            ina = adafruit_ina3221.INA3221(i2c, address=0x40, enable=[0, 1, 2])
            # Explicitly ensure ch1 is enabled
            ina[1].enable(True)
            ch0_v = ina[0].bus_voltage
            ch0_i = ina[0].current
            ch0_sv = ina[0].shunt_voltage
            ch1_v = ina[1].bus_voltage
            ch1_i = ina[1].current
            ch1_sv = ina[1].shunt_voltage
            if attempt == 0:
                logger.info("INA3221 raw: ch0 bus=%.4fV shunt=%.4fmV i=%.2fmA enabled=%s | "
                            "ch1 bus=%.4fV shunt=%.4fmV i=%.2fmA enabled=%s",
                             ch0_v, ch0_sv, ch0_i, ina[0].enabled,
                             ch1_v, ch1_sv, ch1_i, ina[1].enabled)
            return {
                "ch0_voltage": round(ch0_v, 4),
                "ch0_current": round(ch0_i, 2),
                "ch0_power": round(ch0_v * ch0_i, 2),
                "ch1_voltage": round(ch1_v, 4),
                "ch1_current": round(ch1_i, 2),
                "ch1_power": round(ch1_v * ch1_i, 2),
            }
        except Exception:
            if attempt == 2:
                logger.exception("INA3221 read failed after 3 attempts")
    return None
