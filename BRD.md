# BRD — MCP-Powered Internal Knowledge Agent

| | |
|---|---|
| **Document** | Business Requirements Document (BRD) |
| **Product** | Internal Knowledge Agent (B2B, multi-tenant) |
| **Status** | Draft v1.0 — MVP scope |
| **Owners** | Product / Engineering (single founder-engineer at MVP stage) |
| **Related docs** | `AGENT.md` (agent operating rules), `Rule.md` (engineering standards), `Plan.md` (architecture + phased build plan) |

---

## 1. Executive Summary

Small professional-services businesses (law firms, HR/recruitment agencies, real-estate brokerages) store critical
knowledge — contracts, client histories, policies, correspondence — across disconnected tools (Google Drive, Notion,
CRMs, local files). Staff lose hours per week searching for facts that already exist somewhere in the company.

The product is an **internal chat application** that lets an employee ask a natural-language question and receive a
**grounded, cited answer** pulled from the company's own private data, without that data ever being used to train a
third-party model or leaking to another tenant. The system uses **Retrieval-Augmented Generation (RAG)** for
knowledge retrieval and the **Model Context Protocol (MCP)** as the standardized integration layer between the agent
and each external data source (Google Drive, Notion, and future connectors).

---

## 2. Problem Statement

- Company knowledge is fragmented across 3–6+ systems with no unified search.
- Existing search (Drive search, Notion search, email search) is keyword-based, not context-aware, and never spans
  multiple systems at once.
- General-purpose AI assistants (ChatGPT, etc.) cannot see private company data and cannot be trusted with it even if
  they could (no tenant isolation, no audit trail, no citation guarantee).
- Compliance-sensitive industries (law, HR) need **traceable answers** — a confident-sounding hallucination is worse
  than "I don't know."

## 3. Target Customers & Personas

| Persona | Segment | Primary need |
|---|---|---|
| Associate / Paralegal | Law firm | "What terms did we give Client X last year?" — fast contract/clause lookup with citation. |
| HR Generalist / Recruiter | HR & recruitment firm | Policy lookup, candidate history, past offer terms. |
| Agent / Transaction Coordinator | Real estate | Listing history, disclosure documents, past client communications. |
| Firm Admin (buyer) | All segments | Wants low setup effort, data never leaves their control, predictable low cost. |

## 4. Goals

1. Let an employee ask a free-text question and get an answer grounded in the firm's own documents, with source
   citations, in under ~5 seconds for a warm query.
2. Support at least two data connectors at MVP (Google Drive, Notion) through a common, replaceable integration
   layer (MCP), so new connectors can be added without touching agent/core logic.
3. Guarantee **hard tenant isolation**: Tenant A can never retrieve, see, or influence Tenant B's data, credentials,
   or conversation history.
