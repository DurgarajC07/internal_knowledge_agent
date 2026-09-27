"""Builds the tool surface the LLM sees and dispatches its tool-call intents.

`search_knowledge_base` is an internal tool backed directly by
services/retrieval — never wrapped in MCP, per Plan.md SS2 Q5. Every other tool
is namespaced `<provider>__<tool_name>` and dispatched through the MCP client,
so the model can never address a connector tool ambiguously or smuggle a
tenant/credential value through its arguments (Rule.md SS6)."""

from __future__ import annotations

from dataclasses import dataclass, field

from packages.clients.embedding_client import EmbeddingClient
from packages.clients.llm_client import ToolCallIntent, ToolSpec
from packages.clients.mcp_client import MCPClient
from packages.clients.qdrant_client import VectorStore
from packages.core.enums import ConnectorProvider
from packages.core.schemas.citation import Citation
from packages.core.schemas.retrieval import RetrievalQuery
from packages.core.schemas.tool import ToolCallContext
from packages.core.tenant_context import TenantContext
from services.retrieval.retriever import retrieve

SEARCH_KNOWLEDGE_BASE_TOOL = "search_knowledge_base"
_NAMESPACE_SEPARATOR = "__"
_SNIPPET_CHARS = 400


def _namespaced_tool_name(provider: ConnectorProvider, tool_name: str) -> str:
    return f"{provider.value}{_NAMESPACE_SEPARATOR}{tool_name}"


def _split_namespaced_tool_name(name: str) -> tuple[ConnectorProvider, str] | None:
    if _NAMESPACE_SEPARATOR not in name:
        return None
    provider_value, tool_name = name.split(_NAMESPACE_SEPARATOR, 1)
    try:
        return ConnectorProvider(provider_value), tool_name
    except ValueError:
        return None


async def build_tool_specs(mcp_client: MCPClient) -> list[ToolSpec]:
    specs = [
        ToolSpec(
            name=SEARCH_KNOWLEDGE_BASE_TOOL,
            description=(
                "Search this tenant's ingested company documents for information "
                "relevant to the user's question. Always try this before answering."
            ),
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string", "minLength": 1, "maxLength": 2000}},
                "required": ["query"],
                "additionalProperties": False,
            },
        )
    ]
    for provider in mcp_client.available_providers():
        for tool in await mcp_client.list_tools(provider):
            specs.append(
                ToolSpec(
                    name=_namespaced_tool_name(provider, str(tool["name"])),
                    description=str(tool["description"]),
                    input_schema=dict(tool["input_schema"]),  # type: ignore[arg-type]
                )
            )
    return specs


@dataclass
class ToolDispatchResult:
    content: str
    citations: list[Citation] = field(default_factory=list)


async def dispatch_tool_call(
    intent: ToolCallIntent,
    *,
    tenant_ctx: TenantContext,
    embedding_client: EmbeddingClient,
    vector_store: VectorStore,
    mcp_client: MCPClient,
    retrieval_top_k: int,
) -> ToolDispatchResult:
    if intent.tool_name == SEARCH_KNOWLEDGE_BASE_TOOL:
        return await _dispatch_search_knowledge_base(
            intent, tenant_ctx, embedding_client, vector_store, retrieval_top_k
        )

    parsed = _split_namespaced_tool_name(intent.tool_name)
    if parsed is None:
        return ToolDispatchResult(content=f"Unknown tool '{intent.tool_name}'.")
    provider, mcp_tool_name = parsed

    result = await mcp_client.call_tool(
        ToolCallContext(tenant_id=tenant_ctx.tenant_id, requested_by_user_id=tenant_ctx.user_id),
        provider,
        mcp_tool_name,
        intent.tool_input,
    )
    if not result.success:
        return ToolDispatchResult(
            content=f"Tool call failed: {result.error_message or 'unknown error'}"
        )
    return ToolDispatchResult(content=result.content)


async def _dispatch_search_knowledge_base(
    intent: ToolCallIntent,
    tenant_ctx: TenantContext,
    embedding_client: EmbeddingClient,
    vector_store: VectorStore,
    retrieval_top_k: int,
) -> ToolDispatchResult:
    query_text = str(intent.tool_input.get("query", "")).strip()
    if not query_text:
        return ToolDispatchResult(content="No query provided.")

    chunks = await retrieve(
        RetrievalQuery(
            tenant_id=tenant_ctx.tenant_id, query_text=query_text, top_k=retrieval_top_k
        ),
        embedding_client=embedding_client,
        vector_store=vector_store,
    )
    if not chunks:
        return ToolDispatchResult(content="No relevant results found in the knowledge base.")

    lines: list[str] = []
    citations: list[Citation] = []
    for chunk in chunks:
        snippet = chunk.text[:_SNIPPET_CHARS]
        lines.append(f"[Source: {chunk.document_title}]\n{snippet}")
        citations.append(
            Citation(
                document_title=chunk.document_title,
                url_or_path=chunk.url_or_path,
                source=chunk.source,
                chunk_index=chunk.chunk_index,
                snippet=snippet,
            )
        )
    return ToolDispatchResult(content="\n\n".join(lines), citations=citations)
