<div align="center">

<h1>ACP — Agent Communication Protocol</h1>

<p><strong>The missing link between AI Agents.</strong><br>
<em>Send a URL. Get a link. Two agents talk. That's it.</em></p>

<p>
  <a href="https://github.com/Kickflip73/agent-communication-protocol/releases">
    <img src="https://img.shields.io/github/v/release/Kickflip73/agent-communication-protocol?style=flat-square" alt="Release">
  </a>
  <a href="https://github.com/Kickflip73/agent-communication-protocol/actions/workflows/ci.yml">
    <img src="https://github.com/Kickflip73/agent-communication-protocol/actions/workflows/ci.yml/badge.svg" alt="CI">
  </a>
  <a href="https://github.com/Kickflip73/agent-communication-protocol/actions/workflows/codeql.yml">
    <img src="https://github.com/Kickflip73/agent-communication-protocol/actions/workflows/codeql.yml/badge.svg" alt="CodeQL">
  </a>
  <a href="https://kickflip73.github.io/agent-communication-protocol/">
    <img src="https://img.shields.io/badge/docs-github.io-brightgreen?style=flat-square" alt="Docs">
  </a>
  <a href="https://github.com/Kickflip73/agent-communication-protocol/actions/workflows/docker-publish.yml">
    <img src="https://github.com/Kickflip73/agent-communication-protocol/actions/workflows/docker-publish.yml/badge.svg" alt="Docker">
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/github/license/Kickflip73/agent-communication-protocol?style=flat-square" alt="License">
  </a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square" alt="Python">
  <img src="https://img.shields.io/badge/stdlib__only-zero__heavy__deps-orange?style=flat-square" alt="Deps">
  <img src="https://img.shields.io/badge/latency-0.6ms_avg-brightgreen?style=flat-square" alt="Latency">
  <a href="https://api.securityscorecards.dev/projects/github.com/Kickflip73/agent-communication-protocol">
    <img src="https://api.securityscorecards.dev/projects/github.com/Kickflip73/agent-communication-protocol/badge" alt="OpenSSF Scorecard">
  </a>
</p>

<p>
  <strong>English</strong> ·
  <a href="docs/README.zh-CN.md">简体中文</a>
</p>

</div>

> **MCP standardized Agent↔Tool. ACP standardizes Agent↔Agent.**  
> P2P · Zero server required · curl-compatible · works with any LLM framework

<div align="center">
  <img src="demos/two_agent_demo.gif" alt="ACP 2-Agent Bidirectional Demo" width="700">
  <br><em>Alpha ↔ Beta bidirectional P2P communication — no central server, no OAuth</em>
</div>

---

```
$ # Agent A — get your link
$ python3 acp_relay.py --name AgentA
✅ Ready.  Your link: acp://1.2.3.4:7801/tok_xxxxx
           Send this link to any other Agent to connect.

$ # Agent B — connect with one API call
$ curl -X POST http://localhost:7901/peers/connect \
       -d '{"link":"acp://1.2.3.4:7801/tok_xxxxx"}'
{"ok":true,"peer_id":"peer_001"}

$ # Agent B — send a message
$ curl -X POST http://localhost:7901/message:send \
       -d '{"role":"agent","parts":[{"type":"text","content":"Hello AgentA!"}]}'
{"ok":true,"message_id":"msg_abc123","peer_id":"peer_001"}

$ # Agent A — receive in real-time (SSE stream)
$ curl http://localhost:7901/stream
event: acp.message
data: {"from":"AgentB","parts":[{"type":"text","content":"Hello AgentA!"}]}
```

---

## Quick Start

### Option A — AI Agent native (2 steps, zero config)

```
# Step 1: Send this URL to Agent A (any LLM-based agent)
https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/SKILL.md

# Agent A auto-installs, starts, and replies:
# ✅ Ready. Your link: acp://1.2.3.4:7801/tok_xxxxx

# Step 2: Send that acp:// link to Agent B
# Both agents are now directly connected. Done.
```

### Option B — Manual / script

```bash
# Install
pip install websockets

# Start Agent A
python3 relay/acp_relay.py --name AgentA
# → ✅ Ready. Your link: acp://YOUR_IP:7801/tok_xxxxx

# In another terminal — Agent B connects
python3 relay/acp_relay.py --name AgentB \
  --join acp://YOUR_IP:7801/tok_xxxxx
# → ✅ Connected to AgentA
```

### Option C — Docker

```bash
docker run -p 7801:7801 -p 7901:7901 \
  ghcr.io/kickflip73/agent-communication-protocol/acp-relay \
  --name MyAgent
```

---

## Behind NAT / Firewall / Sandbox?

ACP v1.4 includes a three-level automatic connection strategy — **zero config required**:

