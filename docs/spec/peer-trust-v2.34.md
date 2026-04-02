# ACP Spec — Per-Peer Structured Trust Scoring (v2.34)

> **Status**: Stable  
> **Version**: 2.34.0  
> **Date**: 2026-04-02  
> **Supersedes**: N/A (new feature)  
> **Related**: [`core-v0.8.md`](core-v0.8.md), [`nat-traversal-v1.4.md`](nat-traversal-v1.4.md)

---

## 1. Overview

ACP v2.34 introduces **per-peer structured trust scoring**: a single endpoint that aggregates all available identity, liveness, and social signals for a connected peer into a weighted composite score between 0.0 and 1.0.

**Design goals:**

- Zero-config: works with whatever signals are available; missing signals score 0.0
- Cryptographically grounded: `card_sig` and `did_consistent` dimensions verify real cryptographic material
- Actionable: `trust_level` classification (`high`/`medium`/`low`) usable directly in routing or gating logic
- Non-blocking: purely read-only, no side effects, <1ms per call (in-memory computation)

---

## 2. Capability Declaration

An agent that implements this spec MUST declare:

```json
{
  "capabilities": {
    "peer_trust": true
  },
  "endpoints": {
    "peer_trust": "/peers/{peer_id}/trust"
  }
}
```

Agents that do not implement this feature MUST omit `peer_trust` from `capabilities` (or set it to `false`).

---

## 3. Endpoint

### `GET /peers/<peer_id>/trust`

Returns the structured trust assessment for a known peer.

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `peer_id` | string | The peer's identifier (e.g. `tok_abc123`) |

#### Response: 200 OK

```json
{
  "peer_id": "tok_abc123",
  "name": "WorkerAgent",
  "connected": true,
  "trust_score": 0.72,
  "trust_level": "medium",
  "dimensions": {
    "card_sig": {
      "score": 1.0,
      "weight": 0.35,
      "detail": "Ed25519 signature valid"
    },
    "did_consistent": {
      "score": 1.0,
      "weight": 0.20,
      "detail": "DID round-trips consistently"
    },
    "ping_rtt": {
      "score": 0.7,
      "weight": 0.20,
      "detail": "RTT 85ms (<200ms bucket)",
      "last_ping_rtt_ms": 85,
      "ping_count": 3
    },
    "message_hist": {
      "score": 0.2,
      "weight": 0.15,
      "detail": "2 messages sent",
      "messages_sent": 2
    },
    "vouch": {
      "score": 0.0,
      "weight": 0.10,
      "detail": "Not in vouch_chain"
    }
  },
  "evaluated_at": "2026-04-02T04:32:11.123456Z"
}
```

#### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `peer_id` | string | Peer identifier |
| `name` | string | Peer's declared agent name |
| `connected` | boolean | Whether the peer is currently connected |
| `trust_score` | float | Composite score in [0.0, 1.0] (weighted sum of dimensions) |
| `trust_level` | string | `"high"` / `"medium"` / `"low"` (see §4) |
| `dimensions` | object | Per-dimension breakdown (see §5) |
| `evaluated_at` | string | ISO 8601 timestamp of evaluation |

#### Response: 404 Not Found

```json
{
  "error": "ERR_PEER_NOT_FOUND",
  "detail": "No peer with id tok_unknown"
}
```

Returned when `peer_id` does not match any known peer (connected or historical).

---

## 4. Trust Level Classification

| Level | Condition | Recommended interpretation |
|-------|-----------|---------------------------|
| `"high"` | `trust_score >= 0.75` | Peer has strong cryptographic identity + active history |
| `"medium"` | `0.45 <= trust_score < 0.75` | Peer is partially verified; use with caution |
| `"low"` | `trust_score < 0.45` | Peer lacks verification; treat as untrusted |

These thresholds are RECOMMENDED. Agents MAY apply custom thresholds for their use cases.

---

## 5. Trust Dimensions

The composite score is computed as:

```
trust_score = Σ (dimension.score × dimension.weight)
```

All weights sum to 1.0. Each dimension score is in [0.0, 1.0].

### 5.1 `card_sig` — AgentCard Signature (weight: 0.35)

Verifies that the peer's AgentCard is self-signed with its Ed25519 private key.

| Score | Condition |
|-------|-----------|
| `1.0` | Card signature verified (`card_verification.valid == true`) |
| `0.0` | No signature, verification failed, or `capabilities.card_sig == false` |

**Rationale**: Cryptographic proof of identity ownership. Highest weight because it's unforgeable.

### 5.2 `did_consistent` — DID Consistency (weight: 0.20)

Verifies that the peer's DID in its AgentCard matches the observed public key (offline round-trip derivation, requires v2.33 pubkey-discovery).

| Score | Condition |
|-------|-----------|
| `1.0` | DID round-trips consistently (derived DID matches declared DID) |
| `0.0` | DID absent, inconsistent, or derivation failed |

**Rationale**: Ensures the peer's claimed identity is internally consistent. Zero-network-call check.

### 5.3 `ping_rtt` — Liveness / RTT (weight: 0.20)

Measures peer liveness based on observed ping round-trip time. Requires `GET /peers/<id>/ping` data (v2.28+).

