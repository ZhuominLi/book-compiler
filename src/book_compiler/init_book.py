"""Scaffold a new book NOTE directory."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .paths import READINGS_PM, meta_path, register_book, summary_dir, insight_dir, state_dir


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slugify(title: str) -> str:
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "-", title.strip().lower())
    return s.strip("-")[:48] or "book"


def init_book(
    *,
    title: str,
    slug: str | None = None,
    source_txt: Path | None = None,
    source_text: str | None = None,
    source_filename: str | None = None,
    source_format: str | None = None,
    ingest_warnings: list[str] | None = None,
    original_file_bytes: bytes | None = None,
    original_file_name: str | None = None,
    book_type: str = "M",
    note_dir: Path | None = None,
) -> Path:
    """Create {title}NOTE/ with summary/ + insight/ skeleton."""
    slug = slug or _slugify(title)
    root = note_dir or (READINGS_PM / f"{title}NOTE")
    root.mkdir(parents=True, exist_ok=True)
    (root / "_extract").mkdir(exist_ok=True)
    summary_dir(root)
    insight_dir(root)
    state_dir(root)
    (root / "skill").mkdir(exist_ok=True)
    (summary_dir(root) / "chapters").mkdir(exist_ok=True)

    rel_source = None
    pdf_file = None
    epub_file = None
    if source_text:
        fn = source_filename or f"{title}.txt"
        (root / fn).write_text(source_text, encoding="utf-8")
        rel_source = fn
    elif source_txt and source_txt.is_file():
        rel_source = source_txt.name
        if not (root / rel_source).exists() and source_txt.parent != root:
            import shutil
            shutil.copy2(source_txt, root / rel_source)

    if original_file_bytes and original_file_name:
        ext = Path(original_file_name).suffix.lower()
        if ext == ".pdf":
            pdf_name = Path(original_file_name).name
            (root / pdf_name).write_bytes(original_file_bytes)
            pdf_file = pdf_name
        elif ext == ".epub":
            epub_name = Path(original_file_name).name
            (root / epub_name).write_bytes(original_file_bytes)
            epub_file = epub_name

    ingest: dict = {
        "source_format": source_format or "txt",
        "original_filename": source_filename,
        "ingested_at": _now(),
        "warnings": ingest_warnings or [],
    }
    if pdf_file:
        ingest["pdf_file"] = pdf_file
    if epub_file:
        ingest["epub_file"] = epub_file
        try:
            from .ingest.adapters.epub import spine_item_count

            ingest["epub_spine_count"] = spine_item_count(original_file_bytes)
        except Exception:
            pass

    meta = {
        "schema_version": "0.1",
        "title": title,
        "slug": slug,
        "source_file": rel_source,
        "ingest": ingest,
        "language": "zh",
        "book_type": book_type,
        "book_type_reason": "",
        "created_at": _now(),
        "updated_at": _now(),
        "pipeline": {
            "preview_done": False,
            "deep_done": False,
            "deep_current_chapter": None,
            "insight_done": False,
            "skill_compiled_at": None,
        },
        "chapters": [],
        "skill": {"slug": slug, "triggers": [title], "install_paths": [f"~/.cursor/skills/{slug}"]},
    }
    meta_path(root).write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    register_book(slug, root)
    return root
