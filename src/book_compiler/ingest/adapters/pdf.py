"""PDF adapter — text layer extraction; scanned PDF flagged for OCR."""

from __future__ import annotations

from ..canonical import BookDraft

_MIN_CHARS_PER_PAGE = 80


def _extract_with_pypdf(data: bytes) -> tuple[str, int, list[str]]:
    from pypdf import PdfReader  # type: ignore[import-untyped]
    from io import BytesIO

    reader = PdfReader(BytesIO(data))
    pages = len(reader.pages)
    parts: list[str] = []
    for i, page in enumerate(reader.pages, 1):
        t = (page.extract_text() or "").strip()
        if t:
            parts.append(f"--- 第 {i} 页 ---\n{t}")
    return "\n\n".join(parts), pages, []


def adapt(data: bytes, filename: str) -> BookDraft:
    warnings: list[str] = []
    try:
        text, page_count, warnings = _extract_with_pypdf(data)
    except ImportError:
        raise ValueError(
            "PDF 导入需要 pypdf：pip install pypdf（扫描版 PDF 暂不支持，需 OCR 任务）"
        ) from None
    except Exception as e:
        raise ValueError(f"无法解析 PDF：{e}") from e

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
