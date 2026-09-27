"""Query-time retrieval: embed the query, search Qdrant (tenant-filtered), return
ranked chunks with citation-ready metadata. Internal library call from
services/agent — never wrapped in MCP (Plan.md SS2 Q5) and never imports FastAPI
(Rule R-2)."""

from __future__ import annotations

import asyncio
import time

from packages.clients.embedding_client import EmbeddingClient
from packages.clients.qdrant_client import VectorStore
from packages.config.logging import get_logger
from packages.core.exceptions import RetrievalTimeoutError
from packages.core.schemas.retrieval import RetrievalQuery, RetrievedChunk

logger = get_logger(__name__)

_RETRIEVAL_TIMEOUT_SECONDS = 5.0


async def retrieve(
    query: RetrievalQuery,
    *,
    embedding_client: EmbeddingClient,
    vector_store: VectorStore,
    timeout_seconds: float = _RETRIEVAL_TIMEOUT_SECONDS,
) -> list[RetrievedChunk]:
    """`query.tenant_id` is required by the RetrievalQuery model itself, so this
    function structurally cannot run without a tenant scope (Rule.md SS7/SS8).
    Every call is audit-logged (tenant, duration, hit count) — never the query
    text or retrieved content itself (Rule.md SS3, Plan.md SS8)."""
    started_at = time.monotonic()
    try:
        async with asyncio.timeout(timeout_seconds):
            vectors = await embedding_client.embed([query.query_text])
            results = [] if not vectors else await vector_store.search(query, vectors[0])
    except TimeoutError as exc:
        logger.warning(
            "retrieval.timeout",
            tenant_id=str(query.tenant_id),
            duration_ms=round((time.monotonic() - started_at) * 1000, 1),
        )
        raise RetrievalTimeoutError(
            f"Retrieval exceeded {timeout_seconds}s for tenant {query.tenant_id}"
        ) from exc

    logger.info(
        "retrieval.query",
        tenant_id=str(query.tenant_id),
        duration_ms=round((time.monotonic() - started_at) * 1000, 1),
        result_count=len(results),
        success=True,
    )
    return results
