"""Preview / Deep pipeline steps."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .concept_index import build_concept_index
from .llm import complete, has_llm
from .prompts import SYSTEM_M, SYSTEM_N, SYSTEM_OVERVIEW, SYSTEM_SYNTHESIS


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_meta(root: Path) -> dict:
    return json.loads((root / "insight" / "book-meta.json").read_text(encoding="utf-8"))


def _save_meta(root: Path, meta: dict) -> None:
    meta["updated_at"] = _now()
    (root / "insight" / "book-meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _chapter_source(root: Path, ch: dict) -> str:
    p = root / ch["source"]
    return p.read_text(encoding="utf-8") if p.exists() else ""


def run_preview(root: Path) -> None:
    meta = _load_meta(root)
    insight = root / "insight"
    chapters = meta["chapters"]
    snippets = []
    for ch in chapters:
        src = _chapter_source(root, ch)
        snippets.append(f"### {ch['id']} {ch.get('title', '')}\n{src}\n")

    user = "全书章节完整原文：\n\n" + "\n".join(snippets)
    body = complete(SYSTEM_OVERVIEW, user)
    front = (
        f'---\nschema_version: "0.1"\nbook_slug: {meta["slug"]}\n'
        f'kind: overview\ngenerated_at: {_now()}\n'
        f'llm: {"deepseek" if has_llm() else "heuristic"}\n---\n\n'
    )
    (insight / "overview.md").write_text(front + body, encoding="utf-8")
    meta["pipeline"]["preview_done"] = True
    _save_meta(root, meta)
    build_concept_index(root)
    print(f"Preview → {insight / 'overview.md'}")


def run_deep_chapter(
    root: Path,
    chapter_id: str | None = None,
    *,
    force: bool = False,
    hitl: bool = True,
) -> str | None:
    """Generate chapter insight. Returns chapter_id written, or None if nothing to do."""
    meta = _load_meta(root)
    insight = root / "insight"
    chapters_dir = insight / "chapters"
    chapters_dir.mkdir(parents=True, exist_ok=True)

    if chapter_id:
        pending = [c for c in meta["chapters"] if c["id"] == chapter_id]
        if not force and pending and pending[0].get("status") == "approved":
            print(f"{chapter_id} already approved. Use --force to regenerate.")
            return None
        if force and pending:
            pending[0]["status"] = "pending"
    else:
        pending = [
            c
            for c in meta["chapters"]
            if c.get("status") in ("pending", None)
            or (force and c.get("status") != "approved")
        ]

    if not pending:
        print("No pending chapters.")
        return None

    ch = pending[0]
    template = ch.get("template") or meta.get("book_type", "M")
    if template == "H":
        template = ch.get("template", "M")
    system = SYSTEM_N if template == "N" else SYSTEM_M
    src = _chapter_source(root, ch)
    title = ch.get("title", ch["id"])
    user = (
        f"书名：{meta['title']}\n章节：{ch['id']} {title}\n模板：{template}\n\n"
        f"---SOURCE---\n{src}"
    )
    body = complete(system, user)
    status = "draft" if hitl else "approved"
    front = (
        f'---\nschema_version: "0.1"\nbook_slug: {meta["slug"]}\n'
        f'chapter_id: {ch["id"]}\nchapter_title: "{title}"\n'
        f'template: "{template}"\nsource: {ch["source"]}\n'
        f'generated_at: {_now()}\nstatus: {status}\n---\n\n'
        f"# {title} · 深度 Insight\n\n"
    )
    out = chapters_dir / f"{ch['id']}.md"
    out.write_text(front + body, encoding="utf-8")
    ch["status"] = status
    meta["pipeline"]["deep_current_chapter"] = ch["id"]
    finished = sum(1 for c in meta["chapters"] if c.get("status") == "approved")
    meta["pipeline"]["deep_done"] = finished == len(meta["chapters"])
    _save_meta(root, meta)
    build_concept_index(root)
    lines = body.count("\n") + 1
    print(f"Deep {ch['id']} → {out} ({lines} lines, status={status})")
    if hitl and status == "draft":
        print(f"  ⏸ HITL: 请审阅编辑后执行: ./run.sh approve --book {meta['slug']} --chapter {ch['id']}")
    return ch["id"]


def run_deep_all(root: Path, *, force: bool = False, hitl: bool = False) -> None:
    """Batch deep. Default hitl=False for --all; use hitl=True for one-at-a-time with gates."""
    meta = _load_meta(root)
    for ch in meta["chapters"]:
        if ch.get("status") == "approved" and not force:
            continue
        cid = run_deep_chapter(root, ch["id"], force=force, hitl=hitl)
        if hitl and cid:
            print("Stopped after one chapter (HITL mode). Approve then run deep again.")
            return


def run_synthesis(root: Path) -> None:
    meta = _load_meta(root)
    insight = root / "insight"
    parts = []
    for ch in meta["chapters"]:
        p = insight / "chapters" / f"{ch['id']}.md"
        if p.exists() and p.stat().st_size > 0:
            parts.append(p.read_text(encoding="utf-8"))
    qa = ""
    qa_path = insight / "qa.md"
    if qa_path.exists():
        qa = qa_path.read_text(encoding="utf-8")
    user = f"书名：{meta['title']}\n\n各章深度笔记：\n" + "\n---\n".join(parts) + f"\n\n用户Q&A：\n{qa}"
    body = complete(SYSTEM_SYNTHESIS, user)
    front = (
        f'---\nschema_version: "0.1"\nbook_slug: {meta["slug"]}\n'
        f'kind: synthesis\ngenerated_at: {_now()}\n---\n\n'
        f"# {meta['title']} · 深度 Insight（融会贯通）\n\n"
    )
    (insight / "synthesis.md").write_text(front + body, encoding="utf-8")
    print(f"Synthesis → {insight / 'synthesis.md'}")
