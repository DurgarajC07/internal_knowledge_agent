"""End-to-end API test: register -> login -> chat -> list/get conversations,
against an in-memory-equivalent sqlite DB and fake LLM/embedding/vector/MCP
clients (Rule.md SS9: no live network calls, no real Qdrant/Ollama needed)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from urllib.parse import parse_qs, urlparse

import pytest
import respx
from httpx import ASGITransport, AsyncClient, Response
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

    test_settings = build_test_settings(
        google_drive_client_id="gd-client-id",
        google_drive_client_secret="gd-client-secret",
        notion_client_id="notion-client-id",
        notion_client_secret="notion-client-secret",
    )
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


async def _register_admin(client: AsyncClient, email: str) -> dict[str, str]:
    resp = await client.post(
        "/api/auth/register",
        json={"tenant_name": "Acme", "email": email, "password": "correct-horse-battery"},
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_connectors_list_shows_nothing_connected_initially(client: AsyncClient) -> None:
    headers = await _register_admin(client, "admin1@acmelawpartners.com")
    resp = await client.get("/api/connectors", headers=headers)
    assert resp.status_code == 200
    statuses = {s["provider"]: s["connected"] for s in resp.json()}
    assert statuses == {"google_drive": False, "notion": False}


async def test_connector_authorize_returns_a_google_url(client: AsyncClient) -> None:
    headers = await _register_admin(client, "admin2@acmelawpartners.com")
    resp = await client.get("/api/connectors/google_drive/authorize", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["authorize_url"].startswith("https://accounts.google.com/")


async def test_connector_callback_rejects_a_forged_state(client: AsyncClient) -> None:
    # The callback itself is intentionally unauthenticated (a browser
    # redirect from Google/Notion has no Bearer header) -- tenant identity
    # must come only from a verified `state` token, so a forged one is
    # rejected outright with no session required to prove it.
    resp = await client.get(
        "/api/connectors/google_drive/callback",
        params={"code": "irrelevant", "state": "not-a-real-token"},
    )
    assert resp.status_code == 401


@respx.mock
async def test_connector_full_oauth_round_trip_connects_and_lists_as_connected(
    client: AsyncClient,
) -> None:
    headers = await _register_admin(client, "admin4@acmelawpartners.com")

    authorize_resp = await client.get("/api/connectors/google_drive/authorize", headers=headers)
    authorize_url = authorize_resp.json()["authorize_url"]
    state = parse_qs(urlparse(authorize_url).query)["state"][0]

    respx.post("https://oauth2.googleapis.com/token").mock(
        return_value=Response(200, json={"access_token": "gd-tok", "scope": "drive.readonly"})
    )

    callback_resp = await client.get(
        "/api/connectors/google_drive/callback",
        params={"code": "auth-code", "state": state},
        follow_redirects=False,
    )
    assert callback_resp.status_code in (302, 307)
    assert "connected=google_drive" in callback_resp.headers["location"]

    statuses = {
        s["provider"]: s["connected"]
        for s in (await client.get("/api/connectors", headers=headers)).json()
    }
    assert statuses["google_drive"] is True


async def test_connector_sync_enqueues_a_job_without_running_ingestion(client: AsyncClient) -> None:
    """The route must only ever insert a row -- never run the ingestion
    pipeline in-process (Rule R-1). Admin-only enforcement itself is unit-
    tested in tests/unit/apps/test_connectors_usecase.py, since the public
    API has no way to create a non-admin user to exercise it here."""
    headers = await _register_admin(client, "admin5@acmelawpartners.com")
    resp = await client.post("/api/connectors/google_drive/sync", headers=headers)
    assert resp.status_code == 201
    job = resp.json()
    assert job["status"] == "pending"
    assert job["source"] == "google_drive"

    jobs_resp = await client.get("/api/connectors/jobs", headers=headers)
    assert jobs_resp.status_code == 200
    assert len(jobs_resp.json()) == 1
