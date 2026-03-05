from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)

try:
    import smbus2
    HAS_SMBUS = True
except ImportError:
    HAS_SMBUS = False

try:
    import RPi.GPIO as GPIO
    HAS_GPIO = True
except ImportError:
    HAS_GPIO = False

# AS3935 registers
_REG_CONFIG0 = 0x00  # AFE_GB, power down
_REG_CONFIG1 = 0x01  # Noise floor level, watchdog threshold
_REG_CONFIG2 = 0x02  # Spike rejection, min lightning
_REG_CONFIG3 = 0x03  # Interrupt register, disturbers mask, LCO_FDIV
_REG_DISTANCE = 0x07  # Distance estimation
_REG_INT_ENERGY0 = 0x04
_REG_INT_ENERGY1 = 0x05
_REG_INT_ENERGY2 = 0x06
_REG_TUNE_CAP = 0x08  # Tuning capacitor
_REG_CALIB = 0x3D  # Calibration

# Interrupt types
INT_NOISE = 0x01
INT_DISTURBER = 0x04
INT_LIGHTNING = 0x08

I2C_ADDR = 0x03
I2C_BUS = 1


class AS3935:
    def __init__(self, irq_gpio: int = 18):
        self._irq_gpio = irq_gpio
        self._bus = None
        self._events: list[dict] = []
        self._lock = threading.Lock()
        self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def init(self) -> bool:
        if not HAS_SMBUS or not HAS_GPIO:
            logger.info("AS3935: smbus2 or RPi.GPIO not available")
            return False

        try:
            self._bus = smbus2.SMBus(I2C_BUS)
            # Test read
            self._bus.read_byte_data(I2C_ADDR, 0x00)
        except Exception:
            logger.warning("AS3935 not found on I2C bus")
            return False

        try:
            self._configure()
            self._setup_irq()
            self._available = True
            logger.info("AS3935 initialized on GPIO%d", self._irq_gpio)
            return True
        except Exception:
            logger.exception("AS3935 init failed")
            return False

    def _write_reg(self, reg: int, value: int):
        self._bus.write_byte_data(I2C_ADDR, reg, value)

    def _read_reg(self, reg: int) -> int:
        return self._bus.read_byte_data(I2C_ADDR, reg)

    def _configure(self):
        # Power up, OUTDOORS mode (AFE_GB = 0x0E)
        self._write_reg(_REG_CONFIG0, 0x24 | 0x0E)
        time.sleep(0.002)

        # Noise floor level 4, watchdog threshold 2
        self._write_reg(_REG_CONFIG1, (4 << 4) | 2)

        # Spike rejection 2, min lightning 0 (1 strike)
        self._write_reg(_REG_CONFIG2, 2)

        # Enable disturber reporting (bit 5 = 0 = enabled)
        reg3 = self._read_reg(_REG_CONFIG3)
        reg3 &= ~(1 << 5)  # clear MASK_DIST
        self._write_reg(_REG_CONFIG3, reg3)

        # Tuning capacitor = 96pF (value 6 = 6*8pF = 48pF... use 12 = 96pF)
        self._write_reg(_REG_TUNE_CAP, 12)

        # Calibrate
        self._write_reg(_REG_CALIB, 0x96)
        time.sleep(0.002)

    def _setup_irq(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self._irq_gpio, GPIO.IN)
        GPIO.add_event_detect(
            self._irq_gpio, GPIO.RISING,
            callback=self._irq_handler, bouncetime=50,
        )

    def _irq_handler(self, channel):
        time.sleep(0.003)  # Wait for interrupt register to populate
        try:
            int_src = self._read_reg(_REG_CONFIG3) & 0x0F

            event = {
                "ts": int(time.time()),
                "event_type": 0,
                "distance_km": None,
                "energy": None,
            }

            if int_src == INT_LIGHTNING:
                event["event_type"] = 1
                distance = self._read_reg(_REG_DISTANCE) & 0x3F
                event["distance_km"] = distance if distance != 0x3F else None

                e0 = self._read_reg(_REG_INT_ENERGY0)
                e1 = self._read_reg(_REG_INT_ENERGY1)
                e2 = self._read_reg(_REG_INT_ENERGY2) & 0x1F
                event["energy"] = (e2 << 16) | (e1 << 8) | e0

                logger.info("Lightning detected: distance=%s km, energy=%s",
                            event["distance_km"], event["energy"])
            elif int_src == INT_DISTURBER:
                event["event_type"] = 2
                logger.debug("AS3935 disturber event")
            elif int_src == INT_NOISE:
                event["event_type"] = 3
                logger.debug("AS3935 noise event")
            else:
                return

            with self._lock:
                self._events.append(event)

        except Exception:
            logger.exception("AS3935 IRQ handler error")

    def drain_events(self) -> list[dict]:
        with self._lock:
            events = self._events
            self._events = []
        return events

    def cleanup(self):
        if HAS_GPIO and self._available:
            try:
                GPIO.remove_event_detect(self._irq_gpio)
            except Exception:
                pass
        if self._bus:
            try:
                self._bus.close()
            except Exception:
                pass
