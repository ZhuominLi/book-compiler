"""PageIndex-style tree index — no embeddings, reasoning retrieval."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .llm import complete

NODE_SEARCH_SYSTEM = """你是文档树检索助手。根据用户问题，从文档树骨架中推理出可能包含答案的节点。

规则：
1. 只返回 JSON，格式：{"thinking":"简短推理","node_list":["node_id",...]}
2. node_list 至少 1 个、最多 8 个
3. 优先选最相关的小节节点（如 ch01-s02），跨章问题可选多个章节
4. 全书概览类问题选 overview；融会贯通/跨章主线选 synthesis（若存在）
5. 只选树中存在的 node_id，不要编造"""


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


def _split_sections(body: str) -> list[tuple[str, str]]:
    parts = re.split(r"\n(?=### )", body)
    sections: list[tuple[str, str]] = []
    for part in parts:
        part = part.strip()
        if not part.startswith("### "):
            continue
        first_line, _, rest = part.partition("\n")
        title = first_line[4:].strip()
        sections.append((title, rest.strip()))
    return sections


def _chapter_summary(body: str) -> str:
    m = re.search(r"### 一句话概括\s*\n+(.+)", body)
    if m:
        return m.group(1).strip()[:160]
    m = re.search(r"## 二、.*总结.*\n+(.+)", body, re.DOTALL)
    if m:
        return _first_summary(m.group(1))
    return _first_summary(body[:800])


def build_page_index(root: Path, meta: dict) -> dict:
    insight = root / "insight"
    slug = meta.get("slug", root.name)
    nodes: list[dict] = []

    def add(node_id: str, title: str, summary: str, parent: str | None, file: str, section: str | None = None):
        nodes.append({
            "node_id": node_id,
            "title": title,
            "summary": summary,
            "parent": parent,
            "file": file,
            "section": section,
        })

    ov_path = insight / "overview.md"
    if ov_path.is_file():
        body = _strip_frontmatter(ov_path.read_text(encoding="utf-8"))
        add("overview", "全书概览", _first_summary(body, 200), None, "overview.md")

    syn_path = insight / "synthesis.md"
    if syn_path.is_file() and syn_path.stat().st_size > 100:
        body = _strip_frontmatter(syn_path.read_text(encoding="utf-8"))
        add("synthesis", "融会贯通", _first_summary(body, 200), None, "synthesis.md")

    chapters_dir = insight / "chapters"
    for ch in meta.get("chapters", []):
        ch_id = ch["id"]
        ch_file = f"chapters/{ch_id}.md"
        fp = chapters_dir / f"{ch_id}.md"
        if not fp.is_file() or fp.stat().st_size < 50:
            continue
        body = _strip_frontmatter(fp.read_text(encoding="utf-8"))
        ch_title = ch.get("title") or ch_id
        add(ch_id, ch_title, _chapter_summary(body), None, ch_file)

        for i, (sec_title, sec_body) in enumerate(_split_sections(body), 1):
            sid = f"{ch_id}-s{i:02d}"
            add(sid, sec_title, _first_summary(sec_body), ch_id, ch_file, sec_title)

    concepts_dir = insight / "concepts"
    if concepts_dir.is_dir():
        for fp in sorted(concepts_dir.glob("*.md")):
            if fp.stat().st_size < 20:
                continue
            name = fp.stem
            body = _strip_frontmatter(fp.read_text(encoding="utf-8"))
            add(f"concept-{name}", f"概念：{name}", _first_summary(body, 120), None, f"concepts/{fp.name}")

    index = {
        "schema_version": "0.1",
        "book_slug": slug,
        "node_count": len(nodes),
        "nodes": nodes,
    }
    out = insight / "page-index.json"
    out.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return index


def load_or_build_page_index(root: Path) -> dict:
    meta_path = root / "insight" / "book-meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    idx_path = root / "insight" / "page-index.json"
    if idx_path.is_file():
        idx = json.loads(idx_path.read_text(encoding="utf-8"))
        if idx.get("node_count", 0) > 0:
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
        return _fallback_nodes(index, current_file)
    try:
        data = json.loads(m.group())
        ids = data.get("node_list") or []
        valid = {n["node_id"] for n in index["nodes"]}
        picked = [i for i in ids if i in valid]
        return picked or _fallback_nodes(index, current_file)
    except json.JSONDecodeError:
        return _fallback_nodes(index, current_file)


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


def _extract_section_body(full: str, section_title: str | None) -> str:
    if not section_title:
        return full
    parts = re.split(r"\n(?=### )", full)
    for part in parts:
        if part.strip().startswith("### ") and section_title in part[:120]:
            return part.strip()
    return full


def extract_node_content(root: Path, node: dict, clip: int = 6000) -> str:
    insight = root / "insight"
    fp = insight / node["file"]
    if not fp.is_file():
        return ""
    body = _strip_frontmatter(fp.read_text(encoding="utf-8"))
    if node.get("section"):
        body = _extract_section_body(body, node["section"])
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
