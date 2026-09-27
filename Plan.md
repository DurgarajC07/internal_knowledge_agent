# Plan.md — Architecture & Phased Development Plan

Companion to `BRD.md` (what/why), `AGENT.md` (agent operating rules), `Rule.md` (code-level standards). This file is
the how: system architecture, MCP design, project structure, phased plan, setup commands, RAG design, multi-tenancy,
security, cost model, technology decisions, deferred scope, and the final MVP diagram.

Research notes: free-tier limits, local-model recommendations, and embedding-model comparisons below were verified
against current vendor documentation and independent pricing trackers as of September 2026 (sources listed at the end
of each relevant section). Figures like instance-hour counts or storage caps can change — recheck vendor docs before
locking a production budget.

---

## Executive Architecture Decision

- **RAG, not fine-tuning**, is the retrieval mechanism; **MCP is the integration protocol**, not the retrieval
  mechanism itself — these are two different layers and the original brief occasionally conflated them (fixed here).
- **Qdrant Cloud (free tier)** for the vector store at MVP — best fit for a single small founder team; **pgvector** is
  the fallback if you already need relational data and want one fewer service (see §"Vector Database Trade-offs"
  below).
- **No graph database at MVP.** Add Neo4j (or similar) only if a concrete retrieval failure shows relationship
  queries ("who worked on this deal, and what else did they touch") outperform vector search — see §12.
- **Ollama stays a local dev tool.** Production LLM calls go through a hosted, production-grade API behind a
  provider-agnostic client interface — do not deploy Ollama as the production inference server for this MVP.
- **Monorepo**, not dual-repo — one founder-engineer, shared Pydantic↔TypeScript types, and atomic
  frontend+backend changes outweigh the isolation benefits of separate repos at this stage.
- **Render free tier is fine for early demos, not for a paying customer.** Free web services spin down after 15
  minutes of inactivity with a ~30–60s cold start on the next request, and are capped at 750 instance-hours per
  workspace per month — acceptable for a pilot/demo, not for a customer who expects an always-on chat tool. Budget
  for Render's Starter paid tier ($7/mo, always-on) the moment you have a real user relying on this daily.
- **MCP is used only for genuinely external, permissioned data sources** (Google Drive, Notion, future CRM/Slack).
  Qdrant vector search stays an internal library call from the retrieval layer by default — not wrapped in MCP —
  because it's infrastructure the agent host already owns, not a third-party system requiring a protocol boundary
  (full reasoning in §2, Q5).
- **Local dev model:** a fully-in-VRAM 7–8B instruct model (e.g., `qwen2.5:7b-instruct` or `qwen3:8b`) as the
  default — reliable tool-calling, ~4.5–5 GB at Q4, comfortably fits an 8 GB-class RTX 4060 with headroom for Qdrant
  and the rest of the dev stack. A sparse-MoE model such as `gpt-oss:20b` is a valid *optional* upgrade for
  reasoning-heavy testing (only ~3.6B active params/token despite 20B total) but is tighter on a 16 GB-RAM machine
  once other services are running, so it is not the default.
- **Embedding model:** `nomic-embed-text` for local dev (small, Ollama-native, effectively free) with `BGE-M3` as the
  self-hosted upgrade path for production quality (dense+sparse+multi-vector hybrid retrieval in one model) — avoid
  a hosted embedding API at MVP purely to keep the dev loop at $0; revisit once retrieval quality on real documents
  demands it.
- Every "connector," the LLM provider, and the vector DB are accessed through a thin interface in `packages/clients/`
  so any of them can be replaced by changing configuration, not code.

---

## 1. System Architecture (Deliverable 1)

### 1.1 Query Flow (synchronous, request-time)

```
User
  │  types a question
  ▼
Next.js UI (Vercel)
  │  POST /api/chat  (SSE/stream response)
  ▼
FastAPI route (Render)  ── thin: parse request, resolve TenantContext, call use-case
  │
  ▼
AuthN/AuthZ  ── verifies session, resolves tenant_id + user_id + scopes
  │
  ▼
Application / Use-Case Layer  ── loads conversation history, calls Agent Orchestrator
  │
  ▼
Agent Orchestrator (services/agent)
  │
  ├─▶ LLM (hosted API in prod / Ollama in dev)
  │      │  LLM decides: answer directly, or call a tool
  │      ▼
  ├─▶ Retrieval layer (services/retrieval)              [internal call, not MCP — see §2 Q5]
  │      │  embed query → Qdrant similarity search (tenant-filtered) → optional rerank
  │      ▼
  │   Qdrant (tenant-scoped collection) ──▶ top-K chunks + metadata (doc id, url, chunk idx)
  │
  └─▶ MCP Client (packages/clients/mcp_client.py)        [only when a specific external
         │                                                 document/live lookup is needed]
         ▼
      MCP Server (services/mcp_servers/google_drive | notion)
         │
         ▼
      External Data Source (Google Drive API / Notion API, tenant's OAuth token)
         │
         ▼
      Relevant document content ──▶ back to Agent Orchestrator
  │
  ▼
Context Construction  ── retrieved chunks + tool results + conversation history → prompt
  │
  ▼
LLM (final grounded generation, streamed)
  │
  ▼
Response Assembler  ── attaches citations (doc title, url, chunk locator) to streamed answer
  │
  ▼
FastAPI streams tokens + citation metadata over SSE
  │
  ▼
Next.js UI renders streamed answer + clickable source citations
  │
  ▼
Conversation history + citations persisted (Postgres) for this tenant/user
```

