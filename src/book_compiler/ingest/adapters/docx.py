"""DOCX adapter — stdlib zip + XML, no python-docx required."""

from __future__ import annotations

import re
import zipfile
from io import BytesIO
from xml.etree import ElementTree as ET

from ..canonical import BookDraft

_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _extract_paragraphs(xml_bytes: bytes) -> list[str]:
    root = ET.fromstring(xml_bytes)
    paras: list[str] = []
    for p in root.iter(f"{_W_NS}p"):
        parts = [t.text for t in p.iter(f"{_W_NS}t") if t.text]
        if parts:
            paras.append("".join(parts))
    return paras


def adapt(data: bytes, filename: str) -> BookDraft:
    try:
        with zipfile.ZipFile(BytesIO(data)) as zf:
            if "word/document.xml" not in zf.namelist():
                raise ValueError("不是有效的 .docx 文件")
            xml = zf.read("word/document.xml")
    except zipfile.BadZipFile as e:
        raise ValueError("无法解析 .docx（损坏或非 zip）") from e

    paras = _extract_paragraphs(xml)
    if not paras:
        raise ValueError(".docx 中未提取到正文")

    text = "\n".join(paras).strip() + "\n"
    text = re.sub(r"\n{3,}", "\n\n", text)
    return BookDraft(
        text=text,
        source_format="docx",
        original_filename=filename,
        warnings=["Word 已转为纯文本；表格/图片未保留"],
    )
