# RFC: Skill-Level Authorization Tiers for Agent-to-Agent Communication

**Document:** ACP-RFC-001  
**Status:** IMPLEMENTED (reference implementation: ACP v2.50–v2.76)  
**Date:** 2026-04-09  
**Repository:** https://github.com/Kickflip73/agent-communication-protocol  
**Relates to:** A2A Issue [#1716](https://github.com/google/A2A/issues/1716) — Authorization layer for AgentSkill invocations

---

## Abstract

Current agent communication protocols (A2A, ANP) provide authentication mechanisms (OAuth 2.0, API keys, mTLS) but lack a standard way to express **authorization at the skill boundary** — which callers may invoke which skills, under what conditions, and with what approval requirements. This RFC defines a four-tier authorization model (`T0`–`T3`) plus a five-factor `effective_tier` computation that accounts for runtime context: delegation depth, peer reputation, and external attestation. The model is fully implemented in ACP and ships as working code with 60+ passing tests.

---

## 1. Problem Statement

When Agent A invokes a skill on Agent B, authentication answers "who is A?" — but does not answer:

- Is A **authorized** to invoke this particular skill?
- Should a **human approve** before execution (e.g., wire transfer, infrastructure delete)?
- Does A's **delegation depth** (acting on behalf of a chain of principals) affect the trust threshold?
- Does A's **past behavior** and **external reputation** affect how much trust to extend?

Without answers to these questions, skill invocation is all-or-nothing: a caller that authenticates can invoke any skill regardless of its risk level.

This RFC proposes a structured, implementable solution.

---

## 2. Tier Model

### 2.1 Declared Tier (`authorization_tier`)

Each skill in an AgentCard declares its tier:

| Tier | Meaning | Default behavior |
|------|---------|-----------------|
| `T0` | Public — no authorization needed | Execute immediately |
| `T1` | Basic — authenticated caller required | Execute if caller is a recognized peer |
| `T2` | Elevated — trusted peer required | Execute only if peer trust score ≥ threshold |
| `T3` | Critical — human approval required | Block until human confirms via `POST /tasks/{id}:confirm` |

```json
{
  "skills": [
    {
      "id": "search",
      "authorization_tier": "T0"
    },
    {
      "id": "send_email",
      "authorization_tier": "T2"
    },
    {
      "id": "wire_transfer",
      "authorization_tier": "T3",
      "human_confirmation_required": true
    }
  ]
}
```

### 2.2 Human Confirmation (`human_confirmation_required`)

When `authorization_tier: T3` AND `human_confirmation_required: true`:

1. `POST /tasks` → returns `status: "confirmation_pending"` (does not execute)
2. Human reviews via `GET /tasks/{id}`
3. Human approves: `POST /tasks/{id}:confirm` → task enters `submitted` → executes
4. Human rejects: `POST /tasks/{id}:reject` → task enters `failed`

Auto-confirm bypass (`--auto-confirm-t3`) available for testing only.

---

## 3. Effective Tier Computation

Declared tier is a **lower bound**, not the final word. Runtime context can raise it.

### 3.1 Five-Factor Formula

```
effective_tier = max(tier_rule, delegation_depth_floor, combined_adj_tier)
```

**Factor 1: `tier_rule`** — skill's declared `authorization_tier`

**Factor 2: `delegation_depth_floor`** — conservative floor based on `principal_chain` depth

| Chain depth | Floor |
|-------------|-------|
| 0 | None (no effect) |
| 1 | T1 |
| 2 | T2 |
| 3+ | T3 |

Rationale: an agent acting on behalf of a 3-hop chain of principals is less accountable than a direct caller.

**Factor 3: `reputation_adj`** — peer's local trust history

| Condition | Adjustment |
|-----------|-----------|
| Known peer, verified identity, 100+ messages, recent activity | -1 (may lower floor) |
| Neutral / insufficient data | 0 |
| Unknown peer (no card, no messages) | +1 (raises floor) |

**Factor 4: `wtrmrk_adj`** — external attestation (WTRMRK registry)

| Grade | Adjustment |
|-------|-----------|
| Grade 3 (hardware-attested, long track record) | -1 |
| Grade 1–2, query failure, or not provided | 0 (fail-closed) |
| Grade 0 (unknown on-chain) | +1 |

**Factor 5: `bilateral_ir_adj`** — interaction record history

| Condition | Adjustment |
|-----------|-----------|
| Mutual interaction log, consistent behavior, no anomalies | -1 |
| No history | 0 |
| History with anomalies | +1 |

**Combined adjustment:** `clamp(reputation_adj + wtrmrk_adj + bilateral_ir_adj, -1, +1)`

Asymmetric and conservative: all three signals must agree to lower the floor (-1), but any single signal can raise it (+1).

**T3 is immune to downgrade** — `effective_tier` never drops below T3 for a T3 skill, regardless of adjustments.

### 3.2 Example

```
Skill: send_email (authorization_tier=T2)
Caller: unknown peer (no card), acting on behalf of 2-hop chain

tier_rule           = T2 (→ int 2)
delegation_depth    = 2  (→ floor T2, int 2)
reputation_adj      = +1 (unknown peer)
wtrmrk_adj          = 0  (no registry data)
bilateral_ir_adj    = 0  (no history)
combined_adj        = +1 → effective int = max(2, 2) + 1 = 3
effective_tier      = T3

Result: task blocked, requires human confirmation despite T2 declared tier
```

---

## 4. Capability Tokens

For scenarios where a callee needs to grant a **subset of permissions** to a caller (e.g., delegated invocation, short-lived access), ACP provides capability tokens.

### 4.1 Token Structure

```json
{
  "token_id": "ctkn_abc123",
  "issued_to": "peer_007",
  "skill_ids": ["search", "summarize"],
  "tier_ceiling": "T1",
  "expires_at": 1744200000,
  "issued_by_pubkey": "base64url...",
  "signature": "base64url..."
}
```

| Field | Meaning |
|-------|---------|
| `skill_ids` | Which skills may be invoked (explicit allowlist) |
| `tier_ceiling` | Maximum tier the token grants (T0–T3) |
| `expires_at` | Unix timestamp; null = no expiry |
| `signature` | Ed25519 signature by issuer's identity key |

### 4.2 Issuance and Verification

```bash
# Issue token
POST /capability-tokens
{"skill_ids": ["search"], "tier_ceiling": "T1", "issued_to": "peer_007", "ttl_seconds": 3600}

# Revoke token
DELETE /capability-tokens/{token_id}

# Verify token (callee-side check)
POST /capability-tokens/verify
{"token": {...}, "skill_id": "search"}
→ {"valid": true, "tier": "T1", "remaining_ttl": 3580}
```

### 4.3 Token Enforcement in Task Submission

When a task is submitted with a capability token:

1. Token signature verified against issuer's known public key
2. `skill_id` checked against token's `skill_ids` allowlist
3. `tier_ceiling` applied as upper bound: `effective_tier = min(computed_tier, tier_ceiling)`
4. Expired or revoked tokens → `403 ERR_TOKEN_INVALID`

---

## 5. Task State Machine

```
                              [T3 + human_confirmation_required]
                             ┌──────────────────────────────────┐
                             ↓                                  │
POST /tasks → submitted ──→ working ──→ completed               │
                    │                                           │
                    │    [T3 + human needed]                    │
                    └──→ confirmation_pending ─→ :confirm ──→ submitted
                                               ─→ :reject ──→ failed
```

States: `submitted` | `working` | `completed` | `failed` | `input_required` | `confirmation_pending`

---

## 6. API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/tasks` | Submit task; may block at `confirmation_pending` |
| `POST` | `/tasks/{id}:confirm` | Human approves T3 task |
| `POST` | `/tasks/{id}:reject` | Human rejects T3 task |
| `GET`  | `/tasks/{id}` | Task status including `effective_tier` and `tier_factors` |
| `POST` | `/capability-tokens` | Issue delegated capability token |
| `DELETE` | `/capability-tokens/{id}` | Revoke token |
| `POST` | `/capability-tokens/verify` | Verify token for skill invocation |
| `GET`  | `/capabilities` | AgentCard capability flags including `skill_authorization_tiers` |

---

## 7. AgentCard Declaration

```json
{
  "name": "my-agent",
  "skills": [
    {
      "id": "search",
      "name": "Web Search",
      "authorization_tier": "T0"
    },
    {
      "id": "execute_code",
      "name": "Code Execution",
      "authorization_tier": "T2"
    },
    {
      "id": "deploy_infra",
      "name": "Infrastructure Deployment",
      "authorization_tier": "T3",
      "human_confirmation_required": true
    }
  ],
  "capabilities": {
    "skill_authorization_tiers": true,
    "t3_human_confirmation": true,
    "capability_token_issuance": true,
    "effective_tier_computation": true
  }
}
```

---

## 8. Comparison with A2A SecurityRequirement

A2A's `SecurityRequirement` in AgentCard (`securitySchemes` + `security[]`) covers **authentication**: OAuth 2.0, API keys, HTTP Bearer, mTLS.

This RFC covers **authorization**: assuming the caller is authenticated, what are they allowed to do?

The two mechanisms are complementary. A2A Issue [#1716](https://github.com/google/A2A/issues/1716) (opened 2026-04-09) identifies the same gap:

> "A calling agent can authenticate successfully and then invoke **any** skill the AgentCard advertises. There is no standard way for an agent server to express which callers may invoke which skills with which parameters."

ACP has addressed this gap since v2.50 (skill tiers), v2.51 (human confirmation), v2.74 (capability tokens), and v2.76 (five-factor effective_tier). 

---

## 9. Implementation Notes

- Reference implementation: [`relay/acp_relay.py`](../../relay/acp_relay.py) — `_compute_effective_tier()`, `_check_authorization_tier()`, `_issue_capability_token()`, `_verify_capability_token()`
- Test coverage: `tests/test_effective_tier.py`, `tests/test_effective_tier_v276.py`, `tests/test_capability_token.py`, `tests/test_capability_token_detail_v274.py`, `tests/test_capability_token_revoke_v278.py`, `tests/test_capability_token_validate_v277.py`, `tests/test_capability_token_fixtures_v275.py` — **60+ passing tests**
- CLI flags: `--skill-tiers "skill_id:T2,other_skill:T3"`, `--human-confirm-t3`, `--auto-confirm-t3` (test only)
- Version history: T0–T3 tiers (v2.50), `human_confirmation_required` (v2.51), `confirmation_pending` state (v2.51), capability tokens (v2.74), five-factor `effective_tier` (v2.76)

---

## 10. Design Principles

1. **Conservative by default** — unknown peers get floor raised, not lowered
2. **T3 is irreversible floor** — no combination of reputation/attestation can drop T3
3. **Fail-closed on external signals** — if WTRMRK query fails, treat as neutral (0), not positive (-1)
4. **Human confirmation is explicit** — a human must take an action; timeout does not auto-approve
5. **Tokens are bounded** — capability tokens set a ceiling, never a floor; they restrict, not elevate
6. **Backward compatible** — skills without `authorization_tier` default to T0; existing clients unaffected

---

*This RFC documents a working implementation. Feedback and cross-protocol adoption welcome.*
