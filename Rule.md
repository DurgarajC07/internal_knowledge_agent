# Rule.md — Engineering Standards & Layering Rules

Authoritative coding rules for this repository. `AGENT.md` tells an AI coding agent *when* and *how* to work; this
file defines *what "correct code" looks like*. Any code — human- or agent-written — that violates a rule here should
be treated as a bug, not a style nitpick. These rules exist specifically to enforce the constraints in the BRD (tenant
isolation, ingestion/API separation, replaceable providers).

---

## 1. Tooling & Versions

| Tool | Version / rule |
|---|---|
| Python | 3.12+, managed with `uv` (no bare `pip`, no `venv` + `pip install` by hand) |
| Formatting/Lint | `ruff format` + `ruff check` (replaces black/isort/flake8) — must pass with zero warnings before commit |
| Typing | `pyright` (or `mypy --strict` if preferred) — no `# type: ignore` without a one-line justification comment |
| Data models | Pydantic v2 exclusively; no bare dicts crossing a layer boundary |
| Node/Frontend | Node 20+, TypeScript `strict: true`, no `any` (use `unknown` + narrowing) |
| Frontend lint | ESLint + Prettier, pre-commit enforced |
| Tests | `pytest` (backend), `vitest`/`playwright` (frontend) |
| Commits | Conventional Commits (`feat:`, `fix:`, `refactor:`, `chore:`, `docs:`, `test:`) |

Run before every commit:

```bash
uv run ruff format . && uv run ruff check . --fix
uv run pyright
uv run pytest -q
```

---

## 2. Layering Rules (Hard Boundaries)

The architecture is a strict pipeline. **A layer may only import from the layer(s) listed under "May depend on."**
Violating this — e.g., a route handler importing the Qdrant client directly — is a blocking review comment, not a
suggestion.

| Layer | Lives in | May depend on | Must NOT depend on |
|---|---|---|---|
| API (routes) | `apps/api/routes/` | Application/use-case layer, `packages/core` schemas | Agent internals, MCP client, Qdrant client, embedding models, `services/ingestion` |
| Application / use-case | `apps/api/usecases/` | Agent orchestration layer, `packages/core` | HTTP request/response objects, DB drivers directly |
| Agent orchestration | `services/agent/` | LLM client, retrieval layer, MCP client, `packages/core` | FastAPI, HTTP concerns |
| Retrieval / tool layer | `services/retrieval/` | Vector DB client (`packages/clients`), embedding client | Agent prompt-construction logic, FastAPI |
| MCP layer | `services/mcp_servers/`, `packages/clients/mcp_client.py` | External APIs (Drive, Notion), `packages/core` | Agent prompt logic, FastAPI routes |
| Ingestion | `services/ingestion/` | Document loaders, chunker, embedding client, vector DB client, `packages/core` | FastAPI, request/response models, the live query path |
| Infrastructure clients | `packages/clients/` | Third-party SDKs | Business logic |
| Shared core | `packages/core/` | Nothing project-specific (pure models/enums/exceptions) | Every other layer (must stay dependency-free) |

**Rule R-1 (non-negotiable):** `apps/api/routes/**` must never import anything from `services/ingestion/**`.
Ingestion is triggered by the API only indirectly — by enqueuing a job (id, tenant_id, source) onto a queue/table that
a separate worker process consumes. The worker imports ingestion code; the route never does.

**Rule R-2:** `services/retrieval` and `services/agent` never import FastAPI, `Request`, `Response`, or any
HTTP-framework type. They are framework-agnostic and callable from a CLI, a worker, or a test — not just from an API
route.

**Rule R-3:** The only place allowed to construct a vector-DB client, an LLM client, or an MCP client "raw" is
`packages/clients/`. Every other layer receives an already-constructed client via dependency injection
(`Depends(...)` in FastAPI, or a constructor parameter elsewhere) — never a global singleton imported ad hoc.

---

## 3. Backend (FastAPI) Conventions

- Route handlers do three things only: parse/validate the request (Pydantic), call exactly one use-case function,
  and map the result/exception to an HTTP response. No business logic, no prompt construction, no vector-DB calls in
  a route body.
- Every route function is `async def`. Any call to a blocking library (e.g., a sync SDK) is wrapped with
  `run_in_threadpool` or an async-native client — never called blocking inside an `async def`.
- Dependencies (DB session, tenant context, current user, clients) are provided via FastAPI `Depends`, defined once in
  `apps/api/dependencies.py`.
- Every request handler that touches tenant data receives a `TenantContext` object resolved from the auth token —
  never a raw `tenant_id` string parsed ad hoc from the body/query params. See `Rule.md §8`.
- Errors: raise a typed exception from `packages/core/exceptions.py` (e.g., `RetrievalTimeoutError`,
  `ToolPermissionDeniedError`); a single FastAPI exception handler translates these to HTTP responses. Never leak a
  raw stack trace or third-party SDK exception to the client.
- Logging is structured (JSON), includes `tenant_id` and `request_id`, and **never** includes: raw document content,
  full LLM prompts/responses, OAuth tokens/API keys, or any field named in `packages/core/pii_fields.py`.

## 4. Pydantic & Data Modeling

- All request/response bodies, internal DTOs passed between layers, and MCP tool input/output schemas are Pydantic v2
  models — no bare `dict[str, Any]` crossing a function boundary that another module calls.
- Models that cross the API boundary live in `packages/core/schemas/` so both `apps/api` and `apps/web` (via
  generated types) share one source of truth.
- Use `model_config = ConfigDict(extra="forbid")` on any model parsing external/untrusted input (tool results,
  webhook payloads) to fail loudly on unexpected fields rather than silently accept them.

