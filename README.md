<div align="center">

<h1>ACP — Agent Communication Protocol</h1>

<p><strong>The missing link between AI Agents.</strong><br>
<em>Send a URL. Get a link. Two agents talk. That's it.</em></p>

<p>
  <a href="https://github.com/Kickflip73/agent-communication-protocol/releases">
    <img src="https://img.shields.io/badge/version-v1.4.0--dev-blue?style=flat-square" alt="Version">
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/license-Apache_2.0-green?style=flat-square" alt="License">
  </a>
  <img src="https://img.shields.io/badge/python-3.9%2B-blue?style=flat-square" alt="Python">
  <img src="https://img.shields.io/badge/stdlib__only-zero__heavy__deps-orange?style=flat-square" alt="Deps">
  <img src="https://img.shields.io/badge/latency-0.6ms_avg-brightgreen?style=flat-square" alt="Latency">
  <img src="https://img.shields.io/badge/tested-20%2F20_PASS-success?style=flat-square" alt="Tests">
</p>

<p>
  <a href="README.md">English</a> ·
  <a href="docs/README.zh-CN.md">简体中文</a>
</p>

</div>

> **MCP standardized Agent↔Tool. ACP standardizes Agent↔Agent.**  
> P2P · Zero server required · curl-compatible · works with any LLM framework

---

```
$ # Agent A — get your link
$ python3 acp_relay.py --name AgentA
✅ Ready.  Your link: acp://1.2.3.4:7801/tok_xxxxx
           Send this link to any other Agent to connect.

$ # Agent B — connect with one API call
$ curl -X POST http://localhost:7901/peers/connect \
       -d '{"link":"acp://1.2.3.4:7801/tok_xxxxx"}'
{"ok":true,"peer_id":"peer_001"}

$ # Agent B — send a message
$ curl -X POST http://localhost:7901/message:send \
       -d '{"text":"Hello AgentA, I need your analysis on X"}'
{"ok":true,"message_id":"msg_abc123","peer_id":"peer_001"}

$ # Agent A — receive in real-time (SSE stream)
$ curl http://localhost:7901/stream
event: acp.message
data: {"from":"AgentB","text":"Hello AgentA, I need your analysis on X"}
```

---

## Quick Start

### Option A — AI Agent native (2 steps, zero config)

```
# Step 1: Send this URL to Agent A (any LLM-based agent)
https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/SKILL.md

# Agent A auto-installs, starts, and replies:
# ✅ Ready. Your link: acp://1.2.3.4:7801/tok_xxxxx

# Step 2: Send that acp:// link to Agent B
# Both agents are now directly connected. Done.
```

### Option B — Manual / script

```bash
# Install
pip install websockets

# Start Agent A
python3 relay/acp_relay.py --name AgentA
# → ✅ Ready. Your link: acp://YOUR_IP:7801/tok_xxxxx

# In another terminal — Agent B connects
python3 relay/acp_relay.py --name AgentB \
  --join acp://YOUR_IP:7801/tok_xxxxx
# → ✅ Connected to AgentA
```

### Option C — Docker

```bash
docker run -p 7801:7801 -p 7901:7901 \
  ghcr.io/kickflip73/agent-communication-protocol/acp-relay \
  --name MyAgent
```

---

## 网络受限（沙箱 / K8s / 内网）？

ACP v1.4 内置三级自动连接策略，**用户零感知**：

```
Level 1 — Direct connect       (has public IP / same LAN)
   ↓ fail within 3s
Level 2 — UDP hole punch        (both behind NAT — NEW in v1.4)
           DCUtR-style: STUN address discovery → relay signaling → simultaneous probes
           ✅ Works with ~70% of real-world NAT types (full-cone, port-restricted)
   ↓ fail
Level 3 — Relay fallback        (symmetric NAT / CGNAT — ~30% of cases)
           Cloudflare Worker relay, stateless, no message storage
```

SSE 事件实时反映当前连接层级：`dcutr_started` → `dcutr_connected` / `relay_fallback`。
`GET /status` 返回 `connection_type`: `p2p_direct` | `dcutr_direct` | `relay`。

如需显式走 Relay（如旧版本兼容），可加 `--relay` 参数启动，得到 `acp+wss://` 链接。

→ **详见 [NAT 穿透与网络接入指南](docs/nat-traversal.md)**

---

## 通信架构

### 握手流程（人只参与前两步）

```
  Human
    │
    ├─[① Skill URL]──────────────► Agent A
    │                                  │  pip install websockets
    │                                  │  python3 acp_relay.py --name A
    │                                  │  → listens on :7801/:7901
    │◄────────────[② acp://IP:7801/tok_xxx]─┘
    │
    ├─[③ acp://IP:7801/tok_xxx]──► Agent B
    │                                  │  POST /connect {"link":"acp://..."}
    │                                  │
    │          ┌────────── WebSocket Handshake ──────────┐
    │          │  B → A : connect(tok_xxx)               │
    │          │  A → B : AgentCard exchange             │
    │          │  A,B   : connected ✅                   │
    │          └──────────────────────────────────────────┘
    │
   done                ↕ P2P messages flow directly
```

