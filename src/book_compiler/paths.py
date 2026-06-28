"""Book NOTE path helpers — summary vs insight layers."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import unquote

BOOK_COMPILER_ROOT = Path(__file__).resolve().parents[2]
READINGS_PM = BOOK_COMPILER_ROOT.parent  # dev-only: legacy CLI paths


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def frozen_bundle_bases() -> list[Path]:
    """PyInstaller search paths (macOS .app Resources, Windows _internal, one-file _MEIPASS)."""
    if not _is_frozen():
        return []
    exe = Path(sys.executable).resolve()
    candidates: list[Path] = []
    if meipass := getattr(sys, "_MEIPASS", None):
        candidates.append(Path(meipass))
    if sys.platform == "darwin":
        candidates.append(exe.parent.parent / "Resources")
    internal = exe.parent / "_internal"
    if internal.is_dir():
        candidates.append(internal)
    candidates.append(exe.parent)
    seen: set[str] = set()
    bases: list[Path] = []
    for base in candidates:
        key = str(base)
        if key in seen:
            continue
        seen.add(key)
        bases.append(base)
    return bases


def frozen_bundle_root() -> Path | None:
    if not _is_frozen():
        return None
    for base in frozen_bundle_bases():
        if (base / "runtime-version.json").is_file() or (base / "ui" / "static" / "index.html").is_file():
            return base
    bases = frozen_bundle_bases()
    return bases[0] if bases else None


def app_data_dir() -> Path:
    """Registry & user settings (books.json, prompt presets)."""
    if p := os.environ.get("BEANREAD_DATA_DIR"):
        d = Path(p)
    elif _is_frozen():
        if sys.platform == "win32":
            d = Path.home() / "AppData" / "Local" / "BeanRead"
        elif sys.platform == "darwin":
            d = Path.home() / "Library/Application Support/BeanRead"
        else:
            d = Path.home() / ".local/share/BeanRead"
    else:
        d = BOOK_COMPILER_ROOT / "_state"
    d.mkdir(parents=True, exist_ok=True)
    return d


def library_dir() -> Path:
    """Imported book NOTE directories (user uploads only)."""
    if p := os.environ.get("BEANREAD_LIBRARY"):
        d = Path(p)
    elif _is_frozen():
        d = app_data_dir() / "books"
    else:
        d = BOOK_COMPILER_ROOT / "library"
    d.mkdir(parents=True, exist_ok=True)
    return d


def resolve_static_dir(server_file: Path) -> Path:
    """Locate ui/static — runtime overlay first, then bundle / dev tree."""
    from .runtime_update import runtime_static_dir

    rt_static = runtime_static_dir()
    if rt_static:
        return rt_static
    if getattr(sys, "frozen", False):
        for base in frozen_bundle_bases():
            if not base.is_dir():
                continue
            for rel in ("ui/static", "static"):
                cand = base / rel
                if (cand / "index.html").is_file():
                    return cand
    return server_file.resolve().parent / "static"


def resolve_element_dir(server_file: Path) -> Path:
    """Locate ui/element — bundle / dev tree."""
    if getattr(sys, "frozen", False):
        for base in frozen_bundle_bases():
            cand = base / "ui" / "element"
            if (cand / "manifest.json").is_file():
                return cand
    return server_file.resolve().parent / "element"


def bundle_resources_dir() -> Path | None:
    return frozen_bundle_root()


def normalize_slug(slug: str) -> str:
    """Decode URL-encoded slug (%E9%87%91... → 金瓶梅)."""
    s = unquote(slug)
    while "%" in s:
        nxt = unquote(s)
        if nxt == s:
            break
        s = nxt
    return s


def books_registry_path() -> Path:
    return app_data_dir() / "books.json"


def register_book(slug: str, note_dir: Path) -> None:
    """Persist imported book path in books.json."""
    state = books_registry_path()
    data = json.loads(state.read_text(encoding="utf-8")) if state.is_file() else {}
    data[slug] = str(note_dir)
    state.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def unregister_book(slug: str) -> bool:
    """Remove slug from books.json. Returns True if it was registered."""
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
    state = books_registry_path()
    if not state.is_file():
        return {}
    return {k: Path(v) for k, v in json.loads(state.read_text(encoding="utf-8")).items()}


def resolve_book_root(slug: str) -> Path:
    slug = normalize_slug(slug)
    reg = _registered_books()
    if slug in reg:
        root = reg[slug]
        if meta_path(root).is_file():
            return root
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
        alt = (insight_dir(root) / rel).resolve()
        if str(alt).startswith(str(insight_dir(root).resolve())) and alt.is_file():
            return alt
    if not fp.is_file():
        raise FileNotFoundError(rel)
    return fp
