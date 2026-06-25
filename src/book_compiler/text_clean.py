"""Clean OCR / PDF-extracted plain text before split and display."""

from __future__ import annotations

import re

_CJK = re.compile(r"[\u4e00-\u9fff]")
_GARBAGE_URL = re.compile(r"yabook\.org|https?://", re.I)
_PAGE = re.compile(r"^---\s*第\s*(\d+)\s*页\s*---\s*$")
_LATIN_WORD = re.compile(r"[A-Za-z]{3,}")


def normalize_text(raw: str) -> str:
    """Strip null bytes and normalize newlines."""
    if not raw:
        return ""
    return raw.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")


def parse_page_marker(line: str) -> int | None:
    m = _PAGE.match(line.strip())
    return int(m.group(1)) if m else None


def is_garbage_line(line: str) -> bool:
    """PDF watermark / font-mapping junk, not readable prose."""
    t = line.strip()
    if not t:
        return False
    if parse_page_marker(t) is not None:
        return False
    if _GARBAGE_URL.search(t):
        return True

    cjk = len(_CJK.findall(t))
    if cjk > 0:
        return False

    # No Chinese characters — likely junk unless a real English sentence
    if len(t) > 60 and _LATIN_WORD.search(t) and t.count(" ") >= 3:
        return False

    if any(ord(c) < 32 for c in t):
        return True

    printable = sum(1 for c in t if c.isprintable())
    if len(t) >= 2 and printable / len(t) < 0.85:
        return True

    # Symbol / Latin fragments: }"0, fôY, ÅNf0
    if re.search(r"[A-Za-z]", t) or re.search(r"[^\x00-\x7f\u3000-\u303f\uff00-\uffef]", t):
        return True

    if len(t) <= 12 and re.fullmatch(r"[\W\d_]+", t, re.UNICODE):
        return True

    return False


def clean_lines(lines: list[str]) -> list[str]:
    """Replace garbage with empty lines (preserves line numbers / L anchors)."""
    return ["" if is_garbage_line(line.replace("\x00", "")) else line.replace("\x00", "") for line in lines]
