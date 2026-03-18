# ACP — Agent Communication Protocol

<div align="center">

**[English](#quick-start) · [中文](#快速开始)**

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Status: Draft v0.1](https://img.shields.io/badge/Status-Draft%20v0.1-yellow.svg)]()
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)]()

</div>

---

<!-- ============================================================ -->
<!--  ENGLISH                                                      -->
<!-- ============================================================ -->

> **Let any two agents talk directly — no server, no broker, no registration.**
>
> ACP-P2P gives every agent an address (`acp://` URI). Share the address, send a message. That's it.

## Quick Start

**Step 1 — Install**

```bash
pip install aiohttp
curl -o acp_p2p.py https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/p2p/sdk/acp_p2p.py
```

**Step 2 — Add 4 lines to your existing agent**

```python
from acp_p2p import P2PAgent

agent = P2PAgent("my-agent", port=7700)

@agent.on_task
async def handle(task: str, input_data: dict) -> dict:
    # ↓ your existing agent logic goes here — unchanged
    result = your_existing_function(task, input_data)
    return {"output": result}

agent.start()
# Prints: 🔗 ACP URI: acp://192.168.1.42:7700/my-agent
# Share this URI with any other agent that needs to reach you
```

**Step 3 — Send a message to another agent**

```python
# If you know another agent's URI, send directly — no setup needed
result = await agent.send(
    to="acp://192.168.1.50:7701/other-agent",
    task="Summarize this",
    input={"text": "..."},
)
print(result["body"]["output"])
```

**Done.** Your agent is now reachable by any other ACP-compatible agent.

---

## I already have an agent — how do I integrate?

Pick your scenario:

### My agent is a Python function / class

```python
# Before: standalone function
def my_agent_logic(query: str) -> str:
    return llm.run(query)

# After: wrap with P2PAgent (3 lines added)
from acp_p2p import P2PAgent
agent = P2PAgent("my-agent", port=7700)

@agent.on_task
async def handle(task, input_data):
    return {"result": my_agent_logic(input_data.get("query", task))}

agent.start()
```

### My agent already has an HTTP server

```python
# Just add the /acp/v1/receive endpoint to your existing server
# Example with FastAPI:
from fastapi import FastAPI, Request
app = FastAPI()

@app.post("/acp/v1/receive")
async def receive(request: Request):
    msg = await request.json()
    task    = msg["body"]["task"]
    input_  = msg["body"]["input"]
    result  = your_existing_handler(task, input_)
    return {
        "acp": "0.1", "type": "task.result",
        "from": "acp://yourhost:8000/my-agent",
        "to": msg["from"],
        "body": {"status": "success", "output": result}
    }

# Your agent's ACP URI is: acp://yourhost:8000/my-agent
```

### My agent is LangChain / LangGraph

```python
from langchain.agents import AgentExecutor
from acp_p2p import P2PAgent

executor: AgentExecutor = build_your_agent()   # your existing code

acp = P2PAgent("langchain-agent", port=7700)

@acp.on_task
async def handle(task: str, input_data: dict) -> dict:
    result = await executor.ainvoke({"input": task, **input_data})
    return {"output": result["output"]}

acp.start()
```

### My agent is AutoGen

```python
import autogen
from acp_p2p import P2PAgent

assistant = autogen.AssistantAgent("assistant", llm_config={...})
user_proxy = autogen.UserProxyAgent("user_proxy", ...)

acp = P2PAgent("autogen-agent", port=7700)

@acp.on_task
async def handle(task: str, input_data: dict) -> dict:
    user_proxy.initiate_chat(assistant, message=task)
    last_msg = user_proxy.last_message(assistant)
    return {"output": last_msg["content"]}

acp.start()
```

---

## Group Chat (3+ agents, zero servers)

```python
# Agent A — create a group and invite others
group = alice.create_group("my-team")
await alice.invite(group, "acp://host-b:7701/bob")
await alice.invite(group, "acp://host-c:7702/charlie")

# Send to everyone
await alice.group_send(group, {"text": "Hello team!"})

# Agent B / C — register a handler and that's it
@bob.on_group_message
async def on_msg(group_id, from_uri, body):
    print(f"{from_uri}: {body['text']}")
    await bob.group_send(bob.get_group(group_id), {"text": "Got it!"})

# Dynamic join / leave
dave_group = await dave.join_group(group.to_invite_uri())
await charlie.leave_group(group)   # notifies all members automatically
```

---

## Why ACP?

Today's multi-agent systems are **fragmented**:

