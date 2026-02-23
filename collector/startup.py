import logging

from database import models

logger = logging.getLogger(__name__)

STARTUP_COMMANDS = [
    ("get name", "name"),
    ("get public.key", "public_key"),
    ("get radio", "radio_config"),
    ("get lat", "lat"),
    ("get lon", "lon"),
    ("ver", "firmware"),
    ("board", "board"),
]


def collect_device_info(reader):
    for cmd, key in STARTUP_COMMANDS:
        resp = reader.send_command(cmd)
        if resp:
            value = resp.strip()
            if value.startswith("> "):
                value = value[2:]
            models.set_device_info(key, value)
            logger.info("Device %s: %s", key, value)
        else:
            logger.warning("No response for startup command: %s", cmd)
