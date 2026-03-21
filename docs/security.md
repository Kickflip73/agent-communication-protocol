# ACP Security Model

**Version:** 1.0  
**Date:** 2026-03-21  
**Applies to:** `acp_relay.py` v1.0.0+

---

## Overview

ACP provides two optional, independent security mechanisms:

| Mechanism | Purpose | Requires |
|-----------|---------|---------|
| **HMAC-SHA256** (§1) | Message integrity + peer authentication for closed deployments | Shared secret (out-of-band) |
| **Ed25519 Identity** (§2) | Cryptographic sender identity for open deployments | `pip install cryptography` |

Both can be active simultaneously — they are complementary, not mutually exclusive.

**What ACP does NOT provide:**
- Confidentiality (messages are plaintext over WebSocket/HTTP)
- Forward secrecy
- Key exchange / key agreement protocol
- Certificate authority or PKI

For confidentiality, terminate TLS at a load balancer or reverse proxy (see §4).

---

## 1. HMAC-SHA256 Signing (v0.7+)

### How it works

When `--secret <key>` is configured, every **outbound** message is signed:

```
sig = HMAC-SHA256(secret_bytes, "{message_id}:{ts}").hexdigest()
```

The resulting hex string is appended as the `sig` field to the message envelope.

**Inbound verification:** if `sig` is present in a received message and a secret is configured,
the relay verifies using `hmac.compare_digest()` (constant-time, no timing oracle). On mismatch:
- A warning is logged
- The message is **not dropped** (warn-only, per ACP spec §7.1)
- The message object has `_sig_invalid=true` set for application-level inspection

If no secret is configured, `sig` fields in received messages are silently ignored
(backward-compatible interoperability).

### Audit findings

| Check | Result | Notes |
|-------|--------|-------|
| Constant-time comparison | ✅ PASS | `hmac.compare_digest()` used throughout |
| Timing oracle in error response | ✅ PASS | Error path identical for valid/invalid sig |
| Payload determinism | ✅ PASS | `f"{message_id}:{ts}"` — fixed format |
| message_id unpredictability | ✅ PASS | `msg_<16 hex chars>` from `secrets.token_hex(8)` |
| Secret stored in memory only | ✅ PASS | `_hmac_secret: bytes`, never written to disk |
| Replay attack prevention | ⚠️ PARTIAL | `message_id` makes exact replay detectable if tracked; no server-side timestamp window check |
| Key length recommendation | ℹ️ INFO | Any length accepted; recommend ≥32 bytes for 128-bit security |

### Known limitation: replay window

ACP HMAC does **not** implement a server-side timestamp window check. A captured
message with a valid `sig` could theoretically be replayed. Mitigations:
- `message_id` uniqueness: server MAY deduplicate within a session (opt-in)
- Add `--replay-window` flag (planned for v1.1) to enforce timestamp check

**Risk level:** Low for typical Agent-to-Agent use. If replay resistance is critical,
layer a session-level nonce or use Ed25519 identity (§2) instead.

### What HMAC protects

| Threat | Protected? |
|--------|-----------|
| Message tampering in transit | ✅ Yes (integrity) |
| Impersonation by unknown peer | ✅ Yes (authentication) |
| Eavesdropping / confidentiality | ❌ No (use TLS, §4) |
| Replay attacks | ⚠️ Partial (message_id uniqueness only) |
| Key compromise | ❌ No — rotate secret out-of-band |

---

## 2. Ed25519 Identity (v0.8+)

### How it works

When `--identity [path]` is configured, every **outbound** message includes an `identity` block:

```json
"identity": {
  "scheme":     "ed25519",
  "public_key": "<base64url 32-byte public key>",
  "sig":        "<base64url 64-byte Ed25519 signature>"
}
```

**Signing input:** canonical JSON of the full message envelope, excluding `identity.sig`:

```python
canonical = {k: v for k, v in msg.items() if k != "identity"}
payload = json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",",":")).encode()
```

The canonical form uses `sort_keys=True` and compact separators to ensure byte-for-byte
reproducibility across implementations.

**Keypair storage:** `~/.acp/identity.json` (auto-generated on first run, `chmod 0600`).

**Verification:** warn-only on mismatch; message is accepted even if `cryptography` not installed.

### Audit findings

