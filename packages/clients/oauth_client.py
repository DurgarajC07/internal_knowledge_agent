"""OAuth authorization-code clients for connector providers. The only module
allowed to construct these raw (Rule R-3) — apps/api/usecases/connectors.py
receives one via `build_oauth_client`, never talks to Google/Notion's OAuth
endpoints directly."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode

import httpx

from packages.config.settings import Settings
from packages.core.enums import ConnectorProvider
from packages.core.exceptions import OAuthConfigurationError, ToolExecutionError

_REQUEST_TIMEOUT_SECONDS = 15.0


@dataclass(frozen=True)
class OAuthTokenResponse:
    access_token: str
    refresh_token: str | None
    scopes: list[str]


class OAuthProviderClient(Protocol):
    def build_authorize_url(self, *, state: str, redirect_uri: str) -> str: ...

    async def exchange_code(self, *, code: str, redirect_uri: str) -> OAuthTokenResponse: ...


class GoogleDriveOAuthClient:
    """Minimum requested scope is read-only Drive access — least-privilege
    per Rule.md SS6/SS8."""

    _AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    _TOKEN_URL = "https://oauth2.googleapis.com/token"
    _SCOPES = ("https://www.googleapis.com/auth/drive.readonly",)

    def __init__(self, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret

    def build_authorize_url(self, *, state: str, redirect_uri: str) -> str:
        params = {
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(self._SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return f"{self._AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code(self, *, code: str, redirect_uri: str) -> OAuthTokenResponse:
        try:
            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
                resp = await client.post(
                    self._TOKEN_URL,
                    data={
                        "client_id": self._client_id,
                        "client_secret": self._client_secret,
                        "code": code,
                        "grant_type": "authorization_code",
                        "redirect_uri": redirect_uri,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            raise ToolExecutionError(f"Google OAuth code exchange failed: {exc}") from exc

        return OAuthTokenResponse(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            scopes=data.get("scope", "").split(),
        )


class NotionOAuthClient:
    _AUTHORIZE_URL = "https://api.notion.com/v1/oauth/authorize"
    _TOKEN_URL = "https://api.notion.com/v1/oauth/token"

    def __init__(self, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret

    def build_authorize_url(self, *, state: str, redirect_uri: str) -> str:
        params = {
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "owner": "user",
            "state": state,
        }
        return f"{self._AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code(self, *, code: str, redirect_uri: str) -> OAuthTokenResponse:
        try:
            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
                resp = await client.post(
                    self._TOKEN_URL,
                    json={
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": redirect_uri,
                    },
                    auth=(self._client_id, self._client_secret),
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            raise ToolExecutionError(f"Notion OAuth code exchange failed: {exc}") from exc

        # Notion access tokens don't expire and no refresh token is issued;
        # granular scopes aren't returned in the token response (the
        # workspace owner grants access at the page/database level in the
        # consent screen instead).
        return OAuthTokenResponse(access_token=data["access_token"], refresh_token=None, scopes=[])


def build_oauth_client(provider: ConnectorProvider, settings: Settings) -> OAuthProviderClient:
    if provider == ConnectorProvider.GOOGLE_DRIVE:
        if not settings.google_drive_client_id or not settings.google_drive_client_secret:
            raise OAuthConfigurationError("Google Drive OAuth client ID/secret is not configured")
        return GoogleDriveOAuthClient(
            settings.google_drive_client_id, settings.google_drive_client_secret
        )
    if provider == ConnectorProvider.NOTION:
        if not settings.notion_client_id or not settings.notion_client_secret:
            raise OAuthConfigurationError("Notion OAuth client ID/secret is not configured")
        return NotionOAuthClient(settings.notion_client_id, settings.notion_client_secret)
    raise OAuthConfigurationError(f"Unsupported OAuth provider: {provider}")
