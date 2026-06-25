"""Discover book NOTE directories."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from .paths import (
    READINGS_PM,
    _registered_books,
    insight_dir,
    meta_path,
    normalize_slug,
    qa_path,
    resolve_book_root,
    summary_dir,
    synthesis_path,
    unregister_book,
)

BUILTIN_SLUGS = frozenset({"pm-book-sujie", "inspired-cagan"})


def book_stats(root: Path, meta: dict) -> dict:
    chapters = meta.get("chapters", [])
    pipeline = meta.get("pipeline", {})
    approved = sum(1 for c in chapters if c.get("status") == "approved")

    deep_files = 0
    for base in (summary_dir(root) / "chapters", insight_dir(root) / "chapters"):
        if base.is_dir():
            deep_files = max(
                deep_files,
                sum(1 for f in base.glob("ch*.md") if f.is_file() and f.stat().st_size > 50),
            )

    qa = qa_path(root)
    syn = synthesis_path(root)
    return {
        "chapters_total": len(chapters),
        "deep_approved": approved,
        "deep_files": deep_files,
        "split_done": len(chapters) > 0,
        "preview_done": bool(pipeline.get("preview_done")),
        "deep_done": bool(pipeline.get("deep_done")),
        "has_qa": qa.is_file() and qa.stat().st_size > 200,
        "has_synthesis": syn.is_file() and syn.stat().st_size > 100,
        "book_type": meta.get("book_type", "M"),
    }


def is_deletable(slug: str) -> bool:
    slug = normalize_slug(slug)
    return slug not in BUILTIN_SLUGS and slug in _registered_books()


def delete_book(slug: str) -> dict:
    """Delete an imported book: unregister + remove NOTE directory."""
    slug = normalize_slug(slug)
    if slug in BUILTIN_SLUGS:
        raise ValueError("内置书籍不可删除")
    if slug not in _registered_books():
        raise ValueError("仅支持删除通过 UI 导入的书籍")
    root = resolve_book_root(slug)
    title = slug
    mp = meta_path(root)
    if mp.is_file():
        title = json.loads(mp.read_text(encoding="utf-8")).get("title", slug)
    if root.is_dir():
        shutil.rmtree(root)
    unregister_book(slug)
    return {"slug": slug, "title": title, "deleted": True}


def book_item(root: Path) -> dict:
    meta = json.loads(meta_path(root).read_text(encoding="utf-8"))
    slug = meta.get("slug") or root.name.replace("NOTE", "").lower()
    return {
        "slug": slug,
        "title": meta.get("title", slug),
        "path": str(root),
        "chapters": meta.get("chapters", []),
        "pipeline": meta.get("pipeline", {}),
        "stats": book_stats(root, meta),
        "deletable": is_deletable(slug),
    }


def discover_books() -> list[dict]:
    found: dict[str, dict] = {}
    for note_dir in sorted(READINGS_PM.glob("*NOTE")):
        mp = note_dir / "insight" / "book-meta.json"
        if not mp.is_file():
            continue
        item = book_item(note_dir)
        found[item["slug"]] = item

    for slug in ("pm-book-sujie", "inspired-cagan"):
        try:
            root = resolve_book_root(slug)
            if slug not in found and meta_path(root).is_file():
                found[slug] = book_item(root)
        except KeyError:
            pass

    return sorted(
        found.values(),
        key=lambda b: (
            not b.get("stats", {}).get("deep_done"),
            b.get("title", ""),
        ),
    )
