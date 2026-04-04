# ACP Identity Specification — v2.0

**Status**: Stable  
**Authors**: ACP Community  
**Date**: 2026-04-04  
**Supersedes**: [`identity-v1.5.md`](identity-v1.5.md) (Draft — Hybrid model)  
**See also**: [`core-v1.0.md`](core-v1.0.md) · [`transports.md`](transports.md) · [`auth-evaluation.md`](auth-evaluation.md)

> **Stability Promise**: Fields and endpoints marked **`stable`** will not change in a
> backwards-incompatible way within the v2.x series. New optional fields may be added at any time.

---

## 0. Design Principles

ACP identity is **self-sovereign by default, CA-optional by choice**.

| Principle | Meaning |
|-----------|---------|
| **No mandatory PKI** | Agents MUST NOT be required to obtain CA-issued certificates |
| **Pluggable trust** | Verifier decides what it trusts — ACP does not mandate a verification strategy |
| **Optional end-to-end** | Agents without `--identity` operate identically to v0.7 (fully compatible) |
| **Crypto-agile** | Ed25519 is the default; future algorithms added via `scheme` extension |
| **Transport-independent** | Identity is at the application layer; works over any ACP transport binding |

---

## 1. Identity Schemes

`capabilities.identity` (string) declares the active scheme:

| Value | Since | Meaning |
|-------|-------|---------|
| `"none"` | v0.1 | No cryptographic identity — asserted name only |
| `"hmac"` | v0.7 | HMAC-SHA256 shared-secret signing (symmetric) |
| `"ed25519"` | v0.8 | Self-sovereign Ed25519 keypair; `did:acp:` identifier |
| `"ed25519+ca"` | v1.5 | Hybrid: `did:acp:` + optional CA-signed certificate |

Schemes are additive. An agent MAY support multiple schemes simultaneously (e.g. `ed25519` for P2P, `hmac` for legacy peers).

---

## 2. AgentCard `identity` Block — `stable`

When `capabilities.identity` ≠ `"none"`, the AgentCard MUST include a top-level `identity` object:

### 2.1 Ed25519 (self-sovereign)

```json
{
  "identity": {
    "scheme":     "ed25519",
    "public_key": "<base64url-encoded 32-byte Ed25519 public key>",
    "did":        "did:acp:<base64url(public_key)>"
  }
}
```

### 2.2 Hybrid (Ed25519 + CA)

```json
{
  "identity": {
    "scheme":     "ed25519+ca",
    "public_key": "<base64url-encoded Ed25519 public key>",
    "did":        "did:acp:<base64url(public_key)>",
    "ca_cert":    "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----"
  }
}
```

### 2.3 Field Reference

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `scheme` | string | **MUST** | One of: `"ed25519"`, `"ed25519+ca"`, `"hmac"`, `"none"` |
| `public_key` | string | MUST when scheme contains `ed25519` | Base64url-encoded Ed25519 public key (32 bytes) |
| `did` | string | MUST when scheme contains `ed25519` | `did:acp:<base64url(public_key)>` |
| `ca_cert` | string | MUST when scheme is `ed25519+ca` | PEM-encoded X.509 certificate |

---

## 3. Well-Known Endpoints — `stable`

### 3.1 `GET /.well-known/did.json`

Returns the DID Document for this agent's `did:acp:` identifier.

**Availability**: Only when `capabilities.identity` contains `"ed25519"`.  
Returns `404` when no Ed25519 identity is active.

**Response** (200):

```json
{
  "@context": [
    "https://www.w3.org/ns/did/v1",
    "https://w3id.org/security/suites/ed25519-2020/v1"
  ],
  "id":                   "did:acp:<base64url(public_key)>",
  "verificationMethod": [{
    "id":                 "did:acp:<key>#key-1",
    "type":               "Ed25519VerificationKey2020",
    "controller":         "did:acp:<key>",
    "publicKeyMultibase": "z<base58btc(public_key)>"
  }],
  "authentication":        ["did:acp:<key>#key-1"],
  "assertionMethod":       ["did:acp:<key>#key-1"],
  "service": [{
    "id":              "did:acp:<key>#acp",
    "type":            "ACPRelay",
    "serviceEndpoint": "<acp:// or acp+wss:// link>"
  }]
}
```

