# 0004 — Self-serve tenant signup with a JWT-session library, not a managed auth provider

## Status
Accepted (MVP). Revisit before onboarding a compliance-sensitive customer.

## Problem
`Plan.md §11` allows either "a managed auth provider (e.g., a hosted auth
service) or vetted JWT-session library." Phase 4 (`Plan.md` Development Plan)
also requires "basic authentication (sign-in, tenant resolution)" — but
without an external managed auth provider wired up, there is no way to create
the *first* user/tenant at all.

## Decision
- `POST /api/auth/register` (`apps/api/usecases/auth.py`) creates exactly one
  new `Tenant` row and its first `User` row (role `admin`) atomically, hashes
  the password with `passlib`'s Argon2 (`packages/clients/passwords.py` — a
  vetted library, never a hand-rolled hash per Rule.md §3), and issues a JWT.
- `POST /api/auth/login` verifies credentials and issues the same JWT shape.
- `packages/clients/auth_tokens.py` uses `pyjwt` (a vetted library) to
  encode/decode the session token; `apps/api/dependencies.py` resolves a
  `TenantContext` from it on every authenticated request.

## Alternatives considered
- **Managed auth provider (e.g. a hosted auth service)**: the better answer
  for a real production launch — offloads password-reset flows, MFA, session
  revocation, and compliance surface. Not adopted at MVP because it requires
  an external account/service the founder-engineer hasn't provisioned, and
  Plan.md explicitly names a vetted JWT library as an acceptable MVP
  alternative.

## Consequences
- No password-reset, email verification, or MFA flow exists yet — acceptable
  per `BRD.md §5` non-goals (no SOC2/HIPAA posture required at MVP), but must
  be revisited (ideally via swapping in a managed provider) before any
  customer in a compliance-sensitive vertical (law, HR) goes live for real.
- Token revocation is only via short expiry (`JWT_EXPIRES_MINUTES`, default
  12h) — there is no server-side session store to revoke against. Acceptable
  at MVP; a production hardening pass should add one (e.g. a `jti` denylist
  table) before Phase 5's security checklist can be marked fully done.
