# A2A #1712 Comment Draft
> Target: https://github.com/a2aproject/A2A/issues/1712
> Status: Draft (ready to post)
> Context: 64R3N's WTRMRK proposal; aeoess's three-layer model

---

## Comment Text

The gap @64R3N identified is real, and @aeoess's framing is exactly right: identity is only the first layer. The full trust stack needs: **identity (who) → delegation scope (what they're allowed to do) → execution proof (what actually happened)**.

We've been building this three-layer model into [ACP (Agent Communication Protocol)](https://github.com/Kickflip73/agent-communication-protocol), and wanted to share how we addressed each layer without a central CA.

---

### Layer 1: Identity — Ed25519 Self-Signed, No CA

Instead of registering with a central authority, each ACP agent generates an Ed25519 keypair locally on first run. The public key is embedded in the AgentCard (`GET /.well-known/acp.json`) along with a `card_signature` — an Ed25519 signature over the canonical JSON of the card itself.

Any receiving agent can verify the card with:

```http
POST /identity/verify-card
{"card": { ...AgentCard... }}
```

Response: `{"verified": true, "did": "did:key:z6Mk...", "signature_valid": true}`

No CA lookup. No network call. Pure cryptography. Works offline, works air-gapped, works for ephemeral agents.

On @aeoess's point about Ed25519 being the de facto standard — agreed. IETF draft-prakash-aip, APS, SATP, and now ACP all use Ed25519. Standardizing on one curve reduces the verification surface for every receiving agent.

---

### Layer 2: Delegation Scope — Capability Token + Skill Authorization Tiers

Identity proves *who*. But *what are they allowed to do*? We implemented a tiered capability model (T0–T3) where each agent's effective authorization tier is a composite of five factors:

- `identity_verified` (Layer 1 → feeds Layer 2)
- `trust_score` (accumulated from bilateral interactions)
- `bilateral_ir_adj` (adjustment from signed interaction records)
- `revocation_clean` (credential lifecycle check)
- `policy_compliance` (governance standards declared in AgentCard)

The scope is declared in a `capability_token` — a signed structure that any counterparty can verify without contacting a registry.

Full spec: [ACP-RFC-001: Skill Authorization](https://github.com/Kickflip73/agent-communication-protocol/blob/main/docs/rfc/skill-authorization.md)

---

### Layer 3: Execution Proof — Bilateral Signed Interaction Records

After a task completes, *what actually happened* needs to be provable. ACP's bilateral interaction records have both parties sign the same canonical payload — neither party can forge a record that the other didn't participate in. Records are SHA-256 hash-chained (each IR links to the previous), with Merkle roots for batch verification.

This gives you: tamper-evident audit trail, offline-verifiable, no third party needed.

Full spec: [ACP-RFC-002: Bilateral Interaction Records](https://github.com/Kickflip73/agent-communication-protocol/blob/main/docs/rfc/bilateral-interaction-records.md)

---

### On the CA Approach in #1672

We wrote up a detailed comparison in [ACP-RFC-004: Decentralized Agent Identity Without CA](https://github.com/Kickflip73/agent-communication-protocol/blob/main/docs/rfc/identity-without-ca.md). The short version:

| | Self-Signed Ed25519 (ACP) | Central CA (#1672) |
|---|---|---|
| Single point of failure | ❌ None | ✅ getagentid.dev |
| Offline verification | ✅ Pure crypto | ❌ CA reachability |
| Ephemeral agents | ✅ Zero-friction | ❌ Must register first |
| Privacy | ✅ No registry | ❌ CA sees all |
| Implementation | ✅ ~50 lines | ❌ PKI infrastructure |
| Status | ✅ Implemented (v2.85+) | ⏳ Proposed |

The multi-provider direction @aeoess recommends is naturally supported via DID methods — `did:key`, `did:web`, `did:acp` — each independently verifiable.

---

Happy to discuss any of the design decisions. The three-layer model has been running in production for several weeks and we've been finding it covers the scenarios that come up in real cross-agent deployments.

