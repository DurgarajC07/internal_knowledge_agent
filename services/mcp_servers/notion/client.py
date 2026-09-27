"""Thin, purpose-built wrapper around the Notion REST API (v1)."""

from __future__ import annotations

from typing import Any

import httpx

from packages.core.exceptions import ToolExecutionError
from services.mcp_servers._shared.http import assert_host_allowed
from services.mcp_servers.notion.schemas import NotionPageSummary

_NOTION_API_BASE = "https://api.notion.com/v1"
_NOTION_VERSION = "2022-06-28"


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
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    url,
                    json={
                        "query": query,
                        "page_size": max_results,
                        "filter": {"property": "object", "value": "page"},
                    },
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            raise ToolExecutionError(f"Notion search failed: {exc}") from exc

        return [
            NotionPageSummary(
                page_id=page["id"], title=_extract_title(page), url=page.get("url", "")
            )
            for page in data.get("results", [])
        ]

    async def get_page_content(self, page_id: str) -> str:
        url = f"{_NOTION_API_BASE}/blocks/{page_id}/children"
        assert_host_allowed(url, self._allowed_hosts)
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url, params={"page_size": 100}, headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            raise ToolExecutionError(f"Notion page fetch failed: {exc}") from exc

        lines = [_extract_rich_text(block) for block in data.get("results", [])]
        return "\n".join(line for line in lines if line)