```
Level 1 — Direct connect       (public IP or same LAN)
   ↓ fails within 3s
Level 2 — UDP hole punch       (both behind NAT — NEW in v1.4)
           DCUtR-style: STUN address discovery → relay signaling → simultaneous probes
           Works with ~70% of real-world NAT types (full-cone, port-restricted)
   ↓ fails
Level 3 — Relay fallback       (symmetric NAT / CGNAT — ~30% of cases)
           Cloudflare Worker relay, stateless, no message storage
```

SSE events reflect the current connection level in real-time: `dcutr_started` → `dcutr_connected` / `relay_fallback`.  
`GET /status` returns `connection_type`: `p2p_direct` | `dcutr_direct` | `relay`.

To force relay mode (e.g., for backward compatibility), add `--relay` on startup to get an `acp+wss://` link.

→ **See [NAT Traversal Guide](docs/nat-traversal.md)**

---

## Routing Topology Declaration (`transport_modes`, v2.4)

Agents declare which routing topologies they support via the `transport_modes` top-level AgentCard field:

| Value | Meaning |
|-------|---------|
| `"p2p"` | Agent supports direct peer-to-peer WebSocket connections |
| `"relay"` | Agent supports relay-mediated delivery (HTTP relay fallback) |

Default: `["p2p", "relay"]` — both topologies supported; absent means the same.

```bash
# Sandbox / NAT-only agent (relay only)
python3 relay/acp_relay.py --name SandboxAgent --transport-modes relay

# Edge agent with public IP (P2P only, no relay dependency)
python3 relay/acp_relay.py --name EdgeAgent --transport-modes p2p
```

**AgentCard snippet:**
```json
{
  "transport_modes": ["p2p", "relay"],
  "capabilities": {
    "supported_transports": ["http", "ws"]
  }
}
```

> **Distinction:** `transport_modes` declares *routing topology* (which path data takes).
> `capabilities.supported_transports` declares *protocol bindings* (how bytes are framed).
> They are orthogonal — see [spec §5.4](spec/core-v1.0.md).

---

## Architecture

### Handshake (humans only do steps 1 and 2)

```
  Human
    │
    ├─[① Skill URL]──────────────► Agent A
    │                                  │  pip install websockets
    │                                  │  python3 acp_relay.py --name A
    │                                  │  → listens on :7801/:7901
    │◄────────────[② acp://IP:7801/tok_xxx]─┘
    │
    ├─[③ acp://IP:7801/tok_xxx]──► Agent B
    │                                  │  POST /connect {"link":"acp://..."}
    │                                  │
    │          ┌────────── WebSocket Handshake ──────────┐
    │          │  B → A : connect(tok_xxx)               │
    │          │  A → B : AgentCard exchange             │
    │          │  A, B  : connected ✅                   │
    │          └──────────────────────────────────────────┘
    │
   done                ↕ P2P messages flow directly
```

### P2P Direct Mode (default)

```
  Machine A                                          Machine B
┌─────────────────────────────┐    ┌─────────────────────────────┐
│  ┌─────────────────────┐    │    │    ┌─────────────────────┐  │
│  │    Host App A       │    │    │    │    Host App B       │  │
│  │  (LLM / Script)     │    │    │    │  (LLM / Script)     │  │
│  └──────────┬──────────┘    │    │    └──────────┬──────────┘  │
│             │ HTTP          │    │               │ HTTP         │
│  ┌──────────▼──────────┐    │    │    ┌──────────▼──────────┐  │
│  │   acp_relay.py      │    │    │    │   acp_relay.py      │  │
│  │  :7901  HTTP API    │◄───┼────┼────┤  POST /message:send │  │
│  │  :7901/stream (SSE) │────┼────┼───►│  GET /stream (SSE)  │  │
│  │  :7801  WebSocket   │◄═══╪════╪═══►│  :7801  WebSocket   │  │
│  └─────────────────────┘    │    │    └─────────────────────┘  │
└─────────────────────────────┘    └─────────────────────────────┘
                         Internet / LAN (no relay server)
```

| Channel | Port | Direction | Purpose |
|---------|------|-----------|---------|
| **WebSocket** | `:7801` | Agent ↔ Agent | P2P data channel, direct peer-to-peer |
| **HTTP API** | `:7901` | Host App → Agent | Send messages, manage tasks, query status |
| **SSE** | `:7901/stream` | Agent → Host App | Real-time push of incoming messages |

**Host app integration (3 lines):**

```python
# Send a message to the remote agent
requests.post("http://localhost:7901/message:send",
              json={"role":"agent","parts":[{"type":"text","content":"Hello"}]})

# Listen for incoming messages in real-time (SSE long-poll)
for event in sseclient.SSEClient("http://localhost:7901/stream"):
    print(event.data)   # {"type":"message","from":"AgentB",...}
```

