"""Build concept-index.json from concepts/ and chapter files."""

from __future__ import annotations

import json
import re
from pathlib import Path

CONCEPT_HEADING = re.compile(
    r"^#{1,3}\s*概念\d*[：:]\s*(.+)$|^###\s*概念\d*[：:]\s*(.+)$",
    re.MULTILINE,
)
TABLE_CONCEPT = re.compile(r"^\|\s*\*\*(.+?)\*\*\s*\|", re.MULTILINE)


def slugify(name: str) -> str:
    s = re.sub(r"\s+", "-", name.strip())
    s = re.sub(r"[^\w\u4e00-\u9fff-]", "", s)
    return s.lower() or "concept"


def extract_concepts_from_md(text: str, chapter: str, source: str) -> dict:
    found: dict[str, dict] = {}
    for m in CONCEPT_HEADING.finditer(text):
        name = (m.group(1) or m.group(2)).strip()
        if len(name) < 2 or len(name) > 40:
            continue
        found.setdefault(
            name,
            {
                "id": slugify(name),
                "aliases": [name],
                "type": "framework",
                "chapter": chapter,
                "anchors": [],
                "insight_refs": [],
                "related": [],
            },
        )
    return found


def build_concept_index(book_root: Path) -> Path:
    insight = book_root / "insight"
    meta_path = insight / "book-meta.json"
    slug = "unknown"
    if meta_path.exists():
        slug = json.loads(meta_path.read_text(encoding="utf-8")).get("slug", slug)

    concepts: dict[str, dict] = {}

    # from insight/concepts/*.md filenames
    concepts_dir = insight / "concepts"
    if concepts_dir.is_dir():
        for f in concepts_dir.glob("*.md"):
            if f.stat().st_size == 0:
                continue
            name = f.stem
            concepts[name] = {
                "id": slugify(name),
                "aliases": [name],
                "type": "framework",
                "chapter": None,
                "anchors": [],
                "insight_refs": [f"insight/concepts/{f.name}"],
                "related": [],
            }

    # from chapters
    chapters_dir = insight / "chapters"
    if chapters_dir.is_dir():
        for f in sorted(chapters_dir.glob("ch*.md")):
            if f.stat().st_size == 0:
                continue
            ch_id = f.stem
            text = f.read_text(encoding="utf-8")
            for name, entry in extract_concepts_from_md(text, ch_id, "").items():
                if name in concepts:
                    concepts[name]["insight_refs"].append(f"insight/chapters/{f.name}")
                    if not concepts[name]["chapter"]:
                        concepts[name]["chapter"] = ch_id
                else:
                    entry["insight_refs"] = [f"insight/chapters/{f.name}"]
                    concepts[name] = entry

    index = {
        "schema_version": "0.1",
        "book_slug": slug,
        "concepts": concepts,
    }
    out = insight / "concept-index.json"
    out.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out
