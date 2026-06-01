#!/usr/bin/env bash
# One-step Linux VPS install for Reseller Bot (run from repo root with sudo).
set -euo pipefail

INSTALL_DIR="/opt/resellerbot"
SERVICE_NAME="resellerbot"
SERVICE_USER="resellerbot"
NO_START=0
SKIP_SUDOERS_HINT=0

usage() {
  cat <<'EOF'
Usage: sudo bash scripts/install.sh [options]

Options:
  --dir PATH            Install directory (default: /opt/resellerbot)
  --no-start            Install only; do not enable/start systemd service
  --skip-sudoers-hint   Do not print sudoers setup instructions
  -h, --help            Show this help

Run from the cloned repository (or it will copy sources into --dir):
  git clone https://github.com/Dwnial77/resellerbot.git /opt/resellerbot
  cd /opt/resellerbot
  sudo bash scripts/install.sh
EOF
}

log() { echo "[install] $*"; }
die() { echo "[install] ERROR: $*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir)
      INSTALL_DIR="${2:?}"
      shift 2
      ;;
    --no-start)
      NO_START=1
      shift
      ;;
    --skip-sudoers-hint)
      SKIP_SUDOERS_HINT=1
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      die "Unknown option: $1 (use --help)"
      ;;
  esac
done

if [[ "$(id -u)" -ne 0 ]]; then
  die "Run as root: sudo bash scripts/install.sh"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ ! -f "$SOURCE_DIR/bot/version.py" ]] || [[ ! -f "$SOURCE_DIR/requirements.txt" ]]; then
  die "Invalid source tree at $SOURCE_DIR (expected bot/version.py and requirements.txt)"
fi

if ! command -v python3 >/dev/null 2>&1; then
  die "python3 not found. Install: apt install -y python3 python3-venv python3-pip"
fi

if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
  pyver="$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))' 2>/dev/null || echo unknown)"
  die "Python 3.11+ required (found $pyver)"
fi

if ! python3 -c 'import venv' 2>/dev/null; then
  die "python3-venv missing. Install: apt install -y python3-venv"
fi

if ! command -v systemctl >/dev/null 2>&1; then
  die "systemd (systemctl) is required on this host"
fi

mkdir -p "$INSTALL_DIR"
INSTALL_DIR="$(cd "$INSTALL_DIR" && pwd)"

log "Install directory: $INSTALL_DIR"

if ! id "$SERVICE_USER" &>/dev/null; then
  log "Creating system user $SERVICE_USER"
  useradd -r -s /bin/false "$SERVICE_USER"
else
  log "System user $SERVICE_USER already exists"
fi

copy_tree() {
  local src="$1"
  local dst="$2"
  mkdir -p "$dst"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a \
      --exclude '.env' \
      --exclude '.venv' \
      --exclude 'data' \
      --exclude '.git' \
      --exclude '__pycache__' \
      --exclude 'dist' \
      --exclude '.pytest_cache' \
      "$src/" "$dst/"
  else
    # cp fallback (no --exclude); copy known top-level entries only
    for name in bot db services xui deploy scripts requirements.txt RELEASE.json README.md CHANGELOG.md LICENSE .env.example; do
      if [[ -e "$src/$name" ]]; then
        cp -a "$src/$name" "$dst/"
      fi
    done
  fi
}

SOURCE_REAL="$(cd "$SOURCE_DIR" && pwd)"
INSTALL_REAL="$(mkdir -p "$INSTALL_DIR" && cd "$INSTALL_DIR" && pwd)"

if [[ "$SOURCE_REAL" != "$INSTALL_REAL" ]]; then
  log "Copying project from $SOURCE_REAL to $INSTALL_REAL"
  copy_tree "$SOURCE_REAL" "$INSTALL_REAL"
else
  log "Installing in place at $INSTALL_REAL"
fi

cd "$INSTALL_REAL"

if [[ ! -f .env ]]; then
  cp .env.example .env
  log "Created .env from .env.example — edit before production use"
else
  log "Keeping existing .env"
fi

mkdir -p data data/backups
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_REAL"

log "Creating virtualenv and installing dependencies"
sudo -u "$SERVICE_USER" python3 -m venv "$INSTALL_REAL/.venv"
sudo -u "$SERVICE_USER" "$INSTALL_REAL/.venv/bin/pip" install --upgrade pip
sudo -u "$SERVICE_USER" "$INSTALL_REAL/.venv/bin/pip" install -r "$INSTALL_REAL/requirements.txt"

UNIT_SRC="$INSTALL_REAL/deploy/resellerbot.service"
UNIT_DST="/etc/systemd/system/${SERVICE_NAME}.service"
if [[ ! -f "$UNIT_SRC" ]]; then
  die "Missing $UNIT_SRC"
fi

if [[ "$INSTALL_REAL" == "/opt/resellerbot" ]]; then
  cp "$UNIT_SRC" "$UNIT_DST"
else
  sed \
    -e "s|WorkingDirectory=/opt/resellerbot|WorkingDirectory=$INSTALL_REAL|g" \
    -e "s|ExecStart=/opt/resellerbot/.venv/bin/python|ExecStart=$INSTALL_REAL/.venv/bin/python|g" \
    "$UNIT_SRC" >"$UNIT_DST"
fi

systemctl daemon-reload

if [[ "$NO_START" -eq 0 ]]; then
  systemctl enable "$SERVICE_NAME"
  if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    systemctl restart "$SERVICE_NAME"
  else
    systemctl start "$SERVICE_NAME"
  fi
  log "Service $SERVICE_NAME enabled and started"
else
  log "Skipped systemctl start (--no-start)"
fi

cat <<EOF

========================================
  Reseller Bot installed
========================================
  Path:    $INSTALL_REAL
  Service: $SERVICE_NAME
  User:    $SERVICE_USER

Next steps:
  1. Edit config:  nano $INSTALL_REAL/.env
     (BOT_TOKEN, ADMIN_TELEGRAM_IDS, XUI_BASE_URL, XUI_API_TOKEN, ...)
  2. Restart:      systemctl restart $SERVICE_NAME
  3. View logs:    journalctl -u $SERVICE_NAME -f

Updates (ZIP): https://github.com/Dwnial77/resellerbot/releases
  Use Telegram admin menu: /bot_update

EOF

if [[ "$SKIP_SUDOERS_HINT" -eq 0 ]]; then
  cat <<EOF
Optional — allow in-bot ZIP updates to restart the service:
  sudo visudo -f /etc/sudoers.d/resellerbot

Add this line:
  $SERVICE_USER ALL=(root) NOPASSWD: /bin/systemctl restart $SERVICE_NAME

EOF
fi