## 5. Ingestion Pipeline Rules

- Ingestion is a standalone package (`services/ingestion/`) runnable as `uv run python -m ingestion.cli --tenant-id
  ... --source drive`. It must run identically whether triggered by a cron job, a queue worker, or a developer's
  terminal.
- Every ingestion run is **idempotent**: re-ingesting the same document must update/replace its vectors, not
  duplicate them (use a deterministic point ID derived from `tenant_id + source + document_id + chunk_index`).
- Ingestion never imports from `apps/api`. If it needs configuration, it reads from `packages/config`, the same
  settings module the API uses — not a separate hardcoded config.
- Every ingested chunk is written with metadata sufficient to reconstruct a citation without a second lookup:
  `tenant_id`, `source`, `document_id`, `document_title`, `url_or_path`, `chunk_index`, `ingested_at`.

## 6. MCP Server & Tool Rules

- Each external system gets its own MCP server module (`services/mcp_servers/google_drive/`,
  `services/mcp_servers/notion/`) exposing a small number of narrowly-scoped tools (e.g., `search_files`,
  `get_file_content`) — never one giant "do anything" tool.
- Every tool's input schema is a Pydantic model with explicit, bounded fields (no free-form "run this query against
  the API" tool). Every tool's output is size-capped (e.g., truncate file content beyond N tokens) before it re-enters
  the LLM context.
- Every MCP tool call is scoped to exactly one tenant's credentials, resolved from the tenant's encrypted credential
  store — a tool implementation must never accept a tenant ID as a parameter it trusts blindly from model output;
  the tenant ID is injected by the MCP client from the authenticated session, not read from the LLM's tool call
  arguments.
- Tool results returned to the agent are treated as **untrusted data**, exactly like retrieved document text — never
  concatenated into the system prompt as instructions, and any text resembling an instruction inside a tool result
  must not change agent behavior (basic prompt-injection hygiene; see `Plan.md §9`).
- Every tool call is logged (tool name, tenant, duration, success/failure, byte size of result) — not the raw content
  — for audit purposes.
- Network-fetching tools (Drive/Notion HTTP calls) must validate/allowlist destination hosts to prevent SSRF via a
  maliciously crafted "file link."

## 7. Multi-Tenancy Rules

- Every database table storing tenant data has a non-nullable `tenant_id` column; every query is filtered by it —
  enforced via a repository-layer helper, never left to individual call sites to remember.
- Every Qdrant call (search or upsert) includes a mandatory `tenant_id` payload filter; there is no code path where a
  vector search can run without one. Prefer one Qdrant **collection per tenant** at MVP scale (simplest to reason
  about and to delete on offboarding) over a single shared collection with filters, unless/until collection count
  becomes an operational problem (see `Plan.md §8`).
- No raw SQL string interpolation, ever — parameterized queries / ORM only, to remove SQL injection as an attack
  surface entirely.
- `TenantContext` is derived once per request (from the verified auth token) and threaded explicitly through every
  function call that needs it — it is never read from a global/thread-local implicitly.

## 8. Security Rules Checklist (apply to every PR)

- [ ] No secret, API key, or credential is hardcoded or committed; all come from environment variables /
      the secrets manager, loaded through `packages/config`.
- [ ] No log line contains a prompt, a full document body, or a credential.
- [ ] Every new endpoint has an explicit auth dependency; there is no "temporarily unauthenticated" route.
- [ ] Every new Qdrant/DB query has a `tenant_id` filter (see §7).
- [ ] Every new MCP tool has a bounded, validated input schema and a capped output size.
- [ ] Any endpoint accepting a URL or performing an outbound fetch validates the destination against an allowlist.
- [ ] Rate limiting exists (or is explicitly deferred with a ticket) on any endpoint that triggers an LLM call.

## 9. Testing Rules

- Unit tests for `services/retrieval`, `services/agent`, `services/ingestion`, and `packages/*` must not make real
  network calls (mock the LLM/Qdrant/MCP clients).
- Integration tests spin up a local Qdrant (Docker) and use recorded/replayed MCP responses — never call live
  Google Drive/Notion APIs in CI.
- Every bug fix ships with a regression test.
- Minimum coverage gate: 80% on `services/` and `packages/core`; enforced in CI, not aspirational.

## 10. Frontend Conventions

- Next.js App Router; React Server Components by default, `"use client"` only where interactivity is required (chat
  input, streaming message list).
- All API calls go through a single typed client (`apps/web/lib/api-client.ts`) generated/kept in sync with the
  backend Pydantic schemas — no ad hoc `fetch` calls scattered through components.
- Streaming chat responses use the platform's native streaming primitives (SSE or fetch stream reader) — no polling.
- Tailwind + shadcn/ui only; no ad hoc CSS files unless a component genuinely can't be expressed with utility
  classes.

## 11. Git & PR Conventions

- Branch naming: `feat/<short-desc>`, `fix/<short-desc>`, `chore/<short-desc>`.
- Commits follow Conventional Commits.
- A PR that adds a new architectural decision (new dependency, new layer, deviation from `Plan.md`) includes a short
  ADR file under `docs/adr/NNNN-title.md` (problem, decision, alternatives considered, consequences).
- PR checklist (in addition to §8 security checklist): layering rules respected (§2), tests added (§9), docs updated
  if public behavior changed.

---

**When a rule here conflicts with a shortcut that seems faster:** the rule wins. If a rule genuinely blocks a
legitimate need, update this file via a reviewed PR with reasoning — don't silently work around it.
