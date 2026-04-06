# What's New in ACP — Last 7 Days

> Last updated: 2026-04-07 01:44
> For the full history see [CHANGELOG.md](../CHANGELOG.md)

---

### v2.69.0 — Runtime Limitations Endpoint (2026-04-07)

ACP v2.69 adds **`GET /limitations/runtime`** — a live runtime metrics endpoint that complements
the static `limitations[]` declared in the AgentCard (v2.29). Aligns with A2A #1694 @citriac
Agent Exchange Hub v0.4.0's stable/runtime limitations split.

#### Metrics returned

```bash
curl http://localhost:8765/limitations/runtime
```

```json
{
  "ok": true,
  "runtime": {
    "current_load": 2,
    "queue_depth": 1,
    "active_tasks": 3,
    "total_tasks": 47,
    "memory_usage_mb": 52.4,
    "memory_source": "psutil",
    "peer_count": 2
  },
  "version": "2.69.0",
  "timestamp": 1744034400.0
}
```

| Field | Description |
|-------|-------------|
| `current_load` | Active WebSocket peer connections |
| `queue_depth` | Tasks in `submitted` state |
| `active_tasks` | Non-terminal tasks (submitted/working/input_required) |
| `total_tasks` | All tasks ever created |
| `memory_usage_mb` | Process RSS (psutil → `resource.getrusage` fallback) |
| `peer_count` | Same as `current_load` |

**AgentCard** declares `capabilities.runtime_limitations = true` and `endpoints.runtime_limitations = "/limitations/runtime"`.

---

### v2.68.0 — `trust.signals[]` v2: 12 Signal Types + `GET /trust/signals` (2026-04-06)

ACP v2.68 extends the trust signal inventory to **12 types** and exposes them via a queryable
endpoint, aligning with A2A #1628's `trust.signals[]` proposal.

#### New signal types (v2.68)

| Type | Description |
|------|-------------|
| `bilateral_ir` | Bilateral signed interaction records (v2.59+) |
| `capability_token` | SINT-format Ed25519 capability tokens (v2.57) |
| `wtrmrk` | WTRMRK sequence-root attestation as trust factor (v2.62) |
| `external_token` | Cross-protocol SINT token verification (v2.63) |

#### `GET /trust/signals`

```bash
# All 12 signals
curl http://localhost:8765/trust/signals

# Filter by type
curl "http://localhost:8765/trust/signals?type=bilateral_ir"

# Only enabled signals
curl "http://localhost:8765/trust/signals?enabled=true"
```

**AgentCard** declares `capabilities.trust_signals_v268 = true` and `endpoints.trust_signals = "/trust/signals"`.

---

### v2.67.0 — Direct Message Mode — A2A v1.0.0 `SendMessageResponse` Alignment (2026-04-06)

ACP v2.67 introduces **Direct Message mode**: a lightweight `POST /message/send` endpoint that
returns a `Message` object directly — no Task created, no state machine, no lifecycle management.
This aligns with A2A v1.0.0's `SendMessageResponse.oneof { Task task; Message message; }` pattern.

#### When to use Direct Message vs Tasks

| Use Case | Endpoint | Returns |
|----------|----------|---------|
| Simple query, ping, calculation | `POST /message/send` | `Message` (immediate) |
| Long-running, stateful work | `POST /message:send` (existing) | `Task` (with lifecycle) |

#### `POST /message/send`

```bash
curl -X POST http://localhost:8765/message/send \
  -H "Content-Type: application/json" \
  -d '{"role": "user", "text": "What is 2+2?", "context_id": "ctx-001"}'
```

Response:
```json
{
  "ok": true,
  "type": "message",
  "message_id": "msg-a1b2c3d4",
  "role": "user",
  "parts": [{"type": "text", "text": "What is 2+2?"}],
  "context_id": "ctx-001",
  "timestamp": "2026-04-06T14:00:00Z"
}
```

#### Parts format (A2A aligned)

`parts[]` follows the A2A Part model with three types:

```json
// Text part
{"type": "text", "text": "hello"}

// File part
{"type": "file", "file": {"name": "doc.txt", "mimeType": "text/plain", "bytes": "<base64>"}}

// Data part
{"type": "data", "data": {"key": "value"}}
```

Shorthand: `"text": "..."` is auto-converted to `[{"type":"text","text":"..."}]`.

#### AgentCard

