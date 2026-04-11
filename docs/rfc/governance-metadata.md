# ACP-RFC-003: Governance Metadata for Agent Cards

**RFC Number:** RFC-003  
**Title:** Governance Metadata for Agent Cards  
**Status:** Draft  
**Authors:** J.A.R.V.I.S. / ACP Core  
**Created:** 2026-04-09  
**Updated:** 2026-04-09  
**ACP Version:** v2.92+  
**Related:** A2A #1717 (Microsoft, 2026-04-09), aeoess SDK v1.37.0

---

## Abstract

This RFC formalizes the `governance_metadata` block in ACP AgentCards. It defines a structured schema for publishing an agent's trust posture, capability manifest, compliance declarations, derivation rights, and credential lifecycle policy — allowing receiving agents to make authorization decisions before accepting a task.

ACP has shipped a production implementation since v2.60 (March 2026). This RFC documents the specification so that other ACP-compatible implementations can achieve interoperability.

---

## 1. Motivation

When Agent B receives a task delegation from Agent A, B needs to answer:

1. **Is A trustworthy?** — trust score, audit trail
2. **Is A authorized for this skill?** — capability manifest, authorization tier
3. **Is A compliant with my required policies?** — policy_compliance declarations
4. **Can A retain or export data derived from this task?** — derivation rights
5. **How long are A's credentials valid?** — credential lifecycle bounds

Without a standardized governance block, receiving agents must either blindly accept delegations or implement ad-hoc trust checks that break interoperability.

---

## 2. Design Principles

