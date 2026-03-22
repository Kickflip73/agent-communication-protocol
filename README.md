<div align="center">

<h1>ACP — Agent Communication Protocol</h1>

<p>
  <strong>A zero-server, zero-code-change P2P protocol for direct Agent-to-Agent communication.</strong><br>
  Two steps for humans. Everything else is automatic.
</p>

<p>
  <a href="https://github.com/Kickflip73/agent-communication-protocol/releases">
    <img src="https://img.shields.io/badge/version-v1.2.0-blue?style=flat-square" alt="Version">
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/license-Apache_2.0-green?style=flat-square" alt="License">
  </a>
  <img src="https://img.shields.io/badge/python-3.9%2B-blue?style=flat-square" alt="Python">
  <img src="https://img.shields.io/badge/node-18%2B-brightgreen?style=flat-square" alt="Node">
  <img src="https://img.shields.io/badge/required_dep-websockets_only-orange?style=flat-square" alt="Required Dependency">
  <a href="https://github.com/Kickflip73/agent-communication-protocol/issues">
    <img src="https://img.shields.io/github/issues/Kickflip73/agent-communication-protocol?style=flat-square" alt="Issues">
  </a>
</p>

<p>
  <a href="README.md">English</a> ·
  <a href="docs/README.zh-CN.md">简体中文</a>
</p>

</div>

---

## Overview

**ACP** is a lightweight, open protocol that enables any two AI agents — regardless of framework, vendor, or runtime — to establish a direct, serverless P2P communication channel.

Unlike enterprise-grade solutions (Google A2A, IBM ACP) that require server infrastructure and SDK integration, ACP is designed for **speed and simplicity**: a human acts only as a messenger, passing a Skill URL to Agent A and the resulting `acp://` link to Agent B. The agents handle everything else automatically.

```
Human Step 1 ──► Send Skill URL to Agent A  ──► Agent A returns acp:// link
Human Step 2 ──► Send acp:// link to Agent B ──► Agents connect directly
```

No central relay. No code changes. No configuration.

---

## Table of Contents

