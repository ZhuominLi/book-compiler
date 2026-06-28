#!/usr/bin/env bash
# Slim BeanRead.app — uses project-local .venv-pack (NOT conda llm).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
VENV="$ROOT/.venv-pack"
PY="$VENV/bin/python"
PIP="$VENV/bin/pip"

fail() { echo "ERROR: $*" >&2; exit 1; }

# ── Never ship developer secrets ──
if [[ -f "$ROOT/.env.example" ]] && grep -qE 'LLM_API_KEY=sk-' "$ROOT/.env.example"; then
  fail ".env.example contains a real API key — use placeholder only"
fi
if grep -qE '^LLM_API_KEY=sk-' "$ROOT/beanread.spec" 2>/dev/null; then
  fail "beanread.spec must not embed API keys"
fi

if [[ ! -x "$PY" ]]; then
  echo "Creating minimal pack venv at .venv-pack ..."
  python3 -m venv "$VENV"
fi

echo "Installing pack dependencies ..."
"$PIP" install -q -U pip
"$PIP" install -q -r requirements-pack.txt
"$PIP" install -q pyinstaller

echo "Building (slim) ..."
rm -rf build dist
"$PY" -m PyInstaller --noconfirm --clean beanread.spec

APP="$ROOT/dist/懒豆阅读.app"
if grep -rE 'sk-[a-zA-Z0-9]{16,}' "$APP" --include='*.env*' --include='*.json' --include='*.py' 2>/dev/null | grep -v your-key-here; then
  fail "Built app contains suspicious API key pattern — check bundle"
fi
if [[ -f "$APP/Contents/Resources/.env" ]]; then
  fail "Bundled .env must not exist — only .env.example"
fi

SIZE=$(du -sh "$APP" | cut -f1)
echo ""
echo "Built: $APP ($SIZE)"
"$ROOT/scripts/build-dmg.sh"
echo ""
echo "Books: ~/Library/Application Support/BeanRead/"
echo "Note:  Packaged app ignores dev .env; users configure API in Settings."
echo "Test:  open \"$APP\""
