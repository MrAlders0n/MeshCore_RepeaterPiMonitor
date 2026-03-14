#!/usr/bin/env bash
# ============================================================
#  RepeaterWatch Stack Installer
#  Installs: SerialMux → mctomqtt → RepeaterWatch
#
#  Usage:
#    chmod +x install.sh
#    sudo ./install.sh
#
#  Tested on: Raspberry Pi OS Bookworm (64-bit)
# ============================================================
set -euo pipefail

# ── Colour helpers ───────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
die()     { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ── Must run as root ─────────────────────────────────────────
[[ $EUID -eq 0 ]] || die "Please run as root: sudo ./install.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Configuration ────────────────────────────────────────────
INSTALL_DIR=/opt
SERVICE_USER=meshcoremon
SERVICE_GROUP=meshcoremon

# Auto-detect physical serial port
SERIAL_PORT=$(ls /dev/serial/by-id/ 2>/dev/null | head -1)
if [[ -z "$SERIAL_PORT" ]]; then
    warn "No USB serial device found. You will need to set REAL_PORT manually in SerialMux.py."
    SERIAL_PORT_FULL=""
else
    SERIAL_PORT_FULL="/dev/serial/by-id/$SERIAL_PORT"
    info "Detected serial port: $SERIAL_PORT_FULL"
fi

# ── Hardware description prompt ──────────────────────────────
echo ""
echo -e "${CYAN}Enter a short hardware description for this repeater.${NC}"
echo -e "  e.g. Ikoka Stick 30dBm, RAK4631, LILYGO T-Beam"
echo -e "  (leave blank to skip)"
read -rp "Hardware: " MESHCORE_HARDWARE
echo ""

# ── 1. System packages ───────────────────────────────────────
info "Installing system packages..."
apt-get update -qq
apt-get install -y --no-install-recommends \
    git python3 python3-pip python3-venv python3-dev \
    i2c-tools socat nginx \
    build-essential libssl-dev libffi-dev

# Enable I2C
if ! grep -q "^dtparam=i2c_arm=on" /boot/firmware/config.txt 2>/dev/null; then
    echo "dtparam=i2c_arm=on" >> /boot/firmware/config.txt
    info "I2C enabled in /boot/firmware/config.txt (reboot required)"
fi

# ── 2. Service user ──────────────────────────────────────────
if ! id "$SERVICE_USER" &>/dev/null; then
    info "Creating service user: $SERVICE_USER"
    useradd --system --no-create-home --shell /usr/sbin/nologin \
        --groups dialout,i2c,gpio "$SERVICE_USER"
else
    info "Service user $SERVICE_USER already exists"
    usermod -aG dialout,i2c,gpio "$SERVICE_USER" 2>/dev/null || true
fi

# ── 3. SerialMux ─────────────────────────────────────────────
info "Installing SerialMux..."
SERIALMUX_DIR="$INSTALL_DIR/SerialMux"
if [[ -d "$SERIALMUX_DIR/.git" ]]; then
    git -C "$SERIALMUX_DIR" pull --quiet
else
    rm -rf "$SERIALMUX_DIR"
    git clone --depth 1 https://github.com/MrAlders0n/SerialMux.git "$SERIALMUX_DIR"
fi

# Patch the hardcoded REAL_PORT in SerialMux.py if we detected a device
if [[ -n "$SERIAL_PORT_FULL" ]]; then
    sed -i "s|REAL_PORT = '.*'|REAL_PORT = '$SERIAL_PORT_FULL'|" "$SERIALMUX_DIR/SerialMux.py"
    info "SerialMux REAL_PORT set to: $SERIAL_PORT_FULL"
fi

chown -R root:root "$SERIALMUX_DIR"

# SerialMux runs as root — it creates /dev/ttyV* symlinks which requires root
cat > /etc/systemd/system/SerialMux.service << EOF
[Unit]
Description=SerialMux — PTY multiplexer for MeshCore radio
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/python3 $SERIALMUX_DIR/SerialMux.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
success "SerialMux service configured"

# ── 4. mctomqtt ──────────────────────────────────────────────
info "Installing mctomqtt..."
MCTOMQTT_DIR="$INSTALL_DIR/mctomqtt"
if [[ -d "$MCTOMQTT_DIR/.git" ]]; then
    git -C "$MCTOMQTT_DIR" pull --quiet
else
    rm -rf "$MCTOMQTT_DIR"
    git clone --depth 1 https://github.com/Cisien/meshcoretomqtt.git "$MCTOMQTT_DIR"
fi

info "Creating mctomqtt virtualenv..."
python3 -m venv "$MCTOMQTT_DIR/venv"
"$MCTOMQTT_DIR/venv/bin/pip" install --quiet --upgrade pip
[[ -f "$MCTOMQTT_DIR/requirements.txt" ]] && \
    "$MCTOMQTT_DIR/venv/bin/pip" install --quiet -r "$MCTOMQTT_DIR/requirements.txt"

mkdir -p /etc/mctomqtt/config.d
# Copy base config from repo if present and not yet installed
[[ -f "$MCTOMQTT_DIR/config.toml" && ! -f /etc/mctomqtt/config.toml ]] && \
    cp "$MCTOMQTT_DIR/config.toml" /etc/mctomqtt/config.toml

cat > /etc/mctomqtt/config.d/00-user.toml << 'EOF'
[serial]
port = "/dev/ttyV1"
baud_rate = 115200

[mqtt]
# Configure your MQTT broker — see mctomqtt docs for letsmesh.net settings
# broker = "localhost"
# port = 1883
# username = ""
# password = ""
EOF
chown -R "$SERVICE_USER:$SERVICE_GROUP" "$MCTOMQTT_DIR" /etc/mctomqtt

cat > /etc/systemd/system/mctomqtt.service << EOF
[Unit]
Description=mctomqtt — MeshCore to MQTT bridge
After=network.target SerialMux.service
Requires=SerialMux.service

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_GROUP
WorkingDirectory=$MCTOMQTT_DIR
ExecStart=$MCTOMQTT_DIR/venv/bin/python3 $MCTOMQTT_DIR/mctomqtt.py
Restart=on-failure
RestartSec=15

[Install]
WantedBy=multi-user.target
EOF

# Override: wait for /dev/ttyV1 to exist before starting, and treat a clean
# exit (status 0) as a failure so systemd retries. mctomqtt exits 0 when the
# radio doesn't respond, which would otherwise prevent Restart=on-failure.
mkdir -p /etc/systemd/system/mctomqtt.service.d
cat > /etc/systemd/system/mctomqtt.service.d/override.conf << 'EOF'
[Service]
ExecStartPre=
ExecStartPre=/bin/bash -c 'for i in $(seq 30); do [ -e /dev/ttyV1 ] && exit 0; sleep 1; done; exit 1'
Restart=on-failure
RestartSec=15
RestartForceExitStatus=0
EOF
success "mctomqtt service configured"

# ── 5. RepeaterWatch ─────────────────────────────────────────
info "Installing RepeaterWatch..."
RW_DIR="$INSTALL_DIR/RepeaterWatch"
if [[ -d "$RW_DIR/.git" ]]; then
    git -C "$RW_DIR" pull --quiet
else
    rm -rf "$RW_DIR"
    git clone --depth 1 https://github.com/MrAlders0n/RepeaterWatch.git "$RW_DIR"
fi

info "Creating Python virtualenv..."
python3 -m venv "$RW_DIR/venv"
"$RW_DIR/venv/bin/pip" install --quiet --upgrade pip
"$RW_DIR/venv/bin/pip" install --quiet -r "$RW_DIR/requirements.txt"
"$RW_DIR/venv/bin/pip" install --quiet bcrypt

# Copy contrib files over the cloned repo
info "Applying contrib files..."
cp "$SCRIPT_DIR/app.py"                       "$RW_DIR/app.py"
cp "$SCRIPT_DIR/setup_auth.py"                "$RW_DIR/setup_auth.py"
cp "$SCRIPT_DIR/api/routes.py"                "$RW_DIR/api/routes.py"
cp "$SCRIPT_DIR/templates/index.html"         "$RW_DIR/templates/index.html"
cp "$SCRIPT_DIR/static/css/dashboard.css"     "$RW_DIR/static/css/dashboard.css"
cp "$SCRIPT_DIR/static/js/dashboard.js"       "$RW_DIR/static/js/dashboard.js"
cp "$SCRIPT_DIR/static/js/sensors_manage.js"  "$RW_DIR/static/js/sensors_manage.js"
success "Contrib files applied"

# .env — only create if it doesn't exist
if [[ ! -f "$RW_DIR/.env" ]]; then
    info "Creating .env from example..."
    cp "$SCRIPT_DIR/.env.example" "$RW_DIR/.env" 2>/dev/null || \
        cp "$RW_DIR/.env.example" "$RW_DIR/.env" 2>/dev/null || \
        touch "$RW_DIR/.env"

    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    grep -q "^MESHCORE_SECRET_KEY=" "$RW_DIR/.env" && \
        sed -i "s|^MESHCORE_SECRET_KEY=.*|MESHCORE_SECRET_KEY=$SECRET_KEY|" "$RW_DIR/.env" || \
        echo "MESHCORE_SECRET_KEY=$SECRET_KEY" >> "$RW_DIR/.env"

    if [[ -n "${MESHCORE_HARDWARE:-}" ]]; then
        grep -q "^MESHCORE_HARDWARE=" "$RW_DIR/.env" && \
            sed -i "s|^MESHCORE_HARDWARE=.*|MESHCORE_HARDWARE=$MESHCORE_HARDWARE|" "$RW_DIR/.env" || \
            echo "MESHCORE_HARDWARE=$MESHCORE_HARDWARE" >> "$RW_DIR/.env"
    fi

    if [[ -n "$SERIAL_PORT_FULL" ]]; then
        grep -q "^MESHCORE_FLASH_SERIAL_PORT=" "$RW_DIR/.env" && \
            sed -i "s|^MESHCORE_FLASH_SERIAL_PORT=.*|MESHCORE_FLASH_SERIAL_PORT=$SERIAL_PORT_FULL|" "$RW_DIR/.env" || \
            echo "MESHCORE_FLASH_SERIAL_PORT=$SERIAL_PORT_FULL" >> "$RW_DIR/.env"
    fi
fi

chown -R "$SERVICE_USER:$SERVICE_GROUP" "$RW_DIR"
chmod 640 "$RW_DIR/.env"

# sudoers for service control
cat > /etc/sudoers.d/meshcoremon << 'EOF'
meshcoremon ALL=(ALL) NOPASSWD: \
    /usr/bin/systemctl stop SerialMux, \
    /usr/bin/systemctl start SerialMux, \
    /usr/bin/systemctl restart SerialMux, \
    /usr/bin/systemctl stop mctomqtt, \
    /usr/bin/systemctl start mctomqtt, \
    /usr/bin/systemctl restart mctomqtt, \
    /usr/bin/systemctl restart RepeaterWatch, \
    /usr/bin/systemctl reboot
EOF
chmod 440 /etc/sudoers.d/meshcoremon
success "sudoers configured"

# RepeaterWatch systemd unit
cat > /etc/systemd/system/RepeaterWatch.service << EOF
[Unit]
Description=RepeaterWatch — MeshCore dashboard
After=network.target SerialMux.service

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_GROUP
WorkingDirectory=$RW_DIR
EnvironmentFile=$RW_DIR/.env
ExecStart=$RW_DIR/venv/bin/python3 $RW_DIR/app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
success "RepeaterWatch service configured"

# ── 6. Enable & start services ───────────────────────────────
info "Enabling and starting services..."
systemctl daemon-reload
systemctl enable SerialMux mctomqtt RepeaterWatch
systemctl restart SerialMux
sleep 5
systemctl start mctomqtt || true   # override will retry if radio not ready
sleep 3
systemctl restart RepeaterWatch

# ── 7. Status summary ────────────────────────────────────────
echo ""
echo -e "${BOLD}═══════════════════════════════════════${NC}"
echo -e "${BOLD}  Installation complete!${NC}"
echo -e "${BOLD}═══════════════════════════════════════${NC}"
for svc in SerialMux mctomqtt RepeaterWatch; do
    STATUS=$(systemctl is-active "$svc" 2>/dev/null || echo "unknown")
    if [[ "$STATUS" == "active" ]]; then
        echo -e "  ${GREEN}●${NC} $svc — active"
    else
        echo -e "  ${YELLOW}●${NC} $svc — $STATUS (may still be starting)"
    fi
done
echo ""
echo -e "  Dashboard: ${CYAN}http://$(hostname -I | awk '{print $1}'):5000${NC}"
echo ""
echo -e "  ${YELLOW}Note:${NC} mctomqtt will retry automatically if the radio needs"
echo -e "  time to initialize. Check status after 30 seconds:"
echo -e "  ${CYAN}systemctl status mctomqtt${NC}"
echo ""
echo -e "  Set a dashboard password:"
echo -e "  ${YELLOW}sudo -u $SERVICE_USER $RW_DIR/venv/bin/python3 $RW_DIR/setup_auth.py${NC}"
echo ""
