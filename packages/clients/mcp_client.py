"""The MCP client: one instance per connected MCP server, translating the
agent's tool-call intents into MCP protocol calls (AGENT.md SS4). The only
place a tenant's decrypted OAuth credential is loaded into memory and injected
into a tool call — the LLM's tool-call arguments never carry a tenant_id or
credential (Rule.md SS6). Every call is audit-logged (tool, tenant, duration,
success, byte size) — never the raw content (Plan.md SS8, SS9)."""

from __future__ import annotations

import time

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, TextContent

from packages.clients.repositories.credential_repository import (
    CredentialReader,
)
from packages.config.logging import get_logger
from packages.config.settings import Settings
from packages.core.enums import ConnectorProvider
from packages.core.exceptions import CredentialNotFoundError, ToolExecutionError
from packages.core.schemas.tool import ToolCallContext, ToolCallResult
from services.mcp_servers._shared.context import current_credential
from services.mcp_servers.google_drive.server import build_google_drive_server
from services.mcp_servers.notion.server import build_notion_server

logger = get_logger(__name__)


class MCPClient:
    """Wraps the set of configured MCP servers (one per connector). Constructed
    only in packages/clients (Rule R-3); services/agent receives an instance via
    dependency injection."""

    def __init__(
        self,
        servers: dict[ConnectorProvider, MCPServer],
        credential_repository: CredentialReader,
        max_output_chars: int,
    ) -> None:
        self._servers = servers
        self._credential_repository = credential_repository
        self._max_output_chars = max_output_chars

    def available_providers(self) -> list[ConnectorProvider]:
        return list(self._servers)

    async def list_tools(self, provider: ConnectorProvider) -> list[dict[str, object]]:
        server = self._servers[provider]
        tools = await server.list_tools()
        return [
            {"name": t.name, "description": t.description or "", "input_schema": t.input_schema}
            for t in tools
        ]

    async def call_tool(
        self,
        context: ToolCallContext,
        provider: ConnectorProvider,
        tool_name: str,
        tool_input: dict[str, object],
    ) -> ToolCallResult:
        server = self._servers.get(provider)
        if server is None:
            return ToolCallResult(
                tool_name=tool_name,
                success=False,
                content="",
                byte_size=0,
                error_message=f"No MCP server configured for provider '{provider.value}'",
            )

        started_at = time.monotonic()
        success = False
        content = ""
        error_message: str | None = None

        try:
            credential = await self._credential_repository.get(context.tenant_id, provider)
        except CredentialNotFoundError as exc:
            error_message = str(exc)
        else:
            token = current_credential.set(credential)
            try:
                result = await server.call_tool(tool_name, tool_input)
                if isinstance(result, CallToolResult):
                    success = not result.is_error
                    content = "".join(
                        block.text for block in result.content if isinstance(block, TextContent)
                    )
                    if not success and not content:
                        error_message = "Tool call returned an error with no detail"
                else:
                    error_message = "Tool requires interactive input, which is not supported"
            except ToolError as exc:
                error_message = str(exc)
            except Exception as exc:  # noqa: BLE001 - never leak a raw SDK exception (Rule.md SS3)
                raise ToolExecutionError(f"MCP tool '{tool_name}' failed: {exc}") from exc
            finally:
                current_credential.reset(token)

        duration_ms = (time.monotonic() - started_at) * 1000
        byte_size = len(content.encode("utf-8"))
        logger.info(
            "mcp.tool_call",
            tool=tool_name,
            provider=provider.value,
            tenant_id=str(context.tenant_id),
            user_id=str(context.requested_by_user_id),
            duration_ms=round(duration_ms, 1),
            success=success,
            byte_size=byte_size,
        )

        capped = content[: self._max_output_chars]
        return ToolCallResult(
            tool_name=tool_name,
            success=success,
            content=capped,
            byte_size=byte_size,
            error_message=error_message,
        )


def build_mcp_client(settings: Settings, credential_repository: CredentialReader) -> MCPClient:
    servers: dict[ConnectorProvider, MCPServer] = {
        ConnectorProvider.GOOGLE_DRIVE: build_google_drive_server(settings),
        ConnectorProvider.NOTION: build_notion_server(settings),
    }
    return MCPClient(
        servers=servers,
        credential_repository=credential_repository,
        max_output_chars=settings.tool_output_max_chars,
    )
