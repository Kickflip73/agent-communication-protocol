# ACP Integration Guide — v0.9

> **TL;DR** — Any agent, any language, any framework. Two steps:
> 1. Start `acp_relay.py` → get an `acp://` link
> 2. Share the link with the other agent → they connect
>
> No registration. No central server. No config files (unless you want one).

---

## Quickstart (2 minutes)

```bash
# Install (one dependency for WebSocket transport)
pip install websockets

# Start your agent
python3 acp_relay.py --name AgentA --skills "summarize,translate"

# Output:
#   Your link: acp://1.2.3.4:7801/tok_abc123
#   Share this with the other Agent to connect
```

The other agent (any language, any machine) connects with:

```bash
python3 acp_relay.py --name AgentB --join acp://1.2.3.4:7801/tok_abc123
```

Now both agents can exchange messages via the HTTP API on `localhost`.

---

## Transport Options

ACP selects transport automatically based on network conditions:

| Scenario | Transport | Flag |
|----------|-----------|------|
| Both agents have public IPs / same LAN | **P2P WebSocket** (default) | *(none)* |
| Behind firewall / NAT / K8s | **HTTP Polling Relay** | `--relay` |
| LAN only, want auto-discovery | **mDNS** (v0.7) | `--advertise-mdns` |

**Auto-fallback**: P2P connection attempt times out (10 s) → automatically switches to HTTP relay. The `acp://` link works for both.

### P2P mode (default)

```bash
# Host — creates a new session
python3 acp_relay.py --name AgentA

# Guest — joins existing session
python3 acp_relay.py --name AgentB --join acp://HOST_IP:7801/tok_xxx
```

### Relay mode (firewall-friendly)

```bash
# Host — creates session on public relay
python3 acp_relay.py --name AgentA --relay

# Guest — same command, relay handles routing
python3 acp_relay.py --name AgentB --join acp+relay://relay.example.com/tok_xxx
```

### LAN discovery with mDNS (v0.7)

```bash
# Both agents on the same LAN, advertise themselves
python3 acp_relay.py --name AgentA --advertise-mdns

# Discover nearby agents (no link needed)
curl http://localhost:7901/discover
# → [{"name": "AgentA", "link": "acp://192.168.1.5:7801/tok_xxx", ...}]
```

---

## Port Layout

Each `acp_relay.py` instance occupies two ports:

| Port | Protocol | Purpose |
|------|----------|---------|
| `--port` (default 7801) | WebSocket | P2P peer-to-peer transport |
| `--port + 100` (default 7901) | HTTP | Local control API (your agent talks here) |

Your agent code **only uses the HTTP API** on `localhost:7901`. The WebSocket port is for peer transport only.

---

## Sending & Receiving Messages

### Send a message (any language, just curl)

```bash
curl -s -X POST http://localhost:7901/message:send \
  -H "Content-Type: application/json" \
  -d '{
    "role": "user",
    "text": "Summarize this document: ..."
  }'

# Response:
# {"ok": true, "message_id": "msg_abc123", "server_seq": 42}
```

**Required fields** (v0.9 server-side validation):
- `role` — **required**, must be `"user"` or `"agent"`
- `text` OR `parts` — **required**, at least one must be present

Optional fields:
- `message_id` — client-generated UUID for idempotency; server auto-assigns if omitted
- `context_id` — multi-turn conversation grouping (v0.7)
- `task_id` — link message to an existing task
- `create_task` — `true` to auto-create a task for this message
- `sync` — `true` to block until peer replies (with `timeout` in seconds)

### Send structured parts (v0.5+)

```bash
curl -s -X POST http://localhost:7901/message:send \
  -H "Content-Type: application/json" \
  -d '{
    "role": "user",
    "parts": [
      {"type": "text",  "content": "Analyze this image:"},
      {"type": "file",  "url": "https://example.com/photo.png",
                        "media_type": "image/png", "filename": "photo.png"},
      {"type": "data",  "content": {"invoice_id": 42, "amount": 99.50}}
    ]
  }'
```

### Receive messages (SSE stream)

```bash
# Subscribe to the real-time event stream
curl -N http://localhost:7901/stream

# Events:
# data: {"type": "message", "message_id": "...", "role": "agent", "parts": [...]}
# data: {"type": "status",  "status": "working", "task_id": "task_xxx"}
# data: {"type": "artifact","task_id": "task_xxx", "parts": [...]}
```

### Synchronous request-response (v0.6+)

