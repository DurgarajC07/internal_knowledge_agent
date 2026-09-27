# 0001 — MCP servers run in-process, not as separate OS processes, at MVP

## Status
Accepted (MVP). Revisit once a connector needs independent scaling/deployment.

## Problem
`Plan.md §2.3` says MCP servers are deployed "as a separate process/module per
integration ... deployed alongside the API on Render at MVP (same container or
a lightweight sidecar process) — not embedded inside the FastAPI route code, so
it can later move to its own service/host without touching the agent." This
leaves open exactly how "alongside, same container" is implemented.

## Decision
`services/mcp_servers/google_drive/server.py` and `.../notion/server.py` build
a real `mcp.server.mcpserver.MCPServer` instance (the actual MCP Python SDK,
not a hand-rolled stand-in), registered with real tool schemas. The MCP
*client* (`packages/clients/mcp_client.py`) calls `server.call_tool(...)`
directly, in-process — no stdio subprocess, no network hop — because both
already run in the same FastAPI process per Plan.md's "same container" option.

Tenant credential injection uses a `ContextVar` (`services/mcp_servers/_shared/
context.py`) that the client sets immediately before the call and resets
immediately after, rather than the SDK's `Context.request_state` mechanism.
This was a deliberate choice to keep the tenant-isolation guarantee (Rule.md
§6: a tool must never trust a tenant ID from model output) verifiable with a
simple, well-understood Python primitive instead of depending on an
underdocumented, newly-released (v2) SDK internal.

## Alternatives considered
- **stdio subprocess per connector** (literal separate OS process): real
  isolation, but adds process-lifecycle management, IPC serialization, and
  latency for no MVP benefit — the module boundary (`services/mcp_servers/*`
  is never imported by a route, only by `packages/clients/mcp_client.py`)
  already gives the swappability Plan.md asks for.
- **`Context.request_state`**: the SDK-native way to pass per-call state, but
  its exact contract wasn't verified against the running v2 SDK in the time
  available; a ContextVar is simpler and independently testable (see
  `tests/unit/services/mcp_servers/test_google_drive_server.py`).

## Consequences
- Moving a connector to its own service later means: keep the tool functions
  and Pydantic schemas as-is, swap `packages/clients/mcp_client.py`'s in-process
  call for an MCP stdio/HTTP client — the agent orchestrator and route code
  never change.
- Both MCP servers currently share the API process's crash domain. Acceptable
  at MVP scale (Plan.md §12: no microservices split without a demonstrated
  need).
