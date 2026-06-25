"""Human-in-the-loop: draft → review → approve → next chapter."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_meta(root: Path) -> dict:
    return json.loads((root / "insight" / "book-meta.json").read_text(encoding="utf-8"))


def _save_meta(root: Path, meta: dict) -> None:
    meta["updated_at"] = _now()
    (root / "insight" / "book-meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def approve_chapter(root: Path, chapter_id: str) -> None:
    """Mark chapter approved after human review/edit."""
    meta = _load_meta(root)
    ch = next((c for c in meta["chapters"] if c["id"] == chapter_id), None)
    if not ch:
        raise ValueError(f"Unknown chapter: {chapter_id}")
    ch_path = root / "insight" / "chapters" / f"{chapter_id}.md"
    if not ch_path.exists():
        raise FileNotFoundError(f"No draft at {ch_path} — run deep first")
    ch["status"] = "approved"
    finished = sum(1 for c in meta["chapters"] if c["status"] == "approved")
    meta["pipeline"]["deep_done"] = finished == len(meta["chapters"])
    meta["pipeline"]["deep_current_chapter"] = chapter_id
    _save_meta(root, meta)
    print(f"Approved {chapter_id} ({finished}/{len(meta['chapters'])}). Edit file: {ch_path}")


def reset_chapter(root: Path, chapter_id: str) -> None:
    """Reset chapter to pending for regeneration."""
    meta = _load_meta(root)
    ch = next((c for c in meta["chapters"] if c["id"] == chapter_id), None)
    if not ch:
        raise ValueError(f"Unknown chapter: {chapter_id}")
    ch["status"] = "pending"
    meta["pipeline"]["deep_done"] = False
    _save_meta(root, meta)
    print(f"Reset {chapter_id} → pending")


def hitl_status(root: Path) -> None:
    meta = _load_meta(root)
    print(f"\n{'章':<6} {'状态':<10} 标题")
    print("-" * 50)
    for c in meta["chapters"]:
        print(f"{c['id']:<6} {c.get('status','?'):<10} {c.get('title','')[:30]}")
    pending = [c["id"] for c in meta["chapters"] if c["status"] == "pending"]
    draft = [c["id"] for c in meta["chapters"] if c["status"] == "draft"]
    print(f"\n待生成 pending: {len(pending)} | 待审核 draft: {draft} | 已通过 approved: {sum(1 for c in meta['chapters'] if c['status']=='approved')}")
