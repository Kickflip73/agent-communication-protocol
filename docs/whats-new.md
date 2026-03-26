# What's New in ACP — Last 7 Days

> Last updated: 2026-03-26
> For the full history see [CHANGELOG.md](../CHANGELOG.md)

---

## 2026-03-26

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
