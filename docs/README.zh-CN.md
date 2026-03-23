<div align="center">

<h1>ACP — Agent Communication Protocol</h1>

<p>
  <strong>让任意两个 AI Agent 直接通信。人只需做两件事。</strong>
</p>

<p>
  <a href="https://github.com/Kickflip73/agent-communication-protocol/releases">
    <img src="https://img.shields.io/badge/版本-v1.3.0-blue?style=flat-square" alt="Version">
  </a>
  <a href="../LICENSE">
    <img src="https://img.shields.io/badge/协议-Apache_2.0-green?style=flat-square" alt="License">
  </a>
  <img src="https://img.shields.io/badge/Python-3.9%2B-blue?style=flat-square">
  <img src="https://img.shields.io/badge/依赖-仅_websockets-orange?style=flat-square">
</p>

<p>
  <a href="../README.md">English</a> ·
  <strong>简体中文</strong>
</p>

</div>

---

## 两步完成 Agent 互联

```
第一步 → 把 Skill URL 发给 Agent A，它会返回一个 acp:// 链接
第二步 → 把这个链接发给 Agent B
         两个 Agent 自动建立直连，开始通信
```

**人只做两件事：传 URL、传链接。其余全自动。**

---

## 快速开始

### 第一步 — 把 Skill URL 发给 Agent A

```
https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/SKILL.md
```

Agent A 会自动完成：下载脚本 → 安装依赖 → 启动服务 → 返回链接

```
✅ Ready. Your link: acp://1.2.3.4:7801/tok_xxxxx
```

### 第二步 — 把链接发给 Agent B

把上面的 `acp://...` 链接发给 Agent B（同样先发 Skill URL 启动它）。

Agent B 收到链接后自动连接，两边同时显示：

```
✅ Connected to AgentA
```

**完成。** 两个 Agent 现在可以互发消息了。

---

## 网络受限（沙箱 / K8s / 内网）？

如果 `acp://` 直连失败，ACP v1.4 起会**自动尝试 UDP 打洞（DCUtR 风格）**升级到直连；打洞失败才降级到 Relay 中转。全程用户零感知，无需手动 `--relay`。

如需显式走 Relay（兼容旧版），加 `--relay` 参数重启，得到 `acp+wss://` 链接。

→ **详见 [NAT 穿透与网络接入指南](nat-traversal.md)**

---

## 通信架构

### 握手流程（人只参与前两步）

```
  人
  │
  ├─[① Skill URL]──────────────► Agent A
  │                                  │  pip install websockets
  │                                  │  python3 acp_relay.py --name A
  │                                  │  → 监听 :7801/:7901
  │◄────────────[② acp://IP:7801/tok_xxx]─┘
  │
  ├─[③ acp://IP:7801/tok_xxx]──► Agent B
  │                                  │  POST /connect {"link":"acp://..."}
  │          ┌────────── WebSocket 握手 ─────────┐
  │          │  B → A : connect(tok_xxx)         │
  │          │  A ↔ B : AgentCard 互换           │
  │          │  A, B  : connected ✅             │
  │          └───────────────────────────────────┘
 done             ↕ P2P 消息直接流动
```

---

### P2P 直连模式（默认）

```
     机器 A                                              机器 B
┌──────────────────────────────┐    ┌──────────────────────────────┐
│                              │    │                              │
│  ┌──────────────────────┐    │    │    ┌──────────────────────┐  │
│  │     宿主程序 A        │    │    │    │     宿主程序 B        │  │
│  │  （LLM / 脚本）       │    │    │    │  （LLM / 脚本）       │  │
│  └───────────┬──────────┘    │    │    └──────────┬───────────┘  │
│              │ HTTP          │    │               │ HTTP         │
│              │ localhost     │    │               │ localhost    │
│  ┌───────────▼──────────┐    │    │    ┌──────────▼───────────┐  │
│  │    acp_relay.py      │    │    │    │    acp_relay.py      │  │
│  │                      │    │    │    │                      │  │
│  │  :7901  HTTP API  ◄──┼────┼────┼────┼──── POST /message    │  │
│  │          │            │    │    │    │          :send      │  │
│  │          │ SSE 推送   │    │    │    │                     │  │
│  │          ▼            │    │    │    │  GET /stream (SSE)  │  │
│  │  GET /stream ─────────┼────┼────┼────┼─────────────────►   │  │
│  │  （消息即达即推        │    │    │    │  宿主程序实时收到   │  │
│  │    给宿主程序）        │    │    │    │  无需轮询          │  │
│  │                       │    │    │    │                     │  │
│  │  :7801  WebSocket ◄───┼────┼────┼────┼─────────────────────│  │
│  └───────────────────────│    │    │    └────────────────────►│  │
│                          │    │    │                          │  │
│             WebSocket    │    │    │    WebSocket             │  │
│             P2P 直连     │◄═══╪════╪═══►P2P 直连              │  │
│             （无中间节点）│    │    │   （无中间节点）          │  │
└──────────────────────────┘    │    └──────────────────────────┘  │
                                │
                          互联网 / 局域网
                        （无 Relay 服务器参与）
```

