from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SearchPagesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, max_length=500)
    max_results: int = Field(default=10, ge=1, le=50)


class GetPageContentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_id: str = Field(..., min_length=1, max_length=100)


class NotionPageSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_id: str
    title: str
    url: str
