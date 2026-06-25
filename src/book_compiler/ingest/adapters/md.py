"""Markdown adapter — strip frontmatter, keep body as plain text for split."""

from __future__ import annotations

import re

from ..canonical import BookDraft


def _strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        m = re.match(r"^---\s*\n[\s\S]*?\n---\s*\n", text)
        if m:
            return text[m.end() :]
    return text


def adapt(data: bytes, filename: str) -> BookDraft:
    for enc in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            raw = data.decode(enc)
            break
        except UnicodeDecodeError:
            raw = None
    if raw is None:
        raise ValueError("无法解码 Markdown 文件")

    body = _strip_frontmatter(raw).strip()
    return BookDraft(
        text=body + "\n",
        source_format="md",
        original_filename=filename,
        warnings=["Markdown 已转为纯文本供分章；Summary 仍以 .md 存储"],
    )