| 通道 | 端口 | 方向 | 用途 |
|------|------|------|------|
| **WebSocket** | `:7801` | Agent ↔ Agent | P2P 数据通道，消息直达对端，无中间节点 |
| **HTTP API** | `:7901` | 宿主程序 → Agent | 发消息 (`POST /message:send`)、查状态、管理任务 |
| **SSE** | `:7901/stream` | Agent → 宿主程序 | 实时推送收到的消息，长连接，无需轮询 |

**宿主程序接入示例（3 行代码）：**

```python
# 发消息给对端 Agent
requests.post("http://localhost:7901/message:send", json={"text": "你好"})

# 实时监听收到的消息（SSE 长连接，消息即达即收）
for event in sseclient.SSEClient("http://localhost:7901/stream"):
    print(event.data)   # {"type":"message","text":"你好","from":"AgentB"}
```

---

### 完整连接策略（v1.4，自动选择，用户零感知）

```
┌─────────────────────────────────────────────────────────────────┐
│                    三级连接策略                                  │
│                                                                 │
│  Level 1 — 直连（最优）                                          │
│  ┌────────────┐                         ┌────────────┐          │
│  │  Agent A   │◄═══════ WS 直连 ════════►│  Agent B   │          │
│  └────────────┘   （公网 IP 或同内网）   └────────────┘          │
│                                                                 │
│  Level 2 — TCP 打洞 ★ v1.4 新增（双方都在 NAT 后面）             │
│  ┌────────────┐   ┌────────────┐        ┌────────────┐          │
│  │  Agent A   │──►│  Signaling │◄───────│  Agent B   │          │
│  │  (NAT)     │   │ （地址交换）│        │  (NAT)     │          │
│  └────────────┘   └────────────┘        └────────────┘          │
│        │            握手后退出                │                  │
│        └──────────── WS 直连 ───────────────┘                   │
│                    打洞成功，真 P2P                               │
│                                                                 │
│  Level 3 — Relay 降级（约 30% 场景，对称 NAT 兜底）              │
│  ┌────────────┐   ┌─────────────┐       ┌────────────┐          │
│  │  Agent A   │◄─►│  Relay      │◄─────►│  Agent B   │          │
│  └────────────┘   │  （无状态）  │       └────────────┘          │
│                   └─────────────┘                               │
│                     转发帧，不存储消息                            │
└─────────────────────────────────────────────────────────────────┘
```

> **Signaling Server** 只做一次性地址交换（TTL 30s），不转发任何消息，握手完成后立即退出。  
> **Relay** 是真正的最后兜底，不是主路径——对称 NAT 等少数场景才触发。

---

## 为什么选 ACP

| 问题 | 其他方案 | ACP |
|------|---------|-----|
| 需要服务器 | ✅ 是 | ❌ **不需要** |
| 需要改代码 | ✅ 是 | ❌ **不需要** |
| 配置成本 | 注册 / 部署 / 配置 | **一个链接** |
| 框架依赖 | 绑定特定框架 | **任意 Agent、任意语言** |
| 依赖数量 | 重量级 SDK | **只需 `websockets`** |

> MCP 标准化了 Agent↔Tool，ACP 标准化 Agent↔Agent。

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
| Docker | `docker pull ghcr.io/kickflip73/agent-communication-protocol/acp-relay` | 多架构 |

---

## 协议对比

| 维度 | MCP (Anthropic) | A2A (Google) | **ACP（本项目）** |
|------|----------------|-------------|-----------------|
| 定位 | Agent ↔ Tool | Agent ↔ Agent（企业级） | Agent ↔ Agent（**P2P 个人/小团队**） |
| 需要服务器 | — | ✅ 是 | ❌ **否** |
| 需要改代码 | ✅ 是 | ✅ 是 | ❌ **否** |
| 必要依赖 | 较多 | 较多 | **仅 `websockets`** |
| Task 状态机 | — | ✅ | ✅ |
| 调度元数据 | — | — | ✅ `availability`（v1.2，业界首创） |
| DID 身份 | — | OAuth 2.0（强制） | ✅ `did:acp:`（可选） |
| Docker 镜像 | — | — | ✅ GHCR CI（v1.3） |

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
| v1.3 | ✅ | Rust SDK、DID 身份、Extension 机制、GHCR CI |
| **v1.4** | 🔥 **进行中** | **真 P2P NAT 穿透**：TCP 打洞 + Signaling，Relay 退化为最后降级 |

---

## License

[Apache License 2.0](../LICENSE)

---

<div align="center">
<sub>MCP 标准化 Agent↔Tool，ACP 标准化 Agent↔Agent。P2P · 零服务器 · curl 可接入。</sub>
</div>
