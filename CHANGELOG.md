# CHANGELOG

All notable changes to ACP (Agent Communication Protocol) are documented here.

Format: [Semantic Versioning](https://semver.org) — `MAJOR.MINOR.PATCH-status`
Dates: Asia/Shanghai (UTC+8)

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
| 0.9.0-dev | 2026-03-21 | Developer UX + Distribution | CLI flags, async SDK stdlib-only, unit tests, `pip install acp-relay`, `acp-relay-client` npm |
| 0.8.0 | 2026-03-21 | Ecosystem | Ed25519 identity, Node.js SDK, compat test suite |
| 0.7.0 | 2026-03-20 | Trust + Discovery | HMAC signing, mDNS LAN discovery, context_id |
| 0.6.0 | 2026-03-20 | Multi-peer + Reliability | Peer registry, error codes, HTTP relay, Python SDK |
| 0.5.0 | 2026-03-19 | Structure | Task state machine, Part model, idempotency, QuerySkill |
| 0.4.0 | 2026-03-18 | Safety | AgentCard v2, max-msg-size, SKILL.md SOP |
| 0.3.0 | 2026-03-18 | Modes | 4 communication modes, explicit lifecycle |
| 0.2.0 | 2026-03-05 | P2P | True P2P relay, Skill guide, zero-code-change |
| 0.1.0 | 2026-03-05 | Foundation | Initial spec, Python SDK, design principles |
