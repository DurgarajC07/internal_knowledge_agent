# 0002 — Structured citations only from the internal retrieval tool at MVP

## Status
Accepted (MVP). Revisit if a pilot tenant relies heavily on live Drive/Notion
lookups rather than ingested-document search.

## Problem
`BRD.md FR-3` requires every answer using retrieved context to carry a
citation (document name/link + snippet locator). `Plan.md §1.1` says citations
are "derived directly from retrieved-chunk metadata **and/or** MCP tool-result
metadata" — the "and/or" leaves the MCP side optional.

## Decision
`services/agent/tools.py` builds a `Citation` (title, url, source, chunk
index, snippet) only for hits from the internal `search_knowledge_base` tool,
whose results come straight from Qdrant payload metadata. Google Drive/Notion
tool calls (`google_drive__search_files`, `notion__get_page_content`, etc.)
return their formatted text as tool-result content that the LLM can reason
over and mention in its answer, but no `Citation` object is constructed from
them.

## Alternatives considered
- **Structured citation from every MCP tool result**: would need every tool
  function to return a machine-parseable (title, url) pair in addition to its
  human-readable text, and `packages/core/schemas/tool.ToolCallResult` would
  need a structured metadata field beyond `content: str`. Deferred — it's a
  real enhancement, not a blocker for the BRD's core user story, which the
  vector-search path already satisfies end to end (see
  `tests/unit/services/agent/test_orchestrator.py::test_handle_message_grounds_answer_in_retrieved_chunk_and_attaches_citation`).

## Consequences
- An answer grounded purely in a live Drive/Notion fetch (no matching ingested
  chunk) will state its source in prose but won't produce a clickable
  `Citation` in the API response's `citations` list. The system prompt
  (`services/agent/prompts.py`) still requires the model to name its source in
  text, so `BRD.md`'s spirit (traceability) holds even where the structured
  field doesn't.
- Adding structured MCP citations later is additive: extend `ToolCallResult`
  with an optional `citation: Citation | None` field, have each MCP tool
  function populate it, and thread it through `dispatch_tool_call` in
  `services/agent/tools.py`. No existing test needs to change.
