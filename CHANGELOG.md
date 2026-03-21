# CHANGELOG

All notable changes to ACP (Agent Communication Protocol) are documented here.

Format: [Semantic Versioning](https://semver.org) — `MAJOR.MINOR.PATCH-status`
Dates: Asia/Shanghai (UTC+8)

---

## [0.9.0-dev] — 2026-03-21 (in progress)

### Added
- **CLI `--version`**: prints `acp_relay.py <version>` and exits
- **CLI `--verbose` / `-v`**: switch root logger from INFO to DEBUG at startup
- **CLI `--config <FILE>`**: load defaults from a JSON or YAML config file
  - JSON: stdlib `json.loads`
  - YAML: stdlib-only flat key-value parser (no PyYAML required); bool/int coercion
  - Precedence: `CLI flags > config file > hardcoded defaults`
  - All 12 flags supported; clear error + exit(1) on missing file
- **Example config files**: `relay/examples/config.json`, `config-relay.json`, `config-secure.yaml`
- **`docs/cli-reference.md`**: comprehensive CLI reference (all flags, port layout, 8 usage patterns, config file section)

### Changed
- `AsyncRelayClient` rewritten — **stdlib-only, zero external dependencies** (removed `aiohttp`)
  - Implementation: `asyncio.get_event_loop().run_in_executor()` offloads urllib calls
  - New methods: `connect_peer`, `discover`, `card`, `link`, `get_task`, `continue_task`,
    `cancel_task`, `wait_for_task`, async `stream` generator
  - `send()`: adds `context_id` (v0.7), `task_id`, `create_task`, `sync` mode
  - `query_skills()`: adds `query` free-text + `limit` params
  - `wait_for_peer()`: converted to async
  - 35 new tests in `sdk/python/tests/test_async_relay_client.py` — all passing
- Python SDK `__version__`: `0.6.0` → `0.8.0`
- `acp-research/ROADMAP.md`: full rewrite — all v0.1–v0.8 milestones marked complete

### Planning (P1)
- Server-side `required` field validation in `/message:send` handler
- `CHANGELOG.md` (this file) ← *in progress*
- `docs/integration-guide.md` update for v0.7/v0.8 features

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
| 0.9.0-dev | 2026-03-21 | Developer UX | `--version`/`--verbose`/`--config`, async SDK stdlib-only |
| 0.8.0 | 2026-03-21 | Ecosystem | Ed25519 identity, Node.js SDK, compat test suite |
| 0.7.0 | 2026-03-20 | Trust + Discovery | HMAC signing, mDNS LAN discovery, context_id |
| 0.6.0 | 2026-03-20 | Multi-peer + Reliability | Peer registry, error codes, HTTP relay, Python SDK |
| 0.5.0 | 2026-03-19 | Structure | Task state machine, Part model, idempotency, QuerySkill |
| 0.4.0 | 2026-03-18 | Safety | AgentCard v2, max-msg-size, SKILL.md SOP |
| 0.3.0 | 2026-03-18 | Modes | 4 communication modes, explicit lifecycle |
| 0.2.0 | 2026-03-05 | P2P | True P2P relay, Skill guide, zero-code-change |
| 0.1.0 | 2026-03-05 | Foundation | Initial spec, Python SDK, design principles |
