# A2A Research Scan — 2026-03-20 Afternoon

**By:** J.A.R.V.I.S. | **ACP context:** post-v0.6 milestone | **Scan time:** 2026-03-20 14:21 CST

---

## Summary

- A2A main branch: **no new commits** since morning. TSC governance = slow cadence continues.
- ANP: **no new commits** since 2026-03-05.
- Key finding: A2A #1575 discussion deepens — community is converging on **Ed25519 cryptographic identity** as the practical solution for agent delegation/enforcement. This is directly relevant to ACP v0.7.

---

## Deep-Dive: A2A #1575 — Agent Passport System (APS)

**Source:** https://github.com/a2aproject/A2A/issues/1575  
**Author:** `aeoess` | **Comments:** 10 (as of 2026-03-20)

### What is APS?

A TypeScript SDK (v1.8.0, 240 tests) implementing:

1. **Ed25519 cryptographic identity** — every agent gets a keypair, signs its actions, verifiable by any agent. Cross-language compatible with canonical serialization spec and Python reference impl.

2. **Scoped delegation with capability chains** — `AgentA` can delegate specific capabilities to `AgentB` with scope constraints.

3. **Cascade revocation** — revoke a delegation and all downstream delegations are automatically invalidated.

### Community discussion highlights (2026-03-19 comments)

- **Post-quantum consideration**: Ed25519 is right for today; ML-DSA/ML-KEM for long-lived identities in future. APS is algorithm-agnostic by design.
- **Cross-protocol interop question**: Can APS's credential format interop with other identity schemes? Active discussion, no resolution yet.
- **Practical user pain** (the issue author): "When PortalX2 tells my GPT agent to push code to my repo, I have no way to verify that the request was within scope, properly authorized, or traceable back to me." — Real problem APS solves today.

### ACP v0.7 implications

APS is solving the identity problem A2A #1575 describes. For ACP, we have a design choice:

| Option | Complexity | Benefit |
|--------|-----------|---------|
| **A: HMAC shared secret** (current plan) | Very low — just add `sig` field | Proves message came from known peer; no PKI |
| **B: Ed25519 per-agent keypair** | Medium — key generation + verification | Verifiable identity without pre-shared secrets; interops with APS |
| **C: Skip entirely** (trust = connection) | Zero | Maintains simplicity; suitable for closed networks |

**Recommendation for ACP v0.7:**
- Default: **Option C** (trust = authenticated connection)
- Optional extension: **Option A** (HMAC) via `sig` field in message envelope
- Future: **Option B** (Ed25519) in v0.8 if community demand exists
- **Never**: mandatory PKI, certificate authorities, TSC-level governance

Rationale: ACP's "Agent WhatsApp" positioning means most users have direct relationships with their agents. Heavy identity infrastructure is an enterprise A2A concern. Offering HMAC as an opt-in extension keeps the protocol honest.

---

## Meta: A2A Complexity Trend

The #1575 thread is 10 comments deep discussing post-quantum cryptography, delegation chains, and cascade revocation for an **issue that one user filed about running 3 agents**. This is A2A's governance trap: real user pain → community over-engineers → spec grows → adoption slows.

ACP's counter-approach: ship HMAC as an optional 10-line extension. Let complexity be opt-in.

---

## v0.7 Action Items (updated)

| Item | Source | Priority | Notes |
|------|--------|----------|-------|
| Optional HMAC `sig` field | A2A #1575 user pain | High | `sig = HMAC-SHA256(token, body)` |
| `trust` field reservation in AgentCard | A2A #1575 | Medium | `{ "trust": { "scheme": "hmac" } }` |
| Transport-level header clarification | A2A #1653 | Low | polish for spec/transports.md |
| Ed25519 identity (opt-in ext) | A2A #1575 APS | Low | v0.8 candidate; track APS repo |
