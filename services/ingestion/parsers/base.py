from __future__ import annotations

from typing import Protocol


class DocumentParser(Protocol):
    """Format-specific: raw bytes in, plain text out. Parses defensively — no
    parser may execute content extracted from a document (Plan.md SS9)."""

    def parse(self, raw_bytes: bytes, filename: str) -> str: ...
