from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from packages.core.enums import Role


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_name: str = Field(..., min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=200)


class TokenResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str
    token_type: Literal["bearer"] = "bearer"


class SessionUser(BaseModel):
    """Decoded JWT claims — the input to resolving a TenantContext per request."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    user_id: UUID
    tenant_id: UUID
    email: EmailStr
    role: Role
