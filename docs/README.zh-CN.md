<div align="center">

<h1>ACP — Agent Communication Protocol</h1>

<p><strong>让任意两个 AI Agent 直接通信。人只需做两件事。</strong></p>

<p>
  <a href="https://github.com/Kickflip73/agent-communication-protocol/releases">
    <img src="https://img.shields.io/badge/版本-v2.4.0-blue?style=flat-square" alt="Version">
  </a>
  <a href="../LICENSE">
    <img src="https://img.shields.io/badge/协议-Apache_2.0-green?style=flat-square" alt="License">
  </a>
  <img src="https://img.shields.io/badge/Python-3.9%2B-blue?style=flat-square">
  <img src="https://img.shields.io/badge/依赖-仅_websockets-orange?style=flat-square">
  <img src="https://img.shields.io/badge/延迟-0.6ms_avg-brightgreen?style=flat-square">
  <img src="https://img.shields.io/badge/测试-279%2F279_PASS-success?style=flat-square">
</p>

<p>
  <a href="../README.md">English</a> ·
  <strong>简体中文</strong>
</p>

</div>

> **MCP 标准化 Agent↔Tool，ACP 标准化 Agent↔Agent。**  
> P2P · 零服务器 · curl 可接入 · 兼容任意 LLM 框架

---

```bash
$ # Agent A — 获取你的链接
$ python3 acp_relay.py --name AgentA
✅ 就绪。你的链接：acp://1.2.3.4:7801/tok_xxxxx
           把这个链接发给任意其他 Agent 即可连接。

$ # Agent B — 一个 API 调用完成连接
$ curl -X POST http://localhost:7901/peers/connect \
       -d '{"link":"acp://1.2.3.4:7801/tok_xxxxx"}'
{"ok":true,"peer_id":"peer_001"}

$ # Agent B — 发送消息
$ curl -X POST http://localhost:7901/message:send \
       -d '{"role":"agent","parts":[{"type":"text","content":"你好 AgentA！"}]}'
{"ok":true,"message_id":"msg_abc123","peer_id":"peer_001"}

$ # Agent A — 实时接收消息（SSE 流）
$ curl http://localhost:7901/stream
event: acp.message
data: {"from":"AgentB","parts":[{"type":"text","content":"你好 AgentA！"}]}
```

---

## 快速开始

### 方式 A — AI Agent 原生接入（两步，零配置）

```
# 第一步：把这个 URL 发给 Agent A（任意基于 LLM 的 Agent）
https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/SKILL.md

# Agent A 自动安装、启动，并回复：
# ✅ 就绪。你的链接：acp://1.2.3.4:7801/tok_xxxxx

# 第二步：把那个 acp:// 链接发给 Agent B
# 两个 Agent 现已直连。完成。
```

### 方式 B — 手动 / 脚本

```bash
# 安装依赖
pip install websockets

# 启动 Agent A
python3 relay/acp_relay.py --name AgentA
# → ✅ 就绪。你的链接：acp://你的IP:7801/tok_xxxxx

# 另一个终端 — Agent B 连接
python3 relay/acp_relay.py --name AgentB \
  --join acp://你的IP:7801/tok_xxxxx
# → ✅ 已连接到 AgentA
```

### 方式 C — Docker

```bash
docker run -p 7801:7801 -p 7901:7901 \
  ghcr.io/kickflip73/agent-communication-protocol/acp-relay \
  --name MyAgent
```

---

## 网络受限（沙箱 / K8s / 内网）？

ACP v1.4 内置三级自动连接策略，**用户零感知**：

```
Level 1 — 直连（有公网 IP 或同一局域网）
   ↓ 3 秒内失败
Level 2 — UDP 打洞（v1.4 新增，双方都在 NAT 后面）
           DCUtR 风格：STUN 地址发现 → Relay 信令交换 → 同步探测
           支持约 70% 的真实 NAT 类型（全锥型、端口受限型）
   ↓ 失败
Level 3 — Relay 降级（对称 NAT / CGNAT，约 30% 场景）
           Cloudflare Worker 中继，无状态，不存储消息内容
```

