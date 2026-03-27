# ACP Core Specification — v1.3

**Status:** Development  
**Authors:** ACP Community  
**Date:** 2026-03-23  
**License:** Apache 2.0  
**Supersedes:** [core-v1.0.md](core-v1.0.md) (incremental — all v1.0 sections remain in effect unless explicitly amended here)  
**See also:** [transports.md](transports.md) · [error-codes.md](error-codes.md) · [identity-v0.8.md](identity-v0.8.md)

> **Stability Promise (v1.x series):**  All fields and endpoints listed as **`stable`** in v1.0
> retain that guarantee. New optional fields added in v1.1–v1.3 start as **`experimental`** and
> may be promoted to `stable` at v2.0. Unknown fields MUST be ignored by receivers.

---

## Summary of Changes

| Version | Change |
|---------|--------|
| v1.1 | `failed_message_id` on all `/message:send` error responses; HMAC replay-window |
| v1.2 | AgentCard `availability` block; `PATCH /.well-known/acp.json`; Rust SDK |
| v1.3 | Extension mechanism; `did:acp:` DID identity; Docker GHCR CI; conformance guide |

---

## §1.2 Amendment — Optional Message Fields (v1.1+)

The following optional field is added to the Message Envelope (§1.2 of core-v1.0.md):

| Field | Type | Since | Stability | Description |
|-------|------|-------|-----------|-------------|
| `sig` | string | v0.7 | **stable** | HMAC-SHA256 signature (see §6.1) |
| `identity` | object | v0.8 | **stable** | Ed25519 identity block (see §6.2) |

*(No new envelope fields in v1.1–v1.3. See §6.1 amendment for HMAC replay-window.)*

---

## §5. AgentCard — v1.3 Schema (Full)

The complete AgentCard schema including all v1.0–v1.3 fields:

```json
{
  "name":        "MyAgent",
  "acp_version": "1.3",
  "version":     "1.3.0-dev",
  "timestamp":   "2026-03-23T09:23:00Z",

  "skills": [
    { "id": "summarize", "name": "summarize" }
  ],

  "capabilities": {
    "streaming":          true,
    "push_notifications": true,
    "input_required":     true,
    "part_types":         ["text", "file", "data"],
    "max_msg_bytes":      1048576,
    "query_skill":        true,
    "server_seq":         true,
    "multi_session":      true,
    "error_codes":        true,
    "hmac_signing":       false,
    "lan_discovery":      false,
    "context_id":         true,
    "identity":           "none",

    "scheduling":         true,   // v1.2 — true when availability block present
    "did_identity":       true,   // v1.3 — true when --identity + DID derivation active
    "extensions":         true    // v1.3 — true when at least one extension declared
  },

  "availability": {               // v1.2 — omitted when not configured
    "mode":               "cron",
    "interval_seconds":   3600,
    "next_available_at":  "2026-03-23T10:00:00Z",
    "timezone":           "UTC"
  },

  "extensions": [                 // v1.3 — omitted when none declared
    {
      "uri":      "https://example.com/ext/code-execution/v1",
      "required": false,
      "params":   { "languages": ["python", "bash"] }
    }
  ],

  "did": "did:acp:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",  // v1.3 — omitted when --identity not set

  "identity": null,

  "trust": {
    "scheme":  "none",
    "enabled": false
  },

  "auth": {
    "schemes": ["none"]
  },

  "endpoints": {
    "send":          "/message:send",
    "stream":        "/stream",
    "card":          "/.well-known/acp.json",
    "tasks":         "/tasks",
    "peers":         "/peers",
    "skills":        "/skills",
    "extensions":    "/extensions",     // v1.3
    "did_document":  "/.well-known/did.json"  // v1.3
  }
}
```

### §5.1 Amendment — `capabilities` New Fields (v1.2–v1.3)

