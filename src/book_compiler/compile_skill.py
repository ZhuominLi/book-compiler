"""Compile insight/ → skill/ and optionally install to ~/.cursor/skills/."""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_meta(book_root: Path) -> dict:
    p = book_root / "insight" / "book-meta.json"
    return json.loads(p.read_text(encoding="utf-8"))


def _compress_synthesis(text: str, max_lines: int = 120) -> str:
    lines = text.splitlines()
    # skip frontmatter
    if lines and lines[0].strip() == "---":
        for i, ln in enumerate(lines[1:], 1):
            if ln.strip() == "---":
                lines = lines[i + 1 :]
                break
    body = [ln for ln in lines if ln.strip() and not ln.startswith("*报告生成")]
    return "\n".join(body[:max_lines])


def _pick_qa_examples(qa_text: str, limit: int = 5) -> str:
    if not qa_text.strip():
        return "# Examples\n\n（暂无 Q&A，深度阅读后补充。）\n"
    blocks = re.split(r"\n(?=Q[:：]|### Q)", qa_text)
    picked = [b.strip() for b in blocks if b.strip()][:limit]
    return "# 示例问答\n\n" + "\n\n---\n\n".join(picked)


def _build_reference(meta: dict, index: dict, synthesis: str) -> str:
    title = meta.get("title", "Book")
    lines = [f"# {title} · Reference\n"]
    concepts = index.get("concepts", {})
    if concepts:
        lines.append("## 概念索引\n\n| 概念 | 章节 | 参考 |\n|------|------|------|")
        for name, c in sorted(concepts.items()):
            ch = c.get("chapter") or "—"
            refs = ", ".join(c.get("insight_refs") or [])[:60]
            lines.append(f"| {name} | {ch} | {refs} |")
        lines.append("")
    lines.append("## 全书压缩\n")
    lines.append(_compress_synthesis(synthesis, 80))
    return "\n".join(lines) + "\n"


def compile_skill(book_root: Path, install: bool = False) -> Path:
    meta = _read_meta(book_root)
    slug = meta["skill"]["slug"]
    insight = book_root / "insight"
    skill = book_root / "skill"
    skill.mkdir(parents=True, exist_ok=True)

    synthesis_path = insight / "synthesis.md"
    overview_path = insight / "overview.md"
    qa_path = insight / "qa.md"
    index_path = insight / "concept-index.json"

    synthesis = ""
    if synthesis_path.exists():
        synthesis = synthesis_path.read_text(encoding="utf-8")
    elif overview_path.exists():
        synthesis = overview_path.read_text(encoding="utf-8")

    index = {"concepts": {}}
    if index_path.exists():
        index = json.loads(index_path.read_text(encoding="utf-8"))

    triggers = meta["skill"].get("triggers", [])
    title = meta.get("title", slug)
    desc = f"{title}知识库。{'、'.join(triggers[:6])}。触发：{'、'.join(triggers)}"

    core = _compress_synthesis(synthesis, 100)
    skill_md = f"""---
name: {slug}
description: >-
  {desc}
---

# {title}

基于本书 Insight 编译。答案须 grounded 于 insight/。

## 何时调用

- 讨论与「{title}」相关的概念、方法、案例
- 用户触发词：{', '.join(triggers[:8])}

## 路由

| 意图 | 查阅 |
|------|------|
| 全书脉络 | `insight/synthesis.md` 或 `reference.md` |
| 单概念 | `insight/concept-index.json` → chapters/ 或 concepts/ |
| 用户历史问答 | `insight/qa.md` |

## 核心框架（压缩）

{core}

## 行为边界

- 仅基于本书 insight 回答；无依据时说「书中未明确涉及」
- 优先引用 concept-index 中的章节与 insight_refs

## 附加资源

- [reference.md](reference.md)
- [examples.md](examples.md)
- Insight 根目录：`{book_root / 'insight'}`
"""
    (skill / "SKILL.md").write_text(skill_md, encoding="utf-8")
    (skill / "reference.md").write_text(_build_reference(meta, index, synthesis), encoding="utf-8")

    qa = qa_path.read_text(encoding="utf-8") if qa_path.exists() else ""
    (skill / "examples.md").write_text(_pick_qa_examples(qa), encoding="utf-8")

    manifest = {
        "schema_version": "0.1",
        "book_slug": slug,
        "skill_name": slug,
        "compiled_from": {
            "synthesis": str(synthesis_path.relative_to(book_root))
            if synthesis_path.exists()
            else None,
            "concept_index": str(index_path.relative_to(book_root))
            if index_path.exists()
            else None,
            "qa": str(qa_path.relative_to(book_root)) if qa_path.exists() else None,
            "compiled_at": _now(),
        },
        "insight_root": "../insight",
        "install_to": meta["skill"].get("install_paths", []),
    }
    (skill / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    meta["pipeline"]["skill_compiled_at"] = _now()
    meta["updated_at"] = _now()
    (insight / "book-meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    if install:
        dest = Path.home() / ".cursor" / "skills" / slug
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(skill, dest)
        print(f"Installed skill → {dest}")

    return skill
