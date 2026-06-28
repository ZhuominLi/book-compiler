"""LLM backend — DeepSeek / OpenAI-compatible API."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .llm_settings import active_config, is_configured

MAX_OUTPUT_TOKENS = 8192


@dataclass
class StreamChunk:
    text: str = ""
    completion_tokens: int | None = None
    finish_reason: str | None = None


def estimate_tokens(text: str) -> int:
    """Rough live estimate for mixed Chinese/English (not billing-accurate)."""
    if not text:
        return 0
    cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    other = len(text) - cjk
    return max(0, int(cjk * 0.85 + other / 4))


def _api_key() -> str | None:
    key = (active_config().get("api_key") or "").strip()
    return key or None


def _base_url() -> str | None:
    return (active_config().get("base_url") or "").strip() or None


def _model() -> str:
    return (active_config().get("model") or "").strip() or "deepseek-chat"


def has_llm() -> bool:
    return is_configured()


def _normalize_base(url: str) -> str:
    base = url.rstrip("/")
    if not base.endswith("/v1"):
        base += "/v1"
    return base


def _http_client():
    import ssl

    import httpx

    # trust_env=False: bypass broken system HTTP_PROXY (causes Connection refused)
    try:
        import certifi

        ca = certifi.where()
        if Path(ca).is_file():
            return httpx.Client(
                verify=ca,
                trust_env=False,
                timeout=httpx.Timeout(connect=30.0, read=600.0, write=30.0, pool=30.0),
            )
    except (ImportError, OSError, FileNotFoundError):
        pass
    return httpx.Client(
        verify=ssl.create_default_context(),
        trust_env=False,
        timeout=httpx.Timeout(connect=30.0, read=600.0, write=30.0, pool=30.0),
    )


def _client():
    from openai import OpenAI

    kwargs: dict = {"api_key": _api_key()}
    base = _base_url()
    if base:
        kwargs["base_url"] = _normalize_base(base)
    kwargs["http_client"] = _http_client()
    return OpenAI(**kwargs)


def _completion_kwargs(model: str | None) -> dict:
    return {
        "model": model or _model(),
        "temperature": 0.6,
        "max_tokens": MAX_OUTPUT_TOKENS,
    }


def complete(system: str, user: str, model: str | None = None) -> str:
    """Call LLM with explicit max_tokens."""
    if not has_llm():
        return _heuristic(user)
    resp = _client().chat.completions.create(
        **_completion_kwargs(model),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp.choices[0].message.content or ""


def complete_stream(system: str, user: str, model: str | None = None) -> Iterator[StreamChunk]:
    """Yield text chunks; final chunk may carry API usage / finish_reason."""
    if not has_llm():
        yield StreamChunk(text=_heuristic(user))
        return

    stream = _client().chat.completions.create(
        **_completion_kwargs(model),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        stream=True,
        stream_options={"include_usage": True},
    )

    finish_reason: str | None = None
    completion_tokens: int | None = None

    for chunk in stream:
        usage = getattr(chunk, "usage", None)
        if usage and usage.completion_tokens is not None:
            completion_tokens = usage.completion_tokens

        if not chunk.choices:
            continue

        choice = chunk.choices[0]
        if choice.finish_reason:
            finish_reason = choice.finish_reason
        delta = choice.delta.content or ""
        if delta:
            yield StreamChunk(text=delta)

    if completion_tokens is not None or finish_reason:
        yield StreamChunk(completion_tokens=completion_tokens, finish_reason=finish_reason)


def _heuristic(prompt: str) -> str:
    if "章节原文" in prompt or "---SOURCE---" in prompt:
        src = prompt.split("---SOURCE---")[-1]
        headings = re.findall(r"^(.{4,80})$", src, re.MULTILINE)[:20]
        bullets = "\n".join(f"- {h.strip()}" for h in headings if h.strip())
        return (
            "（离线模式：请在设置中填写 API Key）\n\n## 提取的段落标题\n\n" + bullets + "\n"
        )
    return "（离线模式：请在设置 → AI 接口 中配置 API Key。）\n"


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
