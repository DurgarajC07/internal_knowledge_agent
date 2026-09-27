"""The Notion MCP server — mirrors google_drive/server.py's shape exactly, per
Plan.md SS1.2's "same MCP server code the agent uses for live lookups — reused,
not duplicated" (this server module is shared by the agent's live-lookup path
and the ingestion pipeline's "list + fetch" mode)."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from packages.config.settings import Settings
from services.mcp_servers._shared.context import require_current_credential
from services.mcp_servers._shared.http import cap_output
from services.mcp_servers.notion.client import NotionClient
from services.mcp_servers.notion.schemas import GetPageContentInput, SearchPagesInput


def build_notion_server(settings: Settings) -> MCPServer:
    server = MCPServer("notion")
    allowed_hosts = settings.mcp_allowed_hosts
    max_output_chars = settings.tool_output_max_chars

    def _client() -> NotionClient:
        credential = require_current_credential()
        return NotionClient(access_token=credential.access_token, allowed_hosts=allowed_hosts)

    @server.tool(
        description="Search the tenant's Notion workspace for pages matching a text query."
    )
    async def search_pages(params: SearchPagesInput) -> str:
        pages = await _client().search_pages(params.query, params.max_results)
        if not pages:
            return "No matching pages found."
        lines = [f"- {p.title} ({p.url})" for p in pages]
        return cap_output("\n".join(lines), max_output_chars)

    @server.tool(description="Fetch the plain-text content of one Notion page by ID.")
    async def get_page_content(params: GetPageContentInput) -> str:
        content = await _client().get_page_content(params.page_id)
        return cap_output(content, max_output_chars)

    return server
