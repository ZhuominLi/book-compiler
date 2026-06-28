"""Minimal local reader — stdlib HTTP server, no FastAPI."""

from __future__ import annotations

import cgi
import json
import re
import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from book_compiler.paths import (  # noqa: E402
    chapter_path,
    frozen_bundle_root,
    meta_path,
    normalize_slug,
    overview_path,
    read_layer_file,
    resolve_book_root,
    resolve_static_dir,
    resolve_element_dir,
)

if getattr(sys, "frozen", False):
    root = frozen_bundle_root()
    ROOT = root if root else Path(sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(ROOT / "src"))

STATIC = resolve_static_dir(Path(__file__))
ELEMENT = resolve_element_dir(Path(__file__))

from book_compiler.books import book_item, delete_book, discover_books  # noqa: E402
from book_compiler.ingest import detect_format, ingest_bytes, ingest_text  # noqa: E402
from book_compiler.ingest.adapters.epub import extract_chapter_html, read_epub_asset  # noqa: E402
from book_compiler.ingest.registry import SUPPORTED_EXTENSIONS, SUPPORTED_LABEL  # noqa: E402
from book_compiler.init_book import init_book  # noqa: E402
from book_compiler.llm import complete, has_llm, load_env_file  # noqa: E402
from book_compiler.llm_settings import public_status, save_settings  # noqa: E402
from book_compiler.runtime_update import apply_runtime_update, check_for_update, runtime_status  # noqa: E402
from book_compiler.text_clean import is_garbage_line, normalize_text  # noqa: E402
from book_compiler.page_index import (  # noqa: E402
    build_chat_context,
    load_or_build_page_index,
)
from book_compiler.source_viewer import (  # noqa: E402
    chapter_epub_location,
    chapter_epub_spine_index,
    chapter_pdf_page,
    epub_file_path,
    line_pdf_page,
    load_meta,
    pdf_file_path,
)
from book_compiler.deep_prompt import (  # noqa: E402
    bind_deep_prompt_preset,
    get_deep_prompt,
    reset_deep_prompt,
    save_deep_prompt,
    save_deep_prompt_as_preset,
)
from book_compiler.prompt_presets import create_preset, delete_preset, list_presets, update_preset  # noqa: E402
from book_compiler.pipeline import iter_deep_chapter_stream, run_deep_chapter, run_preview  # noqa: E402
from book_compiler.qa_log import append_qa_turn, ensure_qa_file  # noqa: E402
from book_compiler.split_chapters import detect_split, split_book  # noqa: E402
from book_compiler.brand import APP_TITLE  # noqa: E402

PORT = 8765
HOST = "0.0.0.0"


def _lan_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return None


def _slug(raw: str) -> str:
    return normalize_slug(raw)


def _preset_id(raw: str) -> str:
    return normalize_slug(raw)


def _resolve_content(slug: str, file_path: str) -> tuple[str, Path]:
    """Map legacy paths to summary vs insight layer."""
    root = resolve_book_root(slug)
    if file_path.startswith("chapters/") or file_path == "overview.md":
        layer = "summary"
    else:
        layer = "insight"
    fp = read_layer_file(root, layer, file_path)
    return layer, fp


CHAT_SYSTEM = """你是懒豆阅读（BeanRead）阅读助手。基于用户提供的材料回答问题。

材料可能包含（按实际提供的内容）：
- **本章原文**：当前章 _extract 全文（带 L 行号），仅涵盖这一章
- **跨章 Summary 检索**：PageIndex 从全书其他章节/概念节点检索的 Summary 片段
- **仅 Summary 检索**：全书概览或未读具体章节时，由 PageIndex 提供的片段

规则：
1. 有本章原文时，本章内问题严格基于该章作答；跨章问题结合 Summary 检索片段
2. 仅 Summary 时，基于片段作答，跨章需标注出处（节点 id 或章节）
3. 引用原文使用 `(chNN, L起始-L结束)`，便于锚点跳转
4. 回答详细清晰、准确、有帮助，使用中文
5. 不要编造案例、数据或引用"""


