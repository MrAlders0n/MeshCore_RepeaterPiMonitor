from __future__ import annotations

import logging
import math

logger = logging.getLogger(__name__)

try:
    import board
    import adafruit_lis2dw12
    HAS_LIS2DW12 = True
except ImportError:
    HAS_LIS2DW12 = False


def read() -> dict | None:
    """Read LIS2DW12 at 0x18. Returns x, y, z, vibration magnitude, tilt angle."""
    if not HAS_LIS2DW12:
        return None

    for attempt in range(3):
        try:
            i2c = board.I2C()
            accel = adafruit_lis2dw12.LIS2DW12(i2c, address=0x18)
            x, y, z = accel.acceleration
            magnitude = math.sqrt(x * x + y * y + z * z)
            # Tilt angle from vertical (z-axis alignment with gravity)
            tilt = math.degrees(math.acos(min(1.0, max(-1.0, z / magnitude)))) if magnitude > 0 else 0.0
            return {
                "x": round(x, 4),
                "y": round(y, 4),
                "z": round(z, 4),
                "magnitude": round(magnitude, 4),
                "tilt": round(tilt, 2),
            }
        except Exception:
            if attempt == 2:
                logger.exception("LIS2DW12 read failed after 3 attempts")
    return None
