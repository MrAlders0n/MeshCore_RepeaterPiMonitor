# RepeaterWatch — Community Contributions

Enhancements to [RepeaterWatch](https://github.com/MrAlders0n/RepeaterWatch) developed and tested on a Raspberry Pi 4 running Raspberry Pi OS Bookworm. These changes add bcrypt authentication, a fully responsive dark/light-mode dashboard UI, dynamic sensor management, RX error tracking fixes, and a one-command installer for the full SerialMux → mctomqtt → RepeaterWatch stack.

---

## What's Included

| File | Description |
|------|-------------|
| `install.sh` | One-command installer for the full stack |
| `uninstall.sh` | Clean uninstaller (`--purge` to remove data too) |
| `app.py` | Bcrypt login, logout route, auth guard |
| `setup_auth.py` | Interactive password setup (bcrypt) |
| `api/routes.py` | All API routes including sensor config, hardware field, RX error fix |
| `static/css/dashboard.css` | Fully responsive dark/light theme (DM Sans + JetBrains Mono) |
| `static/js/dashboard.js` | Dashboard JS — device info card, all tab logic |
| `static/js/sensors_manage.js` | Sensor config modal + dynamic section visibility |
| `templates/index.html` | Full responsive dashboard template |
| `.env.example` | All supported environment variables |

---

## Quick Install (fresh Pi)

```bash
git clone https://github.com/jjkroell/Repeater-Watch.git
cd Repeater-Watch
chmod +x install.sh
sudo ./install.sh
```

The installer will:
- Detect your USB serial device automatically
- Prompt for a hardware description (e.g. `Ikoka Stick 30dBm`)
- Clone and configure SerialMux, mctomqtt, and RepeaterWatch
- Apply all contrib files
- Create and start all three systemd services

Then set a dashboard password:

```bash
sudo -u meshcoremon /opt/RepeaterWatch/venv/bin/python3 /opt/RepeaterWatch/setup_auth.py
```

Dashboard available at `http://<pi-ip>:5000`

---

## Applying to an Existing Install

Copy modified files individually, then restart:

```bash
sudo cp app.py                      /opt/RepeaterWatch/app.py
sudo cp setup_auth.py               /opt/RepeaterWatch/setup_auth.py
sudo cp api/routes.py               /opt/RepeaterWatch/api/routes.py
sudo cp templates/index.html        /opt/RepeaterWatch/templates/index.html
sudo cp static/css/dashboard.css    /opt/RepeaterWatch/static/css/dashboard.css
sudo cp static/js/dashboard.js      /opt/RepeaterWatch/static/js/dashboard.js
sudo cp static/js/sensors_manage.js /opt/RepeaterWatch/static/js/sensors_manage.js

sudo chown -R meshcoremon:meshcoremon \
    /opt/RepeaterWatch/app.py \
    /opt/RepeaterWatch/api/routes.py \
    /opt/RepeaterWatch/setup_auth.py \
    /opt/RepeaterWatch/static/css/dashboard.css \
    /opt/RepeaterWatch/static/js/dashboard.js \
    /opt/RepeaterWatch/static/js/sensors_manage.js \
    /opt/RepeaterWatch/templates/index.html

sudo /opt/RepeaterWatch/venv/bin/pip install bcrypt
sudo systemctl restart RepeaterWatch
```

---

## Serial Port Architecture

[SerialMux](https://github.com/MrAlders0n/SerialMux) multiplexes one physical USB serial port across three virtual PTY ports:

| Virtual Port | Consumer | Purpose |
|---|---|---|
| `/dev/ttyV0` | RepeaterWatch | Main data polling (`MESHCORE_SERIAL_PORT`) |
| `/dev/ttyV1` | mctomqtt | LetsMesh / MQTT cloud relay |
| `/dev/ttyV2` | RepeaterWatch | Web terminal (`MESHCORE_TERMINAL_SERIAL_PORT`) |

The physical device path is auto-detected from `/dev/serial/by-id/` at install time and patched directly into `SerialMux.py` (which uses hardcoded constants, not CLI args).

> **Important:** Service names are case-sensitive. `RepeaterWatch.service`, `mctomqtt.service`, and `SerialMux.service` must match exactly — these strings are referenced in `api/routes.py`.

> **Important:** SerialMux must run as `root` to create `/dev/ttyV*` symlinks. This is set in the service unit.

---

## mctomqtt Startup Behaviour

mctomqtt depends on SerialMux having created `/dev/ttyV1` before it can start. A systemd drop-in override at `/etc/systemd/system/mctomqtt.service.d/override.conf` handles this robustly:

```ini
[Service]
ExecStartPre=
ExecStartPre=/bin/bash -c 'for i in $(seq 30); do [ -e /dev/ttyV1 ] && exit 0; sleep 1; done; exit 1'
Restart=on-failure
RestartSec=15
RestartForceExitStatus=0
```

- Waits up to 30 seconds for `/dev/ttyV1` to appear before starting
- `RestartForceExitStatus=0` makes systemd treat a clean exit (status 0) as a failure — mctomqtt exits 0 when the radio doesn't respond, which would otherwise prevent `Restart=on-failure` from triggering
- After a firmware flash or radio power cycle, mctomqtt will self-recover within a few restart cycles

---

## Authentication

Authentication uses bcrypt hashing. Set a password:

```bash
sudo -u meshcoremon /opt/RepeaterWatch/venv/bin/python3 /opt/RepeaterWatch/setup_auth.py
```

This writes `MESHCORE_PASSWORD_HASH` to `.env`. To disable authentication, clear both `MESHCORE_PASSWORD_HASH` and `MESHCORE_PASSWORD` in `.env` and restart.

---

## Sensor Management

The Sensors tab is fully dynamic — it only shows sections for sensors enabled in `.env`. Use the **Manage Sensors** modal to toggle sensors without editing files.

| Sensor | Variable | Capability |
|---|---|---|
| INA3221 | `MESHCORE_SENSOR_INA3221` | 3-channel voltage / current / power |
| BME280 | `MESHCORE_SENSOR_BME280` | Temperature, humidity, pressure |
| LIS2DW12 | `MESHCORE_SENSOR_LIS2DW12` | Accelerometer / vibration |
| AS3935 | `MESHCORE_SENSOR_AS3935` | Lightning strike detector |
| BQ24074 | `MESHCORE_SENSOR_BQ24074` | Solar charger status |

`MESHCORE_SENSOR_POLL` is managed automatically — set to `1` when any sensor is enabled. A service restart is required after changing sensor config for polling to take effect.

---

## Environment Variables

See [`.env.example`](.env.example) for a full reference. Key variables:

```env
MESHCORE_PASSWORD_HASH=             # bcrypt hash — set via setup_auth.py
MESHCORE_SECRET_KEY=                # Flask session key — auto-generated at install
MESHCORE_SERIAL_PORT=/dev/ttyV0
MESHCORE_TERMINAL_SERIAL_PORT=/dev/ttyV2
MESHCORE_FLASH_SERIAL_PORT=/dev/serial/by-id/usb-...
MESHCORE_HARDWARE=Ikoka Stick 30dBm # Shown in dashboard device info card
MESHCORE_SENSOR_BME280=1            # Enable BME280
MESHCORE_SENSOR_POLL=1              # Auto-managed
```

---

## Sudoers

The installer creates `/etc/sudoers.d/meshcoremon` automatically. To add manually:

```
meshcoremon ALL=(ALL) NOPASSWD: \
    /usr/bin/systemctl stop SerialMux, \
    /usr/bin/systemctl start SerialMux, \
    /usr/bin/systemctl restart SerialMux, \
    /usr/bin/systemctl stop mctomqtt, \
    /usr/bin/systemctl start mctomqtt, \
    /usr/bin/systemctl restart mctomqtt, \
    /usr/bin/systemctl restart RepeaterWatch, \
    /usr/bin/systemctl reboot
```

---

## Uninstall

```bash
# Safe — preserves database and .env
sudo ./uninstall.sh

# Full purge — removes everything
sudo ./uninstall.sh --purge
```

---

## Tested On

- Raspberry Pi 4 Model B (4 GB)
- Raspberry Pi OS Bookworm (64-bit)
- Ikoka repeater with Seeed Studio XIAO nRF52840 USB stick
- MeshCore firmware 1.13.0-letsmesh.net
- Python 3.11+, Flask 3.x, bcrypt 4.x
