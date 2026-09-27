"""Standalone ingestion entrypoint.

    uv run python -m services.ingestion.cli --tenant-id <uuid> --source local --path ./sample_docs

Runs identically whether invoked by hand, a cron job, or a queue worker
(Rule.md SS5) — this module is never imported by apps/api (Rule R-1).
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from uuid import UUID

from packages.clients.embedding_client import build_embedding_client
from packages.clients.qdrant_client import build_qdrant_store
from packages.config.logging import configure_logging
from packages.config.settings import get_settings
from services.ingestion.loaders.local_file_loader import LocalFileLoader
from services.ingestion.pipeline import ingest_source


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest documents into Qdrant for one tenant.")
    parser.add_argument("--tenant-id", required=True, type=UUID)
    parser.add_argument("--source", required=True, choices=["local"])
    parser.add_argument("--path", required=True, type=Path)
    return parser


async def main_async(tenant_id: UUID, source: str, path: Path) -> None:
    settings = get_settings()
    configure_logging(settings.environment)

    if source == "local":
        loader = LocalFileLoader(root=path)
    else:  # pragma: no cover - argparse `choices` already restricts this
        raise ValueError(f"Unsupported source: {source}")

    embedding_client = build_embedding_client(settings)
    vector_store = build_qdrant_store(settings)

    result = await ingest_source(
        tenant_id=tenant_id,
        loader=loader,
        embedding_client=embedding_client,
        vector_store=vector_store,
    )
    print(
        f"Ingested {result.document_count} documents "
        f"({result.chunk_count} chunks, {result.skipped_count} skipped) "
        f"for tenant {tenant_id}."
    )


def main() -> None:
    args = build_arg_parser().parse_args()
    asyncio.run(main_async(args.tenant_id, args.source, args.path))


if __name__ == "__main__":
    main()
