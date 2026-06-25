"""Original source file helpers for reader UI (PDF / EPUB)."""

from __future__ import annotations

import json
from pathlib import Path

from .text_clean import normalize_text, parse_page_marker


def asset_file_path(root: Path, meta: dict, key: str) -> Path | None:
    name = (meta.get("ingest") or {}).get(key)
    if not name:
        return None
    fp = root / name
    return fp if fp.is_file() else None


def pdf_file_path(root: Path, meta: dict) -> Path | None:
    return asset_file_path(root, meta, "pdf_file")


def epub_file_path(root: Path, meta: dict) -> Path | None:
    return asset_file_path(root, meta, "epub_file")


def _full_book_text(root: Path, meta: dict) -> str | None:
    name = meta.get("source_file")
    if not name:
        return None
    fp = root / name
    if not fp.is_file():
        return None
    return normalize_text(fp.read_bytes().decode("utf-8", errors="replace"))


def line_pdf_page_in_full_book(root: Path, meta: dict, absolute_line: int) -> int:
    text = _full_book_text(root, meta)
    if not text:
        return 1
    page = 1
    for i, line in enumerate(text.splitlines(), start=1):
        marker = parse_page_marker(line)
        if marker is not None:
            page = marker
        if i >= max(1, absolute_line):
            break
    return page


def _first_page_marker_in_extract(root: Path, ch: dict) -> int | None:
    src = root / ch.get("source", "")
    if not src.is_file():
        return None
    text = normalize_text(src.read_bytes().decode("utf-8", errors="replace"))
    for line in text.splitlines():
        marker = parse_page_marker(line)
        if marker is not None:
            return marker
    return None


def chapter_pdf_page(root: Path, meta: dict, chapter_id: str) -> int:
    ch = next((c for c in meta.get("chapters", []) if c.get("id") == chapter_id), None)
    if not ch:
        return 1
    line_start = ch.get("line_start")
    if line_start:
        return line_pdf_page_in_full_book(root, meta, int(line_start))
    marker = _first_page_marker_in_extract(root, ch)
    if marker is not None:
        return marker
    return line_pdf_page(root, meta, chapter_id, 1)


def line_pdf_page(root: Path, meta: dict, chapter_id: str, line_no: int) -> int:
    ch = next((c for c in meta.get("chapters", []) if c.get("id") == chapter_id), None)
    if not ch:
        return 1
    line_start = ch.get("line_start")
    if line_start:
        absolute = int(line_start) + max(0, int(line_no) - 1)
        return line_pdf_page_in_full_book(root, meta, absolute)
    src = root / ch.get("source", "")
    if not src.is_file():
        return 1
    text = normalize_text(src.read_bytes().decode("utf-8", errors="replace"))
    page = 1
    first_marker: int | None = None
    for i, line in enumerate(text.splitlines(), start=1):
        marker = parse_page_marker(line)
        if marker is not None:
            page = marker
            if first_marker is None:
                first_marker = marker
        if i >= max(1, line_no):
            break
    if line_no <= 1 and first_marker is not None:
        return first_marker
    return page


def chapter_epub_spine_index(root: Path, meta: dict, chapter_id: str) -> int:
    loc = chapter_epub_location(root, meta, chapter_id)
    return loc["spine_index"]


def chapter_epub_location(root: Path, meta: dict, chapter_id: str) -> dict:
    ch = next((c for c in meta.get("chapters", []) if c.get("id") == chapter_id), None)
    has_epub = epub_file_path(root, meta) is not None
    if not ch:
        return {"spine_index": 0, "href": None, "has_epub": has_epub}
    href = ch.get("epub_href")
    if ch.get("epub_spine_index") is not None:
        return {"spine_index": int(ch["epub_spine_index"]), "href": href, "has_epub": has_epub}
    idx = max(0, (ch.get("index") or 1) - 1)
    spine_count = (meta.get("ingest") or {}).get("epub_spine_count")
    if spine_count:
        idx = min(idx, max(0, int(spine_count) - 1))
    return {"spine_index": idx, "href": href, "has_epub": has_epub}


def load_meta(root: Path) -> dict:
    from .paths import meta_path

    return json.loads(meta_path(root).read_text(encoding="utf-8"))
