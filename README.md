# ACP — Agent Communication Protocol

<div align="center">

**[English](#acp--agent-communication-protocol-1) · [中文](#acp--agent-通信协议)**

</div>

---

<!-- ================================================================ -->
<!-- ENGLISH                                                           -->
<!-- ================================================================ -->

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

## ACP-P2P: Decentralized Peer-to-Peer Mode

Beyond the gateway model, ACP includes a **fully decentralized P2P mode** — any two agents communicate directly with zero third-party servers.

```python
from acp_p2p import P2PAgent

# Agent A — start and share URI
alice = P2PAgent("alice", port=7700)
@alice.on_task
async def handle(task, input_data): return {"result": "done"}

async with alice:
    print(alice.uri)  # acp://192.168.1.42:7700/alice  ← share this

# Agent B — connect and send
async with bob:
    session = await bob.connect("acp://192.168.1.42:7700/alice")
    result  = await bob.send(session, "Summarize this", {"text": "..."})
    await bob.disconnect(session)
```

**Group chat (≥3 agents, zero servers):**

```python
group = alice.create_group("team")
await alice.invite(group, str(bob.uri))
await alice.invite(group, str(charlie.uri))
await alice.group_send(group, {"text": "Hello everyone!"})

# Dynamic join / leave
dave_group = await dave.join_group(group.to_invite_uri())
await charlie.leave_group(group)   # notifies all members
```

→ See [P2P Skill Guide](p2p/skill/SKILL.md) | [P2P Spec](p2p/spec/acp-p2p-v0.1.md) | [P2P SDK](p2p/sdk/acp_p2p.py)

---

## Specification

- [Core Spec v0.1](spec/core-v0.1.md)
- [Message Types Reference](spec/message-types.md)
- [Identity & Trust](spec/identity.md)
- [Capability Discovery](spec/discovery.md)
- [Transport Bindings](spec/transports.md)
- [Error Codes](spec/errors.md)

## SDKs

- [Python P2P SDK](p2p/sdk/acp_p2p.py) — single file, copy and use
- [Python Gateway SDK](sdk/python/) — `pip install acp-sdk`
- [TypeScript SDK](sdk/typescript/) — `npm install @acp-protocol/sdk`

## Examples

- [P2P Lifecycle Demo](p2p/examples/demo_lifecycle.py)
- [Group Chat Demo](p2p/examples/demo_group.py)
- [Orchestrator + Workers](examples/orchestrator-workers/)
- [Human-in-the-Loop](examples/hitl/)

---

## Roadmap

- [x] v0.1 — Core message envelope, task delegation, result reporting
- [x] v0.2 — P2P mode: decentralized agent-to-agent, group chat
- [x] v0.3 — Connection lifecycle: connect/disconnect, join/leave group
- [ ] v0.4 — Security: Ed25519 signatures, encrypted transport
- [ ] v0.5 — Capability discovery, agent registry
- [ ] v1.0 — Stable spec, RFC submission

---

## Contributing

ACP is community-driven. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache 2.0 — free for commercial and open source use.

---

<!-- ================================================================ -->
<!-- CHINESE                                                           -->
<!-- ================================================================ -->

# ACP — Agent 通信协议

> **轻量级、传输无关的开放标准，专为多智能体系统（MAS）通信设计。**

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Status: Draft v0.1](https://img.shields.io/badge/状态-草案%20v0.1-yellow.svg)]()
[![PRs Welcome](https://img.shields.io/badge/PR-欢迎贡献-brightgreen.svg)]()

---

## 为什么需要 ACP？

当前的多智能体系统（MAS）**高度碎片化**：

| 框架 | Agent 间通信方式 | 是否标准化 |
|------|----------------|-----------|
| LangGraph | 进程内 Python 调用 | ❌ 私有实现 |
| AutoGen | HTTP + 自定义 Schema | ❌ 私有实现 |
| CrewAI | 直接方法调用 | ❌ 私有实现 |
| Google A2A | REST/gRPC（Google 主导）| ⚠️ 厂商驱动 |
| MCP（Anthropic）| 仅工具调用，无 Agent 间通信 | ⚠️ 不同场景 |

**ACP 填补了这一空白**：一个厂商中立、社区拥有的 Agent 间通信协议——就像 HTTP 之于 Web，ACP 之于自主 Agent。

---

## 核心设计原则

1. **传输无关** — 支持 HTTP、WebSocket、MQTT、gRPC、消息队列等任意传输层
2. **轻量可组合** — 基础规范极简，能力通过扩展叠加
3. **异步优先** — Agent 天然异步运行，ACP 原生建模这一特性
4. **身份与信任** — 每个 Agent 拥有可验证身份（兼容 DID 标准）
5. **可观测性** — 内置链路追踪、关联 ID、审计日志
6. **人机协作就绪** — 升级审批和人工介入流程是一等公民

---

## 快速示例

```json
// Agent A → Agent B：委托任务
{
  "acp": "0.1",
  "id": "msg_7f3a9b2c",
  "type": "task.delegate",
  "from": "did:acp:agent-a",
  "to":   "did:acp:agent-b",
  "ts":   "2026-03-18T10:00:00Z",
  "correlation_id": "session_abc123",
  "body": {
    "task": "总结 Q1 销售报告",
    "input": { "document_url": "https://..." },
    "constraints": {
      "max_tokens": 500,
      "deadline": "2026-03-18T10:05:00Z"
    }
  }
}

// Agent B → Agent A：返回结果
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
    "output": { "summary": "Q1 营收同比增长 23%..." }
  }
}
```

---

## ACP-P2P：去中心化点对点模式

ACP 包含一个**完全去中心化的 P2P 模式**——任意两个 Agent 无需任何第三方服务器即可直接通信。

```python
from acp_p2p import P2PAgent

# Agent A — 启动，打印 URI，等待消息
alice = P2PAgent("alice", port=7700)
@alice.on_task
async def handle(task, input_data): return {"result": "完成"}

async with alice:
    print(alice.uri)  # acp://192.168.1.42:7700/alice ← 把这个发给对方

# Agent B — 连接并发消息
async with bob:
    session = await bob.connect("acp://192.168.1.42:7700/alice")
    result  = await bob.send(session, "总结这段文字", {"text": "..."})
    await bob.disconnect(session)
```

**群聊（≥3 个 Agent，零服务器）：**

```python
group = alice.create_group("team")
await alice.invite(group, str(bob.uri))
await alice.invite(group, str(charlie.uri))
await alice.group_send(group, {"text": "大家好！"})

# 动态加入 / 退出
dave_group = await dave.join_group(group.to_invite_uri())
await charlie.leave_group(group)   # 自动通知所有成员
```

**连接生命周期：**

```
connect()  →  send() × N  →  disconnect()
create_group() / join_group()  →  group_send() × N  →  leave_group()
async with agent  →  ...  →  退出 with 块自动停止服务器
```

→ 查看 [P2P 使用指南（中文）](p2p/skill/SKILL.zh.md) | [P2P 协议规范](p2p/spec/acp-p2p-v0.1.zh.md) | [P2P SDK](p2p/sdk/acp_p2p.py)

---

## 规范文档

- [核心规范 v0.1（中文）](spec/core-v0.1.zh.md)
- [消息类型参考](spec/message-types.md)
- [身份与信任](spec/identity.md)
- [能力发现](spec/discovery.md)
- [传输绑定](spec/transports.md)
- [错误码](spec/errors.md)

## SDK

- [Python P2P SDK](p2p/sdk/acp_p2p.py) — 单文件，复制即用
- [Python Gateway SDK](sdk/python/) — `pip install acp-sdk`
- [TypeScript SDK](sdk/typescript/) — `npm install @acp-protocol/sdk`

## 示例

- [P2P 生命周期 Demo](p2p/examples/demo_lifecycle.py)
- [群聊 Demo](p2p/examples/demo_group.py)
- [编排器 + 工作者](examples/orchestrator-workers/)
- [人机协作流程](examples/hitl/)

---

## 路线图

- [x] v0.1 — 核心消息信封、任务委托、结果上报
- [x] v0.2 — P2P 模式：去中心化 Agent 通信、群聊
- [x] v0.3 — 连接生命周期：connect/disconnect、join/leave group
- [ ] v0.4 — 安全：Ed25519 签名、加密传输
- [ ] v0.5 — 能力发现、Agent 注册中心
- [ ] v1.0 — 稳定规范，提交 RFC

---

## 参与贡献

ACP 由社区驱动。查看 [CONTRIBUTING.zh.md](CONTRIBUTING.zh.md) 了解贡献指南。

## 开源协议

Apache 2.0 — 商业与开源项目均可免费使用。
