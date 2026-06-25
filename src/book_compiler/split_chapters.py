"""Split OCR/plain book txt into _extract/chNN.txt chapters."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .ingest.adapters.epub import extract_nav_chapters, match_nav_spine, nav_spine_entries
from .paths import READINGS_PM, meta_path, state_dir, summary_dir
from .split_judge import SplitProfile, find_chapters, resolve_split_profile


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def detect_split(text: str, *, use_llm: bool = True) -> dict:
    """Preview split detection for UI."""
    profile = resolve_split_profile(text, use_llm=use_llm)
    starts = find_chapters(text, profile)
    return {
        "profile": {
            "pattern_id": profile.pattern_id,
            "unit": profile.unit,
            "number_style": profile.number_style,
            "label": profile.label(),
            "body_start_line": profile.body_start_line + 1,
            "confidence": round(profile.confidence, 2),
            "sample_title": profile.sample_title,
        },
        "chapters_found": len(starts),
        "preview": [
            {"index": num, "line": line + 1, "title": title or f"第{num}{profile.unit}"}
            for line, num, title in starts[:8]
        ],
    }


def split_text(
    text: str,
    *,
    use_llm: bool = True,
) -> tuple[SplitProfile, list[tuple[int, int, str]]]:
    profile = resolve_split_profile(text, use_llm=use_llm)
    starts = find_chapters(text, profile)
    if len(starts) < 1:
        raise RuntimeError(f"未找到有效的「第X{profile.unit}」章节")
    return profile, starts


def _write_split_state(book_root_path: Path, meta: dict, *, chapters: int, profile: dict) -> None:
    sd = state_dir(book_root_path)
    sd.mkdir(parents=True, exist_ok=True)
    (sd / "pipeline.json").write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "book_slug": meta.get("slug"),
                "mode": "split",
                "updated_at": _now(),
                "split": {"chapters": chapters, **profile},
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _split_book_epub_nav(
    book_root_path: Path,
    meta: dict,
    epub_path: Path,
    extract: Path,
    template: str,
) -> int:
    chapters_data = extract_nav_chapters(epub_path.read_bytes())
    if not chapters_data:
        raise RuntimeError("EPUB 目录分章未得到有效章节")

    chapters_meta = []
    for idx, ch in enumerate(chapters_data, start=1):
        cid = f"ch{idx:02d}" if idx < 100 else f"ch{idx}"
        chunk = ch["text"]
        (extract / f"{cid}.txt").write_text(chunk, encoding="utf-8")
        chapters_meta.append(
            {
                "id": cid,
                "index": idx,
                "title": ch["title"],
                "template": template,
                "source": f"_extract/{cid}.txt",
                "summary_file": f"summary/chapters/{cid}.md",
                "status": "pending",
                "line_start": 0,
                "char_count": len(chunk),
                "epub_href": ch["href"],
                "epub_spine_index": ch["spine_index"],
            }
        )

    meta["chapters"] = chapters_meta
    meta["updated_at"] = _now()
    meta["split_profile"] = {
        "pattern_id": "epub_nav",
        "unit": "节",
        "number_style": "arabic",
        "body_start_line": 0,
    }
    meta_path(book_root_path).write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_split_state(
        book_root_path,
        meta,
        chapters=len(chapters_meta),
        profile={"pattern_id": "epub_nav", "unit": "节", "body_start_line": 0},
    )
    return len(chapters_meta)


def _enrich_epub_spine(chapters_meta: list[dict], epub_path: Path) -> None:
    try:
        entries = nav_spine_entries(epub_path.read_bytes())
    except Exception:
        return
    for ch in chapters_meta:
        hit = match_nav_spine(entries, ch.get("title", ""))
        if hit:
            ch["epub_href"] = hit["href"]
            ch["epub_spine_index"] = hit["spine_index"]


def split_book(book_root_path: Path, source: Path | None = None, *, use_llm: bool = True) -> int:
    """Split source txt into _extract/ and update book-meta.json chapters."""
    mp = meta_path(book_root_path)
    if not mp.is_file():
        raise FileNotFoundError(f"缺少 book-meta.json: {mp}")
    meta = json.loads(mp.read_text(encoding="utf-8"))

    if source is None:
        sf = meta.get("source_file")
        if not sf:
            raise ValueError("book-meta.json 缺少 source_file")
        source = book_root_path / sf
    if not source.is_file():
        raise FileNotFoundError(f"源文件不存在: {source}")

    template = meta.get("book_type", "M")
    if template not in ("M", "N"):
        template = "M"

    extract = book_root_path / "_extract"
    if extract.exists():
        shutil.rmtree(extract)
    extract.mkdir(parents=True, exist_ok=True)
    (summary_dir(book_root_path) / "chapters").mkdir(parents=True, exist_ok=True)

    ingest = meta.get("ingest") or {}
    epub_name = ingest.get("epub_file")
    if ingest.get("source_format") == "epub" and epub_name:
        epub_path = book_root_path / epub_name
        if epub_path.is_file():
            try:
                return _split_book_epub_nav(book_root_path, meta, epub_path, extract, template)
            except Exception:
                pass

    text = source.read_text(encoding="utf-8")
    try:
        profile, starts = split_text(text, use_llm=use_llm)
    except RuntimeError:
        if ingest.get("source_format") == "epub" and epub_name:
            epub_path = book_root_path / epub_name
            if epub_path.is_file():
                return _split_book_epub_nav(book_root_path, meta, epub_path, extract, template)
        raise

    lines = text.splitlines(keepends=True)
    chapters_meta = []
    unit = profile.unit

    for idx, (line_start, num, title) in enumerate(starts):
        line_end = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        chunk = "".join(lines[line_start:line_end])
        cid = f"ch{num:02d}" if num < 100 else f"ch{num}"
        (extract / f"{cid}.txt").write_text(chunk, encoding="utf-8")
        chapters_meta.append(
            {
                "id": cid,
                "index": num,
                "title": title or f"第{num}{unit}",
                "template": template,
                "source": f"_extract/{cid}.txt",
                "summary_file": f"summary/chapters/{cid}.md",
                "status": "pending",
                "line_start": line_start,
                "char_count": len(chunk),
            }
        )

    ingest = meta.get("ingest") or {}
    epub_name = ingest.get("epub_file")
    if ingest.get("source_format") == "epub" and epub_name:
        epub_path = book_root_path / epub_name
        if epub_path.is_file():
            _enrich_epub_spine(chapters_meta, epub_path)

    meta["chapters"] = chapters_meta
    meta["updated_at"] = _now()
    meta["split_profile"] = {
        "pattern_id": profile.pattern_id,
        "unit": unit,
        "number_style": profile.number_style,
        "body_start_line": profile.body_start_line,
    }
    if source.parent == book_root_path:
        meta["source_file"] = source.name
    mp.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    _write_split_state(
        book_root_path,
        meta,
        chapters=len(chapters_meta),
        profile={
            "body_start_line": profile.body_start_line,
            "pattern_id": profile.pattern_id,
            "unit": unit,
        },
    )
    return len(chapters_meta)


def split_inspired(
    source: Path | None = None,
    book_root_path: Path | None = None,
) -> Path:
    source = source or (
        READINGS_PM / "2. 启示录-打造用户喜爱的产品[美] Marty Cagan著.txt"
    )
    root = book_root_path or (READINGS_PM / "启示录NOTE")
    split_book(root, source)
    return root
