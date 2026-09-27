"""Provider-agnostic LLM client interface.

Ollama is a local dev tool only; production inference goes through the hosted
client. Both implement the same `LLMClient` protocol so `services/agent` never
imports a provider SDK directly (AGENT.md SS2.8, Plan.md Executive Architecture
Decision). This is the only module allowed to construct a raw LLM SDK client
(Rule.md R-3) — every other layer receives one via dependency injection.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, Literal, Protocol

import anthropic
import httpx
from pydantic import BaseModel, ConfigDict

from packages.config.settings import Settings
from packages.core.exceptions import LLMProviderError


class ToolSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    input_schema: dict[str, Any]


class ToolCallIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_call_id: str
    tool_name: str
    tool_input: dict[str, Any]


class LLMMessage(BaseModel):
    """A single turn in the replayed conversation.

    An `assistant` message that issued tool calls carries them in `tool_calls` —
    both providers need that assistant tool-use turn replayed before the
    matching `tool` result message, or the transcript is invalid (Anthropic
    rejects it outright; Ollama silently loses the call). `content` may be
    empty for a pure tool-call turn.
    """

    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant", "tool"]
    content: str = ""
    tool_calls: list[ToolCallIntent] = []
    tool_call_id: str | None = None
    tool_name: str | None = None


class LLMResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    tool_calls: list[ToolCallIntent] = []
    stop_reason: str


class LLMClient(Protocol):
    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        system: str | None = None,
        tools: list[ToolSpec] | None = None,
    ) -> LLMResponse: ...

    def stream(
        self,
        messages: list[LLMMessage],
        *,
        system: str | None = None,
    ) -> AsyncIterator[str]: ...


class OllamaLLMClient:
    """Local dev only — never assumed as production infrastructure (BRD.md SS10)."""

    def __init__(self, base_url: str, model: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model

    def _to_ollama_messages(
        self, messages: list[LLMMessage], system: str | None
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if system:
            out.append({"role": "system", "content": system})
        for m in messages:
            if m.role == "tool":
                out.append({"role": "tool", "content": m.content, "name": m.tool_name})
            elif m.role == "assistant" and m.tool_calls:
                out.append(
                    {
                        "role": "assistant",
                        "content": m.content,
                        "tool_calls": [
                            {
                                "function": {
                                    "name": tc.tool_name,
                                    "arguments": tc.tool_input,
                                }
                            }
                            for tc in m.tool_calls
                        ],
                    }
                )
            else:
                out.append({"role": m.role, "content": m.content})
        return out

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        system: str | None = None,
        tools: list[ToolSpec] | None = None,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": self._to_ollama_messages(messages, system),
            "stream": False,
        }
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.input_schema,
                    },
                }
                for t in tools
            ]
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(f"{self._base_url}/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"Ollama request failed: {exc}") from exc

        message = data.get("message", {})
        raw_tool_calls = message.get("tool_calls") or []
        tool_calls = [
            ToolCallIntent(
                tool_call_id=f"ollama-{i}",
                tool_name=tc["function"]["name"],
                tool_input=(
                    tc["function"]["arguments"]
                    if isinstance(tc["function"]["arguments"], dict)
                    else json.loads(tc["function"]["arguments"])
                ),
            )
            for i, tc in enumerate(raw_tool_calls)
        ]
        return LLMResponse(
            text=message.get("content", ""),
            tool_calls=tool_calls,
            stop_reason="tool_use" if tool_calls else "end_turn",
        )

    async def stream(
        self,
        messages: list[LLMMessage],
        *,
        system: str | None = None,
    ) -> AsyncIterator[str]:
        payload = {
            "model": self._model,
            "messages": self._to_ollama_messages(messages, system),
            "stream": True,
        }
        try:
            async with (
                httpx.AsyncClient(timeout=120.0) as client,
                client.stream("POST", f"{self._base_url}/api/chat", json=payload) as resp,
            ):
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    token = chunk.get("message", {}).get("content", "")
                    if token:
                        yield token
                    if chunk.get("done"):
                        break
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"Ollama stream failed: {exc}") from exc


class HostedLLMClient:
    """Hosted, production-grade LLM API (Anthropic) behind the same interface."""

    def __init__(self, api_key: str, model: str) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    def _to_anthropic_messages(self, messages: list[LLMMessage]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "tool":
                out.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": m.tool_call_id,
                                "content": m.content,
                            }
                        ],
                    }
                )
            elif m.role == "assistant" and m.tool_calls:
                blocks: list[dict[str, Any]] = []
                if m.content:
                    blocks.append({"type": "text", "text": m.content})
                blocks.extend(
                    {
                        "type": "tool_use",
                        "id": tc.tool_call_id,
                        "name": tc.tool_name,
                        "input": tc.tool_input,
                    }
                    for tc in m.tool_calls
                )
                out.append({"role": "assistant", "content": blocks})
            else:
                out.append({"role": m.role, "content": m.content})
        return out

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        system: str | None = None,
        tools: list[ToolSpec] | None = None,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": 4096,
            "messages": self._to_anthropic_messages(messages),
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.input_schema}
                for t in tools
            ]
        try:
            response = await self._client.messages.create(**kwargs)
        except anthropic.APIError as exc:
            raise LLMProviderError(f"Hosted LLM request failed: {exc}") from exc

        text_parts: list[str] = []
        tool_calls: list[ToolCallIntent] = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCallIntent(
                        tool_call_id=block.id,
                        tool_name=block.name,
                        tool_input=dict(block.input),
                    )
                )
        return LLMResponse(
            text="".join(text_parts),
            tool_calls=tool_calls,
            stop_reason=response.stop_reason or "end_turn",
        )

    async def stream(
        self,
        messages: list[LLMMessage],
        *,
        system: str | None = None,
    ) -> AsyncIterator[str]:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": 4096,
            "messages": self._to_anthropic_messages(messages),
        }
        if system:
            kwargs["system"] = system
        try:
            async with self._client.messages.stream(**kwargs) as stream:
                async for text in stream.text_stream:
                    yield text
        except anthropic.APIError as exc:
            raise LLMProviderError(f"Hosted LLM stream failed: {exc}") from exc


def build_llm_client(settings: Settings) -> LLMClient:
    """The one place `llm_provider` config is switched — never scattered
    hardcoded provider checks elsewhere (BRD.md SS4)."""
    if settings.llm_provider == "hosted":
        if not settings.hosted_llm_api_key:
            raise LLMProviderError("hosted_llm_api_key is required when llm_provider=hosted")
        return HostedLLMClient(api_key=settings.hosted_llm_api_key, model=settings.hosted_llm_model)
    return OllamaLLMClient(base_url=settings.ollama_base_url, model=settings.local_llm_model)
