"""Resolves the right DocumentLoader for a source, including fetching the
tenant's stored OAuth credential for connector sources (FR-6). Shared by
cli.py, worker.py, and scheduler.py so the resolution logic lives in exactly
one place."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from packages.clients.repositories.credential_repository import CredentialReader
from packages.config.settings import Settings
from packages.core.enums import ConnectorProvider
from services.ingestion.loaders.base import DocumentLoader
from services.ingestion.loaders.google_drive_loader import GoogleDriveLoader
from services.ingestion.loaders.local_file_loader import LocalFileLoader
from services.ingestion.loaders.notion_loader import NotionLoader
from services.mcp_servers.google_drive.client import GoogleDriveClient
from services.mcp_servers.notion.client import NotionClient

SUPPORTED_SOURCES = ("local", "google_drive", "notion")


async def build_loader(
    source: str,
    tenant_id: UUID,
    *,
    settings: Settings,
    credential_repository: CredentialReader,
    local_path: Path | None = None,
) -> DocumentLoader:
    if source == "local":
        if local_path is None:
            raise ValueError("local_path is required for source=local")
        return LocalFileLoader(root=local_path)

    if source == "google_drive":
        credential = await credential_repository.get(tenant_id, ConnectorProvider.GOOGLE_DRIVE)
        client = GoogleDriveClient(
            access_token=credential.access_token, allowed_hosts=settings.mcp_allowed_hosts
        )
        return GoogleDriveLoader(client)

    if source == "notion":
        credential = await credential_repository.get(tenant_id, ConnectorProvider.NOTION)
        client = NotionClient(
            access_token=credential.access_token, allowed_hosts=settings.mcp_allowed_hosts
        )
        return NotionLoader(client)

    raise ValueError(f"Unsupported ingestion source: {source}")
