"""Build concept-index.json from summary/concepts/*.json and chapter files."""

from __future__ import annotations

import json
from pathlib import Path

from .paths import insight_dir, meta_path, summary_dir
import re

from .summary_parse import load_chapter_concepts, parse_chapter_summary


def slugify(name: str) -> str:
    s = re.sub(r"\s+", "-", name.strip())
    s = re.sub(r"[^\w\u4e00-\u9fff-]", "", s)
    return s.lower() or "concept"


def build_concept_index(book_root: Path) -> Path:
    insight = insight_dir(book_root)
    summ = summary_dir(book_root)
    mp = meta_path(book_root)
    slug = "unknown"
    if mp.exists():
        slug = json.loads(mp.read_text(encoding="utf-8")).get("slug", slug)

    concepts: dict[str, dict] = {}

    def upsert(name: str, chapter: str | None, ref: str, anchor: str = "") -> None:
        if not name or len(name) < 2:
            return
        if name in concepts:
            if ref not in concepts[name]["insight_refs"]:
                concepts[name]["insight_refs"].append(ref)
            if not concepts[name]["chapter"]:
                concepts[name]["chapter"] = chapter
            if anchor and anchor not in concepts[name]["anchors"]:
                concepts[name]["anchors"].append(anchor)
        else:
            concepts[name] = {
                "id": slugify(name),
                "aliases": [name],
                "type": "framework",
                "chapter": chapter,
                "anchors": [anchor] if anchor else [],
                "insight_refs": [ref],
                "related": [],
            }

    # from insight/concepts/*.md filenames
    concepts_dir = insight / "concepts"
    if concepts_dir.is_dir():
        for f in concepts_dir.glob("*.md"):
            if f.stat().st_size == 0:
                continue
            name = f.stem
            upsert(name, None, f"insight/concepts/{f.name}")

    # primary: summary/concepts/*.json (written by page index build)
    json_dir = summ / "concepts"
    if json_dir.is_dir():
        for f in sorted(json_dir.glob("ch*.json")):
            parsed = load_chapter_concepts(book_root, f.stem)
            if not parsed:
                continue
            ref = f"summary/concepts/{f.name}"
            for c in parsed.concepts:
                upsert(c.name, parsed.chapter_id, ref, c.anchor)

    # fallback: parse chapter markdown directly
    for chapters_dir, prefix in (
        (summ / "chapters", "summary/chapters"),
        (insight / "chapters", "insight/chapters"),
    ):
        if not chapters_dir.is_dir():
            continue
        for f in sorted(chapters_dir.glob("ch*.md")):
            if f.stat().st_size == 0:
                continue
            ch_id = f.stem
            if json_dir.is_dir() and (json_dir / f"{ch_id}.json").is_file():
                continue
            parsed = parse_chapter_summary(
                f.read_text(encoding="utf-8"), ch_id, source_file=f"{prefix}/{f.name}"
            )
            ref = f"{prefix}/{f.name}"
            for c in parsed.concepts:
                upsert(c.name, ch_id, ref, c.anchor)

    index = {
        "schema_version": "0.2",
        "book_slug": slug,
        "concepts": concepts,
    }
    out = insight / "concept-index.json"
    out.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out
