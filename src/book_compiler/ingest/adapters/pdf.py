"""PDF adapter — text layer extraction; scanned PDF flagged for OCR."""

from __future__ import annotations

from io import BytesIO

from ..canonical import BookDraft

_MIN_CHARS_PER_PAGE = 80


def _looks_truncated(data: bytes) -> bool:
    if len(data) < 64:
        return True
    if not data.lstrip().startswith(b"%PDF"):
        return False
    tail = data[-16384:]
    return b"%%EOF" not in tail and b"startxref" not in tail[-4096:]


def _friendly_pdf_error(data: bytes, err: Exception) -> str:
    msg = str(err).strip() or type(err).__name__
    hints: list[str] = []

    if not data.lstrip().startswith(b"%PDF"):
        hints.append("文件头不是有效 PDF，可能是网盘「在线文档」或未下载完成的占位文件")
    elif _looks_truncated(data):
        hints.append("文件可能下载不完整（百度网盘请等 100% 下载完成后再导入，勿从「传输列表未完成」的文件导入）")
    elif "Stream has ended unexpectedly" in msg or "EOF" in msg:
        hints.append(
            "PDF 内部结构不规范或损坏（网盘分享、扫描合并、浏览器打印常见）；"
            "可尝试：macOS 预览打开 → 导出 PDF，或用 Adobe / WPS 另存为新 PDF"
        )

    if hints:
        return f"无法解析 PDF：{msg}。{' '.join(hints)}"
    return f"无法解析 PDF：{msg}"


def _extract_with_pypdf(data: bytes) -> tuple[str, int, list[str]]:
    from pypdf import PdfReader  # type: ignore[import-untyped]

    warnings: list[str] = []
    last_err: Exception | None = None
    reader = None
    used_lenient = False

    for strict in (True, False):
        try:
            reader = PdfReader(BytesIO(data), strict=strict)
            used_lenient = not strict
            break
        except Exception as e:
            last_err = e
            if strict:
                continue
            raise

    if reader is None:
        assert last_err is not None
        raise last_err

    if used_lenient:
        warnings.append("PDF 格式略不规范，已用兼容模式读取（常见于网盘下载或第三方导出）")

    pages = len(reader.pages)
    parts: list[str] = []
    for i, page in enumerate(reader.pages, 1):
        t = (page.extract_text() or "").strip()
        if t:
            parts.append(f"--- 第 {i} 页 ---\n{t}")
    return "\n\n".join(parts), pages, warnings


def adapt(data: bytes, filename: str) -> BookDraft:
    if not data:
        raise ValueError("PDF 文件为空，请确认百度网盘已下载完成后再导入")

    warnings: list[str] = []
    try:
        text, page_count, extract_warnings = _extract_with_pypdf(data)
        warnings.extend(extract_warnings)
    except ImportError:
        raise ValueError(
            "PDF 导入需要 pypdf：pip install pypdf（扫描版 PDF 暂不支持，需 OCR 任务）"
        ) from None
    except Exception as e:
        raise ValueError(_friendly_pdf_error(data, e)) from e

    char_count = len(text.replace("\n", "").strip())
    if page_count > 0 and char_count < page_count * _MIN_CHARS_PER_PAGE:
        return BookDraft(
            text="",
            source_format="pdf_scan",
            original_filename=filename,
            warnings=[
                f"检测到扫描版 PDF（{page_count} 页，仅提取 {char_count} 字）",
                "请使用 OCR 流程（P3）或提供带文字层的 PDF",
            ],
            needs_ocr=True,
        )

    if not text.strip():
        raise ValueError("PDF 无可用文字层")

    warnings.append("PDF 文字层已转为纯文本，页标记为「--- 第 N 页 ---」")
    if "\x00" in text or "yabook.org" in text.lower():
        warnings.append("检测到 PDF 水印/乱码片段，部分行可能在阅读器中隐藏；建议使用正版文字层 PDF 或 OCR")
    return BookDraft(
        text=text.strip() + "\n",
        source_format="pdf_text",
        original_filename=filename,
        warnings=warnings,
    )
