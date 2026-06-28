"""Global reusable deep Summary prompt presets (style library)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .paths import app_data_dir
from .prompts import SYSTEM_M, SYSTEM_N

BUILTIN_M = "builtin-m"
BUILTIN_N = "builtin-n"
_VALID_TEMPLATES = frozenset({"M", "N"})

_BUILTIN = [
    {
        "id": BUILTIN_M,
        "name": "概念清单",
        "icon": "📋",
        "template": "M",
        "builtin": True,
    },
    {
        "id": BUILTIN_N,
        "name": "叙事串联",
        "icon": "📖",
        "template": "N",
        "builtin": True,
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def presets_path() -> Path:
    return app_data_dir() / "prompt-presets.json"


def _load_store() -> dict:
    fp = presets_path()
    if not fp.is_file():
        return {"schema_version": "1.0", "presets": []}
    return json.loads(fp.read_text(encoding="utf-8"))


def _save_store(data: dict) -> None:
    presets_path().write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _builtin_prompt(template: str) -> str:
    return SYSTEM_N if template == "N" else SYSTEM_M


def _slugify(name: str) -> str:
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "-", name.strip().lower()).strip("-")
    return s[:40] or "style"


def list_presets(template: str | None = None) -> list[dict]:
    t = template if template in _VALID_TEMPLATES else None
    user = _load_store().get("presets", [])
    out: list[dict] = []
    for p in _BUILTIN:
        if t and p["template"] != t:
            continue
        out.append({**p, "user": False})
    for p in user:
        if t and p.get("template") != t:
            continue
        out.append({**p, "builtin": False, "user": True})
    return out


def get_preset(preset_id: str) -> dict | None:
    for p in _BUILTIN:
        if p["id"] == preset_id:
            return {**p, "user": False}
    for p in _load_store().get("presets", []):
        if p.get("id") == preset_id:
            return {**p, "builtin": False, "user": True}
    return None


def resolve_preset_prompt(preset_id: str) -> str:
    p = get_preset(preset_id)
    if not p:
        raise ValueError(f"未知风格 preset: {preset_id}")
    if p.get("builtin"):
        return _builtin_prompt(p["template"])
    text = (p.get("prompt") or "").strip()
    if not text:
        raise ValueError(f"风格 {preset_id} 的 prompt 为空")
    return text


def default_preset_id(template: str) -> str:
    return BUILTIN_N if template == "N" else BUILTIN_M


def create_preset(name: str, icon: str, template: str, prompt: str) -> dict:
    t = template if template in _VALID_TEMPLATES else "M"
    text = (prompt or "").strip()
    if not text:
        raise ValueError("prompt 不能为空")
    name = (name or "").strip() or "未命名风格"
    icon = (icon or "").strip() or "✨"
    store = _load_store()
    presets = store.setdefault("presets", [])
    base = _slugify(name)
    pid = base
    n = 1
    existing = {p["id"] for p in presets} | {b["id"] for b in _BUILTIN}
    while pid in existing:
        pid = f"{base}-{n}"
        n += 1
    entry = {
        "id": pid,
        "name": name,
        "icon": icon,
        "template": t,
        "prompt": text,
        "created_at": _now(),
        "updated_at": _now(),
    }
    presets.append(entry)
    _save_store(store)
    return {**entry, "builtin": False, "user": True}


def update_preset(preset_id: str, *, name: str | None = None, icon: str | None = None, prompt: str | None = None) -> dict:
    if get_preset(preset_id) and get_preset(preset_id).get("builtin"):
        raise ValueError("内置风格不可编辑")
    store = _load_store()
    for p in store.get("presets", []):
        if p.get("id") != preset_id:
            continue
        if name is not None:
            p["name"] = name.strip() or p["name"]
        if icon is not None:
            p["icon"] = icon.strip() or p["icon"]
        if prompt is not None:
            text = prompt.strip()
            if not text:
                raise ValueError("prompt 不能为空")
            p["prompt"] = text
        p["updated_at"] = _now()
        _save_store(store)
        return {**p, "builtin": False, "user": True}
    raise ValueError(f"风格不存在: {preset_id}")


def delete_preset(preset_id: str) -> None:
    p = get_preset(preset_id)
    if not p:
        raise ValueError(f"风格不存在: {preset_id}")
    if p.get("builtin"):
        raise ValueError("内置风格不可删除")
    store = _load_store()
    presets = store.get("presets", [])
    store["presets"] = [x for x in presets if x.get("id") != preset_id]
    _save_store(store)
