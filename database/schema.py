import sqlite3

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS device_info (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stats_core (
    ts          INTEGER PRIMARY KEY,
    battery_mv  INTEGER,
    uptime_secs INTEGER,
    errors      INTEGER,
    queue_len   INTEGER
);

CREATE TABLE IF NOT EXISTS stats_radio (
    ts          INTEGER PRIMARY KEY,
    noise_floor REAL,
    tx_air_secs REAL,
    rx_air_secs REAL
);

CREATE TABLE IF NOT EXISTS stats_packets (
    ts          INTEGER PRIMARY KEY,
    recv_total  INTEGER,
    sent_total  INTEGER,
    recv_errors INTEGER,
    fwd_total   INTEGER,
    fwd_errors  INTEGER,
    direct_dups INTEGER
);

CREATE TABLE IF NOT EXISTS stats_extpower (
    ts           INTEGER PRIMARY KEY,
    ch0_voltage  REAL,
    ch0_current  REAL,
    ch0_power    REAL,
    ch1_voltage  REAL,
    ch1_current  REAL,
    ch1_power    REAL,
    ch2_voltage  REAL,
    ch2_current  REAL,
    ch2_power    REAL
);

CREATE TABLE IF NOT EXISTS packet_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        INTEGER NOT NULL,
    direction TEXT,
    pkt_type  INTEGER,
    route     TEXT,
    snr       REAL,
    rssi      REAL,
    score     REAL,
    hash      TEXT
);

CREATE TABLE IF NOT EXISTS neighbors (
    pubkey_prefix TEXT PRIMARY KEY,
    name          TEXT,
    device_role   TEXT,
    last_seen     INTEGER,
    last_snr      REAL,
    last_rssi     REAL,
    lat           REAL,
    lon           REAL
);

CREATE TABLE IF NOT EXISTS neighbor_sightings (
    ts            INTEGER NOT NULL,
    pubkey_prefix TEXT NOT NULL,
    snr           REAL,
    rssi          REAL,
    PRIMARY KEY (ts, pubkey_prefix)
);

CREATE INDEX IF NOT EXISTS idx_packet_log_ts ON packet_log(ts);
CREATE INDEX IF NOT EXISTS idx_neighbor_sightings_ts ON neighbor_sightings(ts);
"""


MIGRATIONS = [
    "ALTER TABLE packet_log ADD COLUMN pkt_type INTEGER",
    "ALTER TABLE packet_log ADD COLUMN route TEXT",
    "ALTER TABLE neighbors ADD COLUMN device_role TEXT",
    "ALTER TABLE neighbors ADD COLUMN last_rssi REAL",
    "ALTER TABLE neighbor_sightings ADD COLUMN snr REAL",
    "ALTER TABLE neighbor_sightings ADD COLUMN rssi REAL",
    "ALTER TABLE packet_log ADD COLUMN raw_hex TEXT",
]


def init_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.executescript(SCHEMA_SQL)
    for sql in MIGRATIONS:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.commit()
    return conn
