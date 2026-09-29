from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from packages.clients.db import Base, build_session_factory
from packages.clients.repositories.credential_repository import CredentialRepository
from packages.clients.repositories.ingestion_job_repository import IngestionJobRepository
from packages.core.enums import ConnectorProvider, IngestionStatus
from packages.core.schemas.connector import IngestionJobOut
from packages.core.schemas.tenant_credentials import ConnectorCredential
from services.ingestion.scheduler import _enqueue_overdue_jobs, _needs_resync
from tests.conftest import build_test_settings

_TEST_KEY = "wZ0nQ3z6r6t2c8m0y6q0k0k3m4h9j1p6y6b3z8t5u4o="


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = build_session_factory(engine)
    async with factory() as session:
        yield session
    await engine.dispose()


def _job(source: str, status, started_at: datetime) -> IngestionJobOut:
    return IngestionJobOut(
        id=uuid4(),
        tenant_id=uuid4(),
        source=source,
        status=status,
        document_count=0,
        chunk_count=0,
        error_message=None,
        started_at=started_at,
        finished_at=None,
    )


def test_needs_resync_true_when_never_synced() -> None:
    assert _needs_resync([], "google_drive", datetime.now(UTC).replace(tzinfo=None)) is True


def test_needs_resync_false_when_recently_succeeded() -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    jobs = [_job("google_drive", IngestionStatus.SUCCEEDED, now - timedelta(hours=1))]
    assert _needs_resync(jobs, "google_drive", now - timedelta(hours=6)) is False


def test_needs_resync_true_when_last_sync_is_older_than_cutoff() -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    jobs = [_job("google_drive", IngestionStatus.SUCCEEDED, now - timedelta(hours=10))]
    assert _needs_resync(jobs, "google_drive", now - timedelta(hours=6)) is True


def test_needs_resync_false_when_already_pending_or_running() -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    jobs = [_job("google_drive", IngestionStatus.PENDING, now - timedelta(hours=10))]
    assert _needs_resync(jobs, "google_drive", now - timedelta(hours=6)) is False


def test_needs_resync_ignores_jobs_for_a_different_source() -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    jobs = [_job("notion", IngestionStatus.SUCCEEDED, now)]
    assert _needs_resync(jobs, "google_drive", now - timedelta(hours=6)) is True


async def test_enqueue_overdue_jobs_only_enqueues_tenants_with_a_connected_credential(
    session,
) -> None:
    tenant_with_credential = uuid4()
    tenant_without_credential = uuid4()

    credential_repository = CredentialRepository(session, _TEST_KEY)
    await credential_repository.upsert(
        tenant_with_credential,
        ConnectorCredential(
            tenant_id=tenant_with_credential,
            provider=ConnectorProvider.GOOGLE_DRIVE,
            access_token="tok",
            scopes=[],
        ),
    )
    job_repository = IngestionJobRepository(session)
    settings = build_test_settings(ingestion_resync_interval_hours=6)

    enqueued = await _enqueue_overdue_jobs(job_repository, credential_repository, settings)
    await session.commit()

    assert enqueued == 1
    jobs = await job_repository.list_for_tenant(tenant_with_credential)
    assert len(jobs) == 1
    assert jobs[0].source == "google_drive"

    no_jobs = await job_repository.list_for_tenant(tenant_without_credential)
    assert no_jobs == []


async def test_enqueue_overdue_jobs_does_not_duplicate_an_already_pending_job(session) -> None:
    tenant_id = uuid4()
    credential_repository = CredentialRepository(session, _TEST_KEY)
    await credential_repository.upsert(
        tenant_id,
        ConnectorCredential(
            tenant_id=tenant_id,
            provider=ConnectorProvider.NOTION,
            access_token="tok",
            scopes=[],
        ),
    )
    job_repository = IngestionJobRepository(session)
    settings = build_test_settings(ingestion_resync_interval_hours=6)

    first_run = await _enqueue_overdue_jobs(job_repository, credential_repository, settings)
    await session.commit()
    second_run = await _enqueue_overdue_jobs(job_repository, credential_repository, settings)
    await session.commit()

    assert first_run == 1
    assert second_run == 0
    assert len(await job_repository.list_for_tenant(tenant_id)) == 1
