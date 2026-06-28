"""User LLM settings — persisted in app data, overrides .env for product use."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .paths import app_data_dir

_DEFAULT_BASE = "https://api.deepseek.com"
_DEFAULT_MODEL = "deepseek-chat"


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def _env_api_key() -> str | None:
    if _is_frozen():
        return None
    return os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")


def _env_base_url() -> str | None:
    if _is_frozen():
        return None
    return os.environ.get("LLM_BASE_URL") or os.environ.get("OPENAI_BASE_URL")


def _env_model() -> str | None:
    if _is_frozen():
        return None
    return os.environ.get("LLM_MODEL") or os.environ.get("OPENAI_MODEL")


def settings_path() -> Path:
    return app_data_dir() / "llm.json"


def _read_raw() -> dict:
    fp = settings_path()
    if not fp.is_file():
        return {}
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _key_hint(key: str | None) -> str | None:
    if not key or len(key) < 8:
        return None
    return f"{key[:3]}…{key[-4:]}"


def active_config() -> dict[str, str | None]:
    """Effective LLM config: user llm.json overrides environment."""
    saved = _read_raw()
    api_key = (saved.get("api_key") or "").strip() or _env_api_key()
    base_url = (saved.get("base_url") or "").strip() or _env_base_url() or _DEFAULT_BASE
    model = (saved.get("model") or "").strip() or _env_model() or _DEFAULT_MODEL
    return {"api_key": api_key, "base_url": base_url, "model": model}


def is_configured() -> bool:
    return bool((active_config().get("api_key") or "").strip())


def needs_user_setup() -> bool:
    """True until user saves their own API key in Settings (llm.json)."""
    return not bool((_read_raw().get("api_key") or "").strip())


def public_status() -> dict:
    cfg = active_config()
    key = (cfg.get("api_key") or "").strip()
    saved = _read_raw()
    user_key = (saved.get("api_key") or "").strip()
    return {
        "configured": bool(key),
        "needs_setup": needs_user_setup(),
        "source": "user" if user_key else ("env" if key else "none"),
        "base_url": cfg.get("base_url") or _DEFAULT_BASE,
        "model": cfg.get("model") or _DEFAULT_MODEL,
        "key_hint": _key_hint(key),
    }


def save_settings(*, api_key: str | None = None, base_url: str | None = None, model: str | None = None) -> dict:
    data = _read_raw()
    if api_key is not None:
        api_key = api_key.strip()
        if api_key:
            data["api_key"] = api_key
        else:
            data.pop("api_key", None)
    if base_url is not None:
        base_url = base_url.strip()
        if base_url:
            data["base_url"] = base_url
        else:
            data.pop("base_url", None)
    if model is not None:
        model = model.strip()
        if model:
            data["model"] = model
        else:
            data.pop("model", None)
    fp = settings_path()
    if data:
        fp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    elif fp.is_file():
        fp.unlink()
    return public_status()
