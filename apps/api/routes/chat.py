"""The chat endpoint. Streams a grounded answer over SSE (FR-2).

Note on streaming: the agent's tool-calling loop (retrieval, MCP calls) runs to
completion first via `handle_chat_turn`, then the finished answer is streamed to
the client in word-sized chunks. Streaming *during* tool-call reasoning would
need the LLM client's `.stream()` interleaved with tool dispatch — a real
enhancement, but not required by any BRD/Plan.md requirement and out of scope
without an ADR (AGENT.md SS2.7). This still gives the UI a token-by-token feel
and never blocks the whole response on one round-trip.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from apps.api import dependencies as deps
from apps.api.usecases import chat as chat_usecase
from packages.clients.embedding_client import EmbeddingClient
from packages.clients.llm_client import LLMClient
from packages.clients.mcp_client import MCPClient
from packages.clients.qdrant_client import VectorStore
from packages.clients.repositories.conversation_repository import ConversationRepository
from packages.config.settings import Settings
from packages.core.schemas.chat import ChatRequest, ChatStreamEvent
from packages.core.tenant_context import TenantContext

router = APIRouter(tags=["chat"])


async def _event_stream(result: chat_usecase.ChatTurnResult) -> AsyncIterator[str]:
    for word in result.answer.split(" "):
        yield ChatStreamEvent(type="token", data=word + " ").model_dump_json()
        await asyncio.sleep(0)
    yield ChatStreamEvent(type="citations", citations=result.citations).model_dump_json()
    yield ChatStreamEvent(type="done", conversation_id=result.conversation_id).model_dump_json()


@router.post("/chat")
async def chat(
    payload: ChatRequest,
    tenant_ctx: Annotated[TenantContext, Depends(deps.get_tenant_context)],
    conversation_repository: Annotated[
        ConversationRepository, Depends(deps.get_conversation_repository)
    ],
    llm_client: Annotated[LLMClient, Depends(deps.get_llm_client)],
    embedding_client: Annotated[EmbeddingClient, Depends(deps.get_embedding_client)],
    vector_store: Annotated[VectorStore, Depends(deps.get_vector_store)],
    mcp_client: Annotated[MCPClient, Depends(deps.get_mcp_client)],
    settings: Annotated[Settings, Depends(deps.get_settings_dep)],
) -> EventSourceResponse:
    result = await chat_usecase.handle_chat_turn(
        payload,
        tenant_ctx=tenant_ctx,
        conversation_repository=conversation_repository,
        llm_client=llm_client,
        embedding_client=embedding_client,
        vector_store=vector_store,
        mcp_client=mcp_client,
        settings=settings,
    )
    return EventSourceResponse(_event_stream(result))