```bash
curl -s -X POST http://localhost:7901/message:send \
  -H "Content-Type: application/json" \
  -d '{
    "role": "user",
    "text": "What is 2 + 2?",
    "sync": true,
    "timeout": 30
  }'

# Blocks until peer replies, then returns:
# {"ok": true, "message_id": "...", "reply": {"role": "agent", "parts": [...]}}
```

---

## Task Management (v0.5+)

ACP has a built-in task state machine for async workflows:

```
submitted → working → completed
                   → failed
                   → input_required  ← resumable
```

### Create a task

```bash
# Create task alongside message
curl -s -X POST http://localhost:7901/message:send \
  -d '{"role":"user","text":"Process invoice #42","create_task":true}'

# Response includes task object:
# {"ok":true,"message_id":"msg_xxx","task":{"id":"task_yyy","status":"submitted"}}
```

### Poll task status

```bash
curl http://localhost:7901/tasks/task_yyy
# → {"id":"task_yyy","status":"working","created_at":...}

# Long-poll until terminal state
curl "http://localhost:7901/tasks/task_yyy/wait?timeout=60"
```

### Subscribe to task events (SSE)

```bash
curl -N http://localhost:7901/tasks/task_yyy:subscribe
# data: {"type":"status","status":"working"}
# data: {"type":"artifact","parts":[{"type":"text","content":"Result: ..."}]}
# data: {"type":"status","status":"completed"}
```

### Cancel a task

```bash
curl -X POST http://localhost:7901/tasks/task_yyy:cancel
```

### Resume from `input_required`

```bash
curl -X POST http://localhost:7901/tasks/task_yyy/continue \
  -d '{"role":"user","text":"Yes, proceed with option A"}'
```

---

## Multi-Peer Sessions (v0.6+)

One relay instance can maintain connections to multiple peers simultaneously:

```bash
# List all connected peers
curl http://localhost:7901/peers

# Send to a specific peer
curl -X POST http://localhost:7901/peer/PEER_ID/send \
  -d '{"role":"user","text":"Hello, peer!"}'

# Connect to a new peer (adds to existing session)
curl -X POST http://localhost:7901/peers/connect \
  -d '{"link":"acp://OTHER_HOST:7801/tok_yyy"}'
```

---

## Security Features

### HMAC message signing (v0.7)

Both peers share a secret; every message includes a signature. Verification is warn-only (never drops) for graceful interop.

```bash
# Both sides must use the same secret
python3 acp_relay.py --name AgentA --secret "my-shared-key-32chars"
python3 acp_relay.py --name AgentB --join acp://... --secret "my-shared-key-32chars"
```

Messages include:
```json
{
  "message_id": "msg_xxx",
  "sig": "a3f9b2...",
  "trust": {"scheme": "hmac-sha256", "enabled": true}
}
```

### Ed25519 identity signing (v0.8)

Self-sovereign keypair; messages signed with your private key, verifiable by anyone with your public key.

```bash
# Auto-generate keypair at ~/.acp/identity.json
python3 acp_relay.py --name AgentA --identity

# Or specify path
python3 acp_relay.py --name AgentA --identity /path/to/my-keypair.json

# Requires: pip install cryptography
```

Your AgentCard (`/.well-known/acp.json`) will include your public key:
```json
{
  "identity": {
    "public_key": "base64url-encoded-ed25519-pubkey",
    "algorithm": "ed25519"
  }
}
```

---

## AgentCard Discovery

Every ACP agent exposes a standard card at `GET /.well-known/acp.json`:

```bash
curl http://localhost:7901/.well-known/acp.json
```

```json
{
  "name": "AgentA",
  "version": "0.8-dev",
  "acp_version": "0.8",
  "capabilities": {
    "streaming": true,
    "tasks": true,
    "multi_session": true,
    "hmac_signing": false,
    "lan_discovery": false,
    "context_id": true
  },
  "skills": [
    {"id": "summarize", "description": "Summarize documents"},
    {"id": "translate", "description": "Translate text"}
  ],
  "endpoints": {
    "send":   "/message:send",
    "stream": "/stream",
    "tasks":  "/tasks",
    "peers":  "/peers",
    "skills": "/.well-known/acp.json"
  }
}
```

### Query skills at runtime (v0.5+)

```bash
# List all skills
curl -X POST http://localhost:7901/skills/query -d '{}'

# Filter by capability
curl -X POST http://localhost:7901/skills/query \
  -d '{"capability": "summarize", "limit": 5}'
```

---

## Python SDK

The Python SDK wraps the HTTP API with both sync and async clients.

### Sync client

