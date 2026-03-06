import logging
import time

import config

logger = logging.getLogger(__name__)

TABLES_WITH_TS = [
    "stats_core",
    "stats_radio",
    "stats_packets",
    "stats_extpower",
    "stats_pi_health",
    "packet_log",
    "neighbor_sightings",
    "stats_sensor_power",
    "stats_sensor_env",
    "stats_sensor_accel",
    "sensor_lightning_events",
    "stats_disk_io",
    "stats_bq24074",
]


def purge_old_data(conn):
    cutoff = int(time.time()) - config.RETENTION_DAYS * 86400
    total = 0
    for table in TABLES_WITH_TS:
        cur = conn.execute(f"DELETE FROM {table} WHERE ts < ?", (cutoff,))
        total += cur.rowcount
    conn.commit()
    if total > 0:
        logger.info("Purged %d old rows (cutoff=%d)", total, cutoff)
