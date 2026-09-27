"""Ingestion-internal DTOs. These never cross out of services/ingestion, so they
stay local rather than in packages/core (Rule.md SS4 — that's reserved for schemas
shared across an app/layer boundary)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class RawDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    title: str
    url_or_path: str
    source: str
    raw_bytes: bytes
    filename: str
