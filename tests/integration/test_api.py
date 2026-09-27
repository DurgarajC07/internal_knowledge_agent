"""End-to-end API test: register -> login -> chat -> list/get conversations,
against an in-memory-equivalent sqlite DB and fake LLM/embedding/vector/MCP
clients (Rule.md SS9: no live network calls, no real Qdrant/Ollama needed)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from apps.api import dependencies as deps
from apps.api.main import create_app
from packages.clients.db import Base, build_session_factory
from packages.clients.llm_client import LLMResponse
from packages.clients.mcp_client import build_mcp_client
from tests.conftest import build_test_settings
from tests.fakes import FakeCredentialRepository, FakeEmbeddingClient, FakeVectorStore


class StubLLMClient:
    """Always answers directly with no tool call — enough to exercise the full
    HTTP -> use-case -> agent -> persistence path end to end."""

    async def generate(self, messages, *, system=None, tools=None) -> LLMResponse:
        return LLMResponse(
            text="Hello from the test double.", tool_calls=[], stop_reason="end_turn"
        )

    def stream(self, messages, *, system=None):
        raise NotImplementedError


@pytest.fixture
async def client(tmp_path) -> AsyncIterator[AsyncClient]:
    db_path = tmp_path / "test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = build_session_factory(engine)

    test_settings = build_test_settings()
    app = create_app()

    async def override_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[deps.get_settings_dep] = lambda: test_settings
    app.dependency_overrides[deps.get_db_session] = override_db_session
    app.dependency_overrides[deps.get_llm_client] = lambda: StubLLMClient()
    app.dependency_overrides[deps.get_embedding_client] = lambda: FakeEmbeddingClient()
    app.dependency_overrides[deps.get_vector_store] = lambda: FakeVectorStore()
    app.dependency_overrides[deps.get_mcp_client] = lambda: build_mcp_client(
        test_settings, FakeCredentialRepository({})
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client

    await engine.dispose()


async def test_register_then_login_then_chat_end_to_end(client: AsyncClient) -> None:
    register_resp = await client.post(
        "/api/auth/register",
        json={
            "tenant_name": "Acme Law Partners",
            "email": "admin@acmelawpartners.com",
            "password": "correct-horse-battery",
        },
    )
    assert register_resp.status_code == 201
    token = register_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    login_resp = await client.post(
        "/api/auth/login",
        json={"email": "admin@acmelawpartners.com", "password": "correct-horse-battery"},
    )
    assert login_resp.status_code == 200

    chat_resp = await client.post("/api/chat", json={"message": "hello"}, headers=headers)
    assert chat_resp.status_code == 200
    body = chat_resp.text
    assert "Hello" in body and "test" in body and "double." in body
    assert '"type":"done"' in body

    conversations_resp = await client.get("/api/conversations", headers=headers)
    assert conversations_resp.status_code == 200
    conversations = conversations_resp.json()
    assert len(conversations) == 1

    detail_resp = await client.get(f"/api/conversations/{conversations[0]['id']}", headers=headers)
    assert detail_resp.status_code == 200
    messages = detail_resp.json()["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[1]["content"] == "Hello from the test double."


async def test_chat_without_auth_is_rejected(client: AsyncClient) -> None:
    resp = await client.post("/api/chat", json={"message": "hello"})
    assert resp.status_code == 401


async def test_register_rejects_duplicate_email(client: AsyncClient) -> None:
    payload = {
        "tenant_name": "Acme",
        "email": "dup@acmelawpartners.com",
        "password": "correct-horse-battery",
    }
    first = await client.post("/api/auth/register", json=payload)
    assert first.status_code == 201
    second = await client.post("/api/auth/register", json=payload)
    assert second.status_code == 409


async def test_login_with_wrong_password_is_rejected(client: AsyncClient) -> None:
    await client.post(
        "/api/auth/register",
        json={
            "tenant_name": "Acme",
            "email": "user@acmelawpartners.com",
            "password": "correct-horse-battery",
        },
    )
    resp = await client.post(
        "/api/auth/login",
        json={"email": "user@acmelawpartners.com", "password": "wrong-password"},
    )
    assert resp.status_code == 401


async def test_cross_tenant_conversation_access_is_blocked(client: AsyncClient) -> None:
    tenant_a = await client.post(
        "/api/auth/register",
        json={"tenant_name": "Tenant A", "email": "a@tenanta.com", "password": "password123"},
    )
    tenant_b = await client.post(
        "/api/auth/register",
        json={"tenant_name": "Tenant B", "email": "b@tenantb.com", "password": "password123"},
    )
    headers_a = {"Authorization": f"Bearer {tenant_a.json()['access_token']}"}
    headers_b = {"Authorization": f"Bearer {tenant_b.json()['access_token']}"}

    await client.post("/api/chat", json={"message": "hello from A"}, headers=headers_a)
    conversations_a = (await client.get("/api/conversations", headers=headers_a)).json()
    conversation_id = conversations_a[0]["id"]

    # Tenant B must not be able to read Tenant A's conversation by ID (Rule.md SS7).
    resp = await client.get(f"/api/conversations/{conversation_id}", headers=headers_b)
    assert resp.status_code == 404