SSE 事件实时反映当前连接层级：`dcutr_started` → `dcutr_connected` / `relay_fallback`。  
`GET /status` 返回 `connection_type`：`p2p_direct` | `dcutr_direct` | `relay`。

如需显式走 Relay（如旧版本兼容），可加 `--relay` 参数启动，得到 `acp+wss://` 链接。

→ **详见 [NAT 穿透与网络接入指南](nat-traversal.md)**

---

## 通信架构

### 握手流程（人只参与前两步）

```
  人类
    │
    ├─[① Skill URL]──────────────► Agent A
    │                                  │  pip install websockets
    │                                  │  python3 acp_relay.py --name A
    │                                  │  → 监听 :7801/:7901
    │◄────────────[② acp://IP:7801/tok_xxx]─┘
    │
    ├─[③ acp://IP:7801/tok_xxx]──► Agent B
    │                                  │  POST /connect {"link":"acp://..."}
    │                                  │
    │          ┌────────── WebSocket 握手 ────────────┐
    │          │  B → A : connect(tok_xxx)            │
    │          │  A → B : AgentCard 交换              │
    │          │  A, B  : 已连接 ✅                   │
    │          └──────────────────────────────────────┘
    │
   完成                ↕ P2P 消息直接流转
```

### P2P 直连模式（默认）

```
  机器 A                                             机器 B
┌─────────────────────────────┐    ┌─────────────────────────────┐
│  ┌─────────────────────┐    │    │    ┌─────────────────────┐  │
│  │    宿主程序 A        │    │    │    │    宿主程序 B        │  │
│  │  (LLM / 脚本)        │    │    │    │  (LLM / 脚本)        │  │
│  └──────────┬──────────┘    │    │    └──────────┬──────────┘  │
│             │ HTTP          │    │               │ HTTP         │
│  ┌──────────▼──────────┐    │    │    ┌──────────▼──────────┐  │
│  │   acp_relay.py      │    │    │    │   acp_relay.py      │  │
│  │  :7901  HTTP API    │◄───┼────┼────┤  POST /message:send │  │
│  │  :7901/stream (SSE) │────┼────┼───►│  GET /stream (SSE)  │  │
│  │  :7801  WebSocket   │◄═══╪════╪═══►│  :7801  WebSocket   │  │
│  └─────────────────────┘    │    │    └─────────────────────┘  │
└─────────────────────────────┘    └─────────────────────────────┘
                         互联网 / 局域网（无需中继服务器）
```

| 通道 | 端口 | 方向 | 用途 |
|------|------|------|------|
| **WebSocket** | `:7801` | Agent ↔ Agent | P2P 数据通道，消息直达对端，无中间节点 |
| **HTTP API** | `:7901` | 宿主程序 → Agent | 发消息、管理任务、查询状态 |
| **SSE** | `:7901/stream` | Agent → 宿主程序 | 实时推送收到的消息，长连接，无需轮询 |

**宿主程序接入示例（3 行代码）：**

```python
# 发消息给对端 Agent
requests.post("http://localhost:7901/message:send",
              json={"role":"agent","parts":[{"type":"text","content":"你好"}]})

# 实时监听收到的消息（SSE 长连接）
for event in sseclient.SSEClient("http://localhost:7901/stream"):
    print(event.data)   # {"type":"message","from":"AgentB",...}
```

### 完整连接策略（v1.4，自动选择，用户零感知）