| Field | Type | Since | Default | Description |
|-------|------|-------|---------|-------------|
| `scheduling` | boolean | v1.2 | `false` | `true` when `availability` block is present in AgentCard |
| `did_identity` | boolean | v1.3 | `false` | `true` when agent has a `did:acp:` identifier (requires `--identity`) |
| `extensions` | boolean | v1.3 | `false` | `true` when at least one URI extension is declared |

### §5.2 New — `availability` Block (v1.2)

**Stability:** experimental  
**Capability flag:** `capabilities.scheduling: true`

The `availability` block describes when an agent is expected to be online.
It is OPTIONAL and MUST be omitted from AgentCard when not configured.

```json
"availability": {
  "mode":              "persistent" | "heartbeat" | "cron" | "manual",
  "interval_seconds":  number,         // required for heartbeat/cron modes
  "next_available_at": "ISO 8601",     // optional, hint for callers
  "timezone":          "TZ string"     // optional, e.g. "Asia/Shanghai"
}
```

**`mode` values:**

| Value | Meaning |
|-------|---------|
| `persistent` | Agent is always online (default for long-running services) |
| `heartbeat` | Agent wakes periodically; `interval_seconds` is the poll interval |
| `cron` | Agent runs on a cron schedule; `interval_seconds` is nominal period |
| `manual` | Agent is only online when manually started |

**Live update endpoint (v1.2):**

```
PATCH /.well-known/acp.json   [experimental]
Content-Type: application/json

{ "availability": { "mode": "cron", "interval_seconds": 7200 } }
```

The PATCH request performs a shallow merge on the top-level AgentCard fields.
Nested objects (`availability`, `capabilities`) are replaced in full if provided.
Returns the updated AgentCard on success.

---

## §6.1 Amendment — HMAC Replay-Window (v1.1)

**Stability:** stable  

When `--hmac-window <seconds>` is configured (default: `300`), the server MUST:

1. Parse the `ts` field from the message envelope
2. Compute `age = now - ts` (absolute value, seconds)
3. If `age > hmac_window`: respond with `ERR_INVALID_REQUEST`, `message: "Message timestamp outside replay window"`, HTTP 400
4. If HMAC validation fails: respond with `ERR_UNAUTHORIZED`, HTTP 401

Receivers that do not implement replay-window SHOULD log a warning but MUST NOT drop messages for this reason alone (backwards-compatibility).

---

## §6. Amendment — `failed_message_id` on All Errors (v1.1)

**Stability:** stable  

All `/message:send` error responses (4xx, 5xx) MUST include `failed_message_id` when
the request contained a `message_id` field:

```json
{
  "error":             "ERR_INVALID_REQUEST",
  "message":           "Role field missing",
  "failed_message_id": "msg_7a3f9c2b"
}
```

This applies to all standard error codes: `ERR_INVALID_REQUEST` (all variants),
`ERR_NOT_CONNECTED`, `ERR_INTERNAL`, `ERR_UNAUTHORIZED`.

---

## §7. Extension Mechanism (v1.3) — New Section

**Stability:** experimental  
**Capability flag:** `capabilities.extensions: true`

Extensions allow agents to advertise arbitrary capabilities beyond the core spec.
Each extension is identified by a URI and carries optional parameters.

### §7.1 Extension Object Schema

```json
{
  "uri":      "string",    // REQUIRED — globally unique URI identifying the extension
  "required": false,       // REQUIRED — true if peer MUST support this extension
  "params":   {}           // OPTIONAL — extension-specific parameters
}
```

- `uri` MUST be a valid URI. Recommended: `https://<domain>/ext/<name>/v<version>`
- `required: true` signals that the agent expects peers to understand this extension.
  Peers MAY ignore extensions with `required: false`.
- `params` is freeform JSON. Unknown params MUST be ignored.

### §7.2 Extension API Endpoints

All endpoints require the agent to have `capabilities.extensions: true`.

**List extensions:**

```
GET /extensions
→ { "extensions": [...], "count": 2 }
```

