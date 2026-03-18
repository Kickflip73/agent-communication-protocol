# ACP — Agent Communication Protocol

**让任意两个 Agent 在 2 步内建立直接通信，无中间服务器，真正 P2P。**

> ACP is to Agent-to-Agent communication what MCP is to Agent-to-Tool communication.  
> Zero code changes. Zero central server. Link-based pairing.

[English](#english) | [中文](#中文)

---

## 中文

### 核心理念

```
发起方监听端口 → 生成 acp:// 链接（含 IP:Port/Token）
接收方粘贴链接 → 直接 TCP 连接到发起方
两端直连，无任何中间服务器
```

```
Agent A                                    Agent B
  │                                           │
  │  POST /send                               │  POST /send
  │  GET  /recv                               │  GET  /recv
  │      ↕ localhost:7901                     │      ↕ localhost:7901
  │  ┌─────────────────┐                      │  ┌─────────────────┐
  │  │  ACP P2P Relay  │◄── WebSocket 直连 ───►│  │  ACP P2P Relay  │
  │  │  (本地守护进程)  │    无中间服务器        │  │  (本地守护进程)  │
  │  └─────────────────┘                      │  └─────────────────┘
```

---

### 快速上手

#### 第一步：Agent A 启动并生成链接

```bash
pip install websockets
curl -O https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/relay/acp_relay.py
python3 acp_relay.py --name "Agent-A"
```

输出：
```
✅ ACP P2P 通信服务已启动

🔗 你的通信链接（发给对方）:
   acp://1.2.3.4:7801/tok_abc123def456

📋 对方执行:
   python3 acp_relay.py --name "对方名称" --join acp://1.2.3.4:7801/tok_abc123def456
```

#### 第二步：Agent B 粘贴链接直连

```bash
pip install websockets
curl -O https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/relay/acp_relay.py
python3 acp_relay.py --name "Agent-B" --join acp://1.2.3.4:7801/tok_abc123def456
```

输出：
```
✅ P2P 连接成功！（直连，无中间服务器）
   对方: 1.2.3.4:7801
```

#### 开始通信（双方都用 localhost:7901）

```bash
# 发消息
curl -X POST http://localhost:7901/send \
  -H "Content-Type: application/json" \
  -d '{"type": "chat", "text": "你好！"}'

# 收消息
curl http://localhost:7901/recv

# 查看连接状态
curl http://localhost:7901/status
```

---

### 本地 HTTP 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/send` | 发消息（任意 JSON） |
| `GET` | `/recv` | 取消息（轮询，取后移除） |
| `GET` | `/status` | 连接状态 |
| `GET` | `/link` | 获取本端 acp:// 链接 |

**端口规则：** `--port N`（WebSocket，发起方，默认 7801），HTTP 接口 = N+100（默认 7901）

---

### 命令行参数

```
python3 acp_relay.py [选项]

  --name  NAME    本端名称（显示用，默认 "ACP-Agent"）
  --join  LINK    加入对方链接（接收方用）
  --port  N       WebSocket 监听端口（发起方，默认 7801）
                  HTTP 接口 = N+100（默认 7901）
```

---

### P2P 工作原理

```
链接格式: acp://<host>:<port>/<token>

host  = 发起方的公网 IP（或局域网 IP）
port  = WebSocket 监听端口
token = 一次性随机 token，防止误连

接收方解析链接 → 直接 WebSocket 连接 → 验证 token → 建立双向通道
```

没有注册中心，没有信令服务器，没有中继服务器。
唯一的"服务"是发起方自己监听的端口。

---

### 适用场景

| 场景 | 可行性 |
|------|--------|
| 同一台机器两个 Agent | ✅ 直接用 localhost |
| 同一局域网 | ✅ 用局域网 IP |
| 公网（有公网 IP 的 VPS/云服务器） | ✅ 自动探测 |
| 两端都在 NAT 后（家用路由器） | ⚠️ 需要端口转发或 VPN |

---

## English

### Core Concept

```
Initiator listens on a port → generates acp:// link (contains IP:Port/Token)
Receiver pastes the link → connects directly via TCP (WebSocket)
Pure P2P — no relay server, no central service
```

### Quick Start

**Agent A (initiator):**
```bash
pip install websockets
python3 acp_relay.py --name "Agent-A"
# → prints: 🔗 acp://1.2.3.4:7801/tok_abc123
```

**Agent B (receiver):**
```bash
pip install websockets
python3 acp_relay.py --name "Agent-B" --join acp://1.2.3.4:7801/tok_abc123
```

**Both agents communicate via localhost:**
```bash
curl -X POST http://localhost:7901/send -d '{"text":"Hello!"}'
curl http://localhost:7901/recv
```

### How It Works

```
acp://<host>:<port>/<token>
  host  = initiator's public (or LAN) IP
  port  = WebSocket listen port
  token = one-time random token for authentication

Receiver parses link → WebSocket connect → token verify → bidirectional channel
```

No registry. No signaling server. No relay server.
The only "service" is the initiator's own listening port.

---

## Repository Structure

```
relay/
└── acp_relay.py      ← The only file you need (~300 lines, 1 dependency: websockets)

spec/                 ← Protocol specification
sdk/                  ← SDK for deeper integration
examples/             ← Code examples
```

---

## License

Apache 2.0

**GitHub:** https://github.com/Kickflip73/agent-communication-protocol
