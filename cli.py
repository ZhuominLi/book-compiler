#!/usr/bin/env python3
"""Book Compiler CLI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from book_compiler.llm import load_env_file  # noqa: E402

load_env_file(ROOT / ".env")

from book_compiler.compile_skill import compile_skill  # noqa: E402
from book_compiler.concept_index import build_concept_index  # noqa: E402
from book_compiler.migrate import migrate_pm_book  # noqa: E402
from book_compiler.init_book import init_book  # noqa: E402
from book_compiler.paths import book_root, resolve_book_root  # noqa: E402
from book_compiler.hitl import approve_chapter, hitl_status, reset_chapter  # noqa: E402
from book_compiler.pipeline import (  # noqa: E402
    run_deep_all,
    run_deep_chapter,
    run_preview,
    run_synthesis,
)
from book_compiler.split_chapters import split_inspired  # noqa: E402

BOOKS = ["pm-book-sujie", "inspired-cagan"]


def cmd_init(args: argparse.Namespace) -> None:
    src = Path(args.txt).expanduser().resolve() if args.txt else None
    root = init_book(
        title=args.title,
        slug=args.slug,
        source_txt=src,
        book_type=args.type,
    )
    import json
    from book_compiler.paths import meta_path

    meta = json.loads(meta_path(root).read_text(encoding="utf-8"))
    print(f"Initialized → {root}")
    print(f"  slug: {meta['slug']}")
    print("Next: split chapters → preview → deep → read in UI (Q&A auto-saves) → synthesis → compile")


def cmd_migrate(_: argparse.Namespace) -> None:
    root = migrate_pm_book()
    build_concept_index(root)
    compile_skill(root, install=False)
    print(f"Migrated → {root / 'insight'}")


def cmd_split(_: argparse.Namespace) -> None:
    root = split_inspired()
    n = len(list((root / "_extract").glob("ch*.txt")))
    print(f"Split 启示录 → {root / '_extract'} ({n} chapters)")


def _root(slug: str) -> Path:
    return resolve_book_root(slug)


def cmd_preview(args: argparse.Namespace) -> None:
    run_preview(_root(args.book))


def cmd_deep(args: argparse.Namespace) -> None:
    root = _root(args.book)
    hitl = args.hitl and not args.batch
    if args.all:
        run_deep_all(root, force=args.force, hitl=hitl)
    else:
        run_deep_chapter(
            root,
            args.chapter,
            force=args.force,
            hitl=hitl,
        )


def cmd_approve(args: argparse.Namespace) -> None:
    approve_chapter(_root(args.book), args.chapter)


def cmd_reset(args: argparse.Namespace) -> None:
    reset_chapter(_root(args.book), args.chapter)


def cmd_status(args: argparse.Namespace) -> None:
    hitl_status(_root(args.book))


def cmd_synthesis(args: argparse.Namespace) -> None:
    run_synthesis(_root(args.book))


def cmd_index(args: argparse.Namespace) -> None:
    p = build_concept_index(_root(args.book))
    print(f"Concept index → {p}")


def cmd_compile(args: argparse.Namespace) -> None:
    compile_skill(_root(args.book), install=args.install)


def cmd_all_pm(_: argparse.Namespace) -> None:
    root = migrate_pm_book()
    build_concept_index(root)
    compile_skill(root, install=True)
    print("Done: pm-book-sujie migrated, indexed, skill compiled & installed.")


def cmd_all_inspired(args: argparse.Namespace) -> None:
    root = split_inspired()
    run_preview(root)
    run_deep_chapter(root, "ch01")
    if args.deep_all:
        run_deep_all(root)
        run_synthesis(root)
    build_concept_index(root)
    compile_skill(root, install=args.install)
    # golden sample
    ch01_path = _root("inspired-cagan")
    from book_compiler.paths import chapter_path as cp

    ch01 = cp(ch01_path, "ch01")
    golden = ROOT / "golden" / "inspired-ch01.md"
    if ch01 and ch01.is_file():
        golden.write_text(ch01.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Golden sample → {golden}")
    print("Done: inspired-cagan pipeline.")


def main() -> None:
    p = argparse.ArgumentParser(description="Book Compiler — Insight + Skill")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("migrate", help="Migrate 人人都是产品经理 → summary/ + insight/").set_defaults(func=cmd_migrate)
    sub.add_parser("split-inspired", help="Split 启示录 txt").set_defaults(func=cmd_split)
    sub.add_parser("all-pm", help="Migrate + index + compile + install pm").set_defaults(func=cmd_all_pm)

    sp = sub.add_parser("init", help="Scaffold a new book NOTE directory")
    sp.add_argument("--title", required=True, help='Book title, e.g. "精益创业"')
    sp.add_argument("--slug", default=None, help="URL slug (auto from title if omitted)")
    sp.add_argument("--txt", default=None, help="Path to source OCR txt (copied into NOTE dir)")
    sp.add_argument("--type", default="M", choices=["M", "N"], help="Book template type")
    sp.set_defaults(func=cmd_init)

    ai = sub.add_parser("all-inspired", help="Split + preview + deep ch01 + compile")
    ai.add_argument("--deep-all", action="store_true")
    ai.add_argument("--install", action="store_true", default=True)
    ai.set_defaults(func=cmd_all_inspired)

    def add_book(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--book", default="pm-book-sujie", choices=BOOKS)

    sp = sub.add_parser("preview", help="Generate overview.md")
    add_book(sp)
    sp.set_defaults(func=cmd_preview)

    sp = sub.add_parser("deep", help="Deep one or all chapters")
    add_book(sp)
    sp.add_argument("--chapter", default=None)
    sp.add_argument("--all", action="store_true")
    sp.add_argument("--force", action="store_true", help="Regenerate even if approved")
    sp.add_argument("--batch", action="store_true", help="No HITL pause; mark approved immediately")
    sp.add_argument("--hitl", action="store_true", default=True, help="Single-chapter: draft + wait for approve (default)")
    sp.set_defaults(func=cmd_deep)

    for name, fn in [("approve", cmd_approve), ("reset", cmd_reset), ("status", cmd_status)]:
        sp = sub.add_parser(name, help=f"Chapter {name}")
        add_book(sp)
        if name != "status":
            sp.add_argument("--chapter", required=True)
        sp.set_defaults(func=fn)

    sp = sub.add_parser("synthesis", help="Generate synthesis.md")
    add_book(sp)
    sp.set_defaults(func=cmd_synthesis)

    sp = sub.add_parser("index", help="Rebuild concept-index.json")
    add_book(sp)
    sp.set_defaults(func=cmd_index)

    sp = sub.add_parser("compile", help="Compile insight → skill/")
    add_book(sp)
    sp.add_argument("--install", action="store_true")
    sp.set_defaults(func=cmd_compile)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
