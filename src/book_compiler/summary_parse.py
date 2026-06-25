"""Parse chapter Summary → concept list + synthesis (for PageIndex / concept-index)."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

_FRONTMATTER = re.compile(r"^---[\s\S]*?---\n")


@dataclass
class ChapterConcept:
    id: str
    name: str
    source_quote: str
    anchor: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ChapterSummaryParsed:
    chapter_id: str
    title: str
    concepts: list[ChapterConcept] = field(default_factory=list)
    synthesis: str = ""
    source_file: str = ""

    def to_dict(self) -> dict:
        return {
            "schema_version": "0.2",
            "chapter_id": self.chapter_id,
            "title": self.title,
            "source_file": self.source_file,
            "concepts": [c.to_dict() for c in self.concepts],
            "synthesis": self.synthesis,
        }


def strip_frontmatter(text: str) -> str:
    return _FRONTMATTER.sub("", text).strip()


def _section(body: str, *headings: str) -> str:
    """Extract markdown body under first matching ## heading."""
    for h in headings:
        pat = re.compile(
            rf"(?ms)^##\s*{re.escape(h)}\s*$.*?(?=^##\s|\Z)",
        )
        # Also match headings with prefix like ## 一、概念清单
        pat2 = re.compile(
            rf"(?ms)^##\s*[^\n]*{re.escape(h)}[^\n]*\s*$.*?(?=^##\s|\Z)",
        )
        for p in (pat, pat2):
            m = p.search(body)
            if m:
                block = m.group(0)
                block = re.sub(r"^##[^\n]*\n", "", block, count=1)
                return block.strip()
    return ""


def _parse_table_rows(section: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("|") or re.match(r"^\|[\s:|-]+\|$", line):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells and not all(c.replace("-", "").strip() == "" for c in cells):
            rows.append(cells)
    return rows


def _parse_concept_table(section: str) -> list[ChapterConcept]:
    rows = _parse_table_rows(section)
    if len(rows) < 2:
        return []
    header = [c.replace("*", "").strip() for c in rows[0]]
    name_idx = next((i for i, h in enumerate(header) if "概念" in h or "论点" in h or "术语" in h), 0)
    plain_idx = next((i for i, h in enumerate(header) if "用人话" in h), None)
    quote_idx = next(
        (
            i
            for i, h in enumerate(header)
            if any(k in h for k in ("书里", "原文", "表述", "定义", "案例", "含义", "论据"))
        ),
        None,
    )
    if quote_idx is None:
        quote_idx = 1 if len(header) > 1 and plain_idx != 1 else (2 if len(header) > 2 else 1)
    anchor_idx = next((i for i, h in enumerate(header) if "锚点" in h), len(header) - 1)

    out: list[ChapterConcept] = []
    for i, row in enumerate(rows[1:], start=1):
        if len(row) <= name_idx:
            continue
        name = row[name_idx].replace("**", "").strip()
        if not name or name in ("#", "术语", "概念"):
            continue
        parts: list[str] = []
        if plain_idx is not None and plain_idx < len(row):
            plain = row[plain_idx].replace("**", "").strip()
            if plain:
                parts.append(plain)
        if quote_idx < len(row):
            quote = row[quote_idx].replace("**", "").strip()
            if quote and (not parts or quote not in parts[0]):
                parts.append(quote)
        quote = "\n\n".join(parts)
        anchor = row[anchor_idx].replace("**", "").strip() if anchor_idx < len(row) else ""
        out.append(ChapterConcept(id=f"c{i:02d}", name=name, source_quote=quote, anchor=anchor))
    return out


def _parse_legacy_topics(body: str) -> list[ChapterConcept]:
    """N-template legacy: ### 论点/主题N blocks."""
    out: list[ChapterConcept] = []
    parts = re.split(r"\n(?=### )", body)
    idx = 0
    for part in parts:
        part = part.strip()
        m = re.match(r"^###\s*(?:论点/主题\d+[：:]?|概念\d+[：:]?)\s*(.+)$", part, re.MULTILINE)
        if not m:
            continue
        idx += 1
        name = m.group(1).strip().strip("*")
        quote = ""
        qm = re.search(r"\*\*书中怎么说\*\*[：:]\s*\n+((?:>\s*.+\n?)+)", part)
        if qm:
            quote = re.sub(r"^>\s?", "", qm.group(1), flags=re.MULTILINE).strip()
        elif (cm := re.search(r"\*\*核心观点\*\*[：:]\s*\n+(.+)", part)):
            quote = cm.group(1).strip()
        anchor = ""
        am = re.search(r"\*\*锚点\*\*[：:]\s*(.+)", part)
        if am:
            anchor = am.group(1).strip()
        out.append(ChapterConcept(id=f"c{idx:02d}", name=name, source_quote=quote, anchor=anchor))
    return out


def _parse_synthesis(body: str) -> str:
    for key in ("概念串联", "本章串联", "逻辑链", "一句话总结", "第.*章总结"):
        sec = _section(body, key)
        if not sec:
            continue
        if "概念串联" in key or "本章串联" in key:
            return sec
        return sec
    sec = _section(body, "三、本章逻辑链与一句话总结", "二、第")
    return sec


def parse_chapter_summary(
    text: str,
    chapter_id: str,
    title: str = "",
    *,
    source_file: str = "",
) -> ChapterSummaryParsed:
    body = strip_frontmatter(text)
    concepts: list[ChapterConcept] = []

    list_sec = _section(body, "概念清单", "一、概念清单", "一、本章概念清单")
    if list_sec:
        concepts = _parse_concept_table(list_sec)

    if not concepts:
        concepts = _parse_legacy_topics(body)

    if not concepts:
        term_sec = _section(body, "术语表", "二、术语表")
        if term_sec:
            concepts = _parse_concept_table(term_sec)

    synthesis = _parse_synthesis(body)
    if not synthesis:
        syn_sec = _section(body, "概念串联", "二、概念串联", "三、本章逻辑链")
        synthesis = syn_sec

    return ChapterSummaryParsed(
        chapter_id=chapter_id,
        title=title,
        concepts=concepts,
        synthesis=synthesis,
        source_file=source_file,
    )


def concepts_json_path(root: Path, chapter_id: str) -> Path:
    return root / "summary" / "concepts" / f"{chapter_id}.json"


def save_chapter_concepts(root: Path, parsed: ChapterSummaryParsed) -> Path | None:
    if not parsed.concepts and not parsed.synthesis:
        return None
    d = root / "summary" / "concepts"
    d.mkdir(parents=True, exist_ok=True)
    fp = d / f"{parsed.chapter_id}.json"
    fp.write_text(json.dumps(parsed.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return fp


def load_chapter_concepts(root: Path, chapter_id: str) -> ChapterSummaryParsed | None:
    fp = concepts_json_path(root, chapter_id)
    if not fp.is_file():
        return None
    data = json.loads(fp.read_text(encoding="utf-8"))
    concepts = [ChapterConcept(**c) for c in data.get("concepts", [])]
    return ChapterSummaryParsed(
        chapter_id=data.get("chapter_id", chapter_id),
        title=data.get("title", ""),
        concepts=concepts,
        synthesis=data.get("synthesis", ""),
        source_file=data.get("source_file", ""),
    )
