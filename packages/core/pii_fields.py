"""Field names that structured logging must always redact.

Referenced by the logging setup (packages/config/logging.py) so a log call that
happens to include one of these keys never leaks the raw value (Rule.md SS3, SS8).
"""

from __future__ import annotations

PII_FIELDS: frozenset[str] = frozenset(
    {
        "password",
        "access_token",
        "refresh_token",
        "api_key",
        "client_secret",
        "authorization",
        "cookie",
        "prompt",
        "raw_content",
        "document_body",
        "response_text",
        "email",
        "ssn",
    }
)


def redact(data: dict[str, object]) -> dict[str, object]:
    """Return a shallow copy of `data` with any PII_FIELDS key masked."""
    return {k: ("***REDACTED***" if k.lower() in PII_FIELDS else v) for k, v in data.items()}
