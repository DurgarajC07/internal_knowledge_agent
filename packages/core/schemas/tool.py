from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ToolCallContext(BaseModel):
    """Injected by the MCP host/client from the authenticated session.

    An MCP tool implementation must never accept a tenant_id as a parameter it
    trusts from the model's tool-call arguments (Rule.md SS6, AGENT.md SS7) — this
    is the only object a tool implementation may use to resolve *whose* credentials
    to use.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tenant_id: UUID
    requested_by_user_id: UUID


class ToolCallResult(BaseModel):
    """Untrusted output of any MCP tool. Size-capped before it re-enters the LLM
    context (Rule.md SS6) and always treated as data, never as instructions."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str
    success: bool
    content: str = Field(..., max_length=8000)
    byte_size: int
    error_message: str | None = None
