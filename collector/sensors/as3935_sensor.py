from __future__ import annotations

import logging
import threading
import time

import config

logger = logging.getLogger(__name__)

try:
    import smbus2
    HAS_SMBUS = True
except ImportError:
    HAS_SMBUS = False

try:
    import lgpio
    _GPIO_LIB = "lgpio"
    HAS_GPIO = True
except ImportError:
    try:
        import RPi.GPIO as _rpigpio
        _GPIO_LIB = "rpigpio"
        HAS_GPIO = True
    except ImportError:
        _GPIO_LIB = None
        HAS_GPIO = False

# AS3935 registers (from DFRobot_AS3935_Lib)
_REG_CONFIG0 = 0x00
_REG_CONFIG1 = 0x01
_REG_CONFIG2 = 0x02
_REG_CONFIG3 = 0x03
_REG_ENERGY0 = 0x04
_REG_ENERGY1 = 0x05
_REG_ENERGY2 = 0x06
_REG_DISTANCE = 0x07
_REG_TUNE_CAP = 0x08
_REG_TRCO_CAL = 0x3A
_REG_SRCO_CAL = 0x3B
_REG_CALIB = 0x3D

# Interrupt sources (from register 0x03 bits [3:0])
INT_NOISE = 0x01
INT_DISTURBER = 0x04
INT_LIGHTNING = 0x08

I2C_ADDR = 0x03  # Reserved address — requires force=True with smbus2
I2C_BUS = 1

# DFRobot defaults
CAPACITANCE = 96
OUTDOORS_AFE = 0x0E
INDOORS_AFE = 0x12

# Adaptive noise floor limits
_NF_MIN = 1
_NF_MAX = 7
_NF_LOWER_INTERVAL = 120  # seconds — try lowering noise floor every 2 min


