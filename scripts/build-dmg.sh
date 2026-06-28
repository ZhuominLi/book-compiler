#!/usr/bin/env bash
# Wrap 懒豆阅读.app in a drag-to-Applications DMG for distribution.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

APP_NAME="懒豆阅读.app"
APP="$ROOT/dist/$APP_NAME"
VERSION="$(PYTHONPATH=src python -c "from book_compiler import __version__; print(__version__)")"
DMG="$ROOT/dist/懒豆阅读-${VERSION}-macOS.dmg"

fail() { echo "ERROR: $*" >&2; exit 1; }

[[ -d "$APP" ]] || fail "missing $APP — run ./scripts/build-macos.sh first"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

echo "Staging DMG ..."
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"

rm -f "$DMG"
echo "Creating DMG ..."
hdiutil create \
  -volname "懒豆阅读" \
  -srcfolder "$STAGE" \
  -ov \
  -format UDZO \
  "$DMG" >/dev/null

SIZE=$(du -sh "$DMG" | cut -f1)
echo ""
echo "Built: $DMG ($SIZE)"
echo "Share: send the .dmg file; recipient opens it and drags 懒豆阅读 to Applications."
