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

如果 `acp://` 直连失败，让 Agent 加 `--relay` 参数重启，得到 `acp+wss://` 链接走公共中继。操作步骤完全一样，只是链接格式不同。

---

## 工作原理

```
人 ──[Skill URL]──► Agent A  ─────────────────────────────┐
                     ↓ 启动服务                              │
                     ↓ 返回 acp:// 链接                      │
人 ──[acp:// 链接]──► Agent B                               │
                       ↓ 连接 Agent A ◄─── P2P WebSocket ───┘
                       ✅ 通信建立，Relay 退出
```

- **Relay** 只参与握手打洞，不存储任何消息
- **P2P WebSocket** 是数据通道，Agent 之间直连
- **SSE (`/stream`)** 是 Agent 的本地消息监听接口，供宿主程序订阅

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

---

## License

[Apache License 2.0](../LICENSE)

---

<div align="center">
<sub>MCP 标准化 Agent↔Tool，ACP 标准化 Agent↔Agent。P2P · 零服务器 · curl 可接入。</sub>
</div>
