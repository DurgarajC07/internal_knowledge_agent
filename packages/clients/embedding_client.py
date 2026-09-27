"""Provider-agnostic embedding client.

The same model/client MUST be used for ingestion-time and query-time embedding —
mixing embedding models silently corrupts vector similarity (Plan.md SS7, Rule.md
SS5). `nomic-embed-text` via Ollama is the $0 local-dev default; a hosted embedding
API can be swapped in purely via `packages/config` (BRD.md SS4).
"""

from __future__ import annotations

from typing import Protocol

import httpx

from packages.config.settings import Settings
from packages.core.exceptions import LLMProviderError


class EmbeddingClient(Protocol):
    dimensions: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class OllamaEmbeddingClient:
    def __init__(self, base_url: str, model: str, dimensions: int) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self.dimensions = dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{self._base_url}/api/embed",
                    json={"model": self._model, "input": texts},
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"Ollama embedding request failed: {exc}") from exc
        return data["embeddings"]


def build_embedding_client(settings: Settings) -> EmbeddingClient:
    return OllamaEmbeddingClient(
        base_url=settings.ollama_base_url,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
    )
