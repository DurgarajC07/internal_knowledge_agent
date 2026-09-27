# 0005 — Single-page chat UI with client-side conversation switching

## Status
Accepted (MVP).

## Problem
`Plan.md` Phase 4 requires a chat UI with streaming, citations, and a
"conversation history list" that can be resumed (`BRD.md FR-8`). The obvious
routing shape is a dynamic segment per conversation (`/chat/[conversationId]`).

## Decision
`apps/web/app/chat/page.tsx` is a single client-rendered page. Selecting a
conversation in `components/chat/Sidebar.tsx` loads that conversation's detail
into local state rather than navigating to a new URL. There is no
`/chat/[id]` route.

## Alternatives considered
- **Dynamic route per conversation**: gives each conversation a shareable
  URL, which is a genuine nice-to-have. Not adopted at MVP because Next.js
  16's App Router requires `params` to be awaited as a `Promise` in every
  page/layout that uses it (a real breaking-change surface — see
  `node_modules/next/dist/docs/01-app/02-guides/upgrading/version-15.md` in
  `apps/web`), and the added routing/async-params plumbing has no BRD-required
  payoff yet: FR-8 only requires that history "can be resumed," which the
  sidebar already satisfies within one page load.

## Consequences
- Conversations aren't individually deep-linkable/shareable via URL yet.
  Adding `/chat/[id]` later is additive: move the existing state logic into a
  route-scoped component that reads `conversationId` from the awaited
  `params`, and have the sidebar `<Link>` there instead of calling
  `onSelect`.
