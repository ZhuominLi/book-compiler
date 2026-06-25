"""Minimal local reader — stdlib HTTP server, no FastAPI."""

from __future__ import annotations

import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from book_compiler.books import discover_books  # noqa: E402
from book_compiler.llm import complete, has_llm, load_env_file  # noqa: E402
from book_compiler.page_index import (  # noqa: E402
    load_or_build_page_index,
    retrieve_context,
    search_nodes,
)
from book_compiler.paths import book_root  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
PORT = 8765

CHAT_SYSTEM = """你是 Book Compiler 阅读助手。基于用户提供的书籍 insight 材料回答问题。

规则：
1. 只基于提供的材料回答，材料中没有的内容明确说「书中/笔记中未涉及」
2. 尽量引用锚点（L行号）指向原文位置
3. 回答简洁、准确、有帮助，使用中文
4. 可以跨章节关联概念，但需说明出处
5. 不要编造案例、数据或引用"""


def _pageindex_retrieve(slug: str, question: str, current_file: str) -> tuple[str, list[str]]:
    """PageIndex stage-1 (tree search) + stage-2 (content extract)."""
    root = book_root(slug)
    meta = json.loads((root / "insight" / "book-meta.json").read_text(encoding="utf-8"))
    index = load_or_build_page_index(root)
    node_ids = search_nodes(question, index, current_file)
    context, hit = retrieve_context(root, index, node_ids)
    title = meta.get("title", slug)
    header = f"书名：{title}\n命中节点：{', '.join(hit)}"
    return f"{header}\n\n{context}", hit


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path.startswith("/api/"):
            return self._api(path, qs)
        return self._static(path)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/chat":
            return self._api_chat()
        return self._json({"error": "not found"}, 404)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def _json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _text(self, text: str, content_type="text/plain; charset=utf-8", status=200):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _api_chat(self):
        try:
            body = self._read_json_body()
            slug = body.get("slug")
            if not slug:
                return self._json({"error": "slug required"}, 400)

            messages = body.get("messages") or []
            if not messages or messages[-1].get("role") != "user":
                return self._json({"error": "last message must be user"}, 400)

            question = (messages[-1].get("content") or "").strip()
            current_file = body.get("current_file") or "overview.md"

            history = []
            for m in messages[-8:]:
                role = m.get("role")
                content = (m.get("content") or "").strip()
                if role in ("user", "assistant") and content:
                    history.append(f"{role.upper()}：{content}")

            if not has_llm():
                return self._json({
                    "reply": "（未配置 LLM_API_KEY，请在 book-compiler/.env 配置后重启 UI。）",
                    "nodes": [],
                })

            context, hit_nodes = _pageindex_retrieve(slug, question, current_file)
            user_prompt = (
                f"--- 检索到的书籍材料（PageIndex）---\n{context}\n\n"
                f"--- 对话历史 ---\n" + "\n".join(history) + "\n\n"
                "请回答最后一条 USER 问题。使用 Markdown 格式，引用锚点。"
            )
            reply = complete(CHAT_SYSTEM, user_prompt)
            return self._json({"reply": reply, "nodes": hit_nodes})
        except Exception as e:
            return self._json({"error": str(e)}, 500)

    def _api(self, path: str, qs: dict):
        try:
            if path == "/api/books":
                return self._json(discover_books())

            m = re.match(r"^/api/books/([^/]+)/meta$", path)
            if m:
                slug = m.group(1)
                meta = json.loads(
                    (book_root(slug) / "insight" / "book-meta.json").read_text(encoding="utf-8")
                )
                return self._json(meta)

            m = re.match(r"^/api/books/([^/]+)/page-index$", path)
            if m:
                slug = m.group(1)
                root = book_root(slug)
                return self._json(load_or_build_page_index(root))

            m = re.match(r"^/api/books/([^/]+)/insight/(.+)$", path)
            if m:
                slug, file_path = m.group(1), m.group(2)
                root = book_root(slug)
                fp = (root / "insight" / file_path).resolve()
                if not str(fp).startswith(str((root / "insight").resolve())):
                    return self._json({"error": "forbidden"}, 403)
                return self._json({"path": file_path, "content": fp.read_text(encoding="utf-8")})

            m = re.match(r"^/api/books/([^/]+)/source/([^/]+)$", path)
            if m:
                slug, chapter_id = m.group(1), m.group(2)
                start = int(qs.get("start", ["1"])[0])
                end = int(qs.get("end", ["0"])[0]) or None
                root = book_root(slug)
                meta = json.loads(
                    (root / "insight" / "book-meta.json").read_text(encoding="utf-8")
                )
                ch = next((c for c in meta["chapters"] if c["id"] == chapter_id), None)
                if not ch:
                    return self._json({"error": "chapter not found"}, 404)
                lines = (root / ch["source"]).read_text(encoding="utf-8").splitlines()
                total = len(lines)
                s = max(1, start) - 1
                e = min(total, end or total)
                return self._json(
                    {
                        "chapter_id": chapter_id,
                        "title": ch.get("title", ""),
                        "total_lines": total,
                        "start": s + 1,
                        "end": e,
                        "lines": [
                            {"n": s + i + 1, "text": line}
                            for i, line in enumerate(lines[s:e])
                        ],
                    }
                )

            return self._json({"error": "not found"}, 404)
        except Exception as e:
            return self._json({"error": str(e)}, 500)

    def _static(self, path: str):
        if path in ("/", ""):
            path = "/index.html"
        fp = (STATIC / path.lstrip("/")).resolve()
        if not str(fp).startswith(str(STATIC.resolve())) or not fp.is_file():
            return self._text("Not Found", status=404)
        ctype = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
        }.get(fp.suffix, "application/octet-stream")
        self._text(fp.read_text(encoding="utf-8"), content_type=ctype)


def main():
    load_env_file(ROOT / ".env")
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Book Compiler UI → http://127.0.0.1:{PORT}")
    if has_llm():
        print("AI 对话：已启用")
    else:
        print("AI 对话：未配置 LLM_API_KEY（仅显示提示）")
    server.serve_forever()


if __name__ == "__main__":
    main()
