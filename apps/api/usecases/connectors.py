"""Connector OAuth connect flow + manual sync trigger (FR-6). Routes call
exactly one of these functions (Rule.md SS3) — the ingestion pipeline itself
never runs here, only a PENDING job row is created (Rule R-1);
services/ingestion/scheduler.py does the actual work."""

from __future__ import annotations

from dataclasses import dataclass

from packages.clients.auth_tokens import create_oauth_state_token, decode_oauth_state_token
from packages.clients.oauth_client import build_oauth_client
from packages.clients.repositories.credential_repository import CredentialReadWriter
from packages.clients.repositories.ingestion_job_repository import IngestionJobRepository
from packages.config.settings import Settings
from packages.core.enums import ConnectorProvider, Role
from packages.core.exceptions import AuthorizationError, OAuthStateInvalidError
from packages.core.schemas.connector import (
    ConnectorAuthorizeResponse,
    ConnectorStatus,
    IngestionJobOut,
)
from packages.core.schemas.tenant_credentials import ConnectorCredential
from packages.core.tenant_context import TenantContext


def _require_admin(tenant_ctx: TenantContext) -> None:
    if tenant_ctx.role != Role.ADMIN:
        raise AuthorizationError("Only a tenant admin can manage connectors")


def _callback_redirect_uri(settings: Settings, provider: ConnectorProvider) -> str:
    return f"{settings.api_base_url}/api/connectors/{provider.value}/callback"


async def start_authorize(
    provider: ConnectorProvider, *, tenant_ctx: TenantContext, settings: Settings
) -> ConnectorAuthorizeResponse:
    _require_admin(tenant_ctx)
    oauth_client = build_oauth_client(provider, settings)
    state = create_oauth_state_token(
        tenant_id=tenant_ctx.tenant_id,
        user_id=tenant_ctx.user_id,
        provider=provider,
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    url = oauth_client.build_authorize_url(
        state=state, redirect_uri=_callback_redirect_uri(settings, provider)
    )
    return ConnectorAuthorizeResponse(authorize_url=url)


@dataclass(frozen=True)
class OAuthCallbackResult:
    provider: ConnectorProvider
    redirect_url: str


async def complete_authorize(
    provider: ConnectorProvider,
    *,
    code: str,
    state: str,
    settings: Settings,
    credential_repository: CredentialReadWriter,
) -> OAuthCallbackResult:
    """The callback is an unauthenticated browser redirect from the
    provider — tenant identity comes only from the verified `state` token,
    never from a trusted query parameter (Rule.md SS6)."""
    oauth_state = decode_oauth_state_token(
        state, secret_key=settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )
    if oauth_state.provider != provider:
        raise OAuthStateInvalidError("OAuth state does not match the callback provider")

    oauth_client = build_oauth_client(provider, settings)
    token_response = await oauth_client.exchange_code(
        code=code, redirect_uri=_callback_redirect_uri(settings, provider)
    )

    credential = ConnectorCredential(
        tenant_id=oauth_state.tenant_id,
        provider=provider,
        access_token=token_response.access_token,
        refresh_token=token_response.refresh_token,
        scopes=token_response.scopes,
    )
    await credential_repository.upsert(oauth_state.tenant_id, credential)

    redirect_url = f"{settings.frontend_base_url}/settings/connectors?connected={provider.value}"
    return OAuthCallbackResult(provider=provider, redirect_url=redirect_url)


async def list_statuses(
    *,
    tenant_ctx: TenantContext,
    credential_repository: CredentialReadWriter,
    settings: Settings,
) -> list[ConnectorStatus]:
    connected = set(await credential_repository.list_providers(tenant_ctx.tenant_id))
    configured = {
        ConnectorProvider.GOOGLE_DRIVE: bool(
            settings.google_drive_client_id and settings.google_drive_client_secret
        ),
        ConnectorProvider.NOTION: bool(settings.notion_client_id and settings.notion_client_secret),
    }
    return [
        ConnectorStatus(
            provider=provider,
            connected=provider in connected,
            configured=configured[provider],
        )
        for provider in ConnectorProvider
    ]


async def trigger_sync(
    provider: ConnectorProvider,
    *,
    tenant_ctx: TenantContext,
    ingestion_job_repository: IngestionJobRepository,
) -> IngestionJobOut:
    """Enqueues a job row only — never calls services/ingestion in-process
    (Rule R-1, AGENT.md SS2.1). services/ingestion/scheduler.py picks it up
    on its next scheduled run."""
    _require_admin(tenant_ctx)
    return await ingestion_job_repository.create_pending(tenant_ctx.tenant_id, provider.value)


async def list_jobs(
    *, tenant_ctx: TenantContext, ingestion_job_repository: IngestionJobRepository
) -> list[IngestionJobOut]:
    return await ingestion_job_repository.list_for_tenant(tenant_ctx.tenant_id)
