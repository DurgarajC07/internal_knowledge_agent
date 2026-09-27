# Knowledge Agent

A multi-tenant B2B internal knowledge agent: employees ask natural-language
questions and get grounded, cited answers pulled from their own company's
documents (Google Drive, Notion, and ingested local files) via RAG, with MCP
as the integration layer to external data sources.

Full business context: [`BRD.md`](BRD.md). Architecture and phased plan:
[`Plan.md`](Plan.md). Coding standards: [`Rule.md`](Rule.md). Agent operating
rules: [`AGENT.md`](AGENT.md).

## Status

All five phases in `Plan.md §4` have a working implementation:

| Phase | What's built |
|---|---|
| 1 — Foundation | FastAPI skeleton, config, structured logging, health check |
| 2 — Ingestion & RAG | Local file loader/parser/chunker, embedding + Qdrant clients, idempotent ingestion CLI, tenant-filtered retrieval |
| 3 — Agent + MCP | Tool-calling orchestration loop, Google Drive & Notion MCP servers, encrypted per-tenant credential store, prompt-injection hygiene |
| 4 — Frontend | JWT auth (signup/login), conversation persistence, streaming chat UI (Next.js), tenant isolation enforced end-to-end |
| 5 — Productionization | Rate limiting, audit logging, Alembic migrations, Render/Vercel/Docker configs |

Deliberate MVP scope decisions are recorded in [`docs/adr/`](docs/adr/) —
read those before assuming something is a bug rather than a documented
tradeoff.

**Known limitation of this environment:** the actual LLM call (Ollama or a
hosted provider) could not be live-tested here because neither Ollama nor a
hosted API key is available in this sandbox. Everything else — auth, tenant
isolation, persistence, MCP tool dispatch, retrieval, the full test suite —
has been exercised against a real running server. Point `OLLAMA_BASE_URL` at
a real Ollama instance (or set `LLM_PROVIDER=hosted` with a real API key) to
complete that path.

## Repository layout

See `Plan.md §3` for the authoritative structure and `Rule.md §2` for the
enforced import boundaries between layers.

## Prerequisites

- [`uv`](https://docs.astral.sh/uv/) (Python 3.12+, managed automatically by `uv`)
- Node.js 20+
- [Ollama](https://ollama.com/download) for local LLM/embeddings (dev only —
  never production infrastructure, see `Plan.md` Executive Architecture Decision)
- Docker, for local Qdrant/Postgres (optional — sqlite is the zero-setup default)

## Setup

```bash
# 1. Python backend
uv sync

# 2. Environment
cp .env.example .env   # defaults work for local dev as-is

# 3. Apply database migrations (sqlite by default, zero setup)
uv run alembic upgrade head

# 4. Frontend
cd apps/web
npm install
cp .env.local.example .env.local
cd ../..

# 5. Local LLM (separate terminal)
ollama serve
ollama pull qwen2.5:7b-instruct
ollama pull nomic-embed-text

# 6. (Optional) local Qdrant + Postgres instead of sqlite
docker compose -f infrastructure/docker/docker-compose.yml up -d
```

## Running

```bash
# Backend (from repo root)
uv run uvicorn apps.api.main:app --reload

# Frontend (separate terminal)
cd apps/web && npm run dev
```

Visit `http://localhost:3000` — it redirects to `/login`. Create a workspace
(this calls `POST /api/auth/register`, creating your tenant + admin user),
then ask a question.

### Ingesting documents

Ingestion is a standalone CLI/worker, never triggered from an API route
(`AGENT.md §2.1`):

```bash
uv run python -m services.ingestion.cli \
  --tenant-id <your-tenant-uuid> \
  --source local \
  --path ./tests/fixtures/sample_docs
```

Find your tenant UUID from the JWT you got at signup (decode it, or query the
`tenants` table) — a `GET /api/tenants/me`-style convenience endpoint is a
reasonable Phase-5+ follow-up, not yet built.

## Checks (run before considering any change done — `AGENT.md §5.6`)

```bash
uv run ruff format . && uv run ruff check .
uv run pyright
uv run pytest -q

cd apps/web
npx tsc --noEmit
npm run lint
npm run build
npx playwright install chromium   # first run only
npm run test:e2e
```

## Testing philosophy

- Unit tests (`tests/unit/`) never make a real network call — every external
  client (LLM, embeddings, Qdrant, MCP/HTTP) is faked or mocked (`respx` for
  HTTP, hand-written fakes in `tests/fakes.py`). Coverage on `services/` +
  `packages/core` is enforced at 80% by `pytest`'s own config (`Rule.md §9`) —
  currently ~91%.
- Integration tests (`tests/integration/`) exercise the full FastAPI app via
  `httpx.ASGITransport` against a real (temp-file) sqlite database, with only
  the LLM/embedding/vector-store/MCP clients swapped for fakes — this is what
  proves auth, persistence, and tenant isolation actually work end to end.
- A dedicated prompt-injection test
  (`tests/unit/services/agent/test_orchestrator.py`) proves malicious text
  embedded in a retrieved document cannot alter the agent's tool-dispatch
  behavior.
- The e2e test (`apps/web/tests/e2e/chat.spec.ts`, run via `npm run test:e2e`
  in `apps/web`) drives a real browser through login → ask a question → see a
  cited streamed answer → click the citation, with the backend mocked at the
  network boundary (Playwright route interception) — the backend's own
  correctness is already covered above. It lives inside `apps/web` rather
  than the root `tests/` Plan.md sketches, because Node's module resolution
  needs it inside `apps/web`'s own dependency tree (this project isn't set up
  as an npm workspace); Python tests are unaffected and still live at the
  root `tests/`.

## Deployment

- **Backend → Render**: see `infrastructure/render.yaml`. Free tier is fine
  for a demo; move to the Starter paid tier the moment a real user depends on
  this daily (cold starts on free tier, `Plan.md §10`).
- **Frontend → Vercel**: set the project's Root Directory to `apps/web` in the
  Vercel dashboard; see `infrastructure/vercel.json` for the reference build
  config.
- **Database**: Render's free Postgres expires after ~30 days — budget for a
  paid tier before a real customer.
