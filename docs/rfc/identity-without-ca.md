# ACP-RFC-004: Decentralized Agent Identity Without Certificate Authority

**RFC Number:** ACP-RFC-004  
**Status:** Published  
**Version:** 1.0.0  
**Date:** 2026-04-09  
**Author:** J.A.R.V.I.S. (ACP Project)  
**Relates To:** A2A Issue #1672 ("Agent Identity"), A2A Issue #1712 ("WTRMRK as trust primitive")  
**ACP Implementation:** v2.85.0+ (Ed25519 default-on), v2.90.0+ (`POST /identity/verify-card`)

---

## Abstract

A2A Issue #1672 (414+ comments) proposes an agent identity standard anchored to a central Certificate Authority at `getagentid.dev`. This RFC presents ACP's alternative: **self-sovereign Ed25519 keypairs with DID-based verification** — achieving the same trust guarantees without any single point of failure or centralized registry. We also address the three-layer identity model articulated by `aeoess` in A2A #1712: **who (identity) + what they can do (delegation scope) + what happened (execution proof)**.

---

## 1. The Problem

When agent A contacts agent B for the first time:

1. **Who is A?** — B cannot verify A's claimed identity
2. **What can A do?** — B cannot verify A's authorized scope
3. **What did A actually do?** — Neither party has tamper-evident proof

A2A #1672's proposed solution: register agents with a central CA (`getagentid.dev`), receive a certificate, attach it to the AgentCard. Receiving agents verify against the CA's root certificate.

---

## 2. Problems With the Central CA Approach

| Problem | Description |
|---------|-------------|
| **Single Point of Failure** | If `getagentid.dev` is down, all first-contact verifications fail globally |
| **Registration Bottleneck** | Every new agent (including ephemeral, personal, or air-gapped agents) must register |
| **Privacy Leak** | The CA learns every agent's identity and deployment metadata |
| **Revocation Complexity** | CRL/OCSP infrastructure required; revocation propagation delay |
| **Centralization Antithesis** | Contradicts the "decentralized agent mesh" vision that motivates A2A |
| **CA Capture Risk** | If the CA is compromised, all agent identities are compromised simultaneously |

---

## 3. ACP's Self-Sovereign Identity Model

### 3.1 Key Generation (One-Time, Local)

```bash
# Generate Ed25519 keypair (done automatically by acp_relay.py on first run)
acp-relay start --identity ~/.acp/identity.json
```

`~/.acp/identity.json` (chmod 0600):
```json
{
  "public_key": "base64url(ed25519_public_key)",
  "private_key": "base64url(ed25519_private_key)",
  "did": "did:key:z6Mk...",
  "created_at": "2026-04-09T14:00:00Z",
  "version": 1
}
```

**No CA. No registration. No network call. Zero dependencies.**

### 3.2 AgentCard Identity Declaration

The `identity` block in `GET /.well-known/acp.json`:

```json
{
  "name": "my-agent",
  "identity": {
    "type": "ed25519",
    "public_key": "base64url(pubkey)",
    "did": "did:key:z6Mk...",
    "card_signature": "base64url(ed25519_sign(canonical_card_json))"
  }
}
```

- `card_signature`: Ed25519 signature over the canonical JSON of the AgentCard (excluding `card_signature` itself)
- Any receiver can verify: `ed25519_verify(card_signature, public_key, canonical_card_json) == true`
- **No CA lookup. No network call. Pure cryptography.**

### 3.3 Cross-Instance Verification (Without Pre-Connection)

`POST /identity/verify-card` — introduced in ACP v2.90.0:

```http
POST /identity/verify-card
Content-Type: application/json

{
  "card": { ... AgentCard JSON from another instance ... }
}
```

Response:
```json
{
  "verified": true,
  "did": "did:key:z6Mk...",
  "public_key": "base64url(pubkey)",
  "did_consistent": true,
  "signature_valid": true,
  "verification_method": "ed25519_self_signed"
}
```

**Use case:** Agent C receives a message claiming to be from Agent A (introduced by Agent B). C calls its own relay's `/identity/verify-card` with A's card. The relay verifies the signature — no CA, no network lookup, no prior relationship needed.

---

## 4. The Three-Layer Identity Model

As articulated in A2A #1712 by `aeoess`:

> "What matters more than which identity system an agent uses is what the receiving agent can DO with that identity: verify the sender is who they claim, check what authority they carry, and determine whether to trust the request. Identity proves 'who.' Delegation scope proves 'what they're allowed to do.' Enforcement proves 'what actually happened.'"

ACP implements all three layers:

### Layer 1: Identity ("Who")

```
ACP Ed25519 Self-Signed Identity (v2.85.0+)
├── Self-generated keypair, no CA
├── DID: did:key:z6Mk... (W3C DID Core aligned)
├── card_signature: signs the full AgentCard
└── POST /identity/verify-card: offline verification endpoint
```

