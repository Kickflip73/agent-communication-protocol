# ACP — Agent Communication Protocol

> **A lightweight, transport-agnostic, open standard for Multi-Agent Systems communication.**

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Status: Draft v0.1](https://img.shields.io/badge/Status-Draft%20v0.1-yellow.svg)]()
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)]()

---

## Why ACP?

Today's multi-agent systems (MAS) are **fragmented**:

| Framework | Agent↔Agent Communication | Standardized? |
|-----------|--------------------------|---------------|
| LangGraph | In-process Python calls | ❌ Proprietary |
| AutoGen | HTTP + custom schema | ❌ Proprietary |
| CrewAI | Direct method calls | ❌ Proprietary |
| Google A2A | REST/gRPC (Google-led) | ⚠️ Vendor-driven |
| MCP (Anthropic) | Tool calls only, no Agent↔Agent | ⚠️ Different scope |

**ACP fills the gap**: a vendor-neutral, community-owned protocol for Agent-to-Agent communication — like HTTP for the web, but for autonomous agents.

---

## Core Design Principles

1. **Transport-agnostic** — works over HTTP, WebSocket, MQTT, gRPC, message queues
2. **Minimal & composable** — base spec is tiny; capabilities extend it
3. **Async-first** — agents operate asynchronously; ACP models this natively
4. **Identity & trust** — every agent has a verifiable identity (DID-compatible)
5. **Observable** — built-in tracing, correlation IDs, audit trails
6. **Human-in-the-loop ready** — escalation and approval flows are first-class

---

## Quick Example

```json
// Agent A → Agent B: delegate a task
{
  "acp": "0.1",
  "id": "msg_7f3a9b2c",
  "type": "task.delegate",
  "from": "did:acp:agent-a",
  "to":   "did:acp:agent-b",
  "ts":   "2026-03-18T10:00:00Z",
  "correlation_id": "session_abc123",
  "body": {
    "task": "Summarize the Q1 sales report",
    "input": { "document_url": "https://..." },
    "constraints": {
      "max_tokens": 500,
      "deadline": "2026-03-18T10:05:00Z"
    }
  }
}

// Agent B → Agent A: task result
{
  "acp": "0.1",
  "id": "msg_9d1e4f7a",
  "type": "task.result",
  "from": "did:acp:agent-b",
  "to":   "did:acp:agent-a",
  "ts":   "2026-03-18T10:00:43Z",
  "correlation_id": "session_abc123",
  "reply_to": "msg_7f3a9b2c",
  "body": {
    "status": "success",
    "output": { "summary": "Q1 revenue grew 23% YoY..." }
  }
}
```

---

## Specification

- [Core Spec v0.1](spec/core-v0.1.md)
- [Message Types Reference](spec/message-types.md)
- [Identity & Trust](spec/identity.md)
- [Capability Discovery](spec/discovery.md)
- [Transport Bindings](spec/transports.md)
- [Error Codes](spec/errors.md)

## SDKs

- [Python SDK](sdk/python/) — `pip install acp-sdk`
- [TypeScript SDK](sdk/typescript/) — `npm install @acp-protocol/sdk`

## Examples

- [Orchestrator + Workers](examples/orchestrator-workers/)
- [Peer-to-Peer Agents](examples/peer-to-peer/)
- [Human-in-the-Loop](examples/hitl/)
- [Event-Driven Pipeline](examples/event-pipeline/)

---

## Roadmap

- [x] v0.1 — Core message envelope, task delegation, result reporting
- [ ] v0.2 — Capability discovery, agent registry
- [ ] v0.3 — Streaming responses, long-running tasks
- [ ] v0.4 — Security: authentication, authorization, encryption
- [ ] v1.0 — Stable spec, RFC submission

---

## Contributing

ACP is community-driven. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache 2.0 — free for commercial and open source use.
