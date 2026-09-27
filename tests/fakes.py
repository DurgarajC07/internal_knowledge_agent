"""Shared in-memory test doubles. Unit tests must never make a real network call
(Rule.md SS9) — these stand in for the embedding client and the vector store."""

from __future__ import annotations

from uuid import UUID

from packages.core.enums import ConnectorProvider
from packages.core.exceptions import CredentialNotFoundError
from packages.core.schemas.ingestion import IngestedChunk
from packages.core.schemas.retrieval import RetrievalQuery, RetrievedChunk
from packages.core.schemas.tenant_credentials import ConnectorCredential


class FakeCredentialRepository:
    """In-memory stand-in for CredentialRepository — no DB required."""

    def __init__(
        self, credentials: dict[tuple[UUID, ConnectorProvider], ConnectorCredential]
    ) -> None:
        self._credentials = credentials

    async def get(self, tenant_id: UUID, provider: ConnectorProvider) -> ConnectorCredential:
        key = (tenant_id, provider)
        if key not in self._credentials:
            raise CredentialNotFoundError(f"No {provider.value} credential for tenant {tenant_id}")
        return self._credentials[key]


class FakeEmbeddingClient:
    dimensions = 4

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[float(len(t)), 0.0, 0.0, 0.0] for t in texts]


class FakeVectorStore:
    """Keyed by point_id, so a second upsert of the same point_id overwrites
    rather than duplicates — the idempotency guarantee Rule.md SS5 requires."""

    def __init__(self) -> None:
        self.points: dict[str, tuple[IngestedChunk, list[float]]] = {}

    async def upsert_chunks(
        self, tenant_id: UUID, chunks: list[IngestedChunk], vectors: list[list[float]]
    ) -> None:
        for chunk, vector in zip(chunks, vectors, strict=True):
            self.points[chunk.point_id] = (chunk, vector)

    async def search(
        self, query: RetrievalQuery, query_vector: list[float]
    ) -> list[RetrievedChunk]:
        matches = [
            RetrievedChunk(
                chunk_id=chunk.point_id,
                tenant_id=chunk.tenant_id,
                source=chunk.source,
                document_id=chunk.document_id,
                document_title=chunk.document_title,
                url_or_path=chunk.url_or_path,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                score=1.0,
                ingested_at=chunk.ingested_at,
            )
            for chunk, _ in self.points.values()
            if chunk.tenant_id == query.tenant_id
        ]
        return matches[: query.top_k]
