# ACP Conformance Guide

> **Version:** ACP v1.3 · Last updated: 2026-03-23

This document describes how to verify that an ACP implementation is spec-compliant,
what the conformance levels mean, and how to obtain an unofficial conformance badge.

---

## Table of Contents

1. [Overview](#overview)
2. [Conformance Levels](#conformance-levels)
3. [Running the Test Suite](#running-the-test-suite)
4. [Test Coverage](#test-coverage)
5. [Interpreting Results](#interpreting-results)
6. [Conformance Badge](#conformance-badge)
7. [Implementing from Scratch](#implementing-from-scratch)
8. [Known Limitations](#known-limitations)

---

## Overview

ACP conformance is verified by the **ACP Compatibility Test Suite** located at
`tests/compat/`. It is a black-box HTTP test runner: point it at any running ACP
implementation and it reports which spec requirements pass, fail, or are skipped.

The suite is self-contained (stdlib only, no third-party deps) and runs in under 5 seconds
against a local agent.

---

## Conformance Levels

| Level | Keyword | Meaning |
|-------|---------|---------|
| **Core Compliant** | MUST | All required tests pass (0 FAIL in MUST tier) |
| **Recommended Compliant** | SHOULD | All MUST + all SHOULD tests pass |
| **Full Compliant** | MAY | MUST + SHOULD + all declared optional extensions pass |

> An implementation that fails any **MUST** test is **non-compliant** regardless of
> how many SHOULD/MAY tests it passes.

---

## Running the Test Suite

### Prerequisites

- Python 3.9+
- A running ACP agent (any implementation)
- No extra pip installs required

### Basic usage

```bash
# Clone the ACP repo
git clone https://github.com/Kickflip73/agent-communication-protocol
cd agent-communication-protocol

# Start the reference implementation (optional — to test it yourself)
python3 relay/acp_relay.py --name TestAgent --port 7801

# In another terminal, run the suite
python3 tests/compat/run.py
```

### Against a remote agent

```bash
python3 tests/compat/run.py --url http://remote-agent:7801
```

### With HMAC signing enabled

```bash
python3 tests/compat/run.py \
  --url http://localhost:7801 \
  --secret your-hmac-secret
```

### JSON output (for CI integration)

```bash
python3 tests/compat/run.py --json > results.json
cat results.json
```

### Docker — test a containerised agent

```bash
# Start the reference Docker image
docker run -d --name acp-test -p 7801:7801 \
  ghcr.io/kickflip73/agent-communication-protocol/acp-relay:latest \
  --name TestAgent --port 7801

# Run the suite against it
python3 tests/compat/run.py --url http://localhost:7801

# Cleanup
docker rm -f acp-test
```

---

## Test Coverage

| Suite file | Spec section | Requirement tier | Tests |
|------------|-------------|-----------------|-------|
| `test_agentcard.py` | §3 AgentCard | MUST | Required fields, `acp_version`, capability flags |
| `test_message_send.py` | §4 Message protocol | MUST | `/message:send`, `message_id` idempotency, `failed_message_id` on error |
| `test_tasks.py` | §5 Task state machine | MUST | 5-state transitions (`submitted/working/completed/failed/input_required`), cancel, continue |
| `test_error_codes.py` | §9 Error codes | MUST | Standard error envelope, `error_code` field, `failed_message_id` coverage |
| `test_peers.py` | §7 Multi-session | SHOULD | `/peers`, `/peer/{id}/send` |
| `test_query_skills.py` | §8 QuerySkill | SHOULD | `/skills` endpoint, skill schema |
| `test_hmac.py` | §10 HMAC signing | MAY (opt-in) | `sig` field validation, replay-window rejection — **skipped if not declared in AgentCard** |

Optional extension suites (v1.3):

| Suite | Triggered by | What it tests |
|-------|-------------|---------------|
| AgentCard `availability` block | `capabilities.scheduling: true` in AgentCard | `availability.mode`, `interval_seconds`; `PATCH /.well-known/acp.json` live-update |
| DID identity | `capabilities.did_identity: true` in AgentCard | `did` field format (`did:acp:<base64url>`), `GET /.well-known/did.json` structure |
| Extensions | `capabilities.extensions: true` in AgentCard | `extensions[]` array schema, `GET /extensions`, `POST /extensions/register` |

---

## Interpreting Results

### Example output

```
ACP Compatibility Suite v0.1  →  http://localhost:7801
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

AgentCard ............... ✅ 8/8 PASS
Message Send ............ ✅ 6/6 PASS
Task State Machine ...... ✅ 10/10 PASS
Error Codes ............. ✅ 5/5 PASS
Multi-Session Peers ..... ✅ 5/5 PASS
QuerySkill .............. ✅ 3/3 PASS
HMAC Signing ............ ⏭  SKIP (not declared in AgentCard)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RESULT: COMPLIANT  ✅  37/37 required tests passed
```

### Status symbols

| Symbol | Meaning |
|--------|---------|
| `✅ PASS` | Test passed |
| `❌ FAIL` | Test failed — fix required for compliance |
| `⚠️  WARN` | SHOULD-level test failed — recommended to fix |
| `⏭  SKIP` | Optional test skipped (feature not declared in AgentCard) |

### JSON output schema

```json
{
  "suite_version": "0.1.0",
  "acp_version": "1.3.0-dev",
  "target_url": "http://localhost:7801",
  "compliant": true,
  "summary": { "pass": 37, "fail": 0, "warn": 0, "skip": 1 },
  "suites": [
    {
      "name": "AgentCard",
      "pass": 8, "fail": 0, "warn": 0, "skip": 0,
      "tests": [
        { "id": "AC-01", "name": "has acp_version field", "result": "PASS" }
      ]
    }
  ]
}
```

---

## Conformance Badge

There is no official certification body for ACP (it is an open, community protocol).
However, you can self-certify and display a badge in your project's README:

### Self-certification steps

1. Run `python3 tests/compat/run.py --json > conformance.json` against your implementation
2. Verify `"compliant": true` in the output
3. Commit `conformance.json` to your repo
4. Add the badge below to your README

### Badges (static)

```markdown
<!-- Core compliant (MUST tests pass) -->
![ACP Compliant](https://img.shields.io/badge/ACP-v1.3_compliant-brightgreen?style=flat-square)

<!-- Full compliant (MUST + SHOULD + declared MAY) -->
![ACP Full Compliant](https://img.shields.io/badge/ACP-v1.3_full_compliant-blue?style=flat-square)
```

### Dynamic badge via Shields.io endpoint

If your `conformance.json` is publicly accessible (e.g., from your repo's `main` branch):

```markdown
![ACP Conformance](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/<org>/<repo>/main/conformance.json&style=flat-square)
```

*(Requires your `conformance.json` to follow the [Shields.io endpoint schema](https://shields.io/endpoint).)*

---

## Implementing from Scratch

If you are building a new ACP implementation, the minimum viable set of endpoints to
pass **Core Compliant** is:

### Required endpoints (MUST)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/.well-known/acp.json` | GET | AgentCard — identity + capabilities |
| `/message:send` | POST | Send a message to this agent |
| `/tasks/{id}` | GET | Get task status |
| `/tasks/{id}/cancel` | POST | Cancel a running task |

### Required AgentCard fields

```json
{
  "name": "string",
  "acp_version": "1.x",
  "protocol": "acp",
  "capabilities": {}
}
```

### Recommended endpoints (SHOULD)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/peers` | GET | List connected peers |
| `/peer/{id}/send` | POST | Send message to a specific peer |
| `/skills` | GET | QuerySkill — list agent capabilities |

### Optional endpoints (MAY — declare in `capabilities`)

| Endpoint | Capability flag | Description |
|----------|----------------|-------------|
| `PATCH /.well-known/acp.json` | `scheduling: true` | Live-update AgentCard |
| `GET /.well-known/did.json` | `did_identity: true` | W3C DID Document |
| `GET /extensions` | `extensions: true` | List declared extensions |
| `POST /extensions/register` | `extensions: true` | Register extension at runtime |
| `POST /extensions/unregister` | `extensions: true` | Remove extension at runtime |

### Error envelope (MUST)

All error responses must use:

```json
{
  "error": "ERR_<CODE>",
  "message": "human-readable description",
  "failed_message_id": "<message_id from request, if applicable>"
}
```

Standard error codes: `ERR_INVALID_REQUEST` · `ERR_NOT_CONNECTED` · `ERR_INTERNAL` ·
`ERR_UNAUTHORIZED` · `ERR_TASK_NOT_FOUND` · `ERR_TASK_ALREADY_CANCELED`

---

## Known Limitations

- **No SSE stream suite in compat runner yet** — `test_stream.py` is listed in
  `tests/compat/README.md` but not yet implemented. SSE streaming is tested in
  `tests/integration/` instead.
- **HMAC replay-window testing is timing-sensitive** — the `test_hmac.py` suite
  injects a past `ts` value; ensure your implementation rejects messages older
  than your configured `--hmac-window`.
- **DID / Extension suites not yet in compat runner** — they are in `tests/unit/`;
  a dedicated `test_did.py` and `test_extensions.py` in `tests/compat/` is planned.
- **No certification authority** — ACP is community-driven; self-certification is
  the only current path.
