"""Discover book NOTE directories (user-imported only)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from .paths import (
    _registered_books,
    insight_dir,
    meta_path,
    qa_path,
    resolve_book_root,
    summary_dir,
    synthesis_path,
    unregister_book,
)


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
    }


def is_deletable(slug: str) -> bool:
    from .paths import normalize_slug

    slug = normalize_slug(slug)
    return slug in _registered_books()


def delete_book(slug: str) -> dict:
    """Delete an imported book: unregister + remove NOTE directory."""
    from .paths import normalize_slug

    slug = normalize_slug(slug)
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
        "id": slug,
        "tag": meta.get("tag") or "",
        "title": meta.get("title", slug),
        "path": str(root),
        "chapters": meta.get("chapters", []),
        "pipeline": meta.get("pipeline", {}),
        "stats": book_stats(root, meta),
        "deletable": is_deletable(slug),
    }


def discover_books() -> list[dict]:
    """List books registered via import (books.json only)."""
    items: list[dict] = []
    for slug, root in _registered_books().items():
        if not meta_path(root).is_file():
            continue
        try:
            items.append(book_item(root))
        except (OSError, json.JSONDecodeError, KeyError):
            continue
    return sorted(
        items,
        key=lambda b: (
            not b.get("stats", {}).get("deep_done"),
            b.get("title", ""),
        ),
    )
