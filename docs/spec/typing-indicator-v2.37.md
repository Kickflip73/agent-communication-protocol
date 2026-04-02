# ACP Spec — Typing Indicator (v2.37)

> **Status**: Stable  
> **Version**: 2.37.0  
> **Released**: 2026-04-02  
> **Dependencies**: ACP Core v0.8, `acp.delivered` (v2.35), `acp.read` (v2.36)

---

## Overview

The Typing Indicator feature (`v2.37`) completes the **ACP Agent Real-time Status Trio**:

| Feature | Version | Frame | Meaning |
|---------|---------|-------|---------|
| Delivery ACK | v2.35 | `acp.delivered` | Message physically arrived ✓ |
| Read Receipt | v2.36 | `acp.read` | Message logically consumed ✓✓ |
| **Typing Indicator** | **v2.37** | **`acp.typing`** | **Peer is composing a reply 🖊** |

This mirrors the WhatsApp/iMessage UX pattern — applied to Agent-to-Agent communication. Neither A2A nor ANP implements equivalent signaling.

---

## Motivation

In multi-turn Agent conversations, a recipient Agent often needs to know:

1. Did my message arrive? (`acp.delivered`)
2. Has the other Agent processed it? (`acp.read`)
3. Is the other Agent currently composing a response? (`acp.typing`)

Without typing indicators, a receiving Agent must either poll `/recv` repeatedly or wait blindly. With `acp.typing`, an Orchestrator can implement live progress feedback, timeout detection, and adaptive task routing.

---

## Protocol

### 1. Sending a Typing Indicator

**Endpoint:** `POST /message:typing`  
**Content-Type:** `application/json`

#### Request Body