**Register extension at runtime:**

```
POST /extensions/register
Content-Type: application/json

{ "uri": "https://example.com/ext/my-cap/v1", "required": false, "params": {} }

→ 200 OK  { "registered": true, "uri": "..." }
→ 400     { "error": "ERR_INVALID_REQUEST", "message": "uri is required" }
```

Re-registering an existing URI MUST update the entry in-place (upsert semantics).

**Unregister extension:**

```
POST /extensions/unregister
Content-Type: application/json

{ "uri": "https://example.com/ext/my-cap/v1" }

→ 200 OK  { "unregistered": true, "uri": "..." }
→ 404     { "error": "ERR_INVALID_REQUEST", "message": "Extension not found" }
```

### §7.3 AgentCard Merge Semantics

When extensions are registered or unregistered:
- `AgentCard.extensions` is updated in-place
- `AgentCard.capabilities.extensions` is set to `true` if any extension remains, `false` otherwise
- The `timestamp` field in AgentCard is NOT automatically updated (use `PATCH /.well-known/acp.json` for that)

---

## §8. DID Identity (v1.3) — New Section

**Stability:** experimental  
**Capability flag:** `capabilities.did_identity: true`  
**Requires:** `--identity` flag (Ed25519 keypair, introduced in v0.8)

### §8.1 DID Derivation

When `--identity` is active, the agent derives a `did:acp:` identifier from its Ed25519 public key:

```
did:acp:<base64url(ed25519_public_key_bytes)>
```

- `base64url` encoding: RFC 4648 §5 (no padding)
- The DID is deterministic: same keypair → same DID, always
- No external registry, no DNS lookup required

### §8.2 AgentCard Integration

When `capabilities.did_identity: true`, the AgentCard MUST include a top-level `did` field:

```json
{ "did": "did:acp:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK" }
```

When `--identity` is not set, the `did` field MUST be absent from the AgentCard.

### §8.3 DID Document Endpoint

```
GET /.well-known/did.json   [experimental]
```

Returns a W3C DID Core 1.0 compatible document:

```json
{
  "@context": [
    "https://www.w3.org/ns/did/v1",
    "https://w3id.org/security/suites/ed25519-2020/v1"
  ],
  "id": "did:acp:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",
  "verificationMethod": [
    {
      "id": "did:acp:z6Mk...#key-1",
      "type": "Ed25519VerificationKey2020",
      "controller": "did:acp:z6Mk...",
      "publicKeyMultibase": "z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK"
    }
  ],
  "authentication": ["did:acp:z6Mk...#key-1"],
  "assertionMethod": ["did:acp:z6Mk...#key-1"]
}
```

Returns `404` with standard error envelope when `--identity` is not configured.

### §8.4 Peer Verification (informative)

A receiver MAY verify a sender's identity by:

1. Fetch `GET http://<sender-host>/.well-known/did.json`
2. Extract `verificationMethod[0].publicKeyMultibase`
3. Verify the message `sig` field using the extracted Ed25519 public key
4. Confirm `did` in sender's AgentCard matches the `id` in the DID Document

This is informative guidance; strict verification is application-defined.

---

## §9 Task Query API (v1.5.1)

### §9.1 `GET /tasks` — List Tasks

Returns a paginated list of tasks for this relay instance.

```
GET /tasks
```

#### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `state` | string | — | Filter by task status: `submitted` \| `working` \| `completed` \| `failed` \| `input_required` |
| `peer_id` | string | — | Filter by originating peer ID |
| `created_after` | ISO-8601 string | — | Return only tasks whose `created_at` is after this timestamp |
| `updated_after` | ISO-8601 string | — | Return only tasks whose `updated_at` (or `created_at` if absent) is after this timestamp |
| `limit` | integer | 50 | Max tasks per page (1–200) |
| `cursor` | task ID | — | Exclusive keyset cursor: return tasks after this task's position |
| `sort` | string | `created_desc` | Sort order: `created_asc` \| `created_desc` |

