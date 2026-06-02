#!/usr/bin/env bash
# Remote bootstrap: clone resellerbot repo and run scripts/install.sh (for curl | sudo bash).
set -euo pipefail

REPO_URL="${RESELLERBOT_REPO_URL:-https://github.com/Dwnial77/resellerbot.git}"
BRANCH="${RESELLERBOT_BRANCH:-main}"
INSTALL_DIR="/opt/resellerbot"
FORWARD_ARGS=()

usage() {
  cat <<'EOF'
Usage: curl -fsSL .../bootstrap.sh | sudo bash [-s -- [options]]

Bootstrap options (passed through to scripts/install.sh where applicable):
  --dir PATH            Install directory (default: /opt/resellerbot)
  --branch NAME         Git branch to clone/pull (default: main, or RESELLERBOT_BRANCH)
  --no-start            Install only; do not enable/start systemd service
  --skip-sudoers-hint   Do not print sudoers setup instructions
  -h, --help            Show this help

Environment:
  RESELLERBOT_REPO_URL   Git clone URL (default: Dwnial77/resellerbot)
  RESELLERBOT_BRANCH     Branch name (default: main)

Example:
  curl -fsSL https://raw.githubusercontent.com/Dwnial77/resellerbot/main/scripts/bootstrap.sh | sudo bash
  curl -fsSL .../bootstrap.sh | sudo bash -s -- --dir /opt/resellerbot --no-start
EOF
}

log() { echo "[bootstrap] $*"; }
die() { echo "[bootstrap] ERROR: $*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir)
      INSTALL_DIR="${2:?}"
      shift 2
      ;;
    --branch)
      BRANCH="${2:?}"
      shift 2
      ;;
    --no-start | --skip-sudoers-hint)
      FORWARD_ARGS+=("$1")
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
  die "Run as root: curl ... | sudo bash"
fi

if ! command -v git >/dev/null 2>&1; then
  die "git not found. Install: apt install -y git curl python3 python3-venv python3-pip"
fi

if ! command -v python3 >/dev/null 2>&1; then
  die "python3 not found. Install: apt install -y python3 python3-venv python3-pip"
fi

if ! python3 -c 'import venv' 2>/dev/null; then
  die "python3-venv missing. Install: apt install -y python3-venv"
fi

mkdir -p "$INSTALL_DIR"
INSTALL_DIR="$(cd "$INSTALL_DIR" && pwd)"

log "Repository: $REPO_URL (branch: $BRANCH)"
log "Install directory: $INSTALL_DIR"

if [[ -d "$INSTALL_DIR/.git" ]]; then
  log "Existing git repo at $INSTALL_DIR — pulling (ff-only)"
  git -C "$INSTALL_DIR" fetch origin "$BRANCH"
  git -C "$INSTALL_DIR" checkout "$BRANCH" 2>/dev/null || git -C "$INSTALL_DIR" checkout -B "$BRANCH" "origin/$BRANCH"
  git -C "$INSTALL_DIR" pull --ff-only origin "$BRANCH"
elif [[ -n "$(ls -A "$INSTALL_DIR" 2>/dev/null || true)" ]]; then
  die "$INSTALL_DIR is not empty and not a git repository. Remove it or use another --dir path."
else
  log "Cloning (shallow) into $INSTALL_DIR"
  git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
fi

if [[ ! -f "$INSTALL_DIR/scripts/install.sh" ]]; then
  die "Missing $INSTALL_DIR/scripts/install.sh after clone"
fi

log "Running install.sh"
exec bash "$INSTALL_DIR/scripts/install.sh" --dir "$INSTALL_DIR" "${FORWARD_ARGS[@]}"
