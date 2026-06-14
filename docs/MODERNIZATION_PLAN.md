# Kontext Testing Bot — API Contract Sync & Modernization Plan

**Date:** 2026-06-14
**Branch:** `chore/api-contract-sync-2026-06-14`
**Driver:** The `mira-kontext-api` surface grew significantly (entity clustering, MCP
server, change feed, projects CRUD, connector sync-runs, collection grants, quota
metering) while this CLI stayed on the older REST contract. See `mira-kontext-api`
ADR 0005 (`docs/decisions/0005-kontext-integration-pipeline.md`) for the target
pipeline and the REST-vs-MCP role split this plan aligns to.

---

## Phase 0 — Unblock (DONE on this branch)

Minimal changes so the CLI works against the current API again:

- **`models.py`** — `ContextItem` now declares `related_items` (cross-source cluster,
  API WI-5/WI-6) and a `RelatedContextItem` model. Response-parsed models
  (`ContextItem`, `QueryResult`, `MemoryMessage`) switched from `extra="forbid"` to
  `extra="ignore"`, so **additive** server fields never break the CLI again
  (mirrors AGENTS.md §1.2 forward-compatibility — old clients must read new responses).
  Request/local models keep `extra="forbid"`.
- **`config.py`** — default `KONTEXT_API_URL` corrected `8080` → `7070` (the canonical
  local port in the API's docker-compose and `.env.example`).

Root cause of the breakage: every `/v1/query` response now serializes
`related_items: []`, which the old `extra="forbid"` `ContextItem` rejected — failing
in the bot's response parser, not the API.

---

## Phase 1 — Query parity (small)

The query path works again but doesn't expose new capabilities:

- [ ] Add `group_by_entity: bool` to `KontextClient.query()` and a `/query --group`
      flag / chat affordance; render `related_items` (cluster siblings) in chat output.
- [ ] Surface `permission_counters` denials (e.g. `denied_not_participant`,
      `denied_source_collection`) in `/query` output for ACL debugging.
- [ ] Read and display quota/plan-tier headroom response headers (API `cda4b8e`,
      `9360ff4`) in `/status`.

## Phase 2 — New read surfaces (medium)

- [ ] **Change feed** — `GET /v1/changes` (`since` cursor). New `/changes` command to
      tail `content.upserted` / `acl.changed` events; useful for "did my sync land?".
- [ ] **Projects CRUD** — `GET/POST/PATCH/DELETE /v1/projects`. Today the bot only
      creates projects implicitly via memory writes; wire `/project` to the real API.
- [ ] **Documents** — confirm `/v1/documents/{short_id}` body fields against
      `DocumentItem` (now `content_type`, `body`, `metadata`).

## Phase 3 — Ingest alignment (medium)

- [ ] The real Teams/Slack path is **`POST /v1/sync-runs`** (connector ingest), not the
      single-record `/v1/ingest/records` the bot uses for dev probes. Add an optional
      `sync-run` probe command that opens a run, posts records, finalizes — so the CLI
      can smoke-test the actual connector contract end-to-end.
- [ ] **Collection grants** — role-based grants landed (`5392b84`, `sources.py` POST
      routes). Add commands to grant/inspect collection access for ACL test scenarios.

## Phase 4 — MCP transport (strategic; ADR 0005 P3)

ADR 0005 keeps the REST CLI as the human debug loop **and** wants MCP in the test
matrix so staging matches the production bot transport (`:7072` Streamable HTTP).

- [ ] Add an optional `kontext-bot mcp-query` subcommand that delegates to the MCP SDK
      (or reuses `mira-kontext-api/examples/reference_agent.py`) — **do not** add a
      third hand-rolled HTTP client (ADR 0005 testing policy).
- [ ] CI: run the same ACL scenario via REST (`test_query.py`) and MCP
      (`test_mcp_transport_e2e.py`) to prove parity.

---

## Resilience principle (applies to all phases)

Response-parsed models stay `extra="ignore"`; only request/local models stay
`extra="forbid"`. This keeps the CLI forward-compatible with additive API evolution
(the exact failure mode that motivated this branch) while still catching bot-side
payload bugs at construction time.
