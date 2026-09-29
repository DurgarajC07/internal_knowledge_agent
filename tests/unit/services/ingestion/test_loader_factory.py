from pathlib import Path
from uuid import uuid4

import pytest

from packages.core.enums import ConnectorProvider
from packages.core.exceptions import CredentialNotFoundError
from packages.core.schemas.tenant_credentials import ConnectorCredential
from services.ingestion.loader_factory import build_loader
from services.ingestion.loaders.google_drive_loader import GoogleDriveLoader
from services.ingestion.loaders.local_file_loader import LocalFileLoader
from services.ingestion.loaders.notion_loader import NotionLoader
from tests.conftest import build_test_settings
from tests.fakes import FakeCredentialRepository


async def test_build_loader_local_requires_path() -> None:
    with pytest.raises(ValueError, match="local_path"):
        await build_loader(
            "local",
            uuid4(),
            settings=build_test_settings(),
            credential_repository=FakeCredentialRepository({}),
        )


async def test_build_loader_local_returns_local_file_loader(tmp_path: Path) -> None:
    loader = await build_loader(
        "local",
        uuid4(),
        settings=build_test_settings(),
        credential_repository=FakeCredentialRepository({}),
        local_path=tmp_path,
    )
    assert isinstance(loader, LocalFileLoader)


async def test_build_loader_google_drive_uses_stored_credential() -> None:
    tenant_id = uuid4()
    repo = FakeCredentialRepository(
        {
            (tenant_id, ConnectorProvider.GOOGLE_DRIVE): ConnectorCredential(
                tenant_id=tenant_id,
                provider=ConnectorProvider.GOOGLE_DRIVE,
                access_token="tok",
                scopes=[],
            )
        }
    )
    loader = await build_loader(
        "google_drive", tenant_id, settings=build_test_settings(), credential_repository=repo
    )
    assert isinstance(loader, GoogleDriveLoader)


async def test_build_loader_notion_uses_stored_credential() -> None:
    tenant_id = uuid4()
    repo = FakeCredentialRepository(
        {
            (tenant_id, ConnectorProvider.NOTION): ConnectorCredential(
                tenant_id=tenant_id,
                provider=ConnectorProvider.NOTION,
                access_token="tok",
                scopes=[],
            )
        }
    )
    loader = await build_loader(
        "notion", tenant_id, settings=build_test_settings(), credential_repository=repo
    )
    assert isinstance(loader, NotionLoader)


async def test_build_loader_raises_when_credential_missing() -> None:
    with pytest.raises(CredentialNotFoundError):
        await build_loader(
            "google_drive",
            uuid4(),
            settings=build_test_settings(),
            credential_repository=FakeCredentialRepository({}),
        )


async def test_build_loader_rejects_unknown_source() -> None:
    with pytest.raises(ValueError, match="Unsupported"):
        await build_loader(
            "dropbox",
            uuid4(),
            settings=build_test_settings(),
            credential_repository=FakeCredentialRepository({}),
        )