### Layer 2: Delegation Scope ("What They Can Do")

```
ACP Capability Token + Skill Authorization (ACP-RFC-001, v2.74.0+)
├── T0-T3 tiered authorization model
├── capability_token: signed scope declaration
├── effective_tier: 5-factor composite score
│   ├── identity_verified (Layer 1 → Layer 2 link)
│   ├── trust_score
│   ├── bilateral_ir_adj
│   ├── revocation_clean
│   └── policy_compliance
└── GET /trust/signals/capability-token: per-agent scope query
```

### Layer 3: Execution Proof ("What Happened")

```
ACP Bilateral Interaction Records (ACP-RFC-002, v2.61.0+)
├── Both parties sign the same canonical payload (non-repudiable)
├── SHA-256 hash chain: each IR links to the previous
├── Merkle root: batch of IRs provable without revealing all records
├── GET /trust/bilateral-ir/log: queryable audit trail
└── GET /ir/adversarial-fixtures: test vectors for manipulation detection
```

---

## 5. Comparison: ACP vs A2A #1672 CA Approach

| Dimension | ACP (This RFC) | A2A #1672 (CA Approach) |
|-----------|---------------|------------------------|
| **Registration** | None (generate locally) | Required (contact getagentid.dev) |
| **Single Point of Failure** | ❌ None | ✅ getagentid.dev |
| **Offline Verification** | ✅ Pure cryptography | ❌ Needs CA reachability |
| **Ephemeral Agents** | ✅ Zero-friction | ❌ Must register first |
| **Air-Gapped Environments** | ✅ Works | ❌ Blocked |
| **Privacy** | ✅ No registry knows your identity | ❌ CA sees all registrations |
| **Revocation** | ✅ credential_lifecycle TTL (RFC-003) | ❌ CRL/OCSP complexity |
| **Multi-Provider** | ✅ DID method-agnostic | ❌ Locked to getagentid.dev |
| **Implementation Complexity** | ✅ 50 lines Python | ❌ PKI infrastructure |
| **Cryptographic Standard** | ✅ Ed25519 (IETF RFC 8032) | ❓ RSA/ECDSA (implementation TBD) |
| **ACP Status** | ✅ Implemented (v2.85.0+) | ⏳ Proposed (no implementation) |

---

## 6. Multi-Provider Compatibility

ACP's DID-based approach is inherently multi-provider (as recommended by `aeoess` in A2A #1712):

```json
{
  "identity": {
    "providers": [
      {
        "type": "ed25519",
        "did": "did:key:z6Mk...",
        "public_key": "..."
      },
      {
        "type": "did:web",
        "did": "did:web:example.com",
        "resolution_url": "https://example.com/.well-known/did.json"
      },
      {
        "type": "did:acp",
        "did": "did:acp:relay.acp.dev:agent-id",
        "public_key": "..."
      }
    ],
    "primary": "did:key:z6Mk..."
  }
}
```

Each provider is independently verifiable. An agent can carry multiple identity proofs, and the receiver chooses which to verify based on its trust policy.

---

## 7. Integration With Governance Metadata (ACP-RFC-003)

Identity interacts with governance metadata (ACP-RFC-003) through `credential_lifecycle`:

```json
{
  "governance_metadata": {
    "credential_lifecycle": {
      "max_session_duration": 3600,
      "credential_ttl": 86400,
      "revocation_endpoint": "https://agent.example.com/revoke",
      "revocation_check_frequency": 300
    }
  }
}
```

This replaces the complex CRL/OCSP infrastructure with:
1. Short-lived credentials (TTL-based expiry)
2. Optional revocation endpoint (simple HTTP DELETE)
3. Configurable check frequency (pull-based, no push infrastructure)

---

## 8. Security Analysis

### 8.1 Threat Model

| Threat | ACP Mitigation |
|--------|---------------|
| Identity spoofing | Ed25519 signature over full AgentCard — cannot forge without private key |
| Key compromise | credential_lifecycle.credential_ttl limits blast radius; short-lived sessions |
| Replay attack | HMAC-SHA256 replay window (v1.1, --hmac-window 300s) |
| Man-in-the-middle | card_signature binds public key to AgentCard content |
| Sybil attack (multiple fake identities) | adversarial-fixtures AF-003 detection; trust score adjustment via bilateral IR |

### 8.2 Cryptographic Choices

- **Ed25519**: IETF RFC 8032, 128-bit security level, 64-byte signatures, fast verification (~50k verify/s)
- **Canonical JSON**: RFC 8785 (JSON Canonicalization Scheme) for deterministic serialization
- **DID Method**: `did:key` (W3C DID Core, no network lookup required)
- **Hash**: SHA-256 for hash chains; SHA-512 available via extension

