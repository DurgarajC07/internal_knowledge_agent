from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from packages.core.enums import ConnectorProvider, IngestionStatus


class ConnectorAuthorizeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authorize_url: str


class ConnectorStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: ConnectorProvider
    connected: bool
    configured: bool


class IngestionJobOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    source: str
    status: IngestionStatus
    document_count: int
    chunk_count: int
    error_message: str | None
    started_at: datetime
    finished_at: datetime | None
