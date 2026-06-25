from __future__ import annotations

from pathlib import Path

BOOK_COMPILER_ROOT = Path(__file__).resolve().parents[2]
READINGS_PM = BOOK_COMPILER_ROOT.parent  # Readings/产品经理


def book_root(slug: str) -> Path:
    mapping = {
        "pm-book-sujie": READINGS_PM / "人人都是产品经理NOTE",
        "inspired-cagan": READINGS_PM / "启示录NOTE",
    }
    if slug not in mapping:
        raise KeyError(f"Unknown book slug: {slug}. Known: {list(mapping)}")
    return mapping[slug]


def insight_dir(root: Path) -> Path:
    return root / "insight"


def skill_dir(root: Path) -> Path:
    return root / "skill"


def state_dir(root: Path) -> Path:
    return root / "_state"
