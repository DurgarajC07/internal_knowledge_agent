"""Structured (JSON) logging setup shared by every entry point (API, ingestion CLI,
MCP servers). Never emits a prompt, a full document body, an OAuth token, or any
field named in packages/core/pii_fields.py (Rule.md SS3)."""

from __future__ import annotations

import logging
import sys

import structlog

from packages.core.pii_fields import PII_FIELDS


def _redact_pii(_logger: object, _method_name: str, event_dict: dict) -> dict:
    for key in list(event_dict.keys()):
        if key.lower() in PII_FIELDS:
            event_dict[key] = "***REDACTED***"
    return event_dict


def configure_logging(environment: str = "development") -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        _redact_pii,
    ]

    if environment == "development":
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
