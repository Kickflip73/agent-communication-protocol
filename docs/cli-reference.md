# ACP CLI Reference — v0.8

`acp_relay.py` is both the reference implementation and the command-line interface.
This document covers every flag, common usage patterns, and environment variables.

---

## Synopsis

```
python3 acp_relay.py [OPTIONS]
```

---

## Flags

### Core

| Flag | Default | Description |
|------|---------|-------------|
| `--name <str>` | `ACP-Agent` | Human-readable agent name, shown in AgentCard and peer lists |
| `--port <int>` | `7801` | WebSocket listen port. HTTP API auto-binds to `port + 100` (default: `7901`) |
| `--join <link>` | *(none)* | Connect to an existing peer immediately on startup. Accepts `acp://` or `acp+wss://` links |
| `--skills <csv>` | *(none)* | Comma-separated list of skill ids to advertise in AgentCard (e.g. `summarize,translate`) |
| `--inbox <path>` | `/tmp/acp_inbox_<name>.jsonl` | Path to JSONL message persistence file |
| `--max-msg-size <bytes>` | `1048576` | Maximum inbound message size in bytes (1 MiB). Larger messages get `ERR_MSG_TOO_LARGE`. |

### Network

| Flag | Default | Description |
|------|---------|-------------|
| `--relay` | `false` | Use public HTTP relay instead of direct P2P. Useful behind firewalls / K8s NAT. Produces `acp+wss://` link instead of `acp://` |
| `--relay-url <url>` | `https://black-silence-11c4.yuranliu888.workers.dev` | Override the relay endpoint. Use this to self-host with `relay/acp_worker.js` |

### Security — HMAC Signing (v0.7)

| Flag | Default | Description |
|------|---------|-------------|
| `--secret <key>` | *(none)* | Enable HMAC-SHA256 message signing. Both peers must use the same key. Messages with wrong or missing signatures log a warning but are **not dropped** (warn-only). No extra packages required. |

### Security — Ed25519 Identity (v0.8)

| Flag | Default | Description |
|------|---------|-------------|
| `--identity [path]` | *(flag absent = disabled)* | Enable Ed25519 self-sovereign identity. If no path given, uses `~/.acp/identity.json` (auto-generated on first run, chmod 0600). Requires `pip install cryptography`. |

### Discovery — mDNS (v0.7)

| Flag | Default | Description |
|------|---------|-------------|
| `--advertise-mdns` | `false` | Broadcast presence on LAN via UDP multicast (`224.0.0.251:5354`). Enables `GET /discover` endpoint. No external library required. |

---

## Port Layout

| Purpose | Port | Notes |
|---------|------|-------|
| WebSocket (P2P) | `--port` (default 7801) | Used for agent-to-agent WebSocket connections |
| HTTP API | `--port + 100` (default 7901) | All REST endpoints (`/message:send`, `/stream`, etc.) |

---

## Usage Patterns

### Minimal — single peer, P2P

```bash
# Agent A — host
pip install websockets
python3 acp_relay.py --name "AgentA"
# → Your link: acp://1.2.3.4:7801/tok_xxxxx
# Send this link to Agent B

# Agent B — guest
python3 acp_relay.py --name "AgentB" --join "acp://1.2.3.4:7801/tok_xxxxx"
```

### Custom port

```bash
python3 acp_relay.py --name "AgentA" --port 9000
# WebSocket: 9000   HTTP API: 9100
```

### Behind a firewall — relay fallback

```bash
python3 acp_relay.py --name "AgentA" --relay
# → Your link: acp+wss://black-silence-11c4.yuranliu888.workers.dev/acp/tok_xxxxx

python3 acp_relay.py --name "AgentB" --join "acp+wss://..."
```

### Self-hosted relay

```bash
# Deploy relay/acp_worker.js to Cloudflare Workers, then:
python3 acp_relay.py --name "AgentA" --relay --relay-url "https://my-relay.example.com"
```

### HMAC signing — closed deployment