```python
from sdk.python.relay_client import RelayClient

client = RelayClient("http://localhost:7901")

# Send
resp = client.send("Hello from Python!", role="user")
print(resp["message_id"])

# Send with context grouping (v0.7)
resp = client.send("Follow-up question", context_id="ctx_abc")

# Task lifecycle
task = client.create_task({"parts": [{"type": "text", "content": "Process this"}]})
result = client.wait_for_task(task["id"], timeout=60)

# Receive SSE stream
for event in client.stream(timeout=30):
    print(event["type"], event.get("parts"))
```

### Async client (stdlib-only, no aiohttp)

```python
import asyncio
from sdk.python.relay_client import AsyncRelayClient

async def main():
    client = AsyncRelayClient("http://localhost:7901")

    # Send
    resp = await client.send("Hello async!", role="user")

    # Stream events
    async for event in client.stream(timeout=30):
        if event["type"] == "message":
            print("Received:", event.get("parts"))
        elif event["type"] == "status":
            print("Task status:", event.get("status"))

    # Query skills
    skills = await client.query_skills(capability="summarize")

    # Discover LAN peers (v0.7)
    peers = await client.discover()

asyncio.run(main())
```

---

## Node.js SDK

```javascript
import { RelayClient } from './sdk/node/relay_client.mjs';

const client = new RelayClient('http://localhost:7901');

// Send
const resp = await client.send('Hello from Node!', { role: 'user' });
console.log(resp.message_id);

// Send with parts
await client.sendParts([
  { type: 'text', content: 'Analyze this:' },
  { type: 'data', content: { value: 42 } }
], { role: 'user' });

// Task management
const task = await client.createTask({ parts: [{ type: 'text', content: 'Do work' }] });
const result = await client.waitForTask(task.id, 60);

// Stream events
for await (const event of client.stream(30)) {
  console.log(event.type, event.parts);
}
```

---

## Config File (v0.9)

Instead of long command lines, use a config file:

```json
{
  "name": "MyAgent",
  "port": 7801,
  "skills": "summarize,translate",
  "secret": "optional-hmac-key",
  "verbose": false
}
```

```bash
python3 acp_relay.py --config agent.json
# CLI flags override config file values
```

See `relay/examples/` for JSON and YAML examples.

---

## Language Examples

ACP's HTTP API works from any language. The only requirement: send valid JSON.

### curl (baseline)

```bash
curl -X POST http://localhost:7901/message:send \
  -H "Content-Type: application/json" \
  -d '{"role":"user","text":"Hello"}'
```

### Go

```go
payload := `{"role":"user","text":"Hello from Go"}`
resp, _ := http.Post("http://localhost:7901/message:send",
    "application/json", strings.NewReader(payload))
```

### Java

```java
var client = HttpClient.newHttpClient();
var req = HttpRequest.newBuilder()
    .uri(URI.create("http://localhost:7901/message:send"))
    .header("Content-Type", "application/json")
    .POST(HttpRequest.BodyPublishers.ofString(
        "{\"role\":\"user\",\"text\":\"Hello from Java\"}"))
    .build();
client.send(req, HttpResponse.BodyHandlers.ofString());
```

### Rust

```rust
let client = reqwest::Client::new();
client.post("http://localhost:7901/message:send")
    .json(&serde_json::json!({"role": "user", "text": "Hello from Rust"}))
    .send().await?;
```

---

## Integration Checklist

```
□ Start acp_relay.py (get your acp:// link)
□ Share link with peer agent (they run --join)
□ POST /message:send to send (include role + text/parts)
□ GET /stream (SSE) to receive
□ Optional: --secret for HMAC signing
□ Optional: --identity for Ed25519 self-sovereign identity
□ Optional: --advertise-mdns for LAN discovery
□ Optional: --config for persistent settings
```

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `503 ERR_NOT_CONNECTED` | Peer not connected yet | Wait for peer to join, then retry |
| `400 ERR_INVALID_REQUEST: missing required field: role` | `role` field absent | Add `"role": "user"` or `"role": "agent"` |
| `400 ERR_INVALID_REQUEST: invalid role` | `role` not `user`/`agent` | Use exactly `"user"` or `"agent"` |
| `413 ERR_MSG_TOO_LARGE` | Message exceeds limit | Use `--max-msg-size` or send file URL in parts |
| P2P connection fails silently | Firewall / NAT | Use `--relay` flag; relay auto-fallback handles it |
| WebSocket import error | `websockets` not installed | `pip install websockets` |
| Ed25519 import error | `cryptography` not installed | `pip install cryptography` |

---

*Last updated: 2026-03-21 · ACP v0.9*