**Where things fit:**
- **Qdrant** — internal vector store, one collection per tenant, called from `services/retrieval`.
- **Embeddings** — computed at ingestion time (stored in Qdrant) and at query time (query embedding only,
  ephemeral) using the same embedding model — never mix embedding models between ingestion and query.
- **Document metadata** — stored as Qdrant payload (title, url, source, chunk_index) so a citation never needs a
  second database round-trip.
- **Optional graph database** — not present in the MVP query flow at all (see §12).
- **Conversation history** — Postgres, keyed by `tenant_id + user_id + conversation_id`.
- **Source citations** — derived directly from retrieved-chunk metadata and/or MCP tool-result metadata; assembled by
  the Response Assembler, never invented by the LLM from memory.

### 1.2 Document Ingestion Flow (asynchronous, background)

```
Data Source (Google Drive / Notion)
  │  triggered by: scheduled sync job OR manual "connect & sync" action
  ▼
MCP / Connector  ── services/mcp_servers/{source}/ used in "list + fetch" mode by the ingestion worker
  │                  (same MCP server code the agent uses for live lookups — reused, not duplicated)
  ▼
Document Loader (services/ingestion/loaders/)  ── pulls raw bytes/text per file
  │
  ▼
Parser (services/ingestion/parsers/)  ── format-specific: PDF, DOCX, Notion blocks, plain text
  │
  ▼
Cleaner  ── strips boilerplate/headers-footers, normalizes whitespace
  │
  ▼
Chunker (services/ingestion/chunker.py)  ── splits into ~500–800 token chunks, ~10–15% overlap
  │
  ▼
Embedding Model (packages/clients/embedding_client.py)  ── same model used at query time
  │
  ▼
Qdrant  ── upsert with deterministic point ID (tenant_id + source + doc_id + chunk_index) → idempotent re-ingestion
  │
  ▼
Metadata / Source References  ── written as Qdrant payload alongside each vector
  │
  ▼
Ingestion Job Status  ── recorded in Postgres (job id, tenant, source, doc count, status, timestamps)
```

**Ingestion vs. query-time retrieval — the key differences:**

| | Ingestion | Query-time retrieval |
|---|---|---|
| Trigger | Cron / manual sync / webhook | User's question, every request |
| Runs in | Independent worker/CLI process | Request path of the API |
| Writes | Yes — upserts vectors + metadata | No — read-only |
| Latency budget | Minutes (background) | Sub-second (user is waiting) |
| Idempotency | Required (re-sync must not duplicate) | N/A (read-only) |
| Failure handling | Retry the job; partial progress is fine | Fail fast, return "insufficient context" |

---

## 2. MCP Architecture (Deliverable 2)

1. **MCP Host:** this application's backend process — the thing that decides it needs an external tool and holds the
   MCP client(s).
2. **MCP Client:** `packages/clients/mcp_client.py` — one client connection per configured MCP server, translating
   the agent's tool-call intents into MCP protocol calls and returning results.
3. **Where the MCP Server runs:** as a separate process/module per integration (`services/mcp_servers/google_drive`,
   `services/mcp_servers/notion`), deployed alongside the API on Render at MVP (same container or a lightweight
   sidecar process) — not embedded inside the FastAPI route code, so it can later move to its own service/host without
   touching the agent.
4. **Tools the MCP Server should expose (per source):** a small, purpose-built set — e.g. for Google Drive:
   `list_recent_files`, `search_files(query, filters)`, `get_file_content(file_id)`; for Notion:
   `search_pages(query)`, `get_page_content(page_id)`. Not a generic "call the Drive API" passthrough tool.
5. **Should Qdrant be accessed directly by the agent, or through MCP?** Directly, via `services/retrieval` as an
   internal library call. Qdrant is infrastructure the host itself owns and operates — it isn't a third-party system
   requiring credential isolation or a protocol boundary. Wrapping it in MCP adds a network hop and a protocol layer
   for no isolation benefit. (If Qdrant is ever exposed to *other* internal teams/services beyond this agent, revisit
   this via an ADR — that would be a legitimate reason to front it with MCP.)
6. **Should Google Drive/Notion retrieval happen through MCP?** Yes — these are exactly the case MCP is for:
   permissioned, credentialed, third-party systems where you want a standard tool-calling interface, swappable
   without touching agent logic, and where each tenant's OAuth token must stay scoped and isolated.
7. **Credential isolation:** each tenant's OAuth tokens/API keys for each connector are stored encrypted, keyed by
   `(tenant_id, provider)`, in a dedicated credentials table/secret store — never in application code, environment
   variables shared across tenants, or logs. The MCP client resolves credentials for the *current authenticated
   tenant only*, injected by the host — the LLM's tool-call arguments never carry or select a tenant/credential.
8. **Multi-tenant isolation:** one Qdrant collection per tenant (simplest to reason about, trivial to delete on
   offboarding); one credentials row-set per tenant; MCP server instances are stateless and receive tenant-scoped
   credentials per call rather than holding a single shared session.
