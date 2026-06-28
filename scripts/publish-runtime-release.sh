#!/usr/bin/env bash
# Build runtime zip → GitHub Release → update runtime-manifest.json on disk.
# After running: commit & push runtime-manifest.json to main (app pulls it via raw.githubusercontent.com).
#
# Prerequisites:
#   brew install gh && gh auth login
#   gh repo view ZhuominLi/book-compiler  # repo must exist and you have release permission
#
# Usage:
#   ./scripts/publish-runtime-release.sh              # notes from __version__
#   ./scripts/publish-runtime-release.sh "修复 xxx"   # custom release notes
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

REPO="${BEANREAD_GITHUB_REPO:-ZhuominLi/book-compiler}"
NOTES="${1:-}"

fail() { echo "ERROR: $*" >&2; exit 1; }

command -v gh >/dev/null || fail "需要 GitHub CLI：brew install gh && gh auth login"

VERSION="$(PYTHONPATH=src python -c "from book_compiler import __version__; print(__version__)")"
TAG="v${VERSION}"
ZIP_NAME="runtime-${VERSION}.zip"
ZIP_PATH="$ROOT/dist/$ZIP_NAME"
MANIFEST="$ROOT/runtime-manifest.json"
SHELL_MIN="$(python3 -c "import json; print(json.load(open('$ROOT/runtime-version.json'))['shell_min'])")"

echo "▸ Building runtime ${VERSION} ..."
"$ROOT/scripts/build-runtime.sh" | tail -n +1

[[ -f "$ZIP_PATH" ]] || fail "missing $ZIP_PATH"

SHA256="$(shasum -a 256 "$ZIP_PATH" | awk '{print $1}')"
DOWNLOAD_URL="https://github.com/${REPO}/releases/download/${TAG}/${ZIP_NAME}"
NOTES="${NOTES:-Runtime hot-update ${VERSION}}"

echo ""
echo "▸ Publishing GitHub Release ${TAG} (${REPO}) ..."
if gh release view "$TAG" --repo "$REPO" >/dev/null 2>&1; then
  gh release upload "$TAG" "$ZIP_PATH" --repo "$REPO" --clobber
  gh release edit "$TAG" --repo "$REPO" --notes "$NOTES"
else
  gh release create "$TAG" "$ZIP_PATH" \
    --repo "$REPO" \
    --title "Runtime ${VERSION}" \
    --notes "$NOTES"
fi

echo "▸ Writing runtime-manifest.json ..."
BEANREAD_VERSION="$VERSION" \
BEANREAD_DOWNLOAD_URL="$DOWNLOAD_URL" \
BEANREAD_SHA256="$SHA256" \
BEANREAD_SHELL_MIN="$SHELL_MIN" \
BEANREAD_MANIFEST="$MANIFEST" \
BEANREAD_RELEASE_NOTES="$NOTES" \
PYTHONPATH=src python3 - <<'PY'
import json
import os
from pathlib import Path

manifest = {
    "version": os.environ["BEANREAD_VERSION"],
    "url": os.environ["BEANREAD_DOWNLOAD_URL"],
    "sha256": os.environ["BEANREAD_SHA256"],
    "shell_min": os.environ["BEANREAD_SHELL_MIN"],
    "notes": os.environ.get("BEANREAD_RELEASE_NOTES", ""),
}
Path(os.environ["BEANREAD_MANIFEST"]).write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY

echo ""
echo "Done."
echo "  Release : https://github.com/${REPO}/releases/tag/${TAG}"
echo "  Manifest: ${MANIFEST}"
echo ""
echo "App 检查更新地址（需在 master 分支）："
echo "  https://raw.githubusercontent.com/${REPO}/master/runtime-manifest.json"
echo ""
echo "Next — 提交 manifest 到 master，客户端才能拉到："
echo "  git add runtime-manifest.json"
echo "  git commit -m \"chore: runtime manifest ${VERSION}\""
echo "  git push origin master"
