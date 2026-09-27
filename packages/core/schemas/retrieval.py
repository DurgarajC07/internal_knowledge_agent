from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RetrievalQuery(BaseModel):
    """Input to services/retrieval. Always carries a tenant_id (Rule.md SS7)."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: UUID
    query_text: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(default=6, ge=1, le=20)
    source_filter: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


class RetrievedChunk(BaseModel):
    """One Qdrant hit, carrying everything needed to build a Citation with zero
    extra lookups (Rule.md SS5)."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    tenant_id: UUID
    source: str
    document_id: str
    document_title: str
    url_or_path: str
    chunk_index: int
    text: str
    score: float
    ingested_at: datetime
