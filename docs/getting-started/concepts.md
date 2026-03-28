# Core Concepts

Understanding the five key concepts in ACP.

## 1. The Link

A **link** is a self-contained connection address:

```
acp://1.2.3.4:7801/tok_xxxxxxxxxxxxxxxx
```

| Part | Meaning |
|------|---------|
| `acp://` | Protocol scheme |
| `1.2.3.4:7801` | Agent's WebSocket endpoint (public IP + port) |
| `tok_xxx` | One-time session token |

When you start a relay, it gives you a link. **Send this link to any other agent** to establish a P2P connection. The token is single-use: once a peer connects, it cannot be reused.

## 2. Peers

A **peer** represents a connected agent. After connecting:

```bash
curl http://localhost:7901/peers
```
```json
{
  "peer_001": {
    "peer_id": "peer_001",
    "name": "AgentB",
    "connected": true,
    "link": "acp://...",
    "messages_sent": 5,
    "messages_received": 3
  }
}
```

Each relay maintains its own peer list. Connections are **bidirectional** — after Agent B connects to Agent A's link, both can send to each other.

### Sending to a specific peer

When you have multiple peers, use `/peer/{id}/send` to target one:

```bash
curl -X POST http://localhost:7901/peer/peer_001/send \
     -d '{"role":"agent","parts":[{"type":"text","content":"To peer_001 only"}]}'
```

## 3. Messages

A **message** has a `role` and one or more `parts`:

```json
{
  "role": "agent",
  "parts": [
    {"type": "text", "content": "Hello!"},
    {"type": "data", "data": {"key": "value"}},
    {"type": "file", "mime_type": "text/plain", "content": "SGVsbG8="}
  ],
  "message_id": "msg_abc123",
  "context_id": "ctx_session1"
}
```

### Part types

| Type | Use case |
|------|---------|
| `text` | Natural language, instructions |
| `data` | Structured JSON payloads |
| `file` | Base64-encoded binary content |

### Message IDs

Set `message_id` yourself for **idempotent delivery** — resending the same `message_id` will not duplicate delivery.

## 4. Tasks

Tasks represent work that takes time:

```bash
# Create a task
curl -X POST http://localhost:7901/tasks \
     -d '{"role":"agent","task_id":"task_001","title":"Analyze data"}'

# Update progress
curl -X POST http://localhost:7901/tasks/task_001:update \
     -d '{"status":"working","progress":0.5}'

# Complete
curl -X POST http://localhost:7901/tasks/task_001:update \
     -d '{"status":"completed","result":{"summary":"Done"}}'
```

### Task state machine

```
submitted ──→ working ──→ completed
                    ↘──→ failed
                    ↘──→ cancelling ──→ canceled
                    ↘──→ input_required (can continue)
```

### Subscribe to task events

```bash
curl -N http://localhost:7901/tasks/task_001:subscribe
# event: acp.task.status
# data: {"task_id":"task_001","state":"working","seq":1,"ts":"..."}
```

## 5. Streams (SSE)

The **SSE stream** delivers real-time events to a listener:

```bash
curl -N http://localhost:7901/stream
```

Event types:

| Event | Trigger |
|-------|---------|
| `acp.message` | Incoming message from any peer |
| `acp.task.status` | Task state change |
| `acp.task.artifact` | Task produces output |
| `mdns` | New peer discovered on LAN |

Example stream output:

```
: keepalive

event: acp.message
data: {"role":"agent","parts":[{"type":"text","content":"Hello!"}],"from_peer":"peer_001","message_id":"msg_x","seq":1,"ts":"2026-03-28T10:00:00Z"}

event: acp.task.status
data: {"task_id":"task_001","state":"completed","seq":2,"ts":"2026-03-28T10:00:01Z"}
```

## AgentCard

Every relay exposes its capabilities at:

```bash
curl http://localhost:7901/.well-known/acp.json
```

```json
{
  "name": "AgentA",
  "version": "2.8.0",
  "link": "acp://...",
  "capabilities": {
    "streaming": true,
    "tasks": true,
    "hmac_signing": false,
    "context_id": true,
    "http2": false,
    "mdns_discovery": false
  },
  "limitations": [],
  "extensions": [
    {"uri": "acp:ext:mdns-v1", "required": false}
  ],
  "transport_modes": ["p2p", "relay"],
  "supported_transports": ["http", "ws"]
}
```

## NAT Traversal

ACP uses a three-level strategy to establish P2P connections across any network:

```
Level 1: Direct WebSocket (fast, works on LAN/simple NAT)
Level 2: UDP hole punching via DCUtR (works on most NATs)
Level 3: Cloudflare Worker relay (100% fallback, works everywhere)
```

This is completely transparent — your application code doesn't change regardless of which level is used.

See [NAT Traversal](../nat-traversal.md) for full details.
