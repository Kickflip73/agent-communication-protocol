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

> **Note:** The legacy `sdk/python/acp_sdk/` package is still available for backward compatibility.
> For new projects, use the pip-installable `acp-client` package instead:
> `pip install acp-client`

---

## Python SDK — LangChain Integration (v1.8.0+)

`acp-client` v1.8.0 ships a first-class LangChain adapter that wraps any ACP Relay endpoint
as a `BaseTool`, allowing any LangChain Agent to communicate with remote ACP peers with **zero
changes to the core SDK** (LangChain remains an optional dependency).

### Install

```bash
pip install "acp-client[langchain]"
# equivalent to:
pip install acp-client langchain
```

### Quick-start

```python
from acp_client.integrations.langchain import ACPTool, ACPCallbackHandler, create_acp_tool
from langchain.agents import initialize_agent, AgentType
from langchain_openai import ChatOpenAI

# 1. Create the ACP tool pointing at a running relay + peer
tool = create_acp_tool(
    relay_url="http://localhost:8765",   # local ACP Relay endpoint
    peer_id="agent_b",                   # session-id of the remote peer
    timeout=30,                          # seconds to wait for a reply
)

# 2. (Optional) Add a callback handler for audit logging
handler = ACPCallbackHandler()

# 3. Wire up a LangChain agent
llm = ChatOpenAI(model="gpt-4o")
agent = initialize_agent(
    [tool],
    llm,
    agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
    callbacks=[handler],
    verbose=True,
)

# 4. Run — the agent can now delegate to agent_b via ACP
result = agent.run("Ask agent_b to summarise the latest AI news")
print(result)
```

### API Summary

| Class / Function | Description |
|-----------------|-------------|
| `ACPTool(relay_url, peer_id, timeout)` | `BaseTool` subclass — `name="acp_send"`; `_run` sync, `_arun` async |
| `ACPCallbackHandler(log_level)` | `BaseCallbackHandler` — logs tool start/end/error; accumulates `_calls` list |
| `create_acp_tool(relay_url, peer_id, timeout)` | Factory helper for `ACPTool` |

**Design highlights:**
- **Lazy import**: LangChain is never imported at module load time; `ImportError` with `pip install` hint raised only at first instantiation if absent.
- **Dynamic subclassing**: builds a real `BaseTool` / `BaseCallbackHandler` subclass inside `__new__` — compatible with LangChain Pydantic v1 and v2.
- **Zero new mandatory deps**: core `acp-client` remains stdlib-only.
- **Graceful errors**: `_run` / `_arun` return descriptive error strings (never raise) so the LLM can observe and retry.

