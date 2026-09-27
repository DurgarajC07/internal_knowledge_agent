from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from packages.clients.db import Base, build_session_factory
from packages.clients.repositories.credential_repository import CredentialRepository
from packages.core.enums import ConnectorProvider
from packages.core.exceptions import CredentialNotFoundError
from packages.core.schemas.tenant_credentials import ConnectorCredential

_TEST_KEY = "wZ0nQ3z6r6t2c8m0y6q0k0k3m4h9j1p6y6b3z8t5u4o="


@pytest.fixture
async def session():
    # sqlite in-memory: no network, no file left on disk (Rule.md SS9).
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = build_session_factory(engine)
    async with factory() as session:
        yield session
    await engine.dispose()


async def test_get_raises_when_no_credential_stored(session) -> None:
    repo = CredentialRepository(session, _TEST_KEY)
    with pytest.raises(CredentialNotFoundError):
        await repo.get(uuid4(), ConnectorProvider.GOOGLE_DRIVE)


async def test_upsert_then_get_roundtrips_decrypted_credential(session) -> None:
    tenant_id = uuid4()
    repo = CredentialRepository(session, _TEST_KEY)
    credential = ConnectorCredential(
        tenant_id=tenant_id,
        provider=ConnectorProvider.GOOGLE_DRIVE,
        access_token="secret-access-token",
        refresh_token="secret-refresh-token",
        scopes=["drive.readonly"],
    )

    await repo.upsert(tenant_id, credential)
    fetched = await repo.get(tenant_id, ConnectorProvider.GOOGLE_DRIVE)

    assert fetched.access_token == "secret-access-token"
    assert fetched.scopes == ["drive.readonly"]


async def test_upsert_twice_overwrites_rather_than_duplicates(session) -> None:
    tenant_id = uuid4()
    repo = CredentialRepository(session, _TEST_KEY)
    await repo.upsert(
        tenant_id,
        ConnectorCredential(
            tenant_id=tenant_id,
            provider=ConnectorProvider.NOTION,
            access_token="old-token",
            scopes=[],
        ),
    )
    await repo.upsert(
        tenant_id,
        ConnectorCredential(
            tenant_id=tenant_id,
            provider=ConnectorProvider.NOTION,
            access_token="new-token",
            scopes=[],
        ),
    )

    fetched = await repo.get(tenant_id, ConnectorProvider.NOTION)
    assert fetched.access_token == "new-token"


async def test_credential_encrypted_payload_is_not_plaintext(session) -> None:
    tenant_id = uuid4()
    repo = CredentialRepository(session, _TEST_KEY)
    await repo.upsert(
        tenant_id,
        ConnectorCredential(
            tenant_id=tenant_id,
            provider=ConnectorProvider.GOOGLE_DRIVE,
            access_token="super-secret-value",
            scopes=[],
        ),
    )

    from packages.clients.db_models import ConnectorCredentialORM

    row = await session.get(
        ConnectorCredentialORM, (tenant_id, ConnectorProvider.GOOGLE_DRIVE.value)
    )
    assert b"super-secret-value" not in row.encrypted_payload
