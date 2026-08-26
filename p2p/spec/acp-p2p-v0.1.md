# ACP-P2P Protocol Specification v0.1

## 核心设计原则

1. **零中心化**：任意两个 Agent 之间无需任何第三方服务器
2. **URI 即身份**：一个 `acp://` URI 包含连接所需的全部信息
3. **带外信令**：连接信息可通过任何渠道交换（消息、二维码、配置文件、环境变量）
4. **传输无关**：底层可以是 HTTP、WebSocket、Unix Socket、甚至 stdin/stdout

---

## ACP URI 格式

```
acp://<host>:<port>/<agent-name>?key=<pubkey_b64>&caps=<cap1,cap2>
```

示例：
```
acp://192.168.1.42:7700/summarizer?key=Ed25519_abc123&caps=summarize,translate
acp://localhost:7700/worker-a
acp://agent.example.com:7700/orchestrator?caps=delegate,coordinate
```

### URI 字段说明

| 字段 | 必须 | 说明 |
|------|------|------|
| host | ✅ | IP 或域名（localhost / LAN IP / 公网 IP / 域名） |
| port | ✅ | Agent HTTP 监听端口（默认 7700） |
| agent-name | ✅ | Agent 唯一名称（path 部分） |
| key | ❌ | Ed25519 公钥（v0.1 可选，v0.4 强制） |
| caps | ❌ | 能力列表，逗号分隔 |

---

## 消息格式（与 ACP 核心规范兼容）

```json
{
  "acp": "0.1",
  "id": "msg_<random>",
  "type": "task.delegate",
  "from": "acp://192.168.1.10:7700/orchestrator",
  "to":   "acp://192.168.1.42:7700/summarizer",
  "ts": "2026-03-18T10:00:00Z",
  "body": {
    "task": "Summarize this article",
    "input": { "text": "..." }
  }
}
```

`from` 和 `to` 字段直接使用 ACP URI，无需注册中心解析。

---

## 点对点通信流程

### Phase 1：发现（Discovery）

Agent 获取对方 URI 的方式（任选其一）：

```
A. 直接配置  ── 环境变量 / 配置文件 / 命令行参数
B. 带外交换  ── 把 URI 复制粘贴给对方（IM 消息、邮件）
C. 二维码    ── URI 编码为二维码，扫码建立连接
D. mDNS     ── 局域网内自动广播发现（zeroconf）
E. 共享文件  ── 把 URI 写入共享 NFS / S3 / Git 仓库
```

### Phase 2：握手（可选）

发送方在正式消息前，可先发送 `agent.hello`：

```
POST http://<target-host>:<port>/acp/v1/receive
Body: { "acp":"0.1", "type":"agent.hello", "from":"<my-uri>", ... }
```

接收方回应自己的 `agent.hello`，双方互知对方能力。

### Phase 3：直连通信

```
发送方                              接收方
  │                                    │
  │  POST /acp/v1/receive              │
  │  Body: ACPMessage(task.delegate)   │
  │ ─────────────────────────────────► │
  │                                    │  处理任务
  │  200 OK                            │
  │  Body: ACPMessage(task.result)     │
  │ ◄───────────────────────────────── │
```

或异步模式：
```
发送方                              接收方
  │  POST /acp/v1/receive              │
  │ ─────────────────────────────────► │
  │  202 Accepted                      │
  │ ◄───────────────────────────────── │
  │                                    │  处理中...
  │  POST /acp/v1/receive              │
  │  Body: ACPMessage(task.result)     │ (回调到发送方)
  │ ◄───────────────────────────────── │
```

---

## Agent 必须暴露的最小接口

```
POST /acp/v1/receive          ← 接收消息（必须）
GET  /acp/v1/identity         ← 返回自己的 ACP URI 和能力（推荐）
GET  /acp/v1/health           ← 存活检查（推荐）
```

### `/acp/v1/identity` 响应示例

```json
{
  "uri": "acp://192.168.1.42:7700/summarizer",
  "name": "Summarizer Agent",
  "capabilities": ["summarize", "translate"],
  "acp_version": "0.1"
}
```

---

## 跨网络穿透方案

当两个 Agent 不在同一局域网时：

| 方案 | 适用场景 | 操作 |
|------|---------|------|
| 公网 IP + 端口 | 服务器部署 | 直接使用公网 IP |
| ngrok | 开发调试 | `ngrok http 7700` → 得到公网 URI |
| frp / nps | 自建穿透 | 配置内网穿透 |
| Tailscale | 团队内网 | 安装后直接用 Tailscale IP |
| CloudFlare Tunnel | 生产环境 | 零开放端口，安全 |

---

## 安全模型（v0.1 基础）

- **v0.1**：URI 中可携带预共享密钥（PSK）用于简单认证
- **v0.4**：Ed25519 签名，消息不可伪造
- **传输层**：生产环境推荐使用 HTTPS（TLS）

### v0.1 PSK 认证

发送方在请求头中携带密钥：
```
X-ACP-PSK: <shared_secret>
```

接收方校验，不匹配则返回 401。

---

## 与 ACP Gateway 模式对比

| 维度 | ACP Gateway（中心化） | ACP-P2P（去中心化） |
|------|----------------------|---------------------|
| 依赖 | 需要 Gateway 服务 | 零依赖 |
| 发现 | 注册中心 | URI 带外交换 |
| 延迟 | 多一跳 | 最低延迟 |
| 适用 | 动态 Agent 池 | 已知拓扑 |
| 离线能力 | 依赖 Gateway | 完全离线可用 |
| 部署复杂度 | 需运维 Gateway | 无需运维 |

两种模式**互补而非替代**：固定拓扑用 P2P，动态发现用 Gateway。
