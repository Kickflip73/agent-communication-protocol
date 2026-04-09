# RFC: Bilateral Signed Interaction Records as the Trust Primitive

**Document:** ACP-RFC-002  
**Status:** IMPLEMENTED (reference implementation: ACP v2.59–v2.76)  
**Date:** 2026-04-09  
**Repository:** https://github.com/Kickflip73/agent-communication-protocol  
**Relates to:** A2A Issue [#1718](https://github.com/google/A2A/issues/1718) — Bilateral signed interaction records as the trust primitive for A2A

---

## Abstract

Agent trust systems in current protocols are fragmented: identity, reputation, audit trails, delegation evidence, and Sybil resistance are separate mechanisms that don't compose. This RFC proposes a single data structure — the **bilateral signed interaction record** — that unifies all of them. Both the requesting agent (caller) and the serving agent (relay) co-sign each record, making it non-repudiable by either party. A chain of such records forms a cryptographically verifiable interaction graph from which trust scores, audit trails, and delegation evidence can all be derived. The model is fully implemented in ACP v2.59–v2.76 with 29+ passing tests.

---

## 1. Problem Statement

Current A2A-style agent trust proposals address each concern independently:

| Concern | Current approach | Problem |
|---------|-----------------|---------|
| Identity | DID documents, OAuth tokens | Single-party attestation |
| Reputation | Behavioral signals, manual scores | No objective anchor |
| Audit | Evidence envelopes, action receipts | Relay can forge unilaterally |
| Delegation | Scoped tokens, capability chains | No history of past delegation |
| Sybil resistance | Token gating, vouching | Requires external registry |

The root failure: **unilateral attestation**. A relay reports what happened. If the relay is compromised or incentivized to lie, the record is worthless. An external verifier cannot distinguish a legitimate record from a forged one.

The fix: **require both parties to sign**. A record co-signed by caller and relay is non-repudiable by either. A corpus of such records, each chaining to the previous, forms a tamper-evident interaction history that can bootstrap trust without external registries.

---

## 2. Record Structure

### 2.1 Core Fields

```json
{
  "id": "ir-a1b2c3d4",
  "type": "interaction",
  "relay_did": "did:acp:base58url...",
  "caller_did": "did:acp:base58url...",
  "task_id": "task-xyz",
  "skill_id": "search",
  "sequence_a": 42,
  "previous_hash": "sha256:abc123...",
  "timestamp": "2026-04-09T05:41:00Z",

  "relay_signature": "base64url...",
  "caller_signature": "base64url...",
  "caller_public_key": "base64url...",
  "caller_signature_valid": true,
  "bilateral": true,

  "outcome": "completed",
  "task_duration_ms": 380
}
```

### 2.2 Field Reference

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique record ID (`ir-<random>`) |
| `type` | string | Always `"interaction"` |
| `relay_did` | string | Relay's `did:acp:` identifier |
| `caller_did` | string\|null | Caller's `did:acp:` (null if anonymous) |
| `task_id` | string | Task this record covers |
| `skill_id` | string\|null | Skill invoked |
| `sequence_a` | integer | Monotonic counter — relay side (chain continuity) |
| `previous_hash` | string | SHA-256 of previous record (JSON canonical form) |
| `timestamp` | ISO-8601 | Wall-clock at record creation |
| `relay_signature` | base64url | Ed25519 sig by relay over canonical payload |
| `caller_signature` | base64url\|null | Ed25519 sig by caller (optional) |
| `caller_public_key` | base64url\|null | Caller's public key for signature verification |
| `caller_signature_valid` | bool\|null | `true`/`false` if caller_sig present; `null` if absent |
| `bilateral` | bool | `true` iff both sigs present and `caller_signature_valid=true` |
| `outcome` | string | Task final state (`completed`/`failed`/etc.) |
| `task_duration_ms` | integer | Execution time in milliseconds |

### 2.3 Canonical Signing Payload

Both relay and caller sign the same payload (deterministic JSON):

```json
{
  "id": "ir-a1b2c3d4",
  "type": "interaction",
  "relay_did": "did:acp:...",
  "caller_did": "did:acp:...",
  "task_id": "task-xyz",
  "skill_id": "search",
  "sequence_a": 42,
  "previous_hash": "sha256:...",
  "timestamp": "2026-04-09T05:41:00Z"
}
```

Serialized as: `json.dumps(payload, sort_keys=True, separators=(",", ":"))` — no whitespace, deterministic key order.

---

## 3. Hash Chain

Each record's `previous_hash` is the SHA-256 of the **full prior record** (canonical JSON):

```python
prev_bytes = json.dumps(prev_record, sort_keys=True, separators=(",", ":")).encode()
previous_hash = "sha256:" + hashlib.sha256(prev_bytes).hexdigest()
```

Properties:
- Any tampering with a past record invalidates all subsequent hashes
- Third parties can verify chain integrity without trusting either party
- The first record has `previous_hash: null`

---

## 4. Trust Derivation

The bilateral IR corpus is the input for trust scoring — no external registry needed.

### 4.1 Bilateral IR Adjustment (v2.76)

Records feed into the `effective_tier` computation (see ACP-RFC-001) as the fifth factor:

| Condition | `bilateral_ir_adj` |
|-----------|-------------------|
| Mutual records exist, consistent behavior, no anomalies | -1 (may lower authorization floor) |
| No history | 0 (neutral) |
| History with anomalies or failed records | +1 (raises authorization floor) |

### 4.2 Merkle Root (v2.72)

For compact cross-peer attestation, a Merkle root over the bilateral IR corpus can be computed and included in AgentCard trust signals:

```python
GET /trust/bilateral-ir/log?bilateral=true&peer_did=<did>
# Returns all bilateral records with this peer

# Merkle root of record IDs → compact attestation
```

### 4.3 Trust Signal Integration (v2.68)

Bilateral IR records are surfaced as a trust signal type in AgentCard:

```json
{
  "trust": {
    "signals": [
      {
        "type": "bilateral_ir",
        "bilateral_count": 47,
        "merkle_root": "sha256:...",
        "since": "2026-03-01T00:00:00Z"
      }
    ]
  }
}
```

---

## 5. API Endpoints

### 5.1 List Interaction Records

```
GET /interaction-records
```

Query parameters:

| Param | Description |
|-------|-------------|
| `bilateral=true` | Only bilateral (both-signed) records |
| `caller_did=<did>` | Filter by caller |
| `skill_id=<id>` | Filter by skill |
| `since=<ISO-8601>` | Records after timestamp |
| `limit=<n>` | Max records returned (default 50) |

Response:
```json
{
  "records": [...],
  "total": 47,
  "bilateral_count": 42
}
```

### 5.2 Bilateral IR Log (v2.72)

```
GET /trust/bilateral-ir/log
```

Queryable log focused on bilateral records, with Merkle root for compact attestation.

### 5.3 Test Vectors (v2.64)

```
GET /ir/test-vectors
```

Deterministic test vectors for cross-implementation verification. Enables any implementation to validate its signing and chain logic against ACP's reference output.

### 5.4 Import External Evidence (v2.65)

```
POST /ir/import-evidence
```

Import bilateral IR records from external agents into the local corpus. Validates both signatures, checks chain continuity, generates an APS-compatible `reputation_update` event.

---

## 6. Caller-Side Integration

Callers that support Ed25519 signing can produce bilateral records by including their signature in task submission:

```http
POST /tasks
X-Caller-Signature: <base64url Ed25519 sig over canonical payload>
X-Caller-Public-Key: <base64url Ed25519 public key>

{"skill_id": "search", "message": {...}}
```

The relay verifies the signature before setting `bilateral: true`. If verification fails, the record is stored with `caller_signature_valid: false` and `bilateral: false` — the record is not rejected, allowing degraded-mode operation.

Callers without Ed25519 support omit the headers. The relay creates a relay-only-signed record (`bilateral: false`). This is fully backward-compatible.

---

## 7. Design Principles

1. **Bilateral = non-repudiable** — relay-only records can be forged by a malicious relay; bilateral records cannot be forged by either party alone
2. **Fail-open, not fail-closed** — missing caller signature produces a usable (degraded) record, not an error
3. **Chain = tamper-evident** — any modification to past records is detectable without trusting either party
4. **Trust derives from history, not assertion** — scores are computed from actual interaction records, not from self-declared signals
5. **No external registry required** — the local IR corpus is the trust substrate; Merkle roots enable compact cross-peer attestation without centralization
6. **Backward compatible** — existing callers without signing support work normally; records are just non-bilateral

---

## 8. Comparison with A2A #1718 Proposal

A2A Issue [#1718](https://github.com/google/A2A/issues/1718) (viftode4, 2026-04-05) identifies the same core problem and proposes the same core solution. ACP's implementation predates the proposal:

| Feature | A2A #1718 (proposal) | ACP (implemented) |
|---------|---------------------|-------------------|
| Bilateral signing (both parties) | ✅ Proposed | ✅ v2.61 |
| Hash chain (previous_hash) | ✅ Proposed | ✅ v2.59 |
| Sequence numbers | ✅ Proposed | ✅ v2.59 (`sequence_a`) |
| Trust score derivation | ✅ Proposed | ✅ v2.76 (`bilateral_ir_adj`, 5th factor) |
| Merkle root attestation | Not specified | ✅ v2.72 |
| Cross-impl test vectors | Not specified | ✅ v2.64 (`GET /ir/test-vectors`) |
| External evidence import | Not specified | ✅ v2.65 (`POST /ir/import-evidence`) |
| AgentCard trust signal integration | Not specified | ✅ v2.68 (`type: bilateral_ir`) |
| Test coverage | None | ✅ 29+ tests (`test_bilateral_ir_log_v272.py`, `test_interaction_records.py`, `test_import_evidence.py`) |

---

## 9. Implementation Notes

- Reference implementation: [`relay/acp_relay.py`](../../relay/acp_relay.py)
  - `_create_interaction_record()` — record creation + bilateral signing (v2.59/v2.61)
  - `_bilateral_ir_merkle_root()` — Merkle root computation (v2.72)
  - `_bilateral_ir_adj()` — trust adjustment factor (v2.76)
  - `GET /interaction-records` — list endpoint (v2.59)
  - `GET /trust/bilateral-ir/log` — queryable log (v2.72)
  - `GET /ir/test-vectors` — deterministic test vectors (v2.64)
  - `POST /ir/import-evidence` — external evidence import (v2.65)
- Test files: `tests/test_interaction_records.py`, `tests/test_bilateral_ir_log_v272.py`, `tests/test_ir_test_vectors.py`, `tests/test_import_evidence.py`
- Version history: relay-signed records (v2.59), bilateral caller co-signing (v2.61), test vectors (v2.64), evidence import (v2.65), trust signals (v2.68), Merkle root / queryable log (v2.72), trust score integration (v2.76)

---

*This RFC documents a working implementation. Cross-protocol adoption and feedback welcome. Reference: [ACP-RFC-001](./skill-authorization.md) for the authorization tier model that consumes bilateral IR as input.*
