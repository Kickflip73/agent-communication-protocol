# CHANGELOG

All notable changes to ACP (Agent Communication Protocol) are documented here.

Format: [Semantic Versioning](https://semver.org) — `MAJOR.MINOR.PATCH-status`
Dates: Asia/Shanghai (UTC+8)

---

## [1.3.0-dev] — 2026-03-22/23

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
| 0.9.0-dev | 2026-03-21 | Developer UX + Distribution | CLI flags, async SDK stdlib-only, unit tests, `pip install acp-relay`, `acp-relay-client` npm |
| 0.8.0 | 2026-03-21 | Ecosystem | Ed25519 identity, Node.js SDK, compat test suite |
| 0.7.0 | 2026-03-20 | Trust + Discovery | HMAC signing, mDNS LAN discovery, context_id |
| 0.6.0 | 2026-03-20 | Multi-peer + Reliability | Peer registry, error codes, HTTP relay, Python SDK |
| 0.5.0 | 2026-03-19 | Structure | Task state machine, Part model, idempotency, QuerySkill |
| 0.4.0 | 2026-03-18 | Safety | AgentCard v2, max-msg-size, SKILL.md SOP |
| 0.3.0 | 2026-03-18 | Modes | 4 communication modes, explicit lifecycle |
| 0.2.0 | 2026-03-05 | P2P | True P2P relay, Skill guide, zero-code-change |
| 0.1.0 | 2026-03-05 | Foundation | Initial spec, Python SDK, design principles |