9. **Tool permission handling:** each tool declares the minimum scope it needs (e.g., read-only Drive scope, not
   full Drive access); tool input schemas are strictly validated (Pydantic, `extra="forbid"`); tool output is size-
   capped before re-entering the LLM context; every call is audit-logged (tool, tenant, duration, success) without
   logging raw content.
10. **When MCP should NOT be used:** for the vector store (see Q5); for purely internal, same-process business logic
    that has no permission/credential boundary; for anything that would need sub-100ms latency inside a hot request
    path where a protocol hop isn't justified; and never as a substitute for RAG — MCP is how you *fetch* data from a
    system, RAG is how you *retrieve the relevant slice* of already-ingested data. They're complementary, not
    interchangeable.

**Corrected example flow** (the brief's original diagram was directionally right; tightened below to name each hop
correctly):

```
User: "Find the contract terms for Client X from 2025."
        │
        ▼
Agent Orchestrator (MCP Host) + LLM
        │  LLM reasons: "this needs retrieval; try vector search first"
        ▼
services/retrieval → Qdrant (tenant-filtered search for "Client X contract 2025")
        │
        ├─ If a strong match is found → use it, cite it, done.
        │
        └─ If recall is weak / user named a specific live document →
                 ▼
              MCP Client → MCP Server (google_drive) → Google Drive API
                 │  search_files("Client X contract 2025") → get_file_content(file_id)
                 ▼
              Document content returned to Agent Orchestrator
        ▼
Context Construction (vector hits + any tool-fetched content)
        ▼
LLM generates grounded response
        ▼
Response Assembler attaches citations (Qdrant metadata and/or Drive file link)
        ▼
Answer + citations returned to user
```

---

## 3. Production-Ready Project Structure (Deliverable 3)

**Decision: Monorepo.** A single founder-engineer building an MVP benefits far more from shared types (Pydantic ↔
generated TypeScript), one CI pipeline, and atomic cross-cutting changes than from the isolation a dual-repo setup
would buy. Revisit only if/when separate teams own frontend and backend independently.

```
knowledge-agent/
├── AGENT.md                     # AI-agent operating rules (this project's "constitution")
├── Rule.md                      # engineering standards, layering rules
├── Plan.md                      # this file
├── BRD.md                       # business requirements
├── README.md
├── pyproject.toml                # uv-managed root Python project (workspace)
├── uv.lock
├── .env.example
├── apps/
│   ├── web/                      # Next.js (App Router, TS, Tailwind, shadcn) — deploys to Vercel
│   └── api/                      # FastAPI — thin HTTP layer only — deploys to Render
│       ├── main.py
│       ├── routes/
│       ├── usecases/
│       ├── dependencies.py
│       └── middleware/
├── services/
│   ├── agent/                    # orchestration: prompt construction, tool-call decisions
│   ├── retrieval/                # vector search, reranking, hybrid search
│   ├── mcp_servers/
│   │   ├── google_drive/
│   │   └── notion/
│   └── ingestion/                # standalone CLI/worker; never imported by apps/api routes
│       ├── loaders/
│       ├── parsers/
│       ├── chunker.py
│       └── cli.py
├── packages/
│   ├── core/                     # shared Pydantic schemas, enums, exceptions, TenantContext
│   ├── clients/                  # llm_client, embedding_client, qdrant_client, mcp_client
│   └── config/                   # pydantic-settings based configuration, env schema
├── infrastructure/
│   ├── render.yaml
│   ├── vercel.json
│   ├── docker/
│   └── migrations/               # Alembic migrations for Postgres (tenants, users, conversations, credentials)
├── docs/
│   └── adr/                      # Architecture Decision Records
├── scripts/                       # one-off ops scripts (backfills, tenant offboarding, etc.)
└── tests/
    ├── unit/
    ├── integration/
    └── e2e/
```

This mirrors and is authoritative alongside the layering map in `AGENT.md §3` — if the two ever drift, this file and
`AGENT.md` should be updated together.

---

## 4. Step-by-Step Development Plan (Deliverable 4)

### Phase 1 — Environment & Foundation
- **Objective:** a running, empty-but-correct skeleton: FastAPI talking to local Ollama, Next.js shell, shared config.
- **Features:** `/health`, `/api/chat` (direct-to-Ollama, no agent/MCP yet), basic Next.js chat UI calling it.
- **Files/modules:** `apps/api/main.py`, `apps/api/routes/health.py`, `apps/api/routes/chat.py`,
  `packages/config/settings.py`, `apps/web/` scaffold.
- **Tech:** `uv`, FastAPI, Ollama, Next.js, TypeScript, Tailwind, shadcn/ui.
- **Expected output:** developer can `uv run fastapi dev` + `npm run dev` and chat with a local model end-to-end.
- **Testing:** `pytest` smoke test hitting `/health` and a mocked `/api/chat`.
- **Definition of Done:** both services run locally with zero paid dependencies; `.env.example` documents every
  required variable; README documents the exact run commands.

### Phase 2 — Document Ingestion & RAG
- **Objective:** real documents become searchable, grounded context.
- **Features:** loaders/parsers for PDF & plain text, chunker, embedding client, Qdrant upsert, retrieval query
  function, citation metadata.
