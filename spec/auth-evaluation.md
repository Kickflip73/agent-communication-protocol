# ACP Authentication Model — OAuth 2.0 PKCE Evaluation

**Status:** Final (non-normative)  
**Version:** 1.0 (2026-04-04)  
**Type:** Design decision record — analysis only, not a protocol requirement

> **TL;DR:** ACP does not adopt OAuth 2.0 PKCE. This document explains why, and what ACP uses instead.

---

## 1. Background

A2A v1.0 mandates OAuth 2.0 + PKCE as its primary authentication mechanism. During ACP v0.9 planning, we evaluated whether ACP should adopt the same model. This document records that evaluation.

ACP's design constraints (established 2026-03-19):

- **Lightweight, zero-config** — single-file Skill, one command to run
- **P2P, no central intermediary** — Relay only punches holes, never authenticates
- **Personal/small-team target** — not enterprise multi-tenant
- **"Agent WhatsApp"** — two agents connect as peers, not client-to-server

---

## 2. What OAuth 2.0 PKCE Requires

OAuth 2.0 Authorization Code + PKCE (RFC 7636) requires:

| Component | Description |
|-----------|-------------|
| **Authorization Server (AS)** | A central service that issues tokens (e.g. Auth0, Keycloak, custom IdP) |
| **Client registration** | Every agent must be pre-registered with the AS (`client_id`) |
| **Browser redirect flow** | PKCE was designed for public clients (SPAs, mobile apps) with a browser |
| **Token introspection** | Resource server validates tokens against the AS (online check) or uses signed JWTs |
| **Refresh token lifecycle** | `access_token` expiry + `refresh_token` rotation management |

**Estimated setup overhead for a new agent:** 15–30 minutes (AS deployment or SaaS account, client registration, token endpoint wiring).

---

## 3. Why PKCE Does Not Fit ACP

### 3.1 No Authorization Server in P2P Model

ACP agents connect peer-to-peer. There is no central server that both agents trust. OAuth 2.0 requires a shared AS — this fundamentally conflicts with ACP's P2P topology.

```
OAuth 2.0 topology:        ACP topology:
  
  Agent A ──→ AS ──→ Agent B     Agent A ←──→ Agent B
              ↑                      (direct, no AS)
         central trust
```

Introducing an AS would require either:
- A hosted ACP AS (central infrastructure — violates "no central server")
- Each user running their own AS (more complex than the agent itself)

### 3.2 PKCE Was Designed for Browser Flows

PKCE's code challenge/verifier exchange was specifically designed to prevent authorization code interception in browser redirect flows. ACP agents communicate directly over WebSocket or HTTP — there is no browser redirect, no authorization code, and no interception risk of that type.

### 3.3 Token Lifecycle Complexity vs. Session Lifetime

ACP sessions are ephemeral: an agent starts, connects, exchanges messages, and stops. The token lifecycle (issue → use → refresh → revoke) adds state that outlives the session and requires coordination. ACP's session-scoped token (`tok_` + 16 hex) is simpler and sufficient.

### 3.4 Enterprise Features Not Needed at Target Scale

OAuth 2.0 provides:
- Multi-tenant isolation
- Delegated authorization (user consents to agent acting on their behalf)
- Scope-based permission granularity
- Centralized audit log

These are valuable for enterprise deployments. ACP targets personal and small-team use where the agent owner **is** the resource owner — delegation is not needed.

---

## 4. ACP's Lightweight Alternative

ACP uses a layered trust model with three levels, matching the deployment context:

### Level 0 — Session Token (Always Present)

Every ACP session has a `tok_` + 16 hex chars token generated at startup:

```
tok_ba366fcab78d4d61
```

- Embedded in the link (`acp://host:port/tok_...`)
- Shared out-of-band (user sends link to the other party)
- Single-use per session; new token on restart
- **Trust model:** "Anyone with the link can connect" — equivalent to a shared secret

**Threat coverage:** Prevents random port scanners from connecting. Does not provide identity verification.

### Level 1 — HMAC-SHA256 Message Signing (Optional)

For environments where the token alone is insufficient:

```json
{
  "type": "acp.message",
  "message_id": "msg_abc",
  "sig": {
    "alg": "hmac-sha256",
    "kid": "key_01",
    "value": "<base64-hmac>"
  },
  "parts": [...]
}
```

- Shared secret established at connection time (exchanged in AgentCard)
- Signs individual messages — forgery-resistant even if relay is compromised
- `capabilities.hmac: true` in AgentCard

**Threat coverage:** Message integrity + sender authentication within a session.

### Level 2 — Ed25519 Identity Signing (Optional)

For agents that need verifiable, persistent identity:

```json
{
  "trust": {
    "signals": [
      {
        "type": "ed25519_identity",
        "public_key": "<base64url>",
        "card_sig": "<base64url-signature-over-agentcard>"
      },
      {
        "type": "jwks",
        "jwks_uri": "https://agent.example.com/.well-known/jwks.json"
      }
    ]
  }
}
```

- Ed25519 keypair generated once; public key in AgentCard
- AgentCard itself is signed — tamper-evident
- JWKS endpoint for key discovery (RFC 7517)
- `capabilities.ed25519: true`, `capabilities.trust_jwks: true`

**Threat coverage:** Persistent agent identity, AgentCard integrity, cryptographic non-repudiation.

---

## 5. Comparison

| Criterion | OAuth 2.0 PKCE | ACP Layered Trust |
|-----------|---------------|-------------------|
| Setup time | 15–30 min (AS + registration) | 0 min (token auto-generated) |
| Central dependency | Required (Authorization Server) | None |
| Works P2P | ❌ No | ✅ Yes |
| Browser required | ✅ Yes (PKCE flow) | ❌ Not required |
| Identity persistence | ✅ Yes (AS-issued identity) | ✅ Yes (Ed25519 keypair) |
| Message signing | ❌ Not native | ✅ HMAC + Ed25519 |
| Multi-tenant | ✅ Yes | ❌ Not designed for |
| Delegated auth | ✅ Yes | ❌ Not needed at target scale |
| Enterprise audit | ✅ Yes | ❌ Out of scope |
| **Target fit (personal/small-team)** | ❌ Overengineered | ✅ Right-sized |

---

## 6. Decision

**ACP will not adopt OAuth 2.0 PKCE.**

Rationale:
1. Requires a central Authorization Server — incompatible with P2P topology
2. PKCE's browser redirect flow has no equivalent in Agent-to-Agent communication
3. Token lifecycle complexity exceeds the needs of ephemeral agent sessions
4. Enterprise features (multi-tenant, delegated auth) are out of scope for ACP's target

ACP's layered trust model (Level 0 session token → Level 1 HMAC → Level 2 Ed25519) provides appropriate security for each deployment context without infrastructure dependencies.

**If a future ACP enterprise profile is defined**, OAuth 2.0 or OIDC integration may be reconsidered at that time. This document would serve as the baseline comparison.

---

## 7. Future Considerations

| Scenario | Possible approach | Priority |
|----------|------------------|---------|
| Agent acting on behalf of a human user | OAuth 2.0 PKCE (user consent flow) | Post-v1.0, if needed |
| Cross-organization agent federation | DID-based authentication (A2A #1672 direction) | Watch |
| Hardware-backed identity | TPM / Secure Enclave for Ed25519 key storage | Long-term |

---

*ACP v0.9 · Decision Record · https://github.com/Kickflip73/agent-communication-protocol*
