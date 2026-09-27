"""Loads documents from a local directory — used for local dev ingestion and as
the fixture-backed path exercised by tests (Rule.md SS9: no live network calls in
unit tests). The Drive/Notion loaders (services/mcp_servers/*) are used in
"list + fetch" mode by the pipeline for the connector sources (Plan.md SS1.2)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from services.ingestion.schemas import RawDocument

_MAX_FILE_BYTES = 25 * 1024 * 1024  # defensive cap against runaway/malicious files


class LocalFileLoader:
    source_name = "local"

    def __init__(self, root: Path) -> None:
        self._root = root

    async def load_all(self) -> AsyncIterator[RawDocument]:
        for path in sorted(self._root.rglob("*")):
            if not path.is_file():
                continue
            size = path.stat().st_size
            if size == 0 or size > _MAX_FILE_BYTES:
                continue
            raw_bytes = path.read_bytes()
            yield RawDocument(
                document_id=str(path.relative_to(self._root)),
                title=path.name,
                url_or_path=str(path.resolve()),
                source=self.source_name,
                raw_bytes=raw_bytes,
                filename=path.name,
            )
