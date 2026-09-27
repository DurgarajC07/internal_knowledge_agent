"""Bounded, explicit input schemas — never a free-form "run this query against
the API" tool (Rule.md SS6)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SearchFilesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, max_length=500)
    max_results: int = Field(default=10, ge=1, le=50)


class GetFileContentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_id: str = Field(..., min_length=1, max_length=200)


class ListRecentFilesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_results: int = Field(default=10, ge=1, le=50)


class DriveFileSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_id: str
    name: str
    web_view_link: str
    modified_time: str | None = None
