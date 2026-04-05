# What's New in ACP — Last 7 Days

> Last updated: 2026-04-06
> For the full history see [CHANGELOG.md](../CHANGELOG.md)

---

### v2.57.0 — SINT-format Capability Tokens: Ed25519 signed skill authorization (2026-04-06)

ACP v2.57 introduces **capability tokens** — cryptographically signed, portable credentials
that authorize an agent to invoke a specific skill. The design is fully compatible with the
[SINT Protocol](https://github.com/google-a2a/A2A/issues/1716) proposed in A2A Issue #1716
(0 replies as of 2026-04-05). **ACP ships the reference implementation first.**

**Core insight:** Instead of trusting who's calling based on connection trust score (v2.49),
you now issue a signed token that says: *"this specific agent may invoke this specific skill
at this tier, subject to these constraints, until this expiry."* The relay verifies the
Ed25519 signature inline — no external Authority Server, no OAuth, no key lookup.

---

#### Quick Start: Issue and Use a Capability Token

```bash
# Start relay with Ed25519 identity (required for issuance)
python3 acp_relay.py --port 7801 --name FinanceAgent \
  --identity ~/.acp/identity.json \
  --skills '[{"id":"transfer_funds","name":"Transfer","authorization_tier":"T3","capability_token_required":true}]'

# Issue a capability token for subject agent
curl -s -X POST http://localhost:7901/skills/transfer_funds/capability-token \
  -H "Content-Type: application/json" \
  -d '{"subject":"did:acp:CallerAgent","tier":"T3","ttl":300}'
```

```json
{
  "ok": true,
  "token": {
    "jti":         "a3f8d2e1b4c9...",
    "iss":         "did:acp:FinanceAgentDID",
    "sub":         "did:acp:CallerAgent",
    "resource":    "acp://FinanceAgent/skills/transfer_funds",
    "actions":     ["invoke"],
    "tier":        "T3",
    "constraints": {},
    "iat":         1743954000,
    "exp":         1743954300,
    "signature":   "a7b3c2...",
    "scheme":      "sint_ed25519",
    "public_key":  "3d8f4a..."
  }
}
```

```bash
# Use the token to invoke the skill
curl -s -X POST http://localhost:7901/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "role": "agent",
    "parts": [{"kind": "text", "text": "transfer 100 USD to account #7823"}],
    "skill_id": "transfer_funds",
    "capability_token": { ... token from above ... }
  }'
```

---

#### Enforcement Model

```
POST /tasks
    │
    ├─ skill.capability_token_required=True? ──(no token)──► 403 ERR_CAPABILITY_TOKEN_REQUIRED
    │
    ├─ capability_token provided? ─────────────────────────► validate(sig + exp + skill)
    │        └── invalid ──────────────────────────────────► 403 ERR_CAPABILITY_TOKEN_INVALID
    │        └── valid ──────────────────────────────────── skip authorization_tier gate ✓
    │
    ├─ no token: authorization_tier check (v2.49 trust_score path)
    ├─ param_constraints check (v2.50)
    ├─ rate_limit check (v2.53)
    └─ human_confirmation gate (v2.51, T3 only)
```

**Key design choice:** A valid capability token **bypasses** the `trust_score`-based
authorization_tier check. The token *is* the credential. This enables cross-org invocation
without requiring the caller to have an established trust relationship.

---

#### List Issued Tokens

```bash
# All tokens
curl -s http://localhost:7901/capability-tokens

# Active (non-expired) tokens for a specific skill
curl -s "http://localhost:7901/capability-tokens?skill_id=transfer_funds&active=1"
```

---

#### AgentCard Capabilities

```json
{
  "capabilities": {
    "capability_token_issuance": true
  },
  "endpoints": {
    "capability_token_issuance": "/skills/{skill_id}/capability-token"
  }
}
```

`capability_token_issuance` is `true` only when `--identity` is loaded (Ed25519 keypair required).

---

#### SINT Protocol Compatibility

ACP capability tokens use the standard SINT fields:

| Field | SINT standard | ACP v2.57 |
|-------|--------------|-----------|
| `jti` | token id | ✅ random 16-byte hex |
| `iss` | issuer DID | ✅ `_did_acp` or `_did_key` |
| `sub` | subject DID | ✅ caller's DID |
| `resource` | capability resource | ✅ `acp://{name}/skills/{id}` |
| `actions` | permitted operations | ✅ default `["invoke"]` |
| `tier` | authorization tier | ✅ T0/T1/T2/T3 |
| `constraints` | parameter bounds | ✅ dict, composable with v2.50 |
| `iat` / `exp` | validity window | ✅ unix timestamps |
| `signature` | Ed25519 sig | ✅ over canonical JSON |
| `scheme` | signature scheme | ✅ `"sint_ed25519"` |

---

### v2.56.0 — principal_chain[] OBO Delegation (2026-04-05)

See [v2.56 entry in CHANGELOG](../CHANGELOG.md#2560--2026-04-05).

**TL;DR:** On-behalf-of delegation via a DID-identified principal chain embedded in AgentCard trust block and messages. No shared AS. Answers A2A Issue #1713.

```bash
python3 acp_relay.py --port 7801 --name WorkerAgent \
  --principal did:acp:OrchestratorDID,role=orchestrator
```

---

### v2.55.0 — Per-Peer AgentCard Re-verification (2026-04-05)

`GET /peers/{peer_id}/verify-card` — on-demand re-verification of a connected peer's AgentCard
with optional cache bypass (`force=1`), trust integration (`trust=1`), and custom TTL.

---

### v2.54.0 — Batch Verify-Card + TTL Cache (2026-04-05)

`POST /verify-card` now supports three modes: single card, batch (`cards: [...]`),
and fetch-and-verify (`url: "..."`). TTL cache (300s default), `ttl=0` force-fresh.

---

### v2.53.0 — Per-Skill Rate Limiting (2026-04-05)

`skill.rate_limit: {max_calls, window_seconds, scope}` — sliding window rate limiting
per peer or globally per skill. 429 `ERR_RATE_LIMIT` on exceeded.

---

### v2.52.0 — Skill Deprecation Notices (2026-04-05)

`skill.deprecation_notice: {message, sunset_date, replacement_skill_id, severity}` —
structured skill sunset metadata. Surfaced in `GET /skills` responses.

---

### v2.51.0 — T3 Human Confirmation Gate (2026-04-05)

`skill.human_confirmation_required: true` — T3 skills can require human sign-off before
execution. `POST /tasks/{id}:confirm` / `:reject` two-phase protocol.