---

### P2P 直连模式（默认）

```
  Machine A                                          Machine B
┌─────────────────────────────┐    ┌─────────────────────────────┐
│                             │    │                             │
│  ┌─────────────────────┐    │    │    ┌─────────────────────┐  │
│  │    Host App A       │    │    │    │    Host App B       │  │
│  │  (LLM / Script)     │    │    │    │  (LLM / Script)     │  │
│  └──────────┬──────────┘    │    │    └──────────┬──────────┘  │
│             │ HTTP          │    │               │ HTTP         │
│             │ localhost     │    │               │ localhost    │
│  ┌──────────▼──────────┐    │    │    ┌──────────▼──────────┐  │
│  │   acp_relay.py      │    │    │    │   acp_relay.py      │  │
│  │                     │    │    │    │                     │  │
│  │  :7901  HTTP API ◄──┼────┼────┼────┼──── POST /message   │  │
│  │         │           │    │    │    │          :send      │  │
│  │         │ SSE push  │    │    │    │                     │  │
│  │         ▼           │    │    │    │  GET /stream (SSE)  │  │
│  │  GET /stream ───────┼────┼────┼────┼──────────────────►  │  │
│  │  (real-time push    │    │    │    │  host app receives  │  │
│  │   to host app)      │    │    │    │  messages instantly │  │
│  │                     │    │    │    │                     │  │
│  │  :7801  WebSocket ◄─┼────┼────┼────┼──────────────────── │  │
│  └──────────────────── │    │    │    └────────────────────►│  │
│                        │    │    │                          │  │
│            WebSocket   │    │    │   WebSocket              │  │
│            P2P Direct  │◄═══╪════╪═══►Direct               │  │
│            (no broker) │    │    │   (no broker)            │  │
└────────────────────────┘    │    └──────────────────────────┘  │
                              │                                   │
                         Internet / LAN
                      (no relay server involved)
```

| 通道 | 端口 | 方向 | 用途 |
|------|------|------|------|
| **WebSocket** | `:7801` | Agent ↔ Agent | P2P 数据通道，消息直达对端，无中间节点 |
| **HTTP API** | `:7901` | Host App → Agent | 发消息 (`POST /message:send`)、查状态、管理任务 |
| **SSE** | `:7901/stream` | Agent → Host App | 实时推送收到的消息，长连接，无需轮询 |

**宿主程序接入示例（3 行代码）：**

```python
# 发消息给对端 Agent
requests.post("http://localhost:7901/message:send", json={"text": "Hello"})

# 实时监听收到的消息（SSE 长连接，消息即达即收）
for event in sseclient.SSEClient("http://localhost:7901/stream"):
    print(event.data)   # {"type":"message","text":"Hi back","from":"AgentB"}
```

---

### 完整连接策略（v1.4，自动选择，用户零感知）

```
┌─────────────────────────────────────────────────────────────────┐
│              Three-Level Connection Strategy                    │
│                                                                 │
│  Level 1 ─ Direct Connect（最优）                               │
│  ┌────────────┐                         ┌────────────┐          │
│  │  Agent A   │◄══════ WS direct ══════►│  Agent B   │          │
│  └────────────┘    (public IP / LAN)    └────────────┘          │
│                                                                 │
│  Level 2 ─ UDP Hole Punch ✅ v1.4 已实现（双方在 NAT 后面）        │
│  ┌────────────┐   ┌────────────┐        ┌────────────┐          │
│  │  Agent A   │──►│ Signaling  │◄───────│  Agent B   │          │
│  │  (NAT)     │   │ (addr exch)│        │  (NAT)     │          │
│  └────────────┘   └────────────┘        └────────────┘          │
│        │           exits after                │                  │
│        └──────────── WS direct ──────────────┘                  │
│                   (打洞成功，真 P2P)                              │
│                                                                 │
│  Level 3 ─ Relay Fallback（最后降级，约 30% 对称 NAT 场景）      │
│  ┌────────────┐   ┌─────────────┐       ┌────────────┐          │
│  │  Agent A   │◄─►│ Relay       │◄─────►│  Agent B   │          │
│  └────────────┘   │ (stateless) │       └────────────┘          │
│                   └─────────────┘                               │
│                   frames only, no storage                       │
└─────────────────────────────────────────────────────────────────┘
```

> **Signaling Server** 只做一次性地址交换（TTL 30s），不转发任何消息帧，握手后立即退出。  
> **Relay** 是真正的最后兜底，不是主路径——对称 NAT 等少数场景才会触发。

---

## Why ACP

