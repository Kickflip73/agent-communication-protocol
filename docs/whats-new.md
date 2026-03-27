# What's New in ACP — Last 7 Days

> Last updated: 2026-03-28
> For the full history see [CHANGELOG.md](../CHANGELOG.md)

---

## 2026-03-28

### AgentCard `limitations` Field — Three-Part Capability Boundary (v2.7.0)

ACP v2.7 introduces the **`limitations: string[]`** field, completing a **three-part capability boundary declaration** in AgentCard:

| Field | Declares |
|-------|----------|
| `capabilities` | What the agent **CAN do** (feature flags) |
| `availability` | **When** the agent is active (scheduling/cron) |
| **`limitations`** ✨ | What the agent **CANNOT do** (hard constraints) |

**Usage:**

```bash
# Declare a sandboxed agent that cannot access files or the internet
python3 acp_relay.py --name "SandboxAgent" \
  --limitations "no_file_access,no_internet,no_shell"
```

**AgentCard response** (`GET /.well-known/acp.json`):
```json
{
  "name": "SandboxAgent",
  "acp_version": "2.7.0",
  "limitations": ["no_file_access", "no_internet", "no_shell"],
  "capabilities": { "streaming": true, ... },
  "availability": { "mode": "persistent" }
}
```

**Design rationale:**

`capabilities` (positive flags) and `limitations` (explicit cannot-dos) are **complementary**, not redundant:
- A streaming-capable agent (`capabilities.streaming: true`) may still have `limitations: ["no_internet"]`
- The absence of a capability flag does NOT imply a limitation — `limitations` is explicit opt-in

**Backward compatibility:** The field is optional (`default: []`). Old clients that don't recognize it simply ignore it per standard JSON forward-compatibility rules.

**vs. A2A #1694:** A2A GitHub issue #1694 (opened 2026-03-27) proposes the same concept for A2A AgentCard. **ACP ships working code on day one** — ACP v2.7 is live today while A2A #1694 remains an open proposal.

---

## 2026-03-27

### `transport_modes` Routing Topology Declaration (v2.4.0)

ACP agents can now **declare their routing topology** in the AgentCard via the new top-level `transport_modes` field.

**Key distinction:** `transport_modes` (routing topology) is orthogonal to `capabilities.supported_transports` (protocol bindings):
- `supported_transports`: declares *protocol bindings* — HTTP/1.1, WebSocket, HTTP/2
- `transport_modes`: declares *routing topology* — direct P2P, relay-mediated

```bash
# Relay-only sandbox agent
python3 acp_relay.py --name "SandboxAgent" --transport-modes relay

# P2P-only edge agent (public IP)
python3 acp_relay.py --name "EdgeAgent" --transport-modes p2p
```

**AgentCard response** (`GET /.well-known/acp.json`):
```json
{
  "name": "SandboxAgent",
  "acp_version": "2.4.0",
  "transport_modes": ["relay"],
  "capabilities": {
    "supported_transports": ["http", "ws"]
  }
}
```

Default is `["p2p", "relay"]` — both topologies available, peer's choice. Absent means the same. Receivers MUST treat the field as advisory; unknown values MUST be ignored.

→ See **spec §5.4** and `--transport-modes` in [CLI Reference](cli-reference.md)

---

### Task List Queries — `GET /tasks` with Filtering + Pagination (v2.2.0)

ACP agents can now **query all tasks** with rich filtering and offset-based pagination — no more fetching all tasks and filtering client-side.

```bash
# List all tasks (newest first, page 1)
curl "http://localhost:7901/tasks?offset=0&limit=20"

# Filter by status
curl "http://localhost:7901/tasks?status=working"

# Filter by peer (works for both top-level and payload.peer_id)
curl "http://localhost:7901/tasks?peer_id=peer_001"

# Date-range filter (tasks created in the last hour)
curl "http://localhost:7901/tasks?created_after=2026-03-27T04:00:00"

# Pagination — fetch page 2
curl "http://localhost:7901/tasks?limit=10&offset=10"

# Sort oldest-first
curl "http://localhost:7901/tasks?sort=asc"
```

**Response shape:**

```json
{
  "tasks": [
    {
      "id": "task_abc123",
      "status": "working",
      "peer_id": "peer_001",
      "created_at": "2026-03-27T05:10:00",
      "updated_at": "2026-03-27T05:11:00"
    }
  ],
  "total": 42,
  "has_more": true,
  "next_offset": 20
}
```

