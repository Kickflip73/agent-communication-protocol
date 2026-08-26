# A2A Research Scan — 2026-03-20 Evening

**By:** J.A.R.V.I.S. | **ACP context:** v0.7-dev (HMAC landed) | **Scan time:** 2026-03-20 16:13 CST

---

## Summary

- A2A main: no new commits. TSC governance slowdown continues.
- ANP: still dormant.
- Key findings this round: contextId design evolution (PR #1586) + correlation ID PR (#939) + **A2A has zero mDNS/LAN-discovery discussion** → confirmed ACP differentiation opportunity.

---

## Finding 1: contextId is now OPTIONAL in A2A (PR #1586)

**Source:** https://github.com/a2aproject/A2A/pull/1586  
**State:** Closed (not merged — TSC direction still in flux via #1581)  
**Author:** vinoo999

### What changed

PR proposes making `Task.context_id` fully optional:
- Agents **MAY** generate and include contextId (no longer required)  
- Clients **MAY** provide contextId; agents must preserve it if valid
- Breaking change to `a2a.proto`

### ACP implication

ACP v0.7 plans `context_id` for multi-turn conversation tracking. The A2A debate confirms the right design:

> **contextId should be client-generated, optional, and preserved by server — never mandatory.**

This matches ACP's message model philosophy (client controls identity fields; server echoes).

**Action for ACP v0.7:** Add `context_id` as an optional field in the message envelope:
```json
{
  "type": "acp.message",
  "message_id": "msg_...",
  "context_id": "ctx_...",   ← optional; groups messages into conversations
  "parts": [...]
}
```
No server-side enforcement. If present, relay/receiver must echo it in any reply.

---

## Finding 2: A2A PR #939 — correlation ID for idempotent task creation

**Source:** https://github.com/a2aproject/A2A/pull/939  
**State:** Open (long-running, not merged)

### What it proposes

- New `correlationId` field in `MessageSendParams`
- New capability flag `correlationIdRequired`
- New error code `-32008 CorrelationIdAlreadyExistsError`

### ACP comparison

ACP already implements this more cleanly via `message_id` (client-generated, server-side dedup cache, idempotency guaranteed). No extra capability flag needed — it's always-on.

The A2A PR being stuck for months confirms that designing idempotency as an opt-in capability creates perpetual debate. ACP's approach (mandatory `message_id`, server always deduplicates) avoids this entirely.

**Action:** None. Document as validation of ACP's always-on idempotency design.

---

## Finding 3: A2A has ZERO mDNS / LAN discovery discussion

Searched: `mdns`, `local-network`, `LAN`, `local agent`, `mesh` — only tangential results (Mesh extension proposal from 2025-05, general local-first features not in active discussion).

### ACP differentiation opportunity

A2A is cloud/enterprise-first by design. It has no concept of:
- Agents discovering each other on a local network
- Zero-config LAN peer discovery
- Offline-first agent mesh

**ACP v0.7 mDNS plan:**  
Using Python's `zeroconf` library (or stdlib `socket` multicast):
```python
# Host mode: advertise _acp._tcp.local with token
# Guest mode: browse _acp._tcp.local to find available peers
acp_relay.py --name "Agent-A" --advertise-mdns
acp_relay.py --name "Agent-B" --discover-mdns   # auto-finds Agent-A on LAN
```

This is a **genuine A2A whitespace**: local-first, zero-config, works offline. Positions ACP as "Agent WhatsApp" for personal/home lab/small team use.

**Action:** Implement mDNS discovery as ACP v0.7 feature. File as ROADMAP item.

---

## v0.7 Updated Action Items

| Item | Status | Priority | Notes |
|------|--------|----------|-------|
| HMAC-SHA256 `sig` field | ✅ Done (87dad51) | — | Optional, `--secret` flag |
| `context_id` field (conversation grouping) | ⏳ Next dev round | High | Optional, client-generated, server-echoes |
| mDNS local peer discovery | ⏳ Planned | High | **ACP-unique**, A2A has nothing here |
| `trust` AgentCard reservation | ✅ Done (87dad51) | — | Included in HMAC commit |
| transports.md header clarification | ⏳ Polish | Low | §Binding A note |
