from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from packages.core.schemas.citation import Citation


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(..., min_length=1, max_length=4000)
    conversation_id: UUID | None = None


class ChatResponse(BaseModel):
    """Non-streaming shape, used by Phase-1 smoke tests and any non-SSE caller."""

    model_config = ConfigDict(extra="forbid")

    response: str
    citations: list[Citation] = []
    conversation_id: UUID | None = None


class ChatStreamEvent(BaseModel):
    """One SSE frame. `type` discriminates the payload the UI should render.

    - token: incremental answer text (`data`)
    - citations: the final citation list, sent once after generation completes
    - error: a user-safe error message (never a raw stack trace, Rule.md SS3)
    - done: stream complete; `conversation_id` lets the client resume the thread
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["token", "citations", "error", "done"]
    data: str | None = None
    citations: list[Citation] | None = None
    conversation_id: UUID | None = None
