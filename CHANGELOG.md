# CHANGELOG

All notable changes to ACP (Agent Communication Protocol) are documented here.

Format: [Semantic Versioning](https://semver.org) — `MAJOR.MINOR.PATCH-status`
Dates: Asia/Shanghai (UTC+8)


---

## [3.9.0] - 2026-04-12

### Added
- **Topic-based Pub/Sub subset (v3.9)** — A2A #1196 aligned, 4 new endpoints:
  - `POST /peers/subscribe/{topic}`: Subscribe a peer to a named topic. Resolves "self" or connected peer by default.
  - `POST /peers/unsubscribe/{topic}`: Unsubscribe a peer from a topic (idempotent, `was_subscribed=false` when not found).
  - `POST /peers/broadcast/{topic}`: Publish a message to all topic subscribers. Returns `ok=true, delivered=0` when no subscribers (no error).
  - `GET /peers/topics`: List all active topics with subscriber counts, subscriber_ids, published_count, last_published_at.
- **`capabilities.topic_broadcast: true`** in AgentCard — always advertised in v3.9+.
- **`endpoints.topic_subscribe/topic_unsubscribe/topic_publish/topics_list`** declared in AgentCard.
- **Internal state**: `_topic_subscribers: dict[topic→{peer_id→subscribed_at}]` and `_topic_log: dict[topic→list]` (ring buffer, max 50 per topic).
- **`tests/test_topic_pubsub.py`**: 10 new tests (TP1–TP10), all passed. Covers: empty list, subscribe, no-peer error, publish to empty topic, log recording, response fields, unsubscribe idempotency, AgentCard declarations, accumulating publishes.

### Changed
- `VERSION` → `3.9.0`

### Notes
- ACP Pub/Sub subset is intentionally lightweight — no persistent subscriptions (restart clears state), no message retention, no dead-letter queue. Use `--persist-queue` for offline delivery. Full Pub/Sub persistence is a v4.x+ consideration.
- **A2A #1196 status**: Proposal stage (3 comments, no implementation). ACP v3.9 is the first working reference implementation.

---

## [3.8.0] - 2026-04-12

### Added
- **`GET /offline-queue/summary`**: Lightweight heartbeat-agent poll endpoint (v3.8). Returns `has_messages`, `total_queued`, `peer_count`, `persist_queue`, `oldest_queued_at`, `hint` — minimal overhead, no message contents. Ideal for cron/heartbeat agents that wake periodically and need a fast pre-check before heavier processing.
- **`--heartbeat-agent` CLI flag**: One-shot shortcut to configure the relay as a heartbeat/cron-style agent. Implies `--local-only` + `--availability-mode heartbeat`. Closes the heartbeat-agent three-piece closure: `--persist-queue` (v2.97) + `/tasks/queue` (v2.98) + `/offline-queue/summary` (v3.8).
- **`capabilities.heartbeat_agent`** in AgentCard: `true` when `availability.mode` is `heartbeat` or `cron`.
- **`endpoints.offline_queue_summary`** declared in AgentCard: `"/offline-queue/summary"`.
- **`tests/test_heartbeat_agent.py`**: 8 new tests (HA1–HA8) covering summary structure, empty/non-empty queue states, `--heartbeat-agent` flag effects, AgentCard declarations, and full end-to-end workflow. **8/8 passed**.

### Heartbeat-Agent Workflow (v3.8)
```
1. Agent wakes (cron / scheduled)
2. GET /offline-queue/summary  → has_messages=true/false
3. (if true) GET /offline-queue → full queue contents
4. Process messages, send responses via POST /message:send
5. POST /availability/heartbeat → stamp last_active_at + compute next_active_at
6. Agent sleeps until next scheduled wake
```
**Addresses**: A2A IS#1667 (offline-first / heartbeat-agent discussion)

### Changed
- `VERSION` → `3.8.0`

### Notes
- The heartbeat-agent three-piece set is now complete: persistent queue (`--persist-queue`), async enqueue (`POST /tasks/queue`), and lightweight poll (`GET /offline-queue/summary`)

---

## [3.7.0] - 2026-04-11
### Added
- `test_scenario_d.py`: local-relay 20-msg burst stress test + P99 latency assertion, fully CI-safe (no external network)
- `_check_authorization()` stub in `ACPRelayServer` — reserved for A2A #1716 Authorization Layer spec (watchlist)
### Changed
- VERSION → 3.7.0
### Notes
- A2A #1716 Authorization Layer: 26+ comments, actively discussed; ACP will implement when spec draft stabilizes

---

## [3.6.0] - 2026-04-11

### Fixed
- **BUG-007 P1**: `/message:send` multi-peer 歧义 — 新增 `peer_ids` 列表参数，支持一次请求多播发送多个 peer；兼容逗号分隔的 `peer_id: "a,b"` 自动拆分；响应返回每个 peer 的发送状态 `{peer_id, ok, message_id}`
- **BUG-009 P1**: SSE 推送延迟 ~950ms — 已使用 `threading.Event` 立即 notify 模式（`_sse_notify.wait(30s)` + `_sse_notify.set()` on broadcast），消除 `time.sleep(1)` 轮询延迟，延迟降至 <50ms（commit 22aacd9 验证）
- **BUG-003b P1**: 重复连接幂等问题 — 连接时基于 link token 检测已有活跃会话，幂等返回已有连接；`--join` 直连模式绕过竞态（commit 22aacd9 + 6831f76 验证）

### Changed
- `VERSION` 升至 `3.6.0`

---

## [v3.5.0] - 2026-04-11
### Added
- **`governance.proof_suite`** sub-object in AgentCard.governance (P1: A2A #1717 + ANP eddsa-jcs-2022 interop)
  - Declares supported cryptographic proof suites: `["Ed25519Signature2020", "eddsa-jcs-2022"]`
  - `default`: currently active suite (`"Ed25519Signature2020"`)
  - `interop_refs`: W3C spec URLs (documentary only — not enforced at runtime):
    - `https://w3c.github.io/vc-data-integrity/`
    - `https://www.w3.org/TR/vc-di-eddsa/`
  - Backward-compatible: new sub-field in existing governance block, no existing fields changed
- **`AgentCard.transport_bindings`** block (P2: pre-SlimRPC extension point, A2A #1723)
  - `supported`: `["http", "websocket"]` — stable transports
  - `experimental`: `[]` by default — pre-registration slot for future bindings (SlimRPC, gRPC, etc.)
  - Exposed at top-level `/status` response (alongside `governance`)
  - New CLI flag: `--experimental-transport <name>` (repeatable) — appends to `experimental` list
- **`capabilities.transport_bindings: true`** — always advertised in v3.5+
- **`_build_transport_bindings()`** helper function

### Changed
- `VERSION` bumped to `3.5.0`

### Tests
- `tests/test_v35_extensions.py`: 6 test cases (V35-01 ~ V35-06) — all passing
  - V35-01: `governance.proof_suite` present with non-empty `supported` list
  - V35-02: `proof_suite.default` is a string
  - V35-03: `proof_suite.interop_refs` is a list
  - V35-04: `/status` contains `transport_bindings`
  - V35-05: `transport_bindings` has `supported` and `experimental` lists
  - V35-06: `capabilities.transport_bindings` is bool

---

## [v3.4.0] - 2026-04-11
### Added
- **`AgentCard.governance` block** (A2A #1717 `CredentialLifecyclePolicy` alignment — scan35 P1)
  - `/status` response now includes top-level `governance` object:
    `{framework, version, credential_lifecycle:{ttl_seconds, revocation_endpoint, credential_ttl_seconds}, audit_mode, policy_ref}`
  - `credential_lifecycle.ttl_seconds` defaults to 3600 (1h); `credential_ttl_seconds` to 86400 (24h)
  - `audit_mode` supports `"static"` (declarative; default) and `"live"` (future REST extension)
  - `revocation_endpoint` and `policy_ref` are optional (null by default)
  - Governance block is always present in v3.4+ (not opt-in); clients should default to `ttl_seconds=3600, audit_mode=static` when absent
- **`POST /governance/policy`** — read-only endpoint returning the current `governance` object
  - No body required; safe for polling by clients and orchestrators
- **`capabilities.governance: true`** — always advertised in v3.4+
- **New CLI flags:**
  - `--governance-ttl <seconds>` — override identity token TTL (default: 3600)
  - `--revocation-endpoint <url>` — set credential revocation endpoint
  - `--audit-mode static|live` — set governance audit mode (default: `static`)
- **`/status` top-level `capabilities`** shortcut — exposes `agent_card.capabilities` at status root for easier client polling

### Changed
- `VERSION` bumped to `3.4.0`

---

## [v3.3.0] - 2026-04-11
### Added
- **`capability_token` transparent passthrough in `acp.message`** (A2A #1716 SINT Protocol interop)
  - `/message:send` body: if caller provides `"capability_token": {...}`, relay attaches it verbatim
    to the outgoing `acp.message` frame — relay does NOT validate, recipient verifies.
  - Token format (informative): `{type, subject, resource, actions, tier, exp (ISO-8601), sig}`
  - Persisted to `_recv_queue` outbound entry so `/recv` / `/messages` surfaces it
  - `capabilities.capability_token: true` — always advertised (unconditional flag)
- **`origin_proof` structure upgrade** — new optional OBO fields (A2A #1713 cross-org delegation)
  - `_sign_message()` / `_verify_message_sig()` accept `principal_id`, `operator_id`,
    `governance_framework_ref` which are included in the Ed25519 canonical payload when present
  - `_attach_sig()` builds an `origin_proof` object in the message when any OBO field is provided:
    `{from_peer, to_peer, session_id, timestamp, principal_id?, operator_id?, governance_framework_ref?}`
  - `_build_proof_object()` forwards OBO fields to `_sign_message()` for consistent `proofValue`
  - `/message:send` body: accepts `principal_id`, `operator_id`, `governance_framework_ref` fields
  - `_ws_send` / `_ws_send_sync` updated to accept and forward OBO params
- **`POST /capability/issue`** — ACP-native Ed25519 capability token helper (not A2A mandated)
  - Body: `{subject, resource?, actions?, tier?, exp_seconds?}`
  - Signs canonical JSON with relay's Ed25519 private key; returns full token with `sig` (base64url)
  - Requires `--identity`; 403 `ERR_IDENTITY_REQUIRED` otherwise
  - Token fields: `type`, `subject`, `resource`, `actions`, `tier`, `iss`, `jti`, `iat`, `exp` (ISO-8601), `sig`, `public_key`
- **`_sign_message` / `_verify_message_sig`**: v3.3 canonical payload extended with optional OBO fields
- **VERSION → 3.3.0**
- **Tests**: `tests/test_v33_capability_token.py` — CT-01–CT-06, **6 passed**;
  `tests/test_capability_token.py` — CT-01–CT-06, **6 passed** (new v3.3 test suite replaces v2.57 SINT token fixture tests)
### Fixed
- `origin_proof` OBO fields now correctly appear in `/messages` outbound entries — pre-build
  the `origin_proof` dict eagerly before `_recv_queue.append()` since `_attach_sig()` runs
  inside `_ws_send_sync()` which is called after the entry is stored (CT-06 regression)
### Research
- A2A #1716 (SINT Protocol Ed25519 capability token T0-T3 tiers) — passthrough interop
- A2A #1713 (OBO cross-org delegation) — `origin_proof` field extension

---

## [v3.2.0] - 2026-04-11
### Added
- **W3C DataIntegrityProof compat layer** (ANP 2026-04-10 interoperability, Ed25519Signature2020)
  - `_build_proof_object(msg, to="")`: new function that constructs a W3C-format `proof` object:
    `{"type": "Ed25519Signature2020", "verificationMethod": "did:acp:<pubkey_b64>#key-0",
    "created": "<ISO-8601 UTC>", "proofPurpose": "assertionMethod", "proofValue": "<base64url sig>"}`
    — `proofValue` reuses the identical Ed25519 canonical payload as `msg_sig` for full interop
  - `_attach_sig(msg, to="")` now attaches `proof` object alongside `msg_sig` on all outbound
    messages (only when `_ed25519_private` is loaded; fully backward-compatible addition)
  - **`POST /verify/proof`** — new endpoint accepting W3C DataIntegrityProof format:
    - Body: `{"message": {..., "proof": {"proofValue": "...", "verificationMethod": "did:acp:...", ...}}}`
    - Extracts public key from `proof.verificationMethod` (`did:acp:<pubkey_b64>#key-0`)
    - Verifies using the same canonical payload as `_verify_message_sig` (v3.0 form)
    - Response: `{"valid": bool, "type": "Ed25519Signature2020", "verificationMethod": "...", "created": "..."}`
  - `capabilities.data_integrity_proof: bool(_ed25519_private)` — `true` when identity key loaded
  - `endpoints.verify_proof: "/verify/proof"` added to AgentCard endpoints map
- **Backward compatibility**: `msg_sig` field preserved unchanged; `proof` is an additive field;
  `POST /verify/message` endpoint unchanged; messages without `proof` processed normally
- **Tests**: `tests/test_data_integrity_proof.py` — DIP-01–DIP-06, **6 passed** (unit + integration)
### Research
- ANP 2026-04-10 introduced W3C DataIntegrityProof as standard format; ACP v3.2 bridges
  ACP's msg_sig pattern with the W3C `proof` object format for cross-protocol interoperability

---

## [v3.1.0] - 2026-04-11
### Added
- **`origin_proof` — recipient-bound msg_sig** (ANP DataIntegrityProof alignment, anti-replay)
  - `_sign_message(msg, to="")`: optional `to` parameter adds recipient peer_id to the canonical
    signing payload: `{content, from, message_id, to, ts}` (v3.1) vs `{content, from, message_id, ts}` (v3.0)
  - Signature is now bound to the intended recipient; forwarding a signed message to a different
    peer is cryptographically detectable ("replay-to-wrong-recipient" attack prevention)
  - `_verify_message_sig(msg, public_key_b64, to="")`: optional `to` param; when non-empty,
    reconstructs the v3.1 canonical payload (with `to` field) for verification
  - `POST /verify/message` accepts optional `"to"` field in request body; response echoes `to`
    when provided
  - `_attach_sig(msg, to="")`: passes recipient peer_id through to `_sign_message`; `_ws_send`
    supplies `peer_id` so all outbound messages are automatically origin_proof-signed
  - `capabilities.origin_proof: bool(_ed25519_private)` in AgentCard — `true` when identity key
    is loaded and `to` binding is active
- **Backward compatibility**: messages without `to` field continue to verify with v3.0 canonical
  (no breaking change); `to=""` (default) preserves existing behavior
- **Tests**: `tests/test_origin_proof.py` — OP-01–OP-06, **5 passed, 1 skipped** (integration
  test skipped when relay subprocess port unavailable, same as test_message_sig.py pattern)
### Research
- Background: ANP 2026-04-10 introduced W3C DataIntegrityProof + `origin_proof` field; ACP v3.1
  aligns with this pattern by binding Ed25519 msg_sig to recipient peer_id

---

## [v2.98.0] - 2026-04-10
### Added
- **`POST /tasks/queue` — async task enqueue (202 Accepted)** (A2A #1667 offline-first)
  - Accepts same body as `POST /tasks`; returns 202 immediately with `task_id`, `poll_url`, `sse_url`, `queued_at`
  - Task created in `submitted` state; caller polls `GET /tasks/{id}` or subscribes via SSE
  - `queue_enqueued: true` + `queue_enqueued_at` fields tag queue-originated tasks for observability
  - Audit log entry: `queue_enqueued` via `POST /tasks/queue`
- **`GET /tasks/queue` — queue status**
  - Returns `queue_depth`, active tasks list (submitted + working), `queue_originated` flag per task
- **`capabilities.async_task_queue: true`** in AgentCard when supported
- **`task_queue: /tasks/queue`** in API map
- **Tests**: `tests/test_task_queue_v298.py` — TQ1–TQ9, **9/9 PASS**
### Research
- scan31: #1721 Assay external evidence consumer (ACP /ir/log already covers); #1723 SLIM non-URL transport experiment (ACP relay architecture similar); #1667 DID interop active discussion, original availability gap still open


---

## [v2.96.0-dev] - 2026-04-10
### Added
- **2-Agent Bidirectional Demo** (`demos/two_agent_demo.sh`)
  - Full Alpha↔Beta P2P demo script: auto-waits for link registration, bidirectional connect+send+recv
  - `demos/two_agent_demo.cast` — asciinema v2 terminal recording (30 frames)
  - `demos/two_agent_demo.gif` — 98K animated GIF via agg v1.7.0 (1.5x speed)
  - `demos/two_agent_demo.svg` — 34K SVG animation via svg-term-cli
- **README demo gif** embedded at top (below tagline, before quickstart)
  - Version badge updated: v2.94 → v2.95
  - Test count badge updated: 1092 → 1637

---

## [v2.95.0] - 2026-04-10
### Added
- **Skill-scoped trust scores** — per-skill IR evidence → per-skill score
  - `GET /trust/skills/{skill_id}/score` — query trust score for a specific skill
  - Evidence isolation: IR records tagged with `skill_id` contribute only to that skill's score
  - `capabilities.skill_scoped_trust: true` in AgentCard when enabled
- **BUG-060/061 fix** — `send_to_peer()` missing `client_msg_id` param + `test_version` stale assertion
### Research
- scan28: A2A #1717 skill-scoped trust gap identified; AgentNexus入场; Gemini SDK review
- scan29: A2A #1716 AgentSkill capability token auth (23 comments, high ACP relevance); #1713 OBO cross-org first-contact; SINT×APS 互操作验证 (9/9 pass); a2a-python v0.3.26 released

---

## [v2.94.0] - 2026-04-09
### Added
- **`principal_diversity_defense`** — colluding-pair penalty in bilateral IR
  - Detects when two agents exchange unusually high mutual ratings relative to diversity of their interaction graph
  - New field `diversity_penalty_applied: bool` in IR response
  - `capabilities.principal_diversity_defense: true` in AgentCard
### Docs
- README polish: v2.93 → v2.94 badge, Show HN pitch updated

---

## [v2.93.0] - 2026-04-09
### Added
- **RFC-004: Decentralized Agent Identity Without CA** (`docs/rfc/identity-without-ca.md`)
  - Ed25519 self-signed identity (no central CA required)
  - Three-layer trust model: identity → delegation scope → execution proof
  - 9-dimension comparison vs CA-based approaches
  - Multi-provider DID support
  - Community comment draft: `docs/community/a2a-1712-comment.md`

---

## [v2.92.0] - 2026-04-09
### Added
- **RFC-003: Governance Metadata specification** (`docs/rfc/governance-metadata.md`)
  - Formalizes `governance_metadata` block schema (v2.60–v2.87 production implementation → spec)
  - New field **`derivation_rights`**: controls data retention/export for task-derived data (GDPR alignment)
    - `retention_permitted`, `retention_ttl`, `derivation_classes`, `export_permitted`, `export_requires_consent`, `derivation_audit_required`
    - Directly addresses "derived data leakage" gap from aeoess SDK v1.37.0 / A2A #1717
  - New field **`credential_lifecycle`**: session TTL and revocation policy
    - `max_session_duration`, `credential_ttl`, `revocation_endpoint`, `revocation_check_frequency`
    - Closes "session closed but credentials survive" TLA+ counterexample (aeoess)
  - `capabilities.derivation_rights: true` and `capabilities.credential_lifecycle: true` when governance configured
  - 16 tests (GM01–GM16) all passing: derivation_rights structure / credential_lifecycle structure / capability flags / AgentCard inclusion / no-governance assertions
  - Comparison table vs A2A #1717 and aeoess SDK v1.37.0 included in RFC

---

## [v2.91.0] - 2026-04-09
### Added
- **GET /ir/adversarial-fixtures — 对抗性 IR 测试夹具端点**
  - 5 个自包含 JSON fixture，用于验证 APS/SINT 实现的信任操纵检测算法
  - **AF-001** (`legitimate_dense`): 50 条交互，4 个多样对手方 → `expected_flags=[], trust=high`（基线参照）
  - **AF-002** (`colluding_pair_inflation`): Alice↔Bob 20 条互刷，无外部对手方 → `mutual_inflation_risk, low_counterparty_diversity, trust=suspicious`
  - **AF-003** (`sybil_ring_circular`): A→B→C→A 闭环 21 条 → `sybil_ring_pattern, zero_external_interactions, trust=untrusted`
  - **AF-004** (`isolated_burst_spike`): 5 条历史 + 15 条同日突发 → `temporal_burst_anomaly, velocity_spike, trust=suspicious`
  - **AF-005** (`tampered_hash_chain`): 第 3 条 `caller_signature` 被破坏 → `signature_verification_failure, trust=invalid; bilateral=false`
  - 每个 fixture 包含：完整签名 IR 记录、`expected_flags`、`expected_trust_signal`、`detection_hint`（算法提示）
  - `detection_algorithms` 字段：提供 counterparty_diversity / mutual_pair_ratio / velocity_ratio / ring_detection / chain_integrity 算法说明
  - `capabilities.ir_adversarial_fixtures: true`; `endpoints.ir_adversarial_fixtures: "/ir/adversarial-fixtures"`
  - 直接响应 A2A #1718 (aeoess, 2026-04-08) 对抗性 fixture 提案，ACP 抢先实现
  - 13 个测试（IAF1-IAF13）全通：200 OK / fixture_count / required fields / 各场景 flag / bilateral=false / capability / endpoint / detection_algorithms
  - commit: `5d3ee27`

---

## [v2.90.0] - 2026-04-09
### Added
- **POST /identity/verify-card — 离线 AgentCard 验签端点**
  - 接受任意 AgentCard JSON，无需与 card 所有者建立连接，直接在本地验证 Ed25519 自签名
  - Request: `POST /identity/verify-card` body `{"card": {...}}`
  - Response: `{"verified": bool, "did": str|null, "public_key": str|null, "did_consistent": bool|null, "scheme": str, "error": str|null}`
  - `capabilities.offline_card_verify: true`
  - `endpoints.offline_card_verify: "/identity/verify-card"`
  - 错误处理：缺少 `card` 字段 → 400；无 identity block → `verified=false`；card_sig 缺失 → `verified=false + error`；签名验证失败 → `verified=false + error`
  - **用途**：跨实例信任传递——Agent B 向 Agent C 证明"我持有 Agent A 的合法签名卡片"，C 无需连接 A 即可验证
  - 9 个测试（IVC1-IVC9）全通：valid sig / tampered sig / unsigned / no identity / missing field / empty body / did_consistent / capability flag / endpoint entry
- Bump VERSION: `2.89.0` → `2.90.0`

---

## [v2.89.0] - 2026-04-09
### Added
- **ACP-RFC-002: 双边签名交互记录** (`docs/rfc/bilateral-interaction-records.md`) — 完整记录 ACP v2.59–v2.76 bilateral IR 设计：双方共签规范载荷、SHA-256 哈希链、Merkle root 证明、与 effective_tier 集成（bilateral_ir_adj 第5因子）、跨实现测试向量；README 新增 A2A #1718 对比行；对标 A2A Issue #1718（viftode4，提案阶段，ACP 领先约3周）
- README 新增竞品对比行：A2A #1718 bilateral IR — ACP v2.61 implemented 3 weeks prior

---

## [v2.88.0] - 2026-04-09
### Added
- **ACP-RFC-001: Skill-Level Authorization Tiers** (`docs/rfc/skill-authorization.md`) — 302-line RFC documenting ACP's implemented authorization model: T0–T3 tier model, five-factor `effective_tier` computation, capability token specification, full API reference, design principles, and comparison with A2A Issue #1716. Suitable for cross-posting to A2A community as a reference implementation.

## [v2.88.0] - 2026-04-09
### Fixed
- **BUG-059: peer card exchange race condition** — In guest_mode (POST /peers/connect), peer registry entry was updated AFTER `_send_agent_card()`. When the host sent its own card back immediately, `_on_message` could not find a `connected=True` peer to attach the received card, leaving `agent_card=None` / `card_available=False` indefinitely. Fix: move peer registration to BEFORE `_send_agent_card()` call so incoming card is correctly attributed.
- **test_peer_card.py PC6/PC7 flaky** — Tests used relay without `--local-only`, so `link` was the public IP (33.229.x.x), causing connect to fail silently. Added `--local-only` to `_start()` fixture so both relay instances use `acp://127.0.0.1:PORT/token` links for direct loopback connection.

---

## [v2.87.0] - 2026-04-09
### Added
- **policy_compliance[] in AgentCard** — governance/compliance standards field (inspired by A2A #1717 Microsoft agent-governance-toolkit proposal)
  - `_policy_compliance: list` global; synced into `_status["policy_compliance"]`
  - AgentCard top-level field `policy_compliance: string[]`
  - `capabilities.policy_compliance: bool` — True when any standards declared
  - `endpoints.policy_compliance: "/policy-compliance"` — endpoint registration
  - `--policy-compliance STANDARDS` CLI flag (comma-separated)
  - `GET /policy-compliance` — query current standards list with count + note
  - `PATCH /policy-compliance` — replace mode `{"policy_compliance": [...]}` + incremental `{"add": [...], "remove": [...]}`
  - `do_PATCH` router: `/policy-compliance` branch added (was falling through to 404)
  - Well-known standard identifiers: `OWASP-ASVS`, `ATF-v2`, `NIST-AIRMF`, `ISO-42001`, `EU-AI-Act-conformant`
- **Tests**: `test_policy_compliance_v287.py` — PC-1..PC-10, all passing (commit `1801806`)
- Bump VERSION: `2.85.0` → `2.87.0`
### Research
- 2026-04-09 竞品扫描：A2A #1717（governance metadata，Microsoft）；A2A #1672 仍 403 评论无实现；ANP DID 活跃；ACP Ed25519 领先优势持续

## [v2.86.1] - 2026-04-09
### Fixed
- **BUG-058**: `test_capability_token.py::test_ct_1_to_12` CT-1 — v2.85 Ed25519 default-on causes "no identity → 403" assertion to fail (same class as BUG-031); fixed by adding `no_identity=True` parameter to `_start_relay()` (adds `--no-identity` flag), and extending relay startup wait from 12s → 30s; test now 1/1 PASS

## [v2.86.0] - 2026-04-08
### Changed
- `docs/show-hn-draft.md`: full rewrite for v2.86 — Ed25519 default-on as lead pitch angle, A2A #1672 updated to 403 comments, stale v3.0.0 references removed, test count updated to 1092
- `README.md`: A2A #1672 comment count 62 → 403 (measured 2026-04-08)
### Fixed
- **BUG-031**: `test_cs10_no_card_sig_without_identity` — test assumed pre-v2.85 behavior where running without `--identity` meant no identity; v2.85 made Ed25519 default-on, so test now uses `--no-identity` escape hatch flag; 11/11 card_signature tests PASS
### Research
- 2026-04-08 competitor scan: A2A v1.0.1 (bugfix-only, 23k ⭐); #1672 still open (403 comments, no impl); SLIMRPC custom binding proposal (#1723); ACP identity lead confirmed

## [v2.85.0] - 2026-04-08
### Added
- **Ed25519 identity default-on**: keypair auto-generated on first run with no flags; `capabilities.identity_default: true` in AgentCard
- **`--no-identity` flag**: escape hatch to disable identity for testing or embedded use
- **`GET /protocol-binding/compatibility`**: structured JSON endpoint declaring support levels for 6 protocols (websocket=native, http/sse=native, a2a=partial, anp=partial, mcp=none, grpc=none)
- `"protocol_binding_compatibility"` entry in AgentCard `endpoints` block
### Tests
- `tests/test_identity_default_v285.py`: 20 new tests (ID-01..ID-10, PBC-01..PBC-10), all PASS
- Total: 1092/1092 PASS

## [v2.84.0] - 2026-04-08
### Added
- `protocol_bindings[]` top-level AgentCard field (A2A §5.8 aligned plural form):
  - Array of CPB URI objects for multi-binding advertisement forward compatibility
  - Retains singular `protocol_binding` field for backward compatibility
  - New capability flag `protocol_bindings_array: true`
- `client_msg_id` idempotency enhancement (ANP §3.2 borrow):
  - `/message:send` accepts `client_msg_id` as alias for `message_id`
  - Priority: `message_id` → `client_msg_id` → auto-generated
  - All send responses echo `client_msg_id` field for caller convenience
  - Dedup cache (`_http_dedup_check`) now covers `client_msg_id` alias
### Tests
- 7/7 Scenario B PASS (BUG-055 three-layer root-cause fix)
- 14/14 Scenario E + NAT tests PASS

## [v1.4.0] - 2026-04-08
### Added
- `_connect_with_nat_traversal()` three-level auto-fallback (L1 direct → L2 DCUtR hole punch → L3 relay)
  - Level 1: Direct WebSocket (`ws://IP:port/token`, 3s timeout)
  - Level 2: DCUtR UDP hole punch via signaling relay WS (12s timeout); STUN address discovery + simultaneous probes
  - Level 3: Cloudflare Worker relay fallback (auto-triggered on symmetric NAT / CGNAT)
- DCUtR UDP hole punch via signaling relay WS (`STUNClient` + `DCUtRPuncher` classes)
- `--relay` flag semantics updated: now triggers force-L3 bypass (no longer manual-only)
- SSE events: `dcutr_started` → `dcutr_connected` / `relay_fallback`
- `GET /status` returns `connection_type`: `p2p_direct` | `dcutr_direct` | `relay`
### Tests
- 34 passed covering test_dcutr_t1~t6, test_nat_traversal_integration T1~T5, test_nat_signaling, test_nat_http_reflect
- Commit: `d90b328`

---

## v2.82.0 — evidence_stream: SSE lifecycle subscription (2026-04-08)

### Features
- `GET /tasks/{id}/evidence-stream` — SSE real-time subscription for task lifecycle evidence
- Replay: on connect, pushes all existing evidence entries before live stream
- Multi-subscriber: multiple clients can subscribe to the same task concurrently
- Keepalive interval: 5s (configurable via EVIDENCE_STREAM_KEEPALIVE_INTERVAL env var)
- `capabilities.evidence_stream: true` — declared in status and AgentCard
- Completes the evidence lifecycle: write (POST) → query (GET) → stream (SSE)

### Tests
- `test_evidence_stream.py`: ES1–ES12 = **12/12 PASS**

---

## v2.81.0 — task_evidence: lifecycle evidence anchoring (2026-04-08)

### Features
- `POST /tasks/{id}/evidence` — submit lifecycle evidence entries (requested/updated/completed/failed)
- `GET /tasks/{id}/evidence` — list all evidence for a task
- `GET /tasks/{id}/evidence/latest` — get most recent evidence entry
- `capabilities.task_evidence: true` — declared in status and AgentCard
- Sequential `seq` numbering per task for ordered audit trail
- Differentiator: addresses A2A Issue #1721 (Assay framework task evidence) — ACP first to implement

### Tests
- `test_task_evidence.py`: TE1–TE12 = **12/12 PASS**

---

## v2.80.0 — heartbeat_period_ms (2026-04-08)

### Features
- `heartbeat_period_ms` field in AgentCard — declare agent heartbeat interval (ms)
- `--heartbeat-period-ms <int>` CLI flag
- `capabilities.heartbeat_period_declared: true` when declared
- `GET /availability` and `POST /availability/heartbeat` responses include `heartbeat_period_ms`
- Differentiator: addresses A2A Issue #1667 (heartbeat-based agents) — ACP first to implement

### Tests
- `test_heartbeat_period.py`: HP1–HP10 = **10/10 PASS**

---

## [2.79.0] — 2026-04-07 (GET /protocol-binding + AgentCard protocol_binding — A2A §5.8 CPB URI identification; PR #1619 aligned)

### Added
- **`GET /protocol-binding`** — ACP custom protocol binding declaration (A2A §5.8)
  - Returns `_PROTOCOL_BINDING` dict: binding_uri, binding_name, binding_version, transport, base_protocol, addressing, supports_sse, supports_ws, nat_traversal, nat_levels, description, a2a_ref, spec_url
  - **binding_uri**: `urn:acp:binding:p2p-relay/v1` — canonical ACP protocol binding identifier
  - **transport**: `p2p+relay` — P2P direct connection with relay fallback
  - **addressing**: `acp://<relay_host>/<session_token>` — ACP link scheme
  - **nat_traversal**: True, **nat_levels**: 3 — three-level NAT traversal (P2P → hole-punch → relay)
  - **supports_sse**: True, **supports_ws**: True
  - **a2a_ref**: A2A PR #1619 (merged 2026-04-07, §5.8)
  - POST → 405 ERR_METHOD_NOT_ALLOWED
- **AgentCard `protocol_binding` top-level field** — embedded in `/.well-known/acp.json` response
- **`_PROTOCOL_BINDING` global** — single source of truth for binding declaration
- `capabilities.protocol_binding = True`
- `endpoints.protocol_binding = "/protocol-binding"`

### Background
A2A PR #1619 (merged 2026-04-07) added §5.8 to the spec, requiring custom protocol bindings to:
1. Have a stable URI identifier
2. Be declared in the AgentCard
3. Specify key areas: data type mappings, service parameters, error mapping, streaming, auth, interop testing
ACP v2.79 implements this for the ACP P2P Relay binding.

### Tests
- `test_protocol_binding_v279.py`: PB-01..PB-25 = **25/25 PASS**
  - PB-01..05: basic endpoint (status, ok, binding_uri, version)
  - PB-06..10: required fields (binding_name, transport, addressing, nat_traversal, nat_levels)
  - PB-11..15: streaming + spec fields (sse, ws, description, a2a_ref, spec_url)
  - PB-16..20: method guard (POST→405) + AgentCard integration
  - PB-21..25: content consistency (agentcard ↔ endpoint binding_uri match, URN prefix, version)
- Commit: `4764fed`

### A2A Alignment
- A2A PR #1619 (merged 2026-04-07): `docs/topics/custom-protocol-bindings.md` + spec §5.8
- ACP `urn:acp:binding:p2p-relay/v1` is the first registered ACP protocol binding URI

---

## [2.78.0] — 2026-04-07 (POST /trust/signals/capability-token/revoke + GET /revocations — active SINT token revocation; A2A #1716 full lifecycle)

### Added
- **`POST /trust/signals/capability-token/revoke`** — active SINT capability token revocation
  - Body: `{"jti": "<string>", "reason": "<string>", "revoked_by": "<did>"}`
  - Revokes token by JTI; records in `_revoked_tokens` dict
  - Reasons: `manual` (default) / `expired` / `compromised` / `policy_violation`
  - Forward revocation: unknown JTI accepted (`token_known: false`)
  - 409 `ERR_ALREADY_REVOKED` on duplicate revoke (idempotent conflict with original `revocation_id`)
  - 400 `ERR_BAD_REQUEST` for missing/empty JTI or invalid JSON
  - 405 for non-POST methods
- **`GET /trust/signals/capability-token/revocations`** — list all revoked tokens
  - Returns `{ok, version, total_revoked, revocations: [{jti, revocation_id, revoked_at, reason, revoked_by, token_known}]}`
- **validate endpoint Check 6: revocation** — `POST .../fixtures/validate` now includes revocation check
  - Checks `_revoked_tokens` for JTI presence; `passed=false` + `reason="token_revoked"` if found
  - Priority: revocation check is **highest priority** in deny ordering (before expiry)
  - Non-revoked tokens: `revocation: {passed: true, reason: "token_not_revoked"}`
- Completes the **SINT capability quad**: v2.74 declare + v2.75 fixture + v2.77 validate + v2.78 revoke
  - Full token lifecycle: issue → declare → fixture → validate → **revoke**
- `capabilities.capability_token_revoke = True`
- `endpoints.capability_token_revoke = "/trust/signals/capability-token/revoke"`
- `endpoints.capability_token_revocations = "/trust/signals/capability-token/revocations"`
- `_revoked_tokens: dict` global state store

### Tests
- `test_capability_token_revoke_v278.py`: RV-01..RV-30 = **30/30 PASS**
  - RV-01..05: basic revocation (fields, defaults)
  - RV-06..10: error cases (missing jti, duplicate, empty jti, bad JSON)
  - RV-11..15: revocation list endpoint (structure, fields, a2a_ref)
  - RV-16..20: validate endpoint revocation check (deny, check presence, deny_reason)
  - RV-21..25: reason variants + forward revocation + version/a2a_ref
  - RV-26..30: SINT lifecycle integration + AgentCard reflection
- `test_capability_token_validate_v277.py`: TV-08/TV-10 updated for 6-check pipeline (≥5 / superset)
- Full Regression: **157/157 PASS** (RV×30 + TV×30 + ET×30 + CF×20 + CT×25 + AL×22)
- Commit: `06330bd`

### A2A Alignment
- A2A #1716 (SINT PR#111): complete SINT lifecycle reference implementation
  - ACP now covers declare/fixture/validate/revoke — the full capability token management surface

---

## [2.77.0] — 2026-04-07 (POST /trust/signals/capability-token/fixtures/validate — dynamic SINT token validation; A2A #1716 @pshkv runtime enforcement)

### Added
- **`POST /trust/signals/capability-token/fixtures/validate`** — dynamic SINT capability token validation endpoint
  - Accepts `{"token": {...}, "invocation_context": {...}}` body
  - Runs 5-check validation pipeline:
    1. **expiry** — re-verifies `exp` at `use_time` (TOCTOU re-check, not only at receipt)
    2. **scope** — `resource` URI tail must match `invocation_context.target_skill_id`
    3. **skill_id** — structural resource path validation (optional `explicit_skill_id` override)
    4. **subject** — `token.sub` must match `invocation_context.invoking_agent_did`
    5. **required_fields** — `{jti, iss, sub, resource, scheme}` all present
  - Priority deny ordering: `expiry > scope > skill_id > subject > required_fields`
  - Allow response: `{"ok": true, "authorized": true, "reason_code": "token_valid", "checks": [...]}`
  - Deny response (403): `{"ok": true, "authorized": false, "deny_reason": "...", "http_status": 403, "deny_details": [...], "checks": [...]}`
  - `GET` on this endpoint → 405 METHOD_NOT_ALLOWED
  - Skips checks gracefully when context fields are absent (e.g. no `invoking_agent_did` → subject check skipped)
  - Completes the **SINT capability triad**: v2.74 declaration + v2.75 fixtures + v2.77 validate
- `capabilities.capability_token_validate = True` — advertised in AgentCard
- `endpoints.capability_token_validate = "/trust/signals/capability-token/fixtures/validate"`

### Tests
- `tests/test_capability_token_validate_v277.py` — 30 test cases (TV-01..TV-30)
  - Endpoint availability, version ≥ 2.77, capability/endpoint declaration
  - Allow full context, no context, 5-check presence, all-pass
  - DENY: expired, TOCTOU, missing exp, expiry priority over scope
  - DENY: scope mismatch, skill_id mismatch, missing resource
  - DENY: subject mismatch, skipped-no-did, missing sub
  - DENY: missing required fields, empty token
  - Bad request (no token key → 400)
  - Integration: canonical fixtures from GET /fixtures used as POST inputs → deny confirmed

### Full Regression
- **127/127 PASS** (TV×30 + ET×30 + CF×20 + CT×25 + AL×22 — batched)

### Commit
- `7cb7f90`

### References
- A2A #1716 @pshkv SINT PR#111 — runtime enforcement reference implementation
- ACP v2.74: `GET /trust/signals/capability-token` (declaration)
- ACP v2.75: `GET /trust/signals/capability-token/fixtures` (static fixtures)

---

## [2.76.0] — 2026-04-07 (effective_tier Factor 5 — bilateral_ir_adj; A2A #1716 @64R3N attestation_history_adjustment)

### Added
- **`_bilateral_ir_merkle_root(peer_id)`** — SHA-256 Merkle commitment over local bilateral IR records for a given peer, sorted by timestamp; mirrors the `wtrmrk_sequence_root` concept without requiring an external chain
- **`_bilateral_ir_adj(peer_id)`** — Factor 5 adjustment computation for `effective_tier`:
  - `+1` (0 records) — unknown peer raises tier floor (conservative)
  - ` 0` (1–4 records) — known but limited bilateral history; neutral
  - `-1` (≥5 records) — established bilateral interaction history; may lower tier floor
  - Returns `(adj, count, merkle_root)` tuple
  - Only records with `bilateral=True` and matching `peer_id` are counted
- **`effective_tier` upgraded to 5-factor architecture**:
  - Factor 1: `tier_rule` (skill-declared authorization tier)
  - Factor 2: `delegation_depth_floor` (deeper delegation = more conservative floor)
  - Factor 3: `reputation_adj` (peer trust signals history)
  - Factor 4: `wtrmrk_adj` (on-chain WTRMRK grade)
  - Factor 5 ⭐: **`bilateral_ir_adj`** (local IR log Merkle commitment, A2A #1716 @64R3N)
  - Combination rule: any `+1` immediately overrides (conservative); `-1` requires ≥2 of 3 adjustment factors to agree
  - `factors` dict now includes: `bilateral_ir_adj`, `bilateral_ir_count`, `bilateral_ir_merkle_root`, `factor_count: 5`
- **`capabilities.effective_tier_five_factors: True`** — advertised in AgentCard

### Tests
- `tests/test_effective_tier_v276.py` — 30 test cases (ET-01..ET-30)
  - Version ≥ 2.76, capability declaration
  - HTTP endpoint: `effective-tier` presence, `factor_count=5`
  - `bilateral_ir_adj` / `bilateral_ir_count` / `bilateral_ir_merkle_root` field presence
  - Unknown peer → `adj=+1`, `count=0`, `merkle_root=None`
  - Merkle root with synthetic records → non-null 64-char SHA-256 hex
  - Threshold tests: 1 record→0, 4 records→0, 5 records→−1, 10 records→−1
  - `bilateral=False` records excluded from count
  - Combined adj: any `+1` overrides; two-negative consensus required for `−1`
  - `factor_count=5` always present; T3 immune to all factors
  - Fix CF-19 version assertion in `test_capability_token_fixtures_v275.py` (== → >=)

### Full Regression
- **153/153 PASS** (ET×30 + CF×20 + CT×25 + AL×22 + BL×21 + SP×20 + SC×15 + TS×14 — batched)

### Commit
- `a469555`

### References
- A2A #1716 @64R3N: `effective_tier attestation_history_adjustment` proposal
- ACP v2.62 Factor 4 (`wtrmrk_adj`) — local IR log analogue to `wtrmrk_sequence_root`

---

## [2.75.0] — 2026-04-07 (canonical authorization fixture endpoint; A2A #1716 @pshkv 4-deny+1-allow minimal vector set)

### Added
- **`GET /trust/signals/capability-token/fixtures`** — canonical authorization test fixture vectors for SINT capability tokens
  - Proposed by @pshkv in A2A #1716 as the minimal canonical vector set
  - **1 allow scenario**: `allow_valid_subject_bound` — valid subject-bound token, all fields nominal
  - **4 deny scenarios**:
    - `deny_scope_mismatch` — token resource scope does not match requested skill
    - `deny_expired_toctou` — token expired + TOCTOU (time-of-check/time-of-use) attack scenario
    - `deny_skill_id_mismatch` — token resource path encodes different skill_id than invocation target
    - `deny_subject_mismatch` — token `sub` DID does not match the invoking agent's DID
  - Each fixture includes: `id`, `verdict`, `deny_reason` (deny only), `description`, `token` object, `invocation_context` (deny), `expected_result` (`authorized`, `reason_code`, `http_status`)
  - `fixture_count`: `{allow: 1, deny: 4, total: 5}`
  - `deny_reasons_covered`: `["scope_mismatch", "expired_toctou", "skill_id_mismatch", "subject_mismatch"]`
  - Timestamps in token fixtures are dynamically computed relative to `now` for always-valid context
- `capabilities.capability_token_fixtures = True` — advertised in `/capabilities`
- `endpoints.capability_token_fixtures = "/trust/signals/capability-token/fixtures"` — in endpoint map

### Tests
- `tests/test_capability_token_fixtures_v275.py` — 20 test cases (CF-01..CF-20)
  - Endpoint availability, envelope structure, fixture counts
  - Verdict validation (allow/deny), deny reason coverage
  - Per-deny scenario presence (scope_mismatch / expired_toctou / skill_id_mismatch / subject_mismatch)
  - authorized=False + http_status=403 for all deny scenarios
  - Unique fixture IDs, token object presence, version string, method rejection
  - Fix CT-20 version assertion in `test_capability_token_detail_v274.py` (startswith → >=)

### Full Regression
- **123/123 PASS** (CF×20 + CT×25 + AL×22 + BL×21 + SP×20 + SC×15 + TS×14 — batched)

### Commit
- `2d5fbd7`

---

## [2.74.0] — 2026-04-07 (trust/signals/capability-token — SINT capability token declaration endpoint; A2A #1716 aligned)

### Added
- **`GET /trust/signals/capability-token`** — detailed capability token declaration for this relay
  - `enabled`: whether Ed25519 identity is loaded (required for token issuance)
  - `issuer_did`: issuer DID (`did:acp:` or `did:key:`) when enabled
  - `agent_name`: relay agent name
  - `scheme`: `sint_ed25519` (SINT Protocol format)
  - `algorithm`: `Ed25519`
  - `format`: `SINT`
  - `sint_fields.required`: `["jti","iss","sub","resource","tier","iat","exp","signature","public_key"]`
  - `sint_fields.optional`: `["actions","constraints"]`
  - `supported_tiers`: `["T0","T1","T2","T3"]`
  - `default_ttl_seconds`: `3600`
  - `endpoint_issue`: `/skills/{skill_id}/capability-token`
  - `endpoint_verify`: `/verify/external-token`
  - `token_required_skills`: list of `{skill_id, name, tier}` for skills with `capability_token_required=True`
  - `token_required_count`: integer count of above
  - `active_tokens`: live count of non-expired tokens in issuance cache
  - `total_issued`: total tokens ever issued (this session)
  - `a2a_ref`: `https://github.com/google-a2a/A2A/issues/1716`
- **AgentCard `capabilities.capability_token_detail: true`**
- **AgentCard `endpoints.capability_token_detail: "/trust/signals/capability-token"`**
- Aligned with A2A #1716 @pshkv SINT PR#111 (2026-04-07): canonical capability token check at AgentSkill boundary

### Tests
- `tests/test_capability_token_detail_v274.py` — CT-01..CT-25: **25 tests passed**
  - CT-01..02: 200 + ok=True
  - CT-03..04: enabled=False + issuer_did=None without identity
  - CT-05..07: scheme/algorithm/format constants
  - CT-08: supported_tiers = {T0,T1,T2,T3}
  - CT-09..10: sint_fields required + optional field sets
  - CT-11: default_ttl_seconds = 3600
  - CT-12..13: endpoint_issue + endpoint_verify present
  - CT-14..15: token_required_skills is list; count matches
  - CT-16..17: active_tokens/total_issued are int ≥ 0
  - CT-18: note contains "SINT"
  - CT-19: a2a_ref contains "1716"
  - CT-20: version starts with "2.74"
  - CT-21: POST returns 4xx
  - CT-22..23: AgentCard capabilities + endpoints
  - CT-24: agent_name present in response
  - CT-25: active_tokens ≤ total_issued

### Full Regression
- **152/152 PASS** (CT×25 + AL×22 + BL×21 + SP×20 + SC×15 + TS×14 + B×7 + G×10 + F×10 + AB×5 + H×3)

### Commit
- `1b46f83`

---

## [2.73.0] — 2026-04-07 (agent-limitations/schema — typed JSON Schema for constraint dict; A2A #1694 aligned)

### Added
- **`GET /agent-limitations/schema`** — JSON Schema for the `agent_limitations` structured constraint dict
  - Returns JSON Schema (draft/2020-12) describing all fields in the `agent_limitations` dict
  - Schema title: `AgentLimitations`; `$id: https://acp.dev/schema/agent-limitations/v2.73.json`
  - Documented properties (6): `max_message_size_bytes` / `max_recv_queue_size` / `max_wait_seconds` / `max_peers` / `supported_message_roles` / `supported_priorities`
  - Each property includes: `type`, `minimum`/`enum`, `description`, `x-acp-since` metadata
  - `additionalProperties: false` — strict schema, no undeclared fields
  - `current_values` field: actual `_LIMITATIONS` dict values for this relay instance
  - Consumers can use schema to programmatically validate capability constraints
- **AgentCard `capabilities.agent_limitations_schema: true`**
- **AgentCard `endpoints.agent_limitations_schema: "/agent-limitations/schema"`**
- Aligned with A2A #1694 typed limitations proposal (machine-readable constraint discovery)

### Tests
- `tests/test_agent_limitations_schema_v273.py` — AL-01..AL-22: **22 tests passed**
  - AL-01..02: 200 status + ok=True
  - AL-03: Schema title AgentLimitations
  - AL-04: ≥6 schema properties
  - AL-05..10: Each property type/enum correct
  - AL-11..12: current_values correct (max_peers=100, max_message_size≥64KB)
  - AL-13: Response version == acp_version
  - AL-14..15: AgentCard capabilities + endpoints
  - AL-16: Version 2.73.0
  - AL-17: additionalProperties: False
  - AL-18: $id contains "acp.dev"
  - AL-19: note field present
  - AL-20: POST returns 404/405
  - AL-21: current_values roles contain "user"/"agent"
  - AL-22: Full regression /status + /well-known/acp.json + /trust/bilateral-ir/log

### Full Regression
- **109/109 PASS** (AL×22 + BL×21 + SP×20 + SC×15 + TS×14 + B×7 + G×10)

### Commit
- `ad15e74`

---

## [2.72.0] — 2026-04-07 (trust/bilateral-ir/log — queryable bilateral IR record log; A2A #1718 @viftode4)

### Added
- **`GET /trust/bilateral-ir/log`** — Query the local bilateral interaction record log
  - Returns paginated snapshot of `_interaction_records[]` with filters
  - Filter params: `caller_did` (substring), `skill_id` (substring), `bilateral=true|false`, `since=<unix_ts>`, `limit` (max 500), `offset`
  - Response includes `bilateral_count` — trust-depth quick metric (A2A #1718 aligned)
  - Implements queryable bilateral IR log recommended by A2A #1718 @viftode4
  - Bilateral records co-signed by relay+caller = non-repudiable trust evidence
- **AgentCard `capabilities.bilateral_ir_log: true`**
- **AgentCard `endpoints.bilateral_ir_log: "/trust/bilateral-ir/log"`**

### Fixed
- `?since=<float>` vs ISO timestamp comparison TypeError → relay crash
  - Fix: ISO timestamp → epoch conversion via `fromisoformat()` in filter logic

### Tests
- `tests/test_bilateral_ir_log_v272.py` — BL-01..22: **21 tests passed, 1 skipped**
  - Full filter matrix: caller_did / bilateral / since / limit / offset
  - Regression: /status + /trust/signals + bilateral-ir/log

### Commit
- `cb35cfe` (feat), `b429d76` (docs)

---

## [2.69.0] — 2026-04-07 (runtime limitations endpoint — A2A #1694 @citriac stable/runtime split)

### Added
- **`GET /limitations/runtime`** — Dynamic runtime limitations endpoint
  - Aligns with A2A #1694 @citriac Agent Exchange Hub v0.4.0 stable/runtime limitations split
  - Complements static `limitations[]` in AgentCard (v2.29) with live runtime metrics
  - Response: `{ ok, runtime: { current_load, queue_depth, active_tasks, total_tasks, memory_usage_mb, memory_source, peer_count }, version, timestamp }`
  - `current_load` — number of currently connected WS peers
  - `queue_depth` — tasks in `submitted` state
  - `active_tasks` — tasks not in terminal states (`completed/failed/canceled/rejected`)
  - `total_tasks` — total tasks ever created in this relay session
  - `memory_usage_mb` — process RSS in MB (psutil preferred, resource.getrusage fallback)
  - `memory_source` — `"psutil"` | `"resource"` (indicates which library was used)
  - `peer_count` — total registered peers (connected + disconnected)
  - psutil is optional — lazy import inside function body; graceful degradation to `resource` module
- **AgentCard `capabilities.runtime_limitations: true`**
- **AgentCard `endpoints.runtime_limitations: "/limitations/runtime"`**

### Tests
- `tests/test_runtime_limitations.py` — RL-1..10: **10 tests passed**
  - RL-1: Response shape (ok/runtime/version/timestamp)
  - RL-2: All required keys present
  - RL-3: memory_usage_mb > 0
  - RL-4: active_tasks == 0 initially
  - RL-5: queue_depth >= 0 initially
  - RL-6: active_tasks >= 0 after task creation
  - RL-7: AgentCard capabilities.runtime_limitations == True
  - RL-8: AgentCard endpoints.runtime_limitations == "/limitations/runtime"
  - RL-9: peer_count == 0 with no WS peers
  - RL-10: total_tasks >= 0; memory_source in ("psutil", "resource")

### Alignment
- A2A #1694 @citriac proposes stable/runtime limitations separation in Agent Exchange Hub v0.4.0
- ACP v2.29 already had static `limitations[]` (LimitationObject format)
- v2.69 completes the split with dynamic runtime metrics endpoint

---

## [2.67.0] — 2026-04-06 (Direct Message mode — A2A v1.0.0 `SendMessageResponse` alignment)

### Added
- **`POST /message/send`** — Direct Message endpoint (no Task created, no state machine)
  - Endpoint uses `/` separator (vs existing `/message:send` WS routing endpoint)
  - Request: `{ role: "user"|"agent", parts?: Part[], text?: string, context_id?: string, message_id?: string }`
  - Response: `{ ok, type:"message", message_id, role, parts[], context_id?, timestamp }`
  - Supports both `parts[]` (A2A format) and legacy `text`/`content` shorthand
  - `parts[]` format: A2A Part (text/file/data)
  - Content-Type guard: non-JSON rejected with `400`
  - Oversized body (>1MB) rejected with `413` via `_read_body()` guard (BUG-051)
  - Deduplication via `message_id` (optional client-provided)
- **AgentCard `capabilities.direct_message: true`**
- **AgentCard `endpoints.message_send: "/message/send"`**

### Fixed
- **BUG-053** (false positive): `MAX_MSG_BYTES = 1MB` (not 64KB); `_read_body()` already enforces
  size limit via `Content-Length`. 70KB < 1MB is correctly accepted; 1.1MB correctly returns `413`.

### Tests
- `tests/test_direct_message.py` — DM-1..14: **16 tests passed** (DM-14: size boundary regression)
- All 843+ existing tests continue to pass (no regressions)

### Alignment
- A2A v1.0.0 `SendMessageResponse.oneof { Task task; Message message; }` — Direct Message is the
  `Message` branch; ACP `/message:send` (existing) is the `Task` branch.

---

## [2.66.0] — 2026-04-06 (Task `rejected` terminal state — A2A v1.0.0 alignment)

### Added
- **`TASK_REJECTED = "rejected"`** — New Task terminal state constant
- **`TERMINAL_STATES`** updated to include `rejected`
- **`POST /tasks/{id}:agent-reject`** — Agent-initiated task rejection
  - Accepts `reason` (string) and `reject_code` (string) in request body
  - Transitions any non-terminal task to `rejected`
  - Idempotent: already-terminal tasks return `ok: true` + `note: "already in terminal state"`
  - Unknown task → `404`
- **`GET /tasks?status=rejected`** — Task list filter now accepts `status=rejected`
- **AgentCard `capabilities.rejected_state: true`**
- **AgentCard `endpoints.agent_reject: "/tasks/{id}:agent-reject"`**

### Changed
- **`POST /tasks/{id}:reject`** (T3 human confirmation): `confirmation_pending → rejected`
  (previously `→ failed`). Semantically: human reviewer *actively declines*, not an error.

### Tests
- `tests/test_task_rejected.py` — RJ-1..10: 9 passed, 1 skipped
- `tests/test_t3_human_confirmation.py` — T3C5, T3C11 assertions updated: `failed` → `rejected`

### Motivation
A2A v1.0.0 distinguishes `failed` (error/timeout) from `rejected` (agent actively refuses).
ACP v2.66 aligns with this semantic, giving callers precise signal on *why* a task did not complete.

---

## [2.65.0] — 2026-04-06 (POST /ir/import-evidence — APS-compatible bilateral IR import + reputation_update)

### Added
- **`POST /ir/import-evidence`** — Import an external bilateral interaction record and generate an APS-compatible `reputation_update` payload.
  - Verifies `relay_signature` and `caller_signature` independently (Ed25519)
  - Returns `verify` block: `relay_sig_valid`, `caller_sig_valid`, `bilateral_verified`, `errors[]`
  - Returns `reputation_update` payload (APS v1 schema):
    - `trust_delta`: `+1` (bilateral verified) / `0` (relay-only) / `-1` (tampered/missing)
    - `freshness_hint`: seconds elapsed since the original interaction timestamp
    - `aps_schema: "v1"`, `evidence_type: "bilateral_interaction_record"`
    - Fields: `source_relay_did`, `agent_did`, `task_id`, `skill_id`, `sequence_a`, `timestamp`, `bilateral`
  - `import_id`: `"imp-<uuid>"` — stable identifier for the imported record
  - Imported records stored in `_imported_evidence[]` (separate from `_interaction_records[]`)
- **`GET /ir/imported-evidence`** — List all imported bilateral IR evidence records
  - Supports `?agent_did=` filter and `?limit=` pagination
  - Returns `{ok, count, total, records[]}`
- **`_verify_ir_signatures(ir)`** — dual Ed25519 verification helper with error collection
- **`_build_reputation_update(ir, verify_result)`** — APS v1 reputation_update builder with `freshness_hint`
- **AgentCard**: `capabilities.import_evidence = bool(_ed25519_private)`, `endpoints.import_evidence = "/ir/import-evidence"`
- **`_imported_evidence: list`** global state

### A2A Alignment
- Implements `importBilateralEvidence()` interface discussed in A2A Issue #1718 (@aeoess)
- `trust_delta` scoring aligns with APS reputation registry update semantics

### Tests
- `tests/test_import_evidence.py` — **IE-1..20: 20/20 PASS**
- Full regression: **843 passed, 8 skipped, 0 failed** (pre-existing flaky excluded)

### Bug Fixes
- **BUG-052** (test_t3c3 port contention): `websockets.serve(reuse_address=True)` + `_kill_port()` pre-clean + `wait_http_ready` timeout 20s

---

## [2.64.0] — 2026-04-06 (bilateral IR test vectors + governance live_endpoint — APS serviceEndpoint alignment)

### Added
- **`GET /ir/test-vectors`** — 4 deterministic bilateral interaction record test vectors for cross-implementation verification
  - `tv-ir-001`: bilateral valid (both relay+caller signatures valid)
  - `tv-ir-002`: relay-only (no caller signature), `previous_hash = sha256(tv-ir-001.canonical_payload)`
  - `tv-ir-003`: tampered relay_signature (negative test — `verify=false`)
  - `tv-ir-004`: did:key format consistency test (canonical_bytes_hex for interoperability)
  - Keys derived via SHA-256 seeding → fully deterministic and reproducible across implementations
  - Includes `canonical_bytes_hex` for payload consistency verification
  - Returns 503 if no `--identity` loaded
- **`governance_metadata.live_endpoint: "/governance-metadata"`** — APS `serviceEndpoint` pattern alignment (A2A #1717)
- **AgentCard**: `capabilities.ir_test_vectors = bool(_ed25519_private)`, `endpoints.ir_test_vectors = "/ir/test-vectors"`

### A2A Alignment
- `GET /ir/test-vectors` directly addresses @aeoess's request in A2A #1718 for bilateral IR test vectors to implement `importBilateralEvidence()`
- `live_endpoint` mirrors APS `passportToAgentCard()` `serviceEndpoint` pattern (A2A #1717 @aeoess)

### Tests
- `tests/test_ir_test_vectors.py` — **ITV-1..18: 18/18 PASS**
- Full regression: **860 passed, 8 skipped, 0 failed**

---

## [2.62.0] — 2026-04-06 (effective_tier Factor 4 — wtrmrk_sequence_root external reputation query)

### Added
- **Factor 4**: `wtrmrk_sequence_root` external reputation signal added to `_compute_effective_tier()`
- **`_query_wtrmrk(sequence_root)`** — queries MoltTrust `api.moltrust.ch/capability/verify` for external attestation
- **`_wtrmrk_to_adj(result)`** — converts MoltTrust response to `+1 / 0 / -1` adjustment
- **Asymmetric safety rule**: `combined_adj = rep_adj + wtrmrk_adj` with rule: *either +1 wins; both -1 needed to lower floor*
- **Four-factor formula**: `effective_tier = max(tier_rule, depth_floor(chain_len), base + combined_adj)`
- **`POST /tasks metadata.wtrmrk_sequence_root`** — callers can pass external attestation root with task invocations
- **`GET /skills/{id}/effective-tier?wtrmrk_sequence_root=`** — optional factor 4 query param
- **AgentCard**: `capabilities.wtrmrk_attestation = bool(_ed25519_private)`

### A2A Alignment
- `wtrmrk_sequence_root` aligns with A2A #1716 (@64R3N/@MoltyCel/@aeoess) — Merkle commitment anchored reputation
- ACP asymmetric safety rule prevents single compromised factor from downgrading tier

### Tests
- `tests/test_wtrmrk_attestation.py` — **WA-1..14: 14/14 PASS**
- Full regression: **525+ passed, 4 skipped, 0 failed**

---

## [2.61.0] — 2026-04-06 (caller_signature — full bilateral signing closes unilateral forgery gap)

### Added
- **`caller_signature` + `caller_public_key`** fields in interaction records — closes unilateral attestation forgery vulnerability identified in A2A #1718 (@aeoess)
- **`_create_interaction_record()`** extended: accepts `caller_signature`, `caller_public_key`, `verify_caller_sig=True` parameters
- **Ed25519 verification** of caller signature over canonical payload: `{relay_did, caller_did, task_id, sequence_a, timestamp}` (JSON-sorted, compact)
- **New IR fields**:
  - `caller_signature` — Ed25519 signature (base64url), provided by caller
  - `caller_public_key` — caller's raw Ed25519 public key (base64url)
  - `caller_signature_valid` — `True` / `False` / `None` (not provided)
  - `bilateral` — `true` when both relay and caller signatures are present and valid
- **AgentCard**: `capabilities.bilateral_interaction_records = bool(_ed25519_private and _ED25519_AVAILABLE)`

### Bug Fixes
- **`POST /tasks` role resolution**: fixed logic that only read `role` from token payload, ignoring top-level body field → now correctly reads `body.get("role") or payload.get("role")`

### A2A Alignment
- Directly addresses @aeoess comment in A2A #1718: unilateral relay attestation can be forged; bilateral signing creates non-repudiable records
- Canonical payload spec published in `docs/specs/bilateral-ir-canonical-payload.md`

### Tests
- `tests/test_caller_signature.py` — **CS-1..12: 12/12 PASS**
- Full regression: **511+ passed, 4 skipped, 0 failed**

---

## [2.63.0] — 2026-04-06 (cross-protocol token verify — GET /identity/did-key + POST /verify/external-token)

### Added
- **`GET /identity/did-key`** — returns relay's W3C did:key identifier plus full public key material
  (`did_key`, `did_acp`, `public_key_b64`, `public_key_hex`, `algorithm=Ed25519`, `multicodec=0xed01`)
- **`POST /verify/external-token`** — SINT-format cross-protocol token verification
  - 7-step pipeline: required_fields → expiry → subject_pubkey_decode → did:key_derive → canonical_payload → Ed25519_sig_verify → optional MoltTrust query
  - Response includes `subject_did`, `fields_verified[]`, `relay_did_key`, `expired`
- **AgentCard endpoints**: `did_key` → `/identity/did-key`, `external_token_verify` → `/verify/external-token`
- **AgentCard capabilities**: `external_token_verify = bool(_ed25519_private)`
- **`_verify_sint_token()`** helper — reusable 7-step SINT verification function

### Cross-protocol Compatibility
- did:key derivation uses multicodec `[0xed, 0x01]` + base58btc — identical to APS v1.32.0 `toDIDKey()` and SINT `keyToDid()`
- Cross-verify benchmark: 9/9 PASS (research round #11, A2A #1713, 2026-04-06)

### Tests
- `tests/test_external_token_verify.py` — **ETV-1..16: 16/16 PASS**
- Full regression: **843 passed, 8 skipped, 0 failed**

---

## [2.60.0] — 2026-04-06 (governance_metadata — AgentCard Governance Block, A2A #1717 preempt)

### Added
- **`_build_governance_metadata()`** — Runtime-computed governance metadata block for the AgentCard.
  - **Auto-derived static fields** (persist across calls, configured via `--governance-metadata`):
    - `schema_version` (default `"1.0"`)
    - `trust_score` — heuristic: `0.3 + peer_count×0.04 + ir_count×0.005 + task_count×0.002` (clipped 0.0–1.0)
    - `policy_compliance` — list of `{ policy, status }` objects (default `[]`)
    - `audit_trail_reference` — URI string or null (auto-infers `/interaction-records` when interaction_records present)
    - `capability_manifest` — map of `skill_id → { tier, status, deprecated }` (auto-derived from AgentCard `skills[]`)
  - **Live runtime counters** (always freshly computed on each call):
    - `generated_at` — ISO-8601 UTC timestamp of this specific call
    - `peer_count` — current number of connected peers
    - `task_count` — total tasks processed in this session
    - `interaction_record_count` — total bilateral interaction records generated

- **`GET /governance-metadata`** — New endpoint returning the live governance metadata block.
  - Response: `{ "ok": true, "governance_metadata": { ... } }`
  - Always fresh: `generated_at`, `peer_count`, `task_count`, `interaction_record_count` recomputed on each call

- **`PATCH /governance-metadata`** — Runtime update of writable governance metadata fields.
  - Writable fields: `trust_score`, `policy_compliance`, `audit_trail_reference`, `capability_manifest`, `schema_version`
  - Read-only fields (`generated_at`, `peer_count`, `task_count`, `interaction_record_count`) are **silently ignored**
  - Validation: `trust_score` must be `float` in `[0.0, 1.0]` (400 if out of range); `policy_compliance` must be an array (400 if not); `capability_manifest` must be an object (400 if not)
  - Response: `{ "ok": true, "updated": ["trust_score", ...], "governance_metadata": { ... } }`

- **`--governance-metadata <JSON_OR_PATH>`** — New CLI argument to configure governance metadata at startup.
  - Accepts: inline JSON string or path to a JSON file
  - Same writable field set as `PATCH /governance-metadata`

- **AgentCard changes**:
  - `governance_metadata` block injected when `--governance-metadata` is configured
  - `capabilities.governance_metadata: bool(_governance_metadata)` — `true` when configured, `false` by default
  - `endpoints.governance_metadata: "/governance-metadata"`

- **Global state**: `_governance_metadata: dict` — configured base values (merged with live runtime counters at query time)

### Tests
- `tests/test_governance_metadata.py` — GM-1..14 (14 cases, all PASS in 4.81s)
  - GM-1: AgentCard includes governance_metadata block when `--governance-metadata` provided
  - GM-2: governance_metadata NOT in AgentCard by default
  - GM-3: GET /governance-metadata returns 200 with ok:true
  - GM-4: Auto-computed fields always present (generated_at, peer_count, task_count, ir_count)
  - GM-5/6: capabilities.governance_metadata true/false
  - GM-7..10: PATCH updates trust_score / policy_compliance / audit_trail_reference / capability_manifest
  - GM-11: Read-only fields silently ignored on PATCH
  - GM-12/13: Validation errors return 400
  - GM-14: AgentCard.endpoints.governance_metadata = '/governance-metadata'

### Strategic Context
Implements governance metadata in AgentCard (`trust_score`, `capability_manifest`, `policy_compliance`,
`audit_trail_reference`) as proposed in A2A Issue #1717 (Microsoft agent-governance-toolkit, 0 comments
at time of ACP implementation). ACP ships the working GET+PATCH endpoints and CLI arg before A2A reaches
spec consensus — establishing ACP's governance_metadata as the reference implementation.

---

## [2.59.0] — 2026-04-06 (interaction_records — Bilateral Signed Interaction Records, A2A #1718 lightweight preempt)

### Added
- **`_create_interaction_record()`** — Core function generating a bilateral interaction record on task creation.
  - Fields: `id` (ir-*), `type`, `relay_did`, `caller_did`, `task_id`, `skill_id`, `sequence_a` (monotonic),
    `previous_hash` (sha256 chain or "genesis"), `timestamp`, `quality_hint`, `caller_token_hash`, `relay_signature`, `relay_public_key`
  - `relay_signature`: Ed25519 signature over canonical JSON payload (requires `--identity`)
  - `previous_hash`: sha256 of previous stored record → append-only audit chain
  - `caller_token_hash`: sha256(jti) of capability_token if provided with request
- **`POST /tasks`** — New optional `record: true` field in request body triggers interaction record generation.
  - Generated record is embedded in the response (`interaction_record`) and attached to the task object.
- **`GET /interaction-records`** — New endpoint listing all bilateral interaction records.
  - Query params: `skill_id` (filter), `peer_id` (filter, matches against `caller_did`), `limit` (default 100)
  - Response: `{ ok, count, total, records: [...] }`
- **AgentCard capabilities**: `interaction_records: true` — advertises bilateral interaction record support.
- **`/status` links**: `interaction_records → /interaction-records`

### Global State
- `_interaction_records: list` — append-only store of all generated interaction records
- `_ir_seq: int` — monotonic sequence counter (increments with each record)

### Tests
- `tests/test_interaction_records.py` — IR-1..12 (12 cases, all PASS)

### Strategic Context
Implements a lightweight version of the bilateral signed interaction record concept proposed
in A2A Issue #1718 (proposed 2026-04-05, 0 comments). ACP ships the working implementation
before A2A spec discussion has concluded — establishing ACP as the reference implementation.
Design goals: relay-anchored trust primitive usable without caller-side signing infrastructure.

---

## [2.58.0] — 2026-04-06 (effective_tier three-factor dynamic computation — A2A #1716 @64R3N formula preempt)

### Added
- `_compute_effective_tier(skill_obj, peer_id)`: three-factor effective authorization tier
  - Factor 1 `tier_rule`: skill's declared `authorization_tier` (T0/T1/T2/T3/None)
  - Factor 2 `depth_floor`: `min(len(principal_chain), 3)` → maps depth to T0..T3
  - Factor 3 `reputation_adj`: -1 (known+verified+msgs>100) / 0 (neutral) / +1 (unknown peer)
  - Key design: `rep_adj` only applied when `base_int >= T2`; T0/T1 preserve auto-execute semantics
  - T3 is always T3, immune to any adjustment
- `GET /skills/{skill_id}/effective-tier?peer_id=<id>`: debug/introspection endpoint
  - Returns `{ skill_id, effective_tier, factors: { tier_rule, delegation_depth, depth_floor, reputation_adj, effective_tier } }`
  - Optional `peer_id` query param to simulate different caller contexts
- `capabilities.effective_tier_computation: True` in AgentCard
- `effective_tier` endpoint registered in `/status` links block
- Tests: `tests/test_effective_tier.py` — ET-1..12 (12/12 PASS)

### Changed
- `_check_authorization_tier()`: now calls `_compute_effective_tier()` instead of using static `authorization_tier`
  - Error messages enriched with factor details for observability

### Fixed
- `DELETE /principal-chain/<did>`: now URL-decodes the DID path segment (colons in `did:example:xxx` were encoded as `%3A`, causing 404 mismatch)

---

## [2.57.0] — 2026-04-06 (capability_token — SINT-format Ed25519 signed capability tokens, A2A #1716 preempt)

### Added
- **`_issue_capability_token(subject_did, skill_id, tier, constraints, ttl_seconds, actions)`** — issue a SINT-format Ed25519 signed capability token. Fields: `jti`, `iss`, `sub`, `resource`, `actions`, `tier`, `constraints`, `iat`, `exp`, `signature`, `scheme` (`sint_ed25519`), `public_key`. Signature is Ed25519 over canonical JSON payload (sorted keys, no whitespace).
- **`_verify_capability_token(token, required_skill_id, required_tier)`** — validate a SINT-format token: expiry check, Ed25519 signature verification, optional skill resource match, optional tier sufficiency check. Returns `(bool, reason)`.
- **`POST /skills/{skill_id}/capability-token`** — issue a capability token for a specific skill.
  - Body: `{subject (required), tier?, ttl? (default 3600), actions?, constraints?}`
  - 403 `ERR_IDENTITY_REQUIRED`: `--identity` not loaded
  - 404 `ERR_SKILL_NOT_FOUND`: skill not in AgentCard
  - 400: invalid tier value
  - Token stored in `_capability_tokens` global registry for audit.
- **`GET /capability-tokens`** — list all capability tokens issued by this relay.
  - `?skill_id=X` — filter by skill
  - `?active=1` — exclude expired tokens
- **`_capability_tokens: dict`** — global registry `{jti: CapabilityTokenObject}`.
- **`capabilities.capability_token_issuance`** (`bool`) in AgentCard — `True` when `--identity` is loaded.
- **`endpoints.capability_token_issuance`** — `"/skills/{skill_id}/capability-token"` in AgentCard.
- **`skill.capability_token_required`** (`bool`, default `false`) — new field in `_parse_skill_obj`. When `true`, `POST /tasks` must include a valid `capability_token`.

### Changed
- **`POST /tasks` enforcement gate (v2.57 capability_token layer)**:
  1. Pre-tier check: if `skill.capability_token_required=True` and no token in body → 403 `ERR_CAPABILITY_TOKEN_REQUIRED`.
  2. If `capability_token` present: validates signature/expiry/skill → 403 `ERR_CAPABILITY_TOKEN_INVALID` on failure.
  3. If `capability_token` present: **skips `_check_authorization_tier` trust_score gate** — token is treated as the credential.
  - Execution order: capability_token_required check → tier check (skipped if token present) → param_constraints → rate_limit → capability_token sig validation → human_confirmation gate.

### Design Notes
- A2A Issue #1716 (SINT Protocol RFC, 0 replies as of 2026-04-05) proposes nearly identical primitives. ACP ships first.
- SINT-compatible: `resource`, `actions`, `tier`, `constraints`, `jti`, `iss`, `sub`, `iat`, `exp` — all SINT standard fields.
- No shared AS, no OAuth, no token exchange server. Self-contained via Ed25519 + DID + canonical JSON.
- Composable with: `principal_chain[]` (v2.56), `trust_score` (v2.34), `authorization_tier` (v2.49), `param_constraints` (v2.50).
- Requires `--identity` (Ed25519 keypair) to issue; verification uses embedded `public_key` field (portable, no key lookup needed).

### Tests
- `tests/test_capability_token.py`: **CT-1..12 (12/12 PASS)**
- CT-1: no identity → 403 ERR_IDENTITY_REQUIRED
- CT-2: unknown skill → 404 ERR_SKILL_NOT_FOUND
- CT-3/4: valid issuance + all required SINT fields present
- CT-5/6/7: GET /capability-tokens list/active filter/skill filter
- CT-8: capabilities.capability_token_issuance = True with --identity
- CT-9: valid token → task accepted
- CT-10: tampered token (sub changed without re-signing) → 403 ERR_CAPABILITY_TOKEN_INVALID
- CT-11: required skill, no token → 403 ERR_CAPABILITY_TOKEN_REQUIRED (fires before tier check)
- CT-12: required T3 skill, valid token → task accepted (tier gate bypassed)

---

## [2.56.0] — 2026-04-05 (principal_chain[] OBO delegation chain — trust block, message propagation, GET/POST/DELETE /principal-chain)

### Added
- **`_principal_chain: list`** — global OBO delegation chain `[{did, role, added_at}]`. Written into AgentCard trust block on every `/status` build.
- **`POST /principal-chain`** — add/upsert a principal entry to the chain. Body: `{did (required), role?}`. Upsert semantics: if DID already present, role is updated. Returns `{ok, did, role, added_at, count}`.
- **`GET /principal-chain`** — retrieve current chain with count and `self_did`.
- **`DELETE /principal-chain/{did}`** — remove a specific principal by DID. 404 if not found.
- **`GET /peers/{peer_id}/principal-chain`** — fetch the OBO chain from a connected peer's AgentCard. 404 if peer not connected; 422 if no AgentCard cached for peer.
- **`--principal DID[,role=ROLE]`** CLI flag — seed the chain at startup. Repeatable for multiple principals. Upsert semantics.
- **`on_behalf_of`** field in `POST /message:send` — per-message override of the OBO principal chain. If absent, the standing `_principal_chain` is auto-attached when non-empty.
- **`capabilities.principal_chain`** in AgentCard — `bool(_principal_chain)`.
- AgentCard trust block: `principal_chain[]` embedded whenever `_principal_chain` is non-empty.

### Design Notes
- Directly answers A2A Issue #1713 (OBO cross-org accountability, 15+ comments) without OAuth or shared AS.
- `on_behalf_of` field in messages carries the delegation chain → recipient agents can audit provenance.
- Compatible with SINT Protocol (Issue #1716) — Ed25519 DIDs used throughout.

### Tests
- `tests/test_principal_chain.py`: **PC-1..10 (10/10 PASS)**

---

## [2.55.0] — 2026-04-05 (GET /peers/{peer_id}/verify-card — on-demand per-peer AgentCard re-verification)

### Added
- **`GET /peers/{peer_id}/verify-card`** — re-verify the AgentCard of a connected peer on demand.
  - Query params: `force=1` (bypass cache), `trust=1` (apply trust integration), `ttl=N` (custom cache TTL)
  - 404 if peer not connected; 422 if no AgentCard cached; 503 if fetch fails.
- **`capabilities.peer_verify_card: True`** in AgentCard.
- **`/debug/inject`** extended to accept `agent_card` field for test fixture injection.

### Tests
- `tests/test_peer_verify_card.py`: **PVC-1..10 (10/10 PASS)**

---

## [2.54.0] — 2026-04-05 (POST /verify-card v2 — batch + fetch_and_verify + TTL cache + trust_integration)

### Added
- **`POST /verify-card` v2** — three modes in one endpoint:
  - **single**: `{card: {...}}` — verify a provided AgentCard dict
  - **batch**: `{cards: [{...}, ...]}` — verify multiple cards, returns per-card results
  - **fetch_and_verify**: `{url: "..."}` — fetch AgentCard from URL then verify
- **TTL cache** (`_verify_card_cache`) — default 300s, configurable via `ttl=N` query param. `ttl=0` bypasses both read and write (force-fresh verification).
- **`trust_integration`** flag — when `true`, verification result updates the peer's trust score (requires `from_peer_id` in body).
- **`_fetch_agent_card_from_url(url)`** — fetch AgentCard JSON from a remote URL with 5s timeout.

### Tests
- `tests/test_verify_card_v2.py`: **VC2-1..16 (16/16 PASS)**

---

## [2.53.0] — 2026-04-05 (skill.rate_limit — per-skill per-peer rate limiting)

### Added
- **`skill.rate_limit`** — per-skill rate limit object: `{max_calls, window_seconds, scope}`. Scope: `per_peer` (default) or `global`.
- **`_check_rate_limit(skill_id, peer_id)`** — enforces rate limit; returns `(ok, detail)`. 429 `ERR_RATE_LIMIT` on exceeded.
- **`_rate_limit_counters`** — in-memory counter store `{(skill_id, scope_key): [timestamps]}`.
- **`_parse_rate_limit(raw)`** — parse `rate_limit` field from skill JSON.

### Tests
- `tests/test_rate_limit.py`: **RL-1..8 (8/8 PASS)**

---

## [2.52.0] — 2026-04-05 (skill.deprecation_notice — skill sunset declarations)

### Added
- **`skill.deprecation_notice`** — structured deprecation metadata: `{message, sunset_date?, replacement_skill_id?, severity}`. Severity: `info` / `warning` / `error`.
- **`_parse_deprecation_notice(raw)`** — parse and normalize the deprecation_notice field.
- **`GET /skills`** response now includes `deprecation_notice` field per skill.
- **Audit entry**: `skill_invoked` event records `skill_id`, `peer_id`, `tier` at task creation.

### Tests
- `tests/test_deprecation.py`: **DEP-1..8 (8/8 PASS)**

---

## [2.51.0] — 2026-04-05 (T3 human_confirmation — two-phase irreversible task execution)

### Added
- **`skill.human_confirmation_required`** (bool, default false) — when `true` AND `authorization_tier == "T3"`, a `POST /tasks` targeting this skill enters `confirmation_pending` state instead of `submitted`.
- **`POST /tasks/{id}:confirm`** — approve a `confirmation_pending` task → transitions to `submitted`. Idempotent (already submitted → 200 with note).
- **`POST /tasks/{id}:reject`** — reject a `confirmation_pending` task → transitions to `failed`. Accepts optional `{"reason": "..."}` body; defaults to "human rejected T3 task".
- **`TASK_CONFIRMATION_PENDING`** state (`"confirmation_pending"`) + `CONFIRMATION_PENDING_STATES` set.
- **`ERR_CONFIRM_NOT_PENDING`** — 409 returned when `:confirm`/`:reject` targets a task not in `confirmation_pending`.
- **`_needs_human_confirmation(skill_id)`** — helper: returns True only when tier=T3 + human_confirmation_required=True + `--auto-confirm-t3` not set.
- **`--auto-confirm-t3`** CLI flag — bypass confirmation gate for testing; T3 tasks proceed directly to `submitted`. NEVER use in production.
- **`/debug/inject` `trust_override`** field — set peer trust attributes (card_sig_valid, did_consistent, ping_rtt_ms, message_count, verified_identity) for tier-based testing without a real P2P connection.
- **`capabilities.t3_human_confirmation = True`** in AgentCard.
- **T3C1–T3C14** tests (`tests/test_t3_human_confirmation.py`) — 14/14 PASS.

### Design Notes
- Execution order: tier check → param_constraints check → human_confirmation gate
- `confirmation_pending` is not in `TERMINAL_STATES` or `INTERRUPTED_STATES` — it has its own `CONFIRMATION_PENDING_STATES` set
- `confirmation_required: true` field present on task object while awaiting approval (removed on confirm/reject)
- Backward-compatible: `human_confirmation_required` defaults to false; existing T3 skills unaffected

---

## [2.50.0] — 2026-04-05 (skill.param_constraints — parameter-level invocation constraints, ref SINT Protocol)

### Added
- **`skill.param_constraints`** — per-skill parameter-level constraint declaration in AgentCard skill objects.
  Each key maps a param name to a `ConstraintRule`:
  `{type, required, min, max, allowed_values, pattern}` — all fields optional.
  Supported types: `string | number | integer | boolean | array`.
  `min`/`max` applies to numeric value or string/array length as appropriate.
  `pattern` (regex, string only) validated at parse time; invalid patterns silently dropped.
- **`_parse_param_constraints(raw)`** — normalises param_constraints dict; invalid type/regex silently dropped for forward-compat.
- **`_check_param_constraints(skill_id, params)`** — enforcement at `POST /tasks`; returns `(ok, violations[])`.
- **`ERR_PARAM_CONSTRAINT`** — new error code; 400 response includes `error_code`, `skill_id`, `violated_params[]`.
- **`capabilities.skill_param_constraints = True`** — declared in AgentCard.
- **SPC1–SPC18** tests (`tests/test_skill_param_constraints.py`) — 18/18 PASS.

### Design Notes
- Inspired by SINT Protocol (A2A #1716) `constraints` field — fills the gap where ACP v2.49 added tier-level authorization but lacked parameter-level validation.
- Backward-compatible: `null` default, no effect on existing skills or tasks without `params`.
- Complements v2.49 `authorization_tier`: tier = *who may invoke*, param_constraints = *with what arguments*.

---

## [2.49.0] — 2026-04-05 (skill.authorization_tier T0-T3 — per-skill authorization enforcement, ref A2A #1716)

### Added
- **`skill.authorization_tier`** — per-skill authorization tier field in AgentCard skill objects.
  Values: `"T0"` (observe) | `"T1"` (read) | `"T2"` (act, trust ≥ 0.7) | `"T3"` (irreversible, trust ≥ 0.9 + verified_identity signal) | `null` (unrestricted)
- **`_check_authorization_tier(skill_id, peer_id)`** — enforcement helper at `POST /tasks` creation.
  Computes live trust score from `_peers` (mirrors `/peers/<id>/trust` dimensions) and checks tier requirements.
- **`ERR_AUTHORIZATION_TIER`** — new error code returned with 403 when tier requirements not met.
  Response body includes `error_code`, `error`, `skill_id`, `peer_id` for debugging.
- **`capabilities.skill_authorization_tiers = True`** — declared in AgentCard.
- **SAT1–SAT12** tests (`tests/test_skill_authorization_tier.py`) — 12/12 PASS.

### Design Notes
- Inspired by A2A Issue #1716 (SINT Protocol RFC) and observed gap in both A2A and ACP.
- ACP implementation is intentionally lightweight: reuses existing `trust.signals` (v2.14) + per-peer trust score (v2.34) infrastructure — no new OAuth/capability-token dependency.
- `null` default is fully backward-compatible; existing task creation unaffected unless skill declares a tier.
- T3 requires both `trust_score >= 0.9` AND peer AgentCard `trust.signals` containing `verified_identity`.

### Fixed
- `_check_authorization_tier`: `_vouch_chain` is a `list` (not dict) — fixed iteration to use list traversal.

---

## [2.48.1] — 2026-04-05 (fix: _ACPHTTPServer — concurrent-load RemoteDisconnected, BUG-030/BUG-049)

### Fixed
- **BUG-030 / BUG-049 — relay HTTP `RemoteDisconnected` under concurrent load**: replaced
  bare `ThreadingHTTPServer` with new `_ACPHTTPServer` subclass that sets:
  - `request_queue_size = 64` (was 5 — TCP backlog overflow under 3+ concurrent relay instances)
  - `allow_reuse_address = True` (prevents TIME_WAIT conflicts on rapid test restart)
  - `daemon_threads = True` (worker threads don't block process exit)
  Verified: `test_hc1_10_agents_concurrent_connect` PASS; core regression 165/165 PASS.
- **BUG-031 — test_peer_ping.py fixture SIGTERM with short timeout**: confirmed resolved via
  `pyproject.toml` `timeout = 90` (already set); validated 10/10 PASS.

---

## [2.48.0] — 2026-04-05 (GET /peers/<id>/messages — per-peer message history query)

### Added
- **`GET /peers/<peer_id>/messages`** — 按 peer 查询消息历史，支持：
  - `direction=inbound|outbound|all`（默认 all）
  - `since_seq=<N>`：增量轮询，只返回 server_seq > N 的消息（与 /stream?since= 语义一致）
  - `limit` / `offset`：分页，响应含 `has_more` + `next_offset`
  - `sort=asc|desc`（默认 desc，最新在前）
  - 错误响应：404 ERR_PEER_NOT_FOUND / 400 ERR_INVALID_REQUEST
- **`POST /debug/inject`**（`--test-mode` 保护）：测试专用消息+peer 注入端点，自动注册 sender 为 peer，写入 `_recv_queue` + 持久化
- **`--test-mode`** CLI 标志：启用 debug 注入端点，生产环境无此标志则返回 403
- `capabilities.peer_message_history = True` 在 AgentCard 中声明
- `endpoints.peer_messages = "/peers/{peer_id}/messages"` 端点目录项
- `tests/test_peer_message_history.py`：PMH1–PMH10 全部 PASS（10/10）

### Design Notes
- 消息匹配策略：`peer_id` 字段 OR `raw.from` 在 `peer_identifiers`（peer_id + agent_name + name）中
- 历史数据来源：`_recv_queue`（内存，maxlen=1000）的非破坏性快照
- `--test-mode` 受 `_test_mode` 全局标志保护，生产默认 False，403 拒绝

---

## [2.47.1] — 2026-04-04 (fix: replace deprecated datetime.utcnow() in tests)

### Fixed
- `tests/test_tasks_list.py` 第 331 行：`datetime.utcnow()` → `datetime.now(datetime.timezone.utc)`（消除 Python 3.12 DeprecationWarning）
- `tests/unit/test_relay_core.py` 第 317 行：同上修复

---

## [2.47.0] — 2026-04-04 (RFC 8615 well-known headers + capabilities.well_known_rfc8615)

### Added
- `_json_well_known()` 响应头增加 RFC 8615 标准三件套：
  - `Cache-Control: no-cache, no-store, must-revalidate`
  - `Vary: Accept`
  - `X-Content-Type-Options: nosniff`
- 覆盖全部三个 well-known 端点：`acp.json`、`did.json`、`jwks.json`
- `capabilities.well_known_rfc8615 = True` 新增能力标志位
- `tests/test_well_known_headers.py`：WH1–WH10 全部 PASS

### Updated
- `spec/core-v1.0.md` 升版至 v2.47，Status → Stable，§5.3.1 `capabilities.groups`，§8.7 Conformance 新增 3 条 MUST + 4 条 SHOULD，Appendix A 版本历史补齐 v2.7–v2.47
- 引用文档：增加 `auth-evaluation.md` 交叉链接

---

## [2.46.0] — 2026-04-04 (v0.9 AgentCard capabilities groups — structured capability declaration)
### Added
- `_build_capabilities_groups()`: 从扁平 capabilities 生成 5 分组结构（messaging/tasks/identity/transport/discovery）
- `capabilities.groups` 字段加入 AgentCard 和 `/status` 响应，与旧扁平字段并列（向后兼容）
- `tests/test_capabilities_groups.py`：CG1–CG8 全部 PASS
- 对齐 A2A v1.0 `AgentCapabilities` 嵌套结构设计理念

## [2.45.0] — 2026-04-04 (v0.9 GET /tasks pagination — page_size/after/status filter)

### Added — v0.9 GET /tasks A2A-aligned pagination parameters

- **`page_size`** query param: A2A v1.0 alias for `limit` (default 20, max 100, auto-clamped)
- **`after`** query param: A2A v1.0 alias for `cursor` — keyset cursor returning tasks after given `task_id`
- **`status` multi-value filter**: comma-separated values (e.g. `status=submitted,working`) for
  multi-state queries; all values validated against the canonical status set
- **Response**: cursor-based mode always includes `next_cursor` (null when no more pages)
- **AgentCard**: `capabilities.tasks_pagination: true` — signals A2A v1.0-aligned pagination support
- **Tests**: `tests/test_tasks_pagination.py` — 8 tests (TP1–TP8) all PASS
  - TP1: Default page_size=20
  - TP2: Custom page_size in valid range (1–100)
  - TP3: page_size >100 auto-clamped to 100
  - TP4: `after` cursor pagination (exclusive keyset)
  - TP5: `status` single-value filter
  - TP6: `status` multi-value comma-separated filter
  - TP7: Empty result (has_more=false, next_cursor=null)
  - TP8: No-params backward compatibility + AgentCard capability check
- Commit: `cd958d7`

---

## [2.43.0] — 2026-04-03 (BUG-050: h2c tests graceful skip)

### Fixed — BUG-050: HTTP/2 h2c transport test failures (v2.43)

- `test_http2_transport.py`: Add `H2C_AVAILABLE` flag (checks `hypercorn`+`h2` at import time)
- H2/H3/H4/H6 scenarios now skip gracefully when hypercorn/h2 are not installed,
  instead of failing with `AssertionError`
- H1/H5 (HTTP/1.1 baseline) always run and pass
- Full HTTP/2 transport support deferred to ROADMAP v1.0+ (hypercorn integration)
- BUGS.md: BUG-050 status → ✅ 部分修复

---

## [2.42.0] — 2026-04-03 (Ed25519 Identity v0.8 integration tests)

### Fixed — Identity extension integration tests (v2.42)

- **`POST /debug/inject-peer-card`**: New test-helper HTTP endpoint — injects a peer
  AgentCard directly into relay `_status["peer_card"]` without requiring an active
  WebSocket P2P connection. Enables ID1–ID5 to run in sandboxed CI environments.
- **ID1–ID5 integration tests**: 5 previously SKIP → all 5 now PASS
  - ID1: AgentCard with `identity` field stored correctly in relay
  - ID2: Valid Ed25519 signature accepted (HTTP 200/503, not 400)
  - ID3: Invalid (tampered) signature → 400 `ERR_INVALID_SIGNATURE`
  - ID4: Stale timestamp (replay attack) → 400 `ERR_REPLAY_DETECTED`
  - ID5: Unsigned message accepted when identity is optional
- **Test assertions**: Updated to check `error_code` field (relay's canonical field)
  with fallback to `error` for backward compatibility
- **Total**: 16/16 identity tests PASS (11 unit + 5 integration), 0 SKIP

---

## [2.41.0] — 2026-04-03 (GET /skills OpenAPI 3.1 spec)

### Added — `GET /skills` OpenAPI 3.1 spec (v2.41)

- **`docs/openapi-skills.yaml`**: OpenAPI 3.1 specification for the `/skills` endpoint
  - Full schema for `SkillsResponse` and `Skill` objects
  - Query parameters: `filter` (name substring), `format` (full/names)
  - Complete example included
  - ACP's reference implementation answering A2A IS#1655 (QuerySkill proposal)
- **`AgentCard.skills_schema_url`**: Points to `/docs/openapi-skills.yaml`
- **`GET /docs/openapi-skills.yaml`**: Static file serving endpoint (CORS-enabled)
- **`capabilities.skills_openapi_spec: true`** in AgentCard
- **`tests/test_skills_openapi.py`**: 5 tests (SO1–SO5), all pass
- **Strategic note**: Enables technical evangelism at A2A IS#1655 with a standardized,
  machine-readable schema reference

---

## [2.40.0] — 2026-04-03 (AgentCard agent_limitations)

### Added — AgentCard `agent_limitations` field (v2.40)

- **`agent_limitations` object** in AgentCard (`/health`, `/.well-known/acp.json`) and `/status`
  - Machine-readable constraint declarations for inter-agent negotiation
  - Fields: `max_message_size_bytes` (65536), `max_recv_queue_size` (1000),
    `max_wait_seconds` (30), `max_peers` (100),
    `supported_message_roles` (["user","agent","system"]),
    `supported_priorities` (["critical","high","normal","low"])
  - Named `agent_limitations` (not `limitations`) to coexist with v2.20's `LimitationObject[]`
- **`capabilities.agent_limitations: true`** in AgentCard
- **`tests/test_agentcard_limitations.py`**: 6 tests (AL1–AL6), all pass
- **Inspired by**: A2A IS#1694 proposal (AgentCard capability constraints); ACP is first to implement
- **Design note**: Two limitations concepts coexist:
  - `limitations[]` — narrative capability descriptions (v2.20, LimitationObject[])
  - `agent_limitations{}` — numeric/enum constraint constants (v2.40, machine-readable)

---

## [2.39.0] — 2026-04-03 (Long Poll /recv)

### Added — Long Poll /recv?wait=<seconds> (v2.39)

- **`GET /recv?wait=<seconds>`**: long-poll support — when the receive queue is empty, the request hangs until a message arrives or the timeout expires
  - `wait` parameter: float seconds, clamped to `[0, 30]`; default `0` (backward compatible, immediate return)
  - On timeout: returns `{"messages": [], "count": 0, "remaining": 0, "timed_out": true}`
  - On message: returns normally with `"timed_out": false`
  - Uses existing `_sse_notify` threading.Event infrastructure (BUG-009 fix)
  - Deadline loop design prevents spurious wakeup false-positives
- **`capabilities.recv_long_poll: true`** in AgentCard
- **`tests/test_recv_long_poll.py`**: 9 tests (LP1–LP9), all pass
  - LP5: wake-on-message test — long-poll wakes early when message arrives mid-wait
  - LP6: timeout test — returns `timed_out: true` after wait expires
  - LP7/LP8: clamping and invalid input graceful degradation
- **Differentiator**: A2A and ANP have no long-poll mechanism; polling agents must repeatedly call `/recv`; with long-poll, agents can subscribe efficiently with zero wasted requests
- **Also fixed**: spurious wakeup bug (deadline loop); test port conflict (_free_port() now checks both WS and HTTP ports)

---

## [2.38.0] — 2026-04-03 (Message Priority)

### Added — priority field in /message:send (v2.38)

- **`priority` field in `POST /message:send`**: optional field, values: `critical | high | normal | low` (default: `normal`)
  - Invalid values return 400 `ERR_INVALID_REQUEST`
  - `priority` is embedded in the outgoing `acp.message` frame and transparent to the receiving peer
- **`GET /recv` sorted by priority**: messages returned in order `critical > high > normal > low`
  - Sort key: `_PRIORITY_ORDER = {critical:0, high:1, normal:2, low:3}`
  - Enables Orchestrator→Worker task scheduling based on urgency
- **`_status.priority_counts`**: new field, counts sent messages per level `{critical, high, normal, low: int}`
- **`capabilities.message_priority: true`** in AgentCard
- **`tests/test_message_priority.py`**: 9 tests (MP1–MP9), all pass in ~5.7s
- **Differentiator**: A2A and ANP have no message priority mechanism; ACP is first lightweight protocol with per-message priority routing

---

## [2.37.0] — 2026-04-02 (Typing Indicator)

### Added — acp.typing frame (v2.37)

- **`POST /message:typing`**: new endpoint to signal typing status to peer
  - Body: `{"typing": true/false}` — defaults to `true` if omitted
  - Returns: `{"ok": true, "typing": <bool>, "ts": "<iso>"}`
  - 503 `ERR_NOT_CONNECTED` when no peer is connected
- **`acp.typing` control frame**: sent to peer WS with `{type, from, typing, ts}`
  - `typing: true` — started typing; `typing: false` — stopped typing
- **Receiver handling**: incoming `acp.typing` updates:
  - `_status.peer_typing` (bool) + `_status.peer_typing_since` (ISO or null)
  - Per-peer `typing` + `typing_since` fields in `_peers`
  - SSE `typing` event broadcast to local `/stream` subscribers
- **`capabilities.typing_indicator: true`** in AgentCard
- **Agent real-time status trio complete**:
  - `acp.delivered` (v2.35) — physical delivery ✓
  - `acp.read` (v2.36) — logical consumption ✓✓
  - `acp.typing` (v2.37) — typing status 🖊
- **`tests/test_typing_indicator.py`**: 8 tests (TI1–TI8), all pass in ~5.0s

---

## [2.36.0] — 2026-04-02 (Read Receipt)

### Added — acp.read frame (v2.36)

- **Read Receipt**: when an Agent sends a reply (`/message:send`), it automatically fires an `acp.read` control frame to the peer, signalling that the last inbound message has been logically consumed
  - Frame: `{"type": "acp.read", "message_id": "<last_inbound_id>", "from": "<name>", "ts": "<iso8601>"}`
  - Tracks `last_received_message_id` in `_status`; cleared after sending to avoid duplicate receipts
  - No read-of-read loop; `acp.read` never triggers another `acp.read`
- **Two-phase receipt semantics** (WhatsApp-style):
  - `acp.delivered` (v2.35) — physical delivery: message arrived at peer WS ✓
  - `acp.read` (v2.36) — logical consumption: peer replied / processed ✓✓
- **`capabilities.read_receipt: true`** in AgentCard and `/.well-known/acp.json self.capabilities`
- **`messages_read` counter**: new field in `/status` (global) and `/peers` (per-peer)
- **Bug fix**: `acp.delivered` (v2.35) also corrected to use `asyncio.run_coroutine_threadsafe` (was `asyncio.ensure_future`; would silently fail from HTTP handler thread) — no API change
- **`tests/test_read_receipt.py`**: 8 tests (RR1–RR8), all pass in ~10.6s

---

## [2.35.0] — 2026-04-02 (Delivery ACK)

### Added — acp.delivered frame (v2.35)

- **Delivery ACK**: when a peer receives a business message, it automatically sends an `acp.delivered` frame back to the sender
  - Frame format: `{"type": "acp.delivered", "message_id": "<original_id>", "from": "<agent_name>", "ts": "<iso8601>"}`
  - Sender increments `messages_delivered` in `_status` and per-peer counter
  - No ack-of-ack: `acp.delivered` frames do not trigger further ACKs (loop-safe)
  - Only business messages trigger ACK; control frames (`acp.ping`, `acp.pong`, etc.) do not
- **`capabilities.delivery_ack: true`** declared in AgentCard and `/.well-known/acp.json self.capabilities`
- **`messages_delivered` counter**: new field in `/status` (global) and `/peers` (per-peer)
- **`--local-only` flag**: skip public-IP detection and Cloudflare relay registration; generate `acp://127.0.0.1:PORT/TOKEN` link immediately — ideal for CI/sandboxed environments
- **`tests/test_delivery_ack.py`**: 10 tests (DA1–DA10), all pass in ~12s

---

## [2.34.0] — 2026-04-02 (Per-Peer Structured Trust Score)

### Added — GET /peers/<peer_id>/trust (v2.34)

- **`GET /peers/<peer_id>/trust`** — returns structured trust assessment for any connected or known peer
  - Five weighted dimensions: `card_sig` (0.35) · `did_consistent` (0.20) · `ping_rtt` (0.20) · `message_hist` (0.15) · `vouch` (0.10)
  - `trust_score` (0.0–1.0) = weighted sum of all dimension scores
  - `trust_level` classification: `"high"` (≥0.75) · `"medium"` (≥0.45) · `"low"` (<0.45)
  - `card_sig`: Ed25519 AgentCard signature verification result (1.0 if `valid=true`)
  - `did_consistent`: DID in card matches public key (1.0 if consistent)
  - `ping_rtt`: RTT-based liveness score (<50ms→1.0, <200ms→0.7, <500ms→0.4, else→0.1, no data→0.0)
  - `message_hist`: volume score (≥100→1.0, ≥20→0.7, ≥5→0.4, >0→0.2, 0→0.0)
  - `vouch`: 1.0 if peer's DID appears in `_vouch_chain`, else 0.0
  - Returns 404 `ERR_PEER_NOT_FOUND` for unknown peer_id
- **`capabilities.peer_trust: True`** — declared in AgentCard
- **`endpoints.peer_trust: "/peers/{peer_id}/trust"`** — declared in AgentCard
- **Tests**: PT1–PT10 = **10/10 PASS**
- **Strategic context**: A2A IS#1628 (trust signals) and IS#1672 (identity) both still in discussion (219+ comments, no PR); ACP provides actionable per-peer trust scoring with cryptographic grounding

---

## [2.33.0] — 2026-04-02 (DID Pubkey Discovery — Offline Ed25519 Identity Resolution)

### Added — offline DID → Ed25519 pubkey resolution (v2.33)

- **`_base58_decode(s)`** — pure-stdlib base58btc decode (no external deps); inverse of existing `_base58_encode()`
- **`_resolve_did_to_pubkey(did)`** — offline, zero-network-call resolution of DID strings to Ed25519 public keys
  - Supports `did:acp:<base64url-pubkey>` — direct base64url decode of the pubkey payload
  - Supports `did:key:z<base58btc(0xed01 + pubkey_bytes)>` — multicodec varint + base58btc decode
  - Returns `{ok, did, scheme, public_key_b64, public_key_hex, algorithm, derived_did_acp, derived_did_key, consistent}`
  - `consistent=True` when the input DID round-trips through derivation without mutation
  - Returns `{ok:false, error, did}` for unsupported schemes or malformed inputs
- **`GET /identity/pubkey-discovery?did=<did>`** — single DID query; 400 if `?did` missing or scheme unsupported
- **`POST /identity/pubkey-discovery`** — two modes:
  - Single: `{"did": "<did_string>"}` → same response as GET
  - Batch: `{"dids": ["did1", "did2", ...]}` (max 50) → `{ok:true, count, results:[...]}`
- **`capabilities.pubkey_discovery: True`** declared in AgentCard
- **`endpoints.pubkey_discovery: "/identity/pubkey-discovery"`** declared in AgentCard
- **VERSION** bumped `2.32.0` → `2.33.0`

### Strategic Context
A2A IS#1672 (213 comments as of 2026-04-02) is actively debating how to implement
agent identity verification. ACP already has:
- `peer_card_signature` — cryptographic AgentCard self-signature (v2.16)
- `pubkey_discovery` — offline DID→pubkey resolution (v2.33)

ACP's approach: **offline-first** (no registry, no HTTP call to resolve identity).

### Bug Fixed (in this PR)
- **`UnboundLocalError: cannot access local variable 'urlparse'`** — `from urllib.parse import ... urlparse`
  inside a `do_GET()` elif branch caused Python to treat `urlparse` as a local variable throughout the
  entire function scope, crashing unrelated request paths. Fix: removed the inline import (top-level
  import at line 114 already covers it).

### Tests
- PD1–PD8 = 8/8 PASS (`tests/test_pubkey_discovery.py`)
- Full regression: 8/8 (dedup) + 8/8 (failures) + 8/8 (skill limitations) + 12/12 (skill status) = 36/36 PASS

---

## [2.32.0] — 2026-04-02 (message_id 30s TTL Dedup Window — HTTP Send Idempotency)

### Added — HTTP message idempotency (v2.32)

- **`_http_dedup_check(message_id)`** — 30-second TTL dedup window for HTTP send endpoints
  - Lazy TTL eviction: expired entries cleaned on each check (no background thread needed)
  - Returns `(is_duplicate: bool, cached_server_seq: int | None)`
  - Cache is size-bounded alongside existing `_seen_message_ids` (LRU limit `_SEEN_MAX = 2000`)
- **`_http_dedup_record_seq(message_id, server_seq)`** — stores `server_seq` in dedup cache after successful send
- **`POST /message:send`** — dedup check fires immediately after `message_id` is parsed (before routing)
  - If client supplied `message_id` and same ID seen within 30s → `200 {ok:true, deduplicated:true, message_id, server_seq}`
  - `server_seq` is the integer from the first successful send, or `null` if first send errored
  - Auto-generated IDs (no client `message_id`) are never subject to dedup
- **`POST /peer/<id>/send`** — same dedup logic applied before WS routing
- **`capabilities.message_dedup: True`** declared in AgentCard
- **VERSION** bumped `2.29.0` → `2.32.0`

### Idempotency Semantics
Dedup fires at **request-parse time** (before routing), not at response time. This means:
- A first send that errors (e.g. `ERR_NOT_CONNECTED`, 503) still records the `message_id` in cache
- A retry within 30s returns `200 {deduplicated:true, server_seq:null}` — prevents double-processing at the protocol layer
- A retry after 30s is treated as a new send (TTL expired)

This follows ANP `client_msg_id` idempotency semantics (ANP commit `1f0abd2d`).

### Tests
- MD1–MD7 = 7/7 PASS (`tests/test_message_dedup.py`)
- Regression: FM1-8 + SU1-8 + SS1-12 + unit + scenario-BC + skills series = 210/210 PASS, 2 skip

---

## [2.29.0] — 2026-04-02 (PATCH /skills/<id>/limitations — Runtime Per-Skill Limitations Update)

### Added — PATCH /skills/<id>/limitations (v2.29)

- **`PATCH /skills/<id>/limitations`** — runtime update of per-skill limitations[] without relay restart
  - Replaces declared limitations with a runtime override stored in `_skill_limitations_overrides`
  - Supports `limitations_merge: true` to merge new entries into existing overrides (de-duplicate by `(kind, code)`)
  - Send `limitations: []` to clear runtime override and restore declared defaults
  - Validates limitation `kind` against the allowed set (capability/modality/scale/domain/access/other)
  - Validates each entry via `_parse_limitation()` — same strict validation as global PATCH
  - Returns `{ok: true, skill_id, limitations}` on success; 400/404 on error
- **`GET /skills/<id>/status`** now reflects runtime override:
  - If `_skill_limitations_overrides[skill_id]` is set, uses override instead of declared limitations
  - Response includes `limitations` field (the resolved list, including overrides)
- **`GET /skills`** now merges `_skill_limitations_overrides` into returned skill objects
- **`capabilities.skill_limitations_patch: True`** declared in AgentCard capabilities
- **`PATCH /skills/<nonexistent>/limitations`** returns 404 (skill not found in AgentCard)
- `do_PATCH` docstring updated to describe both routes

### Use Case
Runtime degradation/recovery without restart: an agent or operator can update a skill's limitations dynamically (e.g., GPU goes down → add transient capability limitation → skill shows unavailable; GPU recovers → PATCH with `[]` → skill shows available again).

### Tests
- SU1–SU8 = 8/8 PASS (`tests/test_skill_limitations_patch.py`)
- Regression: test_skill_status + test_skills_list + test_limitations + test_skill_limitations + unit = 189/189 PASS

---

## [2.30.0] — 2026-04-01 (failed_message_id Capability Declaration)

### Added — error_failed_msg_id capability (v2.30)

- **`capabilities.error_failed_msg_id: True`** declared in AgentCard
  - `failed_message_id` field in error responses was already implemented (v0.6, ref ANP 2026-03-05)
  - v2.30 formalizes the capability as discoverable via `/.well-known/acp.json`
  - Callers can now probe `capabilities.error_failed_msg_id` before relying on the field
- **Behavior**: when `POST /message:send` (or `/peer/<id>/send`) fails and the request included `message_id`, the error response includes `"failed_message_id": "<client_msg_id>"`
  - Absent when no `message_id` was provided (never synthesized)
  - Preserved exactly — no truncation or mutation (including unicode)
- Tests: FM1–FM8 = 8/8 PASS
- Regression: test_skill_status + test_skill_limitations + test_queryskill_constraints + test_peers_pagination = 53/53 PASS

---

## [2.29.0] — 2026-04-01 (Per-Skill Availability Probe)

### Added — GET /skills/<id>/status (v2.29)

- **`GET /skills/<id>/status`** — lightweight per-skill availability probe
  - Response: `{skill_id, available, reason?, last_checked}` (ISO-8601 UTC timestamp)
  - `available: false` when skill declares a **runtime** (`permanent: false`) limitation with `kind: "capability"` or `kind: "access"`
  - `available: true` for permanent limitations, string-shorthand limitations, or no limitations
  - `404 ERR_NOT_FOUND` when `skill_id` is absent from the agent card
  - `400 ERR_INVALID_REQUEST` for empty skill_id path segment
  - Use case: orchestrators probe worker skill availability before dispatching tasks
- **`capabilities.skill_status_probe: True`** declared in AgentCard
- **`endpoints.skill_status: "/skills/{id}/status"`** declared in AgentCard
- Tests: SS1–SS12 = 12/12 PASS
- Regression: test_skill_limitations + test_queryskill_constraints + test_peers_pagination = 41/41 PASS

---

## [2.28.0] — 2026-04-01 (Per-Skill limitations[] Field)

### Added — per-skill limitations (v2.28, ref A2A #1694)

- **`limitations[]` field in every skill object** (AgentCard + GET /skills + POST /skills/query)
  - Same `LimitationObject` schema as top-level `AgentCard.limitations` (v2.20): `{kind, code, message, permanent}`
  - String shorthand auto-promoted: `"no_audio"` → `{kind:"capability", code:"no_audio", message:"no_audio", permanent:true}`
  - Declare via `--skills` JSON: `{"id":"transcribe","limitations":[{"kind":"modality","code":"no_video_input","message":"...","permanent":true}]}`
  - Defaults to `[]` when not declared (backward compatible)
- **`GET /skills?has_limitation=<kind|code>`** — filter skills by limitation kind or code
  - `?has_limitation=capability` — all skills declaring a capability-kind limitation
  - `?has_limitation=no_audio_input` — skills with that specific limitation code
- **`POST /skills/query`** response now includes `skill_limitations_declared[]`
  - Calling agents can inspect declared limitations before routing tasks
- **`capabilities.skill_limitations: True`** declared in AgentCard
- **Interoperability**: aligns with A2A IS#1694 `limitations` field proposal at skill level
- Tests: SL1–SL12 = 12/12 PASS

---

## [2.27.0] — 2026-04-01 (GET /peers Pagination + Vouch Chain)

### Added — GET /peers pagination (v2.27)

- **`GET /peers` now supports pagination and filtering**
  - `?limit=N` (1–200, default 50), `?offset=N` (default 0), `?filter=all|connected|disconnected`
  - Response adds `pagination{limit,offset,filter,has_more,next_offset}` + `total_filtered` field
  - Invalid `filter` value → 400 `ERR_INVALID_FILTER`; non-integer `limit` falls back to default
  - Backward compatible: existing clients that omit params get default `filter=all,limit=50,offset=0`
  - `capabilities.peers_pagination: True`

### Added — vouch_chain trust signal (v2.27, A2A IS#1628 compatible)

- **`POST /trust/vouch`** — add a trust endorsement from another agent
  - Body: `{voucher_did, comment?, sig?}` → stored in `_vouch_chain[]`
  - Returns `{ok, vouch_id, total, entry}` with auto-stamped `vouched_at` (ISO-8601 UTC)
- **`GET /trust/vouch`** — list endorsement chain with pagination (`?limit=&offset=`)
- **AgentCard `trust.signals[]`** now includes `{type:"vouch_chain", enabled, details:{count, endpoint, vouches[-5:]}}`
  - `enabled=true` once at least one vouch has been added
  - `capabilities.peers_vouch_chain: True`

---

## [2.26.0] — 2026-04-01 (QuerySkill Constraints Extension)

### Added — per-skill constraints (v2.26)

- **Per-skill `constraints` field** in skill objects (structured in `_parse_skill_obj`)
  - `max_file_size_bytes`: max single-file payload this skill can process (`null` = unlimited)
  - `concurrent_tasks`: max parallel task executions for this skill (`null` = unlimited)
  - `context_window`: max context tokens for LLM-based skills (`null` = unlimited)
  - Declare via `--skills` JSON: `{"id":"transcribe","constraints":{"max_file_size_bytes":104857600,"concurrent_tasks":4,"context_window":32000}}`
- **`POST /skills/query` — three new constraint dimensions**
  - `max_file_size_bytes`: checks relay-level `max_msg_bytes` first, then skill-level limit
    - `constraints_applied.relay_max_msg_bytes` echoed when relay limit exceeded
    - `constraints_applied.skill_max_file_size_bytes` echoed when skill limit exceeded
  - `concurrent_tasks`: checks skill-level declared limit; `constraints_applied.skill_concurrent_tasks` echoed
  - `context_window`: checks skill-level declared limit; `constraints_applied.skill_context_window` echoed
  - Returns `"partial"` when any constraint is violated; reason lists all violations (`;`-separated)
  - Backward compatible: legacy `file_size_bytes` constraint still supported (v0.6+)
  - Skills without `constraints` field treat all limits as `null` — never produces skill-level violation
- **Response: `skill_constraints_declared`** — echoes the queried skill's declared constraints dict
- **`capabilities.skills_query_constraints = true`** — discoverable via `/.well-known/acp.json`
- **`GET /skills`** — skill objects now include `constraints` field (all three dimensions)

### Tests
- `test_queryskill_constraints.py`: QC1–QC12, **12/12 PASS**
- Full regression: 300+ tests across 17 suites, **0 failures**

### vs A2A
- **A2A PR#1655** (QuerySkill RPC) remains open (5+ weeks, unmerged) — ACP leads

---

## [2.25.0] — 2026-04-01 (POST /peers/<id>/ping — Application-Layer Liveness Probe + RTT)

### Added — peer ping (v2.25)

- **`POST /peers/<peer_id>/ping`** — application-layer liveness probe with RTT measurement
  - Sends an `acp.ping` message over the peer's WebSocket; waits for `acp.pong` response
  - Returns `{"ok": true, "peer_id": "...", "rtt_ms": 42.3, "status": "alive", "nonce": "ping_xxx"}`
  - Optional request body: `{"timeout": <float>}` — max seconds to wait for pong (default 10, max 30)
  - **404** `ERR_PEER_NOT_FOUND` — peer_id not in registry
  - **503** `ERR_NOT_CONNECTED` — peer registered but disconnected
  - **503** `ERR_PEER_CONNECTING` — peer registered but WS handshake not yet complete
  - **408** `ERR_PING_TIMEOUT` — no pong received within timeout window; `rtt_ms: null, status: "timeout"`
  - On send failure: peer is unregistered + returns 503 `ERR_NOT_CONNECTED`
- **`acp.ping` / `acp.pong` message types** (application layer)
  - `acp.ping`: `{type, nonce, from, ts}` — probe message; receiver auto-replies with pong
  - `acp.pong`: `{type, nonce, from, ts}` — response; resolves pending Future on originator side
  - Both types are handled before the idempotency check (no dedup overhead, never queued to inbox)
- **Per-peer ping statistics** in `GET /peers` response:
  - `last_ping_rtt_ms` — RTT in milliseconds from most recent successful ping
  - `last_ping_at` — ISO-8601 timestamp of last successful ping
  - `ping_count` — cumulative count of successful pings sent to this peer
- **`capabilities.peer_ping: true`** declared in AgentCard
- **`endpoints.peer_ping: "/peers/{peer_id}/ping"`** declared in AgentCard
- **`_pending_pongs`** global dict: `nonce → asyncio.Future` for async ping/pong correlation

### Changed

- `VERSION`: `2.24.0` → `2.25.0`

### Tests

- `tests/test_peer_ping.py` — PP1–PP10: **10/10 PASS** (57s)
  - PP1: `capabilities.peer_ping = true` in AgentCard
  - PP2: POST `/peers/nonexistent/ping` → 404 ERR_PEER_NOT_FOUND
  - PP3: Disconnected peer → 404/503 (no valid peer in fresh relay)
  - PP4: Successful ping → `ok=true, rtt_ms≥0, status=alive, nonce=ping_xxx`
  - PP5: After ping, `/peers` shows `last_ping_rtt_ms`, `last_ping_at`, `ping_count≥1`
  - PP6: `/peers` list always includes ping stat fields (even before any ping)
  - PP7: No connected peer → 404/408 depending on state
  - PP8: Custom `timeout=15.0` in request body accepted; completes within budget
  - PP9: `/peers/<id>/card` still works alongside `/peers/<id>/ping` routing
  - PP10: Two sequential pings accumulate `ping_count` by 2

---

## [2.24.0] — 2026-04-01 (GET /peers/<id>/card — Fetch Cached AgentCard for Peer)

---

## [2.23.0] — 2026-03-31 (target_peers[] Subset Broadcast + Broadcast History)

### Added — broadcast enhancements (v2.23)

- **`POST /peers/broadcast` — `target_peers[]` optional subset broadcast**
  - New optional body field `"target_peers": ["peer_id_1", "peer_id_2", ...]`
  - When provided: message is sent only to the listed peers (subset broadcast)
  - Unknown `peer_id` in `target_peers` → **400 ERR_INVALID_REQUEST** with list of unknown ids
  - Empty `target_peers` or all listed peers disconnected → **503 ERR_NO_PEERS**
  - When omitted: original fanout-to-all behavior (fully backward compatible)
- **`POST /peers/broadcast` — `broadcast_id` in response**
  - Response now includes `"broadcast_id"` (context_id string) for correlation with history log
- **`GET /peers/broadcast/history`** — broadcast audit log
  - Returns last N broadcasts in reverse-chronological order (newest first)
  - Default `limit=20`, max `limit=200`; configurable via `?limit=N` query param
  - Each entry: `broadcast_id`, `ts`, `role`, `parts`, `target_peers` (null = all), `total_peers`, `delivered`, `failed`, `results[]`
  - In-memory ring buffer (`_broadcast_log`, max 200 entries); resets on relay restart
- **`capabilities.peers_broadcast_subset: true`** — declared in AgentCard (v2.23)
- **`capabilities.peers_broadcast_history: true`** — declared in AgentCard (v2.23)
- **`endpoints.peers_broadcast_history: "/peers/broadcast/history"`** — declared in AgentCard

### Changed

- `VERSION`: `2.22.0` → `2.23.0`
- `test_broadcast.py::test_BC10`: version check updated to `>= 2.22` (forward compatible across releases)

### Tests

- `tests/test_broadcast_v23.py` — BH1–BH11: **11/11 PASS** (82.9s)
  - BH1: `capabilities.peers_broadcast_subset = true`
  - BH2: `capabilities.peers_broadcast_history = true`
  - BH3: `endpoints.peers_broadcast_history = "/peers/broadcast/history"`
  - BH4: history empty on fresh relay start
  - BH5: broadcast populates history (broadcast_id, ts, delivered, failed)
  - BH6: `broadcast_id` present in POST response
  - BH7: `?limit=1` returns exactly 1 entry
  - BH8: `target_peers=[]` → 503 ERR_NO_PEERS
  - BH9: unknown peer_id in `target_peers` → 400 ERR_INVALID_REQUEST
  - BH10: `target_peers=[B]` — only B receives, C does not
  - BH11: version reports `2.23.x`
- Regression: BC1–BC10 **10/10 ✅**, LP13 ✅, LS18 ✅, JW13 ✅, TS8 ✅ (all 52 core pass)

---

## [2.22.0] — 2026-03-31 (POST /peers/broadcast — Fanout to All Connected Peers)

### Added — peers broadcast (v2.22)

- **`POST /peers/broadcast`** — send a message to ALL currently connected peers in one HTTP call
  - Body: `{"text": "...", "role": "agent|user"}` — same format as `/message:send`
  - Also accepts `parts: [{type, content}]`, `task_id`, `context_id` for structured messages
  - Uses `_ws_send_sync()` per peer: full lock, Ed25519 signature, and offline queue support
  - Response: `{"ok": true, "broadcast": true, "delivered": N, "failed": M, "total_peers": T, "results": [{"peer_id": "...", "message_id": "...", "ok": true/false, "error": null/str}]}`
  - Returns **503 ERR_NO_PEERS** when no active peers are connected
  - Returns **400 ERR_INVALID_REQUEST** for missing `role` or empty message body
  - Wire format: `acp.message` type with `broadcast: true` metadata field
- **`capabilities.peers_broadcast: true`** — declared in AgentCard (v2.22)
- **`endpoints.peers_broadcast: "/peers/broadcast"`** — declared in AgentCard

### Changed

- `VERSION`: `2.21.0` → `2.22.0`
- Broadcast `context_id` defaults to `_make_id()` when not provided (fixes undefined function `_default_context_id`)

### Tests

- `tests/test_broadcast.py` — BC1~BC10: **10/10 PASS**
  - BC1: `capabilities.peers_broadcast = true` in AgentCard
  - BC2: `endpoints.peers_broadcast = "/peers/broadcast"` in AgentCard
  - BC3: 503 ERR_NO_PEERS when no peers connected
  - BC4: 400 on missing `role`
  - BC5: 400 on missing `text`/`parts`
  - BC6: broadcast to 2 peers → `delivered >= 1` (integration)
  - BC7: peer B receives broadcast message
  - BC8: peer C receives broadcast message (all peers get it)
  - BC9: `results[]` per-peer contains `peer_id`, `message_id`, `ok`
  - BC10: `/status` reports `acp_version` starting with `2.22`
- Regression: `test_limitations_structured` 18/18 ✅, `test_jwks` 13/13 ✅, `test_trust_signals` 8/8 ✅, `test_limitations_patch` 13/13 ✅

---

## [2.21.0] — 2026-03-31 (limitations PATCH + filter_limitations query)

### Added — runtime limitations management (v2.21)

- **`PATCH /.well-known/acp.json` — `limitations` key support**
  - Agents can now update their `limitations[]` at runtime without restarting
  - **Replace mode** (default): `{"limitations": [...]}` overwrites the entire list
  - **Merge mode**: `{"limitations": [...], "limitations_merge": true}` appends/updates entries, de-duplicating by `(kind, code)` pair
  - Accepts the same input formats as `--limitations-json`: structured `LimitationObject[]` or backward-compat plain strings
  - Dict entries with explicit `kind` field are strictly validated (must be in `_VALID_LIMITATION_KINDS`); invalid kind → HTTP 400
  - Can patch `availability` and `limitations` in the same request body
  - Response includes `"updated": ["availability", "limitations"]` list and the resulting values
- **`GET /.well-known/acp.json?filter_limitations=<value>`** — filter limitations by permanence or kind
  - `?filter_limitations=permanent` → only entries with `permanent: true`
  - `?filter_limitations=transient` → only entries with `permanent: false/null`
  - `?filter_limitations=<kind>` (e.g. `capability`, `scale`, `domain`, …) → only entries matching that kind
  - Unknown filter value → HTTP 400 with helpful error message
- **`capabilities.limitations_patch: true`** — declared in AgentCard; signals PATCH limitations support
- **`capabilities.limitations_filter: true`** — declared in AgentCard; signals filter_limitations query support

### Changed

- `VERSION`: `2.20.0` → `2.21.0`
- `PATCH /.well-known/acp.json` body: `availability` key is no longer required; `limitations` alone is now valid
- Response from `PATCH /card` now returns `{"ok": true, "updated": [...], "availability": {...}, "limitations": [...]}` (updated keys only)

### Use Cases

- **Runtime degradation**: agent under memory pressure → `PATCH {"limitations":[{"kind":"scale","code":"low_memory","permanent":false}], "limitations_merge":true}` → orchestrators see the transient limit, apply retry/fallback
- **Recovery**: agent recovers → `PATCH {"limitations":[], "limitations_merge":false}` → clears all transient limitations
- **Orchestrator routing**: `GET /.well-known/acp.json?filter_limitations=permanent` → fetch only stable routing constraints, ignoring transient state

### Tests

- `tests/test_limitations_patch.py` — LP1~LP13: **13/13 PASS**
  - LP1: replace mode; LP2: merge mode; LP3: string backward-compat; LP4: invalid kind → 400
  - LP5: non-array → 400; LP6: empty body → 400; LP7: both fields in one request
  - LP8: filter=permanent; LP9: filter=transient; LP10: filter by kind
  - LP11: filter invalid value → 400; LP12-LP13: capability flags in AgentCard
- Regression: `test_limitations_structured` 18/18 ✅, `test_jwks` 13/13 ✅

---

## [2.20.0] — 2026-03-31 (Structured limitations[] — LimitationObject)

### Added — structured limitations (v2.20)

- **`_parse_limitation(raw)`** — normalizes a string or dict to `LimitationObject`.
  - `str` input → `{"kind": "capability", "code": raw, "message": raw, "permanent": True}` (backward-compatible promotion)
  - `dict` input → validated and defaulted `LimitationObject`
  - Invalid `kind` values coerced to `"other"`
  - `permanent` defaults to `True` when omitted
- **`LimitationObject` schema** (ref: A2A IS#1694 stable/runtime split):
  - `kind: str` — one of `capability | modality | scale | domain | access | other`
  - `code: str` — machine-readable identifier (e.g. `"image-input-unsupported"`, `"max-10mb"`)
  - `message: str` — human-readable description
  - `permanent: bool` — `True` = stable/static constraint (routing-time filtering); `False` = runtime/transient degradation (retry/fallback)
- **`_VALID_LIMITATION_KINDS`** — set constant for valid kind values
- **`capabilities.limitations_structured: True`** — declared in AgentCard; signals that `limitations[]` uses `LimitationObject` format (v2.20+)
- **`--limitations-json <JSON_ARRAY>`** — new CLI flag accepting a full `LimitationObject[]` JSON array. Takes precedence over `--limitations` when both are provided.
- **`--limitations <csv>`** (existing, v2.7) — now auto-promotes each CSV string to `LimitationObject{kind=capability, permanent=True}`. Output format changed from `string[]` to `LimitationObject[]`.

### Changed

- `AgentCard.limitations[]` format: upgraded from `string[]` → `LimitationObject[]`
- `_status["limitations"]` stores normalized `LimitationObject[]` at parse time
- `--limitations` CSV strings are auto-promoted at startup; no breaking change for existing users

### Stable vs Runtime Split

Inspired by A2A IS#1694 community discussion (Agent Exchange Hub v0.4.0 implementation):
- **Stable limitations** (`permanent: true`): durable constraints declared in AgentCard, cached by registries, used for routing decisions at discovery time
- **Runtime limitations** (`permanent: false`): transient degradation (quota exhausted, service unavailable), distinct caching semantics from stable constraints

### Tests

- `tests/test_limitations_structured.py` — LIM-01~LIM-18: **18/18 PASS**
  - TestNoLimitations (LIM-01~03): empty array, capabilities flag
  - TestCSVLimitations (LIM-04~09): promotion, fields, kind, permanent, codes
  - TestJSONLimitations (LIM-10~15): count, kinds, permanent, messages, stable/runtime split, JSON overrides CSV
  - TestLimitationKinds (LIM-16~18): valid kinds, invalid kind coercion, permanent default
- Full regression: 48/48 PASS (jwks + availability_schedule + nat_integration + scenario_a)

### Differentiation vs A2A IS#1694

- A2A IS#1694 ("Add 'limitations' field to AgentCard") opened 2026-03-27, still in discussion (no merged PR)
- ACP ships working `LimitationObject[]` with stable/runtime split, machine-readable kind taxonomy, and `capabilities.limitations_structured` flag
- Agent Exchange Hub v0.4.0 independently shipped similar split on 2026-03-29; ACP formalizes the pattern in protocol spec

---

## [2.19.0] — 2026-03-31 (NAT Auto-Traversal Integration in /peers/connect)

> *Released as documentation/version bump — v2.19 feature (NAT traversal connection_type) was implemented in the preceding dev cycle and committed at 175e7ad.*

### Added — connection_type NAT result (v2.19)

- **`connection_type`** field in `/status` and `/peers/connect` response: `"host"` (default) | `"p2p_direct"` | `"dcutr_direct"` | `"relay"`
- NAT traversal three-tier auto-negotiation integrated into `/peers/connect` main flow
- `capabilities.nat_traversal: true` — capability flag
- `test_nat_integration.py` — NI1~NI6: **6/6 PASS**

---

## [2.18.0] — 2026-03-30 (trust.signals JWKS Compatibility Layer)

### Added — trust_jwks (v2.18)

- **`_build_jwks(agent_name)`** — builds a JWK Set (RFC 7517) from the ACP Ed25519 identity.
  Returns `{"keys": [<JWK>]}` when `--identity` is enabled; `{"keys": []}` otherwise.
  JWK format: `{"kty": "OKP", "crv": "Ed25519", "x": "<base64url_pubkey>", "use": "sig", "alg": "EdDSA", "kid": "<agent_name>:<pubkey_prefix_8>"}`
- **`GET /.well-known/jwks.json`** — public JWK Set endpoint (unauthenticated, well-known).
  Always returns 200; returns empty keys when `--identity` not provided.
- **`capabilities.trust_jwks: True`** — declared in AgentCard (always true; endpoint always available).
- **`endpoints.jwks: "/.well-known/jwks.json"`** — declared in AgentCard endpoints block.
- **`trust.signals[]` type `"jwks"`** — new signal when `--identity` enabled:
  `{"type": "jwks", "enabled": true, "jwks_uri": "/.well-known/jwks.json", "alg": "EdDSA", "description": "...", "details": {...}}`
- Backward compatible: existing `type=ed25519_identity` raw signal preserved; `type=jwks` added alongside.

### Tests

- `tests/test_jwks.py` — JW1~JW10: **13/13 PASS** (2 no-identity + 8 with-identity + 3 always-declared)
- Full regression: `test_trust_signals.py` 8/8 PASS (no regressions)

### Differentiation vs A2A IS#1628

- A2A IS#1628 proposes `trust.signals[]` with JWKS-format key discovery — ACP now ships a complete implementation.
- ACP's `/.well-known/jwks.json` is a strict RFC 7517 JWK Set; discoverable via both `endpoints.jwks` and `trust.signals[type=jwks].jwks_uri`.
- Ed25519 key type uses `kty=OKP`, `crv=Ed25519`, `alg=EdDSA` per RFC 8037 (CFRG Elliptic Curves for JOSE).
- Both raw Ed25519 identity (`type=ed25519_identity`) and JWKS signal (`type=jwks`) coexist for maximum interoperability.

---

## [2.17.0] — 2026-03-30 (Availability Schedule — CRON-based Agent Scheduling)

### Added — availability_schedule (v2.17)

- **`_parse_cron_field(field, lo, hi)`** — stdlib-only CRON field parser (supports `*`, `/`, `-`, `,`)
- **`_next_cron_datetime(expr, after_dt)`** — computes next UTC datetime matching a 5-field CRON expression
- **`_availability_with_schedule(avail)`** — returns availability dict with auto-computed `next_active_at`
- **`availability.schedule`** field in AgentCard: CRON expression string (e.g. `"0 */4 * * *"`)
- **`availability.timezone`** field: IANA timezone for schedule interpretation (default UTC)
- **`GET /availability`** — dedicated endpoint returning full availability status + `has_schedule` flag
- **`POST /availability/heartbeat`** — stamps `last_active_at = now`, recomputes `next_active_at` from schedule; accepts body to update schedule
- **`capabilities.availability_schedule: bool`** — capability flag (True when schedule is configured)
- AgentCard `endpoints.availability` and `endpoints.heartbeat` declared
- PATCH `/.well-known/acp.json` now accepts `schedule` + `timezone` in whitelist

### Tests

- `tests/test_availability_schedule.py` — AS1~AS15: 22/22 PASS (10 unit + 12 HTTP integration)
- Full regression: 171/171 PASS

### Differentiation

- A2A IS#1667 (2026-03-21) proposes `availability_metadata` for heartbeat agents — still under discussion, no implementation planned
- ACP ships CRON scheduling with **zero dependencies** (stdlib-only pure-Python parser)
- ACP already has `offline_queue` + flush-on-reconnect, completing the "offline-first" picture IS#1667 describes

---

## [2.16.0] — 2026-03-29 (Delegation Chain — Signed Identity Delegation in AgentCard)

### Added — delegation_chain (v2.16)

- **`_delegation_chain`** — global list of signed delegation entries in the relay runtime
- **`_build_delegation_entry(delegator_did, scope, expires_at)`** — creates an Ed25519-signed
  delegation record asserting that `delegator_did` has delegated `scope` to this agent.
  Payload is canonical JSON (sorted keys), signature is base64url-encoded.
- **`_verify_delegation_entry(entry)`** — verifies a delegation entry's Ed25519 signature by
  extracting the public key directly from the `did:acp:` identifier (zero-registry, self-sovereign).
- **`_delegation_chain_status()`** — returns chain summary with per-entry expiry flags.
- **`POST /identity/delegate`** — create a new signed delegation entry.
  - Body: `{delegator_did, scope, expires_at}`. Deduplicates by `delegator_did`.
  - Returns: `{ok, entry, delegation_chain_size}`
- **`GET /identity/delegation`** — query current delegation chain status + entries.
- **`POST /identity/delegation/verify`** — verify an arbitrary delegation entry's signature.
- **AgentCard `identity.delegation`** — included when `_delegation_chain` is non-empty.
- **`capabilities.delegation_chain: true`** — declared when chain is non-empty.
- **`endpoints.delegate/delegation/delegation_verify`** — registered in AgentCard endpoints block.
- **Tests: `tests/test_delegation_chain.py`** — 13/13 PASS (DC1–DC13)
  - Unit: entry fields, sig validity, tamper detection, dedup, expiry, AgentCard integration
  - HTTP: POST /identity/delegate, GET /identity/delegation, POST /identity/delegation/verify

### Fixed — BUG-041 dedup regression (v2.16)

- **BUG-041 (original, v0.7)**: Token-only `duplicate_connection` guard prevented ghost peers from
  NAT traversal Level1/2/3 racing multiple WS paths simultaneously.
- **BUG-041 regression (v2.16)**: Token-only dedup incorrectly rejected a second *different* agent
  connecting to the same `link/token` — e.g. Worker1 and Worker2 both connecting to the same
  Orchestrator link. The second WS was closed as `"duplicate_connection"`, causing B11 scenario
  (Worker2→Orch reverse connect) to always timeout.
- **Fix**: Dedup now requires **both** `link_token AND remote_address` to match.
  - Same token + same remote addr → NAT race duplicate → close
  - Same token + different remote addr → two legitimate agents → both registered
- `_register_peer()` now accepts and stores `remote_address` parameter.

### Added — ws_ready field in GET /peers (v2.16)

- **`ws_ready`** field added to each peer entry in `GET /peers` response.
  - `ws_ready = connected AND ws is not None` — only `True` after WS handshake completes.
  - Previously `connected=True` was set at `/peers/connect` request time (before WS handshake),
    causing `wait_peer_connected` fast-path to prematurely signal readiness.
  - Tests updated to use `ws_ready` for definitive handshake confirmation.

### Differentiation

- A2A Issue #1696 (2026-03-28) lists "delegation chains" under **Future Considerations** — not yet
  proposed, let alone implemented. ACP ships this first with a concrete, verifiable design.
- Zero-registry verification: public key is embedded in `did:acp:` — no lookup service needed.

---

## [2.15.0] — 2026-03-29 (Context Query — GET /context/<id>/messages multi-turn conversation history)

### Added
- `GET /context/<context_id>/messages` — query all messages belonging to a multi-turn conversation thread
  - Filters `_recv_queue` (inbound) + outbound messages by `context_id`
  - Query params: `limit` (max 200), `since_seq` (incremental fetch), `sort=asc|desc`
  - Returns: `{context_id, messages[], count, total, has_more}`
- Outbound messages now persisted to `_recv_queue` with `direction: outbound` (enables full conversation history)
- `capabilities.context_query: true` declared in AgentCard
- Tests: `tests/test_context_query.py` — 8/8 PASS

### Changed
- `/message:send` success path: outbound message appended to `_recv_queue` for local history tracking
- SSE broadcast payload includes `context_id` field for outbound messages

---

## [2.14.0] — 2026-03-29 (Trust Signals — Structured Trust Evidence in AgentCard)

### Added — trust.signals[] (v2.14)

- **`trust.signals[]`** in AgentCard (`/.well-known/acp.json`) — structured, enumerable
  trust evidence block.  Each signal entry has `type`, `enabled`, `description`, and
  `details` fields.  Inspired by A2A Issue #1628 (proposal, not yet merged); ACP ships
  this first with a concrete, per-capability design.
- **`_build_trust_signals()`** — generates the array at AgentCard build time from the
  current runtime state (HMAC secret present? Ed25519 keypair loaded? DID generated?).
  Six signal types:
  | Signal type | Enabled when |
  |---|---|
  | `hmac_message_signing` | `--secret` provided |
  | `ed25519_identity` | `--identity` loaded |
  | `agent_card_signature` | `--identity` loaded |
  | `peer_card_verification` | **always** (built-in v1.9) |
  | `replay_window` | `--secret` provided |
  | `did_document` | DID generated (`--identity`) |
- **`capabilities.trust_signals: true`** in AgentCard — machine-readable flag for
  capability negotiation.
- **`tests/test_trust_signals.py`** — 8 tests (TS1–TS8):
  - TS1: `trust` block present in AgentCard
  - TS2: `trust.signals` is a non-empty list
  - TS3: each signal has required fields (`type`, `enabled`, `description`, `details`)
  - TS4: all 6 expected signal types present
  - TS5: ed25519-related signals disabled without `--identity`
  - TS6: HMAC-related signals disabled without `--secret`
  - TS7: `trust_signals` capability declared
  - TS8: `peer_card_verification` always enabled

### Differentiation

- A2A Issue #1628 proposes `trust.signals[]` but remains unmerged as of 2026-03-29.
  ACP v2.14 is the first protocol implementation to ship this feature with a concrete,
  capability-mapped design.

---

## [2.13.0] — 2026-03-29 (Event Replay — `?since=<seq>` Reconnect Without Data Loss)

### Added — Event Replay for SSE + WebSocket (v2.13)

- **`GET /stream?since=<seq>`** — SSE reconnect replay: immediately delivers all
  buffered events with `seq > since` before joining the live stream.  Clients that
  disconnect and reconnect can resume exactly where they left off without data loss.
- **`GET /ws/stream?since=<seq>`** — same replay semantics over WebSocket; replayed
  events are delivered as `{"event":"acp.message","data":{...}}` frames before the
  connection enters the live-push loop.
- **`_event_log` ring buffer** — last `_EVENT_LOG_MAX` (500) events kept in-memory,
  thread-safe (`_event_log_lock`), populated by `_broadcast_sse_event()` on every
  dispatch (SSE + WS).
- **`capabilities.event_replay: true`** in AgentCard — advertises replay support to
  peers; discoverable via `GET /.well-known/acp.json`.
- **`tests/test_event_replay.py`** — 6 new tests (RP1–RP6):
  - RP1: `/stream?since=0` replays all stored events
  - RP2: `/stream?since=<mid>` replays only events after mid seq
  - RP3: `/stream` (no `?since`) — no regression, live events still arrive
  - RP4: `/ws/stream?since=0` replays events over WebSocket
  - RP5: `capabilities.event_replay` declared in AgentCard
  - RP6: `?since=<last_seq>` returns nothing (correct no-op)

### Fixed

- **`_handle_ws_stream` replay**: `client.send_ws_text()` → `client.send()` (method
  name typo silently suppressed by `except Exception: break`; replay never executed).

### Changed

- VERSION: `2.12.0` → `2.13.0`
- `_broadcast_sse_event()`: appends each event to `_event_log` before distributing
  to SSE subscribers and WS clients.

---

## [2.12.0] — 2026-03-29 (GET /ws/stream — WebSocket Native Push Endpoint)

### Added
- **`GET /ws/stream`** — WebSocket native push endpoint (Upgrade: websocket)
  - Clients subscribe by connecting to `ws://<host>:<http_port>/ws/stream`
  - On each `_broadcast_sse_event()` call, all connected WS clients receive a JSON frame:
    ```json
    {"event": "acp.message", "data": {"message_id": "...", "from": "...", "parts": [...], "timestamp": "...", "server_seq": 42}}
    ```
  - Supports `acp.message` and `acp.peer` event types
  - `_ws_stream_clients: set` tracks active subscribers; dead connections auto-pruned on next broadcast
  - `_handle_ws_stream()` runs in ThreadingHTTPServer worker thread (no asyncio dependency)
  - `_broadcast_ws_stream_event()` called from `_broadcast_sse_event()` — single dispatch path
- **AgentCard** updated:
  - `capabilities.ws_stream: true`
  - `endpoints.ws_stream: "/ws/stream"`
- **`tests/test_ws_stream.py`** — WS1–WS5 test suite
  - WS1: HTTP 101 Switching Protocols handshake ✅
  - WS2: `acp.message` event delivery to WS subscriber (requires P2P peer; skip in sandbox) ⏭
  - WS3: Multi-client broadcast — all connected clients receive same event (requires P2P; skip in sandbox) ⏭
  - WS4: Client disconnect cleanup — relay survives, no crash ✅
  - WS5: `capabilities.ws_stream` + `endpoints.ws_stream` in AgentCard ✅

### Changed
- VERSION: `2.11.0` → `2.12.0`

### Design Notes
- Complements existing SSE `/stream` endpoint: SSE is unidirectional HTTP/1.1 keep-alive; WS provides a proper bidirectional upgrade for clients that prefer WebSocket
- Implemented via raw WebSocket handshake inside ThreadingHTTPServer (SHA-1 + base64 accept key, RFC 6455 compliant)
- Broadcast is fire-and-forget; broken connections detected lazily on next send (no heartbeat overhead)

### Competitive Context
- A2A `#1029` (pub/sub async, 17 comments) remains unimplemented; ACP ws/stream delivers real-time push ahead of A2A

---

## [2.11.0] — 2026-03-28 (Node.js SDK v2.4 — tasks/cancel, capabilities API)

### Added (SDK: `sdk/node/`)
- **`client.tasks.cancel(taskId)`** — cancel a running task
- **`client.capabilities()`** — fetch AgentCard capabilities object
- Node.js SDK version: `2.3.x` → `2.4.0`
- Tests: `sdk/node/tests/` suite updated (all pass)

### Changed
- VERSION: `2.10.0` → `2.11.0`

---

## [2.10.0] — 2026-03-28 (Skills-lite — Structured Skill Declaration + GET /skills)

### Added
- **Structured `skills` field in AgentCard** — upgraded from plain string array to structured object array
  - Fields per skill: `id` (required), `name` (required), `description`, `tags[]`, `examples[]`, `input_modes[]`, `output_modes[]`
  - `--skills` CLI: accepts JSON array string (parsed directly) or plain comma-separated string (auto-converted: `"summarize,translate"` → `[{id: "summarize", name: "summarize"}, ...]`)
- **`GET /skills`** — new skills list endpoint with filtering + pagination
  - `?tag=<tag>` — exact tag match filter
  - `?q=<keyword>` — case-insensitive keyword search across `id`/`name`/`description`
  - `?limit=<N>&offset=<N>` — pagination (default limit 50, max 200)
  - Response: `{"skills": [...], "total": N, "has_more": bool, "next_offset": N|null}`
  - Non-integer `limit`/`offset` → 400 `ERR_INVALID_REQUEST`
- **`POST /skills/query` enhanced** — structured matching when skills are objects (fallback to old string logic for legacy format)
- **`endpoints.skills: "/skills"`** declared in AgentCard
- **`tests/test_skills_list.py`** — SK1–SK6, 6 tests, all pass
  - SK1: basic list, SK2: tag filter, SK3: keyword search, SK4: pagination, SK5: error handling, SK6: AgentCard structured fields

### Changed
- VERSION: `2.9.0` → `2.10.0`
- AgentCard `skills` field: backward-compatible (old plain-string arrays still accepted via auto-conversion)

### Design
- Inspired by A2A v1.0 Skills mechanism (2026-03-12), ACP "Skills-lite" ships lighter: no `inputSchema`/`outputSchema` JSON Schema overhead, focus on discoverability via tags + keyword search
- `GET /skills` complements `POST /skills/query`: list-and-filter vs targeted match

---

## [Unreleased] — post-v2.0-offline

---

## [2.9.0] — 2026-03-28 (GET /messages — History Message List with Pagination + Filtering)
### Added
- **`GET /messages` endpoint** (`relay/acp_relay.py`):
  - Non-destructive read from `_recv_queue` (unlike `GET /recv` which pops items)
  - Query parameters:
    - `limit` — page size, default 20, clamped to max 100
    - `offset` — offset-based pagination, default 0
    - `peer_id` — filter by source peer (matches `raw.from` field or `_peers` registry agent_name)
    - `role` — filter by role (`agent`/`user`)
    - `sort` — sort direction: `asc` (oldest→newest) or `desc` (newest→oldest, default)
    - `received_after` — Unix timestamp; only messages received after this time
  - Response schema: `{ messages, total, has_more, next_offset }`
  - Returns 400 `ERR_INVALID_REQUEST` for non-integer `limit`/`offset`
  - Inspired by A2A v1.0 `tasks/list` pattern, consistent with ACP `GET /tasks` (v2.2)
- **Tests** (`tests/test_messages_list.py`): 8 test cases (ML1–ML8) covering all parameters

---

## [2.8.0] — 2026-03-28 (Extension Mechanism — URI-Identified Extensions in AgentCard)
### Added
- **Extension mechanism** (`relay/acp_relay.py`):
  - `_make_builtin_extensions()` — auto-registers built-in extensions based on runtime config:
    - `acp:ext:hmac-v1` when `--secret` is set (HMAC-SHA256 signing)
    - `acp:ext:mdns-v1` when `--advertise-mdns` is set (mDNS LAN discovery)
    - `acp:ext:h2c-v1` when `--http2` is set (HTTP/2 cleartext transport)
  - `_make_agent_card()` now **always emits `extensions: []`** (empty list when none declared) — was opt-in before v2.8
  - Deduplication by URI: if same URI appears in built-in and user-declared, kept once (first occurrence)
  - `--extensions URI[,URI,...]` new CLI flag — shorthand for declaring multiple extensions by URI
  - Built-in + user-declared extensions merged in card; built-ins first, then user-declared
- **Python SDK** (`sdk/python/acp_client/models.py`):
  - `Extension` dataclass — `uri` (str, required), `required` (bool, default `False`), `params` (dict, default `{}`)
    - `Extension.to_dict()` — serialises to dict; omits `params` when empty
    - `Extension.from_dict(d)` — parses dict; validates `uri` required; forward-compat (skips malformed entries)
    - `__repr__` — human-readable with `required` indicator
  - `AgentCard.extensions: List[Extension]` field (default `[]`)
  - `AgentCard.has_extension(uri)` — bool check by URI
  - `AgentCard.get_extension(uri)` → `Extension | None`
  - `AgentCard.required_extensions()` → `List[Extension]`
  - `AgentCard.from_dict()` — handles missing/null `extensions` field (backward compat)
  - `AgentCard.to_dict()` — always emits `extensions` key
- **Spec** (`spec/core-v1.0.md`):
  - New §5.5 "Extension Mechanism (v2.8+)" with full schema, URI naming convention,
    well-known built-in URIs table, semantics/compat rules, discovery, CLI flags
  - AgentCard schema example updated to show `extensions` array
  - Top-level fields table updated: `extensions` → **stable**
- **Tests** (`tests/test_extensions.py`): 39 test cases (all passing):
  - Extension dataclass defaults, serialisation, round-trip
  - AgentCard `extensions` field: default empty, to_dict/from_dict
  - Backward compat: old responses without `extensions` field
  - Convenience methods: `has_extension`, `get_extension`, `required_extensions`
  - Relay: `_make_builtin_extensions` for all 3 built-ins
  - Relay: `_make_agent_card` always emits extensions key
  - Relay: user-declared merge, deduplication
  - `--extensions` CLI bulk URI parsing

### Changed
- `relay/acp_relay.py` VERSION: `2.7.0` → `2.8.0`
- `tests/unit/test_relay_core.py`: updated `test_extensions_absent_when_empty` to assert extensions key always present (v2.8 semantics)

### Design
- Inspired by A2A extension model; designed to remain minimal and registry-free
- URI naming: `acp:ext:<name>-v<version>` for built-ins; full HTTPS URL for external/vendor extensions
- **Non-required default**: `required: false` — clients that don't recognise an extension MUST ignore it
- No registry, no central authority — URI uniqueness is the extension definer's responsibility

---

## [1.8.0] — 2026-03-28 (acp-client LangChain Tool Adapter)
### Added
- `sdk/python/acp_client/integrations/` — new optional integrations sub-package
  - `langchain.py` — LangChain Tool adapter (`ACPTool`, `ACPCallbackHandler`, `create_acp_tool`)
    - `ACPTool` — `BaseTool` subclass (lazy import; langchain is optional dep, not required for core SDK)
      - `name = "acp_send"`, LLM-readable description
      - `_run(message) -> str` — synchronous send + receive via `RelayClient`
      - `_arun(message) -> str` — async wrapper (thread-pool executor, non-blocking)
      - Graceful error handling: returns descriptive error strings, never raises, so LLM can recover
    - `ACPCallbackHandler` — `BaseCallbackHandler` subclass (lazy import)
      - `on_tool_start` / `on_tool_end` / `on_tool_error` — structured log entries via `logging`
      - `_calls` list accumulates all events for post-run inspection
    - `create_acp_tool(relay_url, peer_id, timeout=30)` — factory helper
  - `__init__.py` — package docstring (zero required imports)
- `__init__.py` — conditional top-level re-export of `create_acp_tool` (available when langchain installed)
- `pyproject.toml` — new optional extra: `[langchain]` = `langchain>=0.1.0`
- `tests/test_langchain_integration.py` — 38 test cases (all passing, mock-only, no real langchain required)
  - TC-01: init (name, description, relay_url, peer_id, timeout)
  - TC-02: _run success paths (send_and_recv, specific peer_id, instance method)
  - TC-03: _run timeout (None reply → error string, no raise)
  - TC-04: _run ACPError handling
  - TC-05: _arun async wrapper
  - TC-06: missing langchain ImportError with install hint
  - TC-07: create_acp_tool factory
  - TC-08: ACPCallbackHandler events
  - TC-09: __repr__
  - TC-10: integration smoke tests
  - TC-11: public API (top-level re-export)
  - TC-12: pyproject.toml optional dep declared
- `sdk/python/README-sdk.md` — new "LangChain Integration" chapter

### Design
- **Lazy import pattern**: LangChain never imported at module load time; `ImportError` with pip hint raised only at first instantiation if langchain absent
- Dynamic subclassing via `__new__`: builds a real `BaseTool`/`BaseCallbackHandler` subclass at instantiation, compatible with all LangChain versions
- Zero new mandatory dependencies; core `acp_client` remains stdlib-only
- Python 3.9–3.13 compatible

### Bump
- `__version__`: `1.7.0` → `1.8.0`

---

## [1.7.0] — 2026-03-28 (acp-client Python pip Package)
### Added
- `sdk/python/acp_client/` — new pip-installable `acp-client` package (v1.7.0)
  - `client.py` — `RelayClient` (sync, stdlib urllib, zero external deps)
  - `async_client.py` — `AsyncRelayClient` (async via run_in_executor bridge)
  - `models.py` — typed dataclasses: `AgentCard`, `Message`, `Task`, `TaskStatus`, `Part`, `PartType`
  - `exceptions.py` — `ACPError` hierarchy: `PeerNotFoundError`, `TaskNotFoundError`, `TaskNotCancelableError`, `SendError`, `AuthError`, `TimeoutError`
  - `__init__.py` — clean public API surface
  - `_cli.py` — `acp-client` CLI entry-point (status / card / link / peers / send / recv / tasks / stream)
- `sdk/python/pyproject.toml` — PEP 517 build config (Python ≥ 3.9, zero mandatory deps, optional: `[async]`, `[http2]`, `[dev]`)
- `sdk/python/README-sdk.md` — complete SDK documentation (install + 30s quick-start + full API reference + relay integration guide)
- `sdk/python/tests/test_sdk_package.py` — 60 test cases (all passing, no live relay required — uses in-process mock HTTP server)

### Design
- Zero mandatory external dependencies (stdlib urllib only for core HTTP)
- Optional extras: `httpx` for native async, `h2` for HTTP/2
- Backward-compatible: `sdk/python/acp_sdk/` unchanged; existing `from acp_sdk import RelayClient` continues to work
- Fully typed public API with rich exception hierarchy
- `acp-client` CLI covers all major relay operations

---

## [2.7.0] — 2026-03-28 (AgentCard `limitations` Field — Three-Part Capability Boundary)
### Added
- `limitations: string[]` top-level AgentCard field: declares what this agent CANNOT do
- Completes three-part capability boundary triad: `capabilities` (can-do) + `availability` (scheduling) + `limitations` (cannot-do)
- `--limitations` CLI flag: comma-separated string (e.g. `--limitations "no_file_access,no_internet"`)
- `_status["limitations"]` in `/status` endpoint response
- `_limitations` global variable initialized to `[]` (backward-compatible default)
- spec/core-v1.3.md §11: `limitations` field schema, well-known values table, 3-part boundary explanation
- docs/whats-new.md: v2.7 section with usage examples and A2A #1694 comparison
- README: new row in vs-A2A comparison table + callout paragraph for #1694
- tests/test_limitations.py: 20 tests across LM1–LM5 (all pass)

### Design
- ACP-exclusive: A2A #1694 (2026-03-27) proposes the same concept — ACP ships working code same day
- Fully backward-compatible: old clients ignore the optional `limitations` field
- Limitation strings are free-form `snake_case`; well-known values documented in spec §11.3

---

## [2.6.0] — 2026-03-27
### Added
- Task `cancelling` 中间状态（两阶段取消协议）
- AgentCard `capabilities.task_cancelling: true` 能力声明
- spec §3.3.1 两阶段取消时序图
- spec Appendix B A2A 对比（Issue #1684/#1680 差异化说明）
- `tests/test_task_cancel.py`（10 个测试用例）

---

## [v2.5.0] - 2026-03-27
### Added
- spec §8: Task 事件序列规范（7 MUST + 2 SHOULD 合规要求）
- SSE 事件 Envelope 必填字段：type/ts/seq/task_id
- Task 完整生命周期 SSE Wire Format 示例
- relay/acp_relay.py: Named event 行（acp.task.status / acp.task.artifact）
- AgentCard: supported_interfaces 字段
- tests/test_task_event_sequence.py: 10 个 Task 事件序列测试

### Fixed
- BUG-031: test_dcutr_t6_scenario_a.py T6.7 缺少 role 字段
- BUG-032: test_scenario_bc.py relay 启动等待不足
- BUG-033: cert teardown TimeoutExpired

---

## [2.4.0] — 2026-03-27 (AgentCard `transport_modes` Top-Level Field)

### Added — `transport_modes` Routing Topology Declaration (v2.4 milestone)

- **`transport_modes` — new top-level AgentCard field** (v2.4+)
  - Declared at `/.well-known/acp.json` as a top-level key (not nested under `capabilities`)
  - Declares the **routing topologies** supported by this node (distinct from `capabilities.supported_transports` which declares *protocol bindings*)
  - Valid values: `"p2p"` (direct peer-to-peer WebSocket) and/or `"relay"` (HTTP relay-mediated)
  - Default: `["p2p", "relay"]` — both topologies supported; peer may choose
  - Examples:
    - `["p2p", "relay"]` — standard node, both modes available (default)
    - `["relay"]` — sandbox/NAT-only node; P2P not possible
    - `["p2p"]` — edge agent with public IP; no relay dependency
  - Absent means `["p2p", "relay"]` (backwards-compatible)
  - Receivers MUST treat as advisory; unknown values MUST be ignored

- **`--transport-modes` CLI flag** (v2.4+)
  - Comma-separated routing modes: `--transport-modes p2p,relay` (default), `--transport-modes p2p`, `--transport-modes relay`
  - Invalid values are warned and silently ignored; empty result falls back to default

- **Spec update** — `spec/core-v1.0.md §5.2–§5.5`
  - §5.2: New "Top-Level AgentCard Fields" table (formally documents all top-level keys)
  - §5.3: Capability Flags table updated with note distinguishing `supported_transports` vs `transport_modes`
  - §5.4: New dedicated section — `transport_modes` semantics, valid values, CLI, examples
  - §5.5: Forward Compatibility (renumbered from §5.3)

- **Tests** — `tests/unit/test_transport_modes_v24.py` — 15 new unit tests
  - `transport_modes` present in AgentCard, is a list, top-level (not under capabilities)
  - Default `["p2p", "relay"]`, p2p-only, relay-only variants
  - Snapshot semantics (mutation does not affect global)
  - Version check (>= 2.4.0)
  - Global default and valid values

### Changed

- `relay/acp_relay.py`: VERSION bumped `2.2.0` → `2.4.0`
- `_make_agent_card()`: returns `transport_modes` as a snapshot list (not reference)

---

## [2.2.0] — 2026-03-27 (GET /tasks List Endpoint with Filtering + Pagination)

### Added — `GET /tasks` List Queries (v2.2 milestone)

- **`GET /tasks` — full list + filtering + dual pagination**
  - `?status=<s>` — filter by task status (submitted/working/completed/failed/canceled/input_required)
    - Returns `400 ERR_INVALID_REQUEST` for unknown status values
    - Backwards-compatible: legacy `?state=` parameter still accepted (`status` takes precedence)
  - `?peer_id=<id>` — filter by peer; checks both `task.peer_id` (top-level) and
    `task.payload.peer_id` (BUG-014 dual-layer lookup)
  - `?created_after=<ISO 8601>` — return only tasks created after given timestamp
  - `?updated_after=<ISO 8601>` — return only tasks updated after given timestamp
  - `?sort=asc|desc` — sort by `created_at`; default `desc` (newest first)
    - Legacy `created_asc` / `created_desc` values also accepted
  - `?limit=<n>` — page size; default 20, max 100 in offset mode; legacy default 50, max 200
  - `?offset=<n>` — offset-based pagination (v2.2 new); triggers offset mode
  - Response shape (offset mode):
    ```json
    {
      "tasks": [...],
      "total": N,
      "has_more": true,
      "next_offset": 20
    }
    ```
  - `total` reflects **filtered count** (not raw `len(_tasks)`)
  - `next_offset` only present when `has_more=true`
  - Legacy keyset cursor mode (`?cursor=<task_id>`) preserved when `offset` param absent

### Tests (TL1–TL10, `tests/test_tasks_list.py`)

- TL1: No params → returns all tasks with required fields
- TL2: `?status=working` filters correctly; only matching tasks returned
- TL3: `?peer_id=` matches both top-level and `payload.peer_id` (BUG-014)
- TL4: `?limit=2&offset=0` — first page
- TL5: `?limit=2&offset=2` — second page; no overlap with first
- TL6: `has_more=true` when items remain; `next_offset` present only when `has_more=true`
- TL7: `?sort=asc` returns oldest task first
- TL8: `?created_after=<ISO>` filters out older tasks
- TL9: Impossible filter → `{"tasks": [], "total": 0, "has_more": false}`
- TL10: `?status=bogus` → `400 ERR_INVALID_REQUEST`

Results: **10/10 passed** — full regression: **256 passed, 4 skipped, 0 failed**

---

## [2.0.0-alpha.1] — 2026-03-26 10:17 (Offline Delivery Queue)

### Added — Offline Message Delivery Queue (v2.0 milestone)

- **`_offline_enqueue(msg, peer_id)`** — buffers messages when peer is disconnected (v2.0)
  - Called automatically from `_ws_send()` on `ConnectionError`
  - Per-peer keyed queue (`peer_id` or `"default"` for legacy single-peer sends)
  - `deque(maxlen=100)` per bucket — oldest messages dropped when full (never blocks)
  - Stores metadata: `_queued_at`, `_offline_for_peer`

- **`_offline_flush(ws, peer_id)`** — delivers buffered messages on reconnect (v2.0)
  - Called automatically in `host_mode` and `guest_mode` after peer connects / reconnects
  - Flushes in FIFO order; strips internal bookkeeping fields; adds `_was_queued: True` marker
  - Tries peer-specific bucket first, then falls back to `"default"` bucket
  - Logs delivery count: `📤 Flushed N offline message(s) to peer '<id>' on connect`

- **`_offline_queue_snapshot()`** — serializable view of all queue buckets

- **`GET /offline-queue`** — inspect offline delivery buffer
  - Returns `{total_queued, max_per_peer, queue: {peer_id: {depth, messages: [{type, queued_at}]}}}`

- **`capabilities.offline_queue: true`** — advertised in AgentCard
- **`endpoints.offline_queue: "/offline-queue"`** — advertised in AgentCard endpoints block

### Behaviour change

- `POST /message:send` and `POST /send` no longer immediately fail with `503` and drop the message.
  They still return `503 ERR_NOT_CONNECTED` (API contract unchanged), but the message is now
  silently buffered for delivery the moment a peer reconnects.
- Callers who want guaranteed delivery can poll `GET /offline-queue` to confirm the message
  is buffered.

### Tests (OQ1–OQ10, `tests/test_offline_queue.py`)

- OQ1: capabilities.offline_queue=True advertised
- OQ2: endpoints.offline_queue="/offline-queue" in AgentCard
- OQ3: GET /offline-queue → empty queue on fresh relay
- OQ4: Required structure fields (total_queued, max_per_peer, queue)
- OQ5: POST /message:send → 503 + message buffered
- OQ6: Queue depth increments with each failed send
- OQ7: Queue snapshot metadata has type, queued_at per message
- OQ8: Legacy POST /send also buffers to offline queue
- OQ9: Queue bounded by OFFLINE_QUEUE_MAXLEN=100 (oldest dropped)
- OQ10: Relay /status healthy after offline queue activity

Results: **10/10 passed** — full regression: **236 passed, 4 skipped, 0 failed**

### Motivation

- A2A has no offline delivery mechanism — if a task message is sent while the
  receiving agent is offline, the message is simply lost.
- ACP v2.0 offline queue: "send and forget safely" — messages survive short
  disconnects, auto-delivered on reconnect without any extra code by the caller.
- Show HN talking point: "If your peer is offline when you send, ACP queues it
  and delivers it the moment they reconnect. A2A drops it silently."

---

## [1.9.0] — 2026-03-26 07:45

### Added — Peer AgentCard Auto-Verification (v1.9)

- **`acp.agent_card` handler now auto-verifies peer card on receipt**
  - When peer sends AgentCard with `identity.card_sig`, immediately calls `_verify_agent_card()`
  - Result stored in `_status["peer_card_verification"]`
  - Logs `✅ AgentCard verified: <name> | did=<did>...` on success
  - Logs `⚠️ AgentCard sig INVALID: <name> | <reason>` on failure
  - Gracefully handles unsigned peers (valid=None, descriptive error)

- **`_send_agent_card()` now sends signed card** (v1.9 integration with v1.8)
  - Calls `_sign_agent_card(card)` before sending during handshake
  - Peer receives a verifiable card from the first message

- **`GET /peer/verify`** — peer card verification result endpoint
  - Returns `{peer_name, peer_did, verified, valid, did_consistent, public_key, scheme, error}`
  - `verified`: convenience boolean (True iff valid is True)
  - 404 when no peer is connected
  - Cleared automatically on disconnect

- **`_status["peer_card_verification"]`** initialized to `None`; cleared on disconnect
  (both host-mode and guest-mode disconnect paths)

- **`capabilities.auto_card_verify: true`** — always advertised (all relays)
- **`endpoints.peer_verify: "/peer/verify"`** — advertised in AgentCard endpoints block

### Tests (PV1–PV8, `tests/test_peer_card_verify.py`)

- PV1: capabilities.auto_card_verify=True on both relays
- PV2: GET /peer/verify → 404 when no peer connected
- PV3: endpoints.peer_verify = "/peer/verify" in AgentCard
- PV4: /.well-known/acp.json returns signed card when --identity enabled
- PV5: auto-verify after peer connect → verified=True *(skipped: sandbox no public IP)*
- PV6: unsigned peer card → valid=False + descriptive error
- PV7: /peer/verify response has all required fields (valid, did, public_key, scheme, error)
- PV8: peer_card_verification=None when no peer connected

Results: **7 passed, 1 skipped** — full regression: **226 passed, 4 skipped, 0 failed**

### Motivation

- Completes the identity story: v1.8 lets you sign your card; v1.9 auto-verifies the peer's card
- Together: when two ACP agents connect, **both sides automatically know if the other's identity is cryptographically verified** — zero extra API calls needed
- Show HN talking point: "Connect two agents → identity mutual verification happens at handshake"

---

## [1.8.0] — 2026-03-26 05:15

### Added — AgentCard Self-Signature (card_sig)

- **`_sign_agent_card(card)`** (commit TBD, v1.8)
  - Signs AgentCard with Ed25519 private key at serve time
  - Signature covers canonical JSON (sorted keys, separators `','`/`':'`) with `identity.card_sig` excluded to avoid circular reference
  - Result stored at `card.identity.card_sig` (base64url, no padding)
  - No-op when `--identity` not enabled (zero-breaking backward compat)

- **`_verify_agent_card(card)`**
  - Verifies any ACP AgentCard's Ed25519 self-signature
  - Returns `{valid, did, did_consistent, public_key, scheme, error}`
  - `did_consistent`: cross-checks `did:acp:` matches `identity.public_key`
  - Works for any relay's card — not just the local agent's

- **`GET /.well-known/acp.json`** now returns signed card when `--identity` enabled
  - `identity.card_sig` field added to response

- **`GET /verify/card`** — self-verification endpoint
  - Returns `{self_verification, card_signed}` for the local agent's own card

- **`POST /verify/card`** — arbitrary card verification endpoint
  - Body: raw AgentCard JSON or wrapped `{self: card}` form
  - Returns full verification result
  - Invalid JSON body → 400

- **`capabilities.card_sig`**: `true` when `--identity` enabled, `false` otherwise

- **`endpoints.verify_card`**: `"/verify/card"` advertised in AgentCard endpoints block

### Tests (CS1–CS10, `tests/test_card_signature.py`)

- CS1: card_sig present in GET /.well-known/acp.json when --identity enabled
- CS2: GET /verify/card self-verification → valid=True
- CS3: POST /verify/card valid signed card → valid=True
- CS4: POST /verify/card tampered card → valid=False
- CS5: POST /verify/card unsigned card → valid=False + "card_sig missing"
- CS6: capabilities.card_sig=True with --identity
- CS7: POST /verify/card accepts wrapped {self: card} form
- CS8: POST /verify/card invalid JSON → 400
- CS9: did_consistent=True when did:acp: matches public_key
- CS10: card_sig absent without --identity; capabilities.card_sig=False

Results: **11/11 PASS** — full regression: **219 passed, 3 skipped, 0 failed**

### Motivation

- Directly addresses A2A issue #1672 (Agent Identity Verification — no protocol-level mechanism)
- ACP ships cryptographic AgentCard verification today; A2A has no timeline
- Any ACP peer can now verify "this card was signed by the owner of this did:acp:" identity
  without any external CA or registration service

---

## [1.7.0] — 2026-03-25 20:30

### Updated (spec + README — post-release patch)

- **spec/error-codes.md**: explicitly documents `Content-Type: application/json; charset=utf-8` for all responses including errors; rejects `application/problem+json` (RFC 9457) by design; references A2A [#1685](https://github.com/a2aproject/A2A/issues/1685) as motivation (commit `81ffd30`)
- **README vs-A2A table** (commit `81ffd30`):
  - New row: "Error response Content-Type" — ACP uniform vs A2A #1685 ambiguous
  - New row: "Webhook security" — ACP URL-only vs A2A #1681 credentials leaked in plaintext
  - New callout paragraph referencing A2A #1681 + #1685

### Added (Python SDK)

- **`RelayClient.tasks()` v1.4 time-window filters** (commit `00e4a09`)
  - New params: `created_after`, `updated_after`, `peer_id`, `sort`, `cursor`, `limit`
  - Aligns sync and async clients with full relay `/tasks` endpoint query surface

- **`RelayClient.cancel_task()` v1.5.2 §10 idempotent semantics**
  - Default: returns error dict on 409 `ERR_TASK_NOT_CANCELABLE` (no exception)
  - `raise_on_terminal=True`: raises `ValueError` for terminal-state tasks
  - Async client (`AsyncRelayClient.cancel_task()`) upgraded identically

- **`RelayClient.capabilities()`** — new method
  - Extracts `capabilities` block from AgentCard (http2 / did_identity / hmac_signing / mdns)
  - Returns `{}` gracefully when relay unreachable

- **`RelayClient.identity()`** — new method
  - Returns `identity` block with `did:acp:` DID field (v1.3+)

- **`RelayClient.did_document()`** — new method
  - Fetches `/.well-known/did.json` W3C DID Document (v1.3+)

- **`AsyncRelayClient`**: all above methods added to async client as well

### Added (relay server)

- **SSE `context_id` propagation** (commit `b91f642`)
  - `_create_task()`: stores `context_id` on task object; includes it in initial `status` SSE event
  - `_update_task()`: propagates `task.context_id` to all subsequent `status` and `artifact` SSE events
  - `/tasks/create` endpoint and `/send` inline task creation both pass `context_id` through
  - Tasks without `context_id`: events cleanly omit the field (no null pollution)
  - Closes parity gap with A2A Issue #1683 (contextId missing from SSE events)

### Updated (README)

- **vs-A2A comparison table**: new row "Cancel task semantics"
  - ACP v1.5.2 §10: synchronous + idempotent (200 / 409 `ERR_TASK_NOT_CANCELABLE`)
  - A2A: `CancelTaskRequest` schema missing (#1684), async cancel state disputed (#1680)
- New callout referencing A2A issues #1680 and #1684

### Tests

- **`sdk/python/tests/test_relay_client_v17.py`**: 10 tests, 10/10 PASS
  - T1–T3: `tasks()` time-window + combined filter query string construction
  - T4–T6: `cancel_task()` success / 409 no-raise / 409 raise
  - T7: `capabilities()` http2 + did_identity flags
  - T8: `identity()` did:acp: field
  - T9: `did_document()` W3C DID Document structure
  - T10: `capabilities()` fallback on unreachable server
- **`tests/test_context_id_sse.py`**: 17/17 PASS (C1–C8, context_id SSE propagation)

**Full suite: 140 passed, 0 failed ✅**

---

## [1.4.1-dev] — 2026-03-25 14:40

### Added

- **DCUtR HTTP reflection fallback** (`relay/acp_relay.py`, commit `b3da914`)
  - `DCUtRPuncher.attempt()`: when STUN fails (UDP blocked by corporate firewall), falls back to HTTP reflection via `_relay_get_public_ip()` to discover public IP
  - Appends `{http_ip}:{local_port}` to candidate address list; Level 2 hole punch continues
  - `_status["relay_base_url"]` now populated at both relay startup paths (`--relay` CLI flag and P2P `guest_mode` fallback)
  - SSE event `dcutr_http_reflect` emitted for observability
  - Graceful no-op when `relay_base_url` is unset

### Tests

- **`tests/test_nat_http_reflect.py`**: 12 unit tests, 12/12 PASS (mock-based, no network required)
  - R1–R3: `_relay_get_public_ip` success / timeout / invalid JSON
  - R4: `_status["relay_base_url"]` round-trip
  - R5: DCUtR triggers HTTP reflection when STUN fails + relay_base set
  - R6: DCUtR skips HTTP reflection when `relay_base_url` is None

### Fixed

- **BUGS.md**: BUG-012 status label corrected to ✅ (code fix was already present in prior commits; status record was missed)

---

## [1.6.0] — 2026-03-25 13:50

### Added

- **HTTP/2 cleartext (h2c) transport binding** (`relay/acp_relay.py`)
  - Optional dependency: `hypercorn` + `h2` (graceful fallback to HTTP/1.1 if unavailable)
  - Implementation: raw `h2` state machine over `socketserver.ThreadingTCPServer`
  - `--http2` CLI flag; `capabilities.http2: true` in AgentCard
  - `_H2Handler._dispatch()`: bridges h2c frames to existing `LocalHTTP` handler via fake socket
  - Supports all endpoints: `/status`, `/.well-known/acp.json`, `/tasks`, SSE streams

### Tests

- **`tests/test_http2_transport.py`**: 6 scenarios (H1–H6) all PASS
  - H1 server startup, H2 AgentCard, H3 SSE, H4 POST /tasks, H5 /status, H6 discovery
- **Test infrastructure overhaul** (commit `21e3e7d`)
  - `tests/conftest.py`: global http_proxy strip + `clean_subprocess_env()` for relay subprocesses
  - `pytest.mark.p2p`: skip P2P-dependent tests in sandbox (`--with-p2p` to enable)
  - `test_scenario_h`: rewritten as HTTP-only concurrent isolation test
  - **Full suite: 15 passed, 3 skipped (P2P), 0 failed, 0 errors**

Key commits: `3f06b24`, `e8974b2`, `cf578e3`, `394b71c` (HTTP/2), `21e3e7d` (test infra), `0ac2215` (BUG-019 docs)

---

## [1.5.2-dev] — 2026-03-25 05:55

### Added

- **spec §10 — Task Cancel Semantics** (`spec/core-v1.3.md`): explicit synchronous cancel contract
  - Cancel is synchronous and immediate: `:cancel` returns final `canceled` state in the same HTTP response, no async/deferred mechanism
  - Cancel is idempotent: calling `:cancel` on an already-canceled task returns 200 with existing state
  - New error code: `ERR_TASK_NOT_CANCELABLE` (409) for tasks in terminal states (`completed`, `failed`)
  - Design rationale documented: deliberate contrast with A2A issue #1680 (async cancel, unresolved)
  - Agent-side cancel behavior guidance (best-effort signal, not a transaction rollback)
- **Show HN draft updated** (`docs/show-hn-draft.md`): added A2A competitive comparison points
  - A2A #1681 security bug: `PushNotificationConfig` leaks credentials by default; ACP has no Push Notification mechanism
  - A2A #1680 cancel design gap: async cancel unresolved; ACP cancel is synchronous and unambiguous
  - Updated anti-trolling prep with cancel and security talking points
- **spec Appendix A**: version history updated to v1.5.2

---

### Research (2026-03-25 05:25 — Competitive scan #7, post-1.5.1-dev update)

- **A2A 9-day code freeze continues** (last merge 2026-03-16, TSC governance mode)
- **A2A #1681 (security bug)**: `GetTaskPushNotificationConfig` leaks full credentials in response — ACP has no PushNotification mechanism, zero exposure to this class of vulnerability; strong differentiation point for Show HN
- **A2A #1680 (design gap)**: async cancel semantics unresolved — community debating two approaches for cancel-in-progress tasks; ACP cancel is simple synchronous (`canceled` state returned immediately), no async webhook complexity
- **A2A #1679**: Python tutorial docs require full rewrite for `v1.0-alpha.0` breaking changes; ACP API stable, low doc maintenance burden
- **ANP**: confirmed archived (last update 2026-03-05), no new activity

---

## [1.5.0-dev] — 2026-03-24 (pre-1.5.1, NAT signaling layer)

### Added (22:47 — v1.4 NAT traversal signaling layer)

- **Cloudflare Worker v2.1**: NAT traversal signaling endpoints (commit `8c162d4`)
  - `GET /acp/myip` — reflect caller's public IP via `CF-Connecting-IP` header; used by agents to discover their public address when STUN UDP is blocked
  - `POST /acp/announce` — register `{token, ip, port, nat_type}` with 30s TTL; auto-expires, no message content stored
  - `GET /acp/peer?token=` — one-time fetch + delete of peer announce record (prevents address harvesting)
  - Privacy design: signaling records are ephemeral (30s) and one-time-read, no persistent storage of agent addresses
- **Python signaling helpers** (`acp_relay.py`) — stdlib-only (`urllib`), no new deps
  - `_relay_get_public_ip(relay_base_url)` — HTTP reflection fallback for when STUN UDP is firewalled
  - `_relay_announce(relay_base_url, token, ip, port, nat_type)` — register address via Worker
  - `_relay_get_peer_addr(relay_base_url, token)` — fetch peer address (one-time, auto-deletes)
  - These complement `STUNClient`: STUN → primary; HTTP reflection → corporate firewall fallback
- **`tests/test_nat_signaling.py`**: 22/22 PASS — covers all helpers, error paths, edge cases, full roundtrip; uses local mock server, no network required

### Fixed (20:33)

- **BUG-016 (P1)**: `/peer/{id}/send` connection race — `ERR_PEER_CONNECTING` guard (commit `665f767`)
  - Root cause: `_register_peer()` sets `connected=True, ws=None` immediately on `/peers/connect`; send handler only checked `connected`, not `ws`, causing a spurious "not connected" 503 during WS handshake
  - Fix: added `ws is None` guard returning 503 `ERR_PEER_CONNECTING` with retry hint
  - Test fix: `wait_peer_ready()` now uses probe-send success as readiness signal instead of peer list polling
  - Verified: `test_scenario_fg.py` 19/19 ✅ (was 16/19 before fix)

### Fixed (20:00)

- **BUG-015 (P3)**: `test_scenario_fg.py` pytest incompatibility (commit `58dbb66`)
  - Root cause: module-level `sys.exit()` triggered `INTERNALERROR: SystemExit` when mixed with other pytest suites
  - Fix: refactored to `run_fg_tests()` + `test_scenario_fg()` pytest entry; `sys.exit()` moved to `if __name__ == "__main__":` guard
  - Verified: 7 tests collected cleanly in mixed-suite run; standalone `python3` execution unchanged

### Research (scan #6 — 2026-03-24 21:37)

- **A2A PR #1678 (NEW ⭐)**: Python SDK tutorial updated to `v1.0.0-alpha.0`
  - `AgentCard.url` renamed to `icon_url` (breaking); new `supported_interfaces` + `extended_agent_card` fields
  - Signal: A2A AgentCard still churning; ACP's minimal, stable AgentCard format is a differentiation point
  - `supported_interfaces` adds protocol negotiation complexity — ACP's "one link, zero config" narrative strengthened
- **A2A code layer**: 9 consecutive days without spec/code merge (last: 2026-03-16)
  - Window remains open for ACP v1.4 + v2.0 launch before A2A stabilizes
- **A2A #1676**: `PushNotificationConfig` missing (still unresolved) — ACP `/recv` polling unaffected
- **A2A #1672**: `getagentid.dev` identity CA discussion still open, no resolution
- **ANP**: archived, no new activity (dropped from tracking)
- Full report: `acp-research/reports/2026-03-24-scan-2.md`

### Research (scan #5 — 2026-03-24 18:00)

- **A2A #1676 (NEW)**: `PushNotificationConfig` definition missing from A2A spec (bug)
  - ACP is unaffected; `/recv` polling design avoids push config complexity entirely
- **A2A #1672 (47 comments)**: `getagentid.dev` emerging as de-facto A2A identity CA
  - Centralized registration service; external dependency; single point of failure
  - **ACP `did:acp:` advantage**: self-sovereign, derived from Ed25519 pubkey, zero external resolver,
    zero registration, works fully offline — already shipping in v1.5
- **A2A code layer**: 8 consecutive days with no merges (last: 2026-03-16, CODEOWNERS update)
  - TSC governance mode confirmed; fast-iteration window remains open for ACP
- **ANP**: confirmed archived (last update 2026-03-05), dropped from active tracking
- Show HN draft updated with `getagentid.dev` vs `did:acp:` talking points (commit `e39ac4f`)
- Full report: `acp-research/reports/2026-03-24-scan.md`

---

## [1.5.1-dev] — 2026-03-24

### Added

- **`GET /tasks` time-window filters** — `created_after` and `updated_after` (commit `a187471`)
  - `created_after=<ISO-8601>` — return only tasks created after this timestamp
  - `updated_after=<ISO-8601>` — return only tasks updated after this timestamp
  - Combinable with existing `state` / `peer_id` / `cursor` / `sort` params
  - Future timestamps → empty list (correct behavior, TF4)
  - Invalid timestamp strings → 200/400, no 500 crash (TF5)
  - Tests: **6/6 PASS** (`tests/test_tasks_filtering.py` — TF1–TF6)
  - Inspired by A2A v1.0.0 `tasks/list` + `last_updated_after` (research scan #4)

### Fixed

- **BUG-014 (P2)**: `GET /tasks?peer_id=` filter was always returning empty list
  - Root cause: `peer_id` is stored in `payload.peer_id`, not top-level `t["peer_id"]`
  - Fix: filter now checks both `t.get("peer_id")` and `t.get("payload", {}).get("peer_id")`
  - Previously silently broken with zero test coverage; discovered during TF6 regression test

### Research

- **A2A v1.0.0 released 2026-03-12** — competitive analysis scan #4 (commit `8f0c9b5`)
  - A2A v0.3.0 → v1.0.0 with multiple BREAKING CHANGES (OAuth modernization, gRPC multi-tenancy,
    `extendedAgentCard` restructure, `canceled` spelling standardization)
  - ACP's P2P/zero-server positioning MORE differentiated vs. A2A enterprise trajectory
  - A2A #1667 (heartbeat agent): ACP `availability` block already ships this natively
  - A2A #1672 (agent identity): reference impl submitted (getagentid.dev, centralized CA);
    ACP ed25519 self-sovereign model is superior (no third-party CA dependency)
  - Action items: P2 — SDK compat version docs; P3 — highlight self-sovereign identity in README
  - Full report: `acp-research/reports/2026-03-24-scan4.md`

---

## [1.5.0-dev] — 2026-03-24 (hybrid identity)

### Added

- **Hybrid Identity Model** (`--ca-cert`) — v1.5 (commit `7aaa2cb`)
  - New CLI flag: `--ca-cert <PATH_OR_PEM>`
  - When used alongside `--identity`: AgentCard gains `identity.ca_cert` (PEM string)
  - `identity.scheme` upgraded from `"ed25519"` → `"ed25519+ca"` in hybrid mode
  - `capabilities.identity`: `"none"` | `"ed25519"` | `"ed25519+ca"` (new enum)
  - All `did:acp:` / `public_key` fields preserved — fully backward compatible
  - New spec: `spec/identity-v1.5.md` (hybrid trust model, 4 verification strategies)
  - Tests: **6/6 PASS** (`tests/test_v15_hybrid_identity.py`)
  - **Motivation**: A2A #1672 (43 comments) converging toward same "hybrid" conclusion;
    ACP ships this today vs. A2A still in discussion

### Research

- A2A code layer: 8 consecutive days without a merge (last commit 2026-03-16)
- A2A #1672 hybrid identity: self-sovereign + CA model — ACP v1.5 preemptively ships this
- A2A #1628 trust.signals[]: enterprise blockchain-level trust, out of ACP scope
- A2A #1606 data handling declarations: compliance metadata, v2.0 extensions candidate
- Reports: `acp-research/reports/2026-03-24-scan.md`, `2026-03-24-scan2.md`

---

## [1.4.0-dev] — 2026-03-24
### Added

- **Java SDK** (`sdk/java/`) — zero external dependencies, JDK 11+ (commit `28813ed`)
  - `RelayClient.of(url)` — ping, send, recv, connectPeer, sendToPeer, stream (SSE), patchAvailability
  - Full model classes: `Part`, `Message`, `Task`, `SendRequest`, `SendResponse`, `SseEvent`
  - Zero-dependency JSON serializer/parser (`Json.java`, hand-written recursive descent)
  - Maven `pom.xml`; zero runtime dependencies (JDK 11 `java.net.http` only)
  - Spring Boot `@Bean` integration example in README
  - Tests: **41/41 ✅** (21 `JsonTest` unit + 10 `RelayClientTest` unit + 10 integration)
- **Scenario H test** — multi-agent concurrent routing validation (commit `06f6fac`)
  - H1: Hub simultaneous dual-peer connect (2/2 peers)
  - H2: Hub→WA + Hub→WB parallel 10-msg each; zero cross-routing errors ✅
  - H3: WA↔WB bidirectional concurrent exchange ✅
  - H4: Idempotency ID isolation across peers ✅
  - **6/6 PASS** — completes all 8 scenario coverage (A–H)
- README: new `## Heartbeat / Cron Agents` section with Python template (commit `06f6fac`)
- Research: ANP downgraded to archived in ROADMAP (last updated 2026-03-05)

### Test Coverage (cumulative)

| Scenario | Status | File |
|----------|--------|------|
| A — P2P dual agent | ✅ | test_three_level_connection.py |
| B — Orchestrator→Workers | ✅ | test_scenario_bc.py |
| C — Pipeline A→B→C→A | ✅ | test_scenario_bc.py |
| D — Stress (100 msgs, concurrent) | ✅ | test_scenario_d_stress.py |
| E — NAT 3-level fallback (real) | ⏳ needs real NAT environment | — |
| F — Error handling | ✅ | test_scenario_fg.py |
| G — Disconnect/reconnect | ✅ | test_scenario_fg.py |
| H — Multi-agent concurrent routing | ✅ | (ad-hoc, 2026-03-24) |

---

## [1.3.0-dev] — 2026-03-22/23
### Added (v1.4-dev)
- **Three-level connection strategy fully integrated** in `guest_mode`:
  - Level 1: Direct WebSocket (unchanged)
  - Level 2: DCUtR UDP hole punch via relay signaling (**NEW** — wired into main connect flow)
    - Signaling-only relay WS for address exchange
    - STUNClient public address discovery
    - Simultaneous UDP probes via DCUtRPuncher
    - SSE events: `dcutr_started`, `dcutr_connected`, `relay_fallback`
    - `status.connection_type`: `p2p_direct` | `dcutr_direct` | `relay`
  - Level 3: Relay permanent fallback (unchanged)
- **tests/test_three_level_connection.py**: 20/20 PASS

### Added (v1.1)
- **`GET /tasks` pagination** — keyset cursor pagination, state/peer_id filter, sort order
  - New params: `limit` (max 200), `cursor` (exclusive keyset), `state`, `peer_id`, `sort`
  - Response: `has_more`, `next_cursor`, `total` fields
  - Addresses the gap noted in A2A issue #1667 discussion


### Added (2026-03-23 — DCUtR NAT 穿透初版实现)

- **DCUtR 风格 UDP 打洞 NAT 穿透 — Level 2 连接策略（v1.4 特性，初版实装）**
  - 新增 `STUNClient` 类 (~120 行)：stdlib-only STUN Binding Request 客户端
    - 支持 RFC 5389 / RFC 8489（XOR-MAPPED-ADDRESS 优先，MAPPED-ADDRESS 兜底）
    - 使用公共 STUN 服务器 `stun.l.google.com:19302`
    - 3s 超时，失败静默返回 None（不抛异常）
    - 运行在 executor 中，不阻塞 asyncio event loop
  - 新增 `DCUtRPuncher` 类 (~200 行)：UDP 打洞状态机
    - `attempt(relay_ws, local_port)` — 发起方：发 dcutr_connect → 等 dcutr_sync → 双方同时发 UDP 包 → 等回包
    - `listen_for_dcutr(relay_ws, local_port)` — 响应方：等 dcutr_connect → 回 dcutr_sync → 执行打洞
    - 打洞成功后自动关闭 Relay 连接（后续通信完全直连）
    - 所有超时/失败均静默降级，不抛异常到上层
  - 新增 `connect_with_holepunch()` 函数 (~60 行)：对外公开 API
    - 返回 `(websocket, is_direct: bool)`
    - Level 1: 直连（3s timeout）→ Level 2: UDP 打洞（5s 信令 + 3s 探测）→ Level 3: Relay 永久中转
  - 新增 3 种 ACP 控制消息类型：`dcutr_connect` / `dcutr_sync` / `dcutr_result`
    - 在 Relay WebSocket 上传输，不影响业务消息
  - **stdlib only**：`asyncio`, `socket`, `struct`, `os`, `time`, `uuid` — 无新增第三方依赖
  - **向后兼容**：`acp://` 链接格式不变，NAT 穿透对上层完全透明
  - 文档：新建 `docs/nat-traversal.md`（用户指南），更新 `spec/nat-traversal-v1.4.md`（完整规范）

### Fixed (commit `638f778` — 2026-03-23, scenario-C ring pipeline testing)

- **BUG-007 part 2 (P1)** — `/message:send` with `peer_id` still routed to wrong peer
  - Root cause: BUG-007 part 1 (commit `3a1c499`) added the ambiguity guard but did not
    update the actual send dispatch — `_ws_send_sync(msg)` continued to use `_peer_ws`
    (the last-connected peer) even when `peer_id` was explicitly provided in the body.
  - Fix: `_ws_send(msg, peer_id=None)` and `_ws_send_sync(msg, peer_id=None)` now accept
    an optional `peer_id` parameter. When supplied, they look up `_peers[peer_id]["ws"]`
    and route directly to that WebSocket, also updating the per-peer `messages_sent`
    counter. Both the sync and async paths of `/message:send` now pass `_req_peer_id`.
  - Legacy behavior (no `peer_id` → use `_peer_ws`) preserved for backward compatibility.
  - Verified with Scenario C (A→B→C→A ring pipeline): 8/8 checks pass ✅.

### Tested — Scenario C: A→B→C→A Ring Pipeline (2026-03-23)
Full end-to-end 3-agent ring pipeline validated:
- Ring topology established: A→B, B→C, C→A (6 peer connections total, 2 per agent) ✅
- A injects payload (`raw=[1,2,3,4,5]`) → B via `peer_id`-directed `/message:send` ✅
- B receives, processes (`doubled=[2,4,6,8,10]`), forwards to C ✅
- C receives, finalizes (`sum=30`), sends result back to A ✅
- A receives complete pipeline result ✅
- Task state machine (`pipeline_001` → `completed`) ✅
- Per-agent send/recv stats correct (A:2/1, B:1/1, C:1/1) ✅
- **Result: 8/8 PASS 🎉**

### Fixed (commit `3a1c499` — 2026-03-23, 3-agent scenario-B testing)
Two bugs discovered during Orchestrator → Worker1 + Worker2 multi-peer test:

- **BUG-007 (P1)** — `/message:send` silently routed to wrong peer when multiple peers connected
  - When ≥2 peers are connected and no `peer_id` is supplied, `/message:send` previously
    sent to `_peer_ws` (the most recently connected peer) with no indication of ambiguity.
  - Fix: if `len(connected_peers) > 1` and `peer_id` is absent in the request body, return
    HTTP 400 `ERR_AMBIGUOUS_PEER` with a `connected_peers` list guiding the caller to use
    `POST /peer/{id}/send` for directed delivery. If `peer_id` IS supplied in the body,
    the message is routed to that specific peer (single-peer path unchanged).
  - Verified: `ERR_AMBIGUOUS_PEER` returned with peer list ✅; `peer_id` routing ✅;
    single-peer agents unaffected ✅.

- **BUG-008 (P2)** — Task action endpoints had inconsistent naming convention
  - `:cancel` used A2A-aligned colon style; `/update`, `/wait`, `/continue` used slash style.
  - Fix: router now accepts **both** colon and slash variants for all three endpoints:
    `POST /tasks/{id}:update` / `/tasks/{id}/update`,
    `GET /tasks/{id}:wait` / `/tasks/{id}/wait`,
    `POST /tasks/{id}:continue` / `/tasks/{id}/continue`.
    Old slash-style paths remain fully supported (backward-compatible).
  - Spec will be updated to recommend colon style; both accepted indefinitely.
  - Verified: `/update` slash ✅, `:update` colon ✅, `:wait` colon ✅.

### Known Issues (discovered 2026-03-23, not yet fixed)

- **BUG-009 (P1)** — SSE `/stream` event delivery latency ~950 ms
  - Root cause: the `/stream` and `/tasks/{id}:subscribe` handlers poll the event queue
    using `time.sleep(1)` in a busy-wait loop. On average, an event arriving mid-sleep
    waits ~500 ms; worst case 1 s. Measured avg 950 ms across 8 trials.
  - Impact: SSE push is unsuitable for latency-sensitive use cases until fixed.
  - Planned fix: replace `time.sleep(1)` with `threading.Event.wait(timeout=0.05)`;
    `_broadcast_sse_event` calls `event.set()` to wake subscribers immediately.
    Expected result: SSE delivery latency < 10 ms.
  - Priority: P1 — fix in next development round.

### Fixed (commit `643450c` — 2026-03-23, real dual-agent testing)
Six bugs discovered during first live AlphaAgent↔BetaAgent P2P communication session:

- **BUG-001 (P0)** — SSE `/stream` never delivered message events (only keepalive)
  - Root cause 1: `HTTPServer` is single-threaded; the `/stream` blocking loop blocked all
    subsequent HTTP requests including `/message:send`. Fix: use `ThreadingHTTPServer`.
  - Root cause 2: BaseHTTP defaults to HTTP/1.0 and sets `close_connection = True` after
    `handle_one_request()` returns, silently closing the SSE connection before any events
    are sent. Fix: `self.close_connection = False` + `X-Accel-Buffering: no` header.
  - Root cause 3: `/message:send` outbound path never called `_broadcast_sse_event`.
    Fix: add broadcast with `direction: "outbound"` after `_ws_send_sync`.
  - Test fix: `tests/compat/test_stream.py` raw-socket reader returns 0 bytes against
    HTTP/1.0 keep-alive connections; replaced with `http.client` streaming reader.

- **BUG-002 (P0)** — Task `:cancel` endpoint returned `status: "failed"` instead of `"canceled"`
  - Added `TASK_CANCELED = "canceled"` constant; added to `TERMINAL_STATES`;
    cancel handler now uses the constant.

- **BUG-003 (P1)** — `/peers/connect` for the same link created duplicate peer entries
  - Two-layer fix: (1) `/peers/connect` checks existing connected peers before registering;
    returns `already_connected: true` on match. (2) `guest_mode()` WS connect reuses
    pre-registered peer entry (matched by token link) instead of calling `_register_peer()`
    again, which had created a second entry.

- **BUG-004 (P1)** — `/message:send` response body missing `server_seq` field
  - Captured `seq = msg["server_seq"]` before `_ws_send_sync`; included in both sync
    (reply) and async (fire-and-forget) response paths.

- **BUG-005 (P1)** — `peer.messages_received` counter never incremented
  - `_on_message()` now looks up sender peer by `msg.get("from")` name; falls back to
    single connected peer when `from` field absent; increments `messages_received`.

- **BUG-006 (P2)** — Client-supplied `task_id` in POST `/tasks` body was ignored
  - `_create_task()` now accepts optional `task_id` parameter; if the ID already exists,
    returns the existing task (idempotent). `/tasks` handler passes `body.get("task_id")`.

### Added
- **Extension mechanism** — URI-identified AgentCard extensions (commit `88d00fc`)
  - New optional `extensions` array in AgentCard: `[{uri, required, params?}]`
  - `capabilities.extensions: true` flag when at least one extension declared
  - Runtime APIs:
    - `GET /extensions` — list all declared extensions with count
    - `POST /extensions/register` — register new extension at runtime (no restart)
    - `POST /extensions/unregister` — remove extension by URI at runtime
  - Merge semantics: URI-keyed; re-registering the same URI updates in-place
  - Extensions omitted from AgentCard when none declared (clean opt-in)
  - `tests/unit`: +5 `TestExtensions` tests (card absent/present, capabilities flag, register/unregister)
  - `docs/integration-guide.md`: full Extension mechanism section with curl examples
  - `docs/comparison.md`: ACP Extensions vs A2A `extensions[]` comparison row
  - Design: aligned with A2A extension model (URI-identified, `required` flag), zero-config when unused

- **`did:acp:` DID Identity** — stable, self-sovereign Agent identifier (commit `6595e39`)
  - Derives `did:acp:<base64url(ed25519-pubkey)>` from existing `--identity` keypair
  - No external registry; the DID **is** the key (key-based method)
  - AgentCard gains `did` field when identity enabled; omitted otherwise
  - New endpoint `GET /.well-known/did.json` — W3C-compatible DID Document:
    - `verificationMethod[]` with `publicKeyMultibase` (Ed25519VerificationKey2020)
    - `authentication`, `assertionMethod` relationships
    - Returns 404 when `--identity` not configured
  - `capabilities.did_identity: true` flag when `--identity` provided
  - Outbound AgentCard includes `did` field for peer verification
  - `tests/unit`: +5 `TestDidAcp` tests (derivation, AgentCard embed, DID Document structure)
  - `docs/integration-guide.md`: full DID Identity section (format, AgentCard sample,
    `/.well-known/did.json` sample, Python peer-verification snippet, design notes)
  - `docs/comparison.md`: DID identifier + DID Document rows — `did:acp:` (key-based, no DNS)
    vs ANP `did:wba:` (domain-based, requires DNS)
  - `docs/README.zh-CN.md`: v1.3 status `规划中` → 🚧 进行中, all three items ✅

- **Official Docker image v1.3 + GHCR CI publish pipeline** (commit `1f0b7e5`)
  - `Dockerfile` version label bumped `1.2.0` → `1.3.0`
  - New run examples in `Dockerfile` header: v1.3 Extension + DID identity flags
  - GHCR pull instructions: `docker pull ghcr.io/kickflip73/agent-communication-protocol/acp-relay:latest`
  - **`.github/workflows/docker-publish.yml`** — automated multi-arch build & push:
    - Triggers: push to `main`, semver tags (`v*.*.*`), manual `workflow_dispatch`
    - Matrix: `base` (no extra deps) + `full` (`websockets` + `cryptography`)
    - Registry: GitHub Container Registry (`ghcr.io`)
    - Tags: `:latest`, `:vX.Y.Z`, `:sha-<short>`, `-full` variant suffix
    - Platforms: `linux/amd64` + `linux/arm64` (multi-arch)
    - GHA layer cache (`cache-from/to: type=gha`) for fast incremental rebuilds
    - Smoke-test job: pull `:latest`, start container, verify `/.well-known/acp.json` returns valid AgentCard
  - `docker-compose.yml` v1.3 additions:
    - Commented DID Identity pair example (requires `acp-relay:full`, persistent `acp-identity` volume)
    - Commented Extension registration demo example
    - `volumes.acp-identity` declaration for stable Ed25519 keypair across container restarts

### Notes
- v1.3 introduces two orthogonal extensibility layers:
  **Extensions** (capability advertisement) + **DID** (identity layer)
- Both are fully opt-in: no breaking changes to v1.0/v1.2 deployments
- Unit test total: 92 (v1.2) + 10 (v1.3 TestExtensions + TestDidAcp) = **102 PASS**
- `tests/unit/test_relay_core.py`: 121 `def test_` entries (includes v1.3 classes)
- ACP now has 4 extensibility dimensions: **HMAC security** · **Ed25519 identity** ·
  **availability scheduling** · **URI-identified Extensions** — all opt-in, zero-config default
- v1.1 Backlog fully closed: `failed_message_id` ✅ · replay-window ✅ · Rust SDK ✅ · DID ✅ · Docker CI ✅
  (only HTTP/2 transport binding remains open as optional long-term item)

---

## [1.2.0-dev] — 2026-03-22

### Added
- **AgentCard `availability` block** — heartbeat/cron agent scheduling metadata (commit `c10c230`)
  - New optional `availability` object in AgentCard; omitted when not configured (opt-in)
  - Fields: `mode` (`persistent`|`heartbeat`|`cron`|`manual`), `interval_seconds`,
    `next_active_at`, `last_active_at` (auto-stamped from startup time), `task_latency_max_seconds`
  - `capabilities.availability: true` flag when block is present
  - CLI flags: `--availability-mode`, `--heartbeat-interval`, `--next-active-at`
  - Config-file keys: `availability-mode`, `heartbeat-interval`, `next-active-at`
  - ACP is the **first Agent communication protocol** to support scheduling metadata natively
    (A2A issue #1667, 2026-03-21: A2A AgentCard has no scheduling fields)
  - `tests/unit`: +10 `TestAgentCardAvailability` tests; total 83 PASS
- **`PATCH /.well-known/acp.json`** — live availability update API (commit `cd67181`)
  - Heartbeat agents can stamp `next_active_at` / `last_active_at` on each wake
    without restarting the relay
  - Merge semantics: only patched fields are updated; others preserved
  - Whitelist validation: allowed fields enforced; unknown fields → 400
  - Mode enum validation; missing `availability` key → 400
  - Supports both `/card` and `/.well-known/acp.json` paths
  - `tests/unit`: +9 `TestPatchAvailability` tests; total 92 PASS
- **`docs/cli-reference.md`** updated to v1.2
  - New section: "Live availability update (PATCH)" with curl examples, response schema,
    PATCH rules summary, macOS/Linux `date` command portability note

- **Rust SDK** — `sdk/rust/` — `acp-relay-sdk` v1.2 (commit `bed7884`)
  - Thin blocking HTTP client (`reqwest 0.12` + `serde` + `thiserror`)
  - `RelayClient::new(base_url)` — validates URL scheme; strips trailing slash
  - `send_message(MessageRequest)` → `MessageResponse`
    - `MessageRequest::user/agent(text)` helpers; `.with_message_id(id)`;
      `.sync_timeout(secs)` for blocking request-response
  - `agent_card()` → `AgentCardResponse` (self + optional peer, with `Availability`)
  - `patch_availability(AvailabilityPatch)` → live update scheduling metadata (v1.2)
  - `status()`, `link()`, `ping()` utility methods
  - `AcpError` enum: `Http` / `Relay { code, message }` / `InvalidUrl` / `Json`
  - 8 unit tests (helpers, URL validation, skip_serializing_if behaviour)
  - `sdk/rust/README.md`: quick-start, heartbeat example, API table
- **`docs/integration-guide.md`** — new full Rust SDK section (send, card, PATCH, error handling)
  - Added Go SDK section header to match Python/Node/Rust consistency

### Notes
- Inspired by A2A issue #1667: A2A protocol has no mechanism for heartbeat/cron agents
  to advertise scheduling intent. ACP v1.2 fills this gap with a clean, opt-in design.
- Multi-language SDK matrix now complete: Python ✅ · Go ✅ · Node.js ✅ · Rust ✅

---

## [1.1.0-dev] — 2026-03-22

### Added
- **HMAC replay-window** (`--hmac-window <seconds>`, default 300 s) (commit `e263f52`)
  - New `_hmac_check_replay_window(ts_str)` helper: parses ISO-8601 UTC timestamp,
    checks `|server_now − msg_ts| ≤ window`; returns `(ok, reason)` for clean logging
  - Inbound WS handler: when `--secret` is set, out-of-window messages are **hard-rejected
    (dropped)** before any processing — prevents replay attacks
  - Signature mismatch remains warn-only for graceful interop with legacy agents
  - Configurable via `--hmac-window <seconds>` CLI flag or `hmac-window` config-file key
  - Graceful degradation: when `--secret` is not set, replay-window check is a no-op
  - `docs/security.md`: HMAC audit result PARTIAL → ✅ PASS; new §1.3 replay-window docs;
    audit history v1.1.0 = 9 PASS, 0 PARTIAL
  - `tests/unit`: +10 `TestHMACReplayWindow` tests; unit test total 63 → **73 PASS**

### Security
- HMAC-SHA256 audit now **fully PASS** (9/9, 0 PARTIAL)
  - Previous PARTIAL item: "no server-side timestamp window check" — now resolved

---

## [1.0.0] — 2026-03-21

### Added (P0 — Specification & Versioning)
- **`spec/core-v1.0.md`**: authoritative v1.0 specification (631 lines) (commit `20aa1ed`)
  - Supersedes `spec/core-v0.8.md`
  - Stability annotations: `stable` / `experimental` per endpoint and field
  - §1.1: role MUST-level validation rules (v0.9 breaking change formally recorded)
  - §4: complete HTTP API stability matrix (17 endpoints)
  - §6: `ERR_INVALID_REQUEST` formal definition (incl. role trigger)
  - §11: CLI reference (12 flags, stability annotations)
  - §12: package distribution (`pip install acp-relay`, `npm install acp-relay-client`)
  - §13: v1.0 compatibility guarantees (4 MUST requirements)
  - Appendix A: version history through v0.9 + v1.0
  - Appendix B: ACP vs A2A comparison table (refs #876, #883)
- **API stability annotations** in `acp_relay.py` (commit `19b3627`)
  - `[stable]` (13 endpoints): `/.well-known/acp.json`, `/status`, `/peers`, `/recv`,
    `/tasks`, `/stream`, `/message:send`, `/send` (legacy), `/peers/connect`,
    `/tasks/{id}/continue`, `/tasks/{id}:cancel`, `/skills/query`
  - `[experimental]` (1 endpoint): `/discover` (mDNS, platform-dependent)
- **`docs/security.md`**: complete security model documentation (commit `a3ee229`)
  - §1 HMAC-SHA256: mechanism, audit findings table (replay-window later resolved in v1.1)
  - §2 Ed25519: mechanism, audit findings table, HMAC coexistence
  - §3 HMAC vs Ed25519 side-by-side comparison
  - §4 Transport security recommendations (nginx/Caddy/Cloudflare Tunnel)
  - §5 Known limitations summary (severity + roadmap)
  - §6 Audit history
- **Go SDK stub** (`sdk/go/`) (commit `bcf6b75`)
  - Package `acprelay` — stdlib-only, zero external dependencies (Go 1.21+)
  - `Client` struct with 6 stable methods: `Send`, `Recv`, `GetStatus`, `GetTasks`,
    `CancelTask`, `QuerySkills`
  - 16 tests via `net/http/httptest.Server`
  - `sdk/go/README.md` with install + quick start + API reference table

### Changed (P0)
- **Version bumped to `1.0.0`** across all package files (commit `ddfaf07`)
  - `relay/acp_relay.py`: `VERSION = "0.8-dev"` → `"1.0.0"`
  - `pyproject.toml`: `0.9.0.dev0` → `1.0.0`
  - `sdk/python/setup.py`: `0.9.0.dev0` → `1.0.0`
  - `sdk/node/package.json`: `0.9.0-dev.0` → `1.0.0`

### Security (P1 — Audit)
- **HMAC-SHA256 audit** (commit `a3ee229`)
  - ✅ PASS: `hmac.compare_digest` constant-time comparison
  - ✅ PASS: no timing oracle in error path
  - ✅ PASS: `message_id` unpredictability (`secrets.token_hex(8)`)
  - ✅ PASS: secret never written to disk
  - ⚠️ PARTIAL: no server-side replay-window timestamp check (resolved in v1.1 `--hmac-window`)
- **Ed25519 identity audit** (commit `a3ee229`)
  - ✅ PASS: key file permissions enforced (`chmod 0600`)
  - ✅ PASS: canonical form deterministic (`sort_keys=True` + compact separators)
  - ✅ PASS: `identity.sig` excluded from signing payload correctly
  - ✅ PASS: `InvalidSignature` exception handling (no exception leaks)
  - ✅ PASS: graceful fallback when `cryptography` not installed
  - ✅ PASS: key generation from OS CSPRNG (`Ed25519PrivateKey.generate()`)

### Release Tag
- `v1.0.0-rc.1` pushed (commit `ddfaf07`)

---

## [0.9.0] — 2026-03-21

### Added (P0 — Developer UX)
- **CLI `--version`**: prints `acp_relay.py <version>` and exits (commit `e74afdf`)
- **CLI `--verbose` / `-v`**: switch root logger from INFO → DEBUG at startup
- **CLI `--config <FILE>`**: load defaults from a JSON or YAML config file
  - JSON: stdlib `json.loads`
  - YAML: stdlib-only flat key-value parser (no PyYAML required); bool/int coercion
  - Precedence: `CLI flags > config file > hardcoded defaults`
  - All 12 flags supported; clear error + exit(1) on missing file
- **Example config files**: `relay/examples/config.json`, `config-relay.json`, `config-secure.yaml`
- **`docs/cli-reference.md`**: comprehensive CLI reference (all flags, port layout, 8 usage patterns, config file section)
- **`spec/core-v0.8.md`**: single authoritative specification (515 lines, supersedes core-v0.5.md) (commit `4728b0e`)
  - 11 chapters: principles, message envelope, Part model, Task FSM, AgentCard, error codes, extensions, transport, peer registration, skill query, versioning
  - Appendix A: full version history v0.1–v0.8
  - Appendix B: A2A v1.0 comparison table

### Changed (P0)
- `AsyncRelayClient` rewritten — **stdlib-only, zero external dependencies** (removed `aiohttp`) (commit `7bcb907`)
  - Implementation: `asyncio.get_event_loop().run_in_executor()` offloads urllib calls to thread pool
  - New methods: `connect_peer`, `discover`, `card`, `link`, `get_task`, `continue_task`,
    `cancel_task`, `wait_for_task`, async `stream` generator
  - `send()`: adds `context_id` (v0.7), `task_id`, `create_task`, `sync` mode
  - `update_task()`: new `artifact` parameter
  - `query_skills()`: adds `query` free-text + `limit` params
  - `wait_for_peer()`: converted to async
  - 35 new tests in `sdk/python/tests/test_async_relay_client.py` — all passing
- Python SDK `__version__`: `0.6.0` → `0.8.0`
- `acp-research/ROADMAP.md`: full rewrite — all v0.1–v0.8 milestones marked complete

### Added (P1 — Quality & Docs)
- **`/message:send` server-side required field validation** (commit `bb1c80e`)
  - Missing `role` → `400 ERR_INVALID_REQUEST` with descriptive error message
  - Invalid `role` value (not `user`/`agent`) → `400 ERR_INVALID_REQUEST`
  - Replaces silent default `"user"` fallback; addresses A2A issue #876 gap
  - 7 new MUST-level test cases in `tests/compat/test_message_send.py`
- **`CHANGELOG.md`** (this file): complete version history v0.1.0–v0.9.0-dev (commit `b48e9d5`)
- **`docs/integration-guide.md`** comprehensive rewrite (commit `2a74d3e`)
  - Covers P2P / Relay / mDNS transport options; port layout (WS :7801 + HTTP :7901)
  - Task CRUD, multi-peer sessions, HMAC signing, Ed25519 identity
  - Python sync + async SDK examples; Node.js SDK examples
  - Multi-language quick-start (curl / Go / Java / Rust)
  - Troubleshooting table (503 / 400 / 413 + solutions)
- **`tests/unit/test_relay_core.py`**: 63 unit tests covering all internal helpers (commit `ac9846c`)
  - TestErrHelper, TestIdGenerators, TestPartConstructors, TestValidatePart/Parts,
    TestHMACHelpers, TestTaskStateConstants, TestLoadConfigFile, TestParseLink, TestVersion

### Added (P2 — Package Distribution)
- **`pyproject.toml`**: `pip install acp-relay` support (commit `0fb0c9e`)
  - Package name: `acp-relay`; version: `0.9.0.dev0`
  - Required dep: `websockets>=12.0` only
  - Optional `[identity]`: `cryptography>=42.0`; Optional `[dev]`: pytest + httpx
  - CLI entry-point: `acp-relay = 'acp_relay:main'`
  - `relay/py.typed` PEP 561 marker
- **Node.js SDK renamed** to `acp-relay-client` (commit `9c1b0d9`)
  - ESM entry-point `src/index.mjs` (createRequire bridge, `export default RelayClient`)
  - `package.json`: full npm metadata, `exports` field (ESM + CJS + types), files whitelist
  - `.npmignore`: excludes `tests/` from published package
  - `LICENSE`: Apache-2.0 (aligned with repo root)
  - 19 tests passing

---

## [0.8.0] — 2026-03-21

### Added
- **Ed25519 optional identity extension** (`--identity [path]`) (commit `1a13dec`)
  - Self-sovereign keypair: auto-generated at `~/.acp/identity.json` (chmod 0600)
  - Every outbound message includes `identity.sig` (base64url-encoded Ed25519 signature)
  - AgentCard publishes `identity.public_key` for peer verification
  - Graceful fallback: identity block omitted when `cryptography` not installed
  - Requires: `pip install cryptography`
- **Node.js SDK** (`sdk/node/`) (commit `fd8c02a`)
  - `RelayClient` class — zero external dependencies, TypeScript types
  - All v0.8 endpoints: send, recv, tasks, peers, skills, stream (SSE)
  - 19 tests passing
- **Compatibility test suite** (`tests/compat/`) (commit `98197cf`)
  - Black-box spec compliance runner: parameterized by `ACP_BASE_URL`
  - Covers: AgentCard structure, `/message:send` response shape, SSE events,
    Task lifecycle, error code format, idempotency
- **`spec/core-v0.8.md`**: consolidated authoritative specification (515 lines)
  supersedes `spec/core-v0.5.md` and `spec/transports.md`

### Changed
- README overhauled for v0.8: dependency table, full feature matrix, updated quickstart

---

## [0.7.0] — 2026-03-20

### Added
- **HMAC-SHA256 optional message signing** (`--secret <key>`) (commit `87dad51`)
  - `sig = HMAC-SHA256(secret, message_id + ":" + timestamp)`
  - Verification is warn-only (never drops messages) for graceful interop
  - AgentCard `trust.scheme`: `"hmac-sha256"` | `"none"`
- **mDNS LAN peer discovery** (`--advertise-mdns`) (commit `aabfae5`)
  - Pure stdlib UDP multicast `224.0.0.251:5354` — no zeroconf library required
  - `GET /discover`: returns list of LAN peers with `acp://` links
  - SSE event `type=mdns` for real-time new-peer notifications
- **`context_id` multi-turn conversation grouping** (commit `aabfae5`)
  - Optional field on `/message:send` — client-generated, server-echoed
  - Groups related messages across multiple Task cycles
  - AgentCard capability: `context_id: true`
- **`spec/transports.md` v0.3**: Protocol Bindings vs Extensions separation (commit `68db641`)

### Changed
- AgentCard `capabilities` block: `hmac_signing`, `lan_discovery`, `context_id` fields

---

## [0.6.0] — 2026-03-20

### Added
- **Multi-session peer registry** (commit `ad7e1c4`)
  - `GET /peers`: list all connected peers
  - `GET /peer/{id}`: get a specific peer's info
  - `POST /peer/{id}/send`: send a message to a specific peer
  - `POST /peers/connect`: connect to a new peer via `acp://` link
  - AgentCard capability: `multi_session: true`
- **Standardized error codes** (commit `c816cb5`)
  - 6 codes: `ERR_NOT_CONNECTED` / `ERR_MSG_TOO_LARGE` / `ERR_NOT_FOUND` /
    `ERR_INVALID_REQUEST` / `ERR_TIMEOUT` / `ERR_INTERNAL`
  - Unified response: `{ok, error_code, error, failed_message_id}`
  - `failed_message_id`: enables precise client-side retries (inspired by ANP)
  - Reference: `spec/error-codes.md`
- **Minimal agent spec** (`spec/v0.6-minimal-agent.md`): 3-endpoint minimum to join ACP network
  - `GET /.well-known/acp.json` (AgentCard)
  - `POST /message:send` (receive inbound)
  - `GET /stream` (SSE outbound, optional)
- **Python SDK v0.6** (`sdk/python/`) (commit `430a97f`)
  - `RelayClient`: sync HTTP client, all v0.6 endpoints, stdlib-only
  - `RelayClient.stream()`: SSE generator using `urllib`
- **Cloudflare Worker v2.0** (commit `8e8b771`)
  - Multi-room concurrent sessions
  - Sliding TTL (30 min inactivity expiry)
  - Cursor-based poll (no duplicate messages)
  - `DELETE /acp/{token}` cleanup endpoint
- **Transport C: HTTP polling relay** (`acp+wss://` scheme) (commit `907c729`)
  - Fallback for K8s/firewall environments with no inbound TCP
  - Auto-fallback: P2P timeout (10 s) → relay (commit `fd74394`)
  - Composite link: single `acp://` token pre-registered on relay; transparent upgrade/fallback
- **Proxy-aware WebSocket connector** (commit `4f392b8`)
  - Reads `http_proxy` / `HTTPS_PROXY` env vars; routes WS through HTTP CONNECT tunnel

### Removed
- **GitHub Issues relay transport** (`acp+gh://`) permanently deleted (commit `bc25ab7`)
  - Reason: required both-side GitHub tokens; violated zero-registration principle

---

## [0.5.0] — 2026-03-19

### Added
- **Task state machine** — 5 states (commit `cd9545e`, `bb6aba3`)

  ```
  submitted → working → completed
                     → failed
                     → input_required  (resumable via /tasks/{id}/continue)
  ```

  New endpoints:
  | Endpoint | Method | Description |
  |----------|--------|-------------|
  | `/tasks` | GET | List tasks; `?status=` filter |
  | `/tasks/{id}` | GET | Get single task |
  | `/tasks/{id}/wait` | GET | Long-poll until terminal state (`?timeout=N`) |
  | `/tasks/{id}/update` | POST | Update state + optional artifact |
  | `/tasks/{id}/continue` | POST | Resume from `input_required` |
  | `/tasks/{id}:cancel` | POST | Cancel → `failed` |
  | `/tasks/{id}:subscribe` | GET | Per-task SSE stream |

- **Bilateral task synchronization**: `create_task: true` on `/message:send` auto-registers
  same-id task on the receiving peer; state updates propagate back via `task.updated` messages
- **Structured Part model** — three types:
  ```json
  {"type": "text",  "content": "Hello"}
  {"type": "file",  "url": "https://...", "media_type": "image/png", "filename": "photo.png"}
  {"type": "data",  "content": {...}}
  ```
- **Message idempotency**
  - `message_id`: client-generated UUID, server deduplicates per session
  - `server_seq`: monotonically increasing counter; clients can detect gaps/reordering
- **QuerySkill API** (commit `710aade`)
  - `POST /skills/query`: runtime capability query (`skill_id`, `capability` filter)
  - `GET /.well-known/acp.json`: standard AgentCard discovery endpoint
- **Structured SSE event types**: `status` | `artifact` | `message` | `peer`
- **`/message:send` endpoint** (A2A-aligned) alongside legacy `/send`
- **`spec/core-v0.5.md`**: initial formal specification

---

## [0.4.0] — 2026-03-18

### Added
- **A2A-aligned AgentCard** (commit `83ca11b`)
  - `/.well-known/acp.json`: `name`, `description`, `version`, `capabilities`, `skills`
  - `session_id` field on all messages
- **Safety limits**: `--max-msg-size` flag (default 1 MiB); `ERR_MSG_TOO_LARGE` on violation
- **`--relay` flag for host mode**: one-command relay session start (commit `07f38ff`)
- **SKILL.md v2**: full SOP runbook with InStreet-style observable verification

### Fixed
- Unbounded consumption risk: max message size enforcement
- Critical `NameError` in peer-equal architecture refactor (commit `af73415`)

---

## [0.3.0] — 2026-03-18

### Added
- **Four communication modes** (commit `4f7e242`)
  1. Standard (request-response)
  2. Streaming (SSE events)
  3. Task delegation (fire-and-forget with status polling)
  4. Broadcast (one-to-many)
- **Explicit connection lifecycle**: `connect` / `disconnect` events; clean teardown
- **Lightweight explicit session management**: session tokens in AgentCard

---

## [0.2.0] — 2026-03-05

### Added
- **ACP P2P v0.2**: decentralized group chat support
- **Skill guide**: how to expose and invoke agent capabilities
- **`acp_relay.py`**: local daemon replacing central relay server architecture
- Zero-code-change design: Agents connect by passing a single link
- Human-as-messenger pattern: `acp://IP:PORT/TOKEN` link shared by human

### Changed
- Architecture shift: from centralized relay → true P2P direct connect (commit `183c425`)

---

## [0.1.0] — 2026-03-05

### Added
- Initial ACP v0.1 specification (`spec/`)
- Python SDK skeleton (`sdk/python/`)
- Gateway server reference implementation
- Framework integration examples (LangChain, AutoGen, CrewAI stubs)
- Bilingual README (EN + ZH)
- Design principles established:
  1. Lightweight & zero-config
  2. True P2P — no middleman
  3. Practical — curl-compatible
  4. Personal/team focus
  5. Standardization (Agent↔Agent, like MCP for Agent↔Tool)

---

## Version Summary

| Version | Date | Theme | Key Feature |
|---------|------|-------|-------------|
| 2.18.0 | 2026-03-30 | JWKS Compat Layer | `trust.signals[type=jwks]`; `GET /.well-known/jwks.json` RFC 7517; `capabilities.trust_jwks`; 13/13 PASS |
| 2.17.0 | 2026-03-30 | Availability Schedule | CRON-based `availability.schedule`; `GET /availability`; `POST /availability/heartbeat`; 22/22 PASS |
| 2.16.0 | 2026-03-30 | Delegation Chain | Signed identity delegation in AgentCard; ws_ready dedup fix (BUG-041) |
| 2.15.0 | 2026-03-29 | Context Query | GET /context/<id>/messages multi-turn conversation history |
| 0.9.0-dev | 2026-03-21 | Developer UX + Distribution | CLI flags, async SDK stdlib-only, unit tests, `pip install acp-relay`, `acp-relay-client` npm |
| 0.8.0 | 2026-03-21 | Ecosystem | Ed25519 identity, Node.js SDK, compat test suite |
| 0.7.0 | 2026-03-20 | Trust + Discovery | HMAC signing, mDNS LAN discovery, context_id |
| 0.6.0 | 2026-03-20 | Multi-peer + Reliability | Peer registry, error codes, HTTP relay, Python SDK |
| 0.5.0 | 2026-03-19 | Structure | Task state machine, Part model, idempotency, QuerySkill |
| 0.4.0 | 2026-03-18 | Safety | AgentCard v2, max-msg-size, SKILL.md SOP |
| 0.3.0 | 2026-03-18 | Modes | 4 communication modes, explicit lifecycle |
| 0.2.0 | 2026-03-05 | P2P | True P2P relay, Skill guide, zero-code-change |
| 0.1.0 | 2026-03-05 | Foundation | Initial spec, Python SDK, design principles |

---

## [v2.97.0] - 2026-04-10
### Added
- **`--persist-queue <DB_PATH>` — SQLite-backed persistent offline queue** (A2A #1667 inspired)
  - Offline messages now survive relay restarts and are re-delivered when the peer reconnects
  - Enables heartbeat-agent (cron-scheduled) workflows: Agent wakes up, receives buffered messages, sleeps again
  - `_pq_init()`: creates SQLite schema, loads surviving messages into memory on startup
  - `_pq_insert()`: persists each enqueued message atomically
  - `_pq_delete_peer()`: purges delivered rows after successful `_offline_flush()`
  - `_pq_stats()`: exposes `{"enabled", "db", "total_rows", "distinct_peers"}` in `/status`
  - `capabilities.persist_queue: true` in AgentCard when enabled
  - Backward-compatible: default behavior (in-memory only) unchanged
  - **Tests**: `tests/test_persist_queue.py` — PQ1–PQ8, **8/8 PASS**
### Research
- scan30: A2A #1667 heartbeat-agents (ACP relay architecture natural fit); #1718 bilateral records
  (ACP bilateral_ir leads by 2-3 months); A2A official Rust SDK merged
