"""Connector connect/sync routes (FR-6). `/callback` is intentionally the one
route in this file with no `get_tenant_context` dependency — it's an
unauthenticated browser redirect from the OAuth provider; tenant identity
comes only from the verified `state` token inside the use-case, never from a
trusted query parameter (Rule.md SS6)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse

from apps.api import dependencies as deps
from apps.api.usecases import connectors as connectors_usecase
from packages.clients.repositories.credential_repository import CredentialRepository
from packages.clients.repositories.ingestion_job_repository import IngestionJobRepository
from packages.config.settings import Settings
from packages.core.enums import ConnectorProvider
from packages.core.schemas.connector import (
    ConnectorAuthorizeResponse,
    ConnectorStatus,
    IngestionJobOut,
)
from packages.core.tenant_context import TenantContext

router = APIRouter(prefix="/connectors", tags=["connectors"])


@router.get("", response_model=list[ConnectorStatus])
async def list_connectors(
    tenant_ctx: Annotated[TenantContext, Depends(deps.get_tenant_context)],
    credential_repository: Annotated[CredentialRepository, Depends(deps.get_credential_repository)],
) -> list[ConnectorStatus]:
    return await connectors_usecase.list_statuses(
        tenant_ctx=tenant_ctx, credential_repository=credential_repository
    )


@router.get("/{provider}/authorize", response_model=ConnectorAuthorizeResponse)
async def authorize(
    provider: ConnectorProvider,
    tenant_ctx: Annotated[TenantContext, Depends(deps.get_tenant_context)],
    settings: Annotated[Settings, Depends(deps.get_settings_dep)],
) -> ConnectorAuthorizeResponse:
    return await connectors_usecase.start_authorize(
        provider, tenant_ctx=tenant_ctx, settings=settings
    )


@router.get("/{provider}/callback")
async def callback(
    provider: ConnectorProvider,
    code: str,
    state: str,
    credential_repository: Annotated[CredentialRepository, Depends(deps.get_credential_repository)],
    settings: Annotated[Settings, Depends(deps.get_settings_dep)],
) -> RedirectResponse:
    result = await connectors_usecase.complete_authorize(
        provider,
        code=code,
        state=state,
        settings=settings,
        credential_repository=credential_repository,
    )
    return RedirectResponse(result.redirect_url)


@router.post("/{provider}/sync", response_model=IngestionJobOut, status_code=201)
async def sync_now(
    provider: ConnectorProvider,
    tenant_ctx: Annotated[TenantContext, Depends(deps.get_tenant_context)],
    ingestion_job_repository: Annotated[
        IngestionJobRepository, Depends(deps.get_ingestion_job_repository)
    ],
) -> IngestionJobOut:
    return await connectors_usecase.trigger_sync(
        provider, tenant_ctx=tenant_ctx, ingestion_job_repository=ingestion_job_repository
    )


@router.get("/jobs", response_model=list[IngestionJobOut])
async def list_jobs(
    tenant_ctx: Annotated[TenantContext, Depends(deps.get_tenant_context)],
    ingestion_job_repository: Annotated[
        IngestionJobRepository, Depends(deps.get_ingestion_job_repository)
    ],
) -> list[IngestionJobOut]:
    return await connectors_usecase.list_jobs(
        tenant_ctx=tenant_ctx, ingestion_job_repository=ingestion_job_repository
    )