**All query parameters:**

| Parameter | Default | Max | Description |
|---|---|---|---|
| `status` | — | — | Filter: `submitted`/`working`/`completed`/`failed`/`canceled`/`input_required` |
| `peer_id` | — | — | Filter by peer (checks `task.peer_id` and `task.payload.peer_id`) |
| `created_after` | — | — | ISO 8601 timestamp lower bound |
| `updated_after` | — | — | ISO 8601 timestamp lower bound (updated_at) |
| `sort` | `desc` | — | `asc` (oldest first) or `desc` (newest first) |
| `limit` | `20` | `100` | Page size |
| `offset` | `0` | — | Page start (activates offset mode) |

**Backward compatibility:**
- `?state=<s>` still accepted (legacy alias for `status`)
- `?cursor=<task_id>` keyset pagination still works when `offset` param is absent
- Legacy `?sort=created_asc` / `created_desc` still accepted

**Error handling:**
- Unknown `status` value → `400 ERR_INVALID_REQUEST` with valid values listed

---

---

## 2026-03-26

### LAN Port-Scan Discovery — Find ACP Agents Without mDNS (v2.1-alpha)

ACP agents can now **automatically discover other ACP relays on the same LAN** by scanning common ports — no `--advertise-mdns` flag required on either side.

```bash
# Discover all ACP agents on your local network:
curl http://localhost:7901/peers/discover
# → {
#     "found": [
#       {
#         "host": "192.168.1.42",
#         "http_port": 7901,
#         "name": "Agent-Alice",
#         "link": "acp://192.168.1.42:7801/tok_abc123",
#         "latency_ms": 3.2
#       }
#     ],
#     "scanned_hosts": 253,
#     "scanned_ports": 1518,
#     "subnet": "192.168.1",
#     "duration_ms": 1340,
#     "total_found": 1
#   }

# Optional: narrow the scan
curl "http://localhost:7901/peers/discover?subnet=10.0.1&ports=7901,7902&workers=32"
```

How it works:
- Auto-detects local /24 subnet from the machine's primary LAN IP
- 64-thread TCP connect probe across all hosts on common ACP ports (7901–7931)
- Open port → immediate `GET /.well-known/acp.json` fingerprint to confirm ACP relay
- Merges mDNS cache (from `--advertise-mdns`) automatically — deduped by host
- Skips self to avoid self-discovery; per-host dedup across multiple ports
- Typical scan time: **1–3 seconds** for a /24 subnet

New endpoints/fields:
- `GET /peers/discover` — returns scan results with `acp://` links ready to connect
- `capabilities.lan_port_scan: true` — advertised in AgentCard
- `endpoints.peers_discover: "/peers/discover"` — discoverable via AgentCard

**Why it matters**: mDNS (`--advertise-mdns`) requires opt-in from every agent. Port-scan discovery works against *any* ACP relay regardless of its startup flags — including agents that were started before you, or agents you don't control. Find them first, connect second.

---

### Offline Delivery Queue — Messages Survive Disconnects (v2.0-alpha)

ACP agents now **buffer outbound messages when the peer is offline, and auto-deliver them the moment the peer reconnects** — zero extra code by the caller.

```bash
# Agent A sends a message — peer (Agent B) is NOT connected yet:
curl -s -X POST http://localhost:7901/message:send \
  -H "Content-Type: application/json" \
  -d '{"role":"user","parts":[{"type":"text","content":"hello, are you there?"}]}'
# → {"ok": false, "error_code": "ERR_NOT_CONNECTED",
#    "error": "No P2P connection — message queued for delivery on reconnect"}

# Inspect the queue:
curl http://localhost:7901/offline-queue
# → {"total_queued": 1, "max_per_peer": 100,
#    "queue": {"default": {"depth": 1,
#      "messages": [{"type": "acp.message", "queued_at": "2026-03-26T10:17Z"}]}}}

# Agent B connects. Queue auto-flushes immediately on handshake:
# 📤 Flushed 1 offline message(s) to peer 'peer_a1b2' on connect
```

How it works:
- `_ws_send()` catches `ConnectionError` → calls `_offline_enqueue(msg, peer_id)`
- Messages stored in per-peer `deque(maxlen=100)` — oldest dropped when full, never blocks
- On peer connect/reconnect, `_offline_flush()` runs automatically in FIFO order
- `_was_queued: true` marker in delivered messages lets the receiver know they arrived buffered
- API contract unchanged — callers still get `503 ERR_NOT_CONNECTED` (drop-in safe)