```json
{
  "typing": true,
  "peer_id": "tok_optional_peer_id"
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `typing` | boolean | No | `true` | `true` = started typing; `false` = stopped |
| `peer_id` | string | No | (first connected peer) | Target peer identifier |

#### Response (200 OK)

```json
{
  "ok": true,
  "typing": true,
  "ts": "2026-04-02T13:37:00.000000Z"
}
```

#### Error Responses

| Code | `error_code` | Condition |
|------|-------------|-----------|
| 503 | `ERR_NOT_CONNECTED` | No peer currently connected |
| 500 | `ERR_INTERNAL` | WebSocket send failure |

---

### 2. The `acp.typing` Control Frame

When `POST /message:typing` is called, the relay sends the following WebSocket frame to the connected peer:

```json
{
  "type": "acp.typing",
  "from": "<agent_name>",
  "typing": true,
  "ts": "2026-04-02T13:37:00.000000Z"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Always `"acp.typing"` |
| `from` | string | Agent name of the sender |
| `typing` | boolean | `true` = composing; `false` = stopped |
| `ts` | string (ISO 8601) | Timestamp of the typing state change |

**Delivery guarantee:** The frame is sent via `asyncio.run_coroutine_threadsafe` — thread-safe, fire-and-forget. No retry on failure.

---

### 3. Receiving a Typing Indicator

When a relay receives an `acp.typing` frame from its peer, it:

1. **Updates global state:**
   ```
   _status["peer_typing"]       = <bool>
   _status["peer_typing_since"] = <ts>  # null when typing=false
   ```

2. **Updates per-peer state:**
   ```
   _peers[<id>]["typing"]       = <bool>
   _peers[<id>]["typing_since"] = <ts>
   ```
   Peer is matched by `agent_name`, `name`, or `id`; falls back to the sole connected peer.

3. **Broadcasts SSE event** to all `/stream` subscribers:
   ```
   event: typing
   data: {"from": "<name>", "typing": <bool>, "typing_since": "<ts>|null"}
   ```

---

### 4. State Inspection

#### `GET /status`

```json
{
  "peer_typing": false,
  "peer_typing_since": null
}
```

When `typing: true`:
```json
{
  "peer_typing": true,
  "peer_typing_since": "2026-04-02T13:37:00.000000Z"
}
```

#### `GET /peers`

Each peer entry includes:

```json
{
  "id": "tok_abc123",
  "name": "WorkerAgent",
  "connected": true,
  "typing": true,
  "typing_since": "2026-04-02T13:37:00.000000Z",
  ...
}
```

---

### 5. AgentCard Capability Declaration

```json
{
  "capabilities": {
    "typing_indicator": true,
    "delivery_ack":     true,
    "read_receipt":     true
  }
}
```

Discoverable via `GET /status` → `agent_card.capabilities.typing_indicator`.

---

## State Machine

```
              POST /message:typing {typing:true}
              ────────────────────────────────►
[IDLE] ─────────────────────────────────────► [TYPING]
  ▲                                               │
  │        POST /message:typing {typing:false}    │
  │   ◄────────────────────────────────────────── │
  │                                               │
  └────── POST /message:send (reply sent) ────────┘
                (typing auto-stops by convention)
```

> **Note:** ACP does not auto-send `acp.typing {typing:false}` when `POST /message:send` is called. Agents should explicitly stop typing via `POST /message:typing {typing:false}` or by convention after replying. This is intentional to keep the protocol stateless.

---

## Usage Example

### Orchestrator sends task, tracks Worker composing

```python
import httpx

base = "http://localhost:8765"

# Step 1: Orchestrator sends task
httpx.post(f"{base}/message:send", json={
    "text": "Analyze this dataset and return a summary.",
    "role": "user"
})

# Step 2: Worker receives task, starts processing — signals typing
httpx.post(f"{base}/message:typing", json={"typing": True})

# ... Worker runs analysis (e.g., 5–10 seconds) ...

# Step 3: Worker stops typing, sends reply
httpx.post(f"{base}/message:typing", json={"typing": False})
httpx.post(f"{base}/message:send", json={
    "text": "Analysis complete. 3 anomalies detected in rows 14, 27, 55.",
    "role": "agent"
})
```

### Checking peer typing state

```bash
# Poll /status
curl http://localhost:8766/status | jq '{peer_typing, peer_typing_since}'

# Subscribe to SSE stream
curl -N http://localhost:8766/stream
# event: typing
# data: {"from":"WorkerAgent","typing":true,"typing_since":"..."}
```

---

## Interaction with Other v2.3x Features

| Scenario | Expected Flow |
|----------|---------------|
| Worker starts typing | `acp.typing {typing:true}` → Orchestrator `peer_typing=true` |
| Worker sends reply | `acp.delivered` → `acp.read` (auto) → Orchestrator acknowledges |
| Worker stops typing without replying | `acp.typing {typing:false}` → `peer_typing=false`, `peer_typing_since=null` |
| Connection drops mid-typing | `peer_typing` state persists; client should reset on reconnect |

---

## Implementation Notes

### Thread Safety

The HTTP handler runs in a `ThreadingHTTPServer` thread. The WebSocket send is dispatched via:

```python
asyncio.run_coroutine_threadsafe(ws.send(frame), _loop).result(timeout=3)
```

This blocks the HTTP handler thread for up to 3 seconds — acceptable for a control frame send. Future versions may use fire-and-forget semantics.

### No Persistence

Typing state is in-memory only. A relay restart resets `peer_typing` to `false`. There is no typing history.

### No Auto-Timeout

ACP does not auto-expire typing state (e.g., after 30 seconds of no update). Implementations that need timeout behavior should:
1. Track `peer_typing_since` and apply their own timeout logic
2. Or subscribe to the SSE `typing` event and start a local timer

---

## Test Coverage

`tests/test_typing_indicator.py` — 8 tests, all pass in ~5.0s

| Test | Description |
|------|-------------|
| TI1 | `capabilities.typing_indicator` declared in AgentCard |
| TI2 | `/status` includes `peer_typing` (bool) + `peer_typing_since` |
| TI3 | `/peers` includes `typing` + `typing_since` per connected peer |
| TI4 | `POST /message:typing {typing:true}` returns `ok:true` |
| TI5 | Alpha typing→true propagates to Beta's `peer_typing` |
| TI6 | Alpha typing→false resets Beta's `peer_typing` + clears `peer_typing_since` |
| TI7 | Omitting `typing` field defaults to `true` |
| TI8 | Standalone relay (no peer) returns 503 `ERR_NOT_CONNECTED` |

---

## Comparison with Competing Protocols

| Feature | A2A | ANP | **ACP v2.37** |
|---------|-----|-----|----------------|
| Typing indicator | ❌ | ❌ | **✅** |
| Delivered receipt | ❌ | ❌ | ✅ (v2.35) |
| Read receipt | ❌ | ❌ | ✅ (v2.36) |
| Full status trio | ❌ | ❌ | **✅** |

---

## Related Specs

- [Delivery ACK — v2.35](./delivery-ack-v2.35.md) *(planned)*
- [Read Receipt — v2.36](./read-receipt-v2.36.md) *(planned)*
- [Peer Trust Score — v2.34](./peer-trust-v2.34.md)
- [Core Protocol — v0.8](./core-v0.8.md)

---

*Spec authored: 2026-04-02 · ACP Project*
