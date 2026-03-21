# ACP CLI Reference — v1.2

`acp_relay.py` is both the reference implementation and the command-line interface.
This document covers every flag, common usage patterns, and environment variables.

---

## Synopsis

```
python3 acp_relay.py [OPTIONS]
```

---

## Flags

### Meta (v0.9)

| Flag | Default | Description |
|------|---------|-------------|
| `--version` | — | Print `acp_relay.py <version>` and exit |
| `--verbose` / `-v` | `false` | Enable DEBUG-level logging. Default is INFO. |
| `--config <FILE>` | *(none)* | Load defaults from a JSON or YAML config file. CLI flags always override file values. See [Config Files](#config-files) below. |

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

### Security — HMAC Signing (v0.7 / v1.1)

| Flag | Default | Description |
|------|---------|-------------|
| `--secret <key>` | *(none)* | Enable HMAC-SHA256 message signing. Both peers must use the same key. Messages with wrong or missing signatures log a warning but are **not dropped** (warn-only). No extra packages required. |
| `--hmac-window <seconds>` | `300` | **(v1.1)** Replay-window for HMAC-signed messages. Inbound messages whose `ts` field is outside `±SECONDS` of server clock are **dropped** (hard reject). Only active when `--secret` is set. Set `0` to disable. Recommended: 60–300 s. |

### Security — Ed25519 Identity (v0.8)

| Flag | Default | Description |
|------|---------|-------------|
| `--identity [path]` | *(flag absent = disabled)* | Enable Ed25519 self-sovereign identity. If no path given, uses `~/.acp/identity.json` (auto-generated on first run, chmod 0600). Requires `pip install cryptography`. |

### Discovery — mDNS (v0.7)

| Flag | Default | Description |
|------|---------|-------------|
| `--advertise-mdns` | `false` | Broadcast presence on LAN via UDP multicast (`224.0.0.251:5354`). Enables `GET /discover` endpoint. No external library required. |

### Availability Metadata — Heartbeat/Cron Support (v1.2)

Opt-in `availability` block in the AgentCard for heartbeat- or cron-based agents
that wake on a schedule rather than running continuously.
Inspired by the gap identified in A2A protocol (issue #1667).

| Flag | Default | Description |
|------|---------|-------------|
| `--availability-mode MODE` | *(absent = no block)* | Agent availability mode: `persistent` \| `heartbeat` \| `cron` \| `manual`. When set, adds an `availability` object to the AgentCard. Use `persistent` to explicitly declare always-on. |
| `--heartbeat-interval SECONDS` | *(none)* | Wake interval in seconds. Sets `interval_seconds` and `task_latency_max_seconds` in the availability block. Only meaningful with `--availability-mode heartbeat\|cron`. |
| `--next-active-at ISO8601` | *(none)* | ISO-8601 UTC timestamp of next scheduled wake (e.g. `2026-03-22T09:00:00Z`). Callers can use this to set retry timers. |

`last_active_at` is **auto-stamped** to the relay's startup time — no manual flag needed.

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
⚠️  HMAC sig mismatch on msg_xxx — message accepted but flagged
```
The message is still delivered (warn-only). Sig mismatch does not drop the message;
this preserves graceful interop for agents that may not implement signing.

### HMAC signing with replay-window (v1.1) — high-security deployment

```bash
# Tight 60-second replay window: replay attacks blocked immediately
python3 acp_relay.py --name "AgentA" --secret "shared-team-key-2026" --hmac-window 60
python3 acp_relay.py --name "AgentB" --join "acp://..." --secret "shared-team-key-2026" --hmac-window 60
```

Messages with a `ts` field outside ±`HMAC_WINDOW` seconds are **hard-rejected and dropped**:
```
⚠️  HMAC replay-window reject on msg_xxx: ts outside replay-window (450s > 300s)
```
The default window is 300 s (5 min), suitable for most Agent-to-Agent use.
For high-security environments, use 60–120 s. Requires synchronized clocks (NTP).

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

### Heartbeat agent — cron/scheduled deployment (v1.2)

Agents that wake on a schedule (e.g. every hour via cron) can advertise
their scheduling metadata so callers know when to expect a response.

```bash
# Cron agent: wakes every hour, next wake at 08:00 UTC
python3 acp_relay.py \
  --name "HourlyAgent" \
  --availability-mode cron \
  --heartbeat-interval 3600 \
  --next-active-at "2026-03-22T08:00:00Z"
```

The AgentCard will include:
```json
{
  "capabilities": { "availability": true },
  "availability": {
    "mode": "cron",
    "interval_seconds": 3600,
    "task_latency_max_seconds": 3600,
    "next_active_at": "2026-03-22T08:00:00Z",
    "last_active_at": "2026-03-22T07:00:00Z"
  }
}
```

Callers can read `next_active_at` to set retry timers, and use
`task_latency_max_seconds` to bound their timeout expectations.
This is the first Agent communication protocol to support scheduling metadata natively.

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
INFO  🕐 HMAC replay-window: ±300s
```

When `--secret` + `--hmac-window 60` is set:
```
INFO  🔐 HMAC signing enabled (--secret configured)
INFO  🕐 HMAC replay-window: ±60s
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

---

## Config Files

All CLI flags (except `--version`) can be set in a JSON or YAML config file
and loaded with `--config <path>`. **CLI flags always take precedence** over
file values.

### Supported keys

Keys use the same names as CLI long flags (hyphens, not underscores):

| Key | Type | Example |
|-----|------|---------|
| `name` | string | `"MyAgent"` |
| `port` | int | `8000` |
| `join` | string | `"acp://1.2.3.4:7801/tok_xxx"` |
| `relay` | bool | `true` |
| `relay-url` | string | `"https://my-relay.example.com"` |
| `skills` | string (CSV) | `"summarize,translate"` |
| `inbox` | string | `"/var/log/acp/messages.jsonl"` |
| `max-msg-size` | int | `2097152` |
| `secret` | string | `"shared-key"` |
| `hmac-window` | int | `120` |
| `advertise-mdns` | bool | `true` |
| `identity` | string | `"~/.acp/identity.json"` |
| `availability-mode` | string | `"heartbeat"` |
| `heartbeat-interval` | int | `3600` |
| `next-active-at` | string | `"2026-03-22T09:00:00Z"` |
| `verbose` | bool | `true` |

### JSON example (`relay/examples/config.json`)

```json
{
  "name": "MyAgent",
  "port": 7801,
  "skills": "summarize,translate,search",
  "verbose": false
}
```

### YAML example (`relay/examples/config-secure.yaml`)

```yaml
# HMAC + Ed25519 + LAN discovery
name: SecureAgent
skills: summarize
secret: replace-with-your-shared-secret
advertise-mdns: true
identity: ~/.acp/identity.json
verbose: false
```

> **YAML note**: The built-in YAML parser supports only JSON-compatible flat
> key-value pairs (no nested objects, no multi-line strings). For complex YAML,
> use JSON format instead.

### Precedence order

```
CLI flags  >  --config file  >  hardcoded defaults
```

---

## Compatibility

| ACP Version | Python | Required packages | Optional packages |
|-------------|--------|-------------------|-------------------|
| v1.2 (current) | 3.9+ | `websockets` | `cryptography` (Ed25519) |
| v1.1 | 3.9+ | `websockets` | `cryptography` (Ed25519) |
| v1.0 | 3.9+ | `websockets` | `cryptography` (Ed25519) |
| v0.8 | 3.9+ | `websockets` | `cryptography` (Ed25519) |
| v0.7 | 3.9+ | `websockets` | — |
| v0.5–v0.6 | 3.9+ | `websockets` | — |

Test any version against the compat suite:
```bash
ACP_BASE_URL=http://localhost:7901 python3 tests/compat/run.py
```