| | A2A (Google) | ACP |
|---|---|---|
| **Setup** | OAuth 2.0 + agent registry + push endpoint | One URL |
| **Server required** | Yes (HTTPS endpoint you must host) | **No** |
| **Framework lock-in** | Yes | **Any agent, any language** |
| **NAT / firewall** | You figure it out | **Auto: direct → hole-punch → relay** |
| **Message latency** | Depends on your infra | **0.6ms avg (P99 2.8ms)** |
| **Min dependencies** | Heavy SDK | **`pip install websockets`** |
| **Identity** | OAuth tokens | **Ed25519 + did:acp: DID** |
| **Availability signaling** | ❌ (open issue #1667) | **✅ `availability` field (v1.2)** |
| **Agent identity proof** | ❌ (open issue #1672) | **✅ Ed25519 keypair (v0.8+)** |

> ACP solves problems A2A is still discussing in GitHub issues.

### Numbers

- **0.6ms** avg send latency · **2.8ms** P99
- **1,930 req/s** sequential throughput
- **< 50ms** SSE push latency (threading.Event, not polling)
- **19/19 test scenarios PASS** (error handling · reconnection · ring pipeline · concurrent)
- **184 commits** · **3,300+ lines** · **zero known P0/P1 bugs**

---

## API 速查

| 功能 | 方法 | 路径 |
|------|------|------|
| 获取本机链接 | GET | `/link` |
| 主动连接对方 | POST | `/connect` `{"link":"acp://..."}` |
| 发消息 | POST | `/message:send` `{"text":"..."}` |
| 实时收消息 | GET | `/stream` (SSE) |
| 查状态 | GET | `/status` |
| 查已连接 Peer | GET | `/peers` |
| AgentCard | GET | `/.well-known/acp.json` |

HTTP 默认端口：`7901`（WS 端口：`7801`）

---

## 可选特性

| 特性 | 参数 | 说明 |
|------|------|------|
| 公共中继（网络受限时） | `--relay` | `acp+wss://` 格式链接 |
| HMAC 消息签名 | `--secret <key>` | 两端共享密钥，无需额外依赖 |
| Ed25519 身份 | `--identity` | 需 `pip install cryptography` |
| mDNS 局域网发现 | `--advertise-mdns` | 无需 zeroconf 库 |
| Docker | `docker pull ghcr.io/kickflip73/agent-communication-protocol/acp-relay` | 多架构，含 GHCR CI |

---

## Task 状态机

用于跨 Agent 协作追踪任务进度：

```
submitted → working → completed ✅
                    → failed    ❌
                    → input_required → working（等待补充输入）
```

API：`POST /tasks` 创建，`POST /tasks/{id}:update` 更新状态。

---

## SDK

- **Python** — `sdk/python/` (`RelayClient`)
- **Node.js** — `sdk/node/` (零外部依赖，含 TypeScript 类型)
- **Go** — `sdk/go/` (零外部依赖，Go 1.21+)
- **Rust** — `sdk/rust/` (v1.3)

---

## 版本历史

| 版本 | 状态 | 重点 |
|------|------|------|
| v0.1–v0.5 | ✅ | P2P 核心、Task 状态机、消息幂等 |
| v0.6 | ✅ | 多 Peer 注册、标准错误码 |
| v0.7 | ✅ | HMAC 签名、mDNS 发现 |
| v0.8–v0.9 | ✅ | Ed25519 身份、Node.js SDK、compat 测试套件 |
| v1.0 | ✅ | 生产稳定、安全审计、Go SDK |
| v1.1 | ✅ | HMAC replay-window、`failed_message_id` |
| v1.2 | ✅ | 调度元数据 (`availability`)、Docker 镜像 |
| v1.3 | ✅ | Rust SDK、DID 身份 (`did:acp:`)、Extension 机制、GHCR CI |
| **v1.4** | ✅ **已实现** | **真 P2P NAT 穿透**：UDP 打洞（DCUtR 风格）+ Signaling，三级自动降级，Relay 退化为最后兜底 |

---

## 仓库结构

```
agent-communication-protocol/
├── SKILL.md              ← 发这个 URL 给 Agent 即可接入
├── relay/
│   └── acp_relay.py      ← 核心守护进程（单文件）
├── spec/                 ← 协议规范文档
├── sdk/                  ← Python / Node.js / Go / Rust SDK
├── tests/                ← compat + integration 测试套件
├── docs/                 ← 中文文档、conformance 指南、博客草稿
└── acp-research/         ← 竞品情报、ROADMAP
```

---

## Contributing

欢迎贡献！详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

- Bug 报告 & 功能请求 → [GitHub Issues](https://github.com/Kickflip73/agent-communication-protocol/issues)
- 协议设计讨论 → [GitHub Discussions](https://github.com/Kickflip73/agent-communication-protocol/discussions)

---

## License

[Apache License 2.0](LICENSE)

---

<div align="center">
<sub>MCP 标准化 Agent↔Tool，ACP 标准化 Agent↔Agent。P2P · 零服务器 · curl 可接入。</sub>
</div>
