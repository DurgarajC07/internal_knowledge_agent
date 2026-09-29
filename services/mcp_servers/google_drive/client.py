"""Thin, purpose-built wrapper around the Google Drive v3 REST API. Only this
module and notion/client.py are allowed to speak to their external system
directly — the MCP server layer wraps them into narrowly-scoped tools
(AGENT.md SS2.2). Reused as-is by the ingestion loader's "list + fetch" mode
(Plan.md SS1.2: "same MCP server code the agent uses for live lookups —
reused, not duplicated")."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx

from packages.core.exceptions import ToolExecutionError
from services.mcp_servers._shared.http import assert_host_allowed
from services.mcp_servers.google_drive.schemas import DriveFileSummary

_DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"
_EXPORTABLE_GOOGLE_MIME_PREFIX = "application/vnd.google-apps"
_LIST_PAGE_SIZE = 100
_MAX_LIST_PAGES = 50  # defensive cap: 5,000 files is already generous at MVP scale


class GoogleDriveClient:
    def __init__(self, access_token: str, allowed_hosts: list[str], timeout: float = 15.0) -> None:
        self._access_token = access_token
        self._allowed_hosts = allowed_hosts
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._access_token}"}

    async def search_files(self, query: str, max_results: int) -> list[DriveFileSummary]:
        url = f"{_DRIVE_API_BASE}/files"
        assert_host_allowed(url, self._allowed_hosts)
        params = {
            "q": f"fullText contains '{query}' and trashed = false",
            "pageSize": str(max_results),
            "fields": "files(id,name,webViewLink,modifiedTime)",
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            return await self._list_one_page(client, url, params)

    async def list_recent_files(self, max_results: int) -> list[DriveFileSummary]:
        url = f"{_DRIVE_API_BASE}/files"
        assert_host_allowed(url, self._allowed_hosts)
        params = {
            "q": "trashed = false",
            "orderBy": "modifiedTime desc",
            "pageSize": str(max_results),
            "fields": "files(id,name,webViewLink,modifiedTime)",
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            return await self._list_one_page(client, url, params)

    async def list_all_files(self) -> AsyncIterator[DriveFileSummary]:
        """Paginated listing for bulk ingestion (Plan.md FR-6) — not used by
        the MCP live-lookup tools, which only ever want a bounded top-K."""
        url = f"{_DRIVE_API_BASE}/files"
        assert_host_allowed(url, self._allowed_hosts)
        params: dict[str, str] = {
            "q": "trashed = false",
            "pageSize": str(_LIST_PAGE_SIZE),
            "fields": "nextPageToken,files(id,name,webViewLink,modifiedTime)",
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            page_token: str | None = None
            for _ in range(_MAX_LIST_PAGES):
                page_params = dict(params)
                if page_token:
                    page_params["pageToken"] = page_token
                data = await self._get_json(client, url, page_params)
                for f in data.get("files", []):
                    yield DriveFileSummary(
                        file_id=f["id"],
                        name=f["name"],
                        web_view_link=f.get("webViewLink", ""),
                        modified_time=f.get("modifiedTime"),
                    )
                page_token = data.get("nextPageToken")
                if not page_token:
                    return

    async def _get_json(
        self, client: httpx.AsyncClient, url: str, params: dict[str, str]
    ) -> dict[str, Any]:
        try:
            resp = await client.get(url, params=params, headers=self._headers())
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            raise ToolExecutionError(f"Google Drive request failed: {exc}") from exc

    async def _list_one_page(
        self, client: httpx.AsyncClient, url: str, params: dict[str, str]
    ) -> list[DriveFileSummary]:
        data = await self._get_json(client, url, params)
        return [
            DriveFileSummary(
                file_id=f["id"],
                name=f["name"],
                web_view_link=f.get("webViewLink", ""),
                modified_time=f.get("modifiedTime"),
            )
            for f in data.get("files", [])
        ]

    async def _resolve_download(
        self, client: httpx.AsyncClient, file_id: str
    ) -> tuple[str, dict[str, str], str, str]:
        metadata_url = f"{_DRIVE_API_BASE}/files/{file_id}"
        assert_host_allowed(metadata_url, self._allowed_hosts)
        meta = await self._get_json(client, metadata_url, {"fields": "name,mimeType"})
        name = meta.get("name", file_id)
        mime_type = meta.get("mimeType", "")

        if mime_type.startswith(_EXPORTABLE_GOOGLE_MIME_PREFIX):
            return f"{metadata_url}/export", {"mimeType": "text/plain"}, mime_type, name
        return metadata_url, {"alt": "media"}, mime_type, name

    async def get_file_content(self, file_id: str) -> str:
        """Extracted plain text — used by the MCP live-lookup tool, where the
        LLM only ever wants readable content, never raw bytes."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                content_url, params, _mime_type, _name = await self._resolve_download(
                    client, file_id
                )
                resp = await client.get(content_url, params=params, headers=self._headers())
                resp.raise_for_status()
                return resp.text
        except httpx.HTTPError as exc:
            raise ToolExecutionError(f"Google Drive file fetch failed: {exc}") from exc

    async def download_file(self, file_id: str) -> tuple[bytes, str]:
        """Raw bytes + a filename carrying the right extension, for the
        ingestion loader's parser-by-extension dispatch (Rule.md SS5) — a
        Google-native doc is exported as text/plain and named `<title>.txt`
        so it routes to the text parser; anything else keeps its own name."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                content_url, params, mime_type, name = await self._resolve_download(client, file_id)
                resp = await client.get(content_url, params=params, headers=self._headers())
                resp.raise_for_status()
                filename = (
                    f"{name}.txt" if mime_type.startswith(_EXPORTABLE_GOOGLE_MIME_PREFIX) else name
                )
                return resp.content, filename
        except httpx.HTTPError as exc:
            raise ToolExecutionError(f"Google Drive file download failed: {exc}") from exc
