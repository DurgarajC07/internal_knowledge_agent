"""Bulk "list + fetch" loader for Google Drive (FR-6) — reuses the exact same
`GoogleDriveClient` the MCP live-lookup tool uses (Plan.md SS1.2: "same MCP
server code the agent uses for live lookups — reused, not duplicated"), just
in paginated bulk mode instead of a bounded top-K search."""

from __future__ import annotations

from collections.abc import AsyncIterator

from services.ingestion.schemas import RawDocument
from services.mcp_servers.google_drive.client import GoogleDriveClient

_MAX_FILE_BYTES = 25 * 1024 * 1024  # mirrors LocalFileLoader's defensive cap


class GoogleDriveLoader:
    source_name = "google_drive"

    def __init__(self, client: GoogleDriveClient) -> None:
        self._client = client

    async def load_all(self) -> AsyncIterator[RawDocument]:
        async for summary in self._client.list_all_files():
            content, filename = await self._client.download_file(summary.file_id)
            if not content or len(content) > _MAX_FILE_BYTES:
                continue
            yield RawDocument(
                document_id=summary.file_id,
                title=summary.name,
                url_or_path=summary.web_view_link,
                source=self.source_name,
                raw_bytes=content,
                filename=filename,
            )
