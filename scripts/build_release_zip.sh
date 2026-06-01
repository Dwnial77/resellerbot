#!/usr/bin/env bash
# Build GitHub release ZIP from project root.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
VERSION="$(python -c "from bot.version import __version__; print(__version__)")"
OUT_DIR="$ROOT/dist"
ZIP="$OUT_DIR/resellerbot-${VERSION}.zip"
rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"
zip -r "$ZIP" \
  bot db services xui deploy scripts \
  requirements.txt RELEASE.json README.md CHANGELOG.md LICENSE \
  -x '*__pycache__*' '*.pyc' '*/*.py[cod]' \
  -x 'bot/handlers/__pycache__/*' 'services/__pycache__/*'
echo "Created $ZIP"
