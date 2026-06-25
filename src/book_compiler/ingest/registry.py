"""Adapter registry — format id → ingest function."""

from __future__ import annotations

from collections.abc import Callable

from .adapters import docx, epub, md, pdf, txt
from .canonical import BookDraft

AdapterFn = Callable[[bytes, str], BookDraft]

_REGISTRY: dict[str, AdapterFn] = {
    "txt": txt.adapt,
    "md": md.adapt,
    "markdown": md.adapt,
    "docx": docx.adapt,
    "epub": epub.adapt,
    "pdf": pdf.adapt,
}

EXTENSION_MAP: dict[str, str] = {
    ".txt": "txt",
    ".md": "md",
    ".markdown": "md",
    ".docx": "docx",
    ".epub": "epub",
    ".pdf": "pdf",
}

SUPPORTED_EXTENSIONS = tuple(EXTENSION_MAP.keys())
SUPPORTED_LABEL = "txt · md · docx · epub · pdf（文字层）"


def get_adapter(fmt: str) -> AdapterFn:
    key = fmt.lower().lstrip(".")
    if key not in _REGISTRY:
        raise ValueError(f"不支持的格式: {fmt}（当前支持 {SUPPORTED_LABEL}）")
    return _REGISTRY[key]
