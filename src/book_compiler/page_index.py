"""PageIndex-style tree index — no embeddings, reasoning retrieval."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .llm import complete
from .paths import insight_dir, meta_path, page_index_path, summary_dir
from .text_clean import normalize_text
from .summary_parse import (
    load_chapter_concepts,
    parse_chapter_summary,
    save_chapter_concepts,
)

NODE_SEARCH_SYSTEM = """你是文档树检索助手。根据用户问题，从文档树骨架中推理出可能包含答案的节点。

规则：
1. 只返回 JSON，格式：{"thinking":"简短推理","node_list":["node_id",...]}
2. node_list 至少 1 个、最多 8 个
3. 优先选最相关的小节节点（如 ch01-c02 概念节点），跨章问题可选多个章节
4. 若提示了「当前阅读文件」，**必须优先**从该章节点中选（如正在读 ch12 则优先 ch12 / ch12-c*）
5. 全书概览类问题选 overview；融会贯通/跨章主线选 synthesis（若存在）
6. 章节整体脉络选章节根节点；具体概念/论点选其子概念节点
7. 只选树中存在的 node_id，不要编造"""


def _strip_frontmatter(text: str) -> str:
    return re.sub(r"^---[\s\S]*?---\n", "", text)


def _first_summary(text: str, limit: int = 160) -> str:
    for pat in (
        r"\*\*核心观点\*\*[：:]\s*(.+)",
        r"\*\*定义\*\*[：:]\s*(.+)",
        r"\*\*一句话\*\*[：:]\s*(.+)",
        r"^>\s*(.+)",
    ):
        m = re.search(pat, text, re.MULTILINE)
        if m:
            s = m.group(1).strip()
            return s[:limit] + ("…" if len(s) > limit else "")
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith(("#", "|", "-", "*", ">")):
            return line[:limit] + ("…" if len(line) > limit else "")
    return ""


def _short(text: str, limit: int = 160) -> str:
    t = re.sub(r"\s+", " ", text.strip())
    return t[:limit] + ("…" if len(t) > limit else "")


def build_page_index(root: Path, meta: dict) -> dict:
    slug = meta.get("slug", root.name)
    nodes: list[dict] = []

    def add(node: dict) -> None:
        nodes.append(node)

    summ = summary_dir(root)
    ins = insight_dir(root)

    for ov_base, ov_file in [(summ, "overview.md"), (ins, "overview.md")]:
        ov_path = ov_base / "overview.md"
        if ov_path.is_file():
            body = _strip_frontmatter(ov_path.read_text(encoding="utf-8"))
            add({
                "node_id": "overview",
                "title": "全书概览",
                "summary": _first_summary(body, 200),
                "parent": None,
                "file": f"summary/{ov_file}" if ov_base == summ else ov_file,
            })
            break

    syn_path = ins / "synthesis.md"
    if syn_path.is_file() and syn_path.stat().st_size > 100:
        body = _strip_frontmatter(syn_path.read_text(encoding="utf-8"))
        add({
            "node_id": "synthesis",
            "title": "Insight 融会贯通",
            "summary": _first_summary(body, 200),
            "parent": None,
            "file": "insight/synthesis.md",
        })

    chapters_dir = summ / "chapters"
    if not chapters_dir.is_dir() or not any(chapters_dir.glob("*.md")):
        chapters_dir = ins / "chapters"

    for ch in meta.get("chapters", []):
        ch_id = ch["id"]
        ch_file = (
            f"summary/chapters/{ch_id}.md"
            if (summ / "chapters" / f"{ch_id}.md").is_file()
            else f"chapters/{ch_id}.md"
        )
        fp = chapters_dir / f"{ch_id}.md"
        if not fp.is_file() or fp.stat().st_size < 50:
            continue

        raw = fp.read_text(encoding="utf-8")
        ch_title = ch.get("title") or ch_id
        parsed = parse_chapter_summary(raw, ch_id, ch_title, source_file=ch_file)
        save_chapter_concepts(root, parsed)

        syn_short = _short(parsed.synthesis, 200) if parsed.synthesis else _first_summary(_strip_frontmatter(raw), 160)
        add({
            "node_id": ch_id,
            "title": ch_title,
            "summary": syn_short,
            "parent": None,
            "file": ch_file,
            "synthesis": parsed.synthesis,
            "concepts_file": f"summary/concepts/{ch_id}.json",
        })

        for c in parsed.concepts:
            add({
                "node_id": f"{ch_id}-{c.id}",
                "title": c.name,
                "summary": _short(c.source_quote or c.name, 160),
                "parent": ch_id,
                "file": ch_file,
                "concept_id": c.id,
                "source_quote": c.source_quote,
                "anchor": c.anchor,
            })

    concepts_dir = ins / "concepts"
    if concepts_dir.is_dir():
        for fp in sorted(concepts_dir.glob("*.md")):
            if fp.stat().st_size < 20:
                continue
            name = fp.stem
            body = _strip_frontmatter(fp.read_text(encoding="utf-8"))
            add({
                "node_id": f"concept-{name}",
                "title": f"概念：{name}",
                "summary": _first_summary(body, 120),
                "parent": None,
                "file": f"insight/concepts/{fp.name}",
            })

    index = {
        "schema_version": "0.2",
        "book_slug": slug,
        "node_count": len(nodes),
        "nodes": nodes,
    }
    out = page_index_path(root)
    if out.parent.name != "summary":
        out = summ / "page-index.json"
    out.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return index


def _current_chapter_id(current_file: str | None) -> str | None:
    if not current_file:
        return None
    m = re.search(r"chapters/(ch\d+)", current_file)
    return m.group(1) if m else None


def resolve_chapter_id(chapter_id: str | None, current_file: str | None) -> str | None:
    return chapter_id or _current_chapter_id(current_file)


def load_chapter_extract(root: Path, meta: dict, chapter_id: str) -> str | None:
    """Full chapter plain text from _extract/chNN.txt."""
    ch = next((c for c in meta.get("chapters", []) if c.get("id") == chapter_id), None)
    if not ch:
        return None
    rel = ch.get("source") or f"_extract/{chapter_id}.txt"
    fp = root / rel
    if not fp.is_file():
        fp = root / "_extract" / f"{chapter_id}.txt"
    if not fp.is_file():
        return None
    return normalize_text(fp.read_bytes().decode("utf-8", errors="replace"))


def format_extract_with_line_numbers(text: str) -> str:
    return "\n".join(f"L{i}\t{line}" for i, line in enumerate(text.splitlines(), start=1))


def build_chapter_only_context(root: Path, meta: dict, chapter_id: str) -> str | None:
    """Current chapter _extract only — not the whole book."""
    extract = load_chapter_extract(root, meta, chapter_id)
    if not extract:
        return None
    ch = next((c for c in meta.get("chapters", []) if c.get("id") == chapter_id), {})
    ch_title = ch.get("title") or chapter_id
    book_title = meta.get("title", "")
    body = format_extract_with_line_numbers(extract)
    return (
        f"书名：{book_title}\n"
        f"当前章节：{chapter_id} · {ch_title}\n\n"
        f"--- 本章原文 ---\n{body}"
    )


def _cross_chapter_node_ids(node_ids: list[str], chapter_id: str) -> list[str]:
    """Prefer nodes outside current chapter to avoid duplicating chapter material."""
    cross = [
        n for n in node_ids
        if n not in (chapter_id,) and not n.startswith(f"{chapter_id}-")
    ]
    return cross or node_ids


def build_chat_context(
    root: Path,
    meta: dict,
    question: str,
    current_file: str,
    chapter_id: str | None = None,
    use_page_index: bool = False,
) -> tuple[str, list[str]]:
    """Chapter reading → chapter _extract; optional PageIndex for cross-chapter."""
    cid = resolve_chapter_id(chapter_id, current_file)
    if cid:
        chapter_ctx = build_chapter_only_context(root, meta, cid)
        if chapter_ctx and not use_page_index:
            return chapter_ctx, [cid]
        if chapter_ctx and use_page_index:
            index = load_or_build_page_index(root)
            node_ids = search_nodes(question, index, current_file)
            cross_ids = _cross_chapter_node_ids(node_ids, cid)
            summary_ctx, hit = retrieve_context(root, index, cross_ids)
            hits = [cid] + [n for n in hit if n != cid]
            header = f"命中节点：{', '.join(hit) or '无'}"
            block = summary_ctx or "（未命中跨章节点）"
            merged = (
                f"{chapter_ctx}\n\n"
                f"--- 跨章 Summary 检索（PageIndex）---\n{header}\n\n{block}"
            )
            return merged, hits

    index = load_or_build_page_index(root)
    node_ids = search_nodes(question, index, current_file)
    context, hit = retrieve_context(root, index, node_ids)
    title = meta.get("title", root.name)
    header = f"书名：{title}\n命中节点：{', '.join(hit)}"
    return f"{header}\n\n--- 检索到的 Summary 材料 ---\n{context}", hit


def _index_needs_rebuild(root: Path, idx: dict, meta: dict) -> bool:
    if idx.get("schema_version", "0.1") < "0.2":
        return True
    summ = summary_dir(root)
    chapters_dir = summ / "chapters"
    concepts_dir = summ / "concepts"
    if not chapters_dir.is_dir():
        chapters_dir = insight_dir(root) / "chapters"

    indexed_chapters = {
        n["node_id"] for n in idx.get("nodes", []) if re.fullmatch(r"ch\d+", n.get("node_id", ""))
    }
    for md in sorted(chapters_dir.glob("ch*.md")):
        if md.stat().st_size < 50:
            continue
        ch_id = md.stem
        if ch_id not in indexed_chapters:
            return True
        cj = concepts_dir / f"{ch_id}.json"
        if not cj.is_file():
            return True
        if md.stat().st_mtime > cj.stat().st_mtime + 1:
            return True
    return False


def _prefer_current_chapter(
    node_ids: list[str], index: dict, current_file: str | None
) -> list[str]:
    """When user is reading a chapter, prioritize that chapter's nodes."""
    cid = _current_chapter_id(current_file)
    if not cid:
        return node_ids
    in_ch = [n for n in node_ids if n == cid or n.startswith(f"{cid}-")]
    out_ch = [n for n in node_ids if n not in in_ch]
    if in_ch:
        return (in_ch + out_ch)[:8]
    kids = [n["node_id"] for n in index["nodes"] if n.get("parent") == cid]
    return (kids[:3] + node_ids)[:8] if kids else node_ids


