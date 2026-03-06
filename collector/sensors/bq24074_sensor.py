from __future__ import annotations

import logging

import config

logger = logging.getLogger(__name__)

_backend = None

try:
    import lgpio as _lgpio
    _backend = "lgpio"
except ImportError:
    pass

if _backend is None:
    try:
        import RPi.GPIO as _rpigpio
        _backend = "rpigpio"
    except ImportError:
        pass

HAS_BQ24074 = _backend is not None

_handle = None  # lgpio chip handle


def _ensure_handle():
    global _handle
    if _backend == "lgpio" and _handle is None:
        _handle = _lgpio.gpiochip_open(0)
        # CHG and PGOOD are active-low with pull-ups
        _lgpio.gpio_claim_input(_handle, config.BQ24074_CHG_GPIO, _lgpio.SET_PULL_UP)
        _lgpio.gpio_claim_input(_handle, config.BQ24074_PGOOD_GPIO, _lgpio.SET_PULL_UP)
        # CE is active-high output (LOW = charging enabled)
        _lgpio.gpio_claim_output(_handle, config.BQ24074_CE_GPIO, 0)
        logger.info("BQ24074 GPIO initialized via lgpio (CHG=%d, PGOOD=%d, CE=%d)",
                     config.BQ24074_CHG_GPIO, config.BQ24074_PGOOD_GPIO, config.BQ24074_CE_GPIO)
    elif _backend == "rpigpio" and _handle is None:
        _rpigpio.setmode(_rpigpio.BCM)
        _rpigpio.setup(config.BQ24074_CHG_GPIO, _rpigpio.IN, pull_up_down=_rpigpio.PUD_UP)
        _rpigpio.setup(config.BQ24074_PGOOD_GPIO, _rpigpio.IN, pull_up_down=_rpigpio.PUD_UP)
        _rpigpio.setup(config.BQ24074_CE_GPIO, _rpigpio.OUT, initial=_rpigpio.LOW)
        _handle = True
        logger.info("BQ24074 GPIO initialized via RPi.GPIO (CHG=%d, PGOOD=%d, CE=%d)",
                     config.BQ24074_CHG_GPIO, config.BQ24074_PGOOD_GPIO, config.BQ24074_CE_GPIO)


def read_status() -> dict | None:
    """Read BQ24074 GPIO status pins.

    Returns dict with:
        charging: True if CHG pin is LOW (actively charging)
        power_good: True if PGOOD pin is LOW (valid input power)
        ce_disabled: True if CE pin is HIGH (charging disabled)
    """
    if not HAS_BQ24074:
        return None
    try:
        _ensure_handle()
        if _backend == "lgpio":
            chg = _lgpio.gpio_read(_handle, config.BQ24074_CHG_GPIO)
            pgood = _lgpio.gpio_read(_handle, config.BQ24074_PGOOD_GPIO)
            ce = _lgpio.gpio_read(_handle, config.BQ24074_CE_GPIO)
        else:
            chg = _rpigpio.input(config.BQ24074_CHG_GPIO)
            pgood = _rpigpio.input(config.BQ24074_PGOOD_GPIO)
            ce = _rpigpio.input(config.BQ24074_CE_GPIO)
        return {
            "charging": chg == 0,       # active low
            "power_good": pgood == 0,    # active low
            "ce_disabled": ce == 1,      # HIGH = charging disabled
        }
    except Exception:
        logger.exception("BQ24074 read failed")
        return None


def set_charging_enabled(enabled: bool):
    """Set CE pin: LOW = charging enabled, HIGH = charging disabled."""
    if not HAS_BQ24074:
        return
    try:
        _ensure_handle()
        level = 0 if enabled else 1
        if _backend == "lgpio":
            _lgpio.gpio_write(_handle, config.BQ24074_CE_GPIO, level)
        else:
            _rpigpio.output(config.BQ24074_CE_GPIO, level)
        logger.info("BQ24074 charging %s (CE=%d)", "enabled" if enabled else "disabled", level)
    except Exception:
        logger.exception("BQ24074 set_charging_enabled failed")


def cleanup():
    global _handle
    if _backend == "lgpio" and _handle is not None:
        try:
            _lgpio.gpiochip_close(_handle)
        except Exception:
            pass
        _handle = None
    elif _backend == "rpigpio" and _handle is not None:
        _handle = None
