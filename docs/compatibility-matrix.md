# ACP Compatibility Matrix

> **Updated**: 2026-04-04  
> **Impl ref**: `relay/acp_relay.py` v2.47.1  
> **Spec ref**: `spec/core-v1.0.md` (v2.47, Stable)

This document defines interoperability guarantees across ACP relay versions.
An agent on any version listed here can communicate with an agent on any other listed version,
subject to the per-feature notes.

---

## 1. Version Overview

| Version | Released | Key Features | Status |
|---------|----------|-------------|--------|
| **v0.5** | 2026-02-xx | Basic message send/recv, AgentCard, ping | Supported (minimal) |
| **v0.6** | 2026-03-05 | Peer connect, SSE stream, `/recv` long-poll | Supported |
| **v0.7** | 2026-03-10 | HMAC signing, availability PATCH, extensions | Supported |
| **v0.8** | 2026-03-21 | Ed25519 identity, DID document, JWKS | Supported |
| **v1.0** | 2026-03-24 | Task state machine, pagination, error codes | Supported |
| **v1.3** | 2026-03-28 | Broadcast, typing indicator, read receipts | Supported |
| **v2.47** | 2026-04-04 | RFC 8615 headers, capabilities.groups, identity-v2.0 | **Current** |

---

## 2. Core Protocol Compatibility

> ✅ = Full compat · ⚠️ = Partial (feature degrades gracefully) · ❌ = Not supported · — = N/A

### 2.1 Sending a Message (`POST /message:send`)

| Sender \ Receiver | v0.5 | v0.6 | v0.8 | v1.0 | v1.3 | v2.47 |
|-------------------|------|------|------|------|------|-------|
| **v0.5** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **v0.6** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **v0.8** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **v1.0** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **v1.3** | ⚠️¹ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **v2.47** | ⚠️¹ | ✅ | ✅ | ✅ | ✅ | ✅ |

¹ v1.3+ `broadcast` messages sent to v0.5 are silently ignored (v0.5 has no `/broadcast` endpoint). Direct messages still work.

### 2.2 AgentCard Discovery (`GET /.well-known/acp.json`)

| Client version | v0.5 host | v0.6 host | v0.8 host | v1.0 host | v2.47 host |
|----------------|-----------|-----------|-----------|-----------|------------|
| **v0.5** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **v0.6** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **v0.8** | ⚠️² | ✅ | ✅ | ✅ | ✅ |
| **v1.0** | ⚠️² | ✅ | ✅ | ✅ | ✅ |
| **v2.47** | ⚠️² | ✅ | ✅ | ✅ | ✅ |

² Newer clients parse unknown AgentCard fields with forward-compat rules (unknown fields ignored). Identity/groups fields absent in v0.5 → `null` / feature disabled.

### 2.3 Task Lifecycle (`/tasks`, `/tasks/{id}`, `/tasks/{id}/cancel`)

| Feature | v0.5 | v0.6 | v0.8 | v1.0 | v1.3 | v2.47 |
|---------|------|------|------|------|------|-------|
| `/tasks` list | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| Task state machine (5 states) | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| Task pagination (`limit`/`offset`) | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| Task cancel | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| `created_after` filter | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |

### 2.4 Identity & Trust

| Feature | v0.5 | v0.6 | v0.7 | v0.8 | v1.5 | v2.47 |
|---------|------|------|------|------|------|-------|
| No identity (asserted name) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| HMAC signing | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ |
| Ed25519 self-sovereign | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| `/.well-known/did.json` | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| `/.well-known/jwks.json` | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| `identity.ca_cert` (hybrid) | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ |
| `trust.signals[]` | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| RFC 8615 well-known headers | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |

### 2.5 Transport & NAT Traversal

| Feature | v0.5 | v0.6 | v0.8 | v1.3 | v2.47 |
|---------|------|------|------|------|-------|
| Direct TCP (`acp://`) | ✅ | ✅ | ✅ | ✅ | ✅ |
| NAT Level-1 (direct) | ✅ | ✅ | ✅ | ✅ | ✅ |
| NAT Level-2 (hole-punch) | ❌ | ✅ | ✅ | ✅ | ✅ |
| NAT Level-3 (relay fallback) | ❌ | ✅ | ✅ | ✅ | ✅ |
| HTTP-SSE transport | ❌ | ❌ | ✅ | ✅ | ✅ |
| WebSocket transport | ✅ | ✅ | ✅ | ✅ | ✅ |

---

