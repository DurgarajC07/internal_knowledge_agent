"""Thin, purpose-built wrapper around the Google Drive v3 REST API. Only this
module and notion/client.py are allowed to speak to their external system
directly — the MCP server layer wraps them into narrowly-scoped tools
(AGENT.md SS2.2)."""

from __future__ import annotations

import httpx

from packages.core.exceptions import ToolExecutionError
from services.mcp_servers._shared.http import assert_host_allowed
from services.mcp_servers.google_drive.schemas import DriveFileSummary

_DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"
_EXPORTABLE_GOOGLE_MIME_PREFIX = "application/vnd.google-apps"


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
        return await self._list(url, params)

    async def list_recent_files(self, max_results: int) -> list[DriveFileSummary]:
        url = f"{_DRIVE_API_BASE}/files"
        assert_host_allowed(url, self._allowed_hosts)
        params = {
            "q": "trashed = false",
            "orderBy": "modifiedTime desc",
            "pageSize": str(max_results),
            "fields": "files(id,name,webViewLink,modifiedTime)",
        }
        return await self._list(url, params)

    async def _list(self, url: str, params: dict[str, str]) -> list[DriveFileSummary]:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url, params=params, headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            raise ToolExecutionError(f"Google Drive search failed: {exc}") from exc

        return [
            DriveFileSummary(
                file_id=f["id"],
                name=f["name"],
                web_view_link=f.get("webViewLink", ""),
                modified_time=f.get("modifiedTime"),
            )
            for f in data.get("files", [])
        ]

    async def get_file_content(self, file_id: str) -> str:
        metadata_url = f"{_DRIVE_API_BASE}/files/{file_id}"
        assert_host_allowed(metadata_url, self._allowed_hosts)
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                meta_resp = await client.get(
                    metadata_url, params={"fields": "mimeType"}, headers=self._headers()
                )
                meta_resp.raise_for_status()
                mime_type = meta_resp.json().get("mimeType", "")

                if mime_type.startswith(_EXPORTABLE_GOOGLE_MIME_PREFIX):
                    content_url = f"{metadata_url}/export"
                    resp = await client.get(
                        content_url,
                        params={"mimeType": "text/plain"},
                        headers=self._headers(),
                    )
                else:
                    content_url = metadata_url
                    resp = await client.get(
                        content_url, params={"alt": "media"}, headers=self._headers()
                    )
                resp.raise_for_status()
                return resp.text
        except httpx.HTTPError as exc:
            raise ToolExecutionError(f"Google Drive file fetch failed: {exc}") from exc
