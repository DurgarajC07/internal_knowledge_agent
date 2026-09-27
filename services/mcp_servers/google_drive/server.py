"""The Google Drive MCP server: a small set of narrowly-scoped tools, never a
generic "call the Drive API" passthrough (AGENT.md SS2.2, Plan.md SS2.4).
Deployed alongside the API at MVP and invoked in-process by
packages/clients/mcp_client.py — never imported by an apps/api route
(Rule R-1, Rule R-2: no FastAPI/HTTP types here).
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from packages.config.settings import Settings
from services.mcp_servers._shared.context import require_current_credential
from services.mcp_servers._shared.http import cap_output
from services.mcp_servers.google_drive.client import GoogleDriveClient
from services.mcp_servers.google_drive.schemas import (
    GetFileContentInput,
    ListRecentFilesInput,
    SearchFilesInput,
)


def build_google_drive_server(settings: Settings) -> MCPServer:
    server = MCPServer("google_drive")
    allowed_hosts = settings.mcp_allowed_hosts
    max_output_chars = settings.tool_output_max_chars

    def _client() -> GoogleDriveClient:
        credential = require_current_credential()
        return GoogleDriveClient(access_token=credential.access_token, allowed_hosts=allowed_hosts)

    @server.tool(description="Search the tenant's Google Drive for files matching a text query.")
    async def search_files(params: SearchFilesInput) -> str:
        files = await _client().search_files(params.query, params.max_results)
        if not files:
            return "No matching files found."
        lines = [f"- {f.name} ({f.web_view_link})" for f in files]
        return cap_output("\n".join(lines), max_output_chars)

    @server.tool(description="List the tenant's most recently modified Google Drive files.")
    async def list_recent_files(params: ListRecentFilesInput) -> str:
        files = await _client().list_recent_files(params.max_results)
        if not files:
            return "No files found."
        lines = [f"- {f.name} ({f.web_view_link})" for f in files]
        return cap_output("\n".join(lines), max_output_chars)

    @server.tool(description="Fetch the plain-text content of one Google Drive file by ID.")
    async def get_file_content(params: GetFileContentInput) -> str:
        content = await _client().get_file_content(params.file_id)
        return cap_output(content, max_output_chars)

    return server
