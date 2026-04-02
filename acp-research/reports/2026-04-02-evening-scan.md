# ACP Research Scan — 2026-04-02 Evening

**Scan time:** 2026-04-02 17:43 CST  
**Scope:** A2A (google/A2A), ANP (agent-network-protocol/AgentNetworkProtocol)

---

## A2A — google/A2A

### Recent Commits (since last scan, ~1.5h ago)
- **No new spec commits** since 2026-03-31 (`c1169f4` OSPO fix)
- Last 5 commits are all docs/partner-list entries — no protocol changes

### Active PRs Updated Today
| PR | Title | Relevance |
|----|-------|-----------|
| **PR#1619** | docs: Add custom protocol bindings documentation | Medium — formalizes "custom protocol binding" as a distinct concept from "extensions"; introduces governance doc. No spec change. |
| PR#1571 | [docs] Update GOVERNANCE.md | Low — governance housekeeping |
| PR#1627 | fix(spec): recent transcoding-related error changes | Medium — error code spec fix (transcoding); may affect error_failed_msg_id interop |

### Active Issues Updated Today
| Issue | Title | Status |
|-------|-------|--------|
| **IS#1672** | Proposal: Agent Identity Verification for Agent Cards | 233+ comments, no PR merged. Hybrid model (CA-issued + self-sovereign) gaining consensus. ACP already implements this via `--identity` flag. |
| IS#652 | [Feat]: Add Ability for Server to Specify Supported Protocol Versions | Long-standing; still open. |

### Key Observation: PR#1619 — Custom Protocol Bindings
A2A is formalizing "custom protocol bindings" as distinct from extensions. This means:
- A binding declares how A2A message semantics map to a non-HTTP transport (e.g., WebSocket, MQTT, gRPC)
- Declared in AgentCard under a new field
- Governance: community tier < foundation tier < core spec

**ACP relevance:** ACP already has `transport_modes: ["p2p", "relay"]` in AgentCard. The A2A custom bindings concept is exactly what ACP does natively. We may want to add a `protocol_bindings` field to our AgentCard for cross-protocol compatibility.

---

## ANP — agent-network-protocol/AgentNetworkProtocol

### Recent Commits
- Last commit: **2026-03-05** (`99806f4` — `failed_msg_id` field)
- **4+ weeks of zero activity** — project appears stalled

### Assessment
ANP continues to be dormant. No action needed.

---

## ACP v2.35 — Delivery ACK (Just Shipped)

This session completed v2.35 Delivery ACK:
- `acp.delivered` frame: receiver auto-ACKs business messages
- `capabilities.delivery_ack: true` in AgentCard
- `messages_delivered` counter in `/status` and `/peers`
- `--local-only` flag for CI/sandbox environments
- DA1–DA10: 10/10 tests pass in 12.5s
- Commits: `d444585`, `227621a` pushed to main

---

## Next Action Items

| Priority | Item | Notes |
|----------|------|-------|
| P2 | Consider `protocol_bindings` field in AgentCard | Align with A2A PR#1619 framing |
| P3 | Monitor A2A IS#1672 for identity PR | ACP hybrid model already implemented |
| P3 | Monitor PR#1627 (error transcoding fix) | May affect `error_failed_msg_id` interop |

---

## ROADMAP Next Target: v2.36

Per ROADMAP.md, after v2.35 (Delivery ACK), recommended next feature is:
- **P1: Read Receipt / Seen ACK** (`acp.read` frame) — sender knows message was read/processed (not just delivered)
- Alternative: **P1: Protocol Version Negotiation** (aligns with A2A IS#652)

Recommendation: **v2.36 = `acp.read` frame** (natural progression from v2.35 delivery→read pipeline).
