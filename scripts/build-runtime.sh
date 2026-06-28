#!/usr/bin/env bash
# Build runtime zip for hot-update (UI + server + book_compiler).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VERSION="$(PYTHONPATH=src python -c "from book_compiler import __version__; print(__version__)")"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$STAGE/src" "$STAGE/ui"
cp -R src/book_compiler "$STAGE/src/"
cp ui/server.py "$STAGE/ui/"
cp -R ui/static "$STAGE/ui/"
cat > "$STAGE/version.json" <<EOF
{
  "version": "$VERSION",
  "built_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF

mkdir -p dist
OUT="$ROOT/dist/runtime-${VERSION}.zip"
rm -f "$OUT"
(cd "$STAGE" && zip -rq "$OUT" .)

SHA="$(shasum -a 256 "$OUT" | awk '{print $1}')"
REPO="${BEANREAD_GITHUB_REPO:-ZhuominLi/book-compiler}"
echo ""
echo "Built: $OUT"
echo "SHA256: $SHA"
echo ""
echo "Publish to GitHub Releases:"
echo "  ./scripts/publish-runtime-release.sh \"更新说明\""
echo ""
echo "runtime-manifest.json preview:"
cat <<EOF
{
  "version": "$VERSION",
  "url": "https://github.com/${REPO}/releases/download/v${VERSION}/runtime-${VERSION}.zip",
  "sha256": "$SHA",
  "shell_min": "0.1.0",
  "notes": "更新说明"
}
EOF
