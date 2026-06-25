"""Book NOTE path helpers — summary vs insight layers."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import unquote

BOOK_COMPILER_ROOT = Path(__file__).resolve().parents[2]
READINGS_PM = BOOK_COMPILER_ROOT.parent  # Readings/产品经理


def normalize_slug(slug: str) -> str:
    """Decode URL-encoded slug (%E9%87%91... → 金瓶梅)."""
    s = unquote(slug)
    while "%" in s:
        nxt = unquote(s)
        if nxt == s:
            break
        s = nxt
    return s


def book_root(slug: str) -> Path:
    mapping = {
        "pm-book-sujie": READINGS_PM / "人人都是产品经理NOTE",
        "inspired-cagan": READINGS_PM / "启示录NOTE",
    }
    if slug not in mapping:
        raise KeyError(f"Unknown book slug: {slug}. Known: {list(mapping)}")
    return mapping[slug]


def books_registry_path() -> Path:
    return BOOK_COMPILER_ROOT / "_state" / "books.json"


def register_book(slug: str, note_dir: Path) -> None:
    """Runtime register (used by init). Persists in _state/books.json."""
    import json

    state = books_registry_path()
    state.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(state.read_text(encoding="utf-8")) if state.is_file() else {}
    data[slug] = str(note_dir)
    state.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def unregister_book(slug: str) -> bool:
    """Remove slug from books.json. Returns True if it was registered."""
    import json

    state = books_registry_path()
    if not state.is_file():
        return False
    data = json.loads(state.read_text(encoding="utf-8"))
    if slug not in data:
        return False
    del data[slug]
    state.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def _registered_books() -> dict[str, Path]:
    import json

    state = books_registry_path()
    if not state.is_file():
        return {}
    return {k: Path(v) for k, v in json.loads(state.read_text(encoding="utf-8")).items()}


def resolve_book_root(slug: str) -> Path:
    slug = normalize_slug(slug)
    try:
        return book_root(slug)
    except KeyError:
        pass
    reg = _registered_books()
    if slug in reg:
        return reg[slug]
    for note_dir in sorted(READINGS_PM.glob("*NOTE")):
        mp = note_dir / "insight" / "book-meta.json"
        if not mp.is_file():
            continue
        meta = json.loads(mp.read_text(encoding="utf-8"))
        if meta.get("slug") == slug:
            return note_dir
    raise KeyError(f"Unknown book slug: {slug}")


def meta_dir(root: Path) -> Path:
    d = root / "insight"
    d.mkdir(parents=True, exist_ok=True)
    return d


def meta_path(root: Path) -> Path:
    return meta_dir(root) / "book-meta.json"


def summary_dir(root: Path) -> Path:
    """Preview + Deep Summary（pipeline 产出，Q&A 之前）。"""
    d = root / "summary"
    d.mkdir(parents=True, exist_ok=True)
    return d


def insight_dir(root: Path) -> Path:
    """Insight（Q&A 之后：qa、synthesis 等）。"""
    d = root / "insight"
    d.mkdir(parents=True, exist_ok=True)
    return d


def skill_dir(root: Path) -> Path:
    return root / "skill"


def state_dir(root: Path) -> Path:
    return root / "_state"


def _first_existing(*paths: Path) -> Path | None:
    for p in paths:
        if p.is_file() and p.stat().st_size > 0:
            return p
    return None


def overview_path(root: Path) -> Path:
    hit = _first_existing(summary_dir(root) / "overview.md", insight_dir(root) / "overview.md")
    return hit or (summary_dir(root) / "overview.md")


def chapter_path(root: Path, chapter_id: str) -> Path | None:
    return _first_existing(
        summary_dir(root) / "chapters" / f"{chapter_id}.md",
        insight_dir(root) / "chapters" / f"{chapter_id}.md",
    )


def chapter_write_path(root: Path, chapter_id: str) -> Path:
    d = summary_dir(root) / "chapters"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{chapter_id}.md"


def qa_path(root: Path) -> Path:
    return insight_dir(root) / "qa.md"


def synthesis_path(root: Path) -> Path:
    return insight_dir(root) / "synthesis.md"


def page_index_path(root: Path) -> Path:
    hit = _first_existing(summary_dir(root) / "page-index.json", insight_dir(root) / "page-index.json")
    return hit or (summary_dir(root) / "page-index.json")


def read_layer_file(root: Path, layer: str, rel: str) -> Path:
    """layer: summary | insight"""
    base = summary_dir(root) if layer == "summary" else insight_dir(root)
    fp = (base / rel).resolve()
    if not str(fp).startswith(str(base.resolve())):
        raise ValueError("forbidden")
    if layer == "summary" and not fp.is_file():
        # backward compat: old books kept chapters under insight/
        alt = (insight_dir(root) / rel).resolve()
        if str(alt).startswith(str(insight_dir(root).resolve())) and alt.is_file():
            return alt
    if not fp.is_file():
        raise FileNotFoundError(rel)
    return fp
