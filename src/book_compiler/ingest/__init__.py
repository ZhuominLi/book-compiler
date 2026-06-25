"""Input pipeline: arbitrary formats → canonical plain text (BookDraft)."""

from .canonical import BookDraft, IngestResult
from .pipeline import detect_format, ingest_bytes, ingest_text

__all__ = ["BookDraft", "IngestResult", "detect_format", "ingest_bytes", "ingest_text"]
