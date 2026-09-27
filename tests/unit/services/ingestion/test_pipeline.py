from pathlib import Path
from uuid import uuid4

from services.ingestion.loaders.local_file_loader import LocalFileLoader
from services.ingestion.pipeline import deterministic_point_id, ingest_source
from tests.fakes import FakeEmbeddingClient, FakeVectorStore

FIXTURE_DIR = Path(__file__).resolve().parents[3] / "fixtures" / "sample_docs"


async def test_ingest_source_writes_chunks_with_metadata() -> None:
    tenant_id = uuid4()
    loader = LocalFileLoader(root=FIXTURE_DIR)
    embedding_client = FakeEmbeddingClient()
    vector_store = FakeVectorStore()

    result = await ingest_source(
        tenant_id=tenant_id,
        loader=loader,
        embedding_client=embedding_client,
        vector_store=vector_store,
    )

    assert result.document_count == 1
    assert result.chunk_count >= 1
    assert len(vector_store.points) == result.chunk_count
    chunk, _vector = next(iter(vector_store.points.values()))
    assert chunk.tenant_id == tenant_id
    assert chunk.source == "local"
    assert chunk.document_title == "contract_client_x.txt"


async def test_ingest_source_is_idempotent_on_reingestion() -> None:
    tenant_id = uuid4()
    loader = LocalFileLoader(root=FIXTURE_DIR)
    embedding_client = FakeEmbeddingClient()
    vector_store = FakeVectorStore()

    await ingest_source(
        tenant_id=tenant_id,
        loader=loader,
        embedding_client=embedding_client,
        vector_store=vector_store,
    )
    point_ids_after_first_run = set(vector_store.points)

    await ingest_source(
        tenant_id=tenant_id,
        loader=loader,
        embedding_client=embedding_client,
        vector_store=vector_store,
    )
    point_ids_after_second_run = set(vector_store.points)

    assert point_ids_after_first_run == point_ids_after_second_run


def test_deterministic_point_id_is_stable_across_calls() -> None:
    tenant_id = uuid4()
    first = deterministic_point_id(tenant_id, "local", "doc-1", 0)
    second = deterministic_point_id(tenant_id, "local", "doc-1", 0)
    assert first == second


def test_deterministic_point_id_differs_by_tenant() -> None:
    first = deterministic_point_id(uuid4(), "local", "doc-1", 0)
    second = deterministic_point_id(uuid4(), "local", "doc-1", 0)
    assert first != second
