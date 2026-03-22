# acp-relay-sdk

[![crates.io](https://img.shields.io/crates/v/acp-relay-sdk)](https://crates.io/crates/acp-relay-sdk)
[![docs.rs](https://img.shields.io/docsrs/acp-relay-sdk)](https://docs.rs/acp-relay-sdk)
[![Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)](../../LICENSE)

Rust SDK for [ACP Relay](https://github.com/Kickflip73/agent-communication-protocol) — the Agent Communication Protocol.

Send and receive messages between agents using the `acp_relay.py` HTTP API.  
Pure blocking HTTP; no async runtime required.

---

## Installation

```toml
[dependencies]
acp-relay-sdk = "1.2"
```

> **No OpenSSL** — uses `rustls-tls` for TLS. Works out-of-the-box on Linux, macOS, and Windows.

---

## Quick start

```rust
use acp_relay_sdk::{RelayClient, MessageRequest};

fn main() -> Result<(), acp_relay_sdk::AcpError> {
    // Connect to a locally running acp_relay.py (HTTP port = WS port + 100)
    let client = RelayClient::new("http://localhost:8100")?;

    // Health check
    assert!(client.ping()?, "relay not reachable");

    // Send a message to the connected peer
    let resp = client.send_message(MessageRequest::user("Hello from Rust!"))?;
    println!("task_id: {:?}", resp.task_id);

    Ok(())
}
```

---

## Usage

### Send a message

```rust
// Simple text message
let resp = client.send_message(MessageRequest::user("Hello!"))?;

// With idempotency key (resend-safe)
let resp = client.send_message(
    MessageRequest::user("Critical update")
        .with_message_id("my-idempotent-uuid-001")
)?;

// Synchronous: block until task completes (timeout = 30s)
let resp = client.send_message(
    MessageRequest::user("Run analysis")
        .sync_timeout(30)
)?;
println!("status: {:?}", resp.status);
```

### Read the AgentCard

```rust
let card_resp = client.agent_card()?;
let self_card = &card_resp.self_card;
println!("Agent: {}", self_card.name.as_deref().unwrap_or("?"));

// Check peer capabilities
if let Some(peer) = &card_resp.peer {
    println!("Peer: {}", peer.name.as_deref().unwrap_or("?"));
    if let Some(avail) = &peer.availability {
        println!("Next active: {:?}", avail.next_active_at);
    }
}
```

### Update availability metadata (v1.2)

Heartbeat/cron agents should call this on every wake to advertise their schedule:

```rust
use acp_relay_sdk::{RelayClient, AvailabilityPatch};

let client = RelayClient::new("http://localhost:8100")?;

client.patch_availability(AvailabilityPatch {
    mode:                    Some("cron".into()),
    last_active_at:          Some("2026-03-22T13:00:00Z".into()),
    next_active_at:          Some("2026-03-22T14:00:00Z".into()),
    task_latency_max_seconds: Some(3600),
    ..Default::default()
})?;
```

### Get relay status

```rust
let status = client.status()?;
println!("Connected: {:?}", status.connected);
println!("Session:   {:?}", status.session_id);
println!("Link:      {:?}", status.link);
```

### Get the session link

Share this with another agent to establish a P2P connection:

```rust
let link = client.link()?;
println!("{}", link.unwrap_or_default());
// → acp://relay.acp.dev/<session-id>
```

---

## Error handling

```rust
use acp_relay_sdk::AcpError;

match client.send_message(MessageRequest::user("hi")) {
    Ok(resp) => println!("ok: {:?}", resp.task_id),
    Err(AcpError::Http(e))            => eprintln!("network error: {e}"),
    Err(AcpError::Relay { code, message, .. }) => {
        eprintln!("relay error [{code}]: {message}")
    }
    Err(e) => eprintln!("other: {e}"),
}
```

---

## API reference

| Method | HTTP | Description |
|--------|------|-------------|
| `send_message(req)` | `POST /message:send` | Send a message to peer |
| `agent_card()` | `GET /.well-known/acp.json` | Fetch AgentCard (self + peer) |
| `patch_availability(patch)` | `PATCH /.well-known/acp.json` | Update availability metadata |
| `status()` | `GET /status` | Relay runtime status |
| `link()` | `GET /link` | Session link (`acp://…`) |
| `ping()` | `GET /.well-known/acp.json` | Reachability check |

---

## Key types

| Type | Description |
|------|-------------|
| `RelayClient` | Main client; wraps a `reqwest::blocking::Client` |
| `MessageRequest` | Request body for `send_message`; builders: `user()`, `agent()` |
| `MessageResponse` | Response from `send_message` |
| `AgentCard` | Single card (self or peer) from AgentCard response |
| `AgentCardResponse` | Wrapper with `self_card` + optional `peer` |
| `Availability` | `availability` block in AgentCard |
| `AvailabilityPatch` | Partial patch for `patch_availability` |
| `RelayStatus` | Relay runtime info |
| `AcpError` | All SDK errors (`Http`, `Relay`, `InvalidUrl`, `Json`) |

---

## Starting the relay

```bash
# Install
pip install websockets

# Start (gets a session link)
python3 acp_relay.py --name RustAgent --http-port 8100

# Then in your Rust app:
let client = RelayClient::new("http://localhost:8100")?;
```

---

## See also

- [Python SDK](../python/)
- [Go SDK](../go/)
- [Node.js SDK](../node/)
- [ACP Protocol Spec](../../spec/)
- [Integration Guide](../../docs/integration-guide.md)

---

## License

Apache-2.0 © ACP Contributors