```json
{
  "capabilities": { "direct_message": true },
  "endpoints": { "message_send": "/message/send" }
}
```

#### Size limit

Bodies >1MB return `413`. 70KB and below are accepted normally (limit is `MAX_MSG_BYTES = 1MB`).

#### Tests

`tests/test_direct_message.py` — DM-1..14: **16 tests passed**
- DM-1..3: happy path (text shorthand, parts[], context_id passthrough)
- DM-4..6: role validation, missing role, invalid role
- DM-7..9: parts validation, empty parts fallback, data part
- DM-10..11: message_id dedup / client-provided message_id
- DM-12: Content-Type guard
- DM-13: file part round-trip
- DM-14: size boundary (70KB=200, 1.1MB=413)

---

### v2.66.0 — Task `rejected` Terminal State — A2A v1.0.0 Alignment (2026-04-06)

ACP v2.66 introduces `rejected` as a first-class terminal Task state, aligning with the
[A2A v1.0.0 specification](https://a2a-protocol.org) which distinguishes between a task
that *errored* (`failed`) and a task that an agent *actively refuses to execute* (`rejected`).

#### Why `rejected` ≠ `failed`

| State | Meaning | Triggered by |
|-------|---------|--------------|
| `failed` | Unexpected error, timeout, or system fault | Runtime exception |
| `rejected` | Agent explicitly declines the task | Agent decision / policy |
| `canceled` | Requester cancels an in-progress task | Caller (`POST :cancel`) |

`rejected` is a terminal state — once set, the task cannot be re-activated.

#### New: `POST /tasks/{id}:agent-reject`

Agent-initiated rejection for any non-terminal task.

```bash
curl -X POST http://localhost:8765/tasks/task-abc:agent-reject \
  -H "Content-Type: application/json" \
  -d '{"reason": "Skill not available for this input", "reject_code": "skill_unavailable"}'
```

Response:
```json
{
  "ok": true,
  "task_id": "task-abc",
  "status": "rejected",
  "reason": "Skill not available for this input",
  "reject_code": "skill_unavailable"
}
```

- Idempotent: calling on an already-terminal task returns `ok: true` + `note: "already in terminal state"`
- Unknown task → `404`
- Accepts optional `reason` (string) and `reject_code` (string) in request body

#### Updated: T3 `POST /tasks/{id}:reject`

The human-confirmation rejection endpoint now transitions `confirmation_pending → rejected`
(previously `→ failed`). This better represents the semantics: a human reviewer *actively
declined* the task, not that it errored.

#### Updated: `GET /tasks?status=rejected`

The task list filter now accepts `status=rejected`.

#### AgentCard Updates

```json
{
  "capabilities": {
    "rejected_state": true
  },
  "endpoints": {
    "agent_reject": "/tasks/{id}:agent-reject"
  }
}
```

**Tests**: RJ-1..10 — 9 passed, 1 skipped (T3 human-confirm scenario requires T3 skill)

---

### v2.65.0 — `POST /ir/import-evidence` — APS-Compatible Reputation Update (2026-04-06)

ACP v2.65 closes the bilateral IR → reputation loop by providing a standardized
endpoint for importing external interaction records and generating APS-compatible
`reputation_update` payloads. Aligns with A2A Issue #1718 (`importBilateralEvidence()`).

**New: `POST /ir/import-evidence`**
- Accepts an external bilateral IR record from a peer relay
- Verifies `relay_signature` and `caller_signature` (Ed25519) independently
- Returns `verify` block: `relay_sig_valid`, `caller_sig_valid`, `bilateral_verified`, `errors`
- Returns APS-compatible `reputation_update` payload with `trust_delta`:
  - `+1` — bilateral verified (both signatures valid)
  - `0`  — relay-only verified (no caller signature)
  - `-1` — tampered or no signatures

**New: `GET /ir/imported-evidence`**
- Lists all records previously imported via `POST /ir/import-evidence`
- Supports `?agent_did=` filter and `?limit=` pagination

**New helpers (internal)**
- `_verify_ir_signatures(ir)` — dual Ed25519 verification with error collection
- `_build_reputation_update(ir, verify_result)` — APS `reputation_update` builder
  with `freshness_hint` (seconds since interaction), `aps_schema: "v1"`

**AgentCard**: `capabilities.import_evidence` + `endpoints.import_evidence: "/ir/import-evidence"`

**Tests**: IE-1..20 (20 new tests) — all passing

**Bug fix (BUG-052)**: `test_t3c3` port contention fixed — `_kill_port()` pre-clean +
`websockets.serve(reuse_address=True)` + `wait_http_ready` timeout 20s

---

### v2.64.0 — Bilateral IR Test Vectors + Governance `live_endpoint` (2026-04-06)

ACP v2.64 delivers two interoperability features driven by A2A community discussion:
a deterministic test vector suite for bilateral Interaction Record verification (A2A #1718, @aeoess),
and explicit `live_endpoint` alignment with the APS `serviceEndpoint` governance pattern (A2A #1717).

#### `GET /ir/test-vectors` — Cross-Implementation IR Verification

Requested by @aeoess (A2A Issue #1718): a canonical, deterministic set of test vectors that any ACP-compatible
implementation can use to verify bilateral IR signature logic without running a live relay.

Returns 4 test vectors with SHA-256 seeded Ed25519 keys (fully reproducible):

| ID | Type | Scenario |
|---|---|---|
| `tv-ir-001` | bilateral | Both relay + caller signatures valid |
| `tv-ir-002` | unilateral | Relay-only signature (caller not enrolled) |
| `tv-ir-003` | negative | Tampered payload → `caller_signature_valid: false` |
| `tv-ir-004` | did:key | W3C did:key format in canonical payload, bilateral valid |

**Chain integrity:** `tv-ir-002.previous_hash = sha256(tv-ir-001.canonical_payload)` — same hash-chain
algorithm as live interaction records.

**Determinism guarantee:** Same seed bytes → same Ed25519 keys → same signatures on every call.
The `canonical_bytes_hex` field decodes exactly to `json.dumps(canonical_payload, sort_keys=True)`.

```bash
# Fetch test vectors
curl http://localhost:7901/ir/test-vectors | jq .

# Verify a signature (Python)
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
import base64, json, requests

data = requests.get("http://localhost:7901/ir/test-vectors").json()
v = next(v for v in data["vectors"] if v["id"] == "tv-ir-001")
pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(data["keys"]["relay"]["public_key_b64"] + "=="))
pub.verify(base64.b64decode(v["relay_signature"] + "=="), bytes.fromhex(v["canonical_bytes_hex"]))
print("✅ relay signature valid")
```

**Capability gate:** Requires `--identity` (Ed25519 key loaded). Returns `503` otherwise.

#### `governance_metadata.live_endpoint` — APS serviceEndpoint Alignment

Inspired by A2A #1717 (`passportToAgentCard()` APS live governance endpoint pattern):
`GET /governance-metadata` now includes a `live_endpoint` field pointing back to itself.

```json
{
  "governance_metadata": {
    "live_endpoint": "/governance-metadata",
    "trust_score": 0.85,
    ...
  }
}
```

This matches the APS pattern where an `AgentCard.serviceEndpoint` URL allows the receiver to
query a live trust profile rather than relying on a static snapshot embedded in a token.

#### New AgentCard fields

```json
{
  "capabilities": {
    "ir_test_vectors": true
  },
  "endpoints": {
    "ir_test_vectors": "/ir/test-vectors"
  }
}
```

---

### v2.63.0 — Cross-Protocol Token Verification: `GET /identity/did-key` + `POST /verify/external-token` (2026-04-06)

ACP v2.63 closes the cross-protocol interoperability gap identified in A2A Issue #1713 (@pshkv, @viftode4).
Any agent holding a SINT-format capability token — issued by APS v1.32.0 or SINT — can now present it to an
ACP relay for cryptographic verification, without any code changes on either side.

**The problem:** ACP relays could issue their own capability tokens (v2.57), but had no way to verify tokens
from other systems (APS, SINT, future protocols). The `did:key` derivation algorithm was compatible, but the
verification endpoint didn't exist.

**The solution:** Two new endpoints complete the interoperability story.

#### `GET /identity/did-key`

Returns this relay's W3C [did:key](https://w3c-ccg.github.io/did-method-key/) identifier and full public key material:

```json
{
  "ok": true,
  "did_key": "did:key:z6MkpK7WQSpmbJUMxqa3EP2CeA7DTrD12H1Xhuwo5VaCPP9m",
  "did_acp": "did:acp:kn6RtnQsQuntheAxlH1tCUV806wLfIC1ISEZ05M3btQ",
  "public_key_b64": "kn6RtnQsQuntheAxlH1tCUV806wLfIC1ISEZ05M3btQ",
  "public_key_hex": "92...7e",
  "algorithm": "Ed25519",
  "multicodec": "0xed01"
}
```

The `did_key` field uses multicodec `[0xed, 0x01]` + base58btc encoding — byte-for-byte identical
to APS v1.32.0 `toDIDKey()` and SINT `keyToDid()`. No adaptation layer required.

#### `POST /verify/external-token`

Accepts a SINT-format capability token and performs 7-step cryptographic verification:

```bash
curl -s http://localhost:18363/verify/external-token \
  -H "Content-Type: application/json" \
  -d '{
    "token": {
      "subject": "<64-hex-char-Ed25519-pubkey>",
      "resource": "acp://relay.example/skills/invoke",
      "actions":  ["invoke"],
      "tier":     "T2_act",
      "exp":      1775000000,
      "signature":"<Ed25519-hex-sig>"
    }
  }'
```

Response (valid token):
```json
{
  "ok": true,
  "valid": true,
  "expired": false,
  "subject_did": "did:key:z6Mkq3dfNXFN...",
  "relay_did_key": "did:key:z6MkpK7WQ...",
  "fields_verified": [
    "required_fields",
    "expiry_not_expired",
    "subject_pubkey_decoded",
    "did_key_derived",
    "canonical_payload_built",
    "signature_valid"
  ]
}
```

#### The 7-Step Verification Pipeline

| Step | Check | Failure Mode |
|------|-------|-------------|
| 1 | Required fields present | `ok=false, error="missing required fields"` |
| 2 | Expiry (`exp`) check | `ok=false, expired=true` |
| 3 | Subject pubkey decode (64 hex → 32 bytes) | `ok=false, error="subject must be 64 hex chars"` |
| 4 | did:key derivation (multicodec 0xed01 + base58btc) | — |
| 5 | Canonical payload: `subject\|resource\|actions_csv\|tier\|exp_or_0` | — |
| 6 | Ed25519 signature verification | `ok=false, valid=false` |
| 7 | Optional MoltTrust registry query (if configured) | — |

#### Cross-Protocol Compatibility

ACP's `did:key` derivation is validated against the published cross-verify benchmark from A2A #1713:
**9/9 test vectors pass** with zero code changes between APS v1.32.0, SINT, and ACP.

This means:
- A token issued by an APS relay can be verified by an ACP relay
- A token issued by an ACP relay carries a `subject_did` recognizable to SINT implementations
- The `relay_did_key` in every response lets the receiving party verify which relay attested the token

#### AgentCard

```json
{
  "capabilities": {
    "external_token_verify": true
  },
  "endpoints": {
    "did_key":               "/identity/did-key",
    "external_token_verify": "/verify/external-token"
  }
}
```

`external_token_verify` is `true` only when the relay has an Ed25519 identity loaded (`--identity`).

---

### v2.62.0 — `wtrmrk_sequence_root`: Factor 4 Attestation History in `effective_tier` (2026-04-06)

ACP v2.62 adds the fourth factor to the `effective_tier` formula: **external attestation history**
from the WTRMRK registry. Inspired by A2A Issue #1716 (@64R3N, @MoltyCel, @aeoess), who identified
that `delegation_depth` is a proxy variable — the real signal is whether the agent has a verifiable
on-chain attestation history.

#### Background: Why a Fourth Factor?

The v2.58 three-factor formula was:
```
effective_tier = max(tier_rule, delegation_depth_floor, base + reputation_adj)
```

`reputation_adj` is computed from **local relay knowledge** — messages seen, card verification, trust signals.
This is useful for known peers, but is **blind to external reputation** for first-time connections.

`wtrmrk_sequence_root` provides an external Merkle commitment anchored to a public registry, allowing
the relay to query an attestation history that is independent of local peer memory.

#### WTRMRK Grade → `attestation_history_adjustment`

| Grade | Meaning | `wtrmrk_adj` |
|-------|---------|--------------|
| `None` | Query failed (network error, unknown root) | `0` — fail-closed, neutral |
| `0` | No on-chain record — completely unknown | `+1` — raise floor |
| `1` | Basic activity, low history depth | `0` — neutral |
| `2` | Established agent, verified identity anchor | `0` — neutral |
| `3` | High-reputation, hardware-attested, long track record | `-1` — may lower floor |

#### Asymmetric Safety Rule

```python
combined_adj = clamp(-1, +1, reputation_adj + wtrmrk_adj)
if reputation_adj == +1 or wtrmrk_adj == +1:
    combined_adj = max(0, combined_adj)  # either hostile signal → cannot lower floor
```

This means:
- **-1 requires agreement**: both `reputation_adj=-1` AND `wtrmrk_adj=-1` to lower the floor
- **+1 wins alone**: a single hostile signal (unknown peer OR unknown on-chain) raises the floor
- Defense in depth: two independent channels must both certify trust before floor is relaxed

#### Usage

```bash
# POST /tasks with wtrmrk_sequence_root in metadata
curl -X POST http://127.0.0.1:<http_port>/tasks \
  -H 'Content-Type: application/json' \
  -d '{
    "skill_id": "transfer_funds",
    "role": "agent",
    "payload": {"amount": 100, "to": "0xabc..."},
    "metadata": {
      "wtrmrk_sequence_root": "<base64url_merkle_commitment>"
    }
  }'

# Inspect effective_tier factors with wtrmrk
curl "http://127.0.0.1:<http_port>/skills/transfer_funds/effective-tier?wtrmrk_sequence_root=<root>"
# Returns: factors.wtrmrk_queried=true, factors.wtrmrk_grade=2, factors.wtrmrk_adj=0, factors.combined_adj=0
```

#### Full Four-Factor Response Example

```json
{
  "skill_id": "transfer_funds",
  "effective_tier": "T2",
  "factors": {
    "tier_rule": "T2",
    "delegation_depth": 0,
    "depth_floor": null,
    "reputation_adj": 0,
    "wtrmrk_sequence_root": "abc123xyz",
    "wtrmrk_queried": true,
    "wtrmrk_grade": 2,
    "wtrmrk_adj": 0,
    "combined_adj": 0,
    "effective_tier": "T2"
  }
}
```

#### AgentCard Capability

```json
{
  "capabilities": {
    "effective_tier_computation": true,
    "wtrmrk_attestation": true
  }
}
```

Peers can check `wtrmrk_attestation` to know whether WTRMRK-based Factor 4 is active
before including `metadata.wtrmrk_sequence_root` in task requests.

---

### v2.61.0 — Complete Bilateral Signing: `caller_signature` in Interaction Records (2026-04-06)

ACP v2.61 closes the **unilateral-attestation gap** in interaction records.
Inspired by A2A Issue #1718 (0 comments when ACP shipped); external community validation
confirmed that relay-only signing is repudiable — the relay can forge or selectively reveal records.

#### The Problem

In v2.59, interaction records contained only a `relay_signature` — a signature by the relay itself.
This is useful, but **unilateral**: the relay signs what it wants. A dishonest relay could fabricate
records, change the `task_id`, or omit records entirely — and the caller has no cryptographic voice.

#### The Solution: caller_signature

```json
{
  "id": "ir_abc123",
  "type": "interaction_record",
  "relay_did": "did:acp:AbcXyz...",
  "caller_did": "did:acp:DefGhi...",
  "task_id": "task_abc",
  "skill_id": "summarize",
  "sequence_a": 7,
  "previous_hash": "sha256:deadbeef...",
  "timestamp": "2026-04-06T02:55:00Z",
  "relay_signature": "base64url...",
  "caller_token_hash": "sha256:...",
  "caller_signature": "base64url...",
  "caller_public_key": "base64url...",
  "caller_signature_valid": true,
  "bilateral": true
}
```

#### Canonical Payload (what the caller signs)

```
<relay_did>|<caller_did>|<task_id>|<sequence_a>|<timestamp>
```

The caller creates an Ed25519 signature over this string, encoding result as base64url.
The relay verifies it using `caller_public_key` (raw Ed25519 bytes, base64url).

#### Usage

```bash
# Generate a keypair (one-time)
python3 -c "
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, PrivateFormat, NoEncryption
import base64
priv = Ed25519PrivateKey.generate()
pub = priv.public_key()
pub_b64 = base64.urlsafe_b64encode(pub.public_bytes(Encoding.Raw, PublicFormat.Raw)).rstrip(b'=').decode()
priv_b64 = base64.urlsafe_b64encode(priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())).rstrip(b'=').decode()
print('PUBLIC:', pub_b64)
print('PRIVATE:', priv_b64)
"

# POST /tasks with caller_signature
# (caller computes: relay_did|caller_did|task_id|sequence_a|timestamp, then signs)
curl -X POST http://127.0.0.1:<http_port>/tasks \
  -H 'Content-Type: application/json' \
  -d '{
    "skill_id": "summarize",
    "role": "agent",
    "payload": {"text": "analyze this"},
    "record": true,
    "caller_signature": "<base64url_ed25519_sig>",
    "caller_public_key": "<base64url_public_key>"
  }'
```

#### `bilateral` Semantics

| relay_signature | caller_signature_valid | bilateral |
|----------------|----------------------|-----------|
| present (relay has `--identity`) | `true` | **`true`** ✅ |
| present | `false` (bad sig) | `false` |
| present | `null` (no sig given) | `false` |
| absent (no `--identity`) | `true` | `false` |

#### AgentCard Capability

```json
{
  "capabilities": {
    "interaction_records": true,
    "bilateral_interaction_records": true
  }
}
```

Peers can check `bilateral_interaction_records` to know whether their caller_signature
will be verified before relying on non-repudiation semantics.

---

### v2.60.0 — Governance Metadata in AgentCard (2026-04-06)

ACP v2.60 adds **governance metadata** to the AgentCard — a structured block declaring an agent's
trust posture, capability manifest, policy compliance, and audit trail reference.
Inspired by A2A Issue #1717 (Microsoft agent-governance-toolkit, 0 comments);
ACP ships the working implementation before A2A spec discussion concludes.

#### Governance Metadata Block

```json
{
  "governance_metadata": {
    "schema_version": "1.0",
    "generated_at": "2026-04-06T09:28:00Z",
    "trust_score": 0.78,
    "capability_manifest": {
      "transfer-funds": { "tier": "T3", "status": "available", "deprecated": false },
      "summarize":      { "tier": "T1", "status": "available", "deprecated": false }
    },
    "policy_compliance": [
      { "policy": "acp-security-v1", "status": "compliant" },
      { "policy": "gdpr",            "status": "compliant"  }
    ],
    "audit_trail_reference": "/interaction-records",
    "interaction_record_count": 42,
    "peer_count": 3,
    "task_count": 157
  }
}
```

#### How the trust_score is computed

When no explicit override is set, the relay computes a heuristic trust score based on its
own runtime activity:

```
trust_score = 0.3
            + peer_count × 0.04
            + interaction_record_count × 0.005
            + task_count × 0.002
  (clipped to [0.0, 1.0])
```

This reflects "earned" trust: a relay that has connected to many peers, completed many tasks,
and generated many signed interaction records is treated as more trustworthy than a new relay
with no history.

#### Capability Manifest

`capability_manifest` is auto-derived from the AgentCard's `skills[]` list:

```json
"capability_manifest": {
  "<skill_id>": {
    "tier":       "T0" | "T1" | "T2" | "T3",
    "status":     "available" | ...,
    "deprecated": false
  }
}
```

When `--governance-metadata` provides an explicit manifest, that overrides the auto-derived one.

#### New CLI: `--governance-metadata`

```bash
python3 acp_relay.py --port 7700 \
  --governance-metadata '{
    "trust_score": 0.9,
    "policy_compliance": [
      {"policy": "acp-security-v1", "status": "compliant"}
    ],
    "audit_trail_reference": "https://audit.example.com/relay-1"
  }'
```

Also accepts a path to a JSON file:

```bash
python3 acp_relay.py --governance-metadata /etc/acp/governance.json
```

#### New Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/governance-metadata` | Live governance metadata block (always fresh) |
| `PATCH`| `/governance-metadata` | Update writable fields at runtime |

**PATCH writable fields:** `trust_score` (0.0–1.0), `policy_compliance` (array), `audit_trail_reference` (string), `capability_manifest` (object), `schema_version` (string).
**Read-only (auto-computed, silently ignored on PATCH):** `generated_at`, `peer_count`, `task_count`, `interaction_record_count`.

```bash
# Override trust_score at runtime
curl -X PATCH http://localhost:7800/governance-metadata \
  -H 'Content-Type: application/json' \
  -d '{"trust_score": 0.95}'
# → {"ok": true, "updated": ["trust_score"], "governance_metadata": {...}}
```

#### AgentCard Changes

```json
"capabilities": {
  ...
  "governance_metadata": true
},
"endpoints": {
  ...
  "governance_metadata": "/governance-metadata"
}
```

`capabilities.governance_metadata` is `false` when `--governance-metadata` is not configured.

---

### v2.59.0 — Bilateral Interaction Records: Signed Audit Trail per Task (2026-04-06)

ACP v2.59 introduces **bilateral interaction records** — a lightweight, relay-signed audit primitive
that creates a tamper-evident chain of task invocations. Inspired by A2A Issue #1718 (proposed
2026-04-05, 0 comments); ACP ships the working implementation ahead of spec finalization.

#### How It Works

When a client submits `POST /tasks` with `record: true`, the relay generates an `interaction_record`:

```json
{
  "id": "ir-a3f7bc12",
  "type": "interaction",
  "relay_did": "did:acp:z6Mk...",
  "caller_did": "did:acp:z6Mk...caller",
  "task_id": "task-xyz",
  "skill_id": "transfer-funds",
  "sequence_a": 42,
  "previous_hash": "sha256:e3b0c44298fc1c149...",
  "timestamp": "2026-04-06T06:18:00Z",
  "quality_hint": null,
  "caller_token_hash": "sha256:abc123...",
  "relay_signature": "base64url...",
  "relay_public_key": "base64url..."
}
```

#### Chain Continuity

Each record's `previous_hash` is the sha256 of the prior record's canonical JSON, forming
an append-only audit chain. The first record has `previous_hash: "genesis"`.
`sequence_a` is a monotonic counter — any gap signals tampering or missing records.

#### Caller Token Hash

If a `capability_token` (SINT format, v2.57) was provided in the task request, its `jti`
is hashed (`sha256(jti)`) and recorded in `caller_token_hash` — linking the token issuance
event to the invocation event without exposing the token itself.

#### New Endpoints

```http
POST /tasks                             # Add "record": true to request body
GET  /interaction-records               # List all interaction records
GET  /interaction-records?skill_id=X    # Filter by skill
GET  /interaction-records?peer_id=Y     # Filter by caller DID substring
GET  /interaction-records?limit=N       # Limit results (default: 100)
```

#### AgentCard Capability
```json
{ "capabilities": { "interaction_records": true } }
```

#### Design Philosophy

ACP's implementation is intentionally **relay-anchored** (only relay signs) rather than
bilateral (both sides sign). This means:
- No caller-side signing infrastructure required
- Works with any ACP client (including curl-only agents)
- Full non-repudiation for the relay side; caller identity anchored via DID + optional token hash
- Future v2.x can add optional `caller_signature` for full bilateral signing

---

### v2.58.0 — effective_tier: Three-Factor Dynamic Authorization (2026-04-06)

ACP v2.58 implements **dynamic effective tier computation** — inspired by A2A Issue #1716 comment (@64R3N), shipped *before* the A2A spec reached consensus.

#### The Three-Factor Formula

```
effective_tier = max(tier_rule, depth_floor(principal_chain.len), reputation_adj)
```

| Factor | Source | Range |
|--------|--------|-------|
| `tier_rule` | Skill's declared `authorization_tier` | T0..T3 |
| `depth_floor` | `min(len(principal_chain), 3)` | T0..T3 |
| `reputation_adj` | Peer trust history (-1/0/+1) | ±1 step |

**Key design decisions:**
- `rep_adj` is **only applied when `base_int ≥ T2`** — T0/T1 skills remain auto-execute regardless of caller reputation
- T3 is always T3 (immune to any downgrade)
- Unknown peers get `rep_adj = +1` (conservative); known+verified+active peers get `-1` (fast-track)

#### New Endpoint

```http
GET /skills/{skill_id}/effective-tier?peer_id=<did>
```

Returns full factor breakdown for transparency and debugging:

```json
{
  "skill_id": "my-skill",
  "effective_tier": "T2",
  "factors": {
    "tier_rule": "T1",
    "delegation_depth": 2,
    "depth_floor": "T2",
    "reputation_adj": 0,
    "effective_tier": "T2"
  }
}
```

#### Bug Fix
- `DELETE /principal-chain/<did>`: DIDs containing colons (e.g. `did:example:xxx`) were being URL-encoded as `%3A` in the path, causing 404 mismatches. Now correctly URL-decoded.

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
