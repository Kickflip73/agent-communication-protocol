# ADR-004: JWKS Compatibility Layer — `/.well-known/jwks.json`

**Status**: Accepted  
**Date**: 2026-03-30  
**Author**: J.A.R.V.I.S. / Stark

---

## Context

ACP uses Ed25519 key pairs for agent identity (since v1.3 `did:acp:` DID). The raw
public key is embedded in the DID, AgentCard's `identity.did` field, and the
Ed25519 identity block. However, raw Ed25519 bytes are not directly consumable by
systems that speak JSON Web Key (JWK) — the dominant format in OAuth 2.0, JOSE, and
JWT ecosystems.

A2A [IS#1628](https://github.com/a2aproject/A2A/issues/1628) proposes adding
`trust.signals[]` with JWKS-format key discovery to A2A's AgentCard. As of
2026-03-30, this proposal has **no merged implementation** in A2A.

Two concrete pain points that motivated this ADR:

1. **Cross-ecosystem interoperability**: Any system that validates JWTs or JWKs
   (API gateways, OpenID Connect verifiers, standard OAuth2 tooling) cannot consume
   ACP's raw Ed25519 key without a translation layer.
2. **trust.signals[] completeness**: ACP's `trust.signals[]` (v2.14) already
   declares `ed25519_identity` as a signal. Adding a `jwks` type signal alongside it
   gives consumers a choice: raw bytes (ACP-native) or JWK (standard ecosystem).

RFC 7517 (JWK) + RFC 8037 (CFRG Elliptic Curves for JOSE) together define how
Ed25519 keys are expressed as JWKs: `kty=OKP`, `crv=Ed25519`, `alg=EdDSA`,
`x=<base64url(pubkey)>`.

## Decision

**ACP ships a JWKS compatibility layer as part of v2.18.**

### Endpoint

```
GET /.well-known/jwks.json
```

- Always returns HTTP 200 with `Content-Type: application/json`
- When `--identity` is enabled: returns `{"keys": [<JWK>]}`
- When `--identity` is not provided: returns `{"keys": []}` (empty but valid JWK Set)
- Unauthenticated — no token required (same as `/.well-known/acp.json`)

### JWK Format

```json
{
  "kty": "OKP",
  "crv": "Ed25519",
  "x": "<base64url(32-byte pubkey)>",
  "use": "sig",
  "alg": "EdDSA",
  "kid": "<agent_name>:<pubkey_prefix_8chars>"
}
```

Per RFC 8037 §2: OKP key type for Edwards curves; `crv=Ed25519`; public key in `x`.

### AgentCard Integration

Two new fields in AgentCard:

```json
{
  "capabilities": {
    "trust_jwks": true
  },
  "endpoints": {
    "jwks": "/.well-known/jwks.json"
  }
}
```

`capabilities.trust_jwks` is always `true` (endpoint is always available, even when
`--identity` is not set — it returns an empty key set, which is valid).

### trust.signals[] Extension

When `--identity` is enabled, a new signal of type `"jwks"` is appended alongside
the existing `"ed25519_identity"` signal:

```json
{
  "type": "jwks",
  "enabled": true,
  "jwks_uri": "/.well-known/jwks.json",
  "alg": "EdDSA",
  "description": "RFC 7517 JWK Set endpoint; Ed25519 public key in OKP/EdDSA format",
  "details": {
    "kty": "OKP",
    "crv": "Ed25519",
    "alg": "EdDSA",
    "kid": "<kid>"
  }
}
```

The existing `"ed25519_identity"` signal (raw key bytes, ACP-native format) is
**preserved** — both signals coexist for maximum interoperability.

## Rationale

- **Standard compliance first**: JWK is the lingua franca of modern identity tooling.
  Expressing ACP's Ed25519 key in JWK format requires zero new cryptographic work —
  just a serialization transform.
- **Backwards compatible**: `capabilities.trust_jwks` is additive. Old relay clients
  that don't know about JWKS simply ignore the new field.
- **Discoverable via two paths**: Consumers can find the JWKS URI either from
  `endpoints.jwks` (AgentCard) or `trust.signals[type=jwks].jwks_uri` (trust signals).
  Two discovery paths → more robust toolchain integration.
- **Empty-set semantics**: Returning `{"keys": []}` when no identity is configured
  avoids 404 errors in clients that pre-fetch JWKS. The endpoint is always safe to GET.
- **Differentiation**: A2A IS#1628 is still a proposal. ACP ships working code today.

## Consequences

### Positive
- Any OAuth2/JOSE-compatible system can now discover and use ACP's signing key
  without custom ACP parsing logic
- `capabilities.trust_jwks` in AgentCard provides a clean capability advertisement
- Show HN talking point: "ACP exposes Ed25519 key as a standard JWKS endpoint —
  drop it into any API gateway that supports JWK validation"
- A2A IS#1628 comparison is favorable: ACP ships what A2A only proposes

### Negative
- `kid` uses `<agent_name>:<pubkey_prefix_8>` — not a globally unique URN. Sufficient
  for single-relay use cases; multi-relay federation (v2.0) may need a stronger `kid`
  convention (e.g. `did:acp:<full_pubkey_base58>`). Deferred to v2.0.
- `use=sig` only — no encryption key declared. ACP does not use key agreement, so
  this is correct, but consumers expecting `use=enc` for TLS will be confused.
  Documented in `GET /.well-known/jwks.json` response (comment field not in spec,
  addressed via `capabilities.trust_jwks` description in AgentCard).

## Implementation Notes

- `_build_jwks(agent_name)` constructs the JWK Set from `_identity["public_key_bytes"]`
  (32 raw bytes loaded at startup from `~/.acp/identity.json`)
- base64url encoding: Python `base64.urlsafe_b64encode(pubkey_bytes).rstrip(b"=").decode()`
  per RFC 4648 §5 (no padding)
- Handler: `elif self.path == "/.well-known/jwks.json":` branch in `_handle_well_known()`
- Test file: `tests/test_jwks.py` — JW1~JW10: 13/13 PASS (2 no-identity + 8 with-identity + 3 always-declared)

## Alternatives Considered

| Alternative | Reason Rejected |
|-------------|----------------|
| Only expose raw Ed25519 bytes (current state before v2.18) | Not consumable by JWK-native toolchains |
| Replace `ed25519_identity` signal with `jwks` signal | Breaks ACP-native consumers; both signals coexist |
| Use `/.well-known/openid-configuration` JWK URI convention | OIDC overhead not appropriate for agent-to-agent context; `/.well-known/jwks.json` is simpler and more direct |
| Return 404 when no identity configured | Causes pre-fetch failures in client code; empty JWK Set is valid and safer |
| Use DID Document (`/.well-known/did.json`) for key discovery | Already exists (v1.3/v2.9); JWKS is additive for JOSE-ecosystem consumers who don't speak DID |

## Related

- ACP v2.18 implementation: `relay/acp_relay.py` (functions `_build_jwks`, `_build_trust_signals`)
- Tests: `tests/test_jwks.py` (JW1–JW10, 13/13 PASS)
- ADR-002: `adrs/adr-002-no-oauth-ed25519-only.md` — identity foundation this builds on
- ADR-003: `adrs/adr-003-event-replay-since-seq.md` — companion ADR style reference
- A2A IS#1628: https://github.com/a2aproject/A2A/issues/1628 (JWKS proposal, not merged as of 2026-03-30)
- RFC 7517: JSON Web Key (JWK)
- RFC 8037: CFRG Elliptic Curves for JOSE (OKP key type, Ed25519)
