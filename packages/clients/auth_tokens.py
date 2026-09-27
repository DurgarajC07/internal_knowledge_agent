"""JWT issuing/verification via a vetted library (pyjwt) — never home-rolled
session tokens (Rule.md SS3, Plan.md SS11)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt

from packages.core.enums import Role
from packages.core.exceptions import AuthenticationError
from packages.core.schemas.auth import SessionUser


def create_access_token(
    user: SessionUser, *, secret_key: str, algorithm: str, expires_minutes: int
) -> str:
    now = datetime.now(UTC)
    payload = {
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

    try:
        return SessionUser(
            user_id=payload["sub"],
            tenant_id=payload["tenant_id"],
            email=payload["email"],
            role=Role(payload["role"]),
        )
    except (KeyError, ValueError) as exc:
        raise AuthenticationError("Session token payload is malformed") from exc
