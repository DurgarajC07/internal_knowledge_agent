from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from services.ingestion.schemas import RawDocument


class DocumentLoader(Protocol):
    """Pulls raw bytes for every document a source currently has. Ingestion-only —
    never imported by apps/api (Rule.md SS5)."""

    source_name: str

    def load_all(self) -> AsyncIterator[RawDocument]: ...
