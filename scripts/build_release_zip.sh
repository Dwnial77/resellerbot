#!/usr/bin/env bash
# Build GitHub release ZIP from project root.
# Usage: build_release_zip.sh [release|source|all]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
TARGET="${1:-release}"
VERSION="$(python -c "from bot.version import __version__; print(__version__)")"
OUT_DIR="$ROOT/dist"
mkdir -p "$OUT_DIR"

build_release() {
  local zip="$OUT_DIR/resellerbot-${VERSION}.zip"
  rm -f "$zip"
  zip -r "$zip" \
    bot db services xui deploy scripts \
    requirements.txt RELEASE.json README.md CHANGELOG.md LICENSE \
    -x '*__pycache__*' '*.pyc' '*/*.py[cod]' \
    -x 'bot/handlers/__pycache__/*' 'services/__pycache__/*'
  echo "Created $zip"
}

build_source() {
  local zip="$OUT_DIR/resellerbot-${VERSION}-source.zip"
  rm -f "$zip"
  git archive --format=zip --prefix="resellerbot-${VERSION}/" HEAD -o "$zip"
  echo "Created $zip"
}

case "$TARGET" in
  release) build_release ;;
  source) build_source ;;
  all)
    build_release
    build_source
    ;;
  *)
    echo "Usage: $0 [release|source|all]" >&2
    exit 1
    ;;
esac
