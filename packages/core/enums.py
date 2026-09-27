from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    MEMBER = "member"


class ConnectorProvider(StrEnum):
    GOOGLE_DRIVE = "google_drive"
    NOTION = "notion"


class IngestionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class LLMProviderName(StrEnum):
    OLLAMA = "ollama"
    HOSTED = "hosted"
