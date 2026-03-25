# What's New in ACP — Last 7 Days

> Last updated: 2026-03-25
> For the full history see [CHANGELOG.md](../CHANGELOG.md)

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

## Protocol Comparison Snapshot (as of 2026-03-25)

| Feature | ACP | A2A |
|---------|-----|-----|
| Cancel semantics | ✅ Defined (§10) | ❓ Open issue #1680 |
| Credential security | ✅ No push creds | ⚠️ Open issue #1681 |
| Identity | ✅ Self-sovereign `did:acp:` | 🔄 Heading toward `getagentid.dev` |
| Setup | `curl` + 2 steps | OAuth 2.0 + infra |
| Task states | 5 (simple) | 8 (complex) |
| Last code activity | Today | 10 days ago |

---

*Built by one person + J.A.R.V.I.S. · [GitHub](https://github.com/Kickflip73/agent-communication-protocol)*