See [sdk/python/README-sdk.md](../sdk/python/README-sdk.md#langchain-integration) for the full API reference.

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

## Go SDK

```go
import "github.com/Kickflip73/agent-communication-protocol/sdk/go/acprelay"

client := acprelay.NewClient("http://localhost:8100")

// Send a message
resp, err := client.Send(ctx, "Hello from Go!", "user")

// Fetch AgentCard
card, err := client.AgentCard(ctx)
fmt.Println(card.Self.Name)
```

---

## Rust SDK (v1.2)

Add to `Cargo.toml`:

```toml
[dependencies]
acp-relay-sdk = "1.2"
```

### Send a message

```rust
use acp_relay_sdk::{RelayClient, MessageRequest};

fn main() -> Result<(), acp_relay_sdk::AcpError> {
    let client = RelayClient::new("http://localhost:8100")?;

    // Simple text message
    let resp = client.send_message(MessageRequest::user("Hello, Agent!"))?;
    println!("task_id: {}", resp.task_id.unwrap_or_default());

    // With idempotency key
    let resp = client.send_message(
        MessageRequest::user("Idempotent message")
            .with_message_id("my-uuid-1234")
    )?;

    // Synchronous request-response (block until complete)
    let resp = client.send_message(
        MessageRequest::user("Summarise this document")
            .sync_timeout(30)
    )?;
    println!("status: {:?}", resp.status);

    Ok(())
}
```

### Fetch AgentCard

```rust
let card = client.agent_card()?;
println!("agent: {:?}", card.self_card.name);
if let Some(peer) = card.peer {
    println!("peer: {:?}", peer.name);
    if let Some(avail) = peer.availability {
        println!("next active: {:?}", avail.next_active_at);
    }
}
```

### Heartbeat agent — live availability update (v1.2)

```rust
use acp_relay_sdk::{RelayClient, AvailabilityPatch};

fn on_cron_wake() -> Result<(), acp_relay_sdk::AcpError> {
    let client = RelayClient::new("http://localhost:8100")?;

    client.patch_availability(AvailabilityPatch {
        last_active_at: Some("2026-03-22T13:00:00Z".into()),
        next_active_at: Some("2026-03-22T14:00:00Z".into()),
        ..Default::default()
    })?;

    // ... do actual work ...

    Ok(())
}
```

### Get session link

```rust
if let Some(link) = client.link()? {
    println!("Share this link: {}", link);
    // → acp://relay.acp.dev/<session_id>
}
```

### Error handling

```rust
use acp_relay_sdk::AcpError;

match client.send_message(MessageRequest::user("hello")) {
    Ok(resp)  => println!("ok: {:?}", resp.task_id),
    Err(AcpError::Relay { code, message, .. }) =>
        eprintln!("relay error {}: {}", code, message),
    Err(AcpError::Http(e)) =>
        eprintln!("connection error: {}", e),
    Err(e) => eprintln!("other: {}", e),
}
```

### Prerequisites

```bash
pip install websockets
python3 acp_relay.py --name MyAgent --port 8000
# Rust SDK connects to HTTP port = WS port + 100 = 8100
```

See `sdk/rust/` for the full source and `sdk/rust/README.md` for more examples.

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

## Extension Mechanism (v1.3)

Extensions allow agents to advertise custom capabilities beyond the core ACP spec — using URI-identified namespaces. They appear in the AgentCard and can be registered at startup or updated at runtime without restarting the relay.

### Declare at startup (CLI)

```bash
# Single extension (required=false by default)
python3 acp_relay.py --name MyAgent \
  --extension https://acp.dev/ext/availability/v1

# With params
python3 acp_relay.py --name MyAgent \
  --extension https://corp.example.com/ext/billing,tier=pro,version=2

# Required extension (peer must understand it)
python3 acp_relay.py --name MyAgent \
  --extension https://example.com/ext/auth,required=true

# Multiple extensions (repeat the flag)
python3 acp_relay.py --name MyAgent \
  --extension https://acp.dev/ext/availability/v1 \
  --extension https://acp.dev/ext/scheduling/v1,required=false
```

The extensions appear in the AgentCard:

```json
{
  "name": "MyAgent",
  "capabilities": { "extensions": true },
  "extensions": [
    {
      "uri": "https://acp.dev/ext/availability/v1",
      "required": false
    },
    {
      "uri": "https://corp.example.com/ext/billing",
      "required": true,
      "params": { "tier": "pro", "version": "2" }
    }
  ]
}
```

### Register at runtime (HTTP)

No restart required — callers can register or unregister extensions while the relay is running.

```bash
# Register (upsert — re-registering the same URI updates, not duplicates)
curl -X POST http://localhost:8100/extensions/register \
  -H "Content-Type: application/json" \
  -d '{
    "uri":      "https://acp.dev/ext/availability/v1",
    "required": false,
    "params":   { "mode": "cron", "interval_seconds": 3600 }
  }'

# Unregister
curl -X POST http://localhost:8100/extensions/unregister \
  -H "Content-Type: application/json" \
  -d '{ "uri": "https://acp.dev/ext/availability/v1" }'

# List current extensions
curl http://localhost:8100/extensions
```

### Extension API reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/extensions` | GET | List all declared extensions |
| `/extensions/register` | POST | Register or update an extension (upsert by URI) |
| `/extensions/unregister` | POST | Remove an extension by URI |

### Register request body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `uri` | string | ✅ | `http(s)://` URI uniquely identifying the extension |
| `required` | boolean | — | Whether peer must understand this extension (default: `false`) |
| `params` | object | — | Extension-specific parameters (arbitrary key-value) |

### Checking peer extensions

```python
# Python: inspect peer's extensions from AgentCard
import requests

card = requests.get("http://localhost:8100/.well-known/acp.json").json()
peer = card.get("peer", {})
exts = peer.get("extensions", [])

for ext in exts:
    if ext["uri"] == "https://acp.dev/ext/availability/v1":
        print("Peer supports availability extension:", ext.get("params"))
    if ext.get("required"):
        print("REQUIRED extension:", ext["uri"])
```

### Design notes

- **URI namespace**: Use your own domain to avoid collisions (e.g. `https://example.com/ext/myfeature/v1`)
- **Opt-in**: Extensions are absent from AgentCard when none are declared
- **Upsert semantics**: Re-registering the same URI replaces the entry
- **Validation**: URI must be `http://` or `https://`; `params` must be a JSON object
- **A2A compatibility**: Mirrors A2A's proposed extension URI format, enabling future cross-protocol discovery

---

## DID Identity (v1.3)

When you start the relay with `--identity`, each agent gets a **stable, persistent DID** — a `did:acp:` identifier that stays the same across sessions (as long as the keypair file is not deleted).

```bash
python3 acp_relay.py --name Alice --identity
# Logs:
#   Ed25519 keypair generated and saved to ~/.acp/identity.json | did=did:acp:AAEC...
```

The DID is included in:
- **AgentCard** (`identity.did` field)
- **Every outbound message** (`identity.did` field alongside the signature)
- **`~/.acp/identity.json`** keypair file (persisted to disk)

### DID format

```
did:acp:<base64url-no-padding(32-byte-Ed25519-pubkey)>
```

Example:
```
did:acp:AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8
```

This is a **key-based DID**: the identifier _is_ the public key. No registration, no DNS, no registry needed — fully P2P-native.

### AgentCard identity block

```json
{
  "identity": {
    "scheme":     "ed25519",
    "public_key": "AAECAwQF...",
    "did":        "did:acp:AAECAwQF..."
  },
  "capabilities": {
    "did_identity": true
  },
  "endpoints": {
    "agent_card":   "/.well-known/acp.json",
    "did_document": "/.well-known/did.json"
  }
}
```

### W3C DID Document endpoint

```bash
curl http://localhost:8100/.well-known/did.json
```

Returns a W3C-compatible DID Document:

```json
{
  "@context": [
    "https://www.w3.org/ns/did/v1",
    "https://w3id.org/security/suites/ed25519-2020/v1"
  ],
  "id": "did:acp:AAECAwQF...",
  "verificationMethod": [{
    "id":                "did:acp:AAECAwQF...#key-1",
    "type":              "Ed25519VerificationKey2020",
    "controller":        "did:acp:AAECAwQF...",
    "publicKeyMultibase": "zAAECAwQF..."
  }],
  "authentication":  ["did:acp:AAECAwQF...#key-1"],
  "assertionMethod": ["did:acp:AAECAwQF...#key-1"],
  "service": [{
    "id":              "did:acp:AAECAwQF...#acp",
    "type":            "ACPRelay",
    "serviceEndpoint": "acp://relay.acp.dev/<session-id>"
  }]
}
```

Returns **404** if `--identity` is not enabled.

### Verifying a peer's DID

```python
import requests, base64, json

# Fetch peer's AgentCard
card = requests.get("http://peer-host:8100/.well-known/acp.json").json()
peer_did = card["self"]["identity"]["did"]
peer_pubkey_b64 = card["self"]["identity"]["public_key"]

# Derive expected DID from public key
pub_raw = base64.urlsafe_b64decode(peer_pubkey_b64 + "==")
expected_did = "did:acp:" + base64.urlsafe_b64encode(pub_raw).rstrip(b"=").decode()

assert peer_did == expected_did, "DID mismatch — possible spoofing"
print(f"Peer verified: {peer_did}")
```

### Checking inbound message DID

```python
# Inbound message from ACP relay WebSocket
msg = json.loads(ws.recv())
if "identity" in msg:
    sender_did = msg["identity"].get("did")
    print(f"Message from: {sender_did}")
    # Cross-check: DID must match public_key
    pub_raw = base64.urlsafe_b64decode(msg["identity"]["public_key"] + "==")
    expected = "did:acp:" + base64.urlsafe_b64encode(pub_raw).rstrip(b"=").decode()
    assert sender_did == expected, "DID/pubkey mismatch"
```

### Design notes

- **Persistent identity**: The keypair (and thus the DID) persists in `~/.acp/identity.json` across relay restarts. To rotate identity, delete that file.
- **Backward compatible**: Agents without `--identity` have `identity: null` and `did_identity: false`. Existing integrations are unaffected.
- **Combination with HMAC**: `--identity` and `--hmac-secret` can be used simultaneously — HMAC covers transport-level authentication, Ed25519/DID covers message-level identity.
- **Cross-protocol**: The `did:acp:` URI format uses the same `did:<method>:<identifier>` structure as W3C DID Core, making it readable to any W3C-compatible DID resolver (though resolution would require understanding the `acp` method).

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