## 3. AgentCard Field Compatibility

Fields introduced in each version. **Older agents silently ignore unknown fields** (forward-compat).

| AgentCard Field | Introduced | v0.5 | v0.6 | v0.8 | v1.0 | v2.47 |
|----------------|------------|------|------|------|------|-------|
| `agent_name` | v0.1 | ✅ | ✅ | ✅ | ✅ | ✅ |
| `version` | v0.1 | ✅ | ✅ | ✅ | ✅ | ✅ |
| `capabilities.*` (flat) | v0.5 | ✅ | ✅ | ✅ | ✅ | ✅ |
| `link` | v0.6 | — | ✅ | ✅ | ✅ | ✅ |
| `peers` | v0.6 | — | ✅ | ✅ | ✅ | ✅ |
| `identity` block | v0.8 | — | — | ✅ | ✅ | ✅ |
| `capabilities.identity` | v0.8 | — | — | ✅ | ✅ | ✅ |
| `skills[]` | v1.0 | — | — | — | ✅ | ✅ |
| `limitations` | v1.0 | — | — | — | ✅ | ✅ |
| `availability` | v1.3 | — | — | — | — | ✅ |
| `trust.signals[]` | v2.47 | — | — | — | — | ✅ |
| `capabilities.groups` | v2.46 | — | — | — | — | ✅ |
| `capabilities.well_known_rfc8615` | v2.47 | — | — | — | — | ✅ |

---

## 4. Cross-Version Connection Matrix

Can Agent A (row) successfully connect to and exchange messages with Agent B (column)?

| A \ B | v0.5 | v0.6 | v0.8 | v1.0 | v1.3 | v2.47 |
|-------|------|------|------|------|------|-------|
| **v0.5** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **v0.6** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **v0.8** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **v1.0** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **v1.3** | ✅³ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **v2.47** | ✅³ | ✅ | ✅ | ✅ | ✅ | ✅ |

³ Broadcast / typing indicator / read receipts features silently degraded when connecting to v0.5 (endpoint absent; client-side graceful degradation).

**Summary: All versions are wire-compatible for basic messaging.** Feature availability depends on the lower-capability peer.

---

## 5. Graceful Degradation Rules

When a newer agent connects to an older agent:

1. **Unknown fields in AgentCard MUST be ignored** (not error).
2. **Missing capabilities MUST be treated as `false`** (not error).
3. **Absent endpoints** (`404`) MUST be treated as "feature not available" — not connection failure.
4. **Task endpoints absent** → agent falls back to stateless message exchange.
5. **`identity` absent** → agent treats peer as unauthenticated (policy-dependent whether to proceed).
6. **`trust.signals[]` absent** → no trust verification attempted.

---

## 6. Upgrade Path

Recommended upgrade sequence for production deployments:

```
v0.5 (baseline)
  └─▶ v0.6  (+NAT traversal, +SSE stream)
        └─▶ v0.8  (+Ed25519 identity, +JWKS)
              └─▶ v1.0  (+tasks, +skills)
                    └─▶ v1.3  (+broadcast, +availability)
                          └─▶ v2.47  (+trust.signals, +RFC 8615, +capabilities.groups)
```

Each step is backward-compatible. Rolling upgrades (mixed-version clusters) are fully supported.

---

## 7. Known Incompatibilities

| Issue | Affected versions | Resolution |
|-------|------------------|------------|
| `datetime.utcnow()` deprecation in relay code | v2.40–v2.47.0 | Fixed in v2.47.1 (commit 4331646) |
| `_CaptureHandler` mock missing `requestline` in tests | v2.40–v2.47.0 | Fixed in v2.47.1 (commit 1c6c1e6) |
| `broadcast` to v0.5 peer returns `404` | v1.3+ → v0.5 | Graceful: client catches 404, logs warning, skips |

---

## 8. Running Compatibility Tests

```bash
# Full test suite (all versions tested via integration tests)
python3 -m pytest tests/ -q

# Identity-specific tests
python3 -m pytest tests/test_identity.py tests/test_jwks.py tests/test_trust_signals.py -v

# Unit tests (mock-based, fast)
python3 -m pytest tests/unit/ -v

# Cross-version AgentCard parse test
python3 -m pytest tests/test_compat.py -v  # if present
```

See [`spec/compatibility-certification.md`](../spec/compatibility-certification.md) for full certification criteria.

---

*ACP Compatibility Matrix — v2.47.1 | Last updated 2026-04-04*