class AS3935:
    def __init__(self, irq_gpio: int = 18):
        self._irq_gpio = irq_gpio
        self._bus: smbus2.SMBus | None = None
        self._gpio_handle = None  # lgpio chip handle
        self._lgpio_cb = None     # lgpio callback handle
        self._events: list[dict] = []
        self._lock = threading.Lock()
        self._available = False
        self._noise_floor: int = config.AS3935_NOISE_FLOOR
        self._last_nf_lower: float = 0.0

    @property
    def available(self) -> bool:
        return self._available

    def init(self) -> bool:
        if not HAS_SMBUS or not HAS_GPIO:
            logger.info("AS3935: smbus2=%s RPi.GPIO=%s", HAS_SMBUS, HAS_GPIO)
            return False

        try:
            self._bus = smbus2.SMBus(I2C_BUS)
            # Test read — force=True required for reserved address 0x03
            val = self._bus.read_byte_data(I2C_ADDR, _REG_CONFIG0, force=True)
            logger.info("AS3935 found at 0x%02X (reg0=0x%02X)", I2C_ADDR, val)
        except Exception:
            logger.warning("AS3935 not found at 0x%02X on I2C bus %d", I2C_ADDR, I2C_BUS)
            return False

        try:
            self._reset()
            self._configure()
            self._setup_irq()
            self._available = True
            logger.info("AS3935 initialized — GPIO%d, cap=%dpF, mode=%s, noise=%d, watchdog=%d, spike=%d, min_strikes=%d, min_dist=%dkm, gpio_lib=%s",
                        self._irq_gpio, CAPACITANCE, config.AS3935_AFE_MODE,
                        config.AS3935_NOISE_FLOOR, config.AS3935_WATCHDOG,
                        config.AS3935_SPIKE_REJECTION, config.AS3935_MIN_STRIKES,
                        config.AS3935_MIN_DISTANCE, _GPIO_LIB)
            return True
        except Exception:
            logger.exception("AS3935 init failed")
            return False

    def _write_reg(self, reg: int, value: int):
        self._bus.write_byte_data(I2C_ADDR, reg, value, force=True)

    def _read_reg(self, reg: int) -> int:
        return self._bus.read_byte_data(I2C_ADDR, reg, force=True)

    def _sing_reg_write(self, reg: int, mask: int, data: int):
        """Read-modify-write a register (DFRobot pattern)."""
        old = self._read_reg(reg)
        new = (old & ~mask) | data
        self._write_reg(reg, new)

    def _reset(self):
        """Send direct command to reset all registers to defaults."""
        err = self._write_reg(0x3C, 0x96)
        time.sleep(0.002)
        # Verify reset by reading reg0 — default value has PWD=0
        val = self._read_reg(_REG_CONFIG0)
        logger.debug("AS3935 reset — reg0=0x%02X", val)

    def _configure(self):
        """Configure following DFRobot detailed example sequence."""
        # Power up (clear PWD bit 0 in reg0)
        self._sing_reg_write(_REG_CONFIG0, 0x01, 0x00)
        time.sleep(0.002)

        # Set AFE mode (AFE_GB bits [5:1] in reg0)
        afe = INDOORS_AFE if config.AS3935_AFE_MODE == "indoor" else OUTDOORS_AFE
        self._sing_reg_write(_REG_CONFIG0, 0x3E, afe << 1)

        # MASK_DIST bit 5 in reg3: 0x20 = mask (suppress), 0x00 = report
        self._sing_reg_write(_REG_CONFIG3, 0x20, 0x20 if config.AS3935_MASK_DISTURBER else 0x00)

        # Clear IRQ output source (bits [7:6] in reg3)
        self._sing_reg_write(_REG_CONFIG3, 0xC0, 0x00)
        time.sleep(0.5)

        # Set tuning capacitor — value is cap_pF / 8
        cap_val = CAPACITANCE // 8
        self._sing_reg_write(_REG_TUNE_CAP, 0x0F, cap_val)

        # Noise floor level (bits [6:4] in reg1)
        self._sing_reg_write(_REG_CONFIG1, 0x70, config.AS3935_NOISE_FLOOR << 4)

        # Watchdog threshold (bits [3:0] in reg1)
        self._sing_reg_write(_REG_CONFIG1, 0x0F, config.AS3935_WATCHDOG)

        # Spike rejection (bits [3:0] in reg2)
        self._sing_reg_write(_REG_CONFIG2, 0x0F, config.AS3935_SPIKE_REJECTION)

        # Minimum number of lightning strikes before interrupt (bits [5:4] in reg2)
        # 0=1, 1=5, 2=9, 3=16
        min_ligh_map = {1: 0, 5: 1, 9: 2, 16: 3}
        min_ligh_bits = min_ligh_map.get(config.AS3935_MIN_STRIKES, 1)  # default 5
        self._sing_reg_write(_REG_CONFIG2, 0x30, min_ligh_bits << 4)

        # Calibrate RCO
        self._write_reg(_REG_CALIB, 0x96)
        time.sleep(0.002)
        # Set SRCO display on IRQ
        self._sing_reg_write(_REG_TUNE_CAP, 0x40, 0x40)
        time.sleep(0.002)
        # Clear SRCO display
        self._sing_reg_write(_REG_TUNE_CAP, 0x40, 0x00)

        # Verify RCO calibration
        trco = self._read_reg(_REG_TRCO_CAL)
        srco = self._read_reg(_REG_SRCO_CAL)
        trco_ok = bool(trco & 0x80) and not bool(trco & 0x40)
        srco_ok = bool(srco & 0x80) and not bool(srco & 0x40)
        if not trco_ok or not srco_ok:
            logger.warning("AS3935 RCO calibration issue — TRCO_OK=%s SRCO_OK=%s", trco_ok, srco_ok)
        else:
            logger.debug("AS3935 RCO calibration OK")

        # Clear distance estimation statistics for a fresh start
        self._clear_statistics()

    def _clear_statistics(self):
        """Toggle CL_STAT bit to reset internal distance algorithm."""
        self._sing_reg_write(_REG_CONFIG2, 0x40, 0x40)
        self._sing_reg_write(_REG_CONFIG2, 0x40, 0x00)
        self._sing_reg_write(_REG_CONFIG2, 0x40, 0x40)

    def _raise_noise_floor(self):
        """Raise noise floor by one level (called on INT_NH)."""
        if self._noise_floor < _NF_MAX:
            self._noise_floor += 1
            self._sing_reg_write(_REG_CONFIG1, 0x70, self._noise_floor << 4)
            logger.info("AS3935 noise floor raised to %d", self._noise_floor)
            self._clear_statistics()

    def _lower_noise_floor(self):
        """Lower noise floor by one level (called periodically)."""
        if self._noise_floor > _NF_MIN:
            self._noise_floor -= 1
            self._sing_reg_write(_REG_CONFIG1, 0x70, self._noise_floor << 4)
            logger.info("AS3935 noise floor lowered to %d", self._noise_floor)

    def maybe_lower_noise_floor(self):
        """Called from poller loop — lowers noise floor every 2 min if quiet."""
        if not self._available:
            return
        now = time.time()
        if now - self._last_nf_lower >= _NF_LOWER_INTERVAL:
            self._last_nf_lower = now
            try:
                self._lower_noise_floor()
            except Exception:
                logger.exception("AS3935 lower noise floor error")

    def _setup_irq(self):
        if _GPIO_LIB == "lgpio":
            h = lgpio.gpiochip_open(0)
            lgpio.gpio_claim_alert(h, self._irq_gpio, lgpio.RISING_EDGE)
            cb = lgpio.callback(h, self._irq_gpio, lgpio.RISING_EDGE,
                                self._lgpio_callback)
            self._gpio_handle = h
            self._lgpio_cb = cb
        else:
            _rpigpio.setmode(_rpigpio.BCM)
            _rpigpio.setup(self._irq_gpio, _rpigpio.IN)
            _rpigpio.add_event_detect(
                self._irq_gpio, _rpigpio.RISING,
                callback=self._irq_handler, bouncetime=50,
            )

    def _lgpio_callback(self, chip, gpio, level, timestamp):
        """lgpio callback — delegates to shared IRQ handler."""
        self._irq_handler(gpio)

    def _irq_handler(self, channel):
        # DFRobot example waits 5ms for interrupt register to populate
        time.sleep(0.005)
        try:
            int_src = self._read_reg(_REG_CONFIG3) & 0x0F

            event = {
                "ts": int(time.time()),
                "event_type": 0,
                "distance_km": None,
                "energy": None,
            }

            if int_src == INT_LIGHTNING:
                distance = self._read_reg(_REG_DISTANCE) & 0x3F
                e0 = self._read_reg(_REG_ENERGY0)
                e1 = self._read_reg(_REG_ENERGY1)
                e2 = self._read_reg(_REG_ENERGY2) & 0x1F
                energy = (e2 << 16) | (e1 << 8) | e0

                # Filter likely false positives by minimum distance
                if distance != 0x3F and distance < config.AS3935_MIN_DISTANCE:
                    logger.debug("AS3935 strike filtered: distance=%d km < min %d km, energy=%d",
                                 distance, config.AS3935_MIN_DISTANCE, energy)
                    return

                event["event_type"] = 1
                event["distance_km"] = distance if distance != 0x3F else None
                event["energy"] = energy

                logger.info("Lightning detected: distance=%s km, energy=%s",
                            event["distance_km"], event["energy"])
            elif int_src == INT_DISTURBER:
                event["event_type"] = 2
                logger.debug("AS3935 disturber event")
            elif int_src == INT_NOISE:
                event["event_type"] = 3
                self._raise_noise_floor()
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
                if _GPIO_LIB == "lgpio":
                    if self._lgpio_cb is not None:
                        self._lgpio_cb.cancel()
                    if self._gpio_handle is not None:
                        lgpio.gpiochip_close(self._gpio_handle)
                else:
                    _rpigpio.remove_event_detect(self._irq_gpio)
            except Exception:
                pass
        if self._bus:
            try:
                self._bus.close()
            except Exception:
                pass