def _chat_retrieve(
    slug: str,
    question: str,
    current_file: str,
    chapter_id: str | None = None,
    use_page_index: bool = False,
) -> tuple[str, list[str]]:
    root = resolve_book_root(slug)
    meta = json.loads(meta_path(root).read_text(encoding="utf-8"))
    return build_chat_context(
        root, meta, question, current_file, chapter_id, use_page_index=use_page_index
    )


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
        path = parsed.path
        if path == "/api/chat":
            return self._api_chat()
        if path == "/api/books":
            return self._api_create_book()
        if path == "/api/split/detect":
            return self._api_split_detect()
        if path == "/api/ingest/detect":
            return self._api_ingest_detect()
        m = re.match(r"^/api/books/([^/]+)/split$", path)
        if m:
            return self._api_split_book(_slug(m.group(1)))
        m = re.match(r"^/api/books/([^/]+)/deep/([^/]+)$", path)
        if m:
            return self._api_deep_chapter(_slug(m.group(1)), m.group(2))
        m = re.match(r"^/api/books/([^/]+)/preview$", path)
        if m:
            return self._api_preview(_slug(m.group(1)))
        m = re.match(r"^/api/books/([^/]+)/deep-prompt$", path)
        if m:
            return self._api_deep_prompt_save(_slug(m.group(1)))
        if path == "/api/prompt-presets":
            return self._api_prompt_presets_create()
        if path == "/api/settings/llm":
            return self._api_llm_settings_save()
        if path == "/api/update/check":
            return self._api_update_check()
        if path == "/api/update/apply":
            return self._api_update_apply()
        return self._json({"error": "not found"}, 404)

    def do_PUT(self):
        parsed = urlparse(self.path)
        m = re.match(r"^/api/prompt-presets/([^/]+)$", parsed.path)
        if m:
            return self._api_prompt_preset_update(_preset_id(m.group(1)))
        return self._json({"error": "not found"}, 404)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path
        m = re.match(r"^/api/books/([^/]+)$", path)
        if m:
            return self._api_delete_book(_slug(m.group(1)))
        m = re.match(r"^/api/prompt-presets/([^/]+)$", path)
        if m:
            return self._api_prompt_preset_delete(_preset_id(m.group(1)))
        return self._json({"error": "not found"}, 404)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    @staticmethod
    def _field_file_bytes(item) -> bytes | None:
        """cgi.FieldStorage items cannot be used in boolean context."""
        if item is None:
            return None
        fp = getattr(item, "file", None)
        if fp is None:
            return None
        return fp.read()

    def _read_multipart(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        env = {
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": self.headers.get("Content-Type", ""),
            "CONTENT_LENGTH": str(length),
        }
        form = cgi.FieldStorage(fp=BytesIO(raw), headers=self.headers, environ=env)
        out: dict = {}
        if "file" in form:
            file_item = form["file"]
            file_bytes = self._field_file_bytes(file_item)
            if file_bytes is not None:
                out["file_bytes"] = file_bytes
                out["source_filename"] = getattr(file_item, "filename", None) or "source.txt"
        for key in ("title", "tag", "auto_split", "use_llm"):
            if key not in form:
                continue
            val = form.getvalue(key)
            if isinstance(val, list):
                val = val[0] if val else ""
            out[key] = val
        return out

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

    def _bytes(self, body: bytes, content_type: str = "application/octet-stream", status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    @staticmethod
    def _sse_frame(event: str, data: dict) -> bytes:
        payload = json.dumps(data, ensure_ascii=False)
        return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")

    def _sse_deep_chapter(self, slug: str, chapter_id: str, *, force: bool):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        try:
            root = resolve_book_root(slug)
            for event, payload in iter_deep_chapter_stream(
                root, chapter_id, force=force, hitl=False
            ):
                self.wfile.write(self._sse_frame(event, payload))
                self.wfile.flush()
        except Exception as e:
            self.wfile.write(self._sse_frame("error", {"error": str(e)}))
            self.wfile.flush()

    def _bytes(self, data: bytes, content_type: str, status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_file(self, fp: Path, content_type: str):
        """Serve a file with Accept-Ranges so Chrome PDF viewer can stream large PDFs."""
        size = fp.stat().st_size
        range_header = self.headers.get("Range")
        if not range_header:
            with fp.open("rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            self.wfile.write(data)
            return

        m = re.match(r"bytes=(\d+)-(\d*)", range_header)
        if not m:
            self.send_error(416)
            return
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else size - 1
        end = min(end, size - 1)
        if start > end or start >= size:
            self.send_error(416)
            return
        with fp.open("rb") as f:
            f.seek(start)
            data = f.read(end - start + 1)
        self.send_response(206)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        self.wfile.write(data)

    def _api_chat(self):
        try:
            body = self._read_json_body()
            slug = body.get("slug")
            if not slug:
                return self._json({"error": "slug required"}, 400)
            slug = normalize_slug(slug)

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
                    "reply": "（未配置 AI 接口，请点击书架右上角 ⚙ 设置 API Key。）",
                    "nodes": [],
                    "context": "",
                })

            chapter_id = body.get("chapter_id")
            use_page_index = bool(body.get("use_page_index"))
            context, hit_nodes = _chat_retrieve(
                slug, question, current_file, chapter_id=chapter_id, use_page_index=use_page_index
            )
            user_prompt = (
                f"--- 书籍材料 ---\n{context}\n\n"
                f"--- 对话历史 ---\n" + "\n".join(history) + "\n\n"
                "请回答最后一条 USER 问题。使用 Markdown 格式；"
                "引用原文时使用 `(chNN, L起始-L结束)` 行号格式。"
            )
            reply = complete(CHAT_SYSTEM, user_prompt)
            root = resolve_book_root(slug)
            meta = json.loads(meta_path(root).read_text(encoding="utf-8"))
            append_qa_turn(
                root,
                slug=slug,
                book_title=meta.get("title", slug),
                chapter_id=body.get("chapter_id"),
                current_file=current_file,
                question=question,
                answer=reply,
                nodes=hit_nodes,
            )
            return self._json({"reply": reply, "nodes": hit_nodes, "context": context})
        except Exception as e:
            return self._json({"error": str(e)}, 500)

    def _api_split_detect(self):
        try:
            ctype = self.headers.get("Content-Type", "")
            ingest_meta = None
            if "multipart/form-data" in ctype:
                form = self._read_multipart()
                file_bytes = form.get("file_bytes")
                filename = form.get("source_filename", "source.txt")
                if not file_bytes:
                    return self._json({"error": "缺少 file"}, 400)
                draft = ingest_bytes(file_bytes, filename)
                if draft.needs_ocr:
                    return self._json({"error": "扫描版 PDF 需 OCR，暂不支持自动分章预览"}, 422)
                source_text = draft.text
                use_llm = str(form.get("use_llm", "true")).lower() not in ("0", "false", "no")
                ingest_meta = {
                    "source_format": draft.source_format,
                    "line_count": draft.line_count,
                    "warnings": draft.warnings,
                }
            else:
                body = self._read_json_body()
                source_text = body.get("source_text")
                if not source_text or not str(source_text).strip():
                    return self._json({"error": "缺少 source_text"}, 400)
                use_llm = bool(body.get("use_llm", True))
            result = detect_split(str(source_text), use_llm=use_llm)
            if ingest_meta:
                result["ingest"] = ingest_meta
            return self._json(result)
        except Exception as e:
            return self._json({"error": str(e)}, 500)

    def _api_ingest_detect(self):
        """Preview ingest + optional split without creating a book."""
        try:
            ctype = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in ctype:
                return self._json({"error": "请使用 multipart 上传文件"}, 400)
            form = self._read_multipart()
            file_bytes = form.get("file_bytes")
            filename = form.get("source_filename", "source.txt")
            if not file_bytes:
                return self._json({"error": "缺少 file"}, 400)
            draft = ingest_bytes(file_bytes, filename)
            out = {
                "source_format": draft.source_format,
                "original_filename": draft.original_filename,
                "char_count": draft.char_count,
                "line_count": draft.line_count,
                "warnings": draft.warnings,
                "needs_ocr": draft.needs_ocr,
            }
            if draft.needs_ocr:
                return self._json(out, 422)
            use_llm = str(form.get("use_llm", "true")).lower() not in ("0", "false", "no")
            if str(form.get("detect_split", "true")).lower() not in ("0", "false", "no"):
                out["split"] = detect_split(draft.text, use_llm=use_llm)
            return self._json(out)
        except Exception as e:
            return self._json({"error": str(e)}, 500)

    def _api_deep_chapter(self, slug: str, chapter_id: str):
        try:
            if not has_llm():
                return self._json({"error": "未配置 AI 接口，请在设置中填写 API Key"}, 503)
            body = self._read_json_body()
            force = bool(body.get("force", False))
            stream = bool(body.get("stream", False))
            root = resolve_book_root(slug)
            meta = json.loads(meta_path(root).read_text(encoding="utf-8"))
            ch = next((c for c in meta["chapters"] if c["id"] == chapter_id), None)
            if not ch:
                return self._json({"error": f"章节不存在: {chapter_id}"}, 404)
            if stream:
                return self._sse_deep_chapter(slug, chapter_id, force=force)
            cid = run_deep_chapter(root, chapter_id, force=force, hitl=False)
            if not cid:
                return self._json({"error": "本章已生成且未指定 force"}, 409)
            fp = chapter_path(root, chapter_id)
            text = fp.read_text(encoding="utf-8") if fp and fp.is_file() else ""
            return self._json({
                "chapter_id": cid,
                "path": str(fp.relative_to(root)) if fp else None,
                "lines": text.count("\n") + 1 if text else 0,
                "status": "approved",
            })
        except Exception as e:
            return self._json({"error": str(e)}, 500)

    def _api_preview(self, slug: str):
        try:
            if not has_llm():
                return self._json({"error": "未配置 AI 接口，请在设置中填写 API Key"}, 503)
            root = resolve_book_root(slug)
            meta = json.loads(meta_path(root).read_text(encoding="utf-8"))
            if not meta.get("chapters"):
                return self._json({"error": "请先分章后再生成全书概览"}, 400)
            run_preview(root)
            fp = overview_path(root)
            text = fp.read_text(encoding="utf-8") if fp.is_file() else ""
            return self._json({
                "path": "summary/overview.md",
                "lines": text.count("\n") + 1 if text else 0,
                "chapters": len(meta["chapters"]),
            })
        except Exception as e:
            return self._json({"error": str(e)}, 500)

    def _api_prompt_presets_list(self, qs: dict):
        template = (qs.get("template") or [None])[0]
        return self._json({"presets": list_presets(template)})

    def _api_prompt_presets_create(self):
        try:
            body = self._read_json_body()
            entry = create_preset(
                body.get("name", "未命名风格"),
                body.get("icon", "✨"),
                body.get("template", "M"),
                body.get("prompt", ""),
            )
            return self._json(entry)
        except ValueError as e:
            return self._json({"error": str(e)}, 400)
        except Exception as e:
            return self._json({"error": str(e)}, 500)

    def _api_prompt_preset_update(self, preset_id: str):
        try:
            body = self._read_json_body()
            entry = update_preset(
                preset_id,
                name=body.get("name"),
                icon=body.get("icon"),
                prompt=body.get("prompt"),
            )
            return self._json(entry)
        except ValueError as e:
            return self._json({"error": str(e)}, 400)
        except Exception as e:
            return self._json({"error": str(e)}, 500)

    def _api_prompt_preset_delete(self, preset_id: str):
        try:
            delete_preset(preset_id)
            return self._json({"ok": True})
        except ValueError as e:
            return self._json({"error": str(e)}, 400)
        except Exception as e:
            return self._json({"error": str(e)}, 500)

    def _api_deep_prompt_save(self, slug: str):
        try:
            body = self._read_json_body()
            template = body.get("template") or "M"
            root = resolve_book_root(slug)
            if body.get("reset"):
                data = reset_deep_prompt(root, template)
            elif body.get("preset_id"):
                data = bind_deep_prompt_preset(root, template, body["preset_id"])
            elif body.get("save_as_preset"):
                sp = body["save_as_preset"]
                prompt = (body.get("prompt") or sp.get("prompt") or "").strip()
                data = save_deep_prompt_as_preset(
                    root,
                    template,
                    sp.get("name", "我的风格"),
                    sp.get("icon", "✨"),
                    prompt,
                )
            else:
                prompt = (body.get("prompt") or "").strip()
                if not prompt:
                    return self._json({"error": "prompt 不能为空"}, 400)
                data = save_deep_prompt(root, template, prompt)
            return self._json(data)
        except ValueError as e:
            return self._json({"error": str(e)}, 400)
        except Exception as e:
            return self._json({"error": str(e)}, 500)

    def _api_create_book(self):
        try:
            ctype = self.headers.get("Content-Type", "")
            ingest_warnings: list[str] = []
            source_format = "txt"

            if "multipart/form-data" in ctype:
                form = self._read_multipart()
                title = (form.get("title") or "").strip()
                file_bytes = form.get("file_bytes")
                source_filename = (form.get("source_filename") or f"{title}.txt").strip()
                upload_name = source_filename
                tag = (form.get("tag") or "").strip() or None
                auto_split = str(form.get("auto_split", "true")).lower() not in ("0", "false", "no")
                if not file_bytes:
                    return self._json({"error": "请上传源文件"}, 400)
                draft = ingest_bytes(file_bytes, source_filename)
                if draft.needs_ocr:
                    return self._json(
                        {
                            "error": "扫描版 PDF 暂无文字层，需 OCR 流程（P3）",
                            "needs_ocr": True,
                            "warnings": draft.warnings,
                        },
                        422,
                    )
                source_text = draft.text
                source_format = draft.source_format
                ingest_warnings = draft.warnings
                original_bytes = file_bytes
                original_name = upload_name
            else:
                body = self._read_json_body()
                title = (body.get("title") or "").strip()
                source_text = body.get("source_text")
                tag = (body.get("tag") or "").strip() or None
                auto_split = bool(body.get("auto_split"))
                source_filename = (body.get("source_filename") or f"{title}.txt").strip()
                original_bytes = None
                original_name = None
                if source_text and str(source_text).strip():
                    try:
                        draft = ingest_text(str(source_text), source_filename)
                        source_text = draft.text
                        source_format = draft.source_format
                        ingest_warnings = draft.warnings
                    except ValueError:
                        source_format = detect_format(source_filename)
                        source_text = str(source_text)

            if not title:
                return self._json({"error": "请填写书名"}, 400)
            if not source_text or not str(source_text).strip():
                return self._json({"error": f"请上传源文件（支持 {SUPPORTED_LABEL}）"}, 400)

            if not source_filename.endswith(".txt"):
                source_filename = Path(source_filename).stem + ".txt"

            upload_ext = Path(original_name).suffix.lower() if original_name else ""
            keep_original = upload_ext in (".pdf", ".epub")

            root = init_book(
                title=title,
                tag=tag,
                source_text=str(source_text),
                source_filename=source_filename,
                source_format=source_format,
                ingest_warnings=ingest_warnings,
                original_file_bytes=original_bytes if keep_original else None,
                original_file_name=original_name if keep_original else None,
            )

            chapters = 0
            split_error = None
            if auto_split:
                try:
                    chapters = split_book(root)
                except Exception as e:
                    split_error = str(e)

            item = book_item(root)
            item["split_chapters"] = chapters
            item["split_error"] = split_error
            item["ingest"] = {
                "source_format": source_format,
                "warnings": ingest_warnings,
            }
            return self._json(item, 201)
        except Exception as e:
            return self._json({"error": str(e)}, 500)

    def _api_delete_book(self, slug: str):
        try:
            return self._json(delete_book(slug))
        except Exception as e:
            return self._json({"error": str(e)}, 400)

    def _api_split_book(self, slug: str):
        try:
            root = resolve_book_root(slug)
            chapters = split_book(root)
            item = book_item(root)
            item["split_chapters"] = chapters
            return self._json(item)
        except Exception as e:
            return self._json({"error": str(e)}, 500)

    def _api_update_check(self):
        try:
            return self._json(check_for_update(ROOT))
        except Exception as e:
            return self._json({"ok": False, "error": str(e), "update_available": False}, 500)

    def _api_update_apply(self):
        try:
            body = self._read_json_body()
            url = (body.get("url") or "").strip()
            if not url:
                return self._json({"error": "缺少 url"}, 400)
            return self._json(apply_runtime_update(url, str(body.get("sha256") or "")))
        except Exception as e:
            return self._json({"error": str(e)}, 500)

    def _api_llm_settings_save(self):
        try:
            body = self._read_json_body()
            kwargs = {}
            if "api_key" in body:
                kwargs["api_key"] = body.get("api_key") or ""
            if "base_url" in body:
                kwargs["base_url"] = body.get("base_url") or ""
            if "model" in body:
                kwargs["model"] = body.get("model") or ""
            return self._json(save_settings(**kwargs))
        except Exception as e:
            return self._json({"error": str(e)}, 500)

    def _api(self, path: str, qs: dict):
        try:
            if path == "/api/books":
                return self._json(discover_books())

            if path == "/api/health":
                return self._json({
                    "ok": True,
                    "features": ["import", "ingest", "split", "chat", "reader", "deep-prompt", "prompt-presets", "settings", "update"],
                    "ingest_formats": list(SUPPORTED_EXTENSIONS),
                    "llm": public_status(),
                    "runtime": runtime_status(ROOT),
                })

            if path == "/api/update/status":
                return self._json(runtime_status(ROOT))

            if path == "/api/settings/llm":
                return self._json(public_status())

            if path == "/api/prompt-presets":
                return self._api_prompt_presets_list(qs)

            m = re.match(r"^/api/books/([^/]+)/meta$", path)
            if m:
                slug = _slug(m.group(1))
                meta = json.loads(meta_path(resolve_book_root(slug)).read_text(encoding="utf-8"))
                return self._json(meta)

            m = re.match(r"^/api/books/([^/]+)/deep-prompt$", path)
            if m:
                slug = _slug(m.group(1))
                template = (qs.get("template") or ["M"])[0]
                root = resolve_book_root(slug)
                return self._json(get_deep_prompt(root, template))

            m = re.match(r"^/api/books/([^/]+)/page-index$", path)
            if m:
                slug = _slug(m.group(1))
                root = resolve_book_root(slug)
                return self._json(load_or_build_page_index(root))

            m = re.match(r"^/api/books/([^/]+)/insight/(.+)$", path)
            if m:
                slug, file_path = _slug(m.group(1)), unquote(m.group(2))
                if file_path == "qa.md":
                    root = resolve_book_root(slug)
                    meta = json.loads(meta_path(root).read_text(encoding="utf-8"))
                    fp = ensure_qa_file(root, meta.get("title", slug), slug)
                    return self._json({"path": file_path, "layer": "insight", "content": fp.read_text(encoding="utf-8")})
                layer, fp = _resolve_content(slug, file_path)
                return self._json({"path": file_path, "layer": layer, "content": fp.read_text(encoding="utf-8")})

            m = re.match(r"^/api/books/([^/]+)/pdf$", path)
            if m:
                slug = _slug(m.group(1))
                root = resolve_book_root(slug)
                meta = load_meta(root)
                fp = pdf_file_path(root, meta)
                if not fp:
                    return self._json({"error": "no pdf"}, 404)
                return self._serve_file(fp, "application/pdf")

            m = re.match(r"^/api/books/([^/]+)/pdf-location/([^/]+)$", path)
            if m:
                slug, chapter_id = _slug(m.group(1)), m.group(2)
                root = resolve_book_root(slug)
                meta = load_meta(root)
                line_q = (qs.get("line") or [None])[0]
                if line_q and str(line_q).isdigit():
                    page = line_pdf_page(root, meta, chapter_id, int(line_q))
                else:
                    page = chapter_pdf_page(root, meta, chapter_id)
                return self._json({
                    "page": page,
                    "has_pdf": pdf_file_path(root, meta) is not None,
                })

            m = re.match(r"^/api/books/([^/]+)/epub$", path)
            if m:
                slug = _slug(m.group(1))
                root = resolve_book_root(slug)
                meta = load_meta(root)
                fp = epub_file_path(root, meta)
                if not fp:
                    return self._json({"error": "no epub"}, 404)
                return self._bytes(fp.read_bytes(), "application/epub+zip")

            m = re.match(r"^/api/books/([^/]+)/epub-chapter/([^/]+)$", path)
            if m:
                slug, chapter_id = _slug(m.group(1)), m.group(2)
                root = resolve_book_root(slug)
                meta = load_meta(root)
                fp = epub_file_path(root, meta)
                ch = next((c for c in meta.get("chapters", []) if c.get("id") == chapter_id), None)
                href = ch.get("epub_href") if ch else None
                if not fp or not href:
                    return self._json({"error": "no epub chapter"}, 404)
                try:
                    html = extract_chapter_html(fp.read_bytes(), href, slug=slug)
                except Exception as e:
                    return self._json({"error": str(e)}, 500)
                return self._json({"html": html})

            m = re.match(r"^/api/books/([^/]+)/epub-asset$", path)
            if m:
                slug = _slug(m.group(1))
                asset_path = unquote((qs.get("path") or [""])[0])
                if not asset_path:
                    return self._json({"error": "path required"}, 400)
                root = resolve_book_root(slug)
                meta = load_meta(root)
                fp = epub_file_path(root, meta)
                if not fp:
                    return self._json({"error": "no epub"}, 404)
                try:
                    data, mime = read_epub_asset(fp.read_bytes(), asset_path)
                except FileNotFoundError:
                    return self._json({"error": "asset not found"}, 404)
                return self._bytes(data, mime)

            m = re.match(r"^/api/books/([^/]+)/epub-location/([^/]+)$", path)
            if m:
                slug, chapter_id = _slug(m.group(1)), m.group(2)
                root = resolve_book_root(slug)
                meta = load_meta(root)
                return self._json(chapter_epub_location(root, meta, chapter_id))

            m = re.match(r"^/api/books/([^/]+)/source/([^/]+)$", path)
            if m:
                slug, chapter_id = _slug(m.group(1)), m.group(2)
                start = int(qs.get("start", ["1"])[0])
                end = int(qs.get("end", ["0"])[0]) or None
                root = resolve_book_root(slug)
                meta = json.loads(meta_path(root).read_text(encoding="utf-8"))
                ch = next((c for c in meta["chapters"] if c["id"] == chapter_id), None)
                if not ch:
                    return self._json({"error": "chapter not found"}, 404)
                raw = (root / ch["source"]).read_bytes()
                text = normalize_text(raw.decode("utf-8", errors="replace"))
                lines = text.splitlines()
                total = len(lines)
                s = max(1, start) - 1
                e = min(total, end or total)
                slice_lines = lines[s:e]
                garbage = sum(1 for ln in slice_lines if is_garbage_line(ln))
                return self._json(
                    {
                        "chapter_id": chapter_id,
                        "title": ch.get("title", ""),
                        "total_lines": total,
                        "garbage_lines": garbage,
                        "start": s + 1,
                        "end": e,
                        "lines": [
                            {
                                "n": s + i + 1,
                                "text": "" if is_garbage_line(line) else line,
                                "corrupt": is_garbage_line(line),
                            }
                            for i, line in enumerate(slice_lines)
                        ],
                    }
                )

            return self._json({"error": "not found"}, 404)
        except Exception as e:
            return self._json({"error": str(e)}, 500)

    def _static(self, path: str):
        if path.startswith("/element/"):
            rel = path[len("/element/") :]
            fp = (ELEMENT / rel).resolve()
            root = ELEMENT.resolve()
            if not str(fp).startswith(str(root)) or not fp.is_file():
                return self._text("Not Found", status=404)
            ctype = {
                ".css": "text/css; charset=utf-8",
                ".json": "application/json; charset=utf-8",
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".webp": "image/webp",
                ".svg": "image/svg+xml",
            }.get(fp.suffix.lower(), "application/octet-stream")
            if fp.suffix.lower() in (".css", ".json", ".svg"):
                return self._text(fp.read_text(encoding="utf-8"), content_type=ctype)
            return self._bytes(fp.read_bytes(), content_type=ctype)

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


def create_httpd(host: str = HOST, port: int = PORT) -> ThreadingHTTPServer:
    from book_compiler.paths import app_data_dir

    load_env_file(app_data_dir() / ".env")
    if not getattr(sys, "frozen", False):
        load_env_file(ROOT / ".env")
    return ThreadingHTTPServer((host, port), Handler)


def main():
    httpd = create_httpd()
    print(f"{APP_TITLE} → http://127.0.0.1:{PORT}")
    lan = _lan_ip()
    if lan:
        print(f"局域网访问 → http://{lan}:{PORT}")
    if has_llm():
        print("AI 对话：已启用")
    else:
        print("AI 对话：未配置（请在设置 → AI 接口 中填写 API Key）")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
