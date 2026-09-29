from uuid import uuid4

import jwt
import pytest

from packages.clients.auth_tokens import (
    create_access_token,
    create_oauth_state_token,
    decode_access_token,
    decode_oauth_state_token,
)
from packages.core.enums import ConnectorProvider, Role
from packages.core.exceptions import AuthenticationError, OAuthStateInvalidError
from packages.core.schemas.auth import SessionUser

_SECRET = "test-secret"
_ALGORITHM = "HS256"


def _make_session_user() -> SessionUser:
    return SessionUser(
        user_id=uuid4(), tenant_id=uuid4(), email="admin@acmelawpartners.com", role=Role.ADMIN
    )


def test_session_token_roundtrips() -> None:
    user = _make_session_user()
    token = create_access_token(user, secret_key=_SECRET, algorithm=_ALGORITHM, expires_minutes=60)
    decoded = decode_access_token(token, secret_key=_SECRET, algorithm=_ALGORITHM)
    assert decoded == user


def test_oauth_state_token_roundtrips() -> None:
    tenant_id, user_id = uuid4(), uuid4()
    token = create_oauth_state_token(
        tenant_id=tenant_id,
        user_id=user_id,
        provider=ConnectorProvider.GOOGLE_DRIVE,
        secret_key=_SECRET,
        algorithm=_ALGORITHM,
    )
    state = decode_oauth_state_token(token, secret_key=_SECRET, algorithm=_ALGORITHM)
    assert state.tenant_id == tenant_id
    assert state.user_id == user_id
    assert state.provider == ConnectorProvider.GOOGLE_DRIVE


def test_oauth_state_token_cannot_be_replayed_as_a_session_token() -> None:
    """A stolen OAuth state token (which only needs to survive a few minutes
    in a URL) must never double as a session token (Rule.md SS3/SS6)."""
    token = create_oauth_state_token(
        tenant_id=uuid4(),
        user_id=uuid4(),
        provider=ConnectorProvider.NOTION,
        secret_key=_SECRET,
        algorithm=_ALGORITHM,
    )
    with pytest.raises(AuthenticationError):
        decode_access_token(token, secret_key=_SECRET, algorithm=_ALGORITHM)


def test_session_token_cannot_be_replayed_as_an_oauth_state_token() -> None:
    token = create_access_token(
        _make_session_user(), secret_key=_SECRET, algorithm=_ALGORITHM, expires_minutes=60
    )
    with pytest.raises(OAuthStateInvalidError):
        decode_oauth_state_token(token, secret_key=_SECRET, algorithm=_ALGORITHM)


def test_oauth_state_token_rejects_tampered_provider() -> None:
    """A forged token targeting a different provider than it was issued for
    must be rejected by the callback's own cross-check — this test proves the
    signature itself is what's verified, not just the shape."""
    payload = {
        "typ": "oauth_state",
        "tenant_id": str(uuid4()),
        "user_id": str(uuid4()),
        "provider": "google_drive",
    }
    forged = jwt.encode(payload, "wrong-secret", algorithm=_ALGORITHM)
    with pytest.raises(OAuthStateInvalidError):
        decode_oauth_state_token(forged, secret_key=_SECRET, algorithm=_ALGORITHM)


def test_oauth_state_token_rejects_expired_token() -> None:
    from datetime import UTC, datetime, timedelta

    payload = {
        "typ": "oauth_state",
        "tenant_id": str(uuid4()),
        "user_id": str(uuid4()),
        "provider": "notion",
        "iat": datetime.now(UTC) - timedelta(minutes=20),
        "exp": datetime.now(UTC) - timedelta(minutes=10),
    }
    expired = jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)
    with pytest.raises(OAuthStateInvalidError):
        decode_oauth_state_token(expired, secret_key=_SECRET, algorithm=_ALGORITHM)
