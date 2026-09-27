from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from packages.core.enums import MessageRole
from packages.core.schemas.citation import Citation


class MessageOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    role: MessageRole
    content: str
    citations: list[Citation] = []
    created_at: datetime


class ConversationOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    user_id: UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class ConversationDetailOut(ConversationOut):
    messages: list[MessageOut] = []


class ConversationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
