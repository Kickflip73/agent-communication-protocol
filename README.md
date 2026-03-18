# ACP — Agent Communication Protocol

**让任意两个 Agent 在 2 步内建立通信，无需修改任何代码。**

> ACP is to Agent-to-Agent communication what MCP is to Agent-to-Tool communication.
> But ACP goes further: **zero-code setup, link-based pairing, works with any existing agent.**

[English](#english) | [中文](#中文)

---

## 中文

### 核心理念

绝大多数 Agent 互联方案都要求你**修改 Agent 代码**，实现特定接口，配置复杂的传输层。

**ACP 的理念完全不同：**

```
Agent 不需要懂 ACP。
Agent 只需要能发 HTTP 请求。
```

ACP 在 Agent 旁边启动一个**本地 Relay 守护进程**，负责所有的协议细节。
Agent 只和本地 Relay 说话，Relay 负责与对方通信。

```
┌─────────────────────────────────┐       ┌─────────────────────────────────┐
│  Agent A（任意框架）              │       │  Agent B（任意框架）              │
│  POST /send → "你好"            │       │  GET  /recv → "你好"            │
│  GET  /recv ← "收到！"           │       │  POST /send → "收到！"           │
│         ↕ localhost:7801        │       │         ↕ localhost:7801        │
│  ┌──────────────────────────┐   │       │   ┌──────────────────────────┐  │
│  │     ACP Local Relay      │   │       │   │     ACP Local Relay      │  │
│  └────────────┬─────────────┘   │       │   └─────────────┬────────────┘  │
└───────────────│─────────────────┘       └─────────────────│───────────────┘
                │         WebSocket (acp:// 链接)            │
                └──────────────────┬────────────────────────┘
                          ┌────────▼────────┐
                          │  ACP Relay 服务  │
                          │  relay.acp.dev  │
                          └─────────────────┘
```

---

### 快速上手：2 步建立 Agent 通信

#### Agent A（发起方）— 执行这个 Skill

```bash
# 1. 安装依赖（仅需一次）
pip install websockets

# 2. 下载并启动通信服务
curl -O https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/relay/acp_relay.py
python3 acp_relay.py --name "Agent-A"
```

输出：
```
✅ ACP 通信服务已启动！

🔗 你的通信链接:
   acp://relay.acp.dev/abc123def456

📋 把这个链接发给对方 Agent，让对方执行:
   python3 acp_relay.py --name "对方名称" --join acp://relay.acp.dev/abc123def456
```

#### Agent B（接收方）— 收到链接后执行

```bash
pip install websockets
curl -O https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/relay/acp_relay.py
python3 acp_relay.py --name "Agent-B" --join acp://relay.acp.dev/abc123def456
```

#### 开始通信（双方均可）

```bash
# 发消息
curl -X POST http://localhost:7801/send \
  -H "Content-Type: application/json" \
  -d '{"type": "chat", "text": "你好！"}'

# 收消息
curl http://localhost:7801/recv

# 查看状态
curl http://localhost:7801/status
```

**就这样。两个 Agent 现在可以双向通信了，一行代码都没改。**

---

### 工作原理

```
步骤 1：Agent A 启动本地 Relay
         Relay 连接到公共中继服务器，注册一个 Session
         服务器返回 Session ID，Relay 生成 acp:// 链接

步骤 2：Agent A 把链接发给 Agent B
         Agent B 启动 Relay，Relay 用链接里的 Session ID 加入同一个 Session

步骤 3：双方 Relay 都在线
         任一方调用 POST /send → Relay A → WebSocket → 中继服务器 → WebSocket → Relay B → 放入消息队列
         对方调用 GET /recv → 从消息队列取出
```

本地 HTTP 接口（`localhost:7801`）完全是标准 REST，任何语言、任何框架都能调用。

---

### 本地接口文档

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/send` | 发送消息（JSON body，任意结构） |
| `GET` | `/recv` | 获取新消息（轮询，取后从队列移除） |
| `GET` | `/status` | 查看连接状态（session ID、在线人数、链接等） |
| `GET` | `/link` | 仅获取 acp:// 链接 |

`/send` 会自动补全 `id`、`ts`、`from` 字段（如果没有提供）。

---

### 自建中继服务器

不想依赖公共服务器？自建只需一个命令：

```bash
pip install websockets
curl -O https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/relay/relay_server.py
python3 relay_server.py --host 0.0.0.0 --port 7800
```

然后用 `--relay` 参数指向你自己的服务器：

```bash
python3 acp_relay.py --name "Agent-A" --relay ws://your-server:7800
```

---

### 消息格式

消息是任意 JSON 对象。ACP Relay 会自动添加元数据，Agent 无需关心：

```json
{
  "type": "chat",
  "text": "你好！",
  "id": "msg_abc123",
  "ts": "2026-03-18T10:00:00Z",
  "from": "Agent-A",
  "_from_peer": "peer_xxx",
  "_session_id": "abc123def456"
}
```

你的 Agent 只需要关心 `type`、`text` 或其他你自己定义的字段。

---

### 与其他方案对比

| | ACP | 传统 SDK 方案 | 自建 API |
|--|-----|--------------|----------|
| 需要改 Agent 代码 | ❌ 不需要 | ✅ 需要 | ✅ 需要 |
| 需要公网 IP | ❌ 不需要 | 通常需要 | ✅ 需要 |
| 配置复杂度 | 2 条命令 | 高 | 极高 |
| 跨语言支持 | ✅ 任意语言 | 限定语言 | 手动实现 |
| 建立连接时间 | < 30 秒 | 数小时 | 数天 |

---

## English

### Core Philosophy

Most agent communication frameworks require you to **modify agent code**, implement specific interfaces, and configure complex transport layers.

**ACP takes a completely different approach:**

```
Agents don't need to understand ACP.
Agents just need to be able to make HTTP requests.
```

ACP runs a **local Relay daemon** beside each agent, handling all protocol details.
Agents only talk to their local Relay; the Relay handles everything else.

---

### Quick Start: 2 Steps to Connect Any Two Agents

**Agent A (initiator):**
```bash
pip install websockets
curl -O https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/relay/acp_relay.py
python3 acp_relay.py --name "Agent-A"
# → prints: 🔗 Your link: acp://relay.acp.dev/abc123def456
```

**Agent B (receiver) — after getting the link:**
```bash
pip install websockets
curl -O https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/relay/acp_relay.py
python3 acp_relay.py --name "Agent-B" --join acp://relay.acp.dev/abc123def456
```

**Both agents now communicate via:**
```bash
# Send
curl -X POST http://localhost:7801/send -H "Content-Type: application/json" \
     -d '{"type": "chat", "text": "Hello!"}'

# Receive
curl http://localhost:7801/recv
```

**That's it. Zero code changes required.**

---

### Architecture

```
Agent A ──HTTP──► Local Relay A ──WebSocket──► Relay Server ◄──WebSocket── Local Relay B ◄──HTTP── Agent B
(any framework)  localhost:7801               relay.acp.dev                localhost:7801   (any framework)
```

1. Agent A starts Relay → Relay registers session on server → gets `acp://` link
2. Agent A shares link with Agent B → Agent B's Relay joins the same session
3. Both Relays connected → messages route through the server automatically

---

### Self-Hosting the Relay Server

```bash
pip install websockets
python3 relay_server.py --host 0.0.0.0 --port 7800

# Then use your server:
python3 acp_relay.py --name "Agent-A" --relay ws://your-server:7800
```

---

## Repository Structure

```
relay/
├── relay_server.py        ← Public relay server (self-hostable, ~150 lines)
├── acp_relay.py           ← Local relay daemon (run beside each agent, ~250 lines)
└── install-acp-skill.md   ← The Skill to send to any Agent for instant setup

spec/                      ← Protocol specification (for advanced use cases)
sdk/                       ← SDK for agents that want deeper integration
examples/                  ← Code examples
```

---

## License

Apache 2.0 — free for commercial and open-source use.

**GitHub:** https://github.com/Kickflip73/agent-communication-protocol
