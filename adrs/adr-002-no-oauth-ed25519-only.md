# ADR-002: No OAuth 2.0 — Ed25519 Self-Sovereign Identity Only

**Status**: Accepted  
**Date**: 2026-03-22  
**Author**: J.A.R.V.I.S. / Stark

---

## Context

Authentication and trust are critical for Agent-to-Agent communication. The dominant
approach in enterprise protocols (A2A) uses OAuth 2.0 with PKCE flows, requiring
authorization servers, client registration, and token management infrastructure.

ACP's design philosophy is "personal and team use, zero-ops" — which is fundamentally
incompatible with OAuth 2.0's requirement for an authorization server.

## Decision

ACP uses **Ed25519 self-sovereign identity** exclusively for authentication:

- Each relay generates a keypair on first run (`~/.acp/identity.json`, chmod 0600)
- Identity is expressed as a W3C DID: `did:acp:<base64url(pubkey)>`
- AgentCard is signed by the relay's Ed25519 private key (`card_sig` field, v1.8)
- On connection, peers automatically verify each other's AgentCard signature (v1.9)
- No authorization server, no client registration, no token refresh

**What ACP deliberately does NOT do:**
- OAuth 2.0 (implicit, password, authorization code, PKCE, device code)
- JWT tokens with expiry/refresh
- API key management UI
- Central identity registry

## Rationale

- **Zero infrastructure**: Ed25519 keypair is self-generated, self-signed — no CA needed
- **Personal use case**: Individual developers don't have OAuth servers; they have keys
- **Stronger cryptographic guarantees**: Ed25519 is immune to the credential leak
  vulnerabilities that plague OAuth token handling (cf. A2A Issue #1681)
- **Offline-capable**: Signature verification doesn't require network calls to auth server
- **Simplicity**: `--identity` flag to enable; zero config for most users

## Consequences

### Positive
- No credential leak attack surface (A2A #1681 class of bugs impossible)
- Works in air-gapped environments
- Private key never leaves the machine
- DID is portable and standard (W3C DID spec compliant)

### Negative
- No delegation model (one keypair = one identity)
- Key rotation requires manual intervention
- Enterprise SSO integration not supported (by design)

## Alternatives Considered

| Alternative | Reason Rejected |
|-------------|----------------|
| OAuth 2.0 + PKCE | Requires authorization server; violates "zero-ops" principle |
| mTLS / X.509 | Requires CA infrastructure; complex certificate management |
| API Keys (symmetric) | No identity binding; key exchange problem; phishing-vulnerable |
| HMAC-SHA256 only | Symmetric — shared secret model, doesn't scale to multi-party |

## Related

- A2A Issue #1672: Agent authentication discussion (83 comments, unmerged as of 2026-03-29)
- ACP v1.3: Ed25519 identity implementation
- ACP v1.8: AgentCard self-signature
- ACP v1.9: Peer AgentCard auto-verification
- `spec/identity-v0.8.md`: Full identity specification
