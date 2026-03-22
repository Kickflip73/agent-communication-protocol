# ACP Relay SDK for Rust

Thin blocking HTTP client for [`acp_relay.py`](https://github.com/Kickflip73/agent-communication-protocol).

## Installation

```toml
# Cargo.toml
[dependencies]
acp-relay-sdk = "1.2"
```

## Quick start

```rust
use acp_relay_sdk::{RelayClient, MessageRequest};

fn main() -> Result<(), acp_relay_sdk::AcpError> {
    // Connect to a running acp_relay.py (default HTTP port = WS port + 100)
    let client = RelayClient::new("http://localhost:8100")?;

    // Send a message to the connected peer
    let resp = client.send_message(MessageRequest::user("Hello, Agent!"))?;
    println!("task_id: {}", resp.task_id.unwrap_or_default());

    // Fetch the AgentCard
    let card = client.agent_card()?;
    println!("agent: {:?}", card.self_card.name);

    Ok(())
}
```

## Heartbeat / cron agent — live availability update (v1.2)

```rust
use acp_relay_sdk::{RelayClient, AvailabilityPatch};

fn main() -> Result<(), acp_relay_sdk::AcpError> {
    let client = RelayClient::new("http://localhost:8100")?;

    // On each cron wake: stamp last_active_at and compute next_active_at
    client.patch_availability(AvailabilityPatch {
        last_active_at: Some("2026-03-22T13:00:00Z".into()),
        next_active_at: Some("2026-03-22T14:00:00Z".into()),
        ..Default::default()
    })?;

    println!("Availability updated.");
    Ok(())
}
```

## API

| Method | Maps to | Description |
|--------|---------|-------------|
| `send_message(req)` | `POST /message:send` | Send a message to connected peer |
| `agent_card()` | `GET /.well-known/acp.json` | Fetch AgentCard + peer card |
| `patch_availability(patch)` | `PATCH /.well-known/acp.json` | Live-update scheduling metadata |
| `status()` | `GET /status` | Relay status and stats |
| `link()` | `GET /link` | Session link (share to connect) |
| `ping()` | `GET /.well-known/acp.json` | Health-check |

## Prerequisites

Start an ACP relay before connecting:

```bash
pip install websockets
python3 acp_relay.py --name MyAgent --port 8000
# HTTP API available at http://localhost:8100
```

## License

Apache-2.0
