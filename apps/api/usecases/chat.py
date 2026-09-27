"""The chat use-case: load history, run the agent, persist both turns. This is
the function apps/api/routes/chat.py calls — the route itself does no
orchestration, retrieval, or persistence (Rule.md SS3, AGENT.md SS6)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from packages.clients.embedding_client import EmbeddingClient
from packages.clients.llm_client import LLMClient, LLMMessage
from packages.clients.mcp_client import MCPClient
from packages.clients.qdrant_client import VectorStore
from packages.clients.repositories.conversation_repository import ConversationRepository
from packages.config.settings import Settings
from packages.core.enums import MessageRole
from packages.core.schemas.chat import ChatRequest
from packages.core.schemas.citation import Citation
from packages.core.tenant_context import TenantContext
from services.agent.orchestrator import handle_message


@dataclass
class ChatTurnResult:
    conversation_id: UUID
    answer: str
    citations: list[Citation]


def _history_role(role: MessageRole) -> Literal["user", "assistant"] | None:
    if role is MessageRole.USER:
        return "user"
    if role is MessageRole.ASSISTANT:
        return "assistant"
    return None  # tool-call turns are not persisted; see module docstring


async def handle_chat_turn(
    payload: ChatRequest,
    *,
    tenant_ctx: TenantContext,
    conversation_repository: ConversationRepository,
    llm_client: LLMClient,
    embedding_client: EmbeddingClient,
    vector_store: VectorStore,
    mcp_client: MCPClient,
    settings: Settings,
) -> ChatTurnResult:
    if payload.conversation_id is not None:
        existing = await conversation_repository.get_detail(
            tenant_ctx.tenant_id, tenant_ctx.user_id, payload.conversation_id
        )
        history = [
            LLMMessage(role=role, content=m.content)
            for m in (existing.messages if existing else [])
            if (role := _history_role(m.role)) is not None
        ]
        conversation_id = payload.conversation_id
    else:
        created = await conversation_repository.create(
            tenant_ctx.tenant_id, tenant_ctx.user_id, title=None
        )
        history = []
        conversation_id = created.id

    await conversation_repository.append_message(
        tenant_ctx.tenant_id, conversation_id, MessageRole.USER, payload.message, citations=[]
    )

    result = await handle_message(
        tenant_ctx=tenant_ctx,
        message=payload.message,
        history=history,
        llm_client=llm_client,
        embedding_client=embedding_client,
        vector_store=vector_store,
        mcp_client=mcp_client,
        settings=settings,
    )

    await conversation_repository.append_message(
        tenant_ctx.tenant_id,
        conversation_id,
        MessageRole.ASSISTANT,
        result.text,
        citations=result.citations,
    )

    return ChatTurnResult(
        conversation_id=conversation_id, answer=result.text, citations=result.citations
    )
