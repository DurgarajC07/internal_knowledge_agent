"""Shared test configuration and settings-builder helpers."""

from __future__ import annotations

from typing import Any

from packages.config.settings import Settings


def build_test_settings(**overrides: Any) -> Settings:
    """A Settings instance safe for unit tests: no real Ollama/Qdrant/DB
    endpoints are contacted unless a test explicitly mocks them."""
    defaults: dict[str, Any] = {
        "environment": "test",
        "database_url": "sqlite+aiosqlite:///:memory:",
        "mcp_allowed_hosts": ["www.googleapis.com", "api.notion.com"],
    }
    defaults.update(overrides)
    return Settings(**defaults)