- **Files/modules:** `services/ingestion/*`, `services/retrieval/*`, `packages/clients/qdrant_client.py`,
  `packages/clients/embedding_client.py`.
- **Tech:** Qdrant Cloud free tier (or local Docker Qdrant for dev), `nomic-embed-text` via Ollama.
- **Expected output:** `uv run python -m ingestion.cli --tenant-id demo --source local --path ./sample_docs` ingests
  files; a retrieval function returns top-K chunks with metadata for a test query.
- **Testing:** unit tests for chunker/parsers with fixture documents; integration test against a local Qdrant
  container verifying idempotent re-ingestion.
- **Definition of Done:** re-running ingestion on the same folder does not duplicate vectors; retrieval returns
  correct citations for a hand-verified query set.

### Phase 3 — Agent + MCP
- **Objective:** the LLM decides when to retrieve vs. call a tool, and can reach Google Drive/Notion.
- **Features:** agent orchestration loop (tool-calling), MCP client, MCP servers for Drive & Notion, tool permission
  scoping, credential storage.
- **Files/modules:** `services/agent/*`, `packages/clients/mcp_client.py`, `services/mcp_servers/google_drive/*`,
  `services/mcp_servers/notion/*`, `packages/core/schemas/tenant_credentials.py`.
- **Tech:** MCP SDK, OAuth flows for Drive/Notion, Postgres for credential storage (encrypted at rest).
- **Expected output:** end-to-end: a question that needs a live Drive lookup successfully round-trips through the
  agent → MCP client → MCP server → Drive API → grounded answer with a real Drive link citation.
- **Testing:** integration tests using recorded/replayed MCP responses (no live API calls in CI); a prompt-injection
  test case (malicious text inside a fetched document must not alter agent behavior).
- **Definition of Done:** tool calls are tenant-scoped and audit-logged; a tool call with insufficient scope is
  rejected; agent falls back to "insufficient context" rather than fabricating when both retrieval and tools miss.

### Phase 4 — Frontend Integration
- **Objective:** a usable product surface.
- **Features:** chat UI with streaming, inline source citations (clickable), loading/error states, conversation
  history list, basic authentication (sign-in, tenant resolution).
- **Files/modules:** `apps/web/app/chat/*`, `apps/web/lib/api-client.ts`, `apps/api/routes/auth.py`,
  `apps/api/routes/conversations.py`.
- **Tech:** Next.js streaming (SSE), an auth provider (e.g., a managed auth service or simple JWT sessions), Postgres
  for conversation history.
- **Expected output:** a logged-in user from Tenant A sees only Tenant A's conversation history and gets streamed,
  cited answers.
- **Testing:** Playwright e2e test covering login → ask question → see cited streamed answer → click citation.
- **Definition of Done:** manual cross-tenant test confirms Tenant A cannot see or trigger retrieval against Tenant
  B's data under any UI path.

### Phase 5 — Productionization
- **Objective:** ready for a first real (paying or pilot) customer.
- **Features:** multi-tenancy hardening, full authN/authZ, secrets management, structured logging, basic monitoring/
  alerting, rate limiting, background ingestion scheduling, deployment pipeline, security hardening pass, cost
  controls (usage caps per tenant).
- **Files/modules:** `infrastructure/render.yaml`, `infrastructure/vercel.json`, `apps/api/middleware/rate_limit.py`,
  `apps/api/middleware/audit_log.py`, `docs/adr/*` documenting each hardening decision.
- **Tech:** Render (paid Starter tier for always-on), Vercel, a hosted LLM API, scheduled jobs (Render Cron or a
  simple worker + queue), an error-tracking tool with a real free tier.
- **Expected output:** deployed, always-on staging environment; a pilot tenant can be onboarded end-to-end
  (connect Drive/Notion → ingestion runs → chat works) without manual database surgery.
- **Testing:** load test at expected pilot volume; security review against the checklist in §9 below.
- **Definition of Done:** every item in the §9 Security Architecture mitigation table is either implemented or has an
  explicit, written justification for deferral.

---

## 5. Phase 1 Exact Setup Commands (Deliverable 5)

```bash
# 1. Root project
mkdir knowledge-agent && cd knowledge-agent
git init
uv init --name knowledge-agent --python 3.12

# 2. Python backend (workspace member)
mkdir -p apps/api packages/config
uv add fastapi "uvicorn[standard]" pydantic pydantic-settings httpx --directory apps/api 2>/dev/null || \
uv add fastapi "uvicorn[standard]" pydantic pydantic-settings httpx

# 3. Next.js frontend
npx create-next-app@latest apps/web --typescript --tailwind --app --eslint --src-dir=false --import-alias "@/*"

# 4. Backend dev dependencies
uv add --dev ruff pyright pytest pytest-asyncio

# 5. Frontend dependencies (shadcn/ui)
cd apps/web
npx shadcn@latest init -d
cd ../..

# 6. Environment variables
cp .env.example .env   # after creating .env.example per Deliverable 6

# 7. Start Ollama (separate terminal, once installed: https://ollama.com/download)
ollama serve

# 8. Pull the recommended local model
ollama pull qwen2.5:7b-instruct
ollama pull nomic-embed-text

# 9. Run FastAPI (from repo root)
uv run fastapi dev apps/api/main.py

# 10. Run Next.js (separate terminal)
cd apps/web && npm run dev

# 11. Test the backend
curl http://localhost:8000/health
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello, are you working?"}'
```

