# CHANGELOG

All notable changes to ACP (Agent Communication Protocol) are documented here.

Format: [Semantic Versioning](https://semver.org) — `MAJOR.MINOR.PATCH-status`
Dates: Asia/Shanghai (UTC+8)

---

## [Unreleased] — post-v1.7 docs

### Updated (spec + README)

- **spec/error-codes.md**: explicitly documents `Content-Type: application/json; charset=utf-8` for all responses including errors; rejects `application/problem+json` (RFC 9457) by design; references A2A [#1685](https://github.com/a2aproject/A2A/issues/1685) as motivation (commit `81ffd30`)
- **README vs-A2A table** (commit `81ffd30`):
  - New row: "Error response Content-Type" — ACP uniform vs A2A #1685 ambiguous
  - New row: "Webhook security" — ACP URL-only vs A2A #1681 credentials leaked in plaintext
  - New callout paragraph referencing A2A #1681 + #1685

---

## [1.7.0] — 2026-03-25 20:30

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

## [1.5.1-dev] — 2026-03-24 (updated 2026-03-25 05:25)

### Research (2026-03-25 05:25 — Competitive scan #7)

- **A2A 9-day code freeze continues** (last merge 2026-03-16, TSC governance mode)
- **A2A #1681 (security bug)**: `GetTaskPushNotificationConfig` leaks full credentials in response — ACP has no PushNotification mechanism, zero exposure to this class of vulnerability; strong differentiation point for Show HN
- **A2A #1680 (design gap)**: async cancel semantics unresolved — community debating two approaches for cancel-in-progress tasks; ACP cancel is simple synchronous (`canceled` state returned immediately), no async webhook complexity
- **A2A #1679**: Python tutorial docs require full rewrite for `v1.0-alpha.0` breaking changes; ACP API stable, low doc maintenance burden
- **ANP**: confirmed archived (last update 2026-03-05), no new activity

---

## [1.5.1-dev] — 2026-03-24 (updated 22:47)

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

## [1.5.0-dev] — 2026-03-24
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
| 0.9.0-dev | 2026-03-21 | Developer UX + Distribution | CLI flags, async SDK stdlib-only, unit tests, `pip install acp-relay`, `acp-relay-client` npm |
| 0.8.0 | 2026-03-21 | Ecosystem | Ed25519 identity, Node.js SDK, compat test suite |
| 0.7.0 | 2026-03-20 | Trust + Discovery | HMAC signing, mDNS LAN discovery, context_id |
| 0.6.0 | 2026-03-20 | Multi-peer + Reliability | Peer registry, error codes, HTTP relay, Python SDK |
| 0.5.0 | 2026-03-19 | Structure | Task state machine, Part model, idempotency, QuerySkill |
| 0.4.0 | 2026-03-18 | Safety | AgentCard v2, max-msg-size, SKILL.md SOP |
| 0.3.0 | 2026-03-18 | Modes | 4 communication modes, explicit lifecycle |
| 0.2.0 | 2026-03-05 | P2P | True P2P relay, Skill guide, zero-code-change |
| 0.1.0 | 2026-03-05 | Foundation | Initial spec, Python SDK, design principles |
