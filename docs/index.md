# ACP — Agent Communication Protocol

<div align="center" markdown>

**The missing link between AI Agents.**

*Send a URL. Get a link. Two agents talk. That's it.*

[![Version](https://img.shields.io/badge/version-v2.8.0-blue?style=flat-square)](https://github.com/Kickflip73/agent-communication-protocol/releases)
[![License](https://img.shields.io/badge/license-Apache_2.0-green?style=flat-square)](https://github.com/Kickflip73/agent-communication-protocol/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue?style=flat-square)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tested-330%2B_PASS-success?style=flat-square)](https://github.com/Kickflip73/agent-communication-protocol/actions)

</div>

---

> **MCP standardized Agent↔Tool. ACP standardizes Agent↔Agent.**  
> P2P · Zero server required · curl-compatible · works with any LLM framework

## What is ACP?

ACP is a lightweight, open protocol for direct Agent-to-Agent communication. Unlike enterprise solutions that require OAuth, service registries, and devops teams, ACP gives you:

- 🔗 **A shareable link** — paste it to any other agent to connect
- ⚡ **Real-time messaging** — SSE stream, sub-millisecond latency
- 🔒 **True P2P** — Relay only punches holes, never stores messages
- 🛠️ **curl-compatible** — any language, any framework, any LLM

## 60-Second Demo

```bash
# Terminal 1 — Agent A
python3 acp_relay.py --name AgentA
# ✅ Ready. Your link: acp://1.2.3.4:7801/tok_xxxxx

# Terminal 2 — Agent B: connect
curl -X POST http://localhost:7901/peers/connect \
     -d '{"link":"acp://1.2.3.4:7801/tok_xxxxx"}'
# {"ok":true,"peer_id":"peer_001"}

# Agent B: send a message
curl -X POST http://localhost:7901/message:send \
     -d '{"role":"agent","parts":[{"type":"text","content":"Hello AgentA!"}]}'
# {"ok":true,"message_id":"msg_abc123"}

# Agent A: receive via SSE stream
curl http://localhost:7901/stream
# event: acp.message
# data: {"role":"agent","parts":[{"type":"text","content":"Hello AgentA!"}]}
```

## Why ACP?

| | A2A (Enterprise) | ACP (Personal/Team) |
|---|---|---|
| **Deploy** | Ops team required | **Zero server, local Skill** |
| **Connect** | Code + config + registry | **One link, paste & go** |
| **Auth** | OAuth 2.0 full suite | **Token in link, HMAC optional** |
| **Privacy** | Through server | **True P2P, relay stores nothing** |
| **Analogy** | Enterprise ESB | **WhatsApp for Agents** |

## Key Features

=== "P2P Communication"

    Three-level NAT traversal, fully transparent to your application:
    
    ```
    Level 1: Direct WebSocket P2P
        ↓ fails 3×
    Level 2: DCUtR UDP hole punching
        ↓ fails (symmetric NAT ~25%)
    Level 3: Cloudflare Worker relay (100% fallback)
    ```

=== "AgentCard"

    Full capability declaration in one JSON response:
    
    ```bash
    curl http://localhost:7901/.well-known/acp.json
    ```
    ```json
    {
      "name": "AgentA",
      "version": "2.8.0",
      "capabilities": {"streaming": true, "hmac_signing": true},
      "limitations": ["no_file_access"],
      "extensions": [{"uri": "acp:ext:hmac-v1"}]
    }
    ```

=== "Task Tracking"

    Built-in task state machine with SSE events:
    
    ```
    submitted → working → completed
                       → failed
                       → cancelling → canceled
                       → input_required
    ```

=== "Python SDK"

    ```python
    from acp_client import RelayClient
    
    c = RelayClient("http://localhost:7901")
    link = c.status()["link"]
    
    # Connect and send
    peer = c.connect("acp://remote:7801/tok_xxx")
    c.send("Hello!", peer_id=peer)
    
    # Receive
    for msg in c.stream():
        print(msg.parts[0].content)
    ```

## Getting Started

<div class="grid cards" markdown>

-   :material-clock-fast:{ .lg .middle } **Quick Start**

    ---

    Get two agents talking in under 60 seconds.

    [:octicons-arrow-right-24: Quick Start](getting-started/quickstart.md)

-   :material-download:{ .lg .middle } **Installation**

    ---

    Install the relay and Python SDK.

    [:octicons-arrow-right-24: Installation](getting-started/installation.md)

-   :material-school:{ .lg .middle } **Core Concepts**

    ---

    Understand links, peers, tasks, and streams.

    [:octicons-arrow-right-24: Concepts](getting-started/concepts.md)

-   :material-compare:{ .lg .middle } **vs. A2A**

    ---

    How ACP compares to Google's A2A protocol.

    [:octicons-arrow-right-24: Comparison](comparison.md)

</div>

## Version

Current stable: **v2.8.0** — Extension mechanism, `limitations` field, LangChain integration.  
See [What's New](whats-new.md) for recent changes or the full [Roadmap](ROADMAP.md).
