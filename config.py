import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

SERIAL_PORT = os.environ.get("MESHCORE_SERIAL_PORT", "/dev/ttyV0")
SERIAL_BAUD = int(os.environ.get("MESHCORE_SERIAL_BAUD", "115200"))
SERIAL_TIMEOUT = float(os.environ.get("MESHCORE_SERIAL_TIMEOUT", "5"))

POLL_INTERVAL_SECS = int(os.environ.get("MESHCORE_POLL_INTERVAL", "300"))

DB_PATH = os.environ.get("MESHCORE_DB_PATH", os.path.join(os.path.dirname(__file__), "meshcore.db"))
RETENTION_DAYS = int(os.environ.get("MESHCORE_RETENTION_DAYS", "30"))

FLASK_HOST = os.environ.get("MESHCORE_HOST", "0.0.0.0")
FLASK_PORT = int(os.environ.get("MESHCORE_PORT", "5000"))
FLASK_DEBUG = os.environ.get("MESHCORE_DEBUG", "0") == "1"

FLASH_SERIAL_PORT = os.environ.get(
    "MESHCORE_FLASH_SERIAL_PORT",
    "/dev/serial/by-id/usb-Seeed_Studio_XIAO_nRF52840_C8A73AB0B3AB137D-if00",
)
FIRMWARE_UPLOAD_DIR = os.environ.get("MESHCORE_FIRMWARE_UPLOAD_DIR", "/tmp/meshcore-fw")

MAX_QUERY_HOURS = 720  # 30 days

SECRET_KEY = os.environ.get("MESHCORE_SECRET_KEY", None)
PASSWORD = os.environ.get("MESHCORE_PASSWORD", None)

TERMINAL_SERIAL_PORT = os.environ.get("MESHCORE_TERMINAL_SERIAL_PORT", "/dev/ttyV2")
TERMINAL_SERIAL_BAUD = int(os.environ.get("MESHCORE_TERMINAL_SERIAL_BAUD", "115200"))

RADIO_RESET_GPIO_PIN = int(os.environ.get("MESHCORE_RADIO_RESET_GPIO", "4"))
USB_RELAY_GPIO_PIN = int(os.environ.get("MESHCORE_USB_RELAY_GPIO", "17"))

SENSOR_POLL_ENABLED = os.environ.get("MESHCORE_SENSOR_POLL", "1") != "0"
AS3935_IRQ_GPIO = int(os.environ.get("MESHCORE_AS3935_IRQ_GPIO", "18"))
AS3935_AFE_MODE = os.environ.get("MESHCORE_AS3935_AFE_MODE", "outdoor")  # "indoor" or "outdoor"
AS3935_NOISE_FLOOR = int(os.environ.get("MESHCORE_AS3935_NOISE_FLOOR", "3"))  # 0-7
AS3935_WATCHDOG = int(os.environ.get("MESHCORE_AS3935_WATCHDOG", "3"))  # 0-15
AS3935_SPIKE_REJECTION = int(os.environ.get("MESHCORE_AS3935_SPIKE_REJECTION", "3"))  # 0-15
AS3935_MASK_DISTURBER = os.environ.get("MESHCORE_AS3935_MASK_DIST", "1") == "1"  # mask disturber events
AS3935_MIN_STRIKES = int(os.environ.get("MESHCORE_AS3935_MIN_STRIKES", "5"))  # 1,5,9,16
AS3935_MIN_DISTANCE = int(os.environ.get("MESHCORE_AS3935_MIN_DISTANCE", "2"))  # km, filter out <= this

BQ24074_CHG_GPIO = int(os.environ.get("MESHCORE_BQ24074_CHG_GPIO", "19"))
BQ24074_PGOOD_GPIO = int(os.environ.get("MESHCORE_BQ24074_PGOOD_GPIO", "13"))
BQ24074_CE_GPIO = int(os.environ.get("MESHCORE_BQ24074_CE_GPIO", "6"))
