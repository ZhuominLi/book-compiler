"""LLM backend — DeepSeek / OpenAI-compatible API."""

from __future__ import annotations

import os
import re
from pathlib import Path


def _api_key() -> str | None:
    return os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")


def _base_url() -> str | None:
    return os.environ.get("LLM_BASE_URL") or os.environ.get("OPENAI_BASE_URL")


def _model() -> str:
    return (
        os.environ.get("LLM_MODEL")
        or os.environ.get("BOOK_COMPILER_MODEL")
        or os.environ.get("OPENAI_MODEL")
        or "deepseek-chat"
    )


def has_llm() -> bool:
    return bool(_api_key())


def _normalize_base(url: str) -> str:
    base = url.rstrip("/")
    if not base.endswith("/v1"):
        base += "/v1"
    return base


def _client():
    import httpx
    from openai import OpenAI

    kwargs: dict = {"api_key": _api_key()}
    base = _base_url()
    if base:
        kwargs["base_url"] = _normalize_base(base)
    # trust_env=False: bypass broken system HTTP_PROXY (causes Connection refused)
    kwargs["http_client"] = httpx.Client(trust_env=False, timeout=120.0)
    return OpenAI(**kwargs)


def complete(system: str, user: str, model: str | None = None) -> str:
    """Call LLM. No input truncation, no max_tokens cap on output."""
    if not has_llm():
        return _heuristic(user)
    resp = _client().chat.completions.create(
        model=model or _model(),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.3,
    )
    return resp.choices[0].message.content or ""


def _heuristic(prompt: str) -> str:
    if "章节原文" in prompt or "---SOURCE---" in prompt:
        src = prompt.split("---SOURCE---")[-1]
        headings = re.findall(r"^(.{4,80})$", src, re.MULTILINE)[:20]
        bullets = "\n".join(f"- {h.strip()}" for h in headings if h.strip())
        return (
            "（离线模式：请配置 LLM_API_KEY）\n\n## 提取的段落标题\n\n" + bullets + "\n"
        )
    return "（离线模式：需 LLM_API_KEY。）\n"


def load_env_file(path: Path | None = None) -> None:
    env_path = path or Path(__file__).resolve().parents[2] / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip("'\""))
