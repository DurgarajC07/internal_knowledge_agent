"""Signup/login use-cases. Route handlers call exactly one of these functions
each (Rule.md SS3) — no password/JWT logic lives in apps/api/routes."""

from __future__ import annotations

from packages.clients.auth_tokens import create_access_token
from packages.clients.passwords import hash_password, verify_password
from packages.clients.repositories.user_repository import UserRepository
from packages.config.settings import Settings
from packages.core.exceptions import AuthenticationError, EmailAlreadyRegisteredError
from packages.core.schemas.auth import LoginRequest, RegisterRequest, SessionUser, TokenResponse


def _issue_token(session_user: SessionUser, settings: Settings) -> TokenResponse:
    token = create_access_token(
        session_user,
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
        expires_minutes=settings.jwt_expires_minutes,
    )
    return TokenResponse(access_token=token)


async def register(
    payload: RegisterRequest, *, user_repository: UserRepository, settings: Settings
) -> TokenResponse:
    if await user_repository.get_by_email(payload.email) is not None:
        raise EmailAlreadyRegisteredError(f"'{payload.email}' is already registered")

    record = await user_repository.register_tenant_with_admin(
        tenant_name=payload.tenant_name,
        admin_email=payload.email,
        hashed_password=hash_password(payload.password),
    )
    session_user = SessionUser(
        user_id=record.id, tenant_id=record.tenant_id, email=record.email, role=record.role
    )
    return _issue_token(session_user, settings)


async def login(
    payload: LoginRequest, *, user_repository: UserRepository, settings: Settings
) -> TokenResponse:
    record = await user_repository.get_by_email(payload.email)
    if record is None or not verify_password(payload.password, record.hashed_password):
        raise AuthenticationError("Invalid email or password")

    session_user = SessionUser(
        user_id=record.id, tenant_id=record.tenant_id, email=record.email, role=record.role
    )
    return _issue_token(session_user, settings)
