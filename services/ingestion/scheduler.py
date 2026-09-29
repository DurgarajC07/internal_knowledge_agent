"""Periodic connector re-sync entrypoint (FR-6), meant to run on a schedule
(Render Cron — see infrastructure/render.yaml's `cronJobs` entry). On each
run it:

  1. Enqueues a PENDING `ingestion_jobs` row for every (tenant, connected
     provider) pair that hasn't been synced within
     `settings.ingestion_resync_interval_hours`.
  2. Processes every currently PENDING job — including ones enqueued by an
     admin's manual "Sync now" click via `POST /api/connectors/{provider}/sync`
     (apps/api/routes/connectors.py), which only ever inserts a row and never
     runs ingestion itself (Rule R-1).

Runs to completion once and exits — no persistent worker process, matching
Plan.md SS11's "Render Cron" choice over a message bus (ruled out at MVP by
Plan.md SS12 without an ADR). Never imported by apps/api (Rule R-1).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from packages.clients.db import build_engine, build_session_factory
from packages.clients.embedding_client import build_embedding_client
from packages.clients.qdrant_client import build_qdrant_store
from packages.clients.repositories.credential_repository import CredentialRepository
from packages.clients.repositories.ingestion_job_repository import IngestionJobRepository
from packages.config.logging import configure_logging, get_logger
from packages.config.settings import Settings, get_settings
from packages.core.enums import ConnectorProvider, IngestionStatus
from packages.core.schemas.connector import IngestionJobOut
from services.ingestion.loader_factory import build_loader
from services.ingestion.pipeline import ingest_source

logger = get_logger(__name__)

_RESYNCABLE_PROVIDERS = (ConnectorProvider.GOOGLE_DRIVE, ConnectorProvider.NOTION)
_MAX_JOBS_PER_RUN = 100


async def _enqueue_overdue_jobs(
    job_repository: IngestionJobRepository,
    credential_repository: CredentialRepository,
    settings: Settings,
) -> int:
    # `IngestionJobORM.started_at` comes back naive from the DB (the column
    # isn't declared timezone-aware, so both sqlite and Postgres return a
    # naive timestamp) — compare against a naive UTC cutoff, not an
    # aware one, or this raises TypeError at comparison time.
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(
        hours=settings.ingestion_resync_interval_hours
    )
    enqueued = 0

    for provider in _RESYNCABLE_PROVIDERS:
        tenant_ids = await credential_repository.list_tenants_with_credential(provider)
        for tenant_id in tenant_ids:
            recent_jobs = await job_repository.list_for_tenant(tenant_id)
            due = _needs_resync(recent_jobs, provider.value, cutoff)
            if due:
                await job_repository.create_pending(tenant_id, provider.value)
                enqueued += 1

    return enqueued


def _needs_resync(recent_jobs: list[IngestionJobOut], source: str, cutoff: datetime) -> bool:
    matching = [job for job in recent_jobs if job.source == source]
    if not matching:
        return True
    already_queued = any(
        job.status in (IngestionStatus.PENDING, IngestionStatus.RUNNING) for job in matching
    )
    if already_queued:
        return False
    most_recent = max(job.started_at for job in matching)
    return most_recent < cutoff


async def main_async() -> None:
    settings = get_settings()
    configure_logging(settings.environment)

    engine = build_engine(settings)
    session_factory = build_session_factory(engine)
    embedding_client = build_embedding_client(settings)
    vector_store = build_qdrant_store(settings)

    enqueued = 0
    succeeded = 0
    failed = 0

    try:
        async with session_factory() as session:
            job_repository = IngestionJobRepository(session)
            credential_repository = CredentialRepository(
                session, settings.credential_encryption_key
            )

            enqueued = await _enqueue_overdue_jobs(job_repository, credential_repository, settings)
            await session.commit()

            pending = await job_repository.list_pending(limit=_MAX_JOBS_PER_RUN)

            for job in pending:
                await job_repository.mark_running(job.id)
                await session.commit()
                try:
                    loader = await build_loader(
                        job.source,
                        job.tenant_id,
                        settings=settings,
                        credential_repository=credential_repository,
                    )
                    result = await ingest_source(
                        tenant_id=job.tenant_id,
                        loader=loader,
                        embedding_client=embedding_client,
                        vector_store=vector_store,
                    )
                    await job_repository.mark_succeeded(
                        job.id,
                        document_count=result.document_count,
                        chunk_count=result.chunk_count,
                    )
                    succeeded += 1
                except Exception as exc:  # noqa: BLE001 - one job's failure must not abort the run
                    logger.error(
                        "ingestion.scheduled_job_failed",
                        job_id=str(job.id),
                        tenant_id=str(job.tenant_id),
                        source=job.source,
                        error=str(exc),
                    )
                    await job_repository.mark_failed(job.id, error_message=str(exc))
                    failed += 1
                await session.commit()
    finally:
        await engine.dispose()

    print(f"Scheduler run complete: {enqueued} enqueued, {succeeded} succeeded, {failed} failed.")


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
