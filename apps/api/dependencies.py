"""Every dependency the API needs, defined once (Rule.md SS3). Expensive
clients (LLM, embeddings, Qdrant, MCP servers, DB engine) are constructed once
at startup (see main.py's lifespan) and stored on `app.state`; these functions
only wrap them for injection — they never construct one themselves (Rule R-3).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from packages.clients.auth_tokens import decode_access_token
from packages.clients.embedding_client import EmbeddingClient
from packages.clients.llm_client import LLMClient
from packages.clients.mcp_client import MCPClient
from packages.clients.qdrant_client import VectorStore
from packages.clients.repositories.conversation_repository import ConversationRepository
from packages.clients.repositories.credential_repository import CredentialRepository
from packages.clients.repositories.user_repository import UserRepository
from packages.config.settings import Settings, get_settings
from packages.core.exceptions import AuthenticationError
from packages.core.schemas.auth import SessionUser
from packages.core.tenant_context import TenantContext


def get_settings_dep() -> Settings:
    return get_settings()


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


DbSession = Annotated[AsyncSession, Depends(get_db_session)]


def get_embedding_client(request: Request) -> EmbeddingClient:
    return request.app.state.embedding_client


def get_vector_store(request: Request) -> VectorStore:
    return request.app.state.vector_store


def get_llm_client(request: Request) -> LLMClient:
    return request.app.state.llm_client


def get_credential_repository(
    session: DbSession, settings: Annotated[Settings, Depends(get_settings_dep)]
) -> CredentialRepository:
    return CredentialRepository(session, settings.credential_encryption_key)


def get_mcp_client(
    request: Request,
    credential_repository: Annotated[CredentialRepository, Depends(get_credential_repository)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> MCPClient:
    return MCPClient(
        servers=request.app.state.mcp_servers,
        credential_repository=credential_repository,
        max_output_chars=settings.tool_output_max_chars,
    )


def get_conversation_repository(session: DbSession) -> ConversationRepository:
    return ConversationRepository(session)


def get_user_repository(session: DbSession) -> UserRepository:
    return UserRepository(session)


async def get_current_session_user(
    settings: Annotated[Settings, Depends(get_settings_dep)],
    authorization: Annotated[str | None, Header()] = None,
) -> SessionUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthenticationError("Missing or malformed Authorization header")
    token = authorization.split(" ", 1)[1]
    return decode_access_token(
        token, secret_key=settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def get_tenant_context(
    session_user: Annotated[SessionUser, Depends(get_current_session_user)],
) -> TenantContext:
    return TenantContext(
        tenant_id=session_user.tenant_id, user_id=session_user.user_id, role=session_user.role
    )
