from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Citation(BaseModel):
    """A reference back to the retrieved/fetched source that grounded an answer.

    Built exclusively from retrieved-chunk metadata or MCP tool-result metadata —
    the Response Assembler constructs these, the LLM never invents one (BRD.md SS6,
    Plan.md SS1.1).
    """

    model_config = ConfigDict(extra="forbid")

    document_title: str
    url_or_path: str
    source: str
    chunk_index: int | None = None
    snippet: str
