"""Preview / Deep Summary pipeline — output goes to summary/, not insight/."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .concept_index import build_concept_index
from .page_index import build_page_index
from .llm import complete, complete_stream, has_llm
from .paths import meta_path, qa_path, summary_dir, synthesis_path, chapter_write_path, chapter_path
from .deep_prompt import resolve_deep_system_prompt
from .prompts import PROMPT_REVISION, SYSTEM_OVERVIEW, SYSTEM_SYNTHESIS


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_meta(root: Path) -> dict:
    return json.loads(meta_path(root).read_text(encoding="utf-8"))


def _save_meta(root: Path, meta: dict) -> None:
    meta["updated_at"] = _now()
    meta_path(root).write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _chapter_source(root: Path, ch: dict) -> str:
    p = root / ch["source"]
    return p.read_text(encoding="utf-8") if p.exists() else ""


def run_preview(root: Path) -> None:
    meta = _load_meta(root)
    summ = summary_dir(root)
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
    (summ / "overview.md").write_text(front + body, encoding="utf-8")
    meta["pipeline"]["preview_done"] = True
    _save_meta(root, meta)
    build_concept_index(root)
    build_page_index(root, meta)
    print(f"Preview → {summ / 'overview.md'}")


def prepare_deep_chapter(
    root: Path,
    chapter_id: str | None = None,
    *,
    force: bool = False,
) -> tuple[dict, dict, str, str, str, str] | None:
    """Return (meta, ch, system, user, front, template) or None if skipped."""
    meta = _load_meta(root)
    summary_dir(root)

    if chapter_id:
        pending = [c for c in meta["chapters"] if c["id"] == chapter_id]
        if not pending:
            raise ValueError(f"章节不存在: {chapter_id}")
        ch = pending[0]
        if not force and ch.get("status") == "approved":
            return None
        if force:
            ch["status"] = "pending"
    else:
        pending = [
            c
            for c in meta["chapters"]
            if c.get("status") in ("pending", None)
            or (force and c.get("status") != "approved")
        ]
        if not pending:
            return None
        ch = pending[0]

    template = ch.get("template") or meta.get("book_type", "M")
    if template == "H":
        template = ch.get("template", "M")
    system = resolve_deep_system_prompt(root, template)
    src = _chapter_source(root, ch)
    title = ch.get("title", ch["id"])
    user = (
        f"书名：{meta['title']}\n章节：{ch['id']} {title}\n模板：{template}\n\n"
        f"---SOURCE---\n{src}"
    )
    front = (
        f'---\nschema_version: "0.1"\nbook_slug: {meta["slug"]}\n'
        f'chapter_id: {ch["id"]}\nchapter_title: "{title}"\n'
        f'template: "{template}"\nsource: {ch["source"]}\n'
        f'kind: deep-summary\ngenerated_at: {_now()}\n'
        f'prompt_revision: "{PROMPT_REVISION}"\nstatus: {{status}}\n---\n\n'
        f"# {title} · 深度 Summary\n\n"
    )
    return meta, ch, system, user, front, template


def finalize_deep_chapter(
    root: Path,
    meta: dict,
    ch: dict,
    front: str,
    body: str,
    *,
    hitl: bool = True,
) -> dict:
    status = "draft" if hitl else "approved"
    out = chapter_write_path(root, ch["id"])
    out.write_text(front.format(status=status) + body, encoding="utf-8")
    ch["summary_file"] = f"summary/chapters/{ch['id']}.md"
    ch["status"] = status
    meta["pipeline"]["deep_current_chapter"] = ch["id"]
    finished = sum(1 for c in meta["chapters"] if c.get("status") == "approved")
    meta["pipeline"]["deep_done"] = finished == len(meta["chapters"])
    _save_meta(root, meta)
    build_concept_index(root)
    build_page_index(root, meta)
    lines = body.count("\n") + 1
    rel = str(out.relative_to(root))
    print(f"Deep Summary {ch['id']} → {out} ({lines} lines, status={status})")
    if hitl and status == "draft":
        print(f"  ⏸ HITL: 审阅后 ./run.sh approve --book {meta['slug']} --chapter {ch['id']}")
    return {
        "chapter_id": ch["id"],
        "path": rel,
        "lines": lines,
        "status": status,
    }


def iter_deep_chapter_stream(
    root: Path,
    chapter_id: str,
    *,
    force: bool = False,
    hitl: bool = False,
) -> Iterator[tuple[str, dict]]:
    """Yield SSE-style (event_name, payload) tuples."""
    prep = prepare_deep_chapter(root, chapter_id, force=force)
    if prep is None:
        yield ("error", {"error": "本章已生成且未指定 force", "code": 409})
        return

    meta, ch, system, user, front, template = prep
    title = ch.get("title", ch["id"])
    yield (
        "meta",
        {
            "chapter_id": ch["id"],
            "title": title,
            "template": template,
        },
    )

    parts: list[str] = []
    for delta in complete_stream(system, user):
        parts.append(delta)
        yield ("delta", {"text": delta})

    body = "".join(parts)
    result = finalize_deep_chapter(root, meta, ch, front, body, hitl=hitl)
    yield ("done", result)


def run_deep_chapter(
    root: Path,
    chapter_id: str | None = None,
    *,
    force: bool = False,
    hitl: bool = True,
) -> str | None:
    """Generate chapter deep summary. Returns chapter_id written, or None."""
    prep = prepare_deep_chapter(root, chapter_id, force=force)
    if prep is None:
        if chapter_id:
            print(f"{chapter_id} already approved. Use --force to regenerate.")
        else:
            print("No pending chapters.")
        return None

    meta, ch, system, user, front, _template = prep
    body = complete(system, user)
    finalize_deep_chapter(root, meta, ch, front, body, hitl=hitl)
    return ch["id"]


def run_deep_all(root: Path, *, force: bool = False, hitl: bool = False) -> None:
    meta = _load_meta(root)
    for ch in meta["chapters"]:
        if ch.get("status") == "approved" and not force:
            continue
        cid = run_deep_chapter(root, ch["id"], force=force, hitl=hitl)
        if hitl and cid:
            print("Stopped after one chapter (HITL mode). Approve then run deep again.")
            return


def run_synthesis(root: Path) -> None:
    """Generate insight/synthesis.md — requires user Q&A from reading UI."""
    meta = _load_meta(root)
    qa = qa_path(root)
    if not qa.is_file() or qa.stat().st_size < 80:
        print("⚠ insight/qa.md 为空：请先在 UI 阅读时用 chatbot 提问，Q&A 会自动写入。")
        print("  仍可使用各章 Summary 继续；完成 Q&A 后再运行 synthesis。")
        return

    parts = []
    for ch in meta["chapters"]:
        p = chapter_path(root, ch["id"])
        if p and p.stat().st_size > 0:
            parts.append(p.read_text(encoding="utf-8"))

    user = (
        f"书名：{meta['title']}\n\n各章深度 Summary：\n"
        + "\n---\n".join(parts)
        + f"\n\n用户 Q&A（阅读过程中产生）：\n{qa.read_text(encoding='utf-8')}"
    )
    body = complete(SYSTEM_SYNTHESIS, user)
    front = (
        f'---\nschema_version: "0.1"\nbook_slug: {meta["slug"]}\n'
        f'kind: insight-synthesis\ngenerated_at: {_now()}\n---\n\n'
        f"# {meta['title']} · Insight（融会贯通）\n\n"
    )
    synthesis_path(root).write_text(front + body, encoding="utf-8")
    meta["pipeline"]["insight_done"] = True
    _save_meta(root, meta)
    print(f"Insight → {synthesis_path(root)}")
