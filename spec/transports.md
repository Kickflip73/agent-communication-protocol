# ACP Transport Bindings

## HTTP Binding

### Endpoint Convention
```
POST /acp/v1/messages
Content-Type: application/json
Authorization: Bearer <token>  (optional in v0.1)
```

### Request
The HTTP body IS the ACP message envelope (JSON).

### Response
- **202 Accepted** — message received, processing async
- **200 OK** — synchronous response, body is ACP reply envelope
- **400 Bad Request** — invalid envelope
- **404 Not Found** — recipient AID unknown
- **429 Too Many Requests** — rate limited

### Synchronous shortcut
For simple request/response patterns, the HTTP response body MAY contain the reply envelope directly (200 OK).

---

## WebSocket Binding

Connect to `ws://<host>/acp/v1/ws`

After connection, both sides exchange ACP message envelopes as JSON text frames. No framing header needed — each frame is exactly one ACP message.

```
Client → Server: {"acp":"0.1","type":"agent.hello", ...}
Server → Client: {"acp":"0.1","type":"agent.hello", ...}  (server's hello)
Client → Server: {"acp":"0.1","type":"task.delegate", ...}
Server → Client: {"acp":"0.1","type":"task.accept", ...}
Server → Client: {"acp":"0.1","type":"task.progress", ...}
Server → Client: {"acp":"0.1","type":"task.result", ...}
```

---

## MQTT Binding

Topic convention:
```
acp/v1/agent/<aid-encoded>/inbox     — unicast to specific agent
acp/v1/topic/<topic-name>            — pub/sub broadcast
acp/v1/broadcast                     — all agents
```

AID encoding: replace `:` with `_` and `/` with `-`
Example: `did:acp:local:summarizer` → `did_acp_local_summarizer`

QoS:
- `task.delegate` / `task.result` — QoS 1 (at least once)
- `agent.heartbeat` — QoS 0 (fire and forget)
- `event.broadcast` — QoS 0 or 1 depending on criticality

---

## In-Process Binding (for testing)

```python
# Python example
from acp_sdk import InProcessBus, Agent

bus = InProcessBus()
agent_a = Agent("did:acp:local:a", bus)
agent_b = Agent("did:acp:local:b", bus)

# Messages are delivered synchronously in-process
await agent_a.send(task_delegate_message)
```