def load_or_build_page_index(root: Path) -> dict:
    meta = json.loads(meta_path(root).read_text(encoding="utf-8"))
    for idx_path in (summary_dir(root) / "page-index.json", insight_dir(root) / "page-index.json"):
        if idx_path.is_file():
            idx = json.loads(idx_path.read_text(encoding="utf-8"))
            if idx.get("node_count", 0) > 0 and not _index_needs_rebuild(root, idx, meta):
                return idx
    return build_page_index(root, meta)


def tree_skeleton(index: dict) -> str:
    by_parent: dict[str | None, list] = {}
    for n in index["nodes"]:
        by_parent.setdefault(n.get("parent"), []).append(n)

    lines: list[str] = []

    def walk(parent: str | None, depth: int = 0):
        for n in by_parent.get(parent, []):
            indent = "  " * depth
            lines.append(f"{indent}[{n['node_id']}] {n['title']} | {n.get('summary', '')}")
            walk(n["node_id"], depth + 1)

    walk(None)
    return "\n".join(lines)


def search_nodes(question: str, index: dict, current_file: str | None = None) -> list[str]:
    skeleton = tree_skeleton(index)
    hint = f"\n当前阅读文件：{current_file}" if current_file else ""
    prompt = f"问题：{question}{hint}\n\n文档树：\n{skeleton}\n\n请返回 JSON。"
    raw = complete(NODE_SEARCH_SYSTEM, prompt)
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return _prefer_current_chapter(_fallback_nodes(index, current_file), index, current_file)
    try:
        data = json.loads(m.group())
        ids = data.get("node_list") or []
        valid = {n["node_id"] for n in index["nodes"]}
        picked = [i for i in ids if i in valid]
        picked = picked or _fallback_nodes(index, current_file)
        return _prefer_current_chapter(picked, index, current_file)
    except json.JSONDecodeError:
        return _prefer_current_chapter(_fallback_nodes(index, current_file), index, current_file)


