from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from packages.core.enums import ConnectorProvider


class ConnectorCredential(BaseModel):
    """Decrypted, in-memory-only view of one tenant's OAuth credential.

    Never logged, never serialized back to a client. Encrypted at rest keyed by
    (tenant_id, provider); decrypted only inside the MCP client at call time,
    scoped to the current request's tenant (Rule.md SS7, Plan.md SS2 Q7).
    """

    model_config = ConfigDict(extra="forbid")

    tenant_id: UUID
    provider: ConnectorProvider
    access_token: str
    refresh_token: str | None = None
    scopes: list[str]
    expires_at: datetime | None = None


class ConnectorCredentialRecord(BaseModel):
    """What is actually stored in Postgres: the encrypted payload only."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: UUID
    provider: ConnectorProvider
    encrypted_payload: bytes
    scopes: list[str]
    created_at: datetime
    updated_at: datetime
