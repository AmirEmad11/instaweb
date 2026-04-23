#!/usr/bin/env bash
# =============================================================================
# setup_vps.sh — One-shot setup for Instagram Lead Bot on a clean Ubuntu VPS
# Tested on Ubuntu 24.04. Run as root or with sudo.
# Usage:  bash setup_vps.sh
# =============================================================================

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${PROJECT_DIR}/instagram_automation"
VENV_DIR="${PROJECT_DIR}/.venv"
SERVICE_NAME="instagram-bot"
IPV6_PREFIX="${IPV6_PREFIX:-2a02:4780:28:421}"
IPV6_INTERFACE="${IPV6_INTERFACE:-eth0}"
RUN_USER="${SUDO_USER:-$USER}"

log()  { echo -e "\033[1;34m[INFO]\033[0m  $*"; }
ok()   { echo -e "\033[1;32m[OK]\033[0m    $*"; }
warn() { echo -e "\033[1;33m[WARN]\033[0m  $*"; }

SUDO=""
if [ "$(id -u)" -ne 0 ]; then SUDO="sudo"; fi

# -----------------------------------------------------------------------------
# 1) System update + base packages + Arabic fonts
# -----------------------------------------------------------------------------
log "Updating system and installing base packages..."
$SUDO apt-get update -y
$SUDO apt-get upgrade -y
$SUDO DEBIAN_FRONTEND=noninteractive apt-get install -y \
    python3 python3-venv python3-pip python3-dev \
    build-essential git curl wget unzip ca-certificates \
    iproute2 net-tools \
    fonts-noto fonts-noto-cjk fonts-noto-color-emoji fonts-arabeyes
ok "System packages installed."

# -----------------------------------------------------------------------------
# 2) Python virtual environment
# -----------------------------------------------------------------------------
log "Creating virtual environment at ${VENV_DIR} ..."
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
pip install --upgrade pip wheel setuptools
ok "Virtual environment ready."

# -----------------------------------------------------------------------------
# 3) Install Python requirements
# -----------------------------------------------------------------------------
log "Installing Python requirements..."
pip install -r "${APP_DIR}/requirements.txt"
ok "Python deps installed."

# -----------------------------------------------------------------------------
# 4) Install Playwright browsers (with system deps)
# -----------------------------------------------------------------------------
log "Installing Playwright Chromium browser..."
playwright install --with-deps chromium || playwright install chromium
ok "Chromium installed."

# -----------------------------------------------------------------------------
# 5) IPv6 prefix bind to interface (optional but recommended)
# -----------------------------------------------------------------------------
log "Binding IPv6 prefix ${IPV6_PREFIX}::/64 to ${IPV6_INTERFACE} ..."
if ip link show "$IPV6_INTERFACE" >/dev/null 2>&1; then
    $SUDO sysctl -w net.ipv6.ip_nonlocal_bind=1 >/dev/null
    $SUDO sysctl -w net.ipv6.conf.all.forwarding=1 >/dev/null
    # Add a /64 route via the interface so Linux accepts random IPs from prefix
    $SUDO ip -6 route add local "${IPV6_PREFIX}::/64" dev "$IPV6_INTERFACE" 2>/dev/null \
        || warn "Route already present or could not be added (non-fatal)."
    ok "IPv6 prefix configured on ${IPV6_INTERFACE}."
else
    warn "Interface ${IPV6_INTERFACE} not found - skipping IPv6 bind."
    warn "Set IPV6_INTERFACE env var to your real interface (e.g. ens3) and rerun."
fi

# -----------------------------------------------------------------------------
# 6) systemd service
# -----------------------------------------------------------------------------
log "Creating systemd service: ${SERVICE_NAME}.service ..."
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
$SUDO tee "$SERVICE_FILE" >/dev/null <<EOF
[Unit]
Description=Instagram Lead Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${RUN_USER}
WorkingDirectory=${APP_DIR}
Environment=PYTHONUNBUFFERED=1
Environment=IPV6_PREFIX=${IPV6_PREFIX}
Environment=IPV6_INTERFACE=${IPV6_INTERFACE}
ExecStart=${VENV_DIR}/bin/python ${APP_DIR}/main.py
Restart=on-failure
RestartSec=10
StandardOutput=append:/var/log/${SERVICE_NAME}.log
StandardError=append:/var/log/${SERVICE_NAME}.log

[Install]
WantedBy=multi-user.target
EOF

$SUDO touch "/var/log/${SERVICE_NAME}.log"
$SUDO chown "${RUN_USER}:${RUN_USER}" "/var/log/${SERVICE_NAME}.log" || true

$SUDO systemctl daemon-reload
$SUDO systemctl enable "${SERVICE_NAME}.service"
ok "systemd service installed and enabled."

# -----------------------------------------------------------------------------
# Done
# -----------------------------------------------------------------------------
echo
ok "Setup complete!"
echo
echo "  ▶  Start the bot now:    sudo systemctl start ${SERVICE_NAME}"
echo "  ▶  Check status:         sudo systemctl status ${SERVICE_NAME}"
echo "  ▶  Live logs:            sudo journalctl -u ${SERVICE_NAME} -f"
echo "  ▶  File logs:            tail -f /var/log/${SERVICE_NAME}.log"
echo "  ▶  Stop the bot:         sudo systemctl stop ${SERVICE_NAME}"
echo "  ▶  Run once manually:    bash run.sh"
echo