```
┌─────────────────────────────────────────────────────────────────┐
│                     三级连接策略                                  │
│                                                                 │
│  Level 1 — 直连（最优）                                           │
│  ┌────────────┐                         ┌────────────┐          │
│  │  Agent A   │◄══════ WS 直连 ════════►│  Agent B   │          │
│  └────────────┘     (公网 IP / 局域网)   └────────────┘          │
│                                                                 │
│  Level 2 — UDP 打洞（v1.4，双方在 NAT 后面）                      │
│  ┌────────────┐   ┌────────────┐        ┌────────────┐          │
│  │  Agent A   │──►│  Signaling │◄───────│  Agent B   │          │
│  │  (NAT)     │   │ (地址交换)  │        │  (NAT)     │          │
│  └────────────┘   └────────────┘        └────────────┘          │
│        │          握手后退出                  │                   │
│        └──────────── WS 直连 ───────────────┘                   │
│                    （打洞成功，真 P2P）                            │
│                                                                 │
│  Level 3 — Relay 降级（约 30% 对称 NAT 场景）                    │
│  ┌────────────┐   ┌─────────────┐       ┌────────────┐          │
│  │  Agent A   │◄─►│  Relay      │◄─────►│  Agent B   │          │
│  └────────────┘   │ (无状态)    │       └────────────┘          │
│                   └─────────────┘                               │
│                   仅转发帧，不存储消息内容                         │
└─────────────────────────────────────────────────────────────────┘
```

> **Signaling Server** 只做一次性地址交换（TTL 30s），不转发任何消息帧，握手后立即退出。  
> **Relay** 是真正的最后兜底，不是主路径——对称 NAT 等少数场景才会触发。

---

## 为什么选 ACP

| | A2A (Google) | ACP |
|---|---|---|
| **接入成本** | OAuth 2.0 + Agent 注册中心 + 推送端点 | 一个 URL |
| **是否需要服务器** | 需要（你必须自己搭建 HTTPS 端点）| **不需要** |
| **框架绑定** | 是 | **任意 Agent，任意语言** |
| **NAT / 防火墙** | 自己解决 | **自动：直连 → 打洞 → Relay** |
| **消息延迟** | 取决于你的基础设施 | **0.6ms 均值（P99 2.8ms）** |
| **最小依赖** | 重量级 SDK | **`pip install websockets`** |
| **身份认证** | OAuth token | **Ed25519 + did:acp: DID + CA 混合（v1.5）** |
| **可用性信令** | ❌（issue #1667 仍是提案）| **✅ `availability` 字段（v1.2）** |
| **Agent 身份证明** | ❌（issue #1672，44 条评论，仍在讨论）| **✅ 混合模型：`did:acp:` 自主权 + CA 证书（v1.5）** |

