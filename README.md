<div align="center">

<h1>ACP — Agent Communication Protocol</h1>

<p>
  <strong>让任意两个 AI Agent 直接通信。人只需做两件事。</strong>
</p>

<p>
  <a href="https://github.com/Kickflip73/agent-communication-protocol/releases">
    <img src="https://img.shields.io/badge/version-v1.3.0-blue?style=flat-square" alt="Version">
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/license-Apache_2.0-green?style=flat-square" alt="License">
  </a>
  <img src="https://img.shields.io/badge/python-3.9%2B-blue?style=flat-square" alt="Python">
  <img src="https://img.shields.io/badge/deps-websockets_only-orange?style=flat-square" alt="Deps">
  <a href="https://github.com/Kickflip73/agent-communication-protocol/actions/workflows/docker-publish.yml">
    <img src="https://img.shields.io/badge/docker-GHCR-2496ED?style=flat-square&logo=docker" alt="Docker">
  </a>
</p>

<p>
  <a href="README.md">English</a> ·
  <a href="docs/README.zh-CN.md">简体中文</a>
</p>

</div>

---

## 两步完成 Agent 互联

```
Step 1 → 把 Skill URL 发给 Agent A，它会返回一个 acp:// 链接
Step 2 → 把这个链接发给 Agent B
         两个 Agent 自动建立直连，开始通信
```

**人只做两件事：传 URL、传链接。其余全自动。**

---

## Quick Start

### Step 1 — 把 Skill URL 发给 Agent A

```
https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/SKILL.md
```

Agent A 会自动完成：下载脚本 → 安装依赖 → 启动服务 → 返回链接

```
✅ Ready. Your link: acp://1.2.3.4:7801/tok_xxxxx
```

### Step 2 — 把链接发给 Agent B

把上面的 `acp://...` 链接发给 Agent B（同样先发 Skill URL 启动它）。

Agent B 收到链接后自动连接，两边同时显示：

```
✅ Connected to AgentA
```

**完成。** 两个 Agent 现在可以互发消息了。

---

## 网络受限（沙箱 / K8s / 内网）？

如果 `acp://` 直连失败，让 Agent 加 `--relay` 参数启动，得到 `acp+wss://` 链接走公共中继。操作步骤完全一样，只是链接格式不同。

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
┌─────────────────────────────────────────────────────────────────┐
│                          P2P Direct                             │
│                                                                 │
│   ┌──────────────────┐          ┌──────────────────┐           │
│   │     Agent A      │          │     Agent B      │           │
│   │                  │          │                  │           │
│   │  acp_relay.py    │          │  acp_relay.py    │           │
│   │  :7801 (WS)      │◄────────►│  :7801 (WS)      │           │
│   │  :7901 (HTTP)    │  P2P WS  │  :7901 (HTTP)    │           │
│   │                  │ ======== │                  │           │
│   │  POST /message   │  frames  │  GET  /stream    │           │
│   │       :send      │─────────►│  (SSE push) ──►  │           │
│   │                  │          │  host app        │           │
│   └──────────────────┘          └──────────────────┘           │
│        ▲ HTTP                         ▲ HTTP                   │
│        │ localhost                    │ localhost               │
│   [host app A]                   [host app B]                  │
│                                                                 │
│   link: acp://IP:7801/tok_xxx    No server. No broker.         │
└─────────────────────────────────────────────────────────────────┘
```

- **WebSocket (`:7801`)** — Agent 之间的专用数据通道，双向全双工
- **HTTP (`:7901`)** — Agent 暴露给宿主程序的本地控制接口
- **SSE (`/stream`)** — 宿主程序订阅收到的消息，实时推送，无需轮询
- **无中间服务器** — 消息直达对端，不经过任何第三方节点

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
│  Level 2 ─ TCP Hole Punch ★ v1.4 新增（双方在 NAT 后面）         │
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

## 为什么选 ACP

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
| **v1.4** | 🔥 **进行中** | **真 P2P NAT 穿透**：TCP 打洞 + Signaling，Relay 退化为最后降级 |

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