---

## 6. Initial FastAPI + Ollama Boilerplate (Deliverable 6)

Intentionally minimal — no agent/MCP layer yet. This evolves into `apps/api/usecases/chat.py` calling
`services/agent` once Phase 3 lands; the route itself will barely change shape (still just parse → call use-case →
return/stream), which is the point of keeping the route thin from day one.

**`apps/api/main.py`**
```python
from fastapi import FastAPI

from apps.api.routes import chat, health

app = FastAPI(title="Knowledge Agent API", version="0.1.0")

app.include_router(health.router)
app.include_router(chat.router, prefix="/api")
```

**`apps/api/routes/health.py`**
```python
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

**`apps/api/routes/chat.py`**
```python
import httpx
from fastapi import APIRouter, Depends

from packages.config.settings import Settings, get_settings
from packages.core.schemas.chat import ChatRequest, ChatResponse

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    settings: Settings = Depends(get_settings),
) -> ChatResponse:
    """Phase-1 placeholder: forwards directly to local Ollama.

    This will be replaced by a call into services/agent once the
    orchestration layer exists (Phase 3) — the route signature and
    responsibility (parse -> call one function -> return) stays the same.
    """
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{settings.ollama_base_url}/api/generate",
            json={
                "model": settings.local_llm_model,
                "prompt": payload.message,
                "stream": False,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    return ChatResponse(response=data.get("response", ""))
```

**`packages/core/schemas/chat.py`**
```python
from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(..., min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    response: str
```

**`packages/config/settings.py`**
```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    ollama_base_url: str = "http://localhost:11434"
    local_llm_model: str = "qwen2.5:7b-instruct"
    environment: str = "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

**`pyproject.toml`** (excerpt)
```toml
[project]
name = "knowledge-agent"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "pydantic>=2.8",
    "pydantic-settings>=2.4",
    "httpx>=0.27",
]

[dependency-groups]
dev = ["ruff>=0.6", "pyright>=1.1", "pytest>=8.3", "pytest-asyncio>=0.24"]

[tool.ruff]
line-length = 100
target-version = "py312"
```

**`.env.example`**
```bash
ENVIRONMENT=development
OLLAMA_BASE_URL=http://localhost:11434
LOCAL_LLM_MODEL=qwen2.5:7b-instruct

# Populated in later phases:
# QDRANT_URL=
# QDRANT_API_KEY=
# GOOGLE_DRIVE_CLIENT_ID=
# GOOGLE_DRIVE_CLIENT_SECRET=
# NOTION_CLIENT_ID=
# NOTION_CLIENT_SECRET=
# DATABASE_URL=
# HOSTED_LLM_API_KEY=
```

**How this evolves:** the `/api/chat` route's *shape* never changes — parse request, call one function, return/stream
a response. What changes underneath is that the function it calls stops being a direct Ollama HTTP call and becomes
`services.agent.orchestrator.handle_message(...)`, which internally decides whether to retrieve, call an MCP tool, or
answer directly, and which LLM client (local Ollama vs. hosted API) it uses is resolved by `packages/config`, not by
the route.

---

## 7. RAG Architecture (Deliverable 7)

```
Document → Parsing → Cleaning → Chunking → Metadata extraction → Embedding → Qdrant
```
```
User Query → Query Embedding → Vector Search → Metadata Filtering → Top-K Documents
           → Optional Re-ranking → Context Construction → LLM
```

**MVP defaults (sensible, not maximal):**

| Parameter | Default | Reasoning |
|---|---|---|
| Chunk size | ~500–800 tokens | Balances enough context per chunk against dilution; contracts/policies read well at this size. |
| Chunk overlap | 10–15% | Prevents losing meaning at chunk boundaries without excessive duplication. |
| Embedding model | `nomic-embed-text` (dev) → `BGE-M3` (prod upgrade) | Free, local, "good enough" at MVP; BGE-M3 adds hybrid dense+sparse retrieval when quality demands it — never mix embedding models between ingestion and query without re-embedding everything. |
| Metadata per chunk | `tenant_id, source, document_id, title, url, chunk_index, ingested_at` | Sufficient to build a citation with zero extra lookups. |
| Top-K | 5–8 | Enough context without blowing the prompt budget on a small/mid-size LLM. |
| Filtering | Always filter by `tenant_id`; optionally by `source` or date range if the query implies it | Tenant isolation is not optional; source/date filters improve precision for "last year's terms"-style queries. |
| Re-ranking | Skip at MVP; revisit if top-K precision is visibly poor | Adds latency and complexity — only justified once real usage shows vector similarity alone isn't precise enough. |
| Hybrid search (dense + keyword/sparse) | Defer until BGE-M3 upgrade (it supports hybrid natively) | Avoids running two separate retrieval systems at MVP. |
| Citation tracking | Attach chunk metadata to every context item fed to the LLM; response assembler maps cited claims back to source metadata | Citations must trace to real retrieved data, never be generated from the LLM's memory. |

**Sources consulted for embedding-model comparison:** independent 2026 embedding-model benchmarking roundups
comparing Qwen3-Embedding, Gemini Embedding, Voyage-4, BGE-M3, and Nomic Embed v2 on MTEB/retrieval scores — used here
only to justify the self-hosted, zero-cost pick for this project's constraints, not as an endorsement of any vendor.

---

## 8. Multi-Tenant SaaS Architecture (Deliverable 8)

```
Tenant A                              Tenant B
 ├── Users (Postgres, tenant_id FK)    ├── Users
 ├── Documents (metadata, Postgres)    ├── Documents
 ├── Qdrant collection: tenant_a       ├── Qdrant collection: tenant_b
 ├── MCP credentials (encrypted,       ├── MCP credentials (encrypted,
 │      keyed by tenant_id+provider)   │      keyed by tenant_id+provider)
 └── Conversations (Postgres)          └── Conversations
```

- **Tenant IDs:** every table has a non-nullable `tenant_id`; every request resolves a `TenantContext` once (from the
  verified auth token) and threads it explicitly through every function call — never inferred from a body/query
  parameter the client controls.
- **Authorization:** role check (admin vs. member) happens after tenant resolution, in the use-case layer, not
  scattered across routes.
- **Database isolation:** shared Postgres instance at MVP with `tenant_id` on every row and a repository layer that
  makes "forgetting the filter" structurally hard (helper functions always require a `TenantContext` argument);
  revisit schema-per-tenant only if a specific customer's compliance requirement demands it.
- **Qdrant collection/namespace strategy:** one collection per tenant at MVP scale. Simpler to reason about,
  trivially deletable on offboarding, and avoids any chance of a missing filter leaking data. Revisit (e.g., a
  shared collection with mandatory payload filters) only if collection count itself becomes an operational problem
  at meaningfully higher tenant counts.
- **Metadata filtering:** every Qdrant query includes a `tenant_id` filter as defense-in-depth even with per-tenant
  collections (belt-and-suspenders in case of a future migration to a shared collection).
- **Credential isolation:** OAuth tokens/API keys stored encrypted at rest, keyed by `(tenant_id, provider)`; decrypted
  only inside the MCP client at call time, scoped to the current request's tenant.
- **Preventing cross-tenant retrieval:** structurally, not just by convention — a retrieval function that cannot
  construct a query without a `TenantContext` object makes the unsafe path unrepresentable in code, not just
  discouraged by a rule.
- **Audit logging:** every retrieval call, every MCP tool call, and every credential access is logged with
  `tenant_id, user_id, action, resource_identifier, timestamp, success/failure` — never the raw content.

---

## 9. Security Architecture (Deliverable 9)

| Risk | MVP-appropriate mitigation |
|---|---|
| Authentication | Managed auth provider or well-tested JWT session flow; no home-rolled password hashing. |
| Authorization | Role checks in the use-case layer; deny-by-default on any new route. |
| Multi-tenancy leakage | Structural `TenantContext` requirement on every data-access function (§8). |
| OAuth credentials | Encrypted at rest, scoped per tenant+provider, minimum requested scopes (read-only where possible). |
| API keys / secrets | Environment variables / secrets manager only; never committed; rotated on suspected exposure. |
| Prompt injection | Treat retrieved/tool content as data, not instructions; instruct the LLM explicitly to ignore
embedded directives in retrieved text; keep tool outputs size-capped. |
| Data exfiltration via tool abuse | Narrow, purpose-built tools only (no generic "run arbitrary query" tool); output
size caps; audit logging of every call. |
| Malicious documents | Parse defensively (timeouts, size limits, sandboxed parsing libraries); never execute
content extracted from a document. |
| MCP tool abuse | Tenant-scoped credentials injected by the host, never trusted from model output; least-privilege
scopes per tool. |
| Excessive tool permissions | Each tool requests the minimum API scope needed; review scopes whenever a new tool is
added. |
| Logging sensitive information | Structured logs exclude prompts, document bodies, and credentials by rule
(`Rule.md §3`); redact known PII fields. |
| Vector-store data leakage | Per-tenant collections + mandatory filters (§8); no shared embeddings across tenants
ever. |
| Cross-tenant retrieval | Structural `TenantContext` requirement (§8); tested explicitly in Phase 4 e2e tests. |
| SSRF | Allowlist destination hosts for any outbound fetch tool (Drive/Notion domains only). |
| Rate limiting | Per-tenant request rate limit on LLM-triggering endpoints from Phase 5 onward; simple in-memory or
Redis-backed limiter is sufficient at MVP scale. |
| Audit logging | Centralized structured log of every retrieval, tool call, and credential access (§8). |

Enterprise-grade additions (SOC 2 controls, dedicated per-tenant infrastructure, formal DLP) are explicitly deferred
per `BRD.md §5 Non-Goals` — the architecture above does not preclude adding them later.

---

## 10. Cost Analysis (Deliverable 10)

**Assumptions stated explicitly — these are planning estimates, not quotes.** Verify current pricing/limits with each
vendor before committing a customer-facing budget; free-tier terms change.

### Development: $0
- Local LLM + embeddings via Ollama on existing hardware.
- Local or free-tier Qdrant.
- Free tiers of every hosting service (Vercel, Render, Qdrant Cloud) for a personal/dev project.

### MVP Production (what free tiers plausibly cover)
- **Vercel:** generous free tier for a low-traffic Next.js frontend — realistically $0 for a first pilot tenant.
- **Qdrant Cloud free tier:** a single-node cluster with roughly 1 GB RAM / 4 GB disk and a monthly inference-token
  allowance — sufficient for a modest first tenant's document set, tight beyond that.
- **Render:** free web-service tier works for a demo but spins down after 15 minutes idle (30–60s cold start) and is
  capped at 750 instance-hours/workspace/month; a real customer expecting an always-on tool should sit on the
  Starter paid tier (~$7/month) instead.
- **Postgres:** Render's free Postgres expires ~30 days after creation with a grace period — not viable long-term;
  budget for a small managed Postgres (or Render's paid tier) once you have a real tenant.
- **LLM API (production):** pay-per-token hosted API; cost scales with usage, not a fixed fee — the single biggest
  variable cost as usage grows.

### Growing Production (costs that appear with more usage)
- Qdrant: moving off the free tier once RAM/disk or the inference-token allowance is exceeded — usage-based pricing
  from there (no published flat rate; use the vendor's calculator).
- Render: moving to Standard/Pro tiers as concurrency and background-job needs grow (roughly $25–85/month per
  service tier, before add-ons).
- LLM API token spend: the dominant marginal cost per additional customer/query volume.
- Postgres: a managed instance with backups (roughly $15–90/month depending on tier).

### Approximate Monthly Cost Model (illustrative, assumptions stated)

| Customers | Vercel | Render (API) | Postgres | Qdrant | LLM API tokens (est.) | Rough total |
|---|---|---|---|---|---|---|
| 1 | $0 | $0–7 | $0–15 | $0 | $5–20 | **~$5–40/mo** |
| 10 | $0–20 | $25 | $19 | $0–~50 (usage-based) | $50–150 | **~$100–250/mo** |
| 100 | $20+ | $85+ | $90+ | usage-based, likely $150–400 | $500–2,000+ | **~$800–2,500+/mo** |

Assumptions: modest document volume per tenant (hundreds–low thousands of chunks), moderate query volume per user per
day, and a mid-tier hosted LLM's per-token pricing. Re-derive this table against live vendor pricing before quoting a
customer.

---

## 11. Technology Decisions (Deliverable 11)

| Component | Recommended Choice | Alternative | Reason |
|---|---|---|---|
| LLM (dev) | Ollama + `qwen2.5:7b-instruct` (or `qwen3:8b`) | `gpt-oss:20b` (MoE) for reasoning-heavy tests | Fits fully in an 8 GB-class GPU with headroom for the rest of the dev stack on 16 GB RAM; reliable tool-calling. |
| LLM (prod) | Hosted production-grade API via a provider-agnostic client | Self-hosted GPU inference | Ollama is a dev tool; production needs uptime/scaling guarantees a single dev GPU can't provide. |
| Embeddings | `nomic-embed-text` (dev) → `BGE-M3` (prod) | Hosted embedding API (e.g., a commercial embeddings endpoint) | Free, self-hosted, no per-token cost; BGE-M3 adds hybrid retrieval when needed without a rewrite. |
| Vector DB | Qdrant Cloud (free tier → paid) | pgvector (if already running Postgres and want one fewer service) | Purpose-built vector engine, generous free tier, clean tenant-per-collection model; pgvector is the right call only if operational simplicity outweighs vector-search-specific features. |
| Graph DB | None at MVP | Neo4j Community/Free (only if relationship queries prove necessary) | No demonstrated retrieval failure justifies the added operational surface yet (see §12). |
| Backend | FastAPI + `uv` | Django/DRF | FastAPI's async-first design and Pydantic integration fit an LLM-calling, I/O-bound workload better than a sync-first framework. |
| Frontend | Next.js (App Router) + Tailwind + shadcn/ui | Remix | Best-supported by Vercel (the chosen deploy target) with the strongest ecosystem for streaming UIs. |
| MCP | Custom MCP servers per connector (Drive, Notion) behind a shared MCP client | Direct SDK calls per connector, no protocol layer | MCP gives a standard tool-calling interface and swappability without touching agent logic — the whole point of the architecture. |
| Auth | Managed auth provider (e.g., a hosted auth service) or vetted JWT-session library | Home-rolled auth | Security-critical, low differentiation — don't build it yourself at MVP. |
| Background Jobs | Simple scheduled worker (Render Cron / a lightweight queue table) | Celery + Redis / a message bus | A message bus is overkill at MVP volume (see §12); a scheduled worker polling a jobs table is enough. |
| Deployment | Vercel (frontend) + Render (backend) | Fly.io / Railway | Matches the brief's target and each has a genuinely usable free tier for a solo founder; revisit only if Render's paid-tier economics stop making sense at scale. |

---

## 12. What NOT to Build Initially (Deliverable 12)

| Deferred item | Why |
|---|---|
| Graph database | No concrete retrieval failure yet demonstrates that relationship-traversal beats vector search for this product; add it only when a real query pattern (e.g., "everyone who touched this deal") proves vector search insufficient. |
| Complex agent frameworks (heavy multi-step planning libraries) | A single orchestration loop (retrieve → maybe call a tool → generate) covers the MVP's needs; a framework adds abstraction and debugging overhead before there's a reason for it. |
| Kubernetes | One backend service on Render and one frontend on Vercel don't need container orchestration; revisit only at a scale where Render's service model genuinely can't keep up. |
| Microservices split (beyond the internal module boundaries already defined) | The layering in `Rule.md §2` already gives clean separation of concerns inside one deployable API service — splitting into separately deployed services multiplies operational cost with no MVP benefit. |
| Event buses (Kafka/RabbitMQ-style) | Ingestion jobs and sync schedules are low-volume and tolerate a simple polling worker; introduce a real message bus only if job volume/latency requirements outgrow that. |
| Multiple vector databases | One vector DB (Qdrant) is enough; running two adds consistency and operational burden for no MVP benefit. |
| Complex memory systems (long-term user memory beyond conversation history) | Conversation history in Postgres is sufficient; sophisticated memory/personalization is a post-MVP feature. |
| Fine-tuning | Off-the-shelf instruct models with good RAG grounding solve this problem; fine-tuning adds cost and MLOps burden without a demonstrated quality gap that grounding can't close. |
| Multi-agent systems | A single orchestrator with tool-calling is sufficient for "answer a question using retrieval and a couple of connectors" — multi-agent coordination solves a different, harder problem this product doesn't yet have. |

Any of these can be revisited — but only via a written ADR justifying the specific, observed need, per `Rule.md §11`.

---

## 13. Final MVP Architecture (Deliverable 13)

```
                         ┌─────────────────────┐
                         │      Next.js UI      │
                         │       (Vercel)       │
                         └──────────┬───────────┘
                                    │ HTTPS / SSE (streamed, cited answers)
                                    ▼
                         ┌─────────────────────┐
                         │     FastAPI API      │
                         │  (Render — thin      │
                         │   routes only)        │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │  Agent Orchestrator   │
                         │ (services/agent)      │
                         └─────────┬────────────┘
                                   │
                 ┌─────────────────┼─────────────────┐
                 ▼                                     ▼
        ┌─────────────────┐                  ┌───────────────────┐
        │       LLM         │                  │    MCP Client      │
        │  Ollama (dev) /    │                  │(packages/clients)   │
        │  hosted API (prod) │                  └─────────┬──────────┘
        └─────────────────┘                                │
                 │                                          ▼
                 │                                ┌───────────────────┐
                 │                                │    MCP Server(s)    │
                 │                                │ google_drive/notion  │
                 │                                └─────────┬──────────┘
                 │                                          │
                 │                          ┌───────────────┴───────────────┐
                 │                          ▼                                 ▼
                 │                   Google Drive                          Notion
                 │                (tenant-scoped OAuth)             (tenant-scoped OAuth)
                 ▼
        ┌─────────────────────┐
        │  services/retrieval   │──────▶ ┌─────────────────┐
        │ (internal call, not    │        │     Qdrant        │
        │  MCP — see §2 Q5)      │        │ (per-tenant        │
        └─────────────────────┘        │  collection)         │
                                          └─────────────────┘

        ┌─────────────────────┐        ┌─────────────────────┐
        │      Postgres          │        │ services/ingestion    │
        │ (tenants, users,       │◀──────▶│ (independent worker/  │
        │ conversations,          │  jobs  │  CLI — writes to      │
        │ credentials, job       │        │  Qdrant, never called │
        │ status)                │        │  from an API route)   │
        └─────────────────────┘        └─────────────────────┘
```

**Corrections vs. the brief's original sketch:** Qdrant is shown as an internal dependency of the retrieval layer,
not a peer sitting unconnected next to the MCP servers — it's reached from `services/retrieval`, not from the MCP
client, per the §2 Q5 decision. Postgres and the ingestion worker are made explicit (the original diagram omitted
conversation storage and ingestion entirely, even though both are required by the functional requirements in
`BRD.md §6`). Ollama is explicitly labeled dev-only, with the hosted API as its production counterpart behind the
same client interface.

---

## Sources Consulted

- Render's official free-tier documentation and independent 2026 pricing trackers, for spin-down behavior, 750
  instance-hours/month, and free Postgres expiration terms.
- Qdrant's official pricing/free-tier documentation and independent 2026 pricing trackers, for free-tier cluster
  specs (single node, ~0.5 vCPU/1 GB RAM/4 GB disk) and inference-token allowance.
- Independent 2026 local-LLM hardware-fit guides, for sizing a 7–8B dense model vs. a sparse-MoE model against an
  8 GB-class consumer GPU and 16 GB system RAM.
- Independent 2026 embedding-model benchmarking roundups (MTEB-based), for comparing self-hosted options
  (Nomic Embed, BGE-M3, Qwen3-Embedding) against hosted APIs.

Recheck all vendor-specific figures above (pricing, free-tier limits, model availability) before finalizing a
customer-facing budget or a production deployment — they are current as of this document's research date
(September 2026) and are the kind of detail that changes without notice.