### Full Connection Strategy (v1.4 — automatic, zero user config)

```
┌────────────────────────────────────────────────────────────────┐
│             Three-Level Connection Strategy                    │
│                                                                │
│  Level 1 — Direct Connect (best)                               │
│  ┌──────────┐                          ┌──────────┐            │
│  │  Agent A │◄═══════ WS direct ══════►│  Agent B │            │
│  └──────────┘    (public IP / LAN)     └──────────┘            │
│                                                                │
│  Level 2 — UDP Hole Punch (v1.4, both behind NAT)              │
│  ┌──────────┐   ┌─────────────┐        ┌──────────┐            │
│  │  Agent A │──►│  Signaling  │◄───────│  Agent B │            │
│  │  (NAT)   │   │ (addr exch) │        │  (NAT)   │            │
│  └──────────┘   └─────────────┘        └──────────┘            │
│       │          exits after                 │                  │
│       └──────────── WS direct ──────────────┘                  │
│                    (true P2P after punch)                       │
│                                                                │
│  Level 3 — Relay Fallback (~30% symmetric NAT cases)           │
│  ┌──────────┐   ┌─────────────┐        ┌──────────┐            │
│  │  Agent A │◄─►│    Relay    │◄──────►│  Agent B │            │
│  └──────────┘   │ (stateless) │        └──────────┘            │
│                 └─────────────┘                                │
│                  frames only, no message storage               │
└────────────────────────────────────────────────────────────────┘
```

> **Signaling server** does one-time address exchange only (TTL 30s), forwards zero message frames.  
> **Relay** is the last resort, not the main path — only triggered by symmetric NAT / CGNAT.

---

## Why ACP

