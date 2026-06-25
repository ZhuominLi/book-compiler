"""Canonical intermediate representation after ingest."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..text_clean import normalize_text


@dataclass
class BookDraft:
    """Normalized book text — single source of truth for split + pipeline."""

    text: str
    source_format: str
    original_filename: str
    warnings: list[str] = field(default_factory=list)
    needs_ocr: bool = False
    char_count: int = 0
    line_count: int = 0

    def __post_init__(self) -> None:
        self.text = normalize_text(self.text)
        self.char_count = len(self.text)
        self.line_count = self.text.count("\n") + (1 if self.text else 0)


@dataclass
class IngestResult:
    draft: BookDraft
    saved_filename: str | None = None
