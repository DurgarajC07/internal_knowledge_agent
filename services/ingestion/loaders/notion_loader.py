"""Bulk "list + fetch" loader for Notion (FR-6) — reuses the exact same
`NotionClient` the MCP live-lookup tool uses (Plan.md SS1.2)."""

from __future__ import annotations

from collections.abc import AsyncIterator

from services.ingestion.schemas import RawDocument
from services.mcp_servers.notion.client import NotionClient


class NotionLoader:
    source_name = "notion"

    def __init__(self, client: NotionClient) -> None:
        self._client = client

    async def load_all(self) -> AsyncIterator[RawDocument]:
        async for summary in self._client.list_all_pages():
            content = await self._client.get_page_content(summary.page_id)
            if not content:
                continue
            yield RawDocument(
                document_id=summary.page_id,
                title=summary.title,
                url_or_path=summary.url,
                source=self.source_name,
                raw_bytes=content.encode("utf-8"),
                filename=f"{summary.title}.txt",
            )
