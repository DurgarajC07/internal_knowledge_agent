"""Thin, purpose-built wrapper around the Notion REST API (v1). Reused as-is
by the ingestion loader's "list + fetch" mode (Plan.md SS1.2)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx

from packages.core.exceptions import ToolExecutionError
from services.mcp_servers._shared.http import assert_host_allowed
from services.mcp_servers.notion.schemas import NotionPageSummary

_NOTION_API_BASE = "https://api.notion.com/v1"
_NOTION_VERSION = "2022-06-28"
_LIST_PAGE_SIZE = 100
_MAX_LIST_PAGES = 50  # defensive cap, mirrors google_drive/client.py


def _extract_title(page: dict[str, Any]) -> str:
    for prop in page.get("properties", {}).values():
        if prop.get("type") == "title":
            title_parts = prop.get("title", [])
            return "".join(part.get("plain_text", "") for part in title_parts) or "Untitled"
    return "Untitled"


def _extract_rich_text(block: dict[str, Any]) -> str:
    block_type = block.get("type", "")
    body = block.get(block_type, {})
    rich_text = body.get("rich_text", [])
    return "".join(part.get("plain_text", "") for part in rich_text)


class NotionClient:
    def __init__(self, access_token: str, allowed_hosts: list[str], timeout: float = 15.0) -> None:
        self._access_token = access_token
        self._allowed_hosts = allowed_hosts
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Notion-Version": _NOTION_VERSION,
        }

    async def search_pages(self, query: str, max_results: int) -> list[NotionPageSummary]:
        url = f"{_NOTION_API_BASE}/search"
        assert_host_allowed(url, self._allowed_hosts)
        body: dict[str, Any] = {
            "query": query,
            "page_size": max_results,
            "filter": {"property": "object", "value": "page"},
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            data = await self._post_json(client, url, body)
        return [
            NotionPageSummary(
                page_id=page["id"], title=_extract_title(page), url=page.get("url", "")
            )
            for page in data.get("results", [])
        ]

    async def list_all_pages(self) -> AsyncIterator[NotionPageSummary]:
        """Paginated listing (no query filter) for bulk ingestion — not used
        by the MCP live-lookup tool, which only wants a bounded top-K."""
        url = f"{_NOTION_API_BASE}/search"
        assert_host_allowed(url, self._allowed_hosts)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            cursor: str | None = None
            for _ in range(_MAX_LIST_PAGES):
                body: dict[str, Any] = {
                    "page_size": _LIST_PAGE_SIZE,
                    "filter": {"property": "object", "value": "page"},
                }
                if cursor:
                    body["start_cursor"] = cursor
                data = await self._post_json(client, url, body)
                for page in data.get("results", []):
                    yield NotionPageSummary(
                        page_id=page["id"], title=_extract_title(page), url=page.get("url", "")
                    )
                if not data.get("has_more"):
                    return
                cursor = data.get("next_cursor")
                if not cursor:
                    return

    async def get_page_content(self, page_id: str) -> str:
        url = f"{_NOTION_API_BASE}/blocks/{page_id}/children"
        assert_host_allowed(url, self._allowed_hosts)
        lines: list[str] = []
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            cursor: str | None = None
            for _ in range(_MAX_LIST_PAGES):
                params: dict[str, Any] = {"page_size": _LIST_PAGE_SIZE}
                if cursor:
                    params["start_cursor"] = cursor
                data = await self._get_json(client, url, params)
                lines.extend(_extract_rich_text(block) for block in data.get("results", []))
                if not data.get("has_more"):
                    break
                cursor = data.get("next_cursor")
                if not cursor:
                    break
        return "\n".join(line for line in lines if line)

    async def _get_json(
        self, client: httpx.AsyncClient, url: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            resp = await client.get(url, params=params, headers=self._headers())
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            raise ToolExecutionError(f"Notion request failed: {exc}") from exc

    async def _post_json(
        self, client: httpx.AsyncClient, url: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            resp = await client.post(url, json=body, headers=self._headers())
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            raise ToolExecutionError(f"Notion request failed: {exc}") from exc