When no relay link is active, `service` is an empty array `[]`.

### 3.2 `GET /.well-known/jwks.json`

Returns the JWKS (JSON Web Key Set, RFC 7517) representation of the agent's public key.

**Availability**: Only when `capabilities.identity` contains `"ed25519"`.  
Returns `404` when no Ed25519 identity is active.

**Response** (200):

```json
{
  "keys": [{
    "kty": "OKP",
    "crv": "Ed25519",
    "x":   "<base64url-encoded public key>",
    "kid": "<did:acp:...>",
    "use": "sig",
    "alg": "EdDSA"
  }]
}
```

Both `/.well-known/did.json` and `/.well-known/jwks.json` MUST include RFC 8615 headers when `capabilities.well_known_rfc8615=true`:
- `Cache-Control: no-cache, no-store, must-revalidate`
- `Vary: Accept`
- `X-Content-Type-Options: nosniff`

---

## 4. Message Signing — `stable`

When `capabilities.identity` contains `"ed25519"`, outbound messages MAY be signed.

### 4.1 Signature Header

```
X-ACP-Signature: <base64url(Ed25519 signature of canonical body)>
X-ACP-Public-Key: <base64url(public key)>
```

Canonical body: UTF-8 JSON serialization of the message envelope (no pretty-printing, keys sorted).

### 4.2 Verification

Receivers SHOULD verify when both headers are present:

1. Decode `X-ACP-Public-Key` → 32-byte Ed25519 public key
2. Compute `did:acp:<base64url(public_key)>` and compare to AgentCard `identity.did`
3. Verify `X-ACP-Signature` against canonical body

Verification failure SHOULD return `401 ERR_IDENTITY_MISMATCH`.

---

## 5. `trust.signals[]` — `stable`

`trust.signals` is an optional array in AgentCard that enumerates verifiable trust evidence:

```json
{
  "trust": {
    "signals": [
      {
        "type":     "jwks",
        "endpoint": "/.well-known/jwks.json",
        "key_id":   "did:acp:<base64url(public_key)>"
      },
      {
        "type":     "ed25519_identity",
        "did":      "did:acp:<base64url(public_key)>",
        "endpoint": "/.well-known/did.json"
      },
      {
        "type":     "ca_cert",
        "issuer":   "CN=MyOrg CA",
        "endpoint": "/.well-known/ca.crt"
      }
    ]
  }
}
```

### 5.1 Signal Type Reference

| `type` | Stability | Description |
|--------|-----------|-------------|
| `"jwks"` | **stable** | RFC 7517 JWKS endpoint; peer can fetch and verify public key |
| `"ed25519_identity"` | **stable** | DID Document endpoint; peer can resolve `did:acp:` identifier |
| `"ca_cert"` | **experimental** | CA certificate chain; endpoint returns PEM-encoded cert |
| `"hmac_shared"` | **experimental** | HMAC shared-secret in use; no endpoint (out-of-band exchange) |

Consumers MUST ignore unknown `type` values (forward compatibility).

---

## 6. `capabilities.groups.identity` — `stable`

Since v2.46, identity capabilities are grouped under `capabilities.groups.identity`:

```json
{
  "capabilities": {
    "identity": "ed25519+ca",
    "groups": {
      "identity": {
        "ed25519":  true,
        "hmac":     false,
        "jwks":     true,
        "did":      true,
        "ca_cert":  true
      }
    }
  }
}
```

