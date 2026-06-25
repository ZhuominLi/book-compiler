"""Ingest pipeline entry — bytes or text → BookDraft."""

from __future__ import annotations

from pathlib import Path

from .canonical import BookDraft, IngestResult
from .registry import EXTENSION_MAP, SUPPORTED_EXTENSIONS, get_adapter


def detect_format(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in EXTENSION_MAP:
        raise ValueError(
            f"不支持的文件扩展名: {ext or '(无)'}，支持 {', '.join(SUPPORTED_EXTENSIONS)}"
        )
    return EXTENSION_MAP[ext]


def ingest_bytes(data: bytes, filename: str, *, fmt: str | None = None) -> BookDraft:
    fmt = fmt or detect_format(filename)
    adapter = get_adapter(fmt)
    draft = adapter(data, filename)
    if draft.needs_ocr:
        return draft
    if not draft.text.strip():
        raise ValueError("导入后正文为空")
    return draft


def ingest_text(text: str, filename: str) -> BookDraft:
    return ingest_bytes(text.encode("utf-8"), filename, fmt=detect_format(filename))


def save_canonical(root: Path, draft: BookDraft, *, title: str) -> str:
    """Write normalized text to NOTE root; return relative path."""
    ext = ".txt" if draft.source_format != "md" else ".md"
    name = f"{title}{ext}" if draft.original_filename else f"source{ext}"
    # keep original stem when sensible
    stem = Path(draft.original_filename).stem if draft.original_filename else title
    rel = f"{stem}.txt"
    if (root / rel).exists():
        rel = f"_ingest/{stem}.txt"
        (root / "_ingest").mkdir(exist_ok=True)
    (root / rel).write_text(draft.text, encoding="utf-8")
    return rel
