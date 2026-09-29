"""Tenant-scoped ingestion job bookkeeping. An API route only ever creates a
PENDING row here — it never runs the ingestion pipeline itself (Rule R-1).
services/ingestion/scheduler.py claims and completes jobs."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.clients.db_models import IngestionJobORM
from packages.core.enums import IngestionStatus
from packages.core.schemas.connector import IngestionJobOut


def _naive_utcnow() -> datetime:
    # `started_at`/`finished_at` aren't declared timezone-aware columns, so
    # both sqlite and Postgres hand back naive timestamps for `started_at`
    # (server_default=func.now()) — keep `finished_at` naive too, or a caller
    # comparing the two (services/ingestion/scheduler.py) hits a TypeError.
    return datetime.now(UTC).replace(tzinfo=None)


def _to_out(row: IngestionJobORM) -> IngestionJobOut:
    return IngestionJobOut(
        id=row.id,
        tenant_id=row.tenant_id,
        source=row.source,
        status=IngestionStatus(row.status),
        document_count=row.document_count,
        chunk_count=row.chunk_count,
        error_message=row.error_message,
        started_at=row.started_at,
        finished_at=row.finished_at,
    )


class IngestionJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_pending(self, tenant_id: UUID, source: str) -> IngestionJobOut:
        row = IngestionJobORM(
            tenant_id=tenant_id, source=source, status=IngestionStatus.PENDING.value
        )
        self._session.add(row)
        await self._session.flush()
        return _to_out(row)

    async def list_for_tenant(self, tenant_id: UUID) -> list[IngestionJobOut]:
        rows = await self._session.scalars(
            select(IngestionJobORM)
            .where(IngestionJobORM.tenant_id == tenant_id)
            .order_by(IngestionJobORM.started_at.desc())
            .limit(50)
        )
        return [_to_out(row) for row in rows]

    async def mark_running(self, job_id: UUID) -> None:
        row = await self._session.get(IngestionJobORM, job_id)
        if row is not None:
            row.status = IngestionStatus.RUNNING.value
            await self._session.flush()

    async def mark_succeeded(self, job_id: UUID, *, document_count: int, chunk_count: int) -> None:
        row = await self._session.get(IngestionJobORM, job_id)
        if row is not None:
            row.status = IngestionStatus.SUCCEEDED.value
            row.document_count = document_count
            row.chunk_count = chunk_count
            row.finished_at = _naive_utcnow()
            await self._session.flush()

    async def mark_failed(self, job_id: UUID, *, error_message: str) -> None:
        row = await self._session.get(IngestionJobORM, job_id)
        if row is not None:
            row.status = IngestionStatus.FAILED.value
            row.error_message = error_message[:2000]
            row.finished_at = _naive_utcnow()
            await self._session.flush()

    async def list_pending(self, *, limit: int = 20) -> list[IngestionJobOut]:
        rows = await self._session.scalars(
            select(IngestionJobORM)
            .where(IngestionJobORM.status == IngestionStatus.PENDING.value)
            .order_by(IngestionJobORM.started_at.asc())
            .limit(limit)
        )
        return [_to_out(row) for row in rows]
