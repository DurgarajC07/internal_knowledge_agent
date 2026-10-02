"""Thin wrapper around the Qdrant SDK — the only module allowed to construct a raw
Qdrant client (Rule.md R-3). One collection per tenant (Plan.md SS8); every search
and upsert call additionally carries a `tenant_id` payload filter as
defense-in-depth even though the collection is already tenant-scoped (Rule.md SS7).
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from qdrant_client import AsyncQdrantClient, models

from packages.config.settings import Settings
from packages.core.schemas.ingestion import IngestedChunk
from packages.core.schemas.retrieval import RetrievalQuery, RetrievedChunk


def collection_name(tenant_id: UUID) -> str:
    return f"tenant_{tenant_id.hex}"


class VectorStore(Protocol):
    """What services/ingestion and services/retrieval actually depend on —
    the concrete Qdrant implementation is injected, never constructed by them
    (Rule R-3). Lets tests substitute an in-memory fake instead of a live Qdrant."""

    async def upsert_chunks(
        self, tenant_id: UUID, chunks: list[IngestedChunk], vectors: list[list[float]]
    ) -> None: ...

    async def search(
        self, query: RetrievalQuery, query_vector: list[float]
    ) -> list[RetrievedChunk]: ...


class QdrantVectorStore:
    def __init__(self, client: AsyncQdrantClient, vector_size: int) -> None:
        self._client = client
        self._vector_size = vector_size

    async def close(self) -> None:
        await self._client.close()

    async def ensure_collection(self, tenant_id: UUID) -> None:
        name = collection_name(tenant_id)
        if not await self._client.collection_exists(name):
            await self._client.create_collection(
                collection_name=name,
                vectors_config=models.VectorParams(
                    size=self._vector_size, distance=models.Distance.COSINE
                ),
            )

    async def upsert_chunks(
        self,
        tenant_id: UUID,
        chunks: list[IngestedChunk],
        vectors: list[list[float]],
    ) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors must be the same length")
        await self.ensure_collection(tenant_id)
        points = [
            models.PointStruct(
                id=chunk.point_id,
                vector=vector,
                payload={
                    "tenant_id": str(tenant_id),
                    "source": chunk.source,
                    "document_id": chunk.document_id,
                    "document_title": chunk.document_title,
                    "url_or_path": chunk.url_or_path,
                    "chunk_index": chunk.chunk_index,
                    "text": chunk.text,
                    "ingested_at": chunk.ingested_at.isoformat(),
                },
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        await self._client.upsert(collection_name=collection_name(tenant_id), points=points)

    async def search(
        self, query: RetrievalQuery, query_vector: list[float]
    ) -> list[RetrievedChunk]:
        name = collection_name(query.tenant_id)
        if not await self._client.collection_exists(name):
            return []

        must: list[models.Condition] = [
            models.FieldCondition(
                key="tenant_id", match=models.MatchValue(value=str(query.tenant_id))
            )
        ]
        if query.source_filter:
            must.append(
                models.FieldCondition(
                    key="source", match=models.MatchValue(value=query.source_filter)
                )
            )

        hits = await self._client.query_points(
            collection_name=name,
            query=query_vector,
            query_filter=models.Filter(must=must),
            limit=query.top_k,
            with_payload=True,
        )

        chunks: list[RetrievedChunk] = []
        for hit in hits.points:
            payload = hit.payload
            assert payload is not None, "search was called with with_payload=True"
            chunks.append(
                RetrievedChunk(
                    chunk_id=str(hit.id),
                    tenant_id=query.tenant_id,
                    source=payload["source"],
                    document_id=payload["document_id"],
                    document_title=payload["document_title"],
                    url_or_path=payload["url_or_path"],
                    chunk_index=payload["chunk_index"],
                    text=payload["text"],
                    score=hit.score,
                    ingested_at=datetime.fromisoformat(payload["ingested_at"]),
                )
            )
        return chunks

    async def delete_tenant_collection(self, tenant_id: UUID) -> None:
        """Used on tenant offboarding — trivial to delete a whole collection (Plan.md SS8)."""
        name = collection_name(tenant_id)
        if await self._client.collection_exists(name):
            await self._client.delete_collection(name)


def build_qdrant_store(settings: Settings) -> QdrantVectorStore:
    client = AsyncQdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
    return QdrantVectorStore(client=client, vector_size=settings.embedding_dimensions)
