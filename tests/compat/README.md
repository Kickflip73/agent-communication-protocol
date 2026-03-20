# ACP Compatibility Test Suite

Black-box HTTP tests that verify **any ACP implementation** complies with the spec.

Point it at a running agent and it reports which ACP spec requirements pass or fail.

## Quick Start

```bash
# Against local acp_relay.py (default port 7801)
python3 tests/compat/run.py

# Against a remote agent
python3 tests/compat/run.py --url http://remote-agent:7801

# JSON output (for CI)
python3 tests/compat/run.py --json > results.json

# Verbose
python3 tests/compat/run.py -v
```

## What It Tests

| Suite | Spec Section | Tests |
|-------|-------------|-------|
| `test_agentcard.py` | AgentCard (§3) | Required fields, capability declarations |
| `test_message_send.py` | Message protocol (§4) | /message:send, message_id idempotency |
| `test_tasks.py` | Task state machine (§5) | 5-state transitions, cancel, continue |
| `test_stream.py` | SSE stream (§6) | /stream endpoint, event types |
| `test_peers.py` | Multi-session (§7) | /peers, /peer/{id}/send |
| `test_query_skills.py` | QuerySkill (§8) | /skills endpoint |
| `test_error_codes.py` | Error codes (§9) | Standard error format, error_code field |
| `test_hmac.py` | HMAC signing (§10, optional) | sig field validation (skipped if not declared) |

## Compliance Levels

- **MUST** — Required by spec. Failure = non-compliant.
- **SHOULD** — Recommended. Failure = warning.
- **MAY** — Optional extension. Skipped if not declared in AgentCard.

## Output Example

```
ACP Compatibility Suite v0.1  →  http://localhost:7801
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

AgentCard ............... ✅ 8/8 PASS
Message Send ............ ✅ 6/6 PASS
Task State Machine ...... ✅ 10/10 PASS
SSE Stream .............. ✅ 4/4 PASS
Multi-Session Peers ..... ✅ 5/5 PASS
QuerySkill .............. ✅ 3/3 PASS
Error Codes ............. ✅ 5/5 PASS
HMAC Signing ............ ⏭  SKIP (not declared in AgentCard)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RESULT: COMPLIANT  ✅  41/41 required tests passed
```