- [Why ACP](#why-acp)
- [Quick Start](#quick-start)
- [Dependencies](#dependencies)
- [Features](#features)
- [API Reference](#api-reference)
- [SDKs](#sdks)
- [Compatibility Test Suite](#compatibility-test-suite)
- [Roadmap](#roadmap)
- [Protocol Comparison](#protocol-comparison)
- [Repository Structure](#repository-structure)
- [Contributing](#contributing)
- [License](#license)

---

## Why ACP

Existing multi-agent communication solutions impose significant operational overhead:

| Challenge | Traditional Approach | ACP |
|-----------|---------------------|-----|
| Infrastructure | Requires a relay server or message broker | **No server required** — pure P2P |
| Integration | Modify agent code, import SDK | **Zero code changes** — Skill-driven |
| Setup | Register, configure, deploy | **One link** — instant connection |
| Portability | Framework-locked | **Framework-agnostic** — any agent, any language |
| Dependencies | Heavy SDK with transitive deps | **One required dep** (`websockets`) |

**Design philosophy:** The `acp://` link *is* the connection. No registry, no discovery service, no broker — just a URI that contains the full address of the other agent.

---

## Quick Start

### Step 1 — Install

```bash
pip install websockets
```

### Step 2 — Download

```bash
curl -sO https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/relay/acp_relay.py
```

### Step 3 — Connect two agents

**Agent A (host):**
```bash
python3 acp_relay.py --name "AgentA"
# Output: Your link: acp://1.2.3.4:7801/tok_xxxxx
# Send this link to Agent B
```

**Agent B (guest):**
```bash
python3 acp_relay.py --name "AgentB" --join "acp://1.2.3.4:7801/tok_xxxxx"
# Both sides: connected ✅
```

### Step 4 — Send & receive

```bash
# Send a message
curl -X POST http://localhost:7901/message:send \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello from AgentA"}'

# Stream incoming messages (SSE)
curl http://localhost:7901/stream

# Check AgentCard
curl http://localhost:7901/.well-known/acp.json
```

### Restricted network? Use relay fallback

```bash
python3 acp_relay.py --name "AgentA" --relay
# Output: acp+wss://black-silence-11c4.yuranliu888.workers.dev/acp/tok_xxxxx
```

> `acp://` = P2P (default). `acp+wss://` = relay fallback for firewalled/K8s environments.

---

## Dependencies

ACP is designed to have **minimal mandatory dependencies** and **truly optional extras**.
Unlike frameworks where importing any module silently pulls in unrelated dependencies,
ACP's optional features are isolated and gracefully degraded without installation.

| Package | Required? | Purpose | Install |
|---------|-----------|---------|---------|
| `websockets` | ✅ **Required** | P2P WebSocket transport | `pip install websockets` |
| `cryptography` | ⚙️ Optional | Ed25519 identity signing (v0.8) | `pip install cryptography` |

> **Zero implicit deps.** If `cryptography` is not installed, `--identity` logs a warning
> and disables identity — the rest of ACP runs normally. There are no other hidden dependencies.

**Node.js SDK** (zero dependencies — uses built-in `fetch` + `EventSource`):
```bash
# No npm install needed — relay_client.js has no external deps
```

---

## Features

### Core (v0.1–v0.5)
- P2P WebSocket transport with NAT traversal
- AgentCard capability exchange (`.well-known/acp.json`)
- Task lifecycle: `submitted` → `working` → `completed` / `failed` / `input_required`
- SSE streaming endpoint (`/stream`)
- Synchronous request/reply (`sync=true`)
- Relay fallback for restricted networks (Cloudflare Worker)
- Message parts: `text` / `file` / `data`
- Server sequence numbers (`server_seq`) for ordering

### v0.6 — Peer Registry & Error Codes
- Multi-session peer registry (`/peers`, `/peer/{id}/send`)
- Standardized error codes (`ERR_NOT_CONNECTED`, `ERR_MSG_TOO_LARGE`, `ERR_NOT_FOUND`, `ERR_INVALID_REQUEST`, `ERR_TIMEOUT`, `ERR_INTERNAL`)
- QuerySkill API (`/skills/query`)

### v0.7 — Trust & Discovery
- **HMAC-SHA256 message signing** (`--secret <key>`) — closed-deployment integrity
- **mDNS LAN peer discovery** (`--advertise-mdns`) — LAN autodiscovery, no zeroconf library
- **Context ID** — multi-turn conversation grouping across messages

### v0.8 — Ecosystem & Identity
- **Ed25519 optional identity** (`--identity`) — self-sovereign keypair, zero PKI
  - Auto-generates keypair to `~/.acp/identity.json` (chmod 600) on first run
  - Every outbound message signed with Ed25519; inbound sigs verified (warn-only)
  - HMAC and Ed25519 can be active simultaneously
- **Node.js SDK** (`sdk/node/`) — zero external dependencies, TypeScript types, 19 tests
- **Compatibility test suite** (`tests/compat/`) — black-box spec compliance runner, parameterized by `ACP_BASE_URL`

### v0.9 — Quality & Distribution
- **Strict role validation** — `role` field required on `/message:send`; missing or invalid → `400 ERR_INVALID_REQUEST`
- **`pip install acp-relay`** — `pyproject.toml`, `acp-relay` CLI entry-point, optional `[identity]` / `[dev]` extras
- **`npm install acp-relay-client`** — ESM + CJS + TypeScript types, zero external dependencies
- **CLI flags**: `--version`, `--verbose`, `--config <FILE>` (JSON/YAML, stdlib-only)
- **63 unit tests** (`tests/unit/`), **7 compat test suites** (`tests/compat/`)

### v1.0 — Production Stable 🎉
- **`spec/core-v1.0.md`** — authoritative 1.0 specification with API stability annotations
  - `[stable]` 13 endpoints · `[experimental]` 1 endpoint (`/discover`)
  - §13: v1.0 compatibility guarantees (4 MUST-level requirements)
- **Security audit** — HMAC-SHA256 + Ed25519 formally audited (`docs/security.md`)
- **Go SDK** (`sdk/go/`) — stdlib-only, Go 1.21+, zero external deps, 24 tests
- **End-to-end integration tests** (`tests/integration/`) — 30 tests against live relay subprocess
- **CHANGELOG** — full version history v0.1.0 → v1.0.0

### v1.1 — Security Hardening
- **HMAC replay-window** (`--hmac-window <seconds>`, default 300 s) — messages outside the window are hard-rejected; prevents replay attacks
- **`failed_message_id`** — all `/message:send` error responses now echo back the client-supplied `message_id` for request tracing
- **Security audit: 9/9 PASS, 0 PARTIAL** (`docs/security.md`)

### v1.2 — Heartbeat Agent Support + Docker 🐳
- **AgentCard `availability` block** — first Agent communication protocol with native scheduling metadata
  ```json
  "availability": { "mode": "cron", "interval_seconds": 3600,
                    "next_active_at": "...", "last_active_at": "..." }
  ```
- **`PATCH /.well-known/acp.json`** — live availability update; heartbeat agents stamp wake times without restarting
- **Official Docker image** — `Dockerfile` + `docker-compose.yml` included; `EXTRAS=full` for Ed25519 support
- **92 unit tests** — all passing

---

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/.well-known/acp.json` | GET | AgentCard (capabilities, identity, endpoints) |
| `/message:send` | POST | Send message to peer (supports `sync`, `parts`, `task_id`, `context_id`) |
| `/stream` | GET | SSE stream of incoming messages and events |
| `/tasks` | GET | List all tasks |
| `/tasks/create` | POST | Create a new task |
| `/tasks/{id}` | GET | Get task details |
| `/tasks/{id}/update` | POST | Update task status |
| `/tasks/{id}/continue` | POST | Send follow-up for `input_required` tasks |
| `/tasks/{id}:cancel` | POST | Cancel a task |
| `/peers` | GET | List connected peers |
| `/peer/{id}` | GET | Get peer info |
| `/peer/{id}/send` | POST | Send message to specific peer |
| `/peers/connect` | POST | Connect to a new peer via `acp://` link |
| `/skills/query` | POST | Query this agent's available skills |
| `/discover` | GET | Discover LAN peers via mDNS (requires `--advertise-mdns`) |
| `/status` | GET | Agent status (connections, message counts, uptime) |

### POST /message:send

```json
{
  "text": "Hello",           // shorthand for parts=[{type:text, content:...}]
  "parts": [...],            // or use explicit Part objects
  "sync": true,              // block until peer replies (default: false)
  "timeout": 30,             // seconds (default: 30, only with sync:true)
  "task_id": "task_abc",     // associate message with a task
  "context_id": "ctx_xyz",   // group messages into a multi-turn context
  "create_task": true,       // auto-create a task for this message
  "message_id": "msg_custom" // optional — auto-generated if omitted
}
```

### Error Response Format

All errors return a consistent envelope:

```json
{
  "ok": false,
  "error_code": "ERR_NOT_CONNECTED",
  "error": "No P2P connection",
  "failed_message_id": "msg_abc123"  // optional, for ERR_TIMEOUT / ERR_MSG_TOO_LARGE
}
```

See [`spec/error-codes.md`](spec/error-codes.md) for full reference.

---

## SDKs

### Python SDK (`sdk/python/`)

```python
from sdk.python.acp_sdk.relay_client import RelayClient, ACPError

client = RelayClient("http://localhost:7901")
client.send("Hello from Python!")
msg = client.recv(timeout=10)
print(msg["parts"][0]["content"])
```

### Node.js SDK (`sdk/node/`)

Zero external dependencies (built-in `fetch` + `EventSource`):

```javascript
import { RelayClient } from './sdk/node/src/relay_client.js';

const client = new RelayClient('http://localhost:7901');
await client.send('Hello from Node!');
const msg = await client.recv({ timeout: 10000 });
console.log(msg.parts[0].content);
```

TypeScript types included (`src/index.d.ts`).

### Go SDK (`sdk/go/`)

Zero external dependencies (Go 1.21+, stdlib `net/http` only):

```go
import "github.com/Kickflip73/agent-communication-protocol/sdk/go/acprelay"

client := acprelay.New("http://localhost:7901")

// Send a message
resp, err := client.Send(ctx, acprelay.SendRequest{Role: "user", Text: "Hello from Go!"})

// SSE streaming
events, _ := client.Stream(ctx, acprelay.StreamOptions{Timeout: 30 * time.Second})
for ev := range events {
    fmt.Printf("[%s] %s\n", ev.Type, ev.Data)
}
```

See [`sdk/go/README.md`](sdk/go/README.md) for full API reference.

---

## Testing

### Compatibility Test Suite

Any ACP implementation can be validated against the spec:

```bash
# Run against the reference implementation
ACP_BASE_URL=http://localhost:7901 python3 tests/compat/run.py

# Run against any other implementation
ACP_BASE_URL=http://other-agent:8080 python3 tests/compat/run.py
```

Tests cover: AgentCard schema, `/message:send`, SSE streaming, task lifecycle, peer registry, error codes, HMAC signing. See [`tests/compat/README.md`](tests/compat/README.md).

### Integration Test Suite

End-to-end tests that spin up a real `acp_relay.py` subprocess:

```bash
pytest tests/integration/ -v
# 30 tests — zero external deps beyond pytest
```

Covers: `/status`, `/card`, `/peers`, `/tasks`, `/message:send`, `/recv`, `/skills/query`, `/link`, `/stream`, `/tasks/{id}:cancel`.

---

## Optional Features

### HMAC Message Signing (v0.7)

For closed deployments where both peers share a secret:

```bash
# Both agents must use the same --secret
python3 acp_relay.py --name "AgentA" --secret "my-shared-key"
python3 acp_relay.py --name "AgentB" --join "acp://..." --secret "my-shared-key"
```

Requires: no additional packages (uses stdlib `hmac`).

### Ed25519 Identity (v0.8)

For open federation where peers need cryptographic attribution:

```bash
# First run: auto-generates ~/.acp/identity.json
python3 acp_relay.py --name "AgentA" --identity

# Subsequent runs: loads existing keypair
python3 acp_relay.py --name "AgentA" --identity

# Custom keypair path
python3 acp_relay.py --name "AgentA" --identity /path/to/id.json
```

Requires: `pip install cryptography`

See [`spec/identity-v0.8.md`](spec/identity-v0.8.md) for full spec.

### mDNS LAN Discovery (v0.7)

```bash
python3 acp_relay.py --name "AgentA" --advertise-mdns
# Peers on the same LAN appear at GET /discover
```

Requires: no additional packages (raw UDP multicast).

---

## Roadmap

| Version | Status | Highlights |
|---------|--------|-----------|
| **v0.1** | ✅ Done | P2P WebSocket, AgentCard, basic send/recv |
| **v0.2** | ✅ Done | Auto-reconnect, JSONL persistence, SSE streaming |
| **v0.3** | ✅ Done | Task lifecycle, multi-session, relay fallback |
| **v0.4** | ✅ Done | Multimodal parts (text/file/data), Cloudflare Worker relay |
| **v0.5** | ✅ Done | QuerySkill API, server_seq ordering, message idempotency |
| **v0.6** | ✅ Done | Peer registry, standardized error codes, minimal agent spec |
| **v0.7** | ✅ Done | HMAC signing, mDNS LAN discovery, context_id |
| **v0.8** | ✅ Done | Ed25519 identity, Node.js SDK, compat test suite |
| **v0.9** | ✅ Done | Consolidated spec, server-side validation, CHANGELOG |
| **v1.0** | ✅ Done | Production stable, security audit, Go SDK, integration tests |
| **v1.1** | ✅ Done | HMAC replay-window, `failed_message_id`, 9/9 security PASS |
| **v1.2** | ✅ Done | AgentCard scheduling metadata, PATCH live-update, Docker image |
| **v1.3** | 🔮 Planned | Rust SDK stub, DID identity (`did:acp:`), Extension mechanism |

See [`acp-research/ROADMAP.md`](acp-research/ROADMAP.md) for detailed planning.

---

## Protocol Comparison

| Dimension | MCP (Anthropic) | A2A (Google) | IBM ACP | **ACP (this project)** |
|-----------|----------------|-------------|---------|------------------------|
| **Scope** | Agent ↔ Tool | Agent ↔ Agent (enterprise) | Agent ↔ Agent (REST) | Agent ↔ Agent (P2P) |
| **Transport** | stdio / HTTP+SSE | HTTP+SSE / JSON-RPC | REST HTTP | WebSocket (direct P2P) |
| **Server required** | — | ✅ Yes | ✅ Yes | ❌ **No** |
| **Code changes required** | ✅ Yes | ✅ Yes | ✅ Yes | ❌ **No** |
| **Required dependencies** | Many | Many (incl. SQLAlchemy) | Many | **`websockets` only** |
| **Task lifecycle** | — | ✅ Yes | ✅ Yes | ✅ Yes |
| **Streaming** | ✅ SSE | ✅ SSE | — | ✅ SSE |
| **Identity / signing** | — | OAuth 2.0 (mandatory) | — | HMAC or Ed25519 (optional) |
| **LAN discovery** | — | — | — | ✅ mDNS (optional) |
| **Scheduling metadata** | — | — | — | ✅ `availability` block (v1.2) |
| **Live availability update** | — | — | — | ✅ `PATCH /.well-known/acp.json` (v1.2) |
| **Docker image** | — | — | — | ✅ Official (v1.2) |
| **Node.js SDK** | ✅ | ✅ | — | ✅ (zero deps) |
| **Compat test suite** | — | ✅ | — | ✅ |
| **Target audience** | Enterprise / teams | Enterprise | Enterprise | **Personal / small teams** |

> ACP's position: MCP standardizes Agent↔Tool. ACP standardizes Agent↔Agent. P2P, lightweight, open, zero infra.
> ACP v1.2 is the **first Agent communication protocol** with native heartbeat/cron scheduling metadata (A2A issue #1667, 2026-03-21).

---

## Repository Structure

```
agent-communication-protocol/
├── relay/
│   ├── acp_relay.py          # Core daemon — single file, one required dep (websockets)
│   └── SKILL.md              # Agent instruction manifest — send this URL to any agent
├── spec/
│   ├── core-v0.1.md          # Core protocol spec (v0.1, English)
│   ├── core-v0.1.zh.md       # Core protocol spec (v0.1, Chinese)
│   ├── core-v0.5.md          # Core protocol spec (v0.5)
│   ├── error-codes.md        # Standard error codes (v0.6)
│   ├── transports.md         # Transport bindings + HMAC (v0.7)
│   ├── transports.zh.md      # Transport bindings (Chinese)
│   ├── identity-v0.8.md      # Ed25519 identity extension (v0.8)
│   ├── v0.6-minimal-agent.md # Minimal agent implementation guide
│   └── v0.8-planning.md      # v0.8 planning document
├── sdk/
│   ├── python/               # Python RelayClient SDK
│   └── node/                 # Node.js RelayClient SDK (zero deps, TS types)
├── tests/
│   └── compat/               # Black-box ACP spec compliance test suite
├── acp-research/
│   ├── ROADMAP.md            # Detailed version roadmap
│   └── reports/              # Competitive intelligence reports (A2A, ANP)
├── docs/
│   └── README.zh-CN.md       # Chinese documentation
├── CONTRIBUTING.md
└── LICENSE                   # Apache 2.0
```

### Docker (v1.2)

```bash
# Build
docker build -t acp-relay .                          # base (websockets only)
docker build --build-arg EXTRAS=full -t acp-relay:full .  # + Ed25519

# Run
docker run --rm -p 8000:8000 -p 8100:8100 acp-relay --name MyAgent

# Cron agent with scheduling metadata
docker run --rm -p 8000:8000 -p 8100:8100 acp-relay \
  --name HourlyAgent --availability-mode cron --heartbeat-interval 3600

# Local two-agent test (Alice + Bob)
docker-compose up
```

The image includes a built-in HEALTHCHECK on `http://localhost:8100/.well-known/acp.json`.

---

## Contributing

Contributions welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting a PR.

- **Bug reports & feature requests** → [GitHub Issues](https://github.com/Kickflip73/agent-communication-protocol/issues)
- **Protocol design discussions** → [GitHub Discussions](https://github.com/Kickflip73/agent-communication-protocol/discussions)
- **Security vulnerabilities** → Please do not file a public issue; contact maintainers directly.

---

## License

ACP is released under the [Apache License 2.0](LICENSE).

---

<div align="center">
<sub>Built with ❤️ for the agent ecosystem — MCP standardizes Agent↔Tool, ACP standardizes Agent↔Agent.</sub>
</div>
