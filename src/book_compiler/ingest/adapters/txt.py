"""Plain text adapter."""

from __future__ import annotations

from ..canonical import BookDraft


def adapt(data: bytes, filename: str) -> BookDraft:
    for enc in ("utf-8", "utf-8-sig", "gb18030", "gbk"):
        try:
            text = data.decode(enc)
            warnings = [] if enc == "utf-8" else [f"以 {enc} 解码"]
            return BookDraft(text=text, source_format="txt", original_filename=filename, warnings=warnings)
        except UnicodeDecodeError:
            continue
    raise ValueError("无法解码文本文件，请转为 UTF-8 后重试")
