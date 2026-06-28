"""Runtime hot-update — UI + Python logic overlay in Application Support."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from . import __version__
from .paths import app_data_dir, bundle_resources_dir

_MANIFEST_ENV = "BEANREAD_UPDATE_MANIFEST"
_DEFAULT_MANIFEST = "https://raw.githubusercontent.com/ZhuominLi/book-compiler/master/runtime-manifest.json"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def runtime_dir() -> Path:
    return app_data_dir() / "runtime"


def parse_version(raw: str) -> tuple[int, ...]:
    s = raw.strip().lstrip("vV")
    parts: list[int] = []
    for piece in re.split(r"[.+_-]", s):
        if not piece:
            continue
        digits = re.match(r"^(\d+)", piece)
        parts.append(int(digits.group(1)) if digits else 0)
    return tuple(parts or (0,))


def version_gte(a: str, b: str) -> bool:
    return parse_version(a) >= parse_version(b)


def _read_json(fp: Path) -> dict:
    if not fp.is_file():
        return {}
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def bundled_version(bundle_root: Path | None = None) -> str:
    root = bundle_root or bundle_resources_dir()
    if root:
        meta = _read_json(root / "runtime-version.json")
        if meta.get("version"):
            return str(meta["version"])
    return __version__


def installed_runtime_version() -> str | None:
    info = _read_json(runtime_dir() / "version.json")
    ver = (info.get("version") or "").strip()
    return ver or None


def runtime_is_valid(root: Path) -> bool:
    return (
        (root / "version.json").is_file()
        and (root / "src" / "book_compiler").is_dir()
        and (root / "ui" / "server.py").is_file()
        and (root / "ui" / "static" / "index.html").is_file()
    )


def active_runtime_root() -> Path | None:
    """Installed runtime overlay (packaged app only, when >= bundled version)."""
    if not _is_frozen():
        return None
    rt = runtime_dir()
    if not runtime_is_valid(rt):
        return None
    inst = installed_runtime_version()
    if not inst:
        return None
    bundle = bundled_version()
    if version_gte(inst, bundle):
        return rt
    return None


def activate_runtime_overlay(bundle_root: Path) -> dict:
    """Prepend runtime paths to sys.path when a newer runtime is installed."""
    active = active_runtime_root()
    if active:
        ui = str(active / "ui")
        src = str(active / "src")
        for path in (ui, src):
            if path not in sys.path:
                sys.path.insert(0, path)
    return runtime_status(bundle_root)


def runtime_static_dir() -> Path | None:
    rt = active_runtime_root()
    if not rt:
        return None
    static = rt / "ui" / "static"
    return static if (static / "index.html").is_file() else None


def runtime_status(bundle_root: Path | None = None) -> dict:
    bundle = bundled_version(bundle_root)
    installed = installed_runtime_version()
    active = active_runtime_root()
    return {
        "frozen": _is_frozen(),
        "bundled_version": bundle,
        "runtime_version": installed,
        "active_version": (installed if active else bundle),
        "source": "runtime" if active else "bundled",
        "runtime_path": str(runtime_dir()) if installed else None,
    }


def manifest_url() -> str:
    if url := os.environ.get(_MANIFEST_ENV):
        return url.strip()
    local = app_data_dir() / "update-manifest.json"
    if local.is_file():
        return local.resolve().as_uri()
    return _DEFAULT_MANIFEST


def _fetch_manifest(url: str) -> dict:
    if url.startswith("file:"):
        from urllib.parse import unquote, urlparse

        fp = Path(unquote(urlparse(url).path))
        return _read_json(fp)
    req = urllib.request.Request(url, headers={"User-Agent": "BeanRead-Updater"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("manifest 格式无效")
    return data


def check_for_update(bundle_root: Path | None = None) -> dict:
    status = runtime_status(bundle_root)
    current = status["active_version"]
    try:
        manifest = _fetch_manifest(manifest_url())
    except (OSError, urllib.error.URLError, json.JSONDecodeError, ValueError) as e:
        return {**status, "ok": False, "error": str(e), "update_available": False}

    latest = str(manifest.get("version") or "").strip()
    if not latest:
        return {**status, "ok": False, "error": "manifest 缺少 version", "update_available": False}

    shell_min = str(manifest.get("shell_min") or "0.0.0")
    if not version_gte(status["bundled_version"], shell_min):
        return {
            **status,
            "ok": False,
            "error": f"当前 Shell {status['bundled_version']} 过旧，需整包升级（要求 ≥ {shell_min}）",
            "update_available": False,
            "latest": latest,
        }

    return {
        **status,
        "ok": True,
        "current": current,
        "latest": latest,
        "update_available": version_gte(latest, current) and latest != current,
        "url": manifest.get("url"),
        "sha256": manifest.get("sha256") or "",
        "notes": manifest.get("notes") or "",
    }


def _download(url: str) -> bytes:
    if not url.startswith("https://"):
        raise ValueError("仅支持 https 下载")
    req = urllib.request.Request(url, headers={"User-Agent": "BeanRead-Updater"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def _verify_sha256(data: bytes, expected: str) -> None:
    expected = expected.strip().lower()
    if not expected:
        return
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected:
        raise ValueError("sha256 校验失败")


def _extract_runtime_zip(data: bytes, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(BytesIO(data)) as zf:
            zf.extractall(tmp_path)
        # zip may contain top-level version.json or nested runtime/
        root = tmp_path
        if (tmp_path / "runtime" / "version.json").is_file():
            root = tmp_path / "runtime"
        elif not (tmp_path / "version.json").is_file():
            for child in tmp_path.iterdir():
                if child.is_dir() and (child / "version.json").is_file():
                    root = child
                    break
        if not runtime_is_valid(root):
            raise ValueError("runtime 包结构无效（需含 version.json、src/book_compiler、ui/）")
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(root, dest)


def apply_runtime_update(url: str, sha256: str = "") -> dict:
    data = _download(url)
    _verify_sha256(data, sha256)
    target = runtime_dir()
    staging = app_data_dir() / ".runtime-staging"
    backup = app_data_dir() / ".runtime-backup"
    if staging.exists():
        shutil.rmtree(staging)
    if backup.exists():
        shutil.rmtree(backup)
    _extract_runtime_zip(data, staging)
    if target.exists():
        target.rename(backup)
    try:
        staging.rename(target)
    except OSError:
        if backup.exists() and not target.exists():
            backup.rename(target)
        raise
    if backup.exists():
        shutil.rmtree(backup, ignore_errors=True)
    info = _read_json(target / "version.json")
    info["installed_at"] = _now()
    (target / "version.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "ok": True,
        "runtime_version": info.get("version"),
        "restart_required": True,
        "message": "更新已安装，请完全退出并重新打开懒豆阅读",
    }
