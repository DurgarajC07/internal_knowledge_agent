from uuid import uuid4

import pytest
import respx
from httpx import Response

from apps.api.usecases import connectors as connectors_usecase
from packages.clients.auth_tokens import create_oauth_state_token
from packages.core.enums import ConnectorProvider, Role
from packages.core.exceptions import AuthorizationError, OAuthStateInvalidError
from packages.core.schemas.tenant_credentials import ConnectorCredential
from packages.core.tenant_context import TenantContext
from tests.conftest import build_test_settings
from tests.fakes import FakeCredentialRepository


def _settings():
    return build_test_settings(
        google_drive_client_id="gd-id",
        google_drive_client_secret="gd-secret",
        notion_client_id="notion-id",
        notion_client_secret="notion-secret",
        jwt_secret_key="test-secret-key-for-connectors",
    )


def _admin_ctx(tenant_id=None, user_id=None) -> TenantContext:
    return TenantContext(
        tenant_id=tenant_id or uuid4(), user_id=user_id or uuid4(), role=Role.ADMIN
    )


def _member_ctx() -> TenantContext:
    return TenantContext(tenant_id=uuid4(), user_id=uuid4(), role=Role.MEMBER)


async def test_start_authorize_rejects_non_admin() -> None:
    with pytest.raises(AuthorizationError):
        await connectors_usecase.start_authorize(
            ConnectorProvider.GOOGLE_DRIVE, tenant_ctx=_member_ctx(), settings=_settings()
        )


async def test_start_authorize_returns_a_url_carrying_a_verifiable_state() -> None:
    tenant_ctx = _admin_ctx()
    result = await connectors_usecase.start_authorize(
        ConnectorProvider.GOOGLE_DRIVE, tenant_ctx=tenant_ctx, settings=_settings()
    )
    assert result.authorize_url.startswith("https://accounts.google.com/")
    assert "state=" in result.authorize_url


@respx.mock
async def test_complete_authorize_stores_credential_for_the_tenant_in_the_state() -> None:
    settings = _settings()
    tenant_ctx = _admin_ctx()
    state = create_oauth_state_token(
        tenant_id=tenant_ctx.tenant_id,
        user_id=tenant_ctx.user_id,
        provider=ConnectorProvider.GOOGLE_DRIVE,
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    respx.post("https://oauth2.googleapis.com/token").mock(
        return_value=Response(200, json={"access_token": "gd-token", "scope": "drive.readonly"})
    )
    repo = FakeCredentialRepository({})

    result = await connectors_usecase.complete_authorize(
        ConnectorProvider.GOOGLE_DRIVE,
        code="auth-code",
        state=state,
        settings=settings,
        credential_repository=repo,
    )

    assert result.provider == ConnectorProvider.GOOGLE_DRIVE
    assert "connected=google_drive" in result.redirect_url
    stored = await repo.get(tenant_ctx.tenant_id, ConnectorProvider.GOOGLE_DRIVE)
    assert stored.access_token == "gd-token"


async def test_complete_authorize_rejects_a_state_issued_for_a_different_provider() -> None:
    """A state token minted for Notion must not be usable against the Google
    Drive callback, even if the code/signature are otherwise valid — proves
    the provider itself is bound into the signed state, not just trusted from
    the URL path (Rule.md SS6)."""
    settings = _settings()
    tenant_ctx = _admin_ctx()
    state = create_oauth_state_token(
        tenant_id=tenant_ctx.tenant_id,
        user_id=tenant_ctx.user_id,
        provider=ConnectorProvider.NOTION,
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(OAuthStateInvalidError):
        await connectors_usecase.complete_authorize(
            ConnectorProvider.GOOGLE_DRIVE,
            code="auth-code",
            state=state,
            settings=settings,
            credential_repository=FakeCredentialRepository({}),
        )


async def test_complete_authorize_rejects_a_tampered_state() -> None:
    settings = _settings()
    with pytest.raises(OAuthStateInvalidError):
        await connectors_usecase.complete_authorize(
            ConnectorProvider.GOOGLE_DRIVE,
            code="auth-code",
            state="not-a-real-token",
            settings=settings,
            credential_repository=FakeCredentialRepository({}),
        )


async def test_trigger_sync_rejects_non_admin() -> None:
    # The admin check raises before ingestion_job_repository is ever touched,
    # so a type-incompatible placeholder is fine here — never reached.
    with pytest.raises(AuthorizationError):
        await connectors_usecase.trigger_sync(
            ConnectorProvider.GOOGLE_DRIVE,
            tenant_ctx=_member_ctx(),
            ingestion_job_repository=None,  # type: ignore[arg-type]
        )


async def test_list_statuses_reports_connected_providers() -> None:
    tenant_ctx = _admin_ctx()
    repo = FakeCredentialRepository({})

    await repo.upsert(
        tenant_ctx.tenant_id,
        ConnectorCredential(
            tenant_id=tenant_ctx.tenant_id,
            provider=ConnectorProvider.NOTION,
            access_token="tok",
            scopes=[],
        ),
    )

    statuses = await connectors_usecase.list_statuses(
        tenant_ctx=tenant_ctx, credential_repository=repo, settings=_settings()
    )

    by_provider = {s.provider: s.connected for s in statuses}
    assert by_provider[ConnectorProvider.NOTION] is True
    assert by_provider[ConnectorProvider.GOOGLE_DRIVE] is False
    assert all(status.configured for status in statuses)
