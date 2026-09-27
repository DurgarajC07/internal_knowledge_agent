# 0003 — Chat streaming runs the tool loop to completion, then streams the answer

## Status
Accepted (MVP). Revisit if pilot feedback says the wait before the first token
is too long once a hosted LLM is in use.

## Problem
`BRD.md FR-2` requires the system to stream a grounded answer "token-by-
token." The agent's tool-calling loop (`services/agent/orchestrator.py`) may
call `search_knowledge_base` and/or an MCP tool zero to `_MAX_TOOL_ITERATIONS`
times before it has enough context to answer — genuinely interleaving
token-level streaming with that reasoning loop means streaming the *model's*
output while it's still deciding whether to call another tool, which the
`LLMClient` interface (`packages/clients/llm_client.py`) doesn't yet support
(its `.generate()` is request/response; `.stream()` doesn't expose tool-call
detection mid-stream).

## Decision
`apps/api/routes/chat.py` calls `handle_chat_turn` (which runs the full
orchestrator loop non-streaming) and only then streams the finished answer
text to the client in word-sized SSE `token` frames, followed by a `citations`
frame and a `done` frame. The user sees a token-by-token typing effect; the
model's own reasoning/tool-calling latency happens before the first frame.

## Alternatives considered
- **True interleaved streaming**: would require `LLMClient.generate()` to
  become a streaming, tool-call-aware API (yielding partial text and
  tool-call events), and the orchestrator to route each tool call through
  `services/agent/tools.py` mid-stream. Real improvement, explicitly deferred
  — no BRD/Plan.md requirement forces it, and it roughly doubles the
  complexity of `services/agent/orchestrator.py` and its test surface.

## Consequences
- First-byte latency for a tool-using query equals the full non-streamed
  turn's latency, not just the first LLM round-trip. Acceptable at MVP scale
  (Plan.md §7: sub-second retrieval; the dominant cost is LLM round-trips,
  which this doesn't change either way).
- The SSE contract (`ChatStreamEvent` in `packages/core/schemas/chat.py`) is
  already shaped to support real interleaved streaming later without a
  breaking change — only the route's internals would need to change.
