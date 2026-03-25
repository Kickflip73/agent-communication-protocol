# What's New in ACP — Last 7 Days

> Last updated: 2026-03-26
> For the full history see [CHANGELOG.md](../CHANGELOG.md)

---

## 2026-03-26

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

**Why it matters**: [A2A issue #1672](https://github.com/a2aproject/A2A/issues/1672) (47 comments, still open): A2A has no protocol-level agent identity verification — they rely on transport-layer trust (OAuth/HTTPS). ACP v1.8 ships verifiable agent identity today.

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
| Cancel semantics | ✅ Defined (§10), synchronous | ❓ Open issues #1680 + #1684 |
| Credential security | ✅ No push creds | ⚠️ Open issue #1681 |
| **AgentCard verification** | ✅ **Ed25519 self-sig (v1.8)** | ❌ Open issue #1672 (no protocol-level solution) |
| SSE context propagation | ✅ context_id in all events | ⚠️ Spec contradiction (§4.2.2 vs §6.2, issue #1683) |
| Identity | ✅ Self-sovereign `did:acp:` | 🔄 Heading toward `getagentid.dev` (external CA) |
| Error Content-Type | ✅ `application/json` (explicit) | ⚠️ Ambiguous (open issue #1685) |
| Setup | `curl` + 2 steps | OAuth 2.0 + infra |
| Task states | 5 (simple) | 8 (complex) |
| Last code activity | Today | 10 days ago |

---

*Built by one person + J.A.R.V.I.S. · [GitHub](https://github.com/Kickflip73/agent-communication-protocol)*
