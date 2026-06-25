"""Split OCR/plain book txt into _extract/chNN.txt chapters."""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .paths import READINGS_PM

CHAPTER_HEADING = re.compile(r"^第\s*(\d{1,2})\s*章\s*$", re.MULTILINE)
PART_MARKER = re.compile(r"^第[一二三四]部分", re.MULTILINE)
MIN_CHAPTER_CHARS = 800


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _body_start_line(text: str) -> int:
    """Skip front matter + TOC; start at first 第X部分 after TOC (~line 300)."""
    lines = text.splitlines()
    part_lines = [i for i, ln in enumerate(lines) if PART_MARKER.match(ln.strip())]
    for pl in part_lines:
        if pl > 300:
            return pl
    return part_lines[0] if part_lines else 0


def find_chapter_starts(text: str, min_line: int = 0) -> list[tuple[int, int, str]]:
    lines = text.splitlines()
    # chapter_num -> (line, title) keep latest occurrence after min_line with enough content
    candidates: dict[int, tuple[int, str]] = {}

    for i, line in enumerate(lines):
        if i < min_line:
            continue
        m = CHAPTER_HEADING.match(line.strip())
        if not m:
            continue
        num = int(m.group(1))
        title = ""
        for j in range(i + 1, min(i + 6, len(lines))):
            t = lines[j].strip()
            if (
                t
                and not t.startswith("---")
                and len(t) < 100
                and not CHAPTER_HEADING.match(t)
                and not PART_MARKER.match(t)
            ):
                title = t
                break
        candidates[num] = (i, title)

    return [(candidates[n][0], n, candidates[n][1]) for n in sorted(candidates)]


def _valid_starts(text: str, starts: list[tuple[int, int, str]]) -> list[tuple[int, int, str]]:
    """Drop chapters whose slice would be too short (TOC noise)."""
    lines = text.splitlines(keepends=True)
    valid = []
    for idx, (line_start, num, title) in enumerate(starts):
        line_end = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        if len("".join(lines[line_start:line_end])) >= MIN_CHAPTER_CHARS:
            valid.append((line_start, num, title))
    return valid


def split_inspired(
    source: Path | None = None,
    book_root_path: Path | None = None,
) -> Path:
    source = source or (
        READINGS_PM / "2. 启示录-打造用户喜爱的产品[美] Marty Cagan著.txt"
    )
    root = book_root_path or (READINGS_PM / "启示录NOTE")
    extract = root / "_extract"
    if extract.exists():
        shutil.rmtree(extract)
    extract.mkdir(parents=True, exist_ok=True)
    (root / "insight" / "chapters").mkdir(parents=True, exist_ok=True)
    (root / "_state").mkdir(parents=True, exist_ok=True)
    (root / "skill").mkdir(parents=True, exist_ok=True)

    text = source.read_text(encoding="utf-8")
    min_line = _body_start_line(text)
    starts = find_chapter_starts(text, min_line=min_line)
    starts = _valid_starts(text, starts)
    if not starts:
        raise RuntimeError("No valid chapter headings found after body start")

    lines = text.splitlines(keepends=True)
    chapters_meta = []

    for idx, (line_start, num, title) in enumerate(starts):
        line_end = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        chunk = "".join(lines[line_start:line_end])
        cid = f"ch{num:02d}"
        out = extract / f"{cid}.txt"
        out.write_text(chunk, encoding="utf-8")
        chapters_meta.append(
            {
                "id": cid,
                "index": num,
                "title": title or f"第{num}章",
                "template": "N",
                "source": f"_extract/{cid}.txt",
                "insight_file": f"insight/chapters/{cid}.md",
                "status": "pending",
                "line_start": line_start,
                "char_count": len(chunk),
            }
        )

    meta = {
        "schema_version": "0.1",
        "title": "启示录：打造用户喜爱的产品",
        "title_en": "Inspired",
        "authors": ["Marty Cagan"],
        "slug": "inspired-cagan",
        "source_file": str(source.name),
        "language": "zh",
        "book_type": "N",
        "book_type_reason": "以产品实践论点、团队角色、案例论证为主",
        "book_type_overrides": {},
        "created_at": _now(),
        "updated_at": _now(),
        "pipeline": {
            "preview_done": False,
            "deep_done": False,
            "deep_current_chapter": None,
            "skill_compiled_at": None,
        },
        "chapters": chapters_meta,
        "skill": {
            "slug": "inspired-cagan",
            "triggers": [
                "启示录",
                "Inspired",
                "Marty Cagan",
                "产品发现",
                "产品团队",
                "产品愿景",
            ],
            "install_paths": ["~/.cursor/skills/inspired-cagan"],
        },
    }
    insight = root / "insight"
    insight.mkdir(parents=True, exist_ok=True)
    (insight / "book-meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (root / "_state" / "pipeline.json").write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "book_slug": "inspired-cagan",
                "mode": "split",
                "updated_at": _now(),
                "split": {"chapters": len(chapters_meta), "body_start_line": min_line},
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return root
