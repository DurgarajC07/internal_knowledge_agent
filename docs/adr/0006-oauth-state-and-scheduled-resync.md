# 0006 — Signed-JWT OAuth state, and Render Cron over a persistent worker

## Status
Accepted. Closes the FR-6 gap noted after the first full build pass (see
`docs/adr/0001`–`0005` for the earlier round of MVP scope decisions).

## Problem
FR-6 requires an admin to connect Google Drive/Notion via OAuth, with
periodic re-sync into the vector store. Two sub-problems needed a decision:

1. The OAuth callback (`GET /api/connectors/{provider}/callback`) is an
   unauthenticated browser redirect from Google/Notion — it carries no
   Bearer token, only `code` and `state`. Something has to bind that
   callback back to the tenant/user that started the flow, without trusting
   a client-controlled value (Rule.md §6).
2. "Periodically re-syncs" needs *something* to run on a schedule. Plan.md
   §11 names two acceptable MVP options ("Render Cron or a lightweight queue
   table"); Plan.md §12 explicitly rules out a message bus/persistent worker
   without an ADR.

## Decision

**OAuth state:** `packages/clients/auth_tokens.py` signs a short-lived (10
minute) JWT carrying `tenant_id`, `user_id`, and `provider`, with a `typ:
"oauth_state"` claim. `apps/api/usecases/connectors.py` mints it in
`start_authorize` and verifies it in `complete_authorize`; the callback
route (`apps/api/routes/connectors.py`) never reads tenant identity from a
query parameter. The existing session-JWT signer (`create_access_token`) was
also given a `typ: "session"` claim and now rejects tokens without it — the
two token kinds share a signing secret, so without this a stolen state token
(designed to survive only minutes in a URL) could otherwise be replayed as a
long-lived session token, or vice versa (see
`tests/unit/packages/test_auth_tokens.py`'s type-confusion tests).

**Scheduling:** `services/ingestion/scheduler.py` is a single script that (1)
enqueues an `ingestion_jobs` row for every (tenant, connected provider) pair
overdue for resync, then (2) drains every currently-PENDING row — including
ones an admin queued manually via `POST /api/connectors/{provider}/sync`,
which only ever inserts a row (Rule R-1). It runs to completion and exits;
`infrastructure/render.yaml` schedules it as a Render Cron job every 6 hours
(`INGESTION_RESYNC_INTERVAL_HOURS`). There is exactly one new ingestion
entrypoint, not a separate "worker" plus "scheduler" — a manual "Sync now"
click is picked up by the next cron tick rather than processed instantly.

## Alternatives considered
- **DB-backed state (a `pending_oauth_flows` table)** instead of a signed
  JWT: works, but needs a cleanup job for abandoned/expired rows and a write
  on the hot path of every "Connect" click for no isolation benefit over a
  signature check. Rejected in favor of the stateless signed token, mirroring
  how session auth already works in this codebase.
- **A persistent worker process (Celery+Redis, or a bespoke poll loop)** for
  instant processing of manual syncs: explicitly the kind of infrastructure
  Plan.md §12 says not to add without a demonstrated need. Rejected — cron
  latency (up to the resync interval) for a manual "Sync now" click is an
  acceptable MVP tradeoff, not a correctness issue.

## Consequences
- A "Sync now" click doesn't run immediately; the UI's job list will show it
  `pending` until the next scheduled run. If pilot feedback says this is too
  slow, the fix is to shorten the cron interval or add a second, more
  frequent cron entry dedicated to draining pending jobs — not to introduce
  a queue/message bus.
- Both the web service and the cron job need the **same**
  `JWT_SECRET_KEY`/`CREDENTIAL_ENCRYPTION_KEY` — `infrastructure/render.yaml`
  marks these `sync: false` (manually set, not auto-generated per service) to
  make that explicit.
