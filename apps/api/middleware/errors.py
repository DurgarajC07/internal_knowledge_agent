"""One place every domain exception becomes an HTTP response. A raw stack
trace or third-party SDK exception must never reach the client (Rule.md SS3)."""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from packages.config.logging import get_logger
from packages.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    CredentialNotFoundError,
    EmailAlreadyRegisteredError,
    InsufficientContextError,
    KnowledgeAgentError,
    ResourceNotFoundError,
    RetrievalTimeoutError,
    SSRFBlockedError,
    ToolPermissionDeniedError,
)

logger = get_logger(__name__)

_STATUS_BY_EXCEPTION: dict[type[KnowledgeAgentError], int] = {
    AuthenticationError: status.HTTP_401_UNAUTHORIZED,
    AuthorizationError: status.HTTP_403_FORBIDDEN,
    ToolPermissionDeniedError: status.HTTP_403_FORBIDDEN,
    ResourceNotFoundError: status.HTTP_404_NOT_FOUND,
    EmailAlreadyRegisteredError: status.HTTP_409_CONFLICT,
    CredentialNotFoundError: status.HTTP_424_FAILED_DEPENDENCY,
    RetrievalTimeoutError: status.HTTP_504_GATEWAY_TIMEOUT,
    InsufficientContextError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    SSRFBlockedError: status.HTTP_400_BAD_REQUEST,
}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(KnowledgeAgentError)
    async def handle_domain_error(request: Request, exc: KnowledgeAgentError) -> JSONResponse:
        status_code = _STATUS_BY_EXCEPTION.get(type(exc), status.HTTP_400_BAD_REQUEST)
        logger.warning(
            "request.domain_error",
            path=request.url.path,
            exception_type=type(exc).__name__,
            status_code=status_code,
        )
        return JSONResponse(status_code=status_code, content={"detail": str(exc)})

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "request.unhandled_error", path=request.url.path, exception_type=type(exc).__name__
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An unexpected error occurred."},
        )