| Sub-field | Type | Description |
|-----------|------|-------------|
| `ed25519` | bool | Ed25519 keypair active |
| `hmac` | bool | HMAC-SHA256 signing active |
| `jwks` | bool | `/.well-known/jwks.json` available |
| `did` | bool | `/.well-known/did.json` available |
| `ca_cert` | bool | CA certificate present in `identity.ca_cert` |

---

## 7. Verification Model

ACP does not mandate a verification strategy. Consumers SHOULD follow this decision matrix:

| Verifier Policy | Accept When |
|-----------------|-------------|
| `did_only` | `did:acp:` signature valid |
| `ca_only` | CA certificate chain valid to trusted root |
| `both_required` | Both `did:acp:` AND CA valid (max security) |
| `either` | At least one passes (max interoperability) |
| `none` | Skip verification — accept asserted identity |

The verifier's policy is local configuration and MUST NOT be transmitted to the peer.

---

## 8. CLI Reference

```bash
# No identity (v0.7 compatible)
python3 acp_relay.py --name MyAgent

# Self-sovereign Ed25519
python3 acp_relay.py --name MyAgent --identity

# Hybrid: Ed25519 + CA certificate from file
python3 acp_relay.py --name MyAgent --identity --ca-cert /path/to/agent.crt

# Hybrid: inline PEM
python3 acp_relay.py --name MyAgent --identity \
  --ca-cert "-----BEGIN CERTIFICATE-----\nMIIB...\n-----END CERTIFICATE-----"
```

`--ca-cert` without `--identity` is silently ignored (warning logged).

---

## 9. Conformance Requirements

Implementations claiming `capabilities.identity = "ed25519"` MUST:

1. Generate an Ed25519 keypair on first `--identity` invocation; persist to disk.
2. Include `identity.scheme`, `identity.public_key`, and `identity.did` in AgentCard.
3. Serve `/.well-known/did.json` (200) when identity is active.
4. Serve `/.well-known/jwks.json` (200) when identity is active.
5. Return `404` on both endpoints when `--identity` is not active.
6. Include `X-ACP-Public-Key` header in all signed messages.
7. Derive `did:acp:` as `"did:acp:" + base64url(public_key_bytes)` (no padding).

Implementations SHOULD:

- Verify incoming message signatures when `trust.signals[]` contains `"ed25519_identity"` or `"jwks"`.
- Return `401 ERR_IDENTITY_MISMATCH` on signature verification failure.
- Include `trust.signals[]` in AgentCard when identity is active.
- Populate `capabilities.groups.identity` for structured capability discovery.

Implementations MAY:

- Support `"ed25519+ca"` scheme for hybrid verification.
- Expose additional trust signals beyond `"jwks"` and `"ed25519_identity"`.

---

## 10. Backward Compatibility

| Version | Identity state | Compatibility |
|---------|---------------|---------------|
| v0.1–v0.6 | No identity (`identity: null`) | ✅ Fully compatible — identity fields optional |
| v0.7 | HMAC signing (`scheme: "hmac"`) | ✅ Compatible — HMAC and Ed25519 coexist |
| v0.8–v1.4 | Self-sovereign (`scheme: "ed25519"`) | ✅ Strict subset of v2.0 |
| v1.5 | Hybrid Draft (`scheme: "ed25519+ca"`) | ✅ Promoted to stable in v2.0 |

No breaking changes from any prior version.

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| v0.8 | 2026-03-21 | Ed25519 self-sovereign identity; `did:acp:`; `/.well-known/did.json` |
| v1.3 | 2026-03-24 | DID Document `service` endpoint; `assertionMethod` field |
| v1.5 | 2026-03-24 | Hybrid model: `ed25519+ca` scheme; `ca_cert` field (Draft) |
| **v2.0** | **2026-04-04** | **Status → Stable; JWKS §3.2; `trust.signals[]` §5; `capabilities.groups.identity` §6; Conformance Requirements §9; full backward compat matrix §10** |

---

*ACP Identity Specification v2.0 — Stable | Reference impl: `relay/acp_relay.py` (v2.47+)*
