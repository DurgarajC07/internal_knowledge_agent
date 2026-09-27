from datetime import UTC, datetime
from uuid import uuid4

import pytest

from packages.core.exceptions import RetrievalTimeoutError
from packages.core.schemas.ingestion import IngestedChunk
from packages.core.schemas.retrieval import RetrievalQuery
from services.retrieval.retriever import retrieve
from tests.fakes import FakeEmbeddingClient, FakeVectorStore


def _make_chunk(tenant_id, document_id: str) -> IngestedChunk:
    return IngestedChunk(
        point_id=f"{tenant_id}-{document_id}",
        tenant_id=tenant_id,
        source="local",
        document_id=document_id,
        document_title=f"{document_id}.txt",
        url_or_path=f"/docs/{document_id}.txt",
        chunk_index=0,
        text="some contract text",
        ingested_at=datetime.now(UTC),
    )


async def test_retrieve_returns_only_matching_tenant_chunks() -> None:
    tenant_a, tenant_b = uuid4(), uuid4()
    vector_store = FakeVectorStore()
    await vector_store.upsert_chunks(tenant_a, [_make_chunk(tenant_a, "doc-a")], [[0.0] * 4])
    await vector_store.upsert_chunks(tenant_b, [_make_chunk(tenant_b, "doc-b")], [[0.0] * 4])

    results = await retrieve(
        RetrievalQuery(tenant_id=tenant_a, query_text="contract terms"),
        embedding_client=FakeEmbeddingClient(),
        vector_store=vector_store,
    )

    assert len(results) == 1
    assert results[0].tenant_id == tenant_a
    assert results[0].document_id == "doc-a"


async def test_retrieve_returns_empty_list_when_embedding_produces_nothing() -> None:
    class EmptyEmbeddingClient:
        dimensions = 4

        async def embed(self, texts: list[str]) -> list[list[float]]:
            return []

    results = await retrieve(
        RetrievalQuery(tenant_id=uuid4(), query_text="anything"),
        embedding_client=EmptyEmbeddingClient(),
        vector_store=FakeVectorStore(),
    )
    assert results == []


async def test_retrieve_raises_retrieval_timeout_error_on_slow_backend() -> None:
    import asyncio

    class SlowEmbeddingClient:
        dimensions = 4

        async def embed(self, texts: list[str]) -> list[list[float]]:
            await asyncio.sleep(10)
            return [[0.0] * 4 for _ in texts]

    with pytest.raises(RetrievalTimeoutError):
        await retrieve(
            RetrievalQuery(tenant_id=uuid4(), query_text="slow query"),
            embedding_client=SlowEmbeddingClient(),
            vector_store=FakeVectorStore(),
            timeout_seconds=0.05,
        )
