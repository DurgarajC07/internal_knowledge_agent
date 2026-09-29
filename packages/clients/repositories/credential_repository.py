"""Tenant-scoped, encrypted OAuth credential storage. Every method requires a
tenant_id argument — there is no code path that can read/write a credential
without one (Rule.md SS7/SS8). Decryption happens only here, at call time,
never logged (Rule.md SS3)."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.clients import crypto
from packages.clients.db_models import ConnectorCredentialORM
from packages.config.logging import get_logger
from packages.core.enums import ConnectorProvider
from packages.core.exceptions import CredentialNotFoundError
from packages.core.schemas.tenant_credentials import ConnectorCredential

logger = get_logger(__name__)


class CredentialReader(Protocol):
    """What packages/clients/mcp_client.py actually depends on — lets tests
    substitute an in-memory fake instead of a real DB session (Rule R-3)."""

    async def get(self, tenant_id: UUID, provider: ConnectorProvider) -> ConnectorCredential: ...


class CredentialReadWriter(CredentialReader, Protocol):
    """What apps/api/usecases/connectors.py depends on — the OAuth callback
    writes a credential, and the connector-status endpoint lists which
    providers are connected for a tenant."""

    async def upsert(self, tenant_id: UUID, credential: ConnectorCredential) -> None: ...

    async def list_providers(self, tenant_id: UUID) -> list[ConnectorProvider]: ...


class CredentialRepository:
    def __init__(self, session: AsyncSession, encryption_key: str) -> None:
        self._session = session
        self._encryption_key = encryption_key

    async def get(self, tenant_id: UUID, provider: ConnectorProvider) -> ConnectorCredential:
        row = await self._session.get(ConnectorCredentialORM, (tenant_id, provider.value))
        found = row is not None
        logger.info(
            "credential.access",
            tenant_id=str(tenant_id),
            provider=provider.value,
            action="get",
            success=found,
        )
        if row is None:
            raise CredentialNotFoundError(f"No {provider.value} credential for tenant {tenant_id}")
        payload = crypto.decrypt(self._encryption_key, row.encrypted_payload)
        return ConnectorCredential.model_validate_json(payload)

    async def upsert(self, tenant_id: UUID, credential: ConnectorCredential) -> None:
        payload = credential.model_dump_json().encode("utf-8")
        encrypted = crypto.encrypt(self._encryption_key, payload)

        row = await self._session.get(
            ConnectorCredentialORM, (tenant_id, credential.provider.value)
        )
        if row is None:
            row = ConnectorCredentialORM(
                tenant_id=tenant_id,
                provider=credential.provider.value,
                encrypted_payload=encrypted,
                scopes=credential.scopes,
            )
            self._session.add(row)
        else:
            row.encrypted_payload = encrypted
            row.scopes = credential.scopes
        await self._session.flush()
        logger.info(
            "credential.access",
            tenant_id=str(tenant_id),
            provider=credential.provider.value,
            action="upsert",
            success=True,
        )

    async def list_providers(self, tenant_id: UUID) -> list[ConnectorProvider]:
        rows = await self._session.scalars(
            select(ConnectorCredentialORM.provider).where(
                ConnectorCredentialORM.tenant_id == tenant_id
            )
        )
        return [ConnectorProvider(value) for value in rows]

    async def list_tenants_with_credential(self, provider: ConnectorProvider) -> list[UUID]:
        """Used by services/ingestion/scheduler.py to find every tenant whose
        connector needs a periodic re-sync (FR-6) — never used on the
        request path."""
        rows = await self._session.scalars(
            select(ConnectorCredentialORM.tenant_id).where(
                ConnectorCredentialORM.provider == provider.value
            )
        )
        return list(rows)