```bash
# Both agents must use the same --secret
python3 acp_relay.py --name "AgentA" --secret "shared-team-key-2026"
python3 acp_relay.py --name "AgentB" --join "acp://..." --secret "shared-team-key-2026"
```

Messages with a wrong or absent `sig` field will log:
```
⚠️  HMAC verification failed for message msg_xxx
```
The message is still delivered (warn-only). To enforce strict rejection, set
`capabilities.hmac_strict: true` in a future version.

### Ed25519 identity — open federation

```bash
# Install optional dep
pip install cryptography

# First run — auto-generates ~/.acp/identity.json
python3 acp_relay.py --name "AgentA" --identity

# Subsequent runs — loads existing keypair
python3 acp_relay.py --name "AgentA" --identity

# Custom keypair location
python3 acp_relay.py --name "AgentA" --identity /secrets/acp-identity.json
```

The AgentCard will include an `identity` block:
```json
{
  "capabilities": { "identity": "ed25519" },
  "identity": {
    "scheme": "ed25519",
    "public_key": "<base64url>"
  }
}
```

### Full feature set

```bash
pip install websockets cryptography
python3 acp_relay.py \
  --name "FullAgent" \
  --port 8000 \
  --skills "summarize,translate,search" \
  --secret "shared-key" \
  --identity \
  --advertise-mdns \
  --inbox /var/log/acp/messages.jsonl
```

### LAN multi-agent mesh

```bash
# All agents on the same LAN
python3 acp_relay.py --name "Agent1" --advertise-mdns
python3 acp_relay.py --name "Agent2" --advertise-mdns
python3 acp_relay.py --name "Agent3" --advertise-mdns

# Discover peers from any agent
curl http://localhost:7901/discover
# → {"peers": [{"name": "Agent1", "link": "acp://..."}, ...]}
```

### Advertise specific skills

```bash
python3 acp_relay.py --name "Summarizer" --skills "summarize,bullet-points,tldr"

# Peer can query available skills
curl -X POST http://localhost:7901/skills/query \
  -H "Content-Type: application/json" \
  -d '{"query": "summarize", "limit": 3}'
```

---

## Output

On startup, `acp_relay.py` prints:

```
INFO  🔗 Your link: acp://1.2.3.4:7801/tok_ba366fcab78d4d61
INFO  🌐 HTTP API:  http://0.0.0.0:7901
INFO  📬 Inbox:     /tmp/acp_inbox_AgentA.jsonl
INFO  ⏳ Waiting for peer...
```

When a peer connects:
```
INFO  ✅ Peer connected: AgentB (acp://2.3.4.5:7801/tok_xyz)
```

When `--advertise-mdns` is set:
```
INFO  📡 mDNS advertising active (224.0.0.251:5354)
```

When `--secret` is set:
```
INFO  🔐 HMAC signing enabled (--secret configured)
```

When `--identity` is set:
```
INFO  🔑 Ed25519 identity loaded: <pubkey-prefix>...
```

---

## Quick API Reference

Once running, the HTTP API is available at `http://localhost:<port+100>`:

```bash
# Send a message
curl -X POST http://localhost:7901/message:send \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello"}'

# Stream events (SSE)
curl http://localhost:7901/stream

# AgentCard
curl http://localhost:7901/.well-known/acp.json

# List peers
curl http://localhost:7901/peers

# List tasks
curl http://localhost:7901/tasks

# LAN discovery (requires --advertise-mdns)
curl http://localhost:7901/discover
```

Full API reference: [`spec/core-v0.8.md §4`](../spec/core-v0.8.md).

---

## Compatibility

| ACP Version | Python | Required packages | Optional packages |
|-------------|--------|-------------------|-------------------|
| v0.8 (current) | 3.9+ | `websockets` | `cryptography` (Ed25519) |
| v0.7 | 3.9+ | `websockets` | — |
| v0.5–v0.6 | 3.9+ | `websockets` | — |

Test any version against the compat suite:
```bash
ACP_BASE_URL=http://localhost:7901 python3 tests/compat/run.py
```
