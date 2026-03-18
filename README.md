# ACP — Agent Communication Protocol

<div align="center">

**[English](#acp--agent-communication-protocol-1) · [中文](#acp--agent-通信协议)**

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Spec: v0.1 Draft](https://img.shields.io/badge/Spec-v0.1%20Draft-yellow.svg)](spec/core-v0.1.md)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

</div>

---

<!-- ================================================================ -->
<!--  ENGLISH                                                          -->
<!-- ================================================================ -->

# ACP — Agent Communication Protocol

> **ACP is to Agent-to-Agent communication what MCP is to Agent-to-Tool communication.**

MCP solved how an agent calls a tool. ACP solves how an agent talks to another agent.

---

## The Problem

Every multi-agent framework invented its own wire format:

| Framework | How agents communicate | Interoperable? |
|-----------|----------------------|----------------|
| LangGraph | In-process Python calls | ❌ Same process only |
| AutoGen | HTTP + ad-hoc JSON | ❌ AutoGen-only |
| CrewAI | Direct method calls | ❌ Same process only |
| Google A2A | REST + Task schema | ⚠️ Google-controlled |
| OpenAI Swarm | In-process only | ❌ Same process only |

**Result:** A LangChain agent cannot talk to an AutoGen agent. A Python agent cannot talk to a TypeScript agent. Multi-agent systems are locked inside their framework.

---

## The Solution

ACP defines a **standard wire protocol** for agent-to-agent communication:

```
┌─────────────────┐     ACP message      ┌─────────────────┐
│  LangChain      │ ──────────────────►  │  AutoGen        │
│  Agent          │                      │  Agent          │
└─────────────────┘  (JSON over stdio,   └─────────────────┘
                       HTTP, or TCP)
```

Any agent that speaks ACP can communicate with any other ACP-compliant agent, regardless of:
- Programming language (Python, TypeScript, Go, Rust, Java, ...)
- Framework (LangChain, AutoGen, CrewAI, raw LLM API, ...)
- Infrastructure (local process, container, remote server, cloud function, ...)

---

## Transport Modes

ACP defines three standard transport bindings:

### 1. stdio (recommended for local/subprocess agents)

```
┌─────────────────────────────────────────────────────┐
│  Parent process                                     │
│                                                     │
│  agent_a ──(stdout)──► agent_b process              │
│           ◄─(stdin)──                               │
└─────────────────────────────────────────────────────┘
```

Each message is a newline-delimited JSON object on stdout/stdin. Zero setup. No ports. Works across languages.

```bash
# Agent B listens on stdin, responds on stdout
echo '{"acp":"0.1","type":"task.delegate","from":"did:acp:local:a",...}' | python agent_b.py
```

### 2. HTTP + SSE (recommended for networked agents)

```
POST /acp/v1/messages          ← send a message
GET  /acp/v1/stream            ← receive messages (Server-Sent Events)
GET  /acp/v1/capabilities      ← discover what this agent can do
```

### 3. Raw TCP (recommended for high-throughput pipelines)

Newline-delimited JSON over a persistent TCP connection. Lowest latency, no HTTP overhead.

---

## The ACP Message

Every ACP message is a JSON object with a standard envelope:

```json
{
  "acp":            "0.1",
  "id":             "msg_7f3a9b2c",
  "type":           "task.delegate",
  "from":           "did:acp:local:orchestrator",
  "to":             "did:acp:local:summarizer",
  "ts":             "2026-03-18T10:00:00Z",
  "correlation_id": "workflow_abc123",
  "body": {
    "task":  "Summarize the attached document",
    "input": { "text": "..." },
    "constraints": { "max_tokens": 500, "deadline": "2026-03-18T10:05:00Z" }
  }
}
```

The **message type** determines the body schema. Core types:

| Category | Types |
|----------|-------|
| Task lifecycle | `task.delegate` `task.accept` `task.reject` `task.result` `task.progress` `task.cancel` |
| Lifecycle | `agent.hello` `agent.bye` `agent.heartbeat` |
| Events | `event.broadcast` `event.subscribe` |
| Coordination | `coord.propose` `coord.vote` |
| Human-in-loop | `hitl.escalate` `hitl.response` |
| System | `error` |

---

## Quick Start

**Install the SDK:**

```bash
pip install acp-sdk           # Python
npm install @acp-protocol/sdk # TypeScript
```

**Build an agent that receives tasks (any framework, 10 lines):**

```python
from acp_sdk import ACPAgent, ACPMessage

class SummarizerAgent(ACPAgent):
    async def handle_task_delegate(self, msg: ACPMessage) -> ACPMessage:
        text = msg.body["input"]["text"]
        summary = your_llm(f"Summarize: {text}")  # your existing logic
        return msg.reply(status="success", output={"summary": summary})

# Start listening on stdio (for subprocess mode) or HTTP
SummarizerAgent(aid="did:acp:local:summarizer").serve()
```

**Send a task to another agent:**

```python
from acp_sdk import ACPClient

async with ACPClient("http://localhost:7700") as client:
    result = await client.delegate(
        to="did:acp:local:summarizer",
        task="Summarize this",
        input={"text": "The quick brown fox..."},
    )
    print(result.body["output"]["summary"])
```

---

## How It Relates to MCP

| | MCP | ACP |
|-|-----|-----|
| **Solves** | Agent ↔ Tool | Agent ↔ Agent |
| **Typical use** | Call a web search / database / API | Delegate a task to a specialized agent |
| **Transport** | stdio, HTTP/SSE | stdio, HTTP/SSE, TCP |
| **Message format** | JSON-RPC 2.0 | ACP envelope (purpose-built) |
| **Capability model** | Tools list | Agent capabilities + schemas |
| **Initiated by** | Always the agent (client) | Either side (async) |

They are **complementary**: an agent uses MCP to call tools, and ACP to talk to other agents.

```
Human ──► Orchestrator Agent
               │  ACP: delegate task
               ▼
          Worker Agent ──► MCP: call web-search tool
               │  ACP: task.result
               ▼
          Orchestrator Agent ──► Human: final answer
```

---

## Specification

| Document | Description |
|----------|-------------|
| [Core Spec v0.1](spec/core-v0.1.md) | Message envelope, types, error codes, versioning |
| [Transport Bindings](spec/transports.md) | stdio, HTTP/SSE, TCP — wire format for each |
| [Identity & Trust](spec/identity.md) | AID format, authentication, signed messages |
| [Capability Discovery](spec/discovery.md) | How agents advertise and discover capabilities |
| [Message Types Reference](spec/message-types.md) | Full schema for each message type |
| [Error Codes](spec/errors.md) | Standard error code registry |

## SDK & Integrations

| | Python | TypeScript |
|-|--------|------------|
| **Core SDK** | [`sdk/python/`](sdk/python/) | [`sdk/typescript/`](sdk/typescript/) |
| **LangChain** | `acp_sdk.integrations.langchain` | — |
| **AutoGen** | `acp_sdk.integrations.autogen` | — |
| **FastAPI middleware** | `acp_sdk.integrations.fastapi` | — |

## Examples

| Example | Transport | What it shows |
|---------|-----------|--------------|
| [quickstart/](examples/quickstart/) | stdio | Hello world: two agents, one task |
| [orchestrator-workers/](examples/orchestrator-workers/) | HTTP | Orchestrator dispatches to parallel workers |
| [cross-framework/](examples/cross-framework/) | HTTP | LangChain agent ↔ AutoGen agent |
| [hitl/](examples/hitl/) | HTTP | Human approves agent decision |

---

## Roadmap

- [x] **v0.1** — Core envelope, task lifecycle, error codes, in-process bus
- [x] **v0.2** — P2P mode, group messaging
- [x] **v0.3** — Connection lifecycle (connect/disconnect/join/leave)
- [ ] **v0.4** — stdio transport, TCP transport; Ed25519 message signing
- [ ] **v0.5** — Capability discovery registry; streaming task results
- [ ] **v1.0** — Stable spec; community RFC process; IANA registration

## Contributing

ACP is community-owned and vendor-neutral. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[Apache 2.0](LICENSE)

---

<!-- ================================================================ -->
<!--  中文                                                             -->
<!-- ================================================================ -->

# ACP — Agent 通信协议

> **ACP 之于 Agent 间通信，如同 MCP 之于 Agent 调用工具。**

MCP 解决了 Agent 如何调用工具的问题。ACP 解决的是 Agent 之间如何互相通信的问题。

---

## 问题所在

每个多智能体框架都发明了自己的通信格式：

| 框架 | 通信方式 | 可互通？|
|------|---------|---------|
| LangGraph | 进程内 Python 调用 | ❌ 仅限同进程 |
| AutoGen | HTTP + 临时 JSON | ❌ 仅限 AutoGen |
| CrewAI | 直接方法调用 | ❌ 仅限同进程 |
| Google A2A | REST + Task Schema | ⚠️ Google 控制 |
| OpenAI Swarm | 仅进程内 | ❌ 仅限同进程 |

**结果**：LangChain 的 Agent 无法与 AutoGen 的 Agent 通信。Python Agent 无法与 TypeScript Agent 对话。多智能体系统被锁死在各自的框架内。

---

## 解决方案

ACP 定义了一套 **标准的 Agent 间通信协议**：

```
┌─────────────────┐     ACP 消息         ┌─────────────────┐
│  LangChain      │ ──────────────────►  │  AutoGen        │
│  Agent          │                      │  Agent          │
└─────────────────┘  (JSON over stdio,   └─────────────────┘
                       HTTP 或 TCP)
```

任何支持 ACP 的 Agent 都能与任何其他 ACP Agent 通信，不受以下因素限制：
- 编程语言（Python、TypeScript、Go、Rust、Java……）
- 框架（LangChain、AutoGen、CrewAI、原生 LLM API……）
- 基础设施（本地进程、容器、远程服务器、云函数……）

---

## 传输模式

ACP 定义三种标准传输绑定：

### 1. stdio（推荐用于本地/子进程 Agent）

```
┌─────────────────────────────────────────────────────┐
│  父进程                                              │
│                                                     │
│  agent_a ──(stdout)──► agent_b 进程                  │
│           ◄─(stdin)──                               │
└─────────────────────────────────────────────────────┘
```

消息是换行符分隔的 JSON 对象，通过 stdout/stdin 传递。零配置，无需端口，跨语言。

```bash
# Agent B 从 stdin 读取消息，向 stdout 输出响应
echo '{"acp":"0.1","type":"task.delegate","from":"did:acp:local:a",...}' | python agent_b.py
```

### 2. HTTP + SSE（推荐用于网络 Agent）

```
POST /acp/v1/messages       ← 发送消息
GET  /acp/v1/stream         ← 接收消息（Server-Sent Events）
GET  /acp/v1/capabilities   ← 查询 Agent 能力
```

### 3. 原始 TCP（推荐用于高吞吐量管道）

持久 TCP 连接上的换行符分隔 JSON。延迟最低，无 HTTP 开销。

---

## ACP 消息格式

每条 ACP 消息都是一个标准信封结构的 JSON 对象：

```json
{
  "acp":            "0.1",
  "id":             "msg_7f3a9b2c",
  "type":           "task.delegate",
  "from":           "did:acp:local:orchestrator",
  "to":             "did:acp:local:summarizer",
  "ts":             "2026-03-18T10:00:00Z",
  "correlation_id": "workflow_abc123",
  "body": {
    "task":  "对附件文档进行摘要",
    "input": { "text": "..." },
    "constraints": { "max_tokens": 500, "deadline": "2026-03-18T10:05:00Z" }
  }
}
```

**消息类型**决定 body 的 schema。核心消息类型：

| 类别 | 类型 |
|------|------|
| 任务生命周期 | `task.delegate` `task.accept` `task.reject` `task.result` `task.progress` `task.cancel` |
| 生命周期 | `agent.hello` `agent.bye` `agent.heartbeat` |
| 事件 | `event.broadcast` `event.subscribe` |
| 协调 | `coord.propose` `coord.vote` |
| 人机协作 | `hitl.escalate` `hitl.response` |
| 系统 | `error` |

---

## 快速开始

**安装 SDK：**

```bash
pip install acp-sdk           # Python
npm install @acp-protocol/sdk # TypeScript
```

**构建一个接收任务的 Agent（任意框架，10 行）：**

```python
from acp_sdk import ACPAgent, ACPMessage

class SummarizerAgent(ACPAgent):
    async def handle_task_delegate(self, msg: ACPMessage) -> ACPMessage:
        text = msg.body["input"]["text"]
        summary = your_llm(f"总结以下内容：{text}")  # 你现有的逻辑
        return msg.reply(status="success", output={"summary": summary})

# 以 stdio 模式启动（子进程模式）或 HTTP 模式
SummarizerAgent(aid="did:acp:local:summarizer").serve()
```

**向另一个 Agent 发送任务：**

```python
from acp_sdk import ACPClient

async with ACPClient("http://localhost:7700") as client:
    result = await client.delegate(
        to="did:acp:local:summarizer",
        task="帮我总结这段文字",
        input={"text": "..."},
    )
    print(result.body["output"]["summary"])
```

---

## 与 MCP 的关系

| | MCP | ACP |
|-|-----|-----|
| **解决** | Agent ↔ 工具 | Agent ↔ Agent |
| **典型用途** | 调用搜索/数据库/API | 把任务委托给专业 Agent |
| **传输** | stdio、HTTP/SSE | stdio、HTTP/SSE、TCP |
| **消息格式** | JSON-RPC 2.0 | ACP 信封（专用设计）|
| **能力模型** | 工具列表 | Agent 能力 + Schema |
| **发起方** | 始终由 Agent（客户端）发起 | 任意一方（异步）|

两者**互补**：Agent 用 MCP 调用工具，用 ACP 与其他 Agent 通信。

```
人类 ──► 编排 Agent
            │  ACP: 委托任务
            ▼
        工作 Agent ──► MCP: 调用网络搜索工具
            │  ACP: task.result
            ▼
        编排 Agent ──► 人类: 最终答案
```

---

## 规范文档

| 文档 | 说明 |
|------|------|
| [核心规范 v0.1（中文）](spec/core-v0.1.zh.md) | 消息信封、类型、错误码、版本控制 |
| [核心规范 v0.1（英文）](spec/core-v0.1.md) | Core spec in English |
| [传输绑定（中文）](spec/transports.zh.md) | stdio、HTTP/SSE、TCP 的具体格式 |
| [身份与信任](spec/identity.md) | AID 格式、认证、消息签名 |
| [能力发现](spec/discovery.md) | Agent 能力广播与查询 |
| [消息类型参考](spec/message-types.md) | 每种消息类型的完整 Schema |
| [错误码](spec/errors.md) | 标准错误码注册表 |

## SDK 与集成

| | Python | TypeScript |
|-|--------|------------|
| **核心 SDK** | [`sdk/python/`](sdk/python/) | [`sdk/typescript/`](sdk/typescript/) |
| **LangChain** | `acp_sdk.integrations.langchain` | — |
| **AutoGen** | `acp_sdk.integrations.autogen` | — |
| **FastAPI 中间件** | `acp_sdk.integrations.fastapi` | — |

## 示例

| 示例 | 传输 | 演示内容 |
|------|------|---------|
| [quickstart/](examples/quickstart/) | stdio | Hello world：两个 Agent，一个任务 |
| [orchestrator-workers/](examples/orchestrator-workers/) | HTTP | 编排器并行分发给多个工作 Agent |
| [cross-framework/](examples/cross-framework/) | HTTP | LangChain Agent ↔ AutoGen Agent |
| [hitl/](examples/hitl/) | HTTP | 人工审批 Agent 决策 |

---

## 路线图

- [x] **v0.1** — 核心信封、任务生命周期、错误码、进程内总线
- [x] **v0.2** — P2P 模式、群组消息
- [x] **v0.3** — 连接生命周期（connect/disconnect/join/leave）
- [ ] **v0.4** — stdio 传输、TCP 传输；Ed25519 消息签名
- [ ] **v0.5** — 能力发现注册中心；流式任务结果
- [ ] **v1.0** — 稳定规范；社区 RFC 流程；IANA 注册

## 参与贡献

ACP 由社区拥有，厂商中立。查看 [CONTRIBUTING.zh.md](CONTRIBUTING.zh.md)。

## 开源协议

[Apache 2.0](LICENSE)
