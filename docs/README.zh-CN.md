# ACP — Agent 通信协议

<p align="center">
  <img src="https://img.shields.io/badge/版本-v1.3-blue" alt="Version">
  <img src="https://img.shields.io/badge/许可证-Apache_2.0-green" alt="License">
  <img src="https://img.shields.io/badge/依赖-websockets-orange" alt="Dependency">
  <img src="https://img.shields.io/badge/Python-3.9%2B-blue" alt="Python">
  <img src="https://img.shields.io/badge/docker-GHCR-2496ED?logo=docker&logoColor=white" alt="Docker GHCR">
</p>

**ACP（Agent Communication Protocol）是一个零服务器、零代码修改的 P2P Agent 通信协议。** 人只需完成 2 步操作，任意两个 AI Agent 即可建立直接加密通信通道。

---

## 目录

- [为什么选择 ACP](#为什么选择-acp)
- [工作原理](#工作原理)
- [快速上手（2分钟）](#快速上手2分钟)
- [接口文档](#接口文档)
- [v0.6-dev 新特性](#v02-新特性)
- [路线图](#路线图)
- [与同类协议对比](#与同类协议对比)
- [贡献指南](#贡献指南)
- [许可证](#许可证)

---

## 为什么选择 ACP

现有 Agent 通信方案存在三大痛点：

| 问题 | 传统方案 | ACP |
|------|---------|-----|
| 需要中间服务器 | ✗ 必须部署 relay/broker | ✅ 纯 P2P 直连 |
| 需要修改代码 | ✗ 集成 SDK，侵入框架 | ✅ Skill 驱动，零代码变更 |
| 配置繁琐 | ✗ 注册、配置、维护 | ✅ 一条链接，即用即连 |

**核心理念：** 人只是信使——把一个 Skill 地址传给 Agent A，把 Agent A 返回的链接传给 Agent B，剩下的全部自动完成。

---

## 工作原理

```
┌─────────────────────────────────────────────────────────────┐
│  人类操作（仅 2 步）                                         │
│                                                              │
│  Step 1: 把 Skill URL 发给 Agent A                          │
│  Step 2: 把 Agent A 返回的 acp:// 链接发给 Agent B          │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  Agent 自动完成                                              │
│                                                              │
│  Agent A                          Agent B                   │
│  ┌─────────────────┐              ┌─────────────────┐       │
│  │ 1. pip install  │              │ 1. pip install  │       │
│  │ 2. 下载脚本     │  WebSocket   │ 2. 下载脚本     │       │
│  │ 3. 监听端口     │◄────────────►│ 3. 解析链接     │       │
│  │ 4. 返回链接     │   直连，无   │ 4. 直接连接     │       │
│  │                 │  中间服务器  │                 │       │
│  │ HTTP :7901      │              │ HTTP :7920      │       │
│  └─────────────────┘              └─────────────────┘       │
│        ↑                                  ↑                 │
│   POST /send                         POST /send             │
│   GET  /recv                         GET  /recv             │
└─────────────────────────────────────────────────────────────┘

链接格式: acp://<host>:<port>/<token>
```

---

## 快速上手（2分钟）

人只需做 **2 件事**，Agent 负责其余所有操作。

### 第 1 步 — 把 Skill 地址发给 Agent A

```
https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/relay/SKILL.md
```

Agent A 读取 Skill，自动安装依赖、启动 P2P 服务，然后返回一条链接：

```
✅ ACP P2P 通信服务已启动。
你的链接：acp://1.2.3.4:7801/tok_abc123def456
请将此链接转发给 Agent B。
```

### 第 2 步 — 把链接发给 Agent B

```
acp://1.2.3.4:7801/tok_abc123def456
```

Agent B 读取同一份 Skill，检测到 `acp://` 链接，直接连接 Agent A，并确认：

```
✅ P2P 连接成功（无中间服务器）。
已连接至：Agent-A  |  能力：summarize, code-review
发消息接口：POST http://localhost:7920/send
```

完成。两个 Agent 已建立直接通信通道。

> **对 Agent 而言：** 完整执行指令在上方 Skill 地址中。Agent 应先读取该文件——其中包含发起方流程、接收方流程、所有 API 端点及回复格式规范。

---

## 通信模式

ACP v0.6-dev 支持四种通信模式，参考 [Google A2A v1.0](https://a2a-protocol.org) 设计：

### 模式一：同步（请求/响应）

发送消息并**阻塞等待对方回复**（或超时）：

```
POST /send  {"type":"query","content":"...","sync":true,"timeout":30}
            ── 阻塞 ──► 对方调用 POST /reply {"correlation_id":"<id>","content":"..."}
            ◄── 立即返回回复内容
```

### 模式二：异步（Task 生命周期）

创建任务、委托给对方、轮询或推送获取结果：

```
POST /tasks/create  {"payload":{...},"delegate":true}
  → 状态: submitted
    → 对方更新: working
    → 对方更新: completed + artifact
GET  /tasks/<id>    ← 随时轮询状态
DELETE /tasks/<id>  ← 取消任务
```

状态流转：`submitted` → `working` → `completed` | `failed` | `cancelled`

### 模式三：流式（SSE 实时推送）

订阅一次，持续接收所有事件：

```
GET /stream
  ← data: {"event":"peer.connected"}
  ← data: {"event":"message.received","message":{...}}
  ← data: {"event":"task.updated","task_id":"...","status":"working"}
```

### 模式四：Push（Webhook 回调）

注册回调 URL，守护进程自动 POST 所有事件：

```
POST /webhooks/register  {"url":"https://your-host/hook"}
  ← 守护进程在后台将每个事件 POST 到你的 URL
```

---

## 接口文档

> 发起方 HTTP `7901`（WS `7801`）；接收方 HTTP `7920`（WS `7820`）。
> 规则：**HTTP 端口 = WS 端口 + 100**

| 方法 | 路径 | 模式 | 描述 |
|------|------|------|------|
| `POST` | `/send` | 同步/异步 | 发消息。加 `"sync":true` 阻塞等待回复 |
| `POST` | `/reply` | 同步 | 通过 `correlation_id` 回复消息 |
| `GET`  | `/recv` | 异步 | 消费队列消息（`?limit=N`） |
| `GET`  | `/wait/<id>` | 同步 | 阻塞等待关联回复（`?timeout=30`） |
| `POST` | `/tasks/create` | 异步 | 创建任务（`"delegate":true` 发给对方） |
| `GET`  | `/tasks` | 异步 | 列出任务（`?status=working`） |
| `GET`  | `/tasks/<id>` | 异步 | 获取任务状态 + artifacts |
| `POST` | `/tasks/<id>/update` | 异步 | 更新状态 / 添加 artifact |
| `DELETE` | `/tasks/<id>` | 异步 | 取消任务 |
| `GET`  | `/stream` | 流式 | SSE 实时事件流 |
| `POST` | `/webhooks/register` | Push | 注册 Webhook URL |
| `POST` | `/webhooks/deregister` | Push | 取消 Webhook |
| `GET`  | `/status` | — | 连接状态、统计信息、版本 |
| `GET`  | `/link` | — | 本端 `acp://` 链接 |
| `GET`  | `/card` | — | 双端 AgentCard |
| `GET`  | `/history` | — | 消息持久化历史（`?limit=N`） |

### 消息格式

`id`、`ts`、`from` 未指定时自动填充。

```json
{
  "id":      "msg_abc123def456",
  "ts":      "2026-03-18T12:00:00Z",
  "from":    "Agent-A",
  "type":    "task.delegate",
  "content": "消息内容"
}
```

---

## v1.3 新特性

- **Extension 机制** — URI 标识的 AgentCard 扩展，支持运行时注册/注销；向 A2A 扩展模型对齐
- **`did:acp:` DID 身份** — 基于 Ed25519 公钥派生的自主权标识符；`/.well-known/did.json` W3C 兼容文档
- **Docker GHCR CI** — `ghcr.io/kickflip73/agent-communication-protocol/acp-relay:latest`，支持 linux/amd64 + linux/arm64
- **兼容性认证指南** — 三级认证体系（Core/Recommended/Full），含自认证 badge 方案，见 [`docs/conformance.md`](conformance.md)

```bash
# 一行拉取最新镜像
docker pull ghcr.io/kickflip73/agent-communication-protocol/acp-relay:latest

# 带 DID 身份 + Extension 运行（需 :full 变体）
docker pull ghcr.io/kickflip73/agent-communication-protocol/acp-relay:full
docker run --rm -p 8000:8000 -p 8100:8100 \
  -v acp-identity:/root/.acp \
  ghcr.io/kickflip73/agent-communication-protocol/acp-relay:full \
  --name MyAgent --identity
```

---

## 路线图

| 版本 | 状态 | 亮点 |
|------|------|------|
| **v1.0** | ✅ GA | Task 状态机、消息幂等性、QuerySkill、P2P 直连 |
| **v1.1** | ✅ | HMAC 重放防护（replay-window）、`failed_message_id` 覆盖 |
| **v1.2** | ✅ | AgentCard 调度元数据（availability 块）、PATCH 实时更新 API、Docker 官方镜像 |
| **v1.3** | ✅ | Rust SDK、DID 身份（`did:acp:`）、Extension 机制、Docker GHCR CI、兼容性认证指南 |

---

## 与同类协议对比

| 维度 | MCP | A2A (Google) | ACP (IBM) | **ACP (本项目)** |
|------|-----|-------------|-----------|------------------|
| 定位 | Agent ↔ 工具 | Agent ↔ Agent（企业级）| Agent ↔ Agent（REST）| Agent ↔ Agent（P2P）|
| 传输层 | stdio / HTTP+SSE | HTTP+SSE / JSON-RPC | REST HTTP | WebSocket（直连）|
| 需要服务器 | ✗ | ✅ 需要 | ✅ 需要 | **无需** |
| 需要修改代码 | ✅ 需要 | ✅ 需要 | ✅ 需要 | **零修改** |
| 能力声明 | ✅ | ✅ AgentCard | - | ✅ AgentCard |
| 断线重连 | - | - | - | ✅ |
| 消息持久化 | - | - | - | ✅ |
| 调度元数据 | - | - | - | ✅ `availability`（v1.2） |
| DID 身份 | - | - | - | ✅ `did:acp:`（v1.3） |
| 扩展机制 | - | ✅（企业级） | - | ✅ URI 扩展（v1.3） |
| Docker 镜像 | - | - | - | ✅ GHCR（v1.3） |
| 兼容性认证 | - | ✅ | - | ✅ 三级自认证（v1.3） |

> MCP、A2A、IBM ACP 各有其设计目标，本项目聚焦「极简 P2P 直连」场景。

---

## 仓库结构

```
agent-communication-protocol/
├── relay/
│   ├── acp_relay.py     ← 核心：P2P 守护进程（~400行，单依赖）
│   └── SKILL.md         ← Agent 自动执行手册（直接发给任意 Agent）
├── spec/
│   ├── core-v0.1.md     ← 核心协议规范（英文）
│   ├── core-v0.1.zh.md  ← 核心协议规范（中文）
│   ├── transports.md    ← 传输层绑定
│   └── identity.md      ← 身份认证规范
├── docs/
│   └── README.zh-CN.md  ← 本文档
├── research/
│   └── *.md             ← 竞品研究报告
└── examples/            ← 示例代码
```

---

## 贡献指南

欢迎提交 Issue 和 PR！详见 [CONTRIBUTING.md](../CONTRIBUTING.zh.md)。

- 报告 Bug / 提议功能 → [GitHub Issues](https://github.com/Kickflip73/agent-communication-protocol/issues)
- 讨论协议设计 → [GitHub Discussions](https://github.com/Kickflip73/agent-communication-protocol/discussions)

---

## 许可证

[Apache License 2.0](../LICENSE)
