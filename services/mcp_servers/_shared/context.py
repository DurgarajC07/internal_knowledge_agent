"""The credential-injection channel between the MCP client and an MCP server's
tool functions.

The MCP client sets this ContextVar to the resolved, tenant-scoped credential
immediately before calling a tool and resets it immediately after (try/finally).
A tool implementation reads it here — it never accepts a tenant_id or credential
as a tool-call argument, because that would mean trusting a value the LLM's
tool-call arguments could supply (Rule.md SS6, AGENT.md SS7). ContextVar is
asyncio-Task-scoped, so concurrent calls for different tenants never leak into
each other.
"""

from __future__ import annotations

from contextvars import ContextVar

from packages.core.schemas.tenant_credentials import ConnectorCredential

current_credential: ContextVar[ConnectorCredential] = ContextVar("current_credential")


def require_current_credential() -> ConnectorCredential:
    try:
        return current_credential.get()
    except LookupError as exc:
        raise RuntimeError(
            "MCP tool invoked without a credential injected by the MCP client — "
            "tools must never be called directly, only via packages.clients.mcp_client"
        ) from exc
