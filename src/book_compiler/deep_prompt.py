"""Per-book deep Summary prompt: preset binding + optional custom override."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .paths import meta_path, state_dir
from .prompt_presets import (
    BUILTIN_M,
    BUILTIN_N,
    create_preset,
    default_preset_id,
    get_preset,
    list_presets,
    resolve_preset_prompt,
)
from .prompts import PROMPT_REVISION, SYSTEM_M, SYSTEM_N

_VALID = frozenset({"M", "N"})


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_meta(root: Path) -> dict:
    return json.loads(meta_path(root).read_text(encoding="utf-8"))


def _save_meta(root: Path, meta: dict) -> None:
    meta["updated_at"] = _now()
    meta_path(root).write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def default_deep_prompt(template: str) -> str:
    t = template if template in _VALID else "M"
    return SYSTEM_N if t == "N" else SYSTEM_M


def deep_prompt_path(root: Path, template: str) -> Path:
    t = template if template in _VALID else "M"
    return state_dir(root) / f"deep-prompt-{t}.txt"


def _read_custom_file(root: Path, template: str) -> str:
    fp = deep_prompt_path(root, template)
    if not fp.is_file():
        return ""
    return fp.read_text(encoding="utf-8").strip()


def _binding(meta: dict, template: str) -> dict:
    return (meta.get("deep_prompt") or {}).get(template) or {}


def _set_binding(root: Path, meta: dict, template: str, mode: str, preset_id: str | None = None) -> None:
    t = template if template in _VALID else "M"
    dp = meta.setdefault("deep_prompt", {})
    if mode == "default":
        dp.pop(t, None)
        if not dp:
            meta.pop("deep_prompt", None)
    elif mode == "preset":
        dp[t] = {"mode": "preset", "preset_id": preset_id or default_preset_id(t)}
    elif mode == "custom":
        dp[t] = {"mode": "custom"}
    _save_meta(root, meta)


def _clear_custom_file(root: Path, template: str) -> None:
    fp = deep_prompt_path(root, template)
    if fp.is_file():
        fp.unlink()


def _resolve_mode_and_prompt(root: Path, meta: dict, template: str) -> tuple[str, str, str | None, bool]:
    """Returns mode, prompt_text, preset_id, is_custom."""
    t = template if template in _VALID else "M"
    bind = _binding(meta, t)
    custom = _read_custom_file(root, t)

    if bind.get("mode") == "preset":
        pid = bind.get("preset_id") or default_preset_id(t)
        try:
            return "preset", resolve_preset_prompt(pid), pid, False
        except ValueError:
            pid = default_preset_id(t)
            return "preset", resolve_preset_prompt(pid), pid, False

    if bind.get("mode") == "custom" or (custom and not bind):
        text = custom or default_deep_prompt(t)
        return "custom", text, None, bool(custom)

    pid = default_preset_id(t)
    return "preset", resolve_preset_prompt(pid), pid, False


def _repair_stale_preset_binding(root: Path, meta: dict, template: str) -> dict:
    t = template if template in _VALID else "M"
    bind = _binding(meta, t)
    if bind.get("mode") != "preset":
        return meta
    pid = bind.get("preset_id")
    if pid and get_preset(pid):
        return meta
    _set_binding(root, meta, t, "preset", default_preset_id(t))
    return _load_meta(root)


def get_deep_prompt(root: Path, template: str) -> dict:
    t = template if template in _VALID else "M"
    meta = _load_meta(root)
    meta = _repair_stale_preset_binding(root, meta, t)
    mode, prompt, preset_id, is_custom = _resolve_mode_and_prompt(root, meta, t)
    presets = [
        {
            "id": p["id"],
            "name": p["name"],
            "icon": p["icon"],
            "template": p["template"],
            "builtin": p.get("builtin", False),
        }
        for p in list_presets(t)
    ]
    active = get_preset_summary(preset_id) if preset_id else None
    return {
        "template": t,
        "mode": mode,
        "preset_id": preset_id,
        "active_preset": active,
        "prompt": prompt,
        "default_prompt": default_deep_prompt(t),
        "is_custom": is_custom,
        "presets": presets,
        "prompt_revision": PROMPT_REVISION,
    }


def get_preset_summary(preset_id: str) -> dict | None:
    from .prompt_presets import get_preset

    p = get_preset(preset_id)
    if not p:
        return None
    return {
        "id": p["id"],
        "name": p["name"],
        "icon": p["icon"],
        "template": p["template"],
        "builtin": p.get("builtin", False),
    }


def bind_deep_prompt_preset(root: Path, template: str, preset_id: str) -> dict:
    resolve_preset_prompt(preset_id)
    meta = _load_meta(root)
    _set_binding(root, meta, template, "preset", preset_id)
    _clear_custom_file(root, template)
    return get_deep_prompt(root, template)


def save_deep_prompt(root: Path, template: str, prompt: str) -> dict:
    t = template if template in _VALID else "M"
    text = (prompt or "").strip()
    if not text:
        raise ValueError("prompt 不能为空")
    meta = _load_meta(root)
    state_dir(root).mkdir(parents=True, exist_ok=True)
    deep_prompt_path(root, t).write_text(text + "\n", encoding="utf-8")
    _set_binding(root, meta, t, "custom")
    return get_deep_prompt(root, t)


def reset_deep_prompt(root: Path, template: str) -> dict:
    t = template if template in _VALID else "M"
    meta = _load_meta(root)
    _clear_custom_file(root, t)
    pid = default_preset_id(t)
    _set_binding(root, meta, t, "preset", pid)
    return get_deep_prompt(root, t)


def save_deep_prompt_as_preset(
    root: Path,
    template: str,
    name: str,
    icon: str,
    prompt: str,
    *,
    bind: bool = True,
) -> dict:
    entry = create_preset(name, icon, template, prompt)
    if bind:
        return bind_deep_prompt_preset(root, template, entry["id"])
    return get_deep_prompt(root, template)


def resolve_deep_system_prompt(root: Path, template: str) -> str:
    meta = _load_meta(root)
    _, prompt, _, _ = _resolve_mode_and_prompt(root, meta, template)
    return prompt
