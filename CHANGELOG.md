# ACP Changelog

All notable changes to ACP (Agent Communication Protocol) are documented here.

This file tracks the **high-level version history** extracted from the README.  
For per-release detailed notes, see the sections below.

← [Back to README](README.md)

---

## Unreleased — Public Release Readiness

### Added
- GitHub Actions CI for Python, Node, Go, Rust, and MkDocs.
- Dependabot configuration, issue templates, pull request template, security policy, code of conduct, editor config, and a top-level Makefile.

### Changed
- Python package metadata now matches the current relay version and builds clean sdist/wheel artifacts.
- CI now runs a stable release smoke suite covering certification, integration, reliable messaging, hybrid identity, and Python SDK tests.

### Fixed
- Relay HTTP startup no longer performs reverse-DNS lookup during bind, avoiding local startup hangs.
- Docker images now keep the HTTP API bound to `0.0.0.0` even when custom relay flags replace `CMD`.
- Push webhook delivery now executes from the SSE broadcast path instead of unreachable code.
- Reliable messaging tests use the active Python interpreter and explicit HTTP ports for deterministic CI runs.
- MkDocs strict builds now pass after fixing stale relative links.

---

## Version History

| Version | Status | Highlights |
|---------|--------|------------|
| v0.1–v0.5 | ✅ | P2P core, task state machine, message idempotency |
| v0.6 | ✅ | Multi-peer registry, standard error codes |
| v0.7 | ✅ | HMAC signing, mDNS discovery |
| v0.8–v0.9 | ✅ | Ed25519 identity, Node.js SDK, compat test suite |
| v1.0 | ✅ | Production-stable, security audit, Go SDK |
| v1.1 | ✅ | HMAC replay-window, `failed_message_id` |
| v1.2 | ✅ | Scheduling metadata (`availability`), Docker image |
| v1.3 | ✅ | Rust SDK, DID identity (`did:acp:`), Extension mechanism, GHCR CI |
| v1.4 | ✅ | True P2P NAT traversal: UDP hole-punch (DCUtR-style) + signaling, three-level auto-fallback |
| v1.5 | ✅ | Hybrid identity: `--ca-cert` adds CA certificate on top of `did:acp:` self-sovereign identity |
| v1.6 | ✅ | HTTP/2 cleartext (h2c) transport binding (`--http2`); AgentCard `capabilities.http2` |
| v2.0–v2.2 | ✅ | Offline delivery queue; LAN discovery; `GET /tasks` list + filtering + offset pagination |
| v2.3 | ✅ | Python SDK `auto_stream`; `supported_transports` spec-documented; cursor pagination |
| v2.4 | ✅ | `transport_modes` top-level AgentCard field — routing topology declaration (`p2p`/`relay`); `--transport-modes` CLI flag; spec §5.4 |
| **acp-client v1.8.0** | ✅ | **Python SDK LangChain adapter** — `ACPTool` (BaseTool), `ACPCallbackHandler`, `create_acp_tool()`; lazy import (langchain optional); `pip install "acp-client[langchain]"` |
| v2.5 | ✅ | Task event sequence spec (spec §8) — SSE Envelope required fields, 7 MUST + 2 SHOULD compliance, Named event lines, 10 integration tests |
| v2.6 | ✅ | Task `cancelling` intermediate state — two-phase cancel protocol, `capabilities.task_cancelling`, spec §3.3.1 sequence diagram, A2A #1684/#1680 differentiation |
| **v2.7** | ✅ | **AgentCard `limitations: string[]`** — tri-part capability boundary declaration (`capabilities` + `availability` + `limitations`); `--limitations` CLI flag; backward-compatible; ref A2A #1694 |
| v2.8 | ✅ | `GET /skills/query` — constraints filter (`input_mode`/`output_mode`/`tag`/`name`); skill examples field; SkillCard v2 schema |
| v2.9 | ✅ | DID identity document (`did:acp:` + `did:key:`); `/.well-known/did.json`; Ed25519 identity persistence; `GET /identity` |
| v2.10 | ✅ | Structured skills objects (AgentCard `skills[]` array); `/skills` endpoint; skill `input_modes`/`output_modes`/`examples` |
| v2.11 | ✅ | `/skills/query` constraints filtering; `capabilities.skill_query: true`; 15 skill tests |
| v2.12 | ✅ | `GET /ws/stream` — WebSocket native push endpoint (SSE alternative); `capabilities.ws_stream: true` |
| v2.13 | ✅ | SSE + WebSocket event replay (`?since=<seq>`) — zero data loss on reconnect; `_event_log` ring buffer |
| **v2.14** | ✅ | **`trust.signals[]`** — AgentCard structured trust evidence (4 types: `self_attested`/`third_party_vouched`/`onchain_credentials`/`behavioral`); Ed25519-signed; A2A #1628 compatible |
| **v2.15** | ✅ | **`GET /context/<id>/messages`** — multi-turn conversation context query; `since_seq`/`sort`/`limit` params; `capabilities.context_query: true`; ahead of A2A contextId proposal |
| **v2.16** | ✅ | **`delegation_chain` identity delegation** — Ed25519-signed delegation records; `POST /identity/delegate`; `GET /identity/delegation`; `capabilities.delegation_chain: true`; ahead of A2A #1696 |
| **v2.17** | ✅ | **`availability.schedule` CRON scheduling** — 5-field CRON expression; `GET /availability`; `POST /availability/heartbeat`; `capabilities.availability_schedule: true`; ahead of A2A #1667 |
| **v2.18** | ✅ | **JWKS compatibility layer** — `GET /.well-known/jwks.json` RFC 7517; `trust.signals[type=jwks]`; `capabilities.trust_jwks: true`; ahead of A2A IS#1628 |
| **v2.19** | ✅ | **NAT Auto-Traversal** — `connection_type` field in `/peers/connect` (`host`/`p2p_direct`/`dcutr_direct`/`relay`); three-level auto-fallback; `capabilities.nat_traversal: true` |
| **v2.20** | ✅ | **Structured `limitations[]`** — `LimitationObject{kind,code,message,permanent}` schema; 6 kind types (capability/modality/scale/domain/access/other); stable/runtime split; `--limitations-json` CLI; ahead of A2A #1694 |
| **v2.21** | ✅ | **Runtime limitations management** — `PATCH /.well-known/acp.json` supports `limitations` updates (replace/merge dual mode); `?filter_limitations=` query; `capabilities.limitations_patch/filter: true` |
| **v2.22** | ✅ | **`POST /peers/broadcast`** — single call broadcasts to all connected peers; per-peer delivery results; 503 ERR_NO_PEERS; `capabilities.peers_broadcast: true` |
| **v2.23** | ✅ | **Broadcast enhancement** — `target_peers[]` optional subset broadcast; `GET /peers/broadcast/history` (last 200 audit log entries, `?limit=N`); `broadcast_id` response field |
| **v2.24** | ✅ | **`GET /peers/<id>/card`** — fetch connected peer's AgentCard snapshot; `capabilities.peer_card_query: true`; no A2A equivalent |
| **v2.25** | ✅ | **`POST /peers/<id>/ping`** — application-layer heartbeat probe + RTT measurement; `acp.ping`/`acp.pong` message types; 408 ERR_PING_TIMEOUT on timeout |
| **v2.26** | ✅ | **QuerySkill constraints extension** — per-skill `constraints: {max_file_size_bytes, concurrent_tasks, context_window}`; `POST /skills/query` three-dimensional constraint check; ahead of A2A PR#1655 |
| **v2.27** | ✅ | **GET /peers pagination + vouch_chain trust signal** — `GET /peers?limit=&offset=&filter=`; trust.signals adds `vouch_chain` type (multi-level endorsement chain) |
| **v2.28** | ✅ | **Per-skill `limitations[]` field** — every skill object carries its own `limitations: LimitationObject[]`; `GET /skills?has_limitation=<kind\|code>` filter; `capabilities.skill_limitations: true` |
| **v2.29** | ✅ | **`GET /skills/<id>/status` — per-skill availability probe** — lightweight GET; `{skill_id, available, reason?, last_checked, limitations[]}`; `capabilities.skill_status_probe: true` |
| **v2.30** | ✅ | **`error_failed_msg_id` capability declaration** — `capabilities.error_failed_msg_id: true`; `failed_message_id` in error responses |
| **v2.31** | ✅ | **`PATCH /skills/<id>/limitations` — runtime per-skill limitations update** — replace/merge dual mode; empty `[]` clears overrides; `capabilities.skill_limitations_patch: true` |
| **v2.32** | ✅ | **`message_id` 30s TTL dedup window — HTTP send idempotency** — 30s window deduplicated: 200 `{ok:true, deduplicated:true}`; `capabilities.message_dedup: true` |
| **v2.33** | ✅ | **DID pubkey offline discovery** — `GET\|POST /identity/pubkey-discovery`; zero-network resolution of `did:acp:` / `did:key:` to Ed25519 pubkey; `capabilities.pubkey_discovery: true` |
| **v2.34** | ✅ | **Per-peer structured trust score — `GET /peers/<id>/trust`** — 5-dimensional weighted score (`card_sig`×0.35 + `did_consistent`×0.20 + `ping_rtt`×0.20 + `message_hist`×0.15 + `vouch`×0.10); `capabilities.peer_trust: true` |
| **v2.38** | ✅ | **Message Priority** — `POST /message:send` supports `priority: critical\|high\|normal\|low`; `GET /recv` returns priority-sorted; `capabilities.message_priority: true` |
| **v2.39** | ✅ | **Long Poll `/recv`** — `GET /recv?wait=<seconds>` (0–30s); suspends when queue empty, returns immediately on message; `capabilities.recv_long_poll: true` |
| **v2.40** | ✅ | **`agent_limitations` machine-readable constraints** — AgentCard + `/status` add `agent_limitations` object; `capabilities.agent_limitations: true` |
| **v2.41** | ✅ | **`GET /skills` OpenAPI 3.1 spec** — `docs/openapi-skills.yaml`; `AgentCard.skills_schema_url`; `capabilities.skills_openapi_spec: true` |
| **v2.45** | ✅ | **`GET /tasks` A2A v1.0 aligned pagination** — `page_size`, `after` keyset cursor, `status` multi-value filter; `capabilities.tasks_pagination: true` |
| **v2.46** | ✅ | **AgentCard `capabilities.groups`** — 5 groups (messaging/tasks/identity/transport/discovery); backward-compatible |
| **v2.80** | ✅ | **`heartbeat_period_ms`** — AgentCard declares heartbeat interval; `--heartbeat-period-ms` CLI flag; `capabilities.heartbeat_period_declared: true`; ahead of A2A #1667 |
| **v2.81** | ✅ | **`task_evidence` — task lifecycle evidence anchors** — `POST /tasks/{id}/evidence`; `GET /tasks/{id}/evidence`; `GET /tasks/{id}/evidence/latest`; `capabilities.task_evidence: true`; ahead of A2A #1721 |
| **v2.84** | ✅ | **`protocol_bindings[]` array field** — AgentCard top-level CPB URI array (A2A §5.8 aligned); backward-compatible singular `protocol_binding` retained |
| **v2.85** | ✅ | **Ed25519 identity default-on** — auto-generated keypair on first run, zero config; `capabilities.identity_default: true`; `--no-identity` escape hatch; 6-protocol compatibility matrix; ahead of A2A #1672 |
| **v2.86** | ✅ | **BUG-058 fix** — v2.85 Ed25519 default broke capability_token test expectations; `--no-identity` fixture fix |
| **v2.87** | ✅ | **`policy_compliance[]` — governance compliance standards field** — AgentCard top-level `policy_compliance: string[]`; `PATCH /policy-compliance`; ahead of A2A #1717 |
| **v2.88** | ✅ | **BUG-059 fix — peer card exchange race condition** — `guest_mode` peer registration moved before `_send_agent_card()`; eliminated `card_available=False` race |
| **v2.89** | ✅ | **ACP-RFC-002 — Bilateral Signed Interaction Records** — `docs/rfc/bilateral-interaction-records.md`; bilateral co-signing spec; SHA-256 hash chain; Merkle root attestation; cross-impl test vectors |
| **v2.90** | ✅ | **`POST /identity/verify-card` — offline AgentCard signature verification** — Ed25519 self-sig verification without connecting to card owner; `capabilities.offline_card_verify: true` |
| **v2.91** | ✅ | **`GET /ir/adversarial-fixtures`** — 5 self-contained JSON fixtures (AF-001–AF-005) for adversarial trust testing; direct response to A2A #1718 |
| **v2.92** | ✅ | **ACP-RFC-003 — Governance Metadata Spec** — `derivation_rights` (GDPR derivative data) + `credential_lifecycle` (session TTL + revocation policy) |
| **v2.93** | ✅ | **ACP-RFC-004 — Decentralized Agent Identity without CA** — Ed25519 self-signed identity full spec; 9-dimension comparison with A2A #1672 central CA approach |
| **v2.94** | ✅ | **Principal Diversity Defense** — `GET /trust/bilateral-ir/diversity`; collusion-pair inflation attack defense; `effective_bilateral_count`; aligned with A2A #1718 |
| **v2.97** | ✅ | **`--persist-queue` SQLite durable offline queue** — messages survive relay restarts; A2A #1667 offline-first requirement |
| **v2.98** | ✅ | **`POST /tasks/queue` async task enqueue (202 Accepted)** — returns `task_id`+`poll_url`+`sse_url` immediately; A2A #1667 trilogy |
| **v2.99** | ✅ | **`--max-offline-ttl` expiry policy** — auto-clean offline queue messages past TTL (drop/notify dual strategy); `POST /offline-queue/sweep` |
| **v3.0** | ✅ | **Per-message Ed25519 signature (`msg_sig`)** — `_sign_message()` + `_verify_message_sig()`; `POST /verify/message` third-party verification; `capabilities.msg_sig: true` |
| **v3.1** | ✅ | **`origin_proof` — recipient-bound Ed25519 signature** — canonical includes `to` field; prevents replay-to-wrong-recipient attacks; `capabilities.origin_proof: true` |
| **v3.2** | ✅ | **W3C DataIntegrityProof compatibility layer** — `Ed25519Signature2020` proof object; `POST /verify/proof` endpoint; `capabilities.data_integrity_proof: true` |
| **v3.3** | ✅ | **Capability Token passthrough & OBO Authorization** — `capability_token` passthrough (A2A #1716 compatible); `POST /capability/issue`; OBO extension fields; `capabilities.capability_token: true` |
| **v3.4** | ✅ | **AgentCard `governance` block** — `/status` top-level governance object (`framework`/`version`/`credential_lifecycle`/`audit_mode`/`policy_ref`); A2A #1717 `CredentialLifecyclePolicy` aligned |
| **v3.5** | ✅ | **Governance Proof Suite & Transport Bindings** — `governance.proof_suite` declares signing suite; `AgentCard.transport_bindings` (`supported`/`experimental`); `capabilities.transport_bindings: true` |
| **v3.6** | ✅ | **P1 Bug Fixes (stable release)** — multi-peer send (`peer_ids` list, true multicast); SSE zero-latency (<50ms); connect idempotency (link token dedup); all P0/P1 bugs cleared |
| **v3.7** | ✅ | **CI Stress Test + Authorization Hook** — `test_scenario_d.py` 20-msg burst; P99 latency assertion; `_check_authorization()` stub for A2A #1716 watchlist |
| **v3.8** | ✅ | **Heartbeat-Agent three-piece closure (A2A IS#1667)** — `GET /offline-queue/summary`; `--heartbeat-agent` CLI flag; `capabilities.heartbeat_agent`; complete 5-step workflow |
| **v3.9** | ✅ | **Topic-based Pub/Sub subset (A2A #1196)** — subscribe/unsubscribe/broadcast/topics; `capabilities.topic_broadcast: true`; first working reference implementation of A2A Pub/Sub Primitives proposal |
| **v3.10** | ✅ | **Multi-relay Federation** — `GET /federation`; `POST /federation` (idempotent); `POST /federation/route`; offline-queue fallback; `capabilities.federation: true` |
| **v3.11** | ✅ | **Async Task Queue Workers** — `POST /tasks/queue/worker` (register callback_url + filters, idempotent); `GET /tasks/queue/workers`; `DELETE /tasks/queue/worker/{id}`; auto-dispatch on enqueue; `capabilities.task_queue_worker: true` |
| **v3.12** | ✅ | **Governance Compliance Report (A2A #1717)** — `AgentCard.governance` adds `compliance_report`/`last_verified_at`/`operator_attestation`; `GET /governance/compliance`; `POST /governance/compliance`; `capabilities.governance_compliance: true` |
| **v3.13** | ✅ | **Governance Audit Endpoint (A2A #1717 `auditEndpoint` first implementation)** — `GET /governance/audit` (structured IR query; `?limit=`/`?peer_id=`/`?task_id=`/`?since=` filters); `governance_metadata.audit_endpoint`; `capabilities.governance_audit: true` |
| **v3.14** | ✅ | **`skill_trust_score` evidence-based composite + `application/acp+json` media type** — P1: `skill_trust_score` struct (`composite`/`evidence`/`last_calculated`) in `/skills`, `/skills/<id>/status`, `/skills/query`; `min_trust_score` filter in `POST /skills/query`; `capabilities.skill_trust_score: true`. P2: `application/acp+json; charset=utf-8` Content-Type when client sends `Accept: application/acp+json`; requests with `Content-Type: application/acp+json` accepted as equivalent to `application/json`; `capabilities.acp_json_media_type: true` (A2A `application/a2a+json` SHOULD aligned) |
| **v3.15** | ✅ | **Batch Message Send (`POST /messages:batch`)** — atomic multi-message enqueue with per-message results (`ok`/`message_id`/`error`); `atomic: true` flag for all-or-nothing semantics; batch size limit 100; `capabilities.batch_message: true`; 7 integration tests |
| **v3.16** | ✅ | **Message ACK Protocol** — `acp.ack` auto-reply; `require_ack=true` on `POST /message:send`; `ack_timeout_ms` param (default 5s, max 30s); `ERR_ACK_TIMEOUT` 408; ACK transparent to `/recv`; `capabilities.message_ack: true` |
| **v3.17** | ✅ | **`POST /messages:stream` WebSocket streaming inlet** — persistent WS connection; per-frame routing with `{ok,message_id,server_seq}` ack; `ERR_PEER_NOT_FOUND` on missing peer; invalid JSON gracefully handled; completes reliable-messaging trio (batch v3.15 + ACK v3.16 + stream v3.17); `capabilities.messages_stream: true` |

---

## Detailed Release Notes (v3.x)

### v3.13.0 — Governance Audit Endpoint

- **`GET /governance/audit`**: Structured query interface returning interaction records audit trail (A2A #1717 `auditEndpoint` first working reference implementation).
  - Query params: `?limit=` (default 50, max 200), `?peer_id=` (exact caller filter), `?task_id=` (exact task filter), `?since=` (ISO 8601 timestamp).
  - Response: `{ok, records, total, returned, audit_endpoint, note}`.
- **`governance_metadata.audit_endpoint: "/governance/audit"`** — declared in AgentCard `governance_metadata`, auto-populated by `_build_governance_metadata()`.
- **`capabilities.governance_audit: true`** + **`endpoints.governance_audit`** declared in AgentCard.
- **Competitive comparison**: A2A #1717 (Microsoft AGT, 26 comments) discusses `auditEndpoint` REST field. ACP v3.13 is the first complete implementation (endpoint + AgentCard declaration + tests). Together with v3.12 compliance reporting, ACP's governance observability is fully closed: IR records (v2.59) → bilateral signing (v2.64) → compliance check (v3.12) → audit query (v3.13).
- 10/10 new tests (GA1–GA10) all PASS.

### v3.14.0 — skill_trust_score Evidence Composite + application/acp+json Media Type

#### P1: `skill_trust_score` — Evidence-Based Composite Trust Score

- **`skill_trust_score` field** added to three skill endpoints:
  - `GET /skills` — per-skill `skill_trust_score` object in each skill in the page
  - `GET /skills/<id>/status` — `skill_trust_score` in status response
  - `POST /skills/query` — `skill_trust_score` in single-skill query response
- **Schema** `{composite: float, evidence: {has_limitations, has_examples, has_constraints, has_status}, last_calculated: ISO8601}`:
  - `composite` — weighted sum (0.0–1.0): each of 4 evidence flags contributes 0.25
  - `has_limitations` (0.25) — `skill.limitations` is non-empty
  - `has_examples` (0.25) — `skill.examples` is non-empty
  - `has_constraints` (0.25) — `skill.constraints` has at least one non-null value
  - `has_status` (0.25) — skill has been probed via `GET /skills/<id>/status`
- **`POST /skills/query` `min_trust_score` filter** — body param `min_trust_score: float [0.0, 1.0]`; filters skills by minimum composite score; returns 400 `ERR_INVALID_REQUEST` if out of range
- **`capabilities.skill_trust_score: true`** declared in AgentCard
- **Design rationale**: A2A #1717 capability_manifest trust signals inspired this evidence-based approach. Documentation completeness is a measurable proxy for agent reliability.
- 16/16 new tests (STS1–STS10 + extras) all PASS.

#### P2: `application/acp+json` Media Type

- **Content-Type negotiation**: responses use `Content-Type: application/acp+json; charset=utf-8` when client sends `Accept: application/acp+json`; default remains `application/json` for backward compatibility
- **Request body acceptance**: `Content-Type: application/acp+json` on POST requests accepted as equivalent to `application/json` (no longer returns 415 Unsupported Media Type)
- **`capabilities.acp_json_media_type: true`** declared in AgentCard
- **Standard alignment**: A2A spec uses `application/a2a+json` SHOULD; ACP v3.14 introduces `application/acp+json` as its equivalent media type
- 8/8 new tests (AMT1–AMT8) all PASS.

### v3.15.0 — Batch Message Send

- **`POST /messages:batch`**: Atomic multi-message enqueue endpoint.
  - Request body: `{messages: [{role, parts|text, peer_id?, task_id?, context_id?, message_id?}, ...], atomic?: bool}`
  - Max batch size: 100 messages (returns 413 `ERR_BATCH_TOO_LARGE` if exceeded)
  - Per-message validation: `role` must be `"user"` or `"agent"`; either `parts` or `text` required
  - Response: `{ok, sent, total, results[], atomic}`
    - `ok`: true if all messages succeeded (or false if any failed and atomic=true)
    - `sent`: count of successfully sent messages
    - `total`: total messages in batch
    - `results[]`: per-message result with `{ok, index, message_id?, server_seq?, error?}`
    - `atomic`: echo of request flag
- **`atomic: true` mode**: When set, all-or-nothing semantics; if any message fails, `ok: false` in response (though partial results still returned for debugging)
- **AgentCard capability declaration**: `capabilities.batch_message: true`
- **Test coverage**: 7 integration tests (B1–B7) covering capability declaration, basic batch, explicit peer_id, empty batch rejection, per-item validation errors, size limits, and atomic mode

### v3.13.0 — Governance Audit Endpoint

- **`GET /governance/audit`**: Structured query interface returning interaction records audit trail (A2A #1717 `auditEndpoint` first working reference implementation).
  - Query params: `?limit=` (default 50, max 200), `?peer_id=` (exact caller filter), `?task_id=` (exact task filter), `?since=` (ISO 8601 timestamp).
  - Response: `{ok, records, total, returned, audit_endpoint, note}`.
- **`governance_metadata.audit_endpoint: "/governance/audit"`** — declared in AgentCard `governance_metadata`, auto-populated by `_build_governance_metadata()`.
- **`capabilities.governance_audit: true`** + **`endpoints.governance_audit`** declared in AgentCard.
- **Competitive comparison**: A2A #1717 (Microsoft AGT, 26 comments) discusses `auditEndpoint` REST field. ACP v3.13 is the first complete implementation (endpoint + AgentCard declaration + tests). Together with v3.12 compliance reporting, ACP's governance observability is fully closed: IR records (v2.59) → bilateral signing (v2.64) → compliance check (v3.12) → audit query (v3.13).
- 10/10 new tests (GA1–GA10) all PASS.

### v3.12.0 — Governance Compliance Report

- **`AgentCard.governance` extension** (aligned with A2A #1717, Microsoft AGT team):
  - `compliance_report` — real-time compliance summary (pass/fail/pending status for all governance policies)
  - `last_verified_at` — ISO 8601 timestamp of last explicit compliance check
  - `operator_attestation` — optional operator declaration (human-in-the-loop supervision support)
- **`GET /governance/compliance`**: Returns current compliance report (read-only, non-triggering).
- **`POST /governance/compliance`**: Triggers real-time compliance check, updates `last_verified_at` and `compliance_report`.
- **`capabilities.governance_compliance: true`** + **`endpoints.governance_compliance`** declared in AgentCard.
- **Competitive comparison**: A2A #1717 (Microsoft AGT, 24 comments) still in proposal stage. ACP v3.12 is the first working implementation with endpoints + tests.
- 12/12 new tests (GC1–GC12) all PASS.

### v3.11.0 — Async Task Queue Workers

- **`POST /tasks/queue/worker`**: Register async task queue worker.
  - Params: `callback_url` (required), `peer_id` (optional, exact filter), `skill_id` (optional, exact filter), `worker_id` (optional, client idempotency key).
  - Filter semantics: `peer_id=None` = match-all; workers with peer_id filter only receive tasks where `from_peer_id` matches exactly.
  - Idempotent: same `worker_id` re-registration → update (overwrite callback_url/filters).
- **`GET /tasks/queue/workers`**: List all registered workers with `worker_id`, `callback_url`, `peer_id`, `skill_id`, `registered_at`, `tasks_dispatched`, `active`.
- **`DELETE /tasks/queue/worker/{id}`**: Deregister worker. Unknown id returns 404.
- **Auto-dispatch**: On `POST /tasks/queue` enqueue, relay auto-dispatches to all matching workers (HTTP POST to callback_url). Dispatch envelope: `{type: "acp.task.dispatch", worker_id, task: {id, status, payload, queued_at, poll_url, sse_url}, dispatched_at}`. Response adds `workers_dispatched` field.
- **`capabilities.task_queue_worker: true`** + **`endpoints.task_queue_workers`** declared in AgentCard.
- 12/12 new tests (TQW1–TQW12) all PASS.

### v3.10.0 — Multi-relay Federation

- **`GET /federation`**: List registered federation relays. Returns `relays[]` (relay_id, peer_id, link, name, connected_at, messages_routed), `relay_count`, `capabilities.federation: true`.
- **`POST /federation`**: Register a remote relay as a federation peer. Supports `link` (acp:// format validation) + `name` (optional). Idempotent: re-registering same link returns `already_connected: true`.
- **`POST /federation/route`**: Route message to a peer on a remote relay. Params: `relay_id` (required), `target_peer_id` (required), `role`/`text`/`parts`/`message_id` (optional). Unknown relay → 404; disconnected → 503.
- **`acp.federation.route` WS message handling**: Local relay receives federated messages and delivers directly to target peer; if peer is offline, enters offline-queue (composable with `--persist-queue`).
- **`capabilities.federation: true`** + **`endpoints.federation` / `endpoints.federation_route`** declared in AgentCard.
- 12/12 new tests (FED1–FED12) all PASS.

### v3.9.0 — Topic-based Pub/Sub Subset (A2A #1196)

- **`POST /peers/subscribe/{topic}`**: Subscribe a peer to a named topic. `peer_id` can be `"self"` (relay itself) or a connected peer's id. Response: `{ok, topic, peer_id, subscribed_at}`.
- **`POST /peers/unsubscribe/{topic}`**: Idempotent unsubscribe. Returns `was_subscribed: false` if peer was not subscribed (no error).
- **`POST /peers/broadcast/{topic}`**: Publish message to all topic subscribers. No subscribers → `ok=true, delivered=0` (silent success). Message body same as `/message:send`.
- **`GET /peers/topics`**: List all active topics with `subscriber_count`, `subscriber_ids`, `published_count`, `last_published_at`, `recent_log` (last 5 entries).
- **`capabilities.topic_broadcast: true`**: AgentCard capability declaration, always true in v3.9+.
- **A2A #1196 comparison**: ACP v3.9 is the **first working reference implementation** of the A2A Pub/Sub Primitives proposal (proposal stage, 3 comments, no implementation).
- 10/10 new tests (TP1–TP10) all PASS.

### v3.8.0 — Heartbeat-Agent Three-Piece Closure

- **`GET /offline-queue/summary`**: Lightweight heartbeat-agent polling endpoint. Returns `has_messages`, `total_queued`, `peer_count`, `oldest_queued_at`, `hint` — no message content, minimal overhead, designed for cron/heartbeat scenarios.
- **`--heartbeat-agent` CLI flag**: One-click relay configuration for heartbeat mode (implies `--local-only` + `availability.mode=heartbeat`). Built-in 5-step workflow documentation.
- **`capabilities.heartbeat_agent`**: AgentCard capability declaration, `true` when `availability.mode=heartbeat/cron`.
- **Heartbeat-Agent trilogy complete**: `--persist-queue` (v2.97) + `POST /tasks/queue` (v2.98) + `GET /offline-queue/summary` (v3.8).
- **Addresses**: A2A IS#1667 (offline-first / heartbeat-agent — upstream still in discussion, ACP implemented 3+ months ahead).
- 8/8 new tests (HA1–HA8) all PASS.

### v3.7.0 — CI Stress Test & Authorization Hook Stub

- **`test_scenario_d.py`**: Local-relay 20-msg burst stress test with P99 latency assertion; fully CI-safe, zero external network dependencies.
- **`_check_authorization()` stub**: Reserved authorization hook in `ACPRelayServer`, placeholder for A2A #1716 Authorization Layer spec (watchlist, 26+ comments, awaiting spec stability).
- 48/48 tests PASS.

### v3.6 — P1 Bug Fixes (Stable Release)

- **Multi-peer send**: `/message:send` adds `peer_ids` list param for true multicast; compatible with comma-separated `peer_id` auto-split.
- **SSE zero-latency**: Event push latency reduced from ~950ms to <50ms, immediate flush.
- **Connect idempotency**: Repeated connections deduplicated by link token, consistent predictable behavior.
- All P0/P1 bugs cleared; v3.6.0 is current stable release.

### v3.5.0 — Governance Proof Suite & Transport Bindings

- **`governance.proof_suite`**: `/status` governance object adds signing suite declaration, supports `Ed25519Signature2020` and `eddsa-jcs-2022`, with W3C spec references, interoperable with ANP.
- **`AgentCard.transport_bindings`**: New `transport_bindings` field with `supported: ["http","websocket"]` declaring stable transports and `experimental: []` extension point reserved for SlimRPC (A2A #1723) and future bindings.
- **`capabilities.transport_bindings: true`**: Capability declaration flag.
- CLI `--experimental-transport <name>`: Repeatably append experimental transport bindings.
- Fully backward-compatible.

### v3.4.0 — Governance Block

- **`AgentCard.governance`**: `/status` adds top-level governance object: `framework`, `version`, `credential_lifecycle` (`ttl_seconds`/`revocation_endpoint`/`credential_ttl_seconds`), `audit_mode`, `policy_ref`.
- `credential_lifecycle.ttl_seconds` defaults to 3600 (1h); `audit_mode` supports `static` (declarative) and `live` (future REST extension).
- Aligned with A2A #1717 `CredentialLifecyclePolicy`; fully backward-compatible.

### v3.3.0 — Capability Token & OBO Authorization

- **`capability_token` passthrough**: Messages carry A2A #1716-compatible Ed25519 capability tokens; relay passes through without verification.
- **`POST /capability/issue`**: Local capability token issuance helper utility.
- **`origin_proof` OBO extension**: Cross-domain delegated authorization fields (`principal_id`/`operator_id`/`governance_framework_ref`).

### v3.2.0 — W3C DataIntegrityProof

- Outbound messages carry `proof` (Ed25519Signature2020) object, interoperable with W3C standards.
- `POST /verify/proof` endpoint supports W3C format verification.

### v3.1.0 — Origin Proof

- `origin_proof`: Ed25519 signature bound to recipient peer_id, preventing replay-to-wrong-recipient attacks.

### v3.0.0 — Message Signature

- `msg_sig`: Per-message Ed25519 signature for every outbound message.

---

← [Back to README](README.md)
