"""Migrate legacy 概览/ layout to insight/ per SPEC."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .paths import BOOK_COMPILER_ROOT, book_root, insight_dir, meta_path, summary_dir, state_dir


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def migrate_pm_book() -> Path:
    root = book_root("pm-book-sujie")
    legacy = root / "概览"
    summ = summary_dir(root)
    insight = insight_dir(root)
    chapters = summ / "chapters"
    concepts = insight / "concepts"
    for d in (summ, chapters, insight, concepts, state_dir(root), root / "skill"):
        d.mkdir(parents=True, exist_ok=True)

    # overview ← 全文深度总结 → summary/
    src_overview = legacy / "全文深度总结.md"
    if src_overview.exists() and src_overview.stat().st_size > 0:
        dst = summ / "overview.md"
        body = src_overview.read_text(encoding="utf-8")
        dst.write_text(
            f"---\nschema_version: \"0.1\"\nbook_slug: pm-book-sujie\n"
            f"kind: overview\nmigrated_at: {_now()}\n---\n\n{body}",
            encoding="utf-8",
        )

    # synthesis ← legacy 融会贯通（历史数据；新书应在 Q&A 后生成）
    src_syn = legacy / "全书融会贯通报告.md"
    if src_syn.exists() and src_syn.stat().st_size > 0:
        body = src_syn.read_text(encoding="utf-8")
        (insight / "synthesis.md").write_text(
            f"---\nschema_version: \"0.1\"\nbook_slug: pm-book-sujie\n"
            f"kind: insight-synthesis\nmigrated_at: {_now()}\nlegacy: true\n---\n\n{body}",
            encoding="utf-8",
        )

    # Q&A：不迁移旧 Q&A.md — 阅读时由 chatbot 自动写入 insight/qa.md

    # concepts ← 方法论抽取
    legacy_concepts = legacy / "方法论抽取"
    if legacy_concepts.is_dir():
        for f in legacy_concepts.glob("*.md"):
            if f.stat().st_size > 0:
                shutil.copy2(f, concepts / f.name)

    # chapters: map 第N章 / 第一章 etc.
    chapter_map = {
        "第一章.md": "ch01.md",
        "第二章.md": "ch02.md",
        "第三章.md": "ch03.md",
        "第4章.md": "ch04.md",
        "第5章.md": "ch05.md",
        "第6章.md": "ch06.md",
        "第7章.md": "ch07.md",
        "第8章.md": "ch08.md",
        "第9章.md": "ch09.md",
        "第10章.md": "ch10.md",
        "第11章.md": "ch11.md",
    }
    for src_name, dst_name in chapter_map.items():
        src = legacy / src_name
        if src.exists() and src.stat().st_size > 0:
            body = src.read_text(encoding="utf-8")
            (chapters / dst_name).write_text(
                f"---\nschema_version: \"0.1\"\nbook_slug: pm-book-sujie\n"
                f"chapter_id: {dst_name.replace('.md', '')}\ntemplate: M\n"
                f"kind: deep-summary\nmigrated_at: {_now()}\n---\n\n{body}",
                encoding="utf-8",
            )

    # book-meta.json
    examples = BOOK_COMPILER_ROOT / "examples" / "pm-book-meta.json"
    meta_path = insight / "book-meta.json"
    if examples.exists():
        meta = json.loads(examples.read_text(encoding="utf-8"))
        meta["updated_at"] = _now()
        # update chapter status from migrated files
        for ch in meta["chapters"]:
            ch_file = chapters / f"{ch['id']}.md"
            ch["status"] = "deep_done" if ch_file.exists() else "pending"
        meta["pipeline"]["preview_done"] = (insight / "overview.md").exists()
        meta["pipeline"]["deep_done"] = all(
            c["status"] == "deep_done" for c in meta["chapters"]
        )
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    # pipeline state
    pipeline = {
        "schema_version": "0.1",
        "book_slug": "pm-book-sujie",
        "mode": "migrated",
        "updated_at": _now(),
        "preview": {"done": (insight / "overview.md").exists()},
        "deep": {
            "done": False,
            "total": 11,
            "finished": sum(1 for f in chapters.glob("ch*.md")),
        },
        "skill": {"compiled": False},
    }
    (state_dir(root) / "pipeline.json").write_text(
        json.dumps(pipeline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    return root