#### Response

```json
{
  "tasks":       [...],
  "count":       5,
  "total":       42,
  "has_more":    true,
  "next_cursor": "task_abc123"
}
```

#### Notes

- `created_after` and `updated_after` use ISO-8601 UTC format (`2026-03-24T08:00:00.000000Z`)
- Future timestamps return empty `tasks` list (correct behavior, not an error)
- Invalid timestamp strings do not cause 500; server MAY return 400 ERR_INVALID_REQUEST
- `peer_id` filter matches against `payload.peer_id` in the stored task object
- All query parameters are combinable (AND semantics)

#### Example: Recent working tasks

```
GET /tasks?state=working&updated_after=2026-03-24T08:00:00Z&sort=created_asc
```

---

## §10 Task Cancel Semantics (v1.5.2) — New Section

**Stability:** stable

### §10.1 Cancel is Synchronous and Immediate

ACP task cancellation is **synchronous**: the relay MUST return the final `canceled` state
in the same HTTP response. There is no deferred/async cancel mechanism.

```
POST /tasks/{task_id}:cancel
```

**Success response (HTTP 200):**

```json
{
  "task": {
    "id": "task_abc123",
    "status": "canceled",
    "canceled_at": "2026-03-25T05:55:00Z"
  }
}
```

**Error cases:**

| Condition | HTTP | Error Code |
|-----------|------|-----------|
| Task not found | 404 | `ERR_INVALID_REQUEST` |
| Task already in terminal state (`completed`, `failed`) | 409 | `ERR_TASK_NOT_CANCELABLE` |
| Task already `canceled` | 200 | Returns existing task (idempotent) |

### §10.2 Design Rationale

ACP deliberately omits async cancel semantics. Rationale:

1. **Simplicity**: Callers do not need to poll for cancel completion or register webhooks.
2. **Predictability**: After `:cancel` returns 200, the task is guaranteed to be in `canceled` state — no intermediate states.
3. **Contrast with A2A**: A2A's cancel semantics are debated (issue #1680, unresolved as of 2026-03-25). ACP takes a deliberate stance: if work cannot be interrupted immediately at the relay layer, the relay returns success and the downstream agent is responsible for honoring the `canceled` state on its next interaction.

### §10.3 Agent-Side Cancel Behavior

Agents receiving a `:cancel` request SHOULD:
- Stop generating new output for the associated task
- Not start new sub-tasks or side-effects for this task
- Acknowledge via AgentCard `capabilities.input_required: false` if applicable

Agents are NOT required to roll back or undo work already completed. Cancel is a best-effort signal, not a transaction.

---

## Appendix A: Version History (v1.1–v1.5.2)

| Version | Date | Key Changes |
|---------|------|-------------|
| v1.1 | 2026-03-21/22 | `failed_message_id` on all errors; HMAC replay-window (`--hmac-window`) |
| v1.2 | 2026-03-22 | AgentCard `availability` block; `PATCH /.well-known/acp.json`; Rust SDK |
| v1.3 | 2026-03-22/23 | Extension mechanism (§7); `did:acp:` DID identity (§8); Docker GHCR CI; conformance guide |
| v1.5 | 2026-03-24 | Hybrid identity model (`--ca-cert`); `identity.scheme: ed25519+ca`; Java SDK |
| v1.5.1 | 2026-03-24 | `GET /tasks` time-window filters (`created_after`, `updated_after`); BUG-014 `peer_id` filter fix |
| v1.5.2 | 2026-03-25 | §10 Task Cancel Semantics — explicit synchronous cancel contract; `ERR_TASK_NOT_CANCELABLE` error code |

---

*For full v1.0 spec, see [core-v1.0.md](core-v1.0.md).*  
*For transport bindings, see [transports.md](transports.md).*  
*For conformance testing, see [../docs/conformance.md](../docs/conformance.md).*

