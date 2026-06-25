"""Discover book NOTE directories."""

from __future__ import annotations

import json
from pathlib import Path

from .paths import READINGS_PM, book_root


def discover_books() -> list[dict]:
    found: dict[str, dict] = {}
    for note_dir in sorted(READINGS_PM.glob("*NOTE")):
        meta_path = note_dir / "insight" / "book-meta.json"
        if not meta_path.is_file():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        slug = meta.get("slug") or note_dir.name.replace("NOTE", "").lower()
        found[slug] = {
            "slug": slug,
            "title": meta.get("title", slug),
            "path": str(note_dir),
            "chapters": meta.get("chapters", []),
            "pipeline": meta.get("pipeline", {}),
        }
    # ensure known slugs
    for slug in ("pm-book-sujie", "inspired-cagan"):
        try:
            root = book_root(slug)
            meta_path = root / "insight" / "book-meta.json"
            if meta_path.is_file() and slug not in found:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                found[slug] = {
                    "slug": slug,
                    "title": meta.get("title", slug),
                    "path": str(root),
                    "chapters": meta.get("chapters", []),
                    "pipeline": meta.get("pipeline", {}),
                }
        except KeyError:
            pass
    return sorted(
        found.values(),
        key=lambda b: (
            not b.get("pipeline", {}).get("deep_done"),
            b.get("title", ""),
        ),
    )
