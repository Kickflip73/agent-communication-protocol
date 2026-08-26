# ACP Spec Addendum — v2.85 → v2.87 Changes

> Supplement to `spec/core-v1.3.md`. Documents protocol-level changes introduced
> in relay versions v2.85.0 – v2.87.0 (2026-04-08 ~ 2026-04-09).

---

## v2.87.0 — `policy_compliance[]` in AgentCard

### New AgentCard field

```json
{
  "policy_compliance": ["OWASP-ASVS", "ATF-v2", "NIST-AIRMF"]
}
```

`policy_compliance` (array of strings, optional) declares which governance/compliance
standards the agent conforms to. Well-known identifiers:

| Identifier | Standard |
|-----------|---------|
| `OWASP-ASVS` | OWASP Application Security Verification Standard |
| `ATF-v2` | Agent Trust Framework v2 |
| `NIST-AIRMF` | NIST AI Risk Management Framework |
| `ISO-42001` | ISO/IEC 42001 AI Management System |
| `EU-AI-Act-conformant` | EU AI Act conformance declaration |

### New endpoints

#### `GET /policy-compliance`
Returns current declared standards.

**Response:**
```json
{
  "ok": true,
  "policy_compliance": ["OWASP-ASVS"],
  "count": 1,
  "note": "Standards are informational; no runtime enforcement"
}
```

#### `PATCH /policy-compliance`
Replace or incrementally update declared standards.

**Replace mode:**
```json
{ "policy_compliance": ["OWASP-ASVS", "ATF-v2"] }
```

**Incremental mode:**
```json
{ "add": ["NIST-AIRMF"], "remove": ["ATF-v2"] }
```

### CLI flag
```
--policy-compliance OWASP-ASVS,ATF-v2,NIST-AIRMF
```

### AgentCard capabilities
```json
"capabilities": {
  "policy_compliance": true
}
```

### Motivation
Inspired by A2A GitHub Issue #1717 (Microsoft agent-governance-toolkit proposal).
ACP implements this ahead of A2A standardization.

---

## v2.85.0 — Ed25519 Identity Default-On

### Behavior change
Prior to v2.85, Ed25519 identity required explicit `--identity` flag.
From v2.85 onwards, a keypair is **automatically generated** on first startup.

| Version | Default behavior |
|---------|----------------|
| ≤ v2.84 | No identity unless `--identity` passed |
| ≥ v2.85 | Identity auto-generated; use `--no-identity` to disable |

### New flag
```
--no-identity    Disable Ed25519 identity (testing / embedded use)
```

### New AgentCard capability
```json
"capabilities": {
  "identity_default": true
}
```

### Protocol compatibility binding endpoint

#### `GET /protocol-binding/compatibility`
```json
{
  "protocol": "acp",
  "version": "2.85.0",
  "bindings": {
    "websocket": "native",
    "http":      "native",
    "sse":       "native",
    "a2a":       "partial",
    "anp":       "partial",
    "mcp":       "none",
    "grpc":      "none"
  }
}
```

### Migration notes for test authors
Tests that previously relied on relay starting without identity must now explicitly pass
`--no-identity` to restore the pre-v2.85 behavior. Fixtures should be updated accordingly.

---

## Related A2A Issues (for context)

| A2A Issue | Status (2026-04-09) | ACP equivalent |
|-----------|-------------------|----------------|
| #1717 — Governance metadata | Proposal (14 comments) | `policy_compliance[]` (v2.87) + `governance_metadata` (v2.85) |
| #1716 — Skill authorization RFC | RFC (22 comments) | `authorization_tier` (v2.50) + `capability_token` (v2.74) |
| #1672 — Agent identity | Open (408 comments, no impl) | Ed25519 + `did:acp:` (v1.3, default-on v2.85) |