| Score | Condition |
|-------|-----------|
| `1.0` | Last RTT < 50ms |
| `0.7` | Last RTT < 200ms |
| `0.4` | Last RTT < 500ms |
| `0.1` | Last RTT ≥ 500ms |
| `0.0` | No ping data available |

Additional response fields: `last_ping_rtt_ms` (integer), `ping_count` (integer).

**Rationale**: Liveness correlates with trust. A peer that responds quickly is more likely to be an actively maintained agent.

### 5.4 `message_hist` — Message History (weight: 0.15)

Measures trust from historical message volume — peers with a longer communication history are more trusted.

| Score | Condition |
|-------|-----------|
| `1.0` | ≥ 100 messages sent |
| `0.7` | ≥ 20 messages sent |
| `0.4` | ≥ 5 messages sent |
| `0.2` | > 0 messages sent |
| `0.0` | No messages ever sent |

Additional response field: `messages_sent` (integer).

**Rationale**: Communication history is a soft trust signal. New peers start at 0 and build reputation through interaction.

### 5.5 `vouch` — Vouch Chain Endorsement (weight: 0.10)

Checks whether the peer's DID appears in the local agent's vouch chain (v2.27 social trust).

| Score | Condition |
|-------|-----------|
| `1.0` | Peer's DID found in `vouch_chain` |
| `0.0` | Peer's DID not in vouch chain, or peer has no DID |

**Rationale**: Social endorsement from known trusted agents. Lowest weight because vouch chains are optional and sparse.

---

## 6. Usage Examples

### Basic trust check

```bash
curl http://127.0.0.1:18001/peers/tok_abc123/trust
```

### Gate a task on trust level

```python
import requests

def is_trusted(http_port, peer_id, min_level="medium"):
    levels = {"high": 2, "medium": 1, "low": 0}
    r = requests.get(f"http://127.0.0.1:{http_port}/peers/{peer_id}/trust")
    if r.status_code != 200:
        return False
    data = r.json()
    return levels.get(data["trust_level"], 0) >= levels[min_level]

if is_trusted(18001, "tok_abc123", min_level="medium"):
    # proceed with task delegation
    pass
```

### Check all connected peers

```python
import requests

def get_all_trust(http_port):
    peers = requests.get(f"http://127.0.0.1:{http_port}/peers").json().get("peers", [])
    results = []
    for p in peers:
        if p.get("connected"):
            t = requests.get(f"http://127.0.0.1:{http_port}/peers/{p['id']}/trust").json()
            results.append(t)
    return sorted(results, key=lambda x: x["trust_score"], reverse=True)
```

---

## 7. Implementation Notes

- The endpoint is **read-only** and has no side effects.
- Scores are computed **on-demand** from in-memory peer state; there is no caching or persistence.
- If `capabilities.card_sig == false` on the peer's AgentCard, `card_sig` score is `0.0`.
- If `capabilities.did_identity == false` or the peer has no DID, `did_consistent` score is `0.0`.
- `ping_rtt` requires at least one prior call to `GET /peers/<id>/ping`; otherwise `0.0`.
- `vouch` requires `capabilities.peers_vouch_chain == true` on the local relay.
- Unknown or disconnected (but historically known) peers are still scoreable; `connected` will be `false`.

---

## 8. Security Considerations

- `card_sig = 1.0` proves the agent *controls* the private key behind the AgentCard at connection time. It does not prove the agent is *benign*.
- `trust_score` is a heuristic, not a security guarantee. Do not use it as the sole gate for sensitive operations.
- Vouch chains can be gamed if a trusted agent is compromised. Treat vouch as a weak signal.
- All five dimensions together provide defense-in-depth: a malicious agent would need to forge a valid Ed25519 signature, maintain a consistent DID, respond with low latency, accumulate message history, and appear in a vouch chain — a high bar in combination.

---

## 9. Relationship to Other Specs

| Spec | Relationship |
|------|-------------|
| `core-v0.8.md §8` (Identity) | `card_sig` and `did_consistent` dimensions depend on Ed25519 identity |
| v2.33 pubkey-discovery | `did_consistent` uses offline DID→pubkey resolution |
| v2.28 peer-ping | `ping_rtt` dimension uses ping RTT data |
| v2.27 vouch-chain | `vouch` dimension reads vouch chain |
| v2.18 JWKS | Complementary key discovery (JWKS vs DID) |

---

## 10. Test Coverage

Reference test suite: `tests/test_peer_trust.py`

| Test ID | Description |
|---------|-------------|
| PT1 | `capabilities.peer_trust: true` declared in AgentCard |
| PT2 | `GET /peers/<id>/trust` returns 200 with correct schema |
| PT3 | `trust_score` is a float in [0.0, 1.0] |
| PT4 | `trust_level` is `high`/`medium`/`low` |
| PT5 | All five dimensions present in response |
| PT6 | `card_sig` score reflects actual card verification result |
| PT7 | `ping_rtt` score updates after `GET /peers/<id>/ping` call |
| PT8 | `message_hist` score updates after messages are sent |
| PT9 | Unknown peer_id returns 404 with `ERR_PEER_NOT_FOUND` |
| PT10 | `evaluated_at` is a valid ISO 8601 timestamp |

All 10 tests pass as of v2.34.0.

---

*ACP is built by Kickflip73 + J.A.R.V.I.S. · [GitHub](https://github.com/Kickflip73/agent-communication-protocol)*