4. Keep local development cost at **$0** (Ollama on the founder's own GPU) and MVP production cost near the
   free/lowest paid tier of each managed service (see `Plan.md §10 Cost Analysis`).
5. Ship an architecture that can evolve into a real production SaaS (multi-tenant, billed, monitored) without a
   rewrite — abstractions over LLM provider, vector DB, and connectors from day one.

## 5. Non-Goals (MVP)

- Not a general-purpose chatbot; only answers grounded in ingested company data.
- Not a document editor or workflow-automation tool (no "send this email," no CRM writes) at MVP — read-only
  retrieval only.
- Not aiming for enterprise compliance certifications (SOC 2, HIPAA) at MVP — architecture should not preclude them
  later (see `Plan.md §9 Security Architecture`).
- Not building a custom fine-tuned model; uses off-the-shelf LLMs (local for dev, hosted API for production).
- No graph database at MVP unless a concrete retrieval failure proves it's needed (see `Plan.md §12`).

## 6. Functional Requirements

| ID | Requirement |
|---|---|
| FR-1 | User authenticates and lands in a chat interface scoped to their company (tenant). |
| FR-2 | User submits a natural-language question; system streams a grounded answer token-by-token. |
| FR-3 | Every answer that uses retrieved context includes source citations (document name/link + snippet locator). |
| FR-4 | System retrieves context via vector similarity search over the tenant's ingested documents. |
| FR-5 | System can call external tools (MCP) to fetch live data (e.g., a specific Google Drive file) when vector
recall is insufficient or the query names a specific document/entity. |
| FR-6 | Admin can connect Google Drive and/or Notion via OAuth; the system ingests and periodically re-syncs
documents into the vector store. |
| FR-7 | Ingestion runs as an independent background/CLI process — never inside a user-facing request. |
| FR-8 | Conversation history is stored per user/tenant and can be resumed. |
| FR-9 | System refuses (or clearly flags) an answer when retrieved context is insufficient, rather than
fabricating an answer. |
| FR-10 | All cross-tenant data access is structurally impossible, not just filtered at the UI layer. |

## 7. Non-Functional Requirements

| Category | Requirement |
|---|---|
| Performance | P50 answer start (first token) < 3s on hosted LLM; retrieval step < 500ms P50 at MVP scale (≤ a few
thousand chunks per tenant). |
| Scalability | Must scale from 1 → 100 tenants without a core-architecture rewrite (see `Plan.md §8`). |
| Security | Tenant isolation, encrypted credential storage, least-privilege MCP tool scopes, audit logging of every
retrieval and tool call (see `Plan.md §9`). |
| Availability | MVP target: best-effort, single-region; documented cold-start behavior on free-tier hosting is
acceptable and disclosed to early customers. |
| Cost | Development: $0. MVP production: designed to fit inside free/near-free tiers for the first 1–3 customers
(see `Plan.md §10`). |
| Portability | LLM provider, vector DB, and each data connector must be swappable via configuration, not code
rewrites. |
| Auditability | Every answer must be traceable to the retrieved chunks and tool calls that produced it. |

## 8. Core User Story (Reference Flow)

> **As** a paralegal at a law firm,
> **I want to** ask "What were the exact terms we gave Client X last year?"
> **so that** I get the answer with a link to the actual contract, in seconds, without opening Drive/Notion myself.

Flow: question → agent decides retrieval is needed → vector search (+ optional MCP tool call to fetch the live file
from Google Drive) → grounded answer with citation → user clicks citation to open source document.

## 9. Success Metrics (MVP)

- ≥ 80% of test queries answered with a correct citation to the source document (manual eval set per pilot tenant).
- Time-to-answer perceived by a pilot user is faster than their manual search baseline (qualitative interview).
- Zero cross-tenant data exposure incidents in security review/pen-test before first paying customer.
- Cost per active tenant stays within the "1–10 customers" band in `Plan.md §10`.

## 10. Assumptions & Constraints

- Founder-engineer team of one at MVP stage; architecture must stay simple enough for one person to operate.
- Local dev hardware: RTX 4060 GPU, 16 GB system RAM — local LLM choice is constrained by this (see `Plan.md §1,
  §Executive Architecture Decision`).
- Initial connectors limited to Google Drive and Notion; CRM/Slack/Dropbox are explicitly deferred, not designed
  away.
- Ollama is a **local development tool only**; production inference uses a hosted, production-grade LLM API unless a
  concrete self-hosted GPU deployment is justified later.

## 11. Key Risks

| Risk | Mitigation |
|---|---|
| Hallucinated or unsourced answers in a legal/HR context | Force citation-or-refuse behavior; low-confidence retrieval returns "not found" instead of a guess. |
| Cross-tenant data leakage | Tenant ID enforced at every layer (DB row, Qdrant filter, MCP credential scope) — see `Rule.md §8`. |
| Free-tier infra limits (cold starts, storage caps) surprise early customers | Document limits transparently; design for a cheap first paid upgrade path (see `Plan.md §10`). |
| Prompt injection via ingested documents or tool output | Treat all retrieved/tool content as untrusted data, never as instructions — see `Plan.md §9`. |
| Scope creep (graph DB, multi-agent frameworks, Kubernetes) before there's a paying customer | Explicit "what not to build" list in `Plan.md §12`; any deviation requires an ADR. |

## 12. Glossary

- **RAG (Retrieval-Augmented Generation):** retrieving relevant private text and inserting it into the LLM's prompt
  so the answer is grounded in real data instead of the model's parametric memory.
- **MCP (Model Context Protocol):** an open protocol that standardizes how an AI application (**host**) exposes
  external tools/data (via an **MCP server**) to a model, through a **client** that manages one 1:1 connection per
  server. See `Plan.md §2` for the full role breakdown used in this project.
- **Tenant:** one customer company using the product; all data, credentials, and vectors are logically and/or
  physically isolated per tenant.
- **Citation:** a reference (document name, link, chunk locator) attached to a generated answer, tracing it back to
  the retrieved source.

## 13. Deliverable Traceability

Detailed architecture, diagrams, MCP design, phased plan, setup commands, RAG design, multi-tenancy, security, cost
model, technology decisions, deferred scope, and the final MVP diagram are specified in **`Plan.md`**. Day-to-day
engineering rules that enforce these requirements in code live in **`Rule.md`**. Operating instructions for any AI
coding agent implementing this BRD live in **`AGENT.md`**.
