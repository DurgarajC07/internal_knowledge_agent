from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from packages.core.enums import IngestionStatus


class IngestedChunk(BaseModel):
    """The unit written to Qdrant. `point_id` is deterministic so re-ingestion
    upserts instead of duplicating (Rule.md SS5)."""

    model_config = ConfigDict(extra="forbid")

    point_id: str
    tenant_id: UUID
    source: str
    document_id: str
    document_title: str
    url_or_path: str
    chunk_index: int
    text: str
    ingested_at: datetime


class IngestionJobStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: UUID
    tenant_id: UUID
    source: str
    status: IngestionStatus
    document_count: int = 0
    chunk_count: int = 0
    error_message: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