def _fallback_nodes(index: dict, current_file: str | None) -> list[str]:
    if current_file and current_file != "overview.md":
        ch = re.search(r"chapters/(ch\d+)", current_file)
        if ch:
            cid = ch.group(1)
            kids = [n["node_id"] for n in index["nodes"] if n.get("parent") == cid]
            return kids[:3] or [cid]
    ids = [n["node_id"] for n in index["nodes"] if n["node_id"] in ("overview", "synthesis")]
    if not ids:
        ids = [index["nodes"][0]["node_id"]] if index["nodes"] else []
    return ids


def extract_node_content(root: Path, node: dict, clip: int = 6000) -> str:
    if node.get("concept_id"):
        quote = node.get("source_quote", "")
        anchor = node.get("anchor", "")
        lines = [f"### [{node['node_id']}] {node['title']}"]
        if quote:
            lines.append(f"**原文表述**：{quote}")
        if anchor:
            lines.append(f"**锚点**：{anchor}")
        text = "\n".join(lines)
        if len(text) > clip:
            text = text[:clip] + "\n…（已截断）"
        return text

    if node.get("synthesis") and not node.get("parent"):
        header = f"### [{node['node_id']}] {node['title']}\n\n"
        text = header + node["synthesis"]
        if len(text) > clip:
            text = text[:clip] + "\n…（已截断）"
        return text

    rel = node["file"]
    if rel.startswith("summary/"):
        fp = root / rel
    elif rel.startswith("insight/"):
        fp = root / rel
    else:
        fp = summary_dir(root) / rel
        if not fp.is_file():
            fp = insight_dir(root) / rel
    if not fp.is_file():
        return ""
    body = _strip_frontmatter(fp.read_text(encoding="utf-8"))
    header = f"### [{node['node_id']}] {node['title']}\n"
    text = header + body
    if len(text) > clip:
        text = text[:clip] + "\n…（已截断）"
    return text


def retrieve_context(root: Path, index: dict, node_ids: list[str]) -> tuple[str, list[str]]:
    by_id = {n["node_id"]: n for n in index["nodes"]}
    parts: list[str] = []
    hit: list[str] = []
    budget = 18000
    used = 0
    for nid in node_ids:
        node = by_id.get(nid)
        if not node:
            continue
        chunk = extract_node_content(root, node, clip=6000)
        if not chunk:
            continue
        if used + len(chunk) > budget:
            chunk = chunk[: max(0, budget - used)]
        parts.append(chunk)
        hit.append(nid)
        used += len(chunk)
        if used >= budget:
            break
    return "\n\n---\n\n".join(parts), hit
