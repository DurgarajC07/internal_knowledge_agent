"""Standalone ingestion entrypoint.

    uv run python -m services.ingestion.cli --tenant-id <uuid> --source local --path ./sample_docs
    uv run python -m services.ingestion.cli --tenant-id <uuid> --source google_drive
    uv run python -m services.ingestion.cli --tenant-id <uuid> --source notion

Runs identically whether invoked by hand, a cron job, or a queue worker
(Rule.md SS5) — this module is never imported by apps/api (Rule R-1). For
google_drive/notion, the tenant must already have a connected credential
(via the app's Connect flow, POST-first through the API — see
apps/api/routes/connectors.py) before this can run.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from uuid import UUID

from packages.clients.db import build_engine, build_session_factory
from packages.clients.embedding_client import build_embedding_client
from packages.clients.qdrant_client import build_qdrant_store
from packages.clients.repositories.credential_repository import CredentialRepository
from packages.config.logging import configure_logging
from packages.config.settings import get_settings
from services.ingestion.loader_factory import SUPPORTED_SOURCES, build_loader
from services.ingestion.pipeline import ingest_source


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest documents into Qdrant for one tenant.")
    parser.add_argument("--tenant-id", required=True, type=UUID)
    parser.add_argument("--source", required=True, choices=SUPPORTED_SOURCES)
    parser.add_argument("--path", required=False, type=Path, help="Required when --source local")
    return parser


async def main_async(tenant_id: UUID, source: str, path: Path | None) -> None:
    settings = get_settings()
    configure_logging(settings.environment)

    if source == "local" and path is None:
        raise SystemExit("--path is required when --source local")

    embedding_client = build_embedding_client(settings)
    vector_store = build_qdrant_store(settings)
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)

    try:
        async with session_factory() as session:
            credential_repository = CredentialRepository(
                session, settings.credential_encryption_key
            )
            loader = await build_loader(
                source,
                tenant_id,
                settings=settings,
                credential_repository=credential_repository,
                local_path=path,
            )

        result = await ingest_source(
            tenant_id=tenant_id,
            loader=loader,
            embedding_client=embedding_client,
            vector_store=vector_store,
        )
    finally:
        await engine.dispose()

    print(
        f"Ingested {result.document_count} documents "
        f"({result.chunk_count} chunks, {result.skipped_count} skipped) "
        f"for tenant {tenant_id} from source '{source}'."
    )


def main() -> None:
    args = build_arg_parser().parse_args()
    asyncio.run(main_async(args.tenant_id, args.source, args.path))


if __name__ == "__main__":
    main()