- **Declared, not just computed.** The agent declares its own governance posture; verifiers may choose to trust, distrust, or independently verify.
- **Live endpoint over static snapshot.** A static trust score in a card goes stale. The `live_endpoint` field lets receivers request a current governance state on demand.
- **Composable.** Fields are independently useful; partial implementations are valid.
- **GDPR-aware.** `derivation_rights` closes the "derived data leakage" gap (aeoess SDK v1.37.0 / A2A #1717).

---

## 3. Schema

### 3.1 Top-level `governance_metadata` block

Added to `AgentCard` as an optional object:

```json
{
  "governance_metadata": {
    "schema_version": "1.0",
    "generated_at": "<ISO8601>",
    "trust_score": 0.82,
    "live_endpoint": "/governance-metadata",
    "capability_manifest": { ... },
    "policy_compliance": [ ... ],
    "derivation_rights": { ... },
    "credential_lifecycle": { ... },
    "audit_trail_reference": "/interaction-records",
    "interaction_record_count": 42,
    "peer_count": 7,
    "task_count": 15
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `schema_version` | string | Yes | Always `"1.0"` for this RFC |
| `generated_at` | ISO8601 string | Yes | Time this block was generated |
| `trust_score` | float [0.0–1.0] or null | No | Computed or configured trust score |
| `live_endpoint` | URI string | No | Endpoint for real-time governance state (recommended: `/governance-metadata`) |
| `capability_manifest` | object | No | Map of skill_id → tier/status/deprecated |
| `policy_compliance` | array | No | List of compliance standard declarations |
| `derivation_rights` | object | No | **NEW v2.92** — data retention/export policy for task-derived data |
| `credential_lifecycle` | object | No | **NEW v2.92** — session TTL, revocation endpoint, check frequency |
| `audit_trail_reference` | URI string or null | No | Live endpoint for interaction records / audit trail |
| `interaction_record_count` | integer | No | Live count of interaction records |
| `peer_count` | integer | No | Number of known peers |
| `task_count` | integer | No | Total tasks handled |

---

### 3.2 `capability_manifest`

Maps skill identifiers to their authorization tier and availability:

```json
{
  "capability_manifest": {
    "search": {
      "tier": "T1",
      "status": "available",
      "deprecated": false
    },
    "code_exec": {
      "tier": "T3",
      "status": "restricted",
      "deprecated": false
    }
  }
}
```

Tier values follow ACP capability token spec (RFC-001): `T0` (public) → `T3` (restricted).

---

### 3.3 `policy_compliance`

Array of compliance standard declarations:

```json
{
  "policy_compliance": [
    { "policy": "OWASP-ASVS-4.0", "status": "compliant" },
    { "policy": "SOC2-Type2",      "status": "compliant" },
    { "policy": "GDPR-Art5",       "status": "compliant" },
    { "policy": "ATF-v2",          "status": "non-compliant" }
  ]
}
```

`status` values: `"compliant"` | `"non-compliant"` | `"unknown"`

---

### 3.4 `derivation_rights` (NEW — v2.92)

Controls what a receiving agent may retain, derive, and export from data accessed during a delegated task. Directly addresses the GDPR "derived data leakage" gap identified in aeoess SDK v1.37.0.

```json
{
  "derivation_rights": {
    "retention_permitted": true,
    "retention_ttl": 86400,
    "derivation_classes": ["summarization", "embedding"],
    "export_permitted": false,
    "export_requires_consent": true,
    "derivation_audit_required": true
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `retention_permitted` | bool | Yes | Whether the receiving agent may retain data derived from this task |
| `retention_ttl` | integer (seconds) or null | No | How long derived data may be retained; null = no time limit (if retention_permitted=true) |
| `derivation_classes` | string[] | No | Allowed derivation operations (e.g. `"summarization"`, `"embedding"`, `"fine-tuning"`). If absent and retention_permitted=true, all classes allowed. |
| `export_permitted` | bool | Yes | Whether derived data may be exported outside the receiving agent's runtime |
| `export_requires_consent` | bool | No | Whether explicit consent is required before export (default: false) |
| `derivation_audit_required` | bool | No | Whether derivation events must be logged to an audit trail (default: false) |

**Enforcement note:** `derivation_rights` is a declaration, not an enforcement mechanism. Receiving agents SHOULD honor these rights. Verification is out-of-band (e.g., via interaction records with `derivation_audit_required=true`).

**GDPR alignment:**
- `retention_permitted=false` → no persistent storage of derived data (Art. 5(1)(e) storage limitation)
- `export_permitted=false` → no data portability to third parties without consent (Art. 20)
- `derivation_audit_required=true` → accountability principle (Art. 5(2))

---

### 3.5 `credential_lifecycle` (NEW — v2.92)

Bounds session duration and credential validity. Closes the "session closed but credentials survive" vulnerability identified by aeoess TLA+ analysis.

```json
{
  "credential_lifecycle": {
    "max_session_duration": 3600,
    "credential_ttl": 7200,
    "revocation_endpoint": "/identity/revoke",
    "revocation_check_frequency": 300
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `max_session_duration` | integer (seconds) | No | Maximum allowed session length; agent SHOULD reject tasks from sessions exceeding this |
| `credential_ttl` | integer (seconds) | No | Time-to-live for issued credentials/tokens |
| `revocation_endpoint` | URI string or null | No | Endpoint for checking or performing revocation |
| `revocation_check_frequency` | integer (seconds) | No | How often receivers SHOULD check revocation status |

**Validation semantics:**  
A receiving agent MAY validate: `(current_time - session_start) <= max_session_duration` and `(current_time - credential_issue_time) <= credential_ttl`. If validation fails → reject delegation.

---

## 4. Endpoints

### 4.1 `GET /governance-metadata`

Returns the current governance metadata block (live, not cached):

```
GET /governance-metadata HTTP/1.1
```

```json
{
  "ok": true,
  "governance_metadata": { ... }
}
```

This is the `live_endpoint` target. Receivers use this to get an up-to-date governance snapshot rather than relying on the (potentially stale) AgentCard.

### 4.2 `PATCH /governance-metadata`

Runtime update of governance metadata fields:

```json
{
  "trust_score": 0.95,
  "derivation_rights": {
    "retention_permitted": false,
    "export_permitted": false
  }
}
```

Response: `{"ok": true, "updated": true}`

### 4.3 `GET /policy-compliance` / `PATCH /policy-compliance`

Dedicated endpoints for compliance standard management:

```
GET /policy-compliance
→ {"ok": true, "policy_compliance": [...], "count": N}

PATCH /policy-compliance
body: {"policy_compliance": ["GDPR-Art5", "SOC2-Type2"]}
→ {"ok": true, "policy_compliance": [...], "count": N, "updated": true}
```

---

## 5. AgentCard Capability Flags

When `governance_metadata` is configured, the following capability flags are set:

```json
{
  "capabilities": {
    "governance_metadata":  true,
    "policy_compliance":    true,
    "derivation_rights":    true,
    "credential_lifecycle": true
  },
  "endpoints": {
    "governance_metadata":  "/governance-metadata",
    "policy_compliance":    "/policy-compliance"
  }
}
```

---

## 6. Comparison with A2A #1717

| Feature | ACP (this RFC) | A2A #1717 |
|---------|---------------|-----------|
| `trust_score` | ✅ v2.60 | Proposed |
| `capability_manifest` | ✅ v2.60 | Proposed |
| `policy_compliance` | ✅ v2.87 | Proposed |
| `audit_trail_reference` | ✅ v2.60 (live endpoint) | Proposed |
| `live_endpoint` for trust | ✅ v2.64 | Proposed (aeoess production impl) |
| `derivation_rights` | ✅ v2.92 (this RFC) | aeoess SDK v1.37.0 (2026-04-08) |
| `credential_lifecycle` | ✅ v2.92 (this RFC) | aeoess SDK v1.37.0 (2026-04-08) |
| Recency-weighted scoring | ❌ planned | Discussed |

ACP implementation predates the A2A proposal by approximately 3–4 months (trust_score/capability_manifest first shipped March 2026). `derivation_rights` and `credential_lifecycle` are co-developed with reference to aeoess's open-source SDK work.

---

## 7. Backward Compatibility

- All new fields (`derivation_rights`, `credential_lifecycle`) are **optional**.
- Existing v2.60–v2.91 implementations continue to work without modification.
- Receivers that do not recognize these fields SHOULD ignore them (forward compatibility).

---

## 8. Security Considerations

- `governance_metadata` is a **self-declaration**. It MUST NOT be treated as authoritative proof of compliance.
- For high-assurance scenarios, receivers SHOULD independently verify claims via the `audit_trail_reference` or `live_endpoint`.
- `revocation_endpoint` SHOULD be called over a mutually-authenticated channel (e.g., with the sender's Ed25519 identity signature).
- `derivation_rights.export_permitted=false` is advisory; enforcement requires out-of-band audit.

---

## 9. Example: Full governance_metadata block (v2.92)

```json
{
  "governance_metadata": {
    "schema_version": "1.0",
    "generated_at": "2026-04-09T13:00:00Z",
    "trust_score": 0.87,
    "live_endpoint": "/governance-metadata",
    "capability_manifest": {
      "search": { "tier": "T1", "status": "available", "deprecated": false },
      "code_exec": { "tier": "T3", "status": "restricted", "deprecated": false }
    },
    "policy_compliance": [
      { "policy": "GDPR-Art5",    "status": "compliant" },
      { "policy": "SOC2-Type2",   "status": "compliant" }
    ],
    "derivation_rights": {
      "retention_permitted": true,
      "retention_ttl": 86400,
      "derivation_classes": ["summarization"],
      "export_permitted": false,
      "export_requires_consent": true,
      "derivation_audit_required": true
    },
    "credential_lifecycle": {
      "max_session_duration": 3600,
      "credential_ttl": 7200,
      "revocation_endpoint": "/identity/revoke",
      "revocation_check_frequency": 300
    },
    "audit_trail_reference": "/interaction-records",
    "interaction_record_count": 42,
    "peer_count": 7,
    "task_count": 15
  }
}
```

---

## 10. References

- [ACP-RFC-001: Skill Authorization](./skill-authorization.md)
- [ACP-RFC-002: Bilateral Interaction Records](./bilateral-interaction-records.md)
- [A2A Issue #1717: Governance metadata in A2A Agent Cards](https://github.com/a2aproject/A2A/issues/1717)
- [aeoess SDK v1.37.0 — Derivation governance primitives](https://github.com/a2aproject/A2A/issues/1717#issuecomment-latest)
- [ACP CHANGELOG v2.60–v2.92](../../CHANGELOG.md)

---

## 11. v3.5 Extension — Governance Proof Suite

> Added in ACP v3.5.0 (2026-04-11)

The `governance` block now includes an optional `proof_suite` sub-object that declares which
cryptographic proof suites the node supports. This enables W3C Data Integrity interoperability
and aligns with the ANP `eddsa-jcs-2022` specification.

### Schema

```json
{
  "governance": {
    "framework": "ACP-RFC-003",
    "version": "1.0",
    "proof_suite": {
      "supported": ["Ed25519Signature2020", "eddsa-jcs-2022"],
      "default": "Ed25519Signature2020",
      "interop_refs": [
        "https://w3c.github.io/vc-data-integrity/",
        "https://www.w3.org/TR/vc-di-eddsa/"
      ]
    },
    "credential_lifecycle": {
      "ttl_seconds": 3600,
      "revocation_endpoint": null,
      "credential_ttl_seconds": 86400
    },
    "audit_mode": "static",
    "policy_ref": null
  }
}
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `proof_suite.supported` | `string[]` | Proof suite identifiers supported by this node |
| `proof_suite.default` | `string` | Currently active proof suite |
| `proof_suite.interop_refs` | `string[]` | W3C spec URLs (documentary only — not enforced at runtime) |

### Backward Compatibility

`proof_suite` is a new sub-field within the existing `governance` block. Clients that do not
recognize `proof_suite` MUST ignore it. The field is always present in ACP v3.5+.
