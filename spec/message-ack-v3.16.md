# ACP v3.16 — Message Acknowledgement (ACK) Protocol

**Status**: ✅ Implemented  
**Version**: 3.16.0  
**Date**: 2025-05

---

## Overview

ACP v3.16 introduces a lightweight protocol-level acknowledgement mechanism (`acp.ack`) that lets a sender confirm a peer received its message.  This complements the existing delivery receipt (`acp.delivered`, v2.35) with an explicit, blockable handshake.

---

## `acp.ack` Message Type

When a relay receives any business message (non-`acp.ack`) over WebSocket, it automatically replies with an `acp.ack` frame directed at the sender:

```json
{
  "type":           "acp.ack",
  "ack_message_id": "<original message_id>",
  "from":           "<receiver agent name>",
  "timestamp":      1748000000000
}
```

| Field             | Type    | Description                                              |
|-------------------|---------|----------------------------------------------------------|
| `type`            | string  | Always `"acp.ack"`                                       |
| `ack_message_id`  | string  | `message_id` of the message being acknowledged           |
| `from`            | string  | Agent name of the acknowledging relay                    |
| `timestamp`       | integer | Unix epoch milliseconds when the ACK was generated       |

### ACK Transparency

`acp.ack` frames are **not** enqueued in `GET /recv` and do **not** trigger SSE `acp.message` events.  They are consumed internally by the relay and are invisible to application-layer consumers.

### No ACK Loops

An `acp.ack` message does **not** trigger a further `acp.ack` reply, preventing infinite loops.

---

## `POST /message:send` — `require_ack` Parameter

Senders may request a confirmed delivery handshake by adding `require_ack=true` to the request body.

### Request Body Extensions

| Field           | Type    | Default | Description                                                        |
|-----------------|---------|---------|--------------------------------------------------------------------|
| `require_ack`   | boolean | `false` | When `true`, sender blocks until peer's `acp.ack` arrives          |
| `ack_timeout_ms`| integer | `5000`  | Maximum wait in milliseconds (min: 1, max: 30000)                  |

### Success Response (when `require_ack=true` and ACK received)

```json
{
  "ok":           true,
  "message_id":   "msg-abc123",
  "client_msg_id":"msg-abc123",
  "server_seq":   42,
  "acked":        true,
  "task":         null
}
```

The `acked: true` field is **only** present when `require_ack=true` and the peer acknowledged in time.

### Error: ACK Timeout (HTTP 408)

When `require_ack=true` and no `acp.ack` arrives within `ack_timeout_ms`:

```json
{
  "ok":               false,
  "error_code":       "ERR_ACK_TIMEOUT",
  "error":            "ACK timeout: no acp.ack received within 5000ms",
  "failed_message_id":"msg-abc123"
}
```

---

## `capabilities.message_ack`

Relays implementing v3.16 declare:

```json
{
  "capabilities": {
    "message_ack": true
  }
}
```

This capability is advertised in:
- `GET /.well-known/acp.json` (AgentCard)
- `GET /status` (shortcut capabilities block)

---

## Backward Compatibility

`require_ack` defaults to `false`.  Existing callers that do not supply the parameter are unaffected.  The auto-reply `acp.ack` over WebSocket is transparent to the peer application layer.

---

## Timeout Semantics

| Parameter       | Default | Maximum | Notes                                    |
|-----------------|---------|---------|------------------------------------------|
| `ack_timeout_ms`| 5000    | 30000   | Clamped to max; values below 1ms floor to 1ms |

If the peer is offline or disconnects before sending `acp.ack`, the `ERR_ACK_TIMEOUT` error is returned after the timeout expires.

---

## Interaction with Other ACK Types

| Frame              | Direction   | Transparent to /recv | Purpose                                          |
|--------------------|-------------|----------------------|--------------------------------------------------|
| `acp.delivered`    | peer→sender | No (tracked in status) | OS-level delivery receipt (v2.35)               |
| `acp.read`         | peer→sender | No (tracked in status) | Application-level read receipt (v2.36)           |
| **`acp.ack`**      | peer→sender | **Yes** (invisible)  | Protocol-level acknowledgement (v3.16, this spec)|

---

## Reference Implementation

See `relay/acp_relay.py`:
- `_pending_acks` — `{message_id: threading.Event}` registry
- `_ACK_DEFAULT_TIMEOUT_MS = 5000`
- `_ACK_MAX_TIMEOUT_MS = 30000`
- `ERR_ACK_TIMEOUT` error code constant
- `acp.ack` handler in `_handle_ws_message()`
- Auto-ACK send in structured-parts message processing
- `require_ack` / `ack_timeout_ms` handling in `/message:send` POST handler
