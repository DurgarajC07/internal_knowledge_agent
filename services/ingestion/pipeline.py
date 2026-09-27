"""Ties load -> parse -> clean -> chunk -> embed -> upsert together. Runnable
identically from a cron job, a queue worker, or a developer's terminal
(Rule.md SS5) — never imported by apps/api routes (AGENT.md SS2.1, Rule R-1).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from packages.clients.embedding_client import EmbeddingClient
from packages.clients.qdrant_client import VectorStore
from packages.config.logging import get_logger
from packages.core.exceptions import UnsupportedDocumentTypeError
from packages.core.pii_fields import redact
from packages.core.schemas.ingestion import IngestedChunk
from services.ingestion.chunker import chunk_text
from services.ingestion.cleaner import clean_text
from services.ingestion.loaders.base import DocumentLoader
from services.ingestion.parsers.registry import get_parser_for

logger = get_logger(__name__)

_EMBED_BATCH_SIZE = 32


def deterministic_point_id(tenant_id: UUID, source: str, document_id: str, chunk_index: int) -> str:
    """Same (tenant, source, doc, chunk_index) always maps to the same point ID,
    so re-ingestion upserts instead of duplicating (Rule.md SS5)."""
    key = f"{tenant_id}:{source}:{document_id}:{chunk_index}"
    return str(uuid5(NAMESPACE_URL, key))


@dataclass
class IngestionResult:
    document_count: int = 0
    chunk_count: int = 0
    skipped_count: int = 0


async def ingest_source(
    *,
    tenant_id: UUID,
    loader: DocumentLoader,
    embedding_client: EmbeddingClient,
    vector_store: VectorStore,
) -> IngestionResult:
    result = IngestionResult()
    pending_chunks: list[IngestedChunk] = []
    pending_texts: list[str] = []

    async def flush() -> None:
        if not pending_chunks:
            return
        vectors = await embedding_client.embed(pending_texts)
        await vector_store.upsert_chunks(tenant_id, pending_chunks, vectors)
        pending_chunks.clear()
        pending_texts.clear()

    async for raw_document in loader.load_all():
        try:
            parser = get_parser_for(raw_document.filename)
        except UnsupportedDocumentTypeError:
            logger.warning(
                "ingestion.unsupported_type", **redact({"filename": raw_document.filename})
            )
            result.skipped_count += 1
            continue

        text = clean_text(parser.parse(raw_document.raw_bytes, raw_document.filename))
        chunks = chunk_text(text)
        if not chunks:
            result.skipped_count += 1
            continue

        ingested_at = datetime.now(UTC)
        for index, chunk in enumerate(chunks):
            pending_chunks.append(
                IngestedChunk(
                    point_id=deterministic_point_id(
                        tenant_id, raw_document.source, raw_document.document_id, index
                    ),
                    tenant_id=tenant_id,
                    source=raw_document.source,
                    document_id=raw_document.document_id,
                    document_title=raw_document.title,
                    url_or_path=raw_document.url_or_path,
                    chunk_index=index,
                    text=chunk,
                    ingested_at=ingested_at,
                )
            )
            pending_texts.append(chunk)
            result.chunk_count += 1

            if len(pending_chunks) >= _EMBED_BATCH_SIZE:
                await flush()

        result.document_count += 1

    await flush()
    logger.info(
        "ingestion.completed",
        tenant_id=str(tenant_id),
        document_count=result.document_count,
        chunk_count=result.chunk_count,
        skipped_count=result.skipped_count,
    )
    return result
