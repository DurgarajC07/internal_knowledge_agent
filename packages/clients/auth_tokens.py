"""JWT issuing/verification via a vetted library (pyjwt) — never home-rolled
session tokens (Rule.md SS3, Plan.md SS11).

Two distinct, non-interchangeable token kinds are signed with the same
secret: `session` (issued at login, read by apps/api/dependencies.py) and
`oauth_state` (issued when an admin starts a connector OAuth flow, verified
on the callback). Each carries a `typ` claim and is rejected by the other's
decoder — without this, a stolen `oauth_state` token (which only needs to
survive a few minutes in a URL) could otherwise be replayed as a session
token, or vice versa.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

from packages.core.enums import ConnectorProvider, Role
from packages.core.exceptions import AuthenticationError, OAuthStateInvalidError
from packages.core.schemas.auth import SessionUser

_SESSION_TOKEN_TYPE = "session"
_OAUTH_STATE_TOKEN_TYPE = "oauth_state"
_OAUTH_STATE_EXPIRES_MINUTES = 10


def create_access_token(
    user: SessionUser, *, secret_key: str, algorithm: str, expires_minutes: int
) -> str:
    now = datetime.now(UTC)
    payload = {
        "typ": _SESSION_TOKEN_TYPE,
        "sub": str(user.user_id),
        "tenant_id": str(user.tenant_id),
        "email": user.email,
        "role": user.role.value,
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, secret_key, algorithm=algorithm)


def decode_access_token(token: str, *, secret_key: str, algorithm: str) -> SessionUser:
    try:
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid or expired session token") from exc

    if payload.get("typ") != _SESSION_TOKEN_TYPE:
        raise AuthenticationError("Token is not a session token")

    try:
        return SessionUser(
            user_id=payload["sub"],
            tenant_id=payload["tenant_id"],
            email=payload["email"],
            role=Role(payload["role"]),
        )
    except (KeyError, ValueError) as exc:
        raise AuthenticationError("Session token payload is malformed") from exc


@dataclass(frozen=True)
class OAuthState:
    tenant_id: UUID
    user_id: UUID
    provider: ConnectorProvider


def create_oauth_state_token(
    *,
    tenant_id: UUID,
    user_id: UUID,
    provider: ConnectorProvider,
    secret_key: str,
    algorithm: str,
) -> str:
    """Binds an OAuth callback back to the tenant/user that started it,
    without a DB round-trip — the callback is an unauthenticated browser
    redirect, so tenant identity can only come from a verified signature,
    never a trusted query parameter (Rule.md SS6, AGENT.md SS7)."""
    now = datetime.now(UTC)
    payload = {
        "typ": _OAUTH_STATE_TOKEN_TYPE,
        "tenant_id": str(tenant_id),
        "user_id": str(user_id),
        "provider": provider.value,
        "iat": now,
        "exp": now + timedelta(minutes=_OAUTH_STATE_EXPIRES_MINUTES),
    }
    return jwt.encode(payload, secret_key, algorithm=algorithm)


def decode_oauth_state_token(token: str, *, secret_key: str, algorithm: str) -> OAuthState:
    try:
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
    except jwt.PyJWTError as exc:
        raise OAuthStateInvalidError("OAuth state is invalid or expired") from exc

    if payload.get("typ") != _OAUTH_STATE_TOKEN_TYPE:
        raise OAuthStateInvalidError("Token is not an OAuth state token")

    try:
        return OAuthState(
            tenant_id=UUID(payload["tenant_id"]),
            user_id=UUID(payload["user_id"]),
            provider=ConnectorProvider(payload["provider"]),
        )
    except (KeyError, ValueError) as exc:
        raise OAuthStateInvalidError("OAuth state payload is malformed") from exc
