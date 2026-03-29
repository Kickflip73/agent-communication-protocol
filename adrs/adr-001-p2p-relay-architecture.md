# ADR-001: P2P Relay Architecture — Zero Central Server

**Status**: Accepted  
**Date**: 2026-03-18  
**Author**: J.A.R.V.I.S. / Stark

---

## Context

ACP needs a way for AI agents to communicate directly without depending on a persistent
cloud service. Existing protocols (A2A, IBM ACP) assume a central broker or cloud
endpoint is always available, creating latency, cost, and trust issues.

The core tension: true P2P requires NAT traversal (hard), but agents want zero-config
simplicity. The relay approach resolves this.

## Decision

ACP uses a **local relay daemon (`acp_relay.py`)** that each participant runs on their
own machine. Connectivity is established through a three-level hierarchy:

```
Level 1: Direct TCP (LAN/same machine) — fastest, used when available
Level 2: NAT hole-punching via Cloudflare Worker signaling — best-effort
Level 3: Cloudflare Worker WebSocket relay — guaranteed fallback
```

The relay exposes a local HTTP API (`localhost:<port>`), so agents communicate with
it using plain `curl` — no ACP SDK required.

**Connection flow:**
1. Host starts relay → gets an `acp://` link  
2. Host shares link with Guest (out-of-band: chat, email, etc.)  
3. Guest starts relay with `--join <link>` → P2P established  
4. Both agents talk to their own local relay via HTTP

## Rationale

- **Zero server dependency**: Relay only needed for signaling; messages go direct once connected
- **Privacy-first**: No message content ever touches Cloudflare (Level 1/2); Level 3 relay
  is end-to-end encrypted via Ed25519 (v1.3+)
- **Curl-accessible**: Any agent in any language can integrate with 3 HTTP endpoints
- **No registration**: Link sharing replaces service discovery registries

## Consequences

### Positive
- Agents in any framework/language can communicate
- No cloud costs for typical usage (Level 1/2 cover most cases)
- Zero trust required in relay infrastructure when Ed25519 identity is enabled
- Easy local development and testing (two processes on localhost)

### Negative
- Both parties must be online simultaneously (mitigated by offline queue in v2.0)
- NAT traversal can fail in strict enterprise networks (Level 3 relay fallback covers this)
- Link sharing is manual (no automatic discovery except LAN mDNS/port-scan)

## Alternatives Considered

| Alternative | Reason Rejected |
|-------------|----------------|
| Central cloud broker (like A2A) | Adds latency, cost, trust dependency; violates P2P principle |
| Pure WebRTC P2P | Browser-only, complex STUN/TURN setup, no Python stdlib support |
| MQTT broker | Requires persistent server, message retention complexity |
| gRPC direct | Firewall issues, complex setup, not curl-friendly |