---

## §11. AgentCard `limitations` Field (v2.7) — New Section

**Ref:** A2A GitHub #1694 (2026-03-27) — proposal to add `limitations` to AgentCard  
**Status:** ACP v2.7 IMPLEMENTED (A2A #1694 still proposal as of 2026-03-28)

### §11.1 Overview — Three-Part Capability Boundary

ACP v2.7 introduces the `limitations` field to complete the **three-part capability boundary declaration**:

| Field | Type | Declares | Example |
|-------|------|----------|---------|
| `capabilities` | object | What this agent **CAN do** (feature flags) | `{"streaming": true, "http2": false}` |
| `availability` | object | **When** the agent is active (scheduling) | `{"mode": "cron", "interval_seconds": 3600}` |
| **`limitations`** | `string[]` | What this agent **CANNOT do** (hard constraints) | `["no_file_access", "no_internet"]` |

This triangle gives consuming agents — and their orchestrators — a complete picture of an agent's operational envelope without requiring runtime probing.

### §11.2 Schema

```json
{
  "name": "SandboxAgent",
  "limitations": ["no_file_access", "no_internet", "no_shell"],
  "capabilities": { ... },
  "availability": { ... }
}
```

**Field rules:**

- **Type:** `string[]` (JSON array of strings)
- **Position:** Top-level AgentCard field (same level as `capabilities` and `availability`)
- **Required:** NO — OPTIONAL field
- **Default:** `[]` (empty array) when absent or not configured
- **Backward compatibility:** Clients that do not recognize this field MUST ignore it (standard JSON forward-compatibility rule)

### §11.3 Limitation String Conventions

Limitation strings are free-form but SHOULD follow `snake_case` naming. Common well-known values:

| Value | Meaning |
|-------|---------|
| `no_file_access` | Agent cannot read or write local files |
| `no_internet` | Agent has no outbound internet access |
| `no_shell` | Agent cannot execute shell commands |
| `no_code_execution` | Agent cannot run arbitrary code |
| `no_memory` | Agent has no persistent memory between sessions |
| `read_only` | Agent can read but not modify external state |
| `rate_limited` | Agent is subject to rate limiting (see `availability` for scheduling) |
| `sandboxed` | Agent runs in a restricted execution environment |

Custom values are allowed. Implementors SHOULD document custom limitation strings in their AgentCard `description` or linked documentation.

### §11.4 CLI Flag

```bash
# Single limitation
python3 acp_relay.py --name SandboxAgent --limitations no_internet

# Multiple limitations (comma-separated)
python3 acp_relay.py --name SandboxAgent --limitations "no_file_access,no_internet,no_shell"
```

The `--limitations` value is split on commas; leading/trailing whitespace is trimmed per entry.

### §11.5 `/status` Response

The `/status` endpoint includes the `limitations` array:

```json
{
  "acp_version": "2.7.0",
  "limitations": ["no_file_access", "no_internet"],
  ...
}
```

### §11.6 Contrast with `capabilities`

`capabilities` is a **positive** declaration (boolean flags and feature arrays).  
`limitations` is a **negative** declaration (what the agent explicitly cannot do).

These are complementary, not redundant:
- An agent may have `capabilities.streaming: true` AND `limitations: ["no_file_access"]`
- The absence of a capability flag does not imply a limitation; `limitations` is explicit opt-in

### §11.7 Relation to A2A #1694

A2A GitHub issue #1694 (opened 2026-03-27) proposes adding a similar `limitations` field to A2A AgentCard. ACP v2.7 implements this concept on the same day — demonstrating ACP's agility as a lightweight protocol.

Key differences from the A2A proposal:
- ACP `limitations` is at the same level as `capabilities` (A2A proposal TBD)
- ACP explicitly frames it as part of a **3-part boundary triad** with `availability`
- ACP ships working code; A2A #1694 is still an open proposal