| Check | Result | Notes |
|-------|--------|-------|
| Key file permissions | ✅ PASS | `path.chmod(0o600)` enforced on creation |
| Canonical form determinism | ✅ PASS | `sort_keys=True, separators=(",",":")` — byte-identical across Python versions |
| `identity.sig` excluded from payload | ✅ PASS | `{k: v for k, v in msg.items() if k != "identity"}` |
| `InvalidSignature` exception handling | ✅ PASS | Caught, returns `False`; no exception leak |
| Graceful fallback without `cryptography` | ✅ PASS | `_ED25519_AVAILABLE` flag checked at call sites |
| Key generation entropy | ✅ PASS | `Ed25519PrivateKey.generate()` uses OS CSPRNG |
| Private key in-memory only | ✅ PASS | `_ed25519_private` never serialized post-load |
| Key rotation | ℹ️ INFO | Delete `~/.acp/identity.json` and restart to rotate |

### What Ed25519 protects

| Threat | Protected? |
|--------|-----------|
| Sender impersonation | ✅ Yes (cryptographic proof of origin) |
| Message tampering | ✅ Yes (signature covers full envelope) |
| Non-repudiation | ✅ Yes (verifiable by any party with public key) |
| Confidentiality | ❌ No (public key visible; use TLS, §4) |
| Forward secrecy | ❌ No (static keypair) |
| Key revocation | ❌ No (no PKI/CRL; manual rotation only) |

### Coexistence with HMAC

HMAC and Ed25519 may be active simultaneously:

```bash
acp-relay --secret "shared-key" --identity
```

- HMAC `sig` is computed first, then included in the Ed25519 signing payload
- This means Ed25519 signature covers the HMAC sig — no ordering vulnerability
- AgentCard reports both: `capabilities.hmac_signing=true` and `capabilities.identity="ed25519"`

---

## 3. Comparison

| Property | HMAC-SHA256 | Ed25519 Identity |
|----------|-------------|-----------------|
| Key type | Symmetric (shared secret) | Asymmetric (keypair) |
| Requires shared state | Yes (both sides need secret) | No (public key in AgentCard) |
| Verifiable by third party | No | Yes |
| Non-repudiation | No | Yes |
| Best for | Closed deployments (known peers) | Open deployments (any peer) |
| Setup | `--secret <key>` | `--identity` (auto-generates) |
| Dependency | stdlib `hmac` | `cryptography` (optional) |

---

## 4. Transport Security Recommendations

ACP over plain HTTP/WS provides **no confidentiality**. For production deployments:

### Option A: Reverse proxy with TLS (recommended)

```
[Agent A] ──WebSocket──► [nginx/caddy TLS termination] ──► [Agent B :7801]
[Client]  ──HTTPS──────► [nginx/caddy TLS termination] ──► [relay :7901]
```

Example (Caddy):
```
youragent.example.com {
    reverse_proxy localhost:7901
    reverse_proxy /ws localhost:7801
}
```

### Option B: Cloudflare Tunnel

```bash
cloudflared tunnel --url http://localhost:7901
# Provides HTTPS + certificate automatically
```

### Option C: Use the built-in Cloudflare Worker relay (Binding C)

```bash
acp-relay --relay "acp+wss://your-worker.workers.dev/..."
```

This transport uses HTTPS by default. See [transports.md](transports.md) §Binding-C.

---

## 5. Known Limitations Summary

| Limitation | Severity | Workaround / Roadmap |
|-----------|----------|---------------------|
| No replay-window timestamp check | Low | Message-ID dedup (opt-in); v1.1 `--replay-window` planned |
| No confidentiality | Medium | Use TLS termination (§4) |
| No forward secrecy | Low–Medium | Rotate secret/keypair periodically |
| No key revocation infrastructure | Low | Manual rotation: delete `~/.acp/identity.json` |
| Ed25519 verification is warn-only | By design | Per ACP spec §7.2: graceful degradation |

---

## 6. Security Audit History

| Version | Date | Auditor | Findings |
|---------|------|---------|---------|
| v1.0.0 | 2026-03-21 | J.A.R.V.I.S. (internal) | 8 PASS, 1 PARTIAL (replay window), 2 INFO — see §1.2 and §2.2 |

---

*Security questions or disclosures: open an issue at https://github.com/Kickflip73/agent-communication-protocol/issues*
