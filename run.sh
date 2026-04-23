#!/usr/bin/env bash
# =============================================================================
# run.sh — Start the bot once inside the project's virtual environment.
# Usage:  bash run.sh
# =============================================================================

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${PROJECT_DIR}/instagram_automation"
VENV_DIR="${PROJECT_DIR}/.venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "[ERROR] Virtual environment not found at ${VENV_DIR}"
    echo "        Run 'bash setup_vps.sh' first."
    exit 1
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

export PYTHONUNBUFFERED=1
export IPV6_PREFIX="${IPV6_PREFIX:-2a02:4780:28:421}"
export IPV6_INTERFACE="${IPV6_INTERFACE:-eth0}"

cd "$APP_DIR"
exec python3 main.py
