#!/usr/bin/env bash
# ============================================================
#  RepeaterWatch Stack Uninstaller
#
#  Usage:
#    chmod +x uninstall.sh
#    sudo ./uninstall.sh
#
#  By default, the database and .env are preserved.
#  Pass --purge to remove everything including data.
# ============================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }

[[ $EUID -eq 0 ]] || { echo "Please run as root: sudo ./uninstall.sh" >&2; exit 1; }

PURGE=0
for arg in "$@"; do
    [[ "$arg" == "--purge" ]] && PURGE=1
done

if [[ $PURGE -eq 1 ]]; then
    warn "PURGE mode — all data and config will be deleted."
else
    info "Safe mode — database and .env will be preserved. Use --purge to remove everything."
fi

read -rp "Continue? [y/N] " confirm
[[ "$confirm" =~ ^[Yy]$ ]] || { info "Aborted."; exit 0; }

# ── Stop and disable services ────────────────────────────────
for svc in RepeaterWatch mctomqtt SerialMux; do
    if systemctl is-active --quiet "$svc" 2>/dev/null; then
        info "Stopping $svc..."
        systemctl stop "$svc"
    fi
    if systemctl is-enabled --quiet "$svc" 2>/dev/null; then
        systemctl disable "$svc"
    fi
    rm -f "/etc/systemd/system/$svc.service"
    # Remove any drop-in overrides
    rm -rf "/etc/systemd/system/$svc.service.d"
    success "Removed $svc service"
done
systemctl daemon-reload

# ── Remove install dirs ──────────────────────────────────────
for dir in /opt/SerialMux /opt/mctomqtt; do
    if [[ -d "$dir" ]]; then
        info "Removing $dir..."
        rm -rf "$dir"
        success "Removed $dir"
    fi
done

if [[ $PURGE -eq 1 ]]; then
    info "Removing /opt/RepeaterWatch (purge)..."
    rm -rf /opt/RepeaterWatch
    success "Removed /opt/RepeaterWatch"
else
    info "Preserving /opt/RepeaterWatch database and .env"
    # Remove code but keep data
    find /opt/RepeaterWatch -mindepth 1 -maxdepth 1 \
        ! -name '.env' ! -name 'meshcore.db' ! -name 'meshcore.db-shm' ! -name 'meshcore.db-wal' \
        -exec rm -rf {} + 2>/dev/null || true
fi

# ── Config dirs ──────────────────────────────────────────────
[[ -d /etc/mctomqtt ]] && { rm -rf /etc/mctomqtt; success "Removed /etc/mctomqtt"; }

# ── sudoers ──────────────────────────────────────────────────
[[ -f /etc/sudoers.d/meshcoremon ]] && { rm -f /etc/sudoers.d/meshcoremon; success "Removed sudoers entry"; }

# ── Service user ─────────────────────────────────────────────
if [[ $PURGE -eq 1 ]] && id meshcoremon &>/dev/null; then
    userdel meshcoremon
    success "Removed service user meshcoremon"
fi

echo ""
success "Uninstall complete."
[[ $PURGE -eq 0 ]] && warn "Data preserved at /opt/RepeaterWatch — run with --purge to remove it."
