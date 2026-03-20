# ACP Error Codes — v0.6

> Status: **Stable** (implemented in `relay/acp_relay.py`, commit `c816cb5`)
> Last updated: 2026-03-20

---

## Overview

All ACP error responses follow a consistent JSON envelope:

```json
{
  "ok": false,
  "error": "<human-readable description>",
  "error_code": "<ACP_ERR_CODE>",
  "failed_message_id": "<message_id>",   // optional, see below
  "ts": "2026-03-20T01:21:00Z"
}
```

The `error_code` field is machine-readable and stable across versions.
The `error` field is human-readable and may change.

---

## Error Code Reference

| Code | HTTP Status | Trigger | `failed_message_id` |
|------|-------------|---------|---------------------|
| `ERR_NOT_CONNECTED` | 503 | No peer currently connected | — |
| `ERR_MSG_TOO_LARGE` | 413 | Message exceeds `max_msg_bytes` | ✅ included |
| `ERR_NOT_FOUND` | 404 | Task / peer / resource does not exist | — |
| `ERR_INVALID_REQUEST` | 400 | Missing or malformed request parameters | — |
| `ERR_TIMEOUT` | 408 | Sync reply wait timed out | ✅ included |
| `ERR_INTERNAL` | 500 | Unexpected server-side exception | — |

---

## `failed_message_id`

Inspired by ANP's `failed_msg_id` field (commit `99806f45`).

When present, `failed_message_id` contains the `message_id` of the message that caused the error. This enables **precise retry** without re-sending unrelated messages.

**Populated for:**
- `ERR_MSG_TOO_LARGE` — message was constructed but rejected before sending
- `ERR_TIMEOUT` — message was sent but no reply arrived within `timeout`

**Not populated for:**
- `ERR_NOT_CONNECTED` — no message to reference
- `ERR_NOT_FOUND` — refers to a resource, not a message
- `ERR_INVALID_REQUEST` — message was never constructed
- `ERR_INTERNAL` — may be populated if message_id is available at error site

---

## Endpoint Coverage

The following endpoints return structured error responses:

| Endpoint | Possible Error Codes |
|----------|----------------------|
| `POST /message:send` | NOT_CONNECTED, MSG_TOO_LARGE, INVALID_REQUEST, TIMEOUT, INTERNAL |
| `POST /peer/{id}/send` | NOT_CONNECTED, MSG_TOO_LARGE, INVALID_REQUEST, NOT_FOUND, INTERNAL |
| `POST /tasks/create` | INVALID_REQUEST, INTERNAL |
| `POST /tasks/{id}/update` | NOT_FOUND, INVALID_REQUEST, INTERNAL |
| `POST /tasks/{id}/continue` | NOT_FOUND, INVALID_REQUEST, INTERNAL |
| `POST /tasks/{id}:cancel` | NOT_FOUND, INTERNAL |
| `POST /skills/query` | INTERNAL |
| `GET /peers` | *(never errors)* |
| `GET /peer/{id}` | NOT_FOUND |

---

## Design Decisions

### Why 6 codes instead of more?

ACP targets personal/team scenarios where over-specification is a cost.
Six codes cover the full error surface without requiring callers to handle
dozens of edge cases. Compare A2A's richer taxonomy — appropriate for
enterprise orchestration, not for "two agents send messages".

### Why not HTTP status codes only?

HTTP status codes are coarse. `400` covers both "missing field" and "field
too long". `error_code` gives callers a stable string to `switch` on without
parsing the human-readable `error` message.

### Alignment with ANP

ANP introduced `failed_msg_id` for reliable message delivery tracking.
ACP adopts the same concept under the name `failed_message_id` (snake_case,
consistent with other ACP field names).

---

## Example Responses

### ERR_NOT_CONNECTED
```json
{
  "ok": false,
  "error": "no peer connected",
  "error_code": "ERR_NOT_CONNECTED",
  "ts": "2026-03-20T01:21:00Z"
}
```

### ERR_MSG_TOO_LARGE
```json
{
  "ok": false,
  "error": "message too large (max 1048576 bytes)",
  "error_code": "ERR_MSG_TOO_LARGE",
  "failed_message_id": "msg_abc123def456",
  "ts": "2026-03-20T01:21:00Z"
}
```

### ERR_TIMEOUT
```json
{
  "ok": false,
  "error": "reply timeout",
  "error_code": "ERR_TIMEOUT",
  "failed_message_id": "msg_abc123def456",
  "ts": "2026-03-20T01:21:00Z"
}
```

### ERR_NOT_FOUND
```json
{
  "ok": false,
  "error": "task not found",
  "error_code": "ERR_NOT_FOUND",
  "ts": "2026-03-20T01:21:00Z"
}
```
