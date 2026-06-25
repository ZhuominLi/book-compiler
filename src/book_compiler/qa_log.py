"""Append UI chatbot Q&A turns to insight/qa.md — never pre-generate."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .paths import qa_path


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def ensure_qa_file(root: Path, book_title: str, slug: str) -> Path:
    p = qa_path(root)
    if not p.is_file() or p.stat().st_size == 0:
        p.write_text(
            f"---\nschema_version: \"0.1\"\nbook_slug: {slug}\nkind: qa\n---\n\n"
            f"# Q&A · {book_title}\n\n"
            "> 由阅读 UI 对话自动追加。不在 pipeline 中预生成。\n\n",
            encoding="utf-8",
        )
    return p


def append_qa_turn(
    root: Path,
    *,
    slug: str,
    book_title: str,
    chapter_id: str | None,
    current_file: str,
    question: str,
    answer: str,
    nodes: list[str] | None = None,
) -> Path:
    p = ensure_qa_file(root, book_title, slug)
    tag = f"ui:{chapter_id}" if chapter_id else "ui:overview"
    ch_label = chapter_id or "overview"
    nodes_line = ", ".join(nodes) if nodes else "—"
    block = (
        f"\n## [{tag}] {_now()}\n\n"
        f"### Q：{question.strip()}\n\n"
        f"**章节**：{ch_label}  \n"
        f"**阅读位置**：{current_file}  \n"
        f"**答案**：\n\n{answer.strip()}\n\n"
        f"**溯源**：\n"
        f"- PageIndex 节点：{nodes_line}\n\n"
        f"---\n"
    )
    with p.open("a", encoding="utf-8") as f:
        f.write(block)
    return p
