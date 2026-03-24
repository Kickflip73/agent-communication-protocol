# ACP Identity v1.5 — Hybrid Identity Model

**Status**: Draft  
**Supersedes**: `identity-v0.8.md` (v0.8 self-sovereign only)  
**Date**: 2026-03-24

---

## Motivation

ACP v0.8/v1.3 shipped `did:acp:` — a self-sovereign Ed25519 identity model.  
ACP v1.5 adds **optional CA-signed certificate support** alongside the existing did:acp: model,
enabling a **hybrid model** where:

- Agent *declares* which identity model(s) it supports
- Verifier *decides* what it trusts

This matches the convergence direction of A2A #1672 (2026-03-24 discussion).

---

## Changes in v1.5

### New field: `identity.ca_cert`

When `--identity` AND `--ca-cert` are both provided, AgentCard `identity` block gains:

```json
{
  "identity": {
    "scheme":     "ed25519+ca",
    "public_key": "<base64url-encoded Ed25519 public key>",
    "did":        "did:acp:<base64url(pubkey)>",
    "ca_cert":    "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----"
  }
}
```

Without `--ca-cert`, behavior is identical to v1.3 (`scheme: "ed25519"`).

### New capability flag: `"ed25519+ca"`

`capabilities.identity` is now a string enum:

| Value | Meaning |
|-------|---------|
| `"none"` | No identity (v0.7 and earlier) |
| `"ed25519"` | Self-sovereign did:acp: only (v0.8–v1.4) |
| `"ed25519+ca"` | Hybrid: did:acp: + CA-signed certificate (v1.5+) |

---

## CLI Usage

```bash
# Self-sovereign only (unchanged from v1.3)
python3 acp_relay.py --name MyAgent --identity

# Hybrid: self-sovereign + CA certificate from file
python3 acp_relay.py --name MyAgent --identity --ca-cert /path/to/agent.crt

# Hybrid: inline PEM string
python3 acp_relay.py --name MyAgent --identity \
  --ca-cert "-----BEGIN CERTIFICATE-----\nMIIB...\n-----END CERTIFICATE-----"
```

`--ca-cert` without `--identity` is silently ignored (warning logged).

---

## Verification Model (Hybrid)

A verifying peer receiving an AgentCard with `scheme: "ed25519+ca"` MAY:

1. **Trust did:acp: only** — verify message signature against `public_key`, ignore `ca_cert`
2. **Trust CA only** — verify `ca_cert` chain to a known root CA, map cert subject to agent name
3. **Trust both** — require both to be valid (max security)
4. **Trust either** — accept if at least one passes (max interoperability)

The verifier's trust policy is local; ACP does not mandate a specific verification strategy.

---

## Backward Compatibility

- Agents without `--ca-cert`: `scheme: "ed25519"`, `ca_cert` field absent. Fully compatible with v1.3.
- Agents without `--identity`: `identity: null`. Fully compatible with v0.7.
- No changes to message signing (Ed25519 signatures unchanged).
- No changes to `/.well-known/did.json` (DID Document unchanged).

---

## Security Notes

- `ca_cert` is transmitted in plaintext over HTTPS (same as `public_key`).
- ACP does not validate the certificate chain internally — verification is the verifier's responsibility.
- The CA certificate SHOULD cover the agent's public key or DID as Subject Alternative Name (SAN).

---

*Specification by J.A.R.V.I.S. — 2026-03-24*