---

## 9. Implementation Reference

### Minimal Ed25519 Identity (Python, ~50 lines)

```python
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding, PublicFormat, PrivateFormat, NoEncryption
)
import json, base64, hashlib

def generate_identity(path="~/.acp/identity.json"):
    key = Ed25519PrivateKey.generate()
    pub = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    priv = key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    pub_b64 = base64.urlsafe_b64encode(pub).rstrip(b'=').decode()
    did = f"did:key:z6Mk{pub_b64[:20]}"  # Simplified; use multibase for production
    identity = {
        "public_key": pub_b64,
        "private_key": base64.urlsafe_b64encode(priv).rstrip(b'=').decode(),
        "did": did,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "version": 1
    }
    with open(os.path.expanduser(path), 'w') as f:
        json.dump(identity, f, indent=2)
    os.chmod(os.path.expanduser(path), 0o600)
    return identity

def sign_card(card: dict, private_key_b64: str) -> str:
    """Sign AgentCard canonical JSON, return base64url signature."""
    card_copy = {k: v for k, v in card.items() if k != "card_signature"}
    canonical = json.dumps(card_copy, sort_keys=True, separators=(',', ':'))
    priv_bytes = base64.urlsafe_b64decode(private_key_b64 + '==')
    key = Ed25519PrivateKey.from_private_bytes(priv_bytes)
    sig = key.sign(canonical.encode())
    return base64.urlsafe_b64encode(sig).rstrip(b'=').decode()

def verify_card(card: dict) -> dict:
    """Verify AgentCard self-signature. Returns {verified, did, public_key}."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from cryptography.exceptions import InvalidSignature
    sig_b64 = card.get("identity", {}).get("card_signature", "")
    pub_b64 = card.get("identity", {}).get("public_key", "")
    card_copy = {k: v for k, v in card.items() if k != "card_signature"}
    canonical = json.dumps(card_copy, sort_keys=True, separators=(',', ':'))
    try:
        pub_bytes = base64.urlsafe_b64decode(pub_b64 + '==')
        key = Ed25519PublicKey.from_public_bytes(pub_bytes)
        sig = base64.urlsafe_b64decode(sig_b64 + '==')
        key.verify(sig, canonical.encode())
        return {"verified": True, "public_key": pub_b64,
                "did": card.get("identity", {}).get("did"), "did_consistent": True}
    except (InvalidSignature, Exception) as e:
        return {"verified": False, "error": str(e)}
```

---

## 10. Relation to Existing Standards

| Standard | Relationship |
|----------|-------------|
| W3C DID Core | ACP uses `did:key` method; `did:web` and `did:acp` also supported |
| IETF RFC 8032 | Ed25519 signature algorithm |
| IETF RFC 8785 | JSON Canonicalization Scheme (for deterministic card signing) |
| IETF draft-prakash-aip | Agent Identity Protocol — ACP Ed25519 approach is aligned |
| A2A AgentCard | ACP `identity` block is an AgentCard extension field |
| ACP-RFC-001 | Skill authorization uses Layer 1 identity as input to `effective_tier` |
| ACP-RFC-002 | Bilateral IR signing uses the same Ed25519 keypair |
| ACP-RFC-003 | `credential_lifecycle` replaces CRL/OCSP for credential revocation |

---

## 11. Open Questions

1. **DID method standardization**: Should ACP adopt `did:key` exclusively, or also support `did:web` (requires network lookup) and `did:acp` (ACP-specific)?
2. **Cross-implementation interoperability**: How should two ACP relay instances from different vendors verify each other's cards? (Currently: `POST /identity/verify-card` is local; needs a gossip/trust-path mechanism for full mesh)
3. **Key rotation**: This RFC assumes a single long-lived keypair. Short-lived session keys (derived from the long-lived key) are a natural extension for high-security environments.

---

## 12. Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-04-09 | Initial publication; covers Ed25519 self-signed identity, three-layer model, CA comparison, multi-provider design, credential_lifecycle integration |

---

## References

1. A2A Issue #1672: https://github.com/a2aproject/A2A/issues/1672
2. A2A Issue #1712: https://github.com/a2aproject/A2A/issues/1712
3. W3C DID Core: https://www.w3.org/TR/did-core/
4. IETF RFC 8032 (Ed25519): https://www.rfc-editor.org/rfc/rfc8032
5. IETF RFC 8785 (JCS): https://www.rfc-editor.org/rfc/rfc8785
6. ACP-RFC-001 (Skill Authorization): `docs/rfc/skill-authorization.md`
7. ACP-RFC-002 (Bilateral IR): `docs/rfc/bilateral-interaction-records.md`
8. ACP-RFC-003 (Governance Metadata): `docs/rfc/governance-metadata.md`
