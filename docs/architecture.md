# ACP Architecture — Three-Layer Model

> Version: v0.8  
> Status: **Stable**  
> Last updated: 2026-04-03

## Overview

ACP (Agent Communication Protocol) is organized into three independent,
composable layers. Each layer can be adopted without requiring the layers above it.

---

## Layer 1 — Transport

**Purpose**: Establish a bidirectional channel between two agents.

| Aspect | Detail |
|--------|--------|
| Primary | WebSocket (RFC 6455) |
| Secondary | HTTP long-poll (SSE `/stream`) |
| NAT traversal | 3-level: Direct → UDP hole-punch → Relay |
| Discovery | mDNS (LAN), manual `acp://` link |

**Entry point**: Start `acp_relay.py`, share the `acp://` link.

---

## Layer 2 — Messaging

**Purpose**: Structured message exchange with task lifecycle management.

| Aspect | Detail |
|--------|--------|
| Message format | JSON envelope with `parts[]` (text / file / data) |
| Task states | `submitted → working → completed / failed / input_required` |
| Deduplication | Client-generated `message_id`, 30s TTL window |
| Delivery ack | `acp.delivered` + `acp.read` receipts |
| Streaming | SSE events: `status` / `artifact` / `message` |

**Key endpoints**: `POST /message:send`, `GET /stream`, `GET /status`

---

## Layer 3 — Identity (Optional)

**Purpose**: Cryptographic agent identity without PKI or central registry.

| Aspect | Detail |
|--------|--------|
| Algorithm | Ed25519 (RFC 8037) |
| Key management | Self-sovereign; agent generates its own keypair |
| Signing | Canonical JSON payload → Ed25519 signature |
| Verification | Public key in AgentCard `identity` block |
| Replay protection | ±300s timestamp window + `message_id` dedup |
| CA integration | Optional `--ca-cert` for hybrid model (v1.5+) |

**Activation**: Pass `--identity <path-to-key>` to `acp_relay.py`.  
**Backward compatible**: Agents without `--identity` are unaffected.

---

## Composability

```
Agent A ──[L1: WebSocket]──► Agent B
            [L2: Parts/Task]
            [L3: Ed25519 sig]   ← optional
```

You can run L1 only (raw transport), L1+L2 (full messaging), or all three.
No layer requires the one above it.

---

## Implementation Status (v0.8)

| Layer | Status | Key file |
|-------|--------|----------|
| L1 Transport | ✅ Stable | `relay/acp_relay.py` |
| L2 Messaging | ✅ Stable | `spec/core-v0.8.md` |
| L3 Identity | ✅ Stable | `spec/identity-v0.8.md`, `relay/identity.py` |

---

## See Also

- `spec/core-v0.8.md` — Full L2 messaging specification
- `spec/identity-v0.8.md` — L3 identity extension spec
- `spec/transports.md` — L1 transport details
- `relay/identity.py` — L3 reference implementation
