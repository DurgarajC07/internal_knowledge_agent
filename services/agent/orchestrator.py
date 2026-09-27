"""The agent's orchestration loop: decide whether to retrieve, call a tool, or
answer directly (AGENT.md SS3, Plan.md SS12 — a single loop, not a multi-agent
framework). Framework-agnostic: no FastAPI/HTTP types (Rule R-2)."""

from __future__ import annotations

from dataclasses import dataclass, field

from packages.clients.embedding_client import EmbeddingClient
from packages.clients.llm_client import LLMClient, LLMMessage
from packages.clients.mcp_client import MCPClient
from packages.clients.qdrant_client import VectorStore
from packages.config.logging import get_logger
from packages.config.settings import Settings
from packages.core.schemas.citation import Citation
from packages.core.tenant_context import TenantContext
from services.agent.prompts import INSUFFICIENT_CONTEXT_FALLBACK, SYSTEM_PROMPT
from services.agent.tools import build_tool_specs, dispatch_tool_call

logger = get_logger(__name__)

_MAX_TOOL_ITERATIONS = 4


@dataclass
class AgentResult:
    text: str
    citations: list[Citation] = field(default_factory=list)


async def handle_message(
    *,
    tenant_ctx: TenantContext,
    message: str,
    history: list[LLMMessage] | None = None,
    llm_client: LLMClient,
    embedding_client: EmbeddingClient,
    vector_store: VectorStore,
    mcp_client: MCPClient,
    settings: Settings,
) -> AgentResult:
    tool_specs = await build_tool_specs(mcp_client)
    messages: list[LLMMessage] = [*(history or []), LLMMessage(role="user", content=message)]
    citations: list[Citation] = []

    for iteration in range(_MAX_TOOL_ITERATIONS):
        response = await llm_client.generate(messages, system=SYSTEM_PROMPT, tools=tool_specs)

        if not response.tool_calls:
            text = response.text.strip() or INSUFFICIENT_CONTEXT_FALLBACK
            return AgentResult(text=text, citations=citations)

        messages.append(
            LLMMessage(role="assistant", content=response.text, tool_calls=response.tool_calls)
        )

        for call in response.tool_calls:
            dispatch = await dispatch_tool_call(
                call,
                tenant_ctx=tenant_ctx,
                embedding_client=embedding_client,
                vector_store=vector_store,
                mcp_client=mcp_client,
                retrieval_top_k=settings.retrieval_top_k,
            )
            citations.extend(dispatch.citations)
            messages.append(
                LLMMessage(
                    role="tool",
                    content=dispatch.content,
                    tool_call_id=call.tool_call_id,
                    tool_name=call.tool_name,
                )
            )

        logger.info(
            "agent.tool_iteration",
            tenant_id=str(tenant_ctx.tenant_id),
            iteration=iteration,
            tool_count=len(response.tool_calls),
        )

    logger.warning(
        "agent.max_tool_iterations_exceeded",
        tenant_id=str(tenant_ctx.tenant_id),
        iterations=_MAX_TOOL_ITERATIONS,
    )
    return AgentResult(text=INSUFFICIENT_CONTEXT_FALLBACK, citations=citations)
