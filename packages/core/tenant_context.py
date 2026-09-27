"""The one object every tenant-scoped function must accept explicitly.

Resolved once per request from the verified auth token (see apps/api/dependencies.py)
and threaded explicitly through every call that touches tenant data. Never read from a
global/thread-local, and never constructed from a raw tenant_id string taken from a
request body or query parameter (Rule.md SS7, SS8; AGENT.md SS2.3).
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from packages.core.enums import Role


class TenantContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    tenant_id: UUID
    user_id: UUID
    role: Role
