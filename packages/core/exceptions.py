"""Typed exceptions raised anywhere in the domain layers.

A single FastAPI exception handler (apps/api/middleware/errors.py) maps these to
HTTP responses. No route or service should raise or expose a raw third-party SDK
exception or stack trace to the client (Rule.md SS3).
"""

from __future__ import annotations


class KnowledgeAgentError(Exception):
    """Base class for every domain error in this project."""


class TenantContextMissingError(KnowledgeAgentError):
    """Raised when a function that requires a TenantContext is called without one."""


class RetrievalTimeoutError(KnowledgeAgentError):
    """Vector search did not complete within the retrieval latency budget."""


class InsufficientContextError(KnowledgeAgentError):
    """Retrieval + tools produced nothing groundable enough to answer confidently."""


class ToolPermissionDeniedError(KnowledgeAgentError):
    """An MCP tool call was rejected because it exceeded its granted scope."""


class ToolExecutionError(KnowledgeAgentError):
    """An MCP tool call failed while talking to the external system."""


class CredentialNotFoundError(KnowledgeAgentError):
    """No stored OAuth credential exists for the given (tenant_id, provider)."""


class IngestionError(KnowledgeAgentError):
    """A document failed to load/parse/chunk/embed during ingestion."""


class UnsupportedDocumentTypeError(IngestionError):
    """The ingestion pipeline has no parser registered for this document type."""


class LLMProviderError(KnowledgeAgentError):
    """The configured LLM provider failed to generate a response."""


class AuthenticationError(KnowledgeAgentError):
    """The request's credentials/session could not be verified."""


class AuthorizationError(KnowledgeAgentError):
    """The authenticated principal is not allowed to perform this action."""


class EmailAlreadyRegisteredError(KnowledgeAgentError):
    """Signup was attempted with an email that already has an account."""


class ResourceNotFoundError(KnowledgeAgentError):
    """The requested resource does not exist, or does not belong to the
    caller's tenant/user — the two are deliberately indistinguishable to the
    client (Rule.md SS7: never leak whether a resource exists cross-tenant)."""


class SSRFBlockedError(KnowledgeAgentError):
    """An outbound fetch target was rejected because its host is not allowlisted."""
