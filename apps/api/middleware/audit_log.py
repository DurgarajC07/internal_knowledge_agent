"""Request-level audit log: method, path, status, duration, client host for
every request. Complements the domain-specific audit logs already emitted by
services/retrieval, packages/clients/mcp_client.py, and
packages/clients/repositories/credential_repository.py — this middleware
covers requests that never reach those layers (auth failures, validation
errors, 404s) so every request is traceable (Plan.md SS8/SS9). Never logs
request/response bodies, headers, or query strings — those can carry
credentials or PII (Rule.md SS3)."""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from packages.config.logging import get_logger

logger = get_logger(__name__)


class AuditLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        started_at = time.monotonic()
        response = await call_next(request)
        duration_ms = (time.monotonic() - started_at) * 1000

        logger.info(
            "request.audit",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round(duration_ms, 1),
            client_host=request.client.host if request.client else None,
        )
        return response
