import respx
from httpx import Response

from packages.clients.oauth_client import (
    GoogleDriveOAuthClient,
    NotionOAuthClient,
    build_oauth_client,
)
from packages.core.enums import ConnectorProvider
from packages.core.exceptions import OAuthConfigurationError
from tests.conftest import build_test_settings


def test_google_drive_authorize_url_requests_readonly_scope_and_offline_access() -> None:
    client = GoogleDriveOAuthClient("client-id", "client-secret")
    url = client.build_authorize_url(state="abc", redirect_uri="https://api.example.com/cb")

    assert "client_id=client-id" in url
    assert "drive.readonly" in url
    assert "access_type=offline" in url
    assert "state=abc" in url


@respx.mock
async def test_google_drive_exchange_code_returns_tokens() -> None:
    respx.post("https://oauth2.googleapis.com/token").mock(
        return_value=Response(
            200,
            json={
                "access_token": "gd-access",
                "refresh_token": "gd-refresh",
                "scope": "https://www.googleapis.com/auth/drive.readonly",
            },
        )
    )
    client = GoogleDriveOAuthClient("client-id", "client-secret")
    result = await client.exchange_code(code="auth-code", redirect_uri="https://api.example.com/cb")

    assert result.access_token == "gd-access"
    assert result.refresh_token == "gd-refresh"
    assert result.scopes == ["https://www.googleapis.com/auth/drive.readonly"]


def test_notion_authorize_url_requests_user_owner() -> None:
    client = NotionOAuthClient("client-id", "client-secret")
    url = client.build_authorize_url(state="xyz", redirect_uri="https://api.example.com/cb")

    assert "owner=user" in url
    assert "state=xyz" in url


@respx.mock
async def test_notion_exchange_code_returns_tokens_with_no_refresh() -> None:
    respx.post("https://api.notion.com/v1/oauth/token").mock(
        return_value=Response(200, json={"access_token": "notion-access"})
    )
    client = NotionOAuthClient("client-id", "client-secret")
    result = await client.exchange_code(code="auth-code", redirect_uri="https://api.example.com/cb")

    assert result.access_token == "notion-access"
    assert result.refresh_token is None


def test_build_oauth_client_raises_when_provider_not_configured() -> None:
    settings = build_test_settings(google_drive_client_id=None, google_drive_client_secret=None)
    try:
        build_oauth_client(ConnectorProvider.GOOGLE_DRIVE, settings)
    except OAuthConfigurationError:
        pass
    else:
        raise AssertionError("expected OAuthConfigurationError when client id/secret are unset")


def test_build_oauth_client_succeeds_when_configured() -> None:
    settings = build_test_settings(google_drive_client_id="id", google_drive_client_secret="secret")
    client = build_oauth_client(ConnectorProvider.GOOGLE_DRIVE, settings)
    assert isinstance(client, GoogleDriveOAuthClient)
