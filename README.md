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
| 5 — Productionization | Rate limiting, audit logging, Alembic migrations, Render/Vercel/Docker configs, OAuth connect flow + scheduled connector re-sync (FR-6) |

Deliberate MVP scope decisions are recorded in [`docs/adr/`](docs/adr/) —
read those before assuming something is a bug rather than a documented
tradeoff. `docs/adr/0006` in particular closes the one functional gap
(FR-6's OAuth connect + periodic re-sync) found after the first full pass —
FR-2 and FR-3's documented simplifications (ADR-0002, ADR-0003) still stand.

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
ollama pull qwen2.5:3b-instruct
ollama pull nomic-embed-text

# 6. (Optional) local Qdrant + Postgres instead of sqlite
docker compose -f infrastructure/docker/docker-compose.yml up -d
```

### Full Docker stack

The Compose file can run the API, Next.js web app, Qdrant, and Postgres together:

```bash
docker compose -f infrastructure/docker/docker-compose.yml up --build
```

The Compose project name is fixed to `knowledge-agent`, so use the same command
from any working directory. For an existing installation after an interrupted
startup, reconcile containers without touching named volumes:

```bash
docker compose -p knowledge-agent -f infrastructure/docker/docker-compose.yml up -d --remove-orphans
```

Do not use `docker rm -f` or `docker compose down -v` during recovery: the
named volumes contain Postgres, Qdrant, and Ollama model data.

For a fresh host, provision the external volumes once before startup:

```bash
docker volume create docker_postgres_data
docker volume create docker_qdrant_data
docker volume create docker_ollama_data
```

Open `http://localhost:3000`. The stack is intentionally sized for a small machine:
one API worker, bounded request concurrency, small database pools, and explicit per-service
memory/CPU/PID limits. The API waits for healthy Postgres and Qdrant before starting, and
all services restart unless stopped. Override values through a root `.env` file, especially
`NEXT_PUBLIC_API_BASE_URL`, `JWT_SECRET_KEY`, and `CREDENTIAL_ENCRYPTION_KEY` outside local development.

The API image is `infrastructure/docker/api.Dockerfile`; the web image uses Next.js standalone
output from `infrastructure/docker/web.Dockerfile`. Both run as non-root users.

The Docker stack includes Ollama for low-cost self-hosted inference. It pulls
`qwen2.5:3b-instruct` (Q4-class Ollama quantization by default) for chat and
`nomic-embed-text` for embeddings, keeps one model loaded, and limits parallel
requests to one to protect small hardware. Set `OLLAMA_MODEL` in `.env` before
startup to select a compatible model. The default 3B model is the recommended
low-compute balance for this local stack. A 7B instruct model remains available
through `OLLAMA_MODEL` when answer quality matters more than response time.

For a real production customer, prefer `LLM_PROVIDER=hosted` with a managed
provider as specified in `Plan.md`. If self-hosting Ollama, provide a GPU-capable
Docker runtime, persistent `ollama_data`, monitoring, and a tested pinned image
digest before exposing it to users.

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
reasonable follow-up, not yet built.

### Connecting Google Drive / Notion (FR-6)

1. Register an OAuth app with each provider and set
   `GOOGLE_DRIVE_CLIENT_ID`/`SECRET` and/or `NOTION_CLIENT_ID`/`SECRET` in
   `.env`. The redirect URI you register with the provider must exactly
   match `{API_BASE_URL}/api/connectors/{provider}/callback`.
2. As a tenant admin, visit `/settings/connectors` in the app and click
   Connect — this hits `GET /api/connectors/{provider}/authorize`, redirects
   to the provider's consent screen, and on approval the callback stores an
   encrypted credential for your tenant.
3. Click "Sync now" (`POST /api/connectors/{provider}/sync`) to queue an
   immediate ingestion job, or just wait — `services/ingestion/scheduler.py`
   re-syncs every connected tenant automatically (see
   `INGESTION_RESYNC_INTERVAL_HOURS`; on Render this runs as a Cron job, see
   `infrastructure/render.yaml`). Either way, the route only ever inserts a
   `PENDING` row — the actual sync always runs out-of-request (Rule R-1).
4. Run it manually any time with `uv run python -m services.ingestion.scheduler`.

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