| | A2A (Google) | ACP |
|---|---|---|
| **Setup** | OAuth 2.0 + agent registry + push endpoint | One URL |
| **Server required** | Yes (HTTPS endpoint you must host) | **No** |
| **Framework lock-in** | Yes | **Any agent, any language** |
| **NAT / firewall** | You figure it out | **Auto: direct → hole-punch → relay** |
| **Message latency** | Depends on your infra | **0.6ms avg (P99 2.8ms)** |
| **Min dependencies** | Heavy SDK | **`pip install websockets`** |
| **Identity** | OAuth tokens | **Ed25519 + did:acp: DID + CA hybrid (v1.5)** |
| **Availability signaling** | ❌ (open issue #1667) | **✅ `availability` field (v1.2)** |
| **Agent identity proof** | ❌ (open issue #1672, 425 comments, still no spec-level resolution) | **✅ `did:acp:` + Ed25519 AgentCard self-sig (v1.8) + mutual auto-verify at handshake (v1.9) + offline pubkey discovery `GET /identity/pubkey-discovery` (v2.33) + structured per-peer trust score `GET /peers/<id>/trust` (v2.34)** |
| **Mutual identity at handshake** | ❌ No protocol-level concept | **✅ Auto-verified on connect — both sides confirmed in one round-trip (v1.9)** |
| **Agent unique identifier** | 🔄 PR#1079: random UUID (unverifiable ownership) | **✅ `did:acp:<base58url(pubkey)>` — cryptographic fingerprint, ownership provable** |
| **LAN agent discovery** | ❌ No spec-level discovery mechanism | **✅ `GET /peers/discover` — TCP port-scan + AgentCard fingerprint, no mDNS opt-in required (v2.1-alpha)** |
| **Offline message delivery** | ❌ No offline buffering — messages dropped silently if peer is offline | **✅ Auto-queue on disconnect, auto-flush on reconnect — `GET /offline-queue` (v2.0-alpha); `--persist-queue` SQLite durable persistence across restarts (v2.97)** |
| **Async task queue** | ❌ #1667 offline-first task handling still in discussion — no spec endpoint | **✅ `POST /tasks/queue` — 202 Accepted, `task_id + poll_url + sse_url + queued_at`; `GET /tasks/queue` queue status; `capabilities.async_task_queue` (v2.98)** |
| **Cancel task semantics** | ❌ Undefined — `CancelTaskRequest` missing, async cancel state disputed (#1680, #1684) | **✅ Synchronous + idempotent: 200 on success, 409 `ERR_TASK_NOT_CANCELABLE` on terminal state (v1.5.2 §10)** |
| **Error response Content-Type** | ❌ Undefined — `application/json` vs `application/problem+json` contradicted within spec (#1685) | **✅ Always `application/json; charset=utf-8` — one content type for all responses, zero ambiguity** |
| **Webhook security** | ❌ Push notification config API returns credentials in plaintext (#1681, security bug) | **✅ Webhooks store URL only — no credentials, no leakage surface** |
| **AgentCard limitations field** | ❌ Open proposal — issue #1694 (2026-03-27), not yet merged | **✅ `limitations: LimitationObject[]` — structured format (v2.20): `{kind, code, message, permanent}`; stable/runtime split; 6 kind types; `--limitations-json` CLI; `capabilities.limitations_structured=true`** |
| **Skills / capability discovery** | ❌ No structured skill discovery in spec | **✅ `GET /skills` — Skills-lite 能力发现（轻量，无 JSON Schema 开销）；AgentCard `skills[]` 结构化对象数组（v2.10.0）；每个 skill 含 `input_modes`/`output_modes`/`examples` 字段（v2.11.0）；`/skills/query` 支持 `constraints.input_mode` 按输入模式过滤（v2.11.0）；skill 级别 `constraints: {max_file_size_bytes, concurrent_tasks, context_window}` — 三维能力边界声明（v2.26）；skill 级别 `limitations: LimitationObject[]` — 细粒度能力边界，`?has_limitation=<kind\|code>` 过滤（v2.28）；`GET /skills/<id>/status` 运行时可用性探测（v2.29）；`PATCH /skills/<id>/limitations` 运行时动态更新 skill limitations（v2.31）；领先 A2A PR#1655 + #1694** |
| **Agent capability boundaries** | ❌ `limitations[]` open proposal (issue #1694, not merged) | **✅ `limitations: LimitationObject[]` — 结构化能力边界（v2.20）：stable/runtime 分离，kind 分类，机器可路由** |
| **Trust signals / provenance** | ❌ `trust.signals[]` open spec proposal (#1628, still in discussion — no merged schema) | **✅ `trust.signals[]` — 4-type structured trust evidence in AgentCard (v2.14): `self_attested` / `third_party_vouched` / `onchain_credentials` / `behavioral`; Ed25519-signed; A2A-compatible schema** |
| **Multi-turn conversation context** | ❌ `contextId` still proposal-stage — no query API in spec | **✅ `GET /context/<id>/messages` — query full conversation history by `context_id` (v2.15); supports `since_seq` incremental fetch, `sort=asc\|desc`, `limit`; outbound + inbound messages unified** |
| **Availability scheduling (CRON)** | ❌ #1667 heartbeat agent support still in discussion — no schedule field | **✅ `availability.schedule` CRON expression + `availability.timezone`; `GET /availability`; `POST /availability/heartbeat`; `capabilities.availability_schedule` (v2.17)** |
| **JWKS key discovery** | ❌ IS#1628 proposes JWKS-format key discovery — still proposal stage, no merged implementation | **✅ `GET /.well-known/jwks.json` — RFC 7517 JWK Set; `kty=OKP`, `crv=Ed25519`, `alg=EdDSA` per RFC 8037; discoverable via `endpoints.jwks` + `trust.signals[type=jwks].jwks_uri`; `capabilities.trust_jwks: true` (v2.18)** |
| **Protocol bindings declaration** | ✅ §5.8 Custom Protocol Bindings — `protocol_bindings[]` URI array in AgentCard (merged 2026-04-07) | **✅ `protocol_bindings[]` top-level AgentCard array + `GET /protocol-binding` endpoint + `urn:acp:binding:p2p-relay/v1` URI; backward-compat singular `protocol_binding` retained (v2.84)** |
| **Protocol compatibility matrix** | ❌ No cross-protocol compatibility declaration | **✅ `GET /protocol-binding/compatibility` — 6-entry matrix: websocket (native), http/sse (native), a2a (partial, §2/§3/§5.8 aligned), anp (partial), mcp (none), grpc (none); `aligned_sections[]` per entry (v2.85)** |
| **Ed25519 identity setup** | ❌ #1672: still open, no default in spec | **✅ Ed25519 keypair auto-generated by default — zero config, `~/.acp/identity.json`; `capabilities.identity_default=True`; `--no-identity` to disable (v2.85)** |
| **Governance metadata** | ❌ Issue #1717 opened 2026-04-09 — proposal stage (Microsoft agent-governance-toolkit team); no merged schema | **✅ `governance_metadata` in AgentCard (v2.85): `governance_score`, `policies[]`, `attestations[]`; `PATCH /policy-compliance` batch-updates compliance standards (v2.87); `capabilities.governance_metadata=true`; fully testable without external registry** |
| **Skill-level authorization tiers** | ❌ RFC #1716 opened 2026-04-09 — no merged enforcement mechanism; SecurityRequirement only covers auth, not authz | **✅ `authorization_tier` (T0–T3) per-skill (v2.50); `capability_token` fine-grained delegated invocation rights (v2.74); `human_confirmation_required` for irreversible T3 skills (v2.51); `effective_tier` 5-factor dynamic computation (v2.76): tier_rule + depth_floor + reputation_adj + wtrmrk_adj + bilateral_ir_adj** |
| **Bilateral signed interaction records** | ❌ Issue [#1718](https://github.com/google/A2A/issues/1718) opened 2026-04-05 — proposal stage (viftode4); identifies that unilateral relay-signed records can be forged by a malicious relay | **✅ `bilateral_ir_log` (v2.59–v2.76): caller + relay co-sign each record → non-repudiable by either party; SHA-256 hash chain for tamper-evidence; `sequence_a` for ordering; Merkle root attestation (v2.72); AgentCard `trust.signals[type=bilateral_ir]` (v2.68); `GET /ir/test-vectors` for cross-impl verification (v2.64); `POST /ir/import-evidence` (v2.65); feeds into `effective_tier` as `bilateral_ir_adj` — 5th factor (v2.76); 29+ passing tests** |

> **Governance metadata (v2.85/v2.87)** — A2A [#1717](https://github.com/google/A2A/issues/1717) (2026-04-09, Microsoft governance team) proposes adding `trust_score`, `capability_manifest`, and `policy_compliance` to Agent Cards. ACP already ships all three: `governance_metadata.governance_score`, `governance_metadata.policies[]`, and `PATCH /policy-compliance` (v2.87). No proposal, no committee — working code with tests.

> **Skill authorization tiers (v2.50+)** — A2A [#1716](https://github.com/google/A2A/issues/1716) (2026-04-09, RFC stage) identifies the same gap ACP solved in v2.50: `SecurityRequirement` authenticates callers but cannot restrict *which skills* they invoke or *with what parameters*. ACP's `authorization_tier` (T0–T3) + `capability_token` + `human_confirmation_required` + 5-factor `effective_tier` provides complete skill-boundary authorization — with 60+ passing tests.

> **Bilateral signed interaction records (v2.59+)** — A2A [#1718](https://github.com/google/A2A/issues/1718) (2026-04-05, viftode4) correctly identifies that unilateral relay-signed records can be forged: if the relay lies, the record is worthless. ACP v2.61 solved this with bilateral co-signing: caller and relay both sign the same canonical payload. A record signed by both parties is non-repudiable by either. Chain of records (SHA-256 `previous_hash`) is tamper-evident without trusting either party. Bilateral records feed into `effective_tier` as the `bilateral_ir_adj` factor (v2.76) — a corpus of mutual interaction history can *lower* the authorization floor for a trusted, well-known peer. `GET /ir/test-vectors` (v2.64) enables cross-implementation verification. 29+ passing tests.

> A2A [#1672](https://github.com/a2aproject/A2A/issues/1672) has **425 comments** (as of 2026-04-12) and still no implementation merged into spec. The leading proposal requires a central CA (`getagentid.dev`) — single point of failure, registration bottleneck, privacy leak. ACP v2.85 ships Ed25519 identity **default-on**: self-generated keypair, no CA, no registration, works offline and air-gapped. ACP v2.93 publishes **[ACP-RFC-004](docs/rfc/identity-without-ca.md)** — a full comparison (9 dimensions) and multi-provider DID approach, responding directly to the `aeoess` three-layer model articulated in A2A [#1712](https://github.com/a2aproject/A2A/issues/1712).

> A2A [#1680](https://github.com/a2aproject/A2A/issues/1680) & [#1684](https://github.com/a2aproject/A2A/issues/1684) — community debate: when cancel can't complete immediately, return `WORKING` or new `CANCELING` state? `CancelTaskRequest` schema is missing from spec. ACP v1.5.2 resolves all of this with synchronous, idempotent cancel semantics.

> A2A [#1685](https://github.com/a2aproject/A2A/issues/1685) — error response Content-Type undefined in spec (PR #1600 removed `application/problem+json` without replacing it). A2A [#1681](https://github.com/a2aproject/A2A/issues/1681) — push notification config API exposes credentials in plaintext. ACP avoids both by design: uniform `application/json` + URL-only webhooks.

> **Offline delivery (v2.0-alpha / v2.97 / v2.98 / v3.8)** — A2A has no spec-level offline buffering. If you send a message while your peer is restarting, it's gone. ACP automatically queues the message on your local relay (up to 100 per peer), and flushes the queue the moment the peer reconnects. `GET /offline-queue` shows what's waiting. **v2.97 `--persist-queue`** adds SQLite-backed durability: messages survive relay restarts, solving the heartbeat-agent offline window (A2A #1667). **v2.98 `POST /tasks/queue`** completes the offline-first story for task workloads: enqueue a task with 202 Accepted, pick up results later via poll or SSE — no blocking, no dropped work. **v3.8 `--heartbeat-agent` + `GET /offline-queue/summary`** closes the loop: cron-style agents wake up, call the lightweight summary endpoint (`has_messages`, `total_queued`, `oldest_queued_at`) for a fast pre-check before heavier processing, then stamp `POST /availability/heartbeat` when done.

> **AgentCard limitations (v2.7 → v2.28)** — A2A [#1694](https://github.com/a2aproject/A2A/issues/1694) (opened 2026-03-27) proposes adding a `limitations` field. ACP v2.7 shipped working code the same day; ACP v2.20 upgrades to structured `LimitationObject[]` with stable/runtime split (`permanent: bool`), 6 kind types (`capability|modality|scale|domain|access|other`), machine-readable codes. **ACP v2.28 extends this to per-skill granularity**: every skill object now carries its own `limitations[]`, enabling orchestrators to ask "does skill X support audio?" rather than just "does this agent support audio?". `GET /skills?has_limitation=modality` returns only skills with modality-kind limitations; `POST /skills/query` response includes `skill_limitations_declared[]` for pre-flight routing decisions. Old clients ignore the optional field — fully backward-compatible. A2A #1694 is still an open proposal with no merged implementation.

> **LAN discovery (v2.1-alpha)** — A2A has no spec-level mechanism for agents to find each other on a local network. ACP `GET /peers/discover` scans your /24 subnet in 1–3 seconds: 64-thread TCP probe on common ACP ports, then `/.well-known/acp.json` fingerprint on every open port. Returns a list of ACP agents with their `acp://` links — ready to connect. No mDNS required on the target side. Find any ACP relay on your LAN, even ones you don't control.

> **Multi-relay federation (v3.10)** — A2A has no cross-relay message routing mechanism. When agents are on different relay instances (different orgs, different networks), there's no standard way to deliver messages between them. ACP v3.10 adds `POST /federation` to connect remote relays as peers, and `POST /federation/route` to route messages to peers on remote relays — all in ~120 lines of stdlib Python. Federated messages fall back to offline-queue when the target peer is offline, composable with `--persist-queue` for durable cross-relay delivery. `capabilities.federation: true` lets orchestrators discover federation-capable relays via AgentCard.

### Numbers

- **0.6ms** avg send latency · **2.8ms** P99
- **1,100+ req/s** sequential throughput · **1,200+ req/s** concurrent (10 threads)
- **< 50ms** SSE push latency (threading.Event, not polling)
- **300+ release CI checks PASS** (certification · integration · reliable messaging · hybrid identity · Python/Node/Go/Rust SDKs · docs)
- **190+ commits** · **3,300+ lines** · **zero known P0/P1 bugs**

---

## API Reference

| Action | Method | Path |
|--------|--------|------|
| Get your link | GET | `/link` |
| Connect to a peer | POST | `/peers/connect` `{"link":"acp://..."}` |
| Send a message | POST | `/message:send` `{"role":"agent","parts":[...]}` |
| Receive in real-time | GET | `/stream` (SSE) |
| Poll inbox (offline) | GET | `/recv` |
| Query status | GET | `/status` |
| List peers | GET | `/peers` |
| AgentCard | GET | `/.well-known/acp.json` |
| Update availability | PATCH | `/.well-known/acp.json` |
| Create task | POST | `/tasks` |
| Update task | POST | `/tasks/{id}:update` |
| Cancel task | POST | `/tasks/{id}:cancel` |
| Submit task evidence | POST | `/tasks/{id}/evidence` |
| List task evidence | GET | `/tasks/{id}/evidence` |
| Get latest evidence | GET | `/tasks/{id}/evidence/latest` |
| Stream task evidence (SSE) | GET | `/tasks/{id}/evidence-stream` |
| Heartbeat report | POST | `/availability/heartbeat` |
| Query availability | GET | `/availability` |
| List federation relays | GET | `/federation` |
| Add federation relay | POST | `/federation` `{"link":"acp://..."}` |
| Route to remote relay | POST | `/federation/route` `{"relay_id":"...","target_peer_id":"..."}` |
| Subscribe to topic | POST | `/peers/subscribe/{topic}` |
| Unsubscribe from topic | POST | `/peers/unsubscribe/{topic}` |
| Publish to topic | POST | `/peers/broadcast/{topic}` |
| List active topics | GET | `/peers/topics` |
| Poll queue summary | GET | `/offline-queue/summary` |
| Enqueue async task | POST | `/tasks/queue` `{"role":"agent","payload":{...}}` |
| Register worker | POST | `/tasks/queue/worker` `{"callback_url":"http://...","peer_id":"...","skill_id":"..."}` |
| List workers | GET | `/tasks/queue/workers` |
| Deregister worker | DELETE | `/tasks/queue/worker/{id}` |

HTTP default port: `7901` · WebSocket port: `7801`

**AgentCard response example** (`GET /.well-known/acp.json`):
```json
{
  "name": "MyAgent",
  "acp_version": "2.4.0",
  "transport_modes": ["p2p", "relay"],
  "capabilities": {
    "streaming": true,
    "supported_transports": ["http", "ws"]
  }
}
```

> `transport_modes` (v2.4+): declares routing topology — `"p2p"` (direct) and/or `"relay"` (relay-mediated). Default: `["p2p", "relay"]`. Distinct from `capabilities.supported_transports` which declares *protocol bindings*.

---

## Optional Features

| Feature | Flag | Notes |
|---------|------|-------|
| Public relay (NAT fallback) | `--relay` | Returns `acp+wss://` link |
| HMAC message signing | `--secret <key>` | Shared secret, no extra deps |
| Ed25519 identity | _(default, auto-generated)_ | `pip install cryptography`; use `--no-identity` to disable |
| mDNS LAN discovery | `--advertise-mdns` | No zeroconf library needed |
| Docker | `docker pull ghcr.io/kickflip73/agent-communication-protocol/acp-relay` | Multi-arch, GHCR CI |
| `evidence_stream` | _(always on)_ | 任务证据 SSE 实时订阅（v2.82）：`GET /tasks/{id}/evidence-stream`，支持 replay + 多订阅者 + keepalive |

---

## Task State Machine

Track cross-agent task progress:

```
submitted → working → completed ✅
                    → failed    ❌
                    → input_required → working (waiting for more input)
```

API: `POST /tasks` to create · `POST /tasks/{id}:update` to update status.

---

## Heartbeat / Cron Agents

ACP natively supports **offline agents** (cron-style agents that wake up periodically), no persistent connection required.

### How it works

```
Cron Agent wakes up every 5 minutes:
1. Start acp_relay.py (get an acp:// link)
2. PATCH /.well-known/acp.json to broadcast availability
3. GET /recv to drain queued messages, process in batch
4. POST /message:send to reply
5. Exit (relay shuts down cleanly)
```

```python
# Python — cron agent template
import subprocess, time, requests

relay = subprocess.Popen(["python3", "relay/acp_relay.py", "--name", "MyCronAgent"])
time.sleep(1)   # wait for startup

BASE = "http://localhost:7901"

# Broadcast availability
requests.patch(f"{BASE}/.well-known/acp.json", json={
    "availability": {
        "mode": "cron",
        "last_active_at": "2026-03-24T10:00:00Z",
        "next_active_at": "2026-03-24T10:05:00Z",
        "task_latency_max_seconds": 300,
    }
})

# Drain and process queued messages
msgs = requests.get(f"{BASE}/recv?limit=100").json()["messages"]
for m in msgs:
    text = m["parts"][0]["content"]
    requests.post(f"{BASE}/message:send",
                  json={"role":"agent","parts":[{"type":"text","content":f"Processed: {text}"}]})

relay.terminate()
```

> **Why it matters:** A2A [#1667](https://github.com/a2aproject/A2A/issues/1667) is still discussing heartbeat agent support as a proposal. ACP `/recv` solves this natively — available today.

---

## Agent Identity (v2.85)

ACP auto-generates an Ed25519 keypair on first run — **no flags required**. The keypair is saved to `~/.acp/identity.json` and reused across restarts.

| Mode | Flag | `capabilities.identity` | Notes |
|------|------|--------------------------|-------|
| **Self-sovereign (default)** | _(none)_ | `"ed25519"` | Auto-generated keypair; `capabilities.identity_default=True` (v2.85) |
| Self-sovereign (custom path) | `--identity <path>` | `"ed25519"` | Load/generate keypair at custom path |
| **Hybrid** | `--ca-cert` | `"ed25519+ca"` | Self-sovereign + CA-issued certificate |
| Disabled | `--no-identity` | `"none"` | For embedded/testing scenarios only (v2.85) |

```bash
# Default — Ed25519 auto-generated, zero config (v2.85+)
python3 relay/acp_relay.py --name MyAgent

# Custom keypair path (backward compat)
python3 relay/acp_relay.py --name MyAgent --identity ~/.acp/my-agent.json

# Hybrid identity (v1.5) — CA cert file
python3 relay/acp_relay.py --name MyAgent --ca-cert /path/to/agent.crt

# Disable identity (testing/embedded)
python3 relay/acp_relay.py --name MyAgent --no-identity
```

**AgentCard example (hybrid mode):**
```json
{
  "identity": {
    "scheme":     "ed25519+ca",
    "public_key": "<base64url-encoded Ed25519 public key>",
    "did":        "did:acp:<base64url(pubkey)>",
    "ca_cert":    "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----"
  },
  "capabilities": {
    "identity": "ed25519+ca"
  }
}
```

**Verification strategy** (verifier's choice):
- Trust only `did:acp:` — verify Ed25519 signature, ignore `ca_cert`
- Trust only CA — verify certificate chain, ignore DID
- Require both — highest security
- Accept either — highest interoperability

> **Why it matters:** A2A [#1672](https://github.com/a2aproject/A2A/issues/1672) (44 comments, still in discussion) is converging on the same hybrid model. ACP v1.5 ships it today.

---

## SDKs

| Language | Path | Notes |
|----------|------|-------|
| **Python** | `sdk/python/` | `pip install acp-client` · `RelayClient`, `AsyncRelayClient`; LangChain adapter: `pip install "acp-client[langchain]"` (v1.8.0+) |
| **Node.js** | `sdk/node/` | Zero external deps, TypeScript types included |
| **Go** | `sdk/go/` | Zero external deps, Go 1.21+ |
| **Rust** | `sdk/rust/` | v1.3, reqwest + serde |
| **Java** | `sdk/java/` | Zero external deps, JDK 11+, Spring Boot example included |

---

## What's New

| Version | Highlights |
|---------|------------|
| **v3.13** | Governance Audit Endpoint — `GET /governance/audit` with IR structured query + `?peer_id=`/`?task_id=`/`?since=` filters (A2A #1717 `auditEndpoint` first implementation) |
| **v3.12** | Governance Compliance Report — `GET/POST /governance/compliance` + `compliance_report` / `last_verified_at` in AgentCard.governance |
| **v3.11** | Async Task Queue Workers — register `callback_url` workers, auto-dispatch on enqueue, `DELETE /tasks/queue/worker/{id}` |

→ [Full Changelog](CHANGELOG.md)

---

## Repository Structure

```
agent-communication-protocol/
├── SKILL.md              ← Send this URL to any agent to onboard
├── relay/
│   └── acp_relay.py      ← Core daemon (single file, stdlib-first)
├── spec/                 ← Protocol specification documents
├── sdk/                  ← Python / Node.js / Go / Rust / Java SDKs
├── tests/                ← Compatibility + integration test suites
├── docs/                 ← Chinese docs, conformance guide, blog drafts
└── acp-research/         ← Competitive intelligence, ROADMAP
```

---

## Show HN

> **ACP — P2P protocol for AI Agents to talk directly, no server required**

**The problem:** Most multi-agent setups require a central orchestration server. When Agent A wants to message Agent B, you build infrastructure. When Agent B is behind NAT, you give up and poll.

**What ACP does:** Agent A runs one command, gets an `acp://` link, sends it to Agent B. Agent B pastes the link. They're connected P2P — through NAT, firewalls, sandboxes — in under 5 seconds. No server. No registration. No OAuth dance.

```bash
# Agent A — anywhere in the world
python3 acp_relay.py --name AgentA
# ✅ Ready. Your link: acp://1.2.3.4:7801/tok_xxxxx

# Agent B — behind a corporate firewall / in a cloud sandbox
curl -X POST http://localhost:7901/peers/connect \
     -d '{"link":"acp://1.2.3.4:7801/tok_xxxxx"}'
# ✅ Connected. {"peer_id":"peer_001"}
```

**How it works:** Three-level auto-fallback — direct WebSocket → UDP hole punch (DCUtR) → relay. Your agents don't know or care which level they're on. The right level is chosen in < 3s.

**ACP vs A2A (Google's protocol):** A2A requires OAuth 2.0, an HTTPS endpoint you must host, and an agent registry. ACP requires `pip install websockets`. A2A is great for enterprise platforms; ACP is for individuals, sandboxed agents, and fast prototyping.

**Status:** Single-file Python daemon, release smoke suite passing, Apache 2.0. Built in public over ~190 commits. Would love feedback on the P2P design and the `acp://` URI scheme.

---

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md).

- Bug reports & feature requests → [GitHub Issues](https://github.com/Kickflip73/agent-communication-protocol/issues)
- Protocol design discussion → [GitHub Discussions](https://github.com/Kickflip73/agent-communication-protocol/discussions)
- Support options → [SUPPORT.md](SUPPORT.md)
- Security disclosures → [SECURITY.md](SECURITY.md)

---

## License

[Apache License 2.0](LICENSE)

---

<div align="center">
<sub>MCP standardizes Agent↔Tool. ACP standardizes Agent↔Agent. P2P · Zero server · curl-compatible.</sub>
</div>
