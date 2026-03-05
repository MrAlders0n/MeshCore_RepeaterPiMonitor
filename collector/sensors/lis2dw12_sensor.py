from __future__ import annotations

import logging
import math
import struct

logger = logging.getLogger(__name__)

try:
    import smbus2
    HAS_LIS2DW12 = True
except ImportError:
    HAS_LIS2DW12 = False
    logger.info("LIS2DW12: smbus2 not available")

I2C_ADDR = 0x18
I2C_BUS = 1

# Registers
_WHO_AM_I = 0x0F
_CTRL1 = 0x20
_CTRL6 = 0x25
_OUT_X_L = 0x28

_WHO_AM_I_VAL = 0x44  # Expected WHO_AM_I response

# Scale: +/- 2g default, sensitivity 0.244 mg/LSB (14-bit mode)
_SENSITIVITY = 0.000244  # g per LSB
_G = 9.80665  # m/s^2

_initialized = False


def _init_sensor(bus: smbus2.SMBus):
    global _initialized
    who = bus.read_byte_data(I2C_ADDR, _WHO_AM_I)
    if who != _WHO_AM_I_VAL:
        raise RuntimeError(f"LIS2DW12 WHO_AM_I mismatch: got 0x{who:02X}, expected 0x{_WHO_AM_I_VAL:02X}")

    # CTRL1: ODR=25Hz (0011), High-Performance mode (01), LP_MODE=00
    bus.write_byte_data(I2C_ADDR, _CTRL1, 0x34)
    # CTRL6: +/- 2g (default 00), low-noise enabled (bit 2)
    bus.write_byte_data(I2C_ADDR, _CTRL6, 0x04)
    _initialized = True


def read() -> dict | None:
    """Read LIS2DW12 at 0x18 via smbus2. Returns x, y, z, vibration magnitude, tilt angle."""
    if not HAS_LIS2DW12:
        return None

    for attempt in range(3):
        try:
            bus = smbus2.SMBus(I2C_BUS)
            try:
                if not _initialized:
                    _init_sensor(bus)

                # Read 6 bytes: X_L, X_H, Y_L, Y_H, Z_L, Z_H
                raw = bus.read_i2c_block_data(I2C_ADDR, _OUT_X_L | 0x80, 6)
                x_raw, y_raw, z_raw = struct.unpack('<hhh', bytes(raw))

                # 14-bit left-justified in 16-bit, shift right by 2
                x_raw >>= 2
                y_raw >>= 2
                z_raw >>= 2

                # Convert to m/s^2
                x = x_raw * _SENSITIVITY * _G
                y = y_raw * _SENSITIVITY * _G
                z = z_raw * _SENSITIVITY * _G

                magnitude = math.sqrt(x * x + y * y + z * z)
                tilt = math.degrees(math.acos(min(1.0, max(-1.0, z / magnitude)))) if magnitude > 0 else 0.0

                return {
                    "x": round(x, 4),
                    "y": round(y, 4),
                    "z": round(z, 4),
                    "magnitude": round(magnitude, 4),
                    "tilt": round(tilt, 2),
                }
            finally:
                bus.close()
        except Exception:
            if attempt == 2:
                logger.exception("LIS2DW12 read failed after 3 attempts")
    return None
