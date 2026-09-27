"""Shared SSRF and output-capping guards for every network-fetching MCP tool
(Rule.md SS6, SS9)."""

from __future__ import annotations

from urllib.parse import urlparse

from packages.core.exceptions import SSRFBlockedError


def assert_host_allowed(url: str, allowed_hosts: list[str]) -> None:
    host = urlparse(url).hostname
    if host is None or host not in allowed_hosts:
        raise SSRFBlockedError(f"Destination host '{host}' is not on the MCP allowlist")


def cap_output(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...(truncated)"
