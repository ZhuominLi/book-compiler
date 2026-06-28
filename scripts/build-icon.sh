#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/assets/app-icon.png"
ICONSET="$ROOT/assets/AppIcon.iconset"
OUT="$ROOT/assets/AppIcon.icns"

[[ -f "$SRC" ]] || { echo "Missing $SRC"; exit 1; }

PY=python3
if command -v conda >/dev/null 2>&1 && conda run -n llm python -c "import PIL" >/dev/null 2>&1; then
  PY="conda run -n llm python"
fi

$PY "$ROOT/scripts/defringe-icon.py" "$SRC"
rm -rf "$ICONSET"
$PY "$ROOT/scripts/make-iconset.py" "$SRC" "$ICONSET"
iconutil -c icns "$ICONSET" -o "$OUT"
rm -rf "$ICONSET"
cp "$SRC" "$ROOT/ui/static/icon.png"
echo "Built: $OUT"
