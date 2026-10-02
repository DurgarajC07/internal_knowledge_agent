"""FastAPI entrypoint. Builds every long-lived client once at startup (Rule
R-3: constructed only in packages/clients, injected everywhere else) and
exposes them via `app.state` for apps/api/dependencies.py to wrap."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.middleware.audit_log import AuditLogMiddleware
from apps.api.middleware.errors import register_exception_handlers
from apps.api.middleware.rate_limit import RateLimitMiddleware
from apps.api.routes import auth, chat, connectors, conversations, health
from packages.clients.db import build_engine, build_session_factory
from packages.clients.embedding_client import build_embedding_client
from packages.clients.llm_client import build_llm_client
from packages.clients.qdrant_client import build_qdrant_store
from packages.config.logging import configure_logging
from packages.config.settings import get_settings
from packages.core.enums import ConnectorProvider
from services.mcp_servers.google_drive.server import build_google_drive_server
from services.mcp_servers.notion.server import build_notion_server


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.environment)

    engine = build_engine(settings)
    app.state.session_factory = build_session_factory(engine)
    app.state.embedding_client = build_embedding_client(settings)
    app.state.vector_store = build_qdrant_store(settings)
    app.state.llm_client = build_llm_client(settings)
    app.state.mcp_servers = {
        ConnectorProvider.GOOGLE_DRIVE: build_google_drive_server(settings),
        ConnectorProvider.NOTION: build_notion_server(settings),
    }

    yield

    await app.state.vector_store.close()
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Knowledge Agent API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RateLimitMiddleware, requests_per_minute=settings.rate_limit_per_minute)
    app.add_middleware(AuditLogMiddleware)

    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(auth.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(conversations.router, prefix="/api")
    app.include_router(connectors.router, prefix="/api")
    return app


app = create_app()
