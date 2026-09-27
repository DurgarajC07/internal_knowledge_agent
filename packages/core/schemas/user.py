from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr

from packages.core.enums import Role


class UserRecord(BaseModel):
    """Internal DTO crossing the repository -> use-case boundary. Never
    returned to a client directly — `hashed_password` must not leave this
    layer (Rule.md SS4, SS3)."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    email: EmailStr
    hashed_password: str
    role: Role
