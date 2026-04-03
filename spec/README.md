# ACP Specification Index

> Version: **v0.8**  
> Status: **Stable**  
> Last updated: 2026-04-03  
> Implementation: [`relay/acp_relay.py`](../relay/acp_relay.py) · v2.43.0

ACP is organized into three independent, composable layers.  
Each layer can be adopted without requiring the layers above it.

---

## Three-Layer Architecture

```
┌─────────────────────────────────────────────────────┐
│  Layer 3 — Identity (Optional)                      │
│  Ed25519 self-sovereign agent identity              │
│  spec: identity-v0.8.md                             │
├─────────────────────────────────────────────────────┤
│  Layer 2 — Messaging                                │
│  Structured messages, task lifecycle, SSE stream    │
│  spec: core-v0.8.md                                 │
├─────────────────────────────────────────────────────┤
│  Layer 1 — Transport                                │
│  WebSocket / HTTP-SSE + NAT traversal               │
│  spec: transports.md                                │
└─────────────────────────────────────────────────────┘
```

All three layers are backward-compatible: an agent using only L1+L2
is fully compatible with one also using L3.

---

## Specification Files

### Layer 1 — Transport

| File | Description | Status |
|------|-------------|--------|
| [`transports.md`](transports.md) | WebSocket, HTTP-SSE, NAT traversal (3-level), mDNS discovery | ✅ Stable |
| [`nat-traversal-v1.4.md`](nat-traversal-v1.4.md) | DCUtR hole-punching deep-dive | ✅ Stable |

### Layer 2 — Messaging

| File | Description | Status |
|------|-------------|--------|
| [`core-v0.8.md`](core-v0.8.md) | Message format (Parts), Task state machine, SSE events, deduplication | ✅ Stable |
| [`core-v1.0.md`](core-v1.0.md) | Task filtering, pagination, error codes extension | ✅ Stable |
| [`core-v1.3.md`](core-v1.3.md) | Broadcast, typing indicator, read receipts, availability | ✅ Stable |
| [`error-codes.md`](error-codes.md) | Complete error code registry | ✅ Stable |

### Layer 3 — Identity (Optional)

| File | Description | Status |
|------|-------------|--------|
| [`identity-v0.8.md`](identity-v0.8.md) | Ed25519 self-sovereign identity, signing, replay protection | ✅ Stable |
| [`identity-v1.5.md`](identity-v1.5.md) | Hybrid CA model (optional PKI overlay) | ✅ Stable |

### Additional Specs

| File | Description | Status |
|------|-------------|--------|
| [`compatibility-certification.md`](compatibility-certification.md) | ACP conformance requirements (MUST/SHOULD/MAY) | ✅ Stable |
| [`v0.6-minimal-agent.md`](v0.6-minimal-agent.md) | Minimal compliant agent implementation guide | ✅ Stable |

---

## Key Endpoints (L2 Reference)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/status` | GET | Agent status + capabilities + AgentCard |
| `/message:send` | POST | Send a message (to specific peer or broadcast) |
| `/stream` | GET | SSE event stream (messages, status, receipts) |
| `/peers` | GET | List connected peers |
| `/peers/connect` | POST | Connect to a remote agent via `acp://` link |
| `/tasks` | GET | List tasks with filtering (`status`, `role`, `since`, `limit`) |
| `/skills` | GET | List published skills (QuerySkill capability) |
| `/recv` | GET | Long-poll message receive (offline queue) |

Full reference: [`../docs/cli-reference.md`](../docs/cli-reference.md)

---

## Quick Start

```bash
# Start an agent
python3 relay/acp_relay.py --name AgentA
# ✅ Ready. Your link: acp://1.2.3.4:7801/tok_xxxxx

# Connect from another agent
curl -X POST http://localhost:7901/peers/connect \
     -d '{"link":"acp://1.2.3.4:7801/tok_xxxxx"}'

# Send a message
curl -X POST http://localhost:7901/message:send \
     -d '{"role":"agent","parts":[{"type":"text","content":"Hello!"}]}'

# Enable Ed25519 identity (Layer 3)
python3 relay/acp_relay.py --name AgentA --identity ~/.acp/agent.key
```

---

## Versioning

ACP uses semantic versioning for spec files. The relay implementation
version (currently v2.43.0) is independent of the spec version.

| Spec | Relay version when introduced |
|------|-------------------------------|
| core-v0.8 | v2.0.0 |
| identity-v0.8 | v2.40.0 |
| core-v1.0 | v2.10.0 |
| core-v1.3 | v2.25.0 |
| identity-v1.5 | v2.35.0 |

---

## See Also

- [`../docs/architecture.md`](../docs/architecture.md) — Three-layer architecture overview
- [`../docs/getting-started/`](../docs/getting-started/) — Tutorials
- [`../docs/comparison.md`](../docs/comparison.md) — ACP vs A2A vs MCP
- [`../docs/conformance.md`](../docs/conformance.md) — Conformance testing guide