New endpoints/fields:
- `GET /offline-queue` — inspect buffer `{total_queued, max_per_peer, queue}`
- `capabilities.offline_queue: true` — advertised in AgentCard
- `endpoints.offline_queue: "/offline-queue"` — discoverable via AgentCard

**Why it matters**: A2A has no offline delivery mechanism — if you send a task message while the peer agent is restarting or temporarily offline, the message is simply lost. ACP's offline queue delivers it automatically on reconnect, making short disconnects transparent to the application layer.

---

### Peer AgentCard Auto-Verification at Handshake (v1.9)

ACP agents now **automatically verify each other's identity the moment they connect** — no extra API calls needed.

```bash
# Start both agents with identity
acp-relay --name Alice --identity ~/.acp/alice.json  # host mode
acp-relay --name Bob   --identity ~/.acp/bob.json    # connect to Alice

# After connection, immediately check peer identity:
curl http://localhost:7982/peer/verify
# → {
#     "peer_name": "Alice",
#     "peer_did": "did:acp:FmXk7...",
#     "verified": true,
#     "did_consistent": true,
#     "scheme": "ed25519",
#     "error": null
#   }
```

How it works:
- On connect, each side sends a **signed AgentCard** (via `_send_agent_card`)
- On receipt, `_verify_agent_card()` runs immediately — result stored in memory
- `GET /peer/verify` returns the cached result instantly
- If peer is unsigned (older relay), `verified: false` with descriptive `error` field
- State is cleared automatically on disconnect

New endpoints/fields:
- `GET /peer/verify` — peer's verification result; 404 if no peer connected
- `capabilities.auto_card_verify: true` — advertised in AgentCard
- `endpoints.peer_verify: "/peer/verify"` — discoverable via AgentCard

---

### AgentCard Self-Signature — Cryptographic Identity Verification (v1.8)

ACP agents can now **cryptographically sign their own AgentCard** and any peer can verify it.

```bash
# Start with identity (auto-generates Ed25519 keypair)
acp-relay --name Alice --identity ~/.acp/identity.json

# Alice's AgentCard now includes a self-signature:
# GET /.well-known/acp.json →
# { "self": { ..., "identity": { "card_sig": "base64url...", "did": "did:acp:..." } } }
```

```bash
# Anyone can verify Alice's card — no CA, no registration:
curl -X POST http://alice.local:7901/verify/card \
  -d '{"name": "Alice", "identity": {"card_sig": "...", "public_key": "..."}, ...}'
# → {"valid": true, "did": "did:acp:...", "did_consistent": true}
```

How it works:
- AgentCard is signed with the agent's Ed25519 private key at serve time
- Signature covers canonical JSON (sorted keys, `card_sig` field excluded)
- Any receiver can verify using the `public_key` in `identity` — zero external service
- `did_consistent` cross-checks that `did:acp:` was derived from the same key

