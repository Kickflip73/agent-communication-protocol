# A2A / ANP Research Scan — 2026-03-20 Noon

**By:** J.A.R.V.I.S. | **ACP version context:** v0.6-dev | **Scan time:** 2026-03-20 12:21 CST

---

## Summary

- **A2A main branch:** No new commits since morning scan. TSC governance mode = slow feature cadence. ACP fast-iteration window persists.
- **ANP:** No new commits since 2026-03-05. Still dormant.

---

## Finding 1: A2A Error Format Inconsistency (Issue #1643)

**Source:** https://github.com/a2aproject/A2A/issues/1643  
**Opened:** 2026-03-16 | **Status:** Open

### What it reveals

A2A spec has an internal contradiction:
- **Section 6** examples use **RFC 7807 Problem Details** (`application/problem+json`):
  ```json
  { "type": "...", "title": "...", "status": 400, "detail": "..." }
  ```
- **Section 11.6** mandates **AIP-193** format (Google's internal API style guide).

This is a non-trivial bug: any A2A implementer reading different sections will produce incompatible error responses.

### ACP implication

Our `spec/error-codes.md` defines a clean, unified error format:
```json
{
  "ok": false,
  "error": "ERR_NOT_CONNECTED",
  "message": "No peer connected",
  "failed_message_id": "msg_abc123"
}
```
This is **simpler and self-consistent** — no dependency on RFC 7807 or AIP-193. The A2A inconsistency confirms ACP's approach of avoiding external spec dependencies is the right call for a lightweight protocol.

**Action:** None needed. Document as a validation of ACP error design.

---

## Finding 2: Custom HTTP Headers — Extension Classification (Issue #1653)

**Source:** https://github.com/a2aproject/A2A/issues/1653  
**Opened:** 2026-03-17 | **Status:** Open

### What it reveals

A user asked: do custom HTTP headers belong to **Data Extensions** or **Profile Extensions** in A2A?

The question is unresolved in A2A docs, reflecting a general ambiguity in their extension model.

### ACP implication

Our `spec/transports.md` (v0.2, commit cb88475) already draws a cleaner line:

| Category | Definition | Examples |
|----------|-----------|---------|
| **Protocol Binding** | How bytes travel (transport layer) | WS, stdio, HTTP relay |
| **Extension** | Additional fields in the message envelope | `message_id`, `task_id`, `to_peer` |

Custom HTTP headers are a **Protocol Binding concern** in ACP — they belong to the transport binding definition, not to the message model. This is a clearer answer than A2A currently provides.

**Action:** Consider adding a note in `spec/transports.md` §Binding A (WS) clarifying that transport-level headers (auth tokens, tracing) are Binding concerns, not Extensions. Add to v0.6 polish list.

---

## Meta-observation: A2A Documentation Debt

Issues #1648, #1649, #1650, #1651 (all opened 2026-03-17, all "[Bug](docs): User Experience") indicate A2A is struggling with documentation consistency as the spec grows complex. This is a structural risk for enterprise adoption despite Google's backing.

**ACP lesson:** Keep spec small and self-consistent. A compact spec is maintainable; a large spec accumulates contradictions.

---

## ANP

No new activity since 2026-03-05. Will re-check next week.

---

## v0.7 Action Items (updated)

| Item | Source | Priority |
|------|--------|----------|
| Lightweight HMAC identity signal | A2A #1575 user pain | High |
| `trust` field reservation in AgentCard | A2A #1575 | Medium |
| Transport Binding clarification for HTTP headers | A2A #1653 | Low (polish) |
| ANP-style `failed_message_id` | Already implemented ✅ | Done |
