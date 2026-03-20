# ACP Identity Extension — v0.8

> Status: **Stable** (implemented in `relay/acp_relay.py` v0.8-dev)  
> Last updated: 2026-03-21

---

## Overview

ACP v0.8 introduces an **optional Ed25519 identity extension** that allows agents to
cryptographically sign their messages without any PKI, certificate authority, or
central key registry.

**Design constraints (non-negotiable):**
- ❌ No certificate authorities
- ❌ No mandatory key registration
- ❌ No revocation infrastructure (deferred to v1.0)
- ✅ Self-sovereign: agent generates its own keypair
- ✅ Optional: agents without `identity.scheme = "ed25519"` are fully unaffected
- ✅ Upgrade path from HMAC (v0.7) — both can be active simultaneously
- ✅ Verifiable by anyone holding the public key (no shared secret required)

---

## Wire Format

Every outbound message from an identity-enabled agent includes an `identity` block:

```json
{
  "type": "acp.message",
  "message_id": "msg_abc123",
  "ts": "2026-03-21T04:13:00Z",
  "from": "Agent-A",
  "role": "user",
  "parts": [{"type": "text", "content": "hello"}],
  "identity": {
    "scheme":     "ed25519",
    "public_key": "<base64url-encoded 32-byte Ed25519 public key>",
    "sig":        "<base64url-encoded 64-byte Ed25519 signature>"
  }
}
```

### Signature Input (Canonical Form)

The signature covers a canonical JSON serialization of the **full message envelope**,
excluding the `identity.sig` field itself:

```
payload = JSON.stringify(
  { all message fields except "identity" },
  { keys: sorted, separators: (",", ":"), ensure_ascii: false }
)
sig = Ed25519.sign(private_key, payload.encode("utf-8"))
```

Python reference:
```python
canonical = {k: v for k, v in msg.items() if k != "identity"}
payload = json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
sig_bytes = private_key.sign(payload)
identity["sig"] = base64.urlsafe_b64encode(sig_bytes).rstrip(b"=").decode()
```

> **Why exclude `identity` from canonical form?**  
> The `identity` block is added *after* the message is fully constructed.
> Excluding it avoids a circular dependency: we can't sign what we're building.
> The public key in `identity.public_key` is trusted because it's self-declared;
> receivers verify the sig against it.

---

## AgentCard Declaration

Agents with Ed25519 identity declare it in their AgentCard:

```json
{
  "capabilities": {
    "identity": "ed25519"
  },
  "identity": {
    "scheme":     "ed25519",
    "public_key": "<base64url>"
  }
}
```

Agents without identity: `capabilities.identity = "none"` (or field absent).

---

## Key Storage

The reference implementation (`relay/acp_relay.py`) stores the keypair at
`~/.acp/identity.json` (configurable via `--identity <path>`):

```json
{
  "scheme":      "ed25519",
  "public_key":  "<base64url 32 bytes>",
  "private_key": "<base64url 32 bytes>",
  "created_at":  "2026-03-21T04:13:00Z"
}
```

File permissions: `0600` (owner read/write only).

On first `--identity` invocation, the keypair is auto-generated and saved.
Subsequent runs load the existing keypair — the agent's identity is **persistent across sessions**.

---

## Verification Policy

**Warn-only, never drop.** This matches the HMAC (v0.7) policy:

- If `identity.sig` verifies correctly → `_ed25519_verified = true` on the message object
- If `identity.sig` is invalid → log warning + `_ed25519_invalid = true`, message still delivered
- If `cryptography` library not installed → verification skipped, message accepted

This ensures forward compatibility: agents running without the `cryptography` library
continue to receive signed messages from identity-enabled peers.

---

## HMAC vs Ed25519 Coexistence

Both signing schemes can be active simultaneously on the same agent:

| | HMAC (v0.7) | Ed25519 (v0.8) |
|--|-------------|----------------|
| **Setup** | Shared secret (pre-agreed out-of-band) | Self-sovereign keypair |
| **Verifiable by** | Only parties who know the secret | Anyone with public key |
| **Use case** | Closed deployments (home lab, team) | Open federation, audit trails |
| **CLI flag** | `--secret <key>` | `--identity [path]` |
| **Overhead** | ~1ms HMAC-SHA256 | ~2ms Ed25519 sign/verify |
| **Wire field** | `msg.sig` (hex string) | `msg.identity.sig` (base64url) |

Use HMAC when peers are known and a shared secret is practical.  
Use Ed25519 when peer identity must be verifiable by third parties or across sessions
without sharing a secret.

---

## Usage

```bash
# Generate identity on first run (saves to ~/.acp/identity.json)
python3 acp_relay.py --name "Agent-A" --identity

# Use existing identity keypair
python3 acp_relay.py --name "Agent-A" --identity ~/.acp/identity.json

# Use custom keypair location
python3 acp_relay.py --name "Agent-A" --identity /path/to/my-id.json

# Combine with HMAC (both active)
python3 acp_relay.py --name "Agent-A" --identity --secret "shared-key"
```

---

## Implementation Notes

### Dependency

```bash
pip install cryptography   # Ed25519 via cryptography.hazmat.primitives
```

If `cryptography` is not installed:
- `--identity` flag logs a warning and disables identity
- Inbound `identity` blocks from peers are accepted without verification

### Canonical JSON Stability

The canonical form (`sort_keys=True, separators=(",",":")`) is deterministic across
Python versions and platforms for all JSON-safe values (strings, numbers, booleans, null).

Avoid putting `float('inf')`, `float('nan')`, or non-JSON types in message envelopes —
they break canonical serialization on some platforms.

### Key Rotation

To rotate the Ed25519 keypair:
1. Delete or rename `~/.acp/identity.json`
2. Restart with `--identity` — a new keypair is auto-generated
3. Notify peers of the new `public_key` via AgentCard exchange

Formal revocation (CRL / OCSP-style) is deferred to v1.0.

---

## Security Properties

| Property | Provided? | Notes |
|----------|-----------|-------|
| Message authenticity | ✅ | Signature proves keypair ownership |
| Message integrity | ✅ | Any tampering invalidates sig |
| Replay prevention | ⚠️ Partial | `message_id` dedup prevents server-side replay; no timestamp window enforced |
| Non-repudiation | ✅ | Ed25519 sig is cryptographically binding |
| Key freshness | ❌ | No revocation in v0.8; see Key Rotation above |
| Confidentiality | ❌ | ACP does not encrypt messages (use TLS at transport layer) |

---

## Comparison with A2A Agent Passport System (APS)

ACP's Ed25519 extension is intentionally minimal compared to A2A's APS:

| Feature | APS (A2A #1575) | ACP v0.8 Ed25519 |
|---------|-----------------|-----------------|
| Algorithm | Ed25519 | Ed25519 |
| Key storage | Managed by APS framework | Self-sovereign (`~/.acp/identity.json`) |
| Delegation | ✅ Scoped delegation chains | ❌ Not supported |
| Revocation | ✅ Cascade revocation | ❌ Manual rotation only |
| Registration | Required (APS registry) | ❌ None required |
| Test coverage | 894 tests, 36 modules | Lightweight unit tests |
| Use case | Enterprise agent authorization | Personal/team attribution |

ACP's approach: **zero infrastructure, maximum simplicity, auditable attribution**.  
APS's approach: **enterprise-grade, full lifecycle management**.

Neither is wrong — they target different deployment contexts.

---

*Spec version: v0.8 | Implemented: 2026-03-21 | See also: [HMAC v0.7](transports.md), [Error Codes v0.6](error-codes.md)*