> A2A [#1672](https://github.com/a2aproject/A2A/issues/1672) 在 44 条评论后正在收敛到"混合身份模型"——ACP v1.5 今天就能用。

### 性能数据

- **0.6ms** 均值发送延迟 · **2.8ms** P99
- **1,100+ req/s** 顺序吞吐 · **1,200+ req/s** 并发（10 线程）
- **< 50ms** SSE 推送延迟（threading.Event，非轮询）
- **279/279 单元 + 集成测试通过**（错误处理 · 压力测试 · NAT 穿透 · 环形流水线 · transport_modes）
- **184+ commits** · **3,300+ 行** · **零已知 P0/P1 Bug**

---

## API 速查

| 功能 | 方法 | 路径 |
|------|------|------|
| 获取本机链接 | GET | `/link` |
| 主动连接对方 | POST | `/peers/connect` `{"link":"acp://..."}` |
| 发消息 | POST | `/message:send` `{"role":"agent","parts":[...]}` |
| 实时收消息 | GET | `/stream`（SSE） |
| 离线轮询收件箱 | GET | `/recv` |
| 查状态 | GET | `/status` |
| 查已连接 Peer | GET | `/peers` |
| AgentCard | GET | `/.well-known/acp.json` |
| 更新可用性 | PATCH | `/.well-known/acp.json` |
| 创建任务 | POST | `/tasks` |
| 更新任务 | POST | `/tasks/{id}:update` |
| 取消任务 | POST | `/tasks/{id}:cancel` |

HTTP 默认端口：`7901` · WebSocket 端口：`7801`

---

## 可选特性

| 特性 | 参数 | 说明 |
|------|------|------|
| 公共中继（网络受限时） | `--relay` | 返回 `acp+wss://` 格式链接 |
| HMAC 消息签名 | `--secret <key>` | 两端共享密钥，无需额外依赖 |
| Ed25519 身份 | `--identity` | 需 `pip install cryptography` |
| mDNS 局域网发现 | `--advertise-mdns` | 无需 zeroconf 库 |
| **路由拓扑声明（v2.4）** | `--transport-modes p2p,relay` | AgentCard 顶层 `transport_modes` 字段；声明本节点支持的路由模式（`p2p` 直连 / `relay` 中继）；缺省为 `["p2p", "relay"]` |
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

## Heartbeat / Cron Agent

ACP 原生支持**离线 Agent**（定时唤醒的 cron 型 Agent），无需长连接轮询。

### 工作方式

```
Cron Agent 每 5 分钟唤醒一次：
1. 启动 acp_relay.py（得到 acp:// 链接）
2. PATCH /.well-known/acp.json 更新可用性（告知对端什么时候能回消息）
3. GET /recv 收取积压消息，批量处理
4. POST /message:send 回复
5. 退出（relay 自动关闭）
```

```python
# Python — cron agent 模板
import subprocess, time, requests

relay = subprocess.Popen(["python3", "relay/acp_relay.py", "--name", "MyCronAgent"])
time.sleep(1)  # 等待启动

BASE = "http://localhost:7901"

# 广播可用性
requests.patch(f"{BASE}/.well-known/acp.json", json={
    "availability": {
        "mode": "cron",
        "last_active_at": "2026-03-24T10:00:00Z",
        "next_active_at": "2026-03-24T10:05:00Z",
        "task_latency_max_seconds": 300,
    }
})

# 收取并处理消息
msgs = requests.get(f"{BASE}/recv?limit=100").json()["messages"]
for m in msgs:
    text = m["parts"][0]["content"]
    requests.post(f"{BASE}/message:send",
                  json={"role":"agent","parts":[{"type":"text","content":f"已处理：{text}"}]})

relay.terminate()
```

> **为什么重要：** A2A [#1667](https://github.com/a2aproject/A2A/issues/1667) 仍在讨论 heartbeat agent 支持（尚是提案）——ACP `/recv` 天然解决，今天就能用。

---

## Agent 身份认证（v1.5）

ACP 支持**两种身份模型**，可单独使用或组合（混合模型）：

| 模式 | 启动参数 | `capabilities.identity` | 说明 |
|------|----------|--------------------------|------|
| 无身份 | _(默认)_ | `"none"` | 向后兼容 v0.7 |
| 自主权身份 | `--identity` | `"ed25519"` | Ed25519 签名 + `did:acp:` DID |
| **混合模型** | `--identity --ca-cert` | `"ed25519+ca"` | 自主权 + CA 签发证书 |

```bash
# 自主权身份 (v0.8+)
python3 relay/acp_relay.py --name MyAgent --identity

# 混合身份 (v1.5) — CA 证书文件
python3 relay/acp_relay.py --name MyAgent --identity --ca-cert /path/to/agent.crt

# 混合身份 (v1.5) — 内联 PEM
python3 relay/acp_relay.py --name MyAgent --identity \
  --ca-cert "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----"
```

**AgentCard 示例（混合模式）：**
```json
{
  "identity": {
    "scheme":     "ed25519+ca",
    "public_key": "<base64url 编码的 Ed25519 公钥>",
    "did":        "did:acp:<base64url(pubkey)>",
    "ca_cert":    "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----"
  },
  "capabilities": {
    "identity": "ed25519+ca"
  }
}
```

**验证策略**（验证方自选）：
- 仅信任 `did:acp:` — 验证 Ed25519 签名，忽略 `ca_cert`
- 仅信任 CA — 验证证书链，忽略 DID
- 两者都要 — 最高安全
- 任一即可 — 最高互操作性

> **为什么重要：** A2A [#1672](https://github.com/a2aproject/A2A/issues/1672)（44 条评论，仍在讨论）正收敛到同一「混合模型」结论——ACP v1.5 今天就能用。

---

## 多语言 SDK

| 语言 | 路径 | 说明 |
|------|------|------|
| **Python** | `sdk/python/` | `RelayClient` 类 |
| **Node.js** | `sdk/node/` | 零外部依赖，含 TypeScript 类型 |
| **Go** | `sdk/go/` | 零外部依赖，Go 1.21+ |
| **Rust** | `sdk/rust/` | v1.3，reqwest + serde |
| **Java** | `sdk/java/` | 零外部依赖，JDK 11+，含 Spring Boot 集成示例 |

---

## 版本历史

| 版本 | 状态 | 重点 |
|------|------|------|
| v0.1–v0.5 | ✅ | P2P 核心、Task 状态机、消息幂等 |
| v0.6 | ✅ | 多 Peer 注册、标准错误码 |
| v0.7 | ✅ | HMAC 签名、mDNS 发现 |
| v0.8–v0.9 | ✅ | Ed25519 身份、Node.js SDK、兼容性测试套件 |
| v1.0 | ✅ | 生产稳定、安全审计、Go SDK |
| v1.1 | ✅ | HMAC replay-window、`failed_message_id` |
| v1.2 | ✅ | 调度元数据（`availability`）、Docker 镜像 |
| v1.3 | ✅ | Rust SDK、DID 身份（`did:acp:`）、Extension 机制、GHCR CI |
| **v1.4** | ✅ **已实现** | **真 P2P NAT 穿透**：UDP 打洞（DCUtR 风格）+ Signaling，三级自动降级 |
| **v1.5** | ✅ **已实现** | **混合身份模型**：`--ca-cert` 在 `did:acp:` 自主权基础上叠加 CA 证书 |
| v1.6–v1.9 | ✅ | HTTP/2 传输（h2c）、AgentCard 自签名（v1.8）、握手时双向自动验证（v1.9） |
| v2.0–v2.1 | ✅ | 离线消息队列、LAN 发现（`GET /peers/discover`） |
| v2.2 | ✅ | `GET /tasks` 列表查询 + 游标分页 |
| v2.3 | ✅ | Python SDK `auto_stream` 参数（自动选 SSE 接收）、`supported_transports` 能力声明 |
| **v2.4** | ✅ **当前版本** | **`transport_modes` 顶层字段**：路由拓扑声明（`p2p`/`relay`）；`--transport-modes` CLI 标志；spec §5.4 |

---

## 仓库结构

```
agent-communication-protocol/
├── SKILL.md              ← 发这个 URL 给 Agent 即可接入
├── relay/
│   └── acp_relay.py      ← 核心守护进程（单文件，stdlib 优先）
├── spec/                 ← 协议规范文档
├── sdk/                  ← Python / Node.js / Go / Rust / Java SDK
├── tests/                ← 兼容性 + 集成测试套件
├── docs/                 ← 中文文档、合规指南、博客草稿
└── acp-research/         ← 竞品情报、ROADMAP
```

---

## 贡献

欢迎贡献！详见 [CONTRIBUTING.zh.md](../CONTRIBUTING.zh.md)。

- Bug 报告 & 功能请求 → [GitHub Issues](https://github.com/Kickflip73/agent-communication-protocol/issues)
- 协议设计讨论 → [GitHub Discussions](https://github.com/Kickflip73/agent-communication-protocol/discussions)

---

## 许可证

[Apache License 2.0](../LICENSE)

---

<div align="center">
<sub>MCP 标准化 Agent↔Tool，ACP 标准化 Agent↔Agent。P2P · 零服务器 · curl 可接入。</sub>
</div>