**Why it matters**: [A2A issue #1672](https://github.com/a2aproject/A2A/issues/1672) (62 comments, still open — three competing 3rd-party implementations in the thread but nothing merged into A2A spec). ACP v1.8+v1.9 ships the complete identity story today: sign your card, verify your peer's card, mutual verification at handshake.

New endpoints:
- `GET /verify/card` — verify local agent's own card
- `POST /verify/card` — verify any external AgentCard
- `capabilities.card_sig: true` — discoverable via AgentCard

---

## 2026-03-25

### Cancel Semantics — spec §10 (v1.5.2)

ACP now has an unambiguous answer to "what happens when you cancel a task":

- **Synchronous**: `:cancel` returns `{"status": "canceled"}` immediately — no async/deferred state
- **Idempotent**: calling `:cancel` on an already-canceled task returns `200` (not an error)
- **ERR_TASK_NOT_CANCELABLE (409)**: canceling a `completed` or `failed` task returns a clear error

This is documented in `spec/core-v1.3.md §10`. Compare: [A2A issue #1680](https://github.com/a2aproject/A2A/issues/1680) has been open for days with two competing proposals and no resolution.

---

## 2026-03-24

### NAT Traversal Signaling Layer (v1.4)

Three-level connection strategy, now with a real signaling layer:

```
Level 1: Direct P2P (same LAN, public IP) — instant
Level 2: UDP hole-punching via Cloudflare Worker signaling — handles most NAT
Level 3: HTTP relay fallback — always works, higher latency
```

The signaling server is privacy-first: addresses are stored ephemerally (30s TTL), one-time-read (auto-deleted after retrieval), no persistent address storage.

### Hybrid Identity (v1.5)

```bash
# Self-sovereign by default
acp-relay --name Alice
# did:acp:abc123...  (derived from Ed25519 key pair, works offline)

# Or hybrid: trust your org CA
acp-relay --name Alice --ca-cert /path/to/org-ca.pem
# identity.scheme: ed25519+ca
```

Compare: A2A is converging on `getagentid.dev` as a reference CA — an external service you have to register with. ACP's default requires no registration, no external service, no internet connection.

### Java SDK

```java
AcpClient client = new AcpClient("http://localhost:7901");
SendResult result = client.send("Hello from Java");
```

Zero external dependencies. Maven Central package: `dev.acp:acp-client`.

### Compatibility Certification

Two certification levels:
- **Level 1** (24 tests): Core messaging, task state machine, AgentCard discovery
- **Level 2** (planned): NAT traversal, identity, multi-peer routing

The reference relay implementation passes Level 1: 24/24 ✅

---

## 2026-03-23

### Real Multi-Agent Scenario Testing

First full end-to-end validation with real processes (not mocks):

- Scenario A: Single agent send/recv
- Scenario B: Orchestrator → Worker1 + Worker2 (team collaboration)  
- Scenario C: Multi-agent pipeline (A → B → C → A chain)
- Scenario D: Stress test (100 messages, concurrent sends, reconnection)
- Scenarios F+G: Error handling, disconnect/reconnect

All passing. See `tests/test_scenario_*.py`.

---

## 2026-03-22

### Docker

```bash
docker pull ghcr.io/kickflip73/acp-relay:latest
docker run -p 7801:7801 -p 7901:7901 ghcr.io/kickflip73/acp-relay:latest --name Alice
```

### DID Identity

`did:acp:<base58url(pubkey)>` — self-sovereign agent identity. No registry. No external resolver. Generated from your Ed25519 key pair on startup.

### Extension Mechanism

Agents can now declare capability extensions via URI:

```json
{
  "extensions": [
    "acp:ext:streaming-video",
    "acp:ext:long-running-tasks"
  ]
}
```

### HMAC Replay Protection

Previously: HMAC-SHA256 signing was optional but replay attacks were possible. Now: sliding window (60s, 1000-entry cache) rejects replayed message IDs. Zero breaking change — unsigned messages still accepted if `--secret` not set.

---

## Protocol Comparison Snapshot (as of 2026-03-26)

| Feature | ACP | A2A |
|---------|-----|-----|
| **LAN discovery** | ✅ **TCP port-scan `/peers/discover` — no mDNS required, finds any relay (v2.1-alpha)** | ❌ No LAN discovery mechanism in spec |
| **Offline delivery** | ✅ **Auto-queue on disconnect, auto-flush on reconnect (v2.0-alpha)** | ❌ No offline delivery — messages lost if peer is offline |
| Cancel semantics | ✅ Defined (§10), synchronous | ❓ Open issues #1680 + #1684 |
| Credential security | ✅ No push creds | ⚠️ Open issue #1681 |
| **AgentCard verification** | ✅ **Ed25519 self-sig + auto mutual verify (v1.8+v1.9)** | ❌ Open issue #1672 (62 comments, 3 competing impls, nothing merged) |
| **Mutual identity at handshake** | ✅ **Auto-verified on connect, `GET /peer/verify` (v1.9)** | ❌ No protocol-level handshake identity |
| Agent identifier | ✅ `did:acp:` (cryptographic, ownership-provable) | 🔄 PR#1079: random UUID (unverifiable) |
| SSE context propagation | ✅ context_id in all events | ⚠️ Spec contradiction (§4.2.2 vs §6.2, issue #1683) |
| Identity | ✅ Self-sovereign `did:acp:` | 🔄 Heading toward `getagentid.dev` (external CA) |
| Error Content-Type | ✅ `application/json` (explicit) | ⚠️ Ambiguous (open issue #1685) |
| Setup | `curl` + 2 steps | OAuth 2.0 + infra |
| Task states | 5 (simple) | 8 (complex) |
| Last code activity | Today | 10 days ago |

---

*Built by one person + J.A.R.V.I.S. · [GitHub](https://github.com/Kickflip73/agent-communication-protocol)*
