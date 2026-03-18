# ACP — Agent 通信协议

<p align="center">
  <img src="https://img.shields.io/badge/版本-v0.2-blue" alt="Version">
  <img src="https://img.shields.io/badge/许可证-Apache_2.0-green" alt="License">
  <img src="https://img.shields.io/badge/依赖-websockets-orange" alt="Dependency">
  <img src="https://img.shields.io/badge/Python-3.9%2B-blue" alt="Python">
</p>

**ACP（Agent Communication Protocol）是一个零服务器、零代码修改的 P2P Agent 通信协议。** 人只需完成 2 步操作，任意两个 AI Agent 即可建立直接加密通信通道。

---

## 目录

- [为什么选择 ACP](#为什么选择-acp)
- [工作原理](#工作原理)
- [快速上手（2分钟）](#快速上手2分钟)
- [接口文档](#接口文档)
- [v0.2 新特性](#v02-新特性)
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

### 发起方（Agent A）

```bash
pip install websockets -q
curl -fsSL https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/relay/acp_relay.py -o acp_relay.py
python3 acp_relay.py --name "Agent-A" --skills "summarize,translate"
```

Agent A 启动后输出：
```
🔗 你的通信链接（发给对方）:
   acp://1.2.3.4:7801/tok_abc123...
```

### 接收方（Agent B）

```bash
pip install websockets -q
curl -fsSL https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/relay/acp_relay.py -o acp_relay.py
python3 acp_relay.py --name "Agent-B" --join acp://1.2.3.4:7801/tok_abc123...
```

### 收发消息

```bash
# 发消息（任意 JSON）
curl -X POST http://localhost:7901/send \
  -H "Content-Type: application/json" \
  -d '{"type": "task.delegate", "content": "请帮我分析这段代码"}'

# 收消息
curl http://localhost:7901/recv
```

### 查看对方能力（AgentCard）

```bash
curl http://localhost:7901/card
# 返回：
# { "self": { "name": "Agent-A", "skills": ["summarize","translate"] },
#   "peer": { "name": "Agent-B", "skills": [...] } }
```

---

## 接口文档

发起方默认使用 `--port 7801`，HTTP 接口为 `7901`（= WS 端口 + 100）。
接收方通常使用 `--port 7820`，HTTP 接口为 `7920`。

| 方法 | 路径 | 描述 |
|------|------|------|
| `POST` | `/send` | 发送消息（任意 JSON body） |
| `GET`  | `/recv` | 获取新消息（消费队列，支持 `?limit=N`） |
| `GET`  | `/status` | 连接状态、统计信息、版本 |
| `GET`  | `/link` | 获取本端 `acp://` 链接 |
| `GET`  | `/card` | 查看本端和对端的 AgentCard（含能力列表）|
| `GET`  | `/history` | 完整消息历史（本地 JSONL，支持 `?limit=N`）|
| `GET`  | `/stream` | SSE 流式消息订阅（实时推送）|

### 消息格式

```json
{
  "id":   "msg_abc123",
  "ts":   "2026-03-18T12:00:00Z",
  "from": "Agent-A",
  "type": "task.delegate",
  "content": "消息内容"
}
```

`id`、`ts`、`from` 字段若未指定，ACP 自动填充。

---

## v0.2 新特性

基于对 **Google A2A**、**IBM ACP**、**ANP** 的竞品研究，v0.2 引入：

- **AgentCard 能力声明** — 连接建立时双方自动交换能力声明，通过 `/card` 接口查询
- **断线自动重连** — 接收方模式下支持指数退避自动重连（最多 10 次，最长间隔 60s）
- **消息持久化** — 所有收到的消息写入本地 JSONL 文件，通过 `/history` 查询完整历史
- **SSE 流式订阅** — `/stream` 端点实时推送新消息，兼容 A2A 风格客户端

---

## 路线图

| 版本 | 计划功能 |
|------|---------|
| **v0.3** | Task 生命周期（submitted/working/completed）、多会话并发、能力查询 API |
| **v0.4** | 多模态消息（文本/文件引用/结构化数据）、NAT 穿透探索 |
| **v1.0** | DID 去中心化身份认证、Agent 发现网络 |

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
