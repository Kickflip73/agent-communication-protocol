<div align="center">

<h1>ACP — Agent Communication Protocol</h1>

<p>
  <strong>A zero-server, zero-code-change P2P protocol for direct Agent-to-Agent communication.</strong><br>
  Two steps for humans. Everything else is automatic.
</p>

<p>
  <a href="https://github.com/Kickflip73/agent-communication-protocol/releases">
    <img src="https://img.shields.io/badge/version-v0.2-blue?style=flat-square" alt="Version">
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/license-Apache_2.0-green?style=flat-square" alt="License">
  </a>
  <img src="https://img.shields.io/badge/python-3.9%2B-blue?style=flat-square" alt="Python">
  <img src="https://img.shields.io/badge/dependency-websockets_only-orange?style=flat-square" alt="Dependency">
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
- [How It Works](#how-it-works)
- [Quick Start](#quick-start)
- [API Reference](#api-reference)
- [What's New in v0.2](#whats-new-in-v02)
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

**Design philosophy:** The `acp://` link *is* the connection. No registry, no discovery service, no broker — just a URI that contains the full address of the other agent.

---

## How It Works

```
┌────────────────────────────────────────────────────────────────────┐
│  Human actions (2 steps only)                                      │
│                                                                    │
│  1. Send Skill URL ──► Agent A                                     │
│  2. Send acp:// link ──► Agent B                                   │
└────────────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┴───────────────────┐
          ▼                                       ▼
┌──────────────────┐      WebSocket          ┌──────────────────┐
│    Agent A       │◄═══════════════════════►│    Agent B       │
│                  │   direct, no middleman  │                  │
│ acp_relay.py     │                         │ acp_relay.py     │
│ WS  :7801        │                         │ WS  :7820        │
│ HTTP:7901        │                         │ HTTP:7920        │
└────────┬─────────┘                         └────────┬─────────┘
         │                                            │
    POST /send                                   POST /send
    GET  /recv                                   GET  /recv
    GET  /card  ◄── AgentCard exchange ──►       GET  /card
```

**Link format:** `acp://<host>:<port>/<token>`
- `host` — Initiator's public or LAN IP (auto-detected at startup)
- `port` — WebSocket listen port (default: `7801`)
- `token` — Single-use random token, prevents accidental cross-connections

---

## Quick Start

Humans do exactly **two things**. Agents handle the rest.

### Step 1 — Send the Skill URL to Agent A

```
https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/relay/SKILL.md
```

The agent reads the Skill, installs its single dependency, starts the P2P service, and replies with a link:

```
✅ ACP P2P service started.
Your link: acp://1.2.3.4:7801/tok_abc123def456
Please forward this link to Agent B.
```

### Step 2 — Send the link to Agent B

```
acp://1.2.3.4:7801/tok_abc123def456
```

Agent B reads the same Skill URL, detects the `acp://` link, connects directly to Agent A, and confirms:

```
✅ P2P connection established (no intermediary server).
Connected to: Agent-A  |  Skills: summarize, code-review
Send messages via: POST http://localhost:7920/send
```

That's it. The two agents are now communicating directly.

> **For agents:** Full execution instructions are in the Skill manifest at the URL above.
> Agents should read that file first — it covers initiator flow, receiver flow, all API endpoints, and expected reply formats.

---

## API Reference

> Default ports: Initiator HTTP `7901` (WS port `7801`). Receiver HTTP `7920` (WS port `7820`).
> Rule: HTTP port = WS port + 100.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/send` | Send a message to the connected peer (any JSON body) |
| `GET`  | `/recv` | Consume queued incoming messages. Supports `?limit=N` |
| `GET`  | `/status` | Connection state, statistics, and version info |
| `GET`  | `/link` | Retrieve this agent's `acp://` connection link |
| `GET`  | `/card` | View AgentCards for both this agent and its peer |
| `GET`  | `/history` | Full persisted message history (local JSONL). Supports `?limit=N` |
| `GET`  | `/stream` | SSE endpoint — real-time push of incoming messages |

### Message Envelope

All messages use the following envelope format. Fields `id`, `ts`, and `from` are auto-populated if omitted.

```json
{
  "id":      "msg_abc123def456",
  "ts":      "2026-03-18T12:00:00Z",
  "from":    "Agent-A",
  "type":    "task.delegate",
  "content": "..."
}
```

### CLI Options

| Flag | Default | Description |
|------|---------|-------------|
| `--name` | `ACP-Agent` | Agent display name (included in AgentCard) |
| `--join` | — | `acp://` link to connect to (omit to run as initiator) |
| `--port` | `7801` | WebSocket listen port. HTTP port = this + 100 |
| `--skills` | — | Comma-separated capability list, e.g. `summarize,translate` |
| `--inbox` | `/tmp/acp_inbox_<name>.jsonl` | Message persistence file path |

---

## What's New in v0.2

This release incorporates findings from a competitive analysis of [Google A2A v1.0](https://a2a-protocol.org), [IBM BeeAgent ACP](https://github.com/i-am-bee/ACP), and [ANP](https://github.com/agent-network-protocol/AgentNetworkProtocol). See [`research/2026-03-18-competitive-analysis.md`](research/2026-03-18-competitive-analysis.md) for the full report.

**New features:**

- **AgentCard capability exchange** — Inspired by A2A. Both agents automatically broadcast their capabilities upon connection. Query via `GET /card`.
- **Automatic reconnection** — The receiver (guest) mode now retries on disconnect using exponential backoff (up to 10 attempts, capped at 60s).
- **Message persistence** — All received messages are appended to a local JSONL file. Full history is accessible via `GET /history`.
- **SSE streaming endpoint** — `GET /stream` delivers real-time message events, compatible with A2A-style clients.

---

## Roadmap

| Version | Planned Features |
|---------|-----------------|
| **v0.3** | Task lifecycle (`submitted` / `working` / `completed`), concurrent multi-session support, capability query API |
| **v0.4** | Multimodal message parts (text / file references / structured data), NAT traversal exploration |
| **v1.0** | Decentralized identity via W3C DIDs, agent discovery network |

See the full roadmap in [`research/RESEARCH-PROTOCOL.md`](research/RESEARCH-PROTOCOL.md).

---

## Protocol Comparison

ACP occupies a distinct niche in the agent protocol ecosystem:

| Dimension | MCP (Anthropic) | A2A (Google) | ACP (IBM) | **ACP (this project)** |
|-----------|----------------|-------------|-----------|------------------------|
| **Scope** | Agent ↔ Tool | Agent ↔ Agent (enterprise) | Agent ↔ Agent (REST) | Agent ↔ Agent (P2P) |
| **Transport** | stdio / HTTP+SSE | HTTP+SSE / JSON-RPC / gRPC | REST HTTP | WebSocket (direct) |
| **Requires server** | — | Yes | Yes | **No** |
| **Requires code changes** | Yes | Yes | Yes | **No** |
| **Capability declaration** | Yes | Yes (AgentCard) | — | Yes (AgentCard) |
| **Auto-reconnect** | — | — | — | Yes |
| **Message persistence** | — | — | — | Yes |
| **Single dependency** | — | — | — | Yes (`websockets`) |

> MCP, A2A, and IBM ACP each serve well-defined purposes. ACP targets the **quick, serverless P2P** scenario where minimal friction is the priority.

---

## Repository Structure

```
agent-communication-protocol/
├── relay/
│   ├── acp_relay.py          # Core daemon — P2P relay process (~400 lines, single dependency)
│   └── SKILL.md              # Agent instruction manifest (send this URL to any agent)
├── spec/
│   ├── core-v0.1.md          # Core protocol specification (English)
│   ├── core-v0.1.zh.md       # Core protocol specification (Chinese)
│   ├── transports.md         # Transport bindings (stdio / HTTP+SSE / TCP)
│   ├── transports.zh.md      # Transport bindings (Chinese)
│   └── identity.md           # Identity and authentication specification
├── docs/
│   └── README.zh-CN.md       # Chinese documentation
├── examples/
│   └── quickstart/           # Runnable quickstart examples
├── research/
│   ├── 2026-03-18-competitive-analysis.md   # Competitive analysis report
│   └── RESEARCH-PROTOCOL.md  # Ongoing research cadence and roadmap
├── CONTRIBUTING.md           # Contribution guide (English)
├── CONTRIBUTING.zh.md        # Contribution guide (Chinese)
└── LICENSE                   # Apache 2.0
```

---

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting a pull request.

- **Bug reports & feature requests** → [GitHub Issues](https://github.com/Kickflip73/agent-communication-protocol/issues)
- **Protocol design discussions** → [GitHub Discussions](https://github.com/Kickflip73/agent-communication-protocol/discussions)
- **Security vulnerabilities** → Please do not file a public issue; contact the maintainers directly.

---

## License

ACP is released under the [Apache License 2.0](LICENSE).

---

<div align="center">
  <sub>Built with the goal of making Agent-to-Agent communication as simple as sending a link.</sub>
</div>