| Framework | How agents communicate | Standard? |
|-----------|----------------------|-----------|
| LangGraph | In-process Python calls | ❌ |
| AutoGen | HTTP + custom schema | ❌ |
| CrewAI | Direct method calls | ❌ |
| Google A2A | REST/gRPC (Google-led) | ⚠️ Vendor |
| MCP | Agent→Tool only, not Agent↔Agent | ⚠️ Different scope |

ACP fills the gap: **any agent, any framework, any language** — one URI, direct communication.

---

## Design Principles

1. **Zero third-party** — P2P mode needs no server, no broker, no registration
2. **URI is the address** — `acp://host:port/name` contains everything needed to connect
3. **Explicit lifecycle** — `connect()` / `disconnect()`, `join_group()` / `leave_group()`
4. **Transport-agnostic** — HTTP today; WebSocket, gRPC, MQTT tomorrow
5. **Framework-neutral** — wrap any existing agent in 4 lines

---

## Documentation

| Document | Description |
|----------|-------------|
| [Quick Start (this page)](#quick-start) | Add ACP to your existing agent |
| [P2P Integration Guide](p2p/skill/SKILL.md) | Full API reference + examples |
| [P2P Protocol Spec](p2p/spec/acp-p2p-v0.1.md) | Protocol specification |
| [Core Spec](spec/core-v0.1.md) | Message format, types, error codes |
| [Contributing](CONTRIBUTING.md) | How to contribute |

## Examples

| Example | What it shows |
|---------|--------------|
| [demo_lifecycle.py](p2p/examples/demo_lifecycle.py) | connect/disconnect, direct send, join/leave group |
| [demo_group.py](p2p/examples/demo_group.py) | 3-agent group chat, zero servers |

## Roadmap

- [x] v0.1 — Core message format, task delegation
- [x] v0.2 — P2P mode, group chat
- [x] v0.3 — Connection lifecycle, join/leave group
- [ ] v0.4 — Ed25519 signatures, encrypted transport
- [ ] v0.5 — Capability discovery, agent registry
- [ ] v1.0 — Stable spec, RFC

## License

Apache 2.0

---

<!-- ============================================================ -->
<!--  中文                                                         -->
<!-- ============================================================ -->

## 快速开始

> **让任意两个 Agent 直接通信——不需要服务器，不需要中间件，不需要注册。**
>
> ACP-P2P 给每个 Agent 一个地址（`acp://` URI）。把地址发给对方，就能直接发消息。

**第一步——安装**

```bash
pip install aiohttp
curl -o acp_p2p.py https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/p2p/sdk/acp_p2p.py
```

**第二步——在你现有的 Agent 里加 4 行代码**

```python
from acp_p2p import P2PAgent

agent = P2PAgent("my-agent", port=7700)

@agent.on_task
async def handle(task: str, input_data: dict) -> dict:
    # ↓ 你现有的 Agent 逻辑放在这里，不需要改动
    result = your_existing_function(task, input_data)
    return {"output": result}

agent.start()
# 输出: 🔗 ACP URI: acp://192.168.1.42:7700/my-agent
# 把这个 URI 发给任何需要联系你的 Agent
```

**第三步——向另一个 Agent 发消息**

```python
# 知道对方的 URI，直接发——不需要任何额外配置
result = await agent.send(
    to="acp://192.168.1.50:7701/other-agent",
    task="帮我总结这段文字",
    input={"text": "..."},
)
print(result["body"]["output"])
```

**完成。** 你的 Agent 现在可以被任何支持 ACP 的 Agent 访问了。

---

## 我已有一个 Agent——怎么接入？

选择你的场景：

### 我的 Agent 是一个 Python 函数 / 类

```python
# 接入前：独立函数
def my_agent_logic(query: str) -> str:
    return llm.run(query)

# 接入后：用 P2PAgent 包裹（只新增 3 行）
from acp_p2p import P2PAgent
agent = P2PAgent("my-agent", port=7700)

@agent.on_task
async def handle(task, input_data):
    return {"result": my_agent_logic(input_data.get("query", task))}

agent.start()
```

### 我的 Agent 已有 HTTP 服务

```python
# 在你现有的服务器上增加一个端点即可
# 以 FastAPI 为例：
from fastapi import FastAPI, Request
app = FastAPI()

@app.post("/acp/v1/receive")
async def receive(request: Request):
    msg     = await request.json()
    task    = msg["body"]["task"]
    result  = your_existing_handler(task, msg["body"]["input"])
    return {
        "acp": "0.1", "type": "task.result",
        "from": "acp://yourhost:8000/my-agent",
        "to": msg["from"],
        "body": {"status": "success", "output": result}
    }

# 你的 ACP URI 就是: acp://yourhost:8000/my-agent
```

### 我的 Agent 是 LangChain / LangGraph

```python
from langchain.agents import AgentExecutor
from acp_p2p import P2PAgent

executor: AgentExecutor = build_your_agent()   # 你已有的代码

acp = P2PAgent("langchain-agent", port=7700)

@acp.on_task
async def handle(task: str, input_data: dict) -> dict:
    result = await executor.ainvoke({"input": task, **input_data})
    return {"output": result["output"]}

acp.start()
```

### 我的 Agent 是 AutoGen

```python
import autogen
from acp_p2p import P2PAgent

assistant  = autogen.AssistantAgent("assistant", llm_config={...})
user_proxy = autogen.UserProxyAgent("user_proxy", ...)

acp = P2PAgent("autogen-agent", port=7700)

@acp.on_task
async def handle(task: str, input_data: dict) -> dict:
    user_proxy.initiate_chat(assistant, message=task)
    last_msg = user_proxy.last_message(assistant)
    return {"output": last_msg["content"]}

acp.start()
```

---

## 群聊（3个以上 Agent，零服务器）

```python
# Agent A——创建群，邀请其他成员
group = alice.create_group("我的团队")
await alice.invite(group, "acp://host-b:7701/bob")
await alice.invite(group, "acp://host-c:7702/charlie")

# 群发消息
await alice.group_send(group, {"text": "大家好！"})

# Agent B / C——注册处理函数，其余不需要改任何东西
@bob.on_group_message
async def on_msg(group_id, from_uri, body):
    print(f"{from_uri}: {body['text']}")
    await bob.group_send(bob.get_group(group_id), {"text": "收到！"})

# 动态加入 / 退出
dave_group = await dave.join_group(group.to_invite_uri())
await charlie.leave_group(group)   # 自动通知所有成员
```

---

## 为什么需要 ACP？

当前多智能体系统**高度碎片化**：

| 框架 | Agent 间通信方式 | 是否标准化 |
|------|----------------|-----------|
| LangGraph | 进程内 Python 调用 | ❌ |
| AutoGen | HTTP + 自定义 Schema | ❌ |
| CrewAI | 直接方法调用 | ❌ |
| Google A2A | REST/gRPC（Google 主导）| ⚠️ 厂商驱动 |
| MCP | 仅 Agent→工具，无 Agent↔Agent | ⚠️ 不同场景 |

ACP 填补了这一空白：**任意 Agent，任意框架，任意语言**——一个 URI，直接通信。

---

## 设计原则

1. **零第三方** — P2P 模式无需服务器、中间件或注册中心
2. **URI 即地址** — `acp://host:port/name` 包含连接所需的全部信息
3. **显式生命周期** — `connect()` / `disconnect()`，`join_group()` / `leave_group()`
4. **传输无关** — 当前 HTTP，未来支持 WebSocket、gRPC、MQTT
5. **框架无关** — 任何现有 Agent 4 行代码接入

---

## 文档导航

| 文档 | 说明 |
|------|------|
| [快速开始（本页）](#快速开始) | 将 ACP 接入你现有的 Agent |
| [P2P 接入指南（中文）](p2p/skill/SKILL.zh.md) | 完整 API 参考 + 使用示例 |
| [P2P 协议规范（中文）](p2p/spec/acp-p2p-v0.1.zh.md) | 协议技术规范 |
| [核心规范（中文）](spec/core-v0.1.zh.md) | 消息格式、类型、错误码 |
| [贡献指南（中文）](CONTRIBUTING.zh.md) | 如何参与贡献 |

## 示例

| 示例 | 演示内容 |
|------|---------|
| [demo_lifecycle.py](p2p/examples/demo_lifecycle.py) | connect/disconnect、直接发送、加入/退出群聊 |
| [demo_group.py](p2p/examples/demo_group.py) | 3个 Agent 群聊，零服务器 |

## 路线图

- [x] v0.1 — 核心消息格式、任务委托
- [x] v0.2 — P2P 模式、群聊
- [x] v0.3 — 连接生命周期、加入/退出群聊
- [ ] v0.4 — Ed25519 签名、加密传输
- [ ] v0.5 — 能力发现、Agent 注册中心
- [ ] v1.0 — 稳定规范，提交 RFC

## 开源协议

Apache 2.0 — 商业与开源项目均可免费使用。
