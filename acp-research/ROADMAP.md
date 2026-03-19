# ACP 协议研发路线图

> 持续更新。贾维斯每周自动扫描竞品动态，每月产出一个新版本。
> 最后更新：2026-03-19 14:44（新增 GitHub Issues Relay 传输层）

---

## 战略定位（2026-03-19 Stark 先生确认）

### 四大核心特性方向

| 特性 | 含义 | 设计原则 |
|------|------|---------|
| **① 轻量级，简单开箱即用** | 最小化接入成本，无需学习曲线 | 单文件 Skill，一个命令即运行，JSON over HTTP/SSE |
| **② P2P 无中间人** | Agent 直连，不经过任何第三方服务器 | Relay 只做连接打洞，消息直通，无持久化 |
| **③ 实用性，解决任意 Agent 通信** | 不限框架、不限平台、不限语言 | 协议最小集 + 渐进扩展，curl 可接入 |
| **④ 差异化：面向个人和团队** | 对标 A2A 企业级，我们做个人/小团队场景 | 零运维、零注册、即用即走 |
| **⑤ 标准化** | 像 MCP 标准化了 Agent↔Tool，ACP 标准化 Agent↔Agent | 开放规范，任意实现可互通 |

### 定位口号（内部）
> **MCP 标准化了 Agent 与 Tool 的通信，ACP 标准化 Agent 与 Agent 的通信。**
> A2A = 企业工厂流水线调度；ACP = 两个 Agent 之间发消息，人人可用，框架无关。

### 对 A2A 的态度
- **借鉴概念，不复制复杂度**
- Task 状态机：借鉴状态分类的思路，但大幅简化（5 种而非 8 种）
- AgentCard：借鉴能力声明理念，但保持极简结构
- Extension：借鉴 URI 标识思路，但不强制
- **不借鉴**：OAuth 2.0、gRPC 绑定、多租户、Push Notification 配置管理 CRUD

---

## 竞品生态现状（2026-03-19）

| 协议 | Stars | 活跃度 | 定位 | 我们的态度 |
|------|-------|--------|------|-----------|
| **A2A** (Google) | 22,643 | ⚡ 极高 | 企业级 Agent 总线 | 借鉴概念，不做复制 |
| **ANP** (社区) | 1,240 | 🟡 中 | 去中心化身份 | 借鉴 DID 思路（长期） |
| **IBM ACP** | 966 | 🔴 停更 | 多模态消息 | 参考即可 |
| **MCP** (Anthropic) | - | ✅ 稳定 | 工具调用 | 不同赛道，可互补 |

---

## 版本路线图

### ✅ v0.4（已完成，2026-03-18）
- P2P Relay 直连（本地守护进程）
- SSE 流式端点
- AgentCard 能力声明（基础版）
- 安全加固（Unbounded Consumption 防护）

---

### 🎯 v0.5（目标：2026-03-26）
**主题：消息结构化 + 任务追踪（轻量版）**

设计原则：借鉴 A2A 概念，但砍掉所有非必要复杂度。

#### Task 状态机（5 种，而非 A2A 的 8 种）

```
submitted → working → completed
                   → failed
                   → input_required  ← 可继续
```

| 状态 | 含义 | 备注 |
|------|------|------|
| `submitted` | 已提交 | 中间态 |
| `working` | 处理中 | 中间态 |
| `completed` | 完成 | 终态 |
| `failed` | 失败 | 终态 |
| `input_required` | 等待追加输入 | 中断态，可继续 |

> 砍掉 `canceled`、`rejected`、`auth_required`——对个人/团队场景过度设计。
> 需要取消？直接断连接。需要认证？连接建立时一次性搞定。

#### 结构化消息（Part 模型，精简版）

```json
{
  "message_id": "client-generated-uuid",
  "role": "user | agent",
  "parts": [
    {"type": "text", "content": "你好"},
    {"type": "file", "url": "https://...", "media_type": "image/png"},
    {"type": "data", "content": {...}}
  ]
}
```

> 3 种 Part 类型（text / file / data），去掉 A2A 的 `bytes`（raw）——URL 引用更轻量，不传原始字节。

#### 消息幂等性
- `message_id` 客户端生成（UUID）
- 服务端在同一 session 内去重

#### Artifact（任务输出产物）
```json
{
  "artifact_id": "uuid",
  "name": "分析报告",
  "parts": [...]
}
```

- 任务完成后通过 `artifactUpdate` 事件推送
- 区分「对话消息」和「任务产物」

#### 结构化 SSE 事件（2 种）
```
data: {"type": "status", "task_id": "x", "state": "working"}
data: {"type": "artifact", "task_id": "x", "artifact": {...}}
data: {"type": "message", "role": "agent", "parts": [...]}
```

---

### 🔮 v0.6（目标：2026-04-09）
**主题：零配置接入 + 跨平台互通**

设计原则：让任意 Agent（不限框架）都能 2 步接入。

- [ ] **标准接入协议**：任意 HTTP 服务只需实现 3 个端点即可接入 ACP
  - `GET /.well-known/acp.json` — AgentCard（我是谁，我能做什么）
  - `POST /connect` — 发起连接（返回 session_id）
  - `GET /stream/{session_id}` — SSE 消息流
- [ ] **Relay 升级**：支持多并发 session，独立超时管理
- [ ] **错误码规范**：建立 ACP 错误体系（精简版，约 6 种）
- [ ] **Python / Node SDK**：让接入从「3 个端点」变成「import + 3 行代码」

---

### 🔮 v0.7（目标：2026-04-23）
**主题：能力发现 + 多轮对话**

- [ ] **能力发现**：本地局域网内 Agent 互相发现（mDNS / 广播）
- [ ] **contextId 多轮对话**：跨 Task 的上下文延续
  - `context_id` 关联多个 Task，支持追加输入
- [ ] **AgentCard 签名**：防伪造（基础版，不用 DID，用 HMAC）

---

### 🔮 v1.0（目标：2026-05）
**主题：生产可用 + 生态建设**

- [ ] **规范文档发布**：清晰的三层架构文档（数据模型/操作语义/绑定）
- [ ] **兼容性测试套件**：自动验证任意实现是否符合 ACP 规范
- [ ] **参考实现**：Python + Node 各一套，可作为 Agent 框架集成的标准插件
- [ ] **DID 身份（可选）**：`did:acp:` 格式，不强制，向 ANP 靠拢
- [ ] **Extension 机制（可选）**：URI 标识的扩展，向 A2A 靠拢

---

## 核心差异化（最终版）

| 维度 | A2A（企业级） | ANP（去中心化） | **我们的 ACP（个人/团队）** |
|------|-------------|--------------|------------------------|
| 部署 | 需要服务端运维 | 需要 DID 基础设施 | **零服务器，本地 Skill 即可** |
| 接入 | 改代码 + 配置 + 注册 | 需要 DID 注册 | **发一个链接，对方粘贴即连** |
| 复杂度 | 企业级，11 个端点 | 协议协商复杂 | **3 个端点，curl 可接入** |
| 认证 | OAuth 2.0 全套 | DID + 签名 | **连接时 token，可选** |
| 数据 | 经过服务器 | 经过 DID 节点 | **真 P2P，Relay 不存消息** |
| 场景 | 企业内系统集成 | 去中心化网络 | **个人 Agent、小团队、临时协作** |
| 类比 | 企业 ERP 之间的 ESB | 区块链上的通信 | **两个人发微信** |

---

## 研究信息源（贾维斯每周自动扫描）

```
A2A:  https://github.com/a2aproject/A2A
ANP:  https://github.com/agent-network-protocol/AgentNetworkProtocol
IBM:  https://github.com/i-am-bee/acp
MCP:  https://github.com/modelcontextprotocol/specification
```

---

## 传输层架构（2026-03-19 新增）

**核心设计原则：会话层不感知传输层。** 两种传输对外 API 完全相同。

```
会话层（不感知传输）
    ├── POST /message:send
    ├── GET  /recv
    ├── GET  /status
    └── GET  /link
         ↓ 透明路由
    ├── 传输 A：WebSocket P2P（acp_relay.py）
    │     链接格式：acp://IP:PORT/TOKEN
    │     延迟：<100ms | 适用：双方 IP 互通
    │     优势：实时全双工
    │     限制：沙箱/NAT 环境可能不通
    │
    └── 传输 B：GitHub Issues 轮询（acp_github_relay.py）★ 2026-03-19
          链接格式：acp+gh://OWNER/REPO/ISSUE_NUM
          延迟：~3s（轮询间隔可调）| 适用：任何能访问 GitHub API 的环境
          优势：无需部署、全球可达、GitHub SLA 99.9%+
          限制：需要双方有 GitHub token (repo scope)；延迟较高
```

**自动降级策略（v0.7 规划）**：
1. 尝试 P2P 直连（WebSocket）
2. 若连接超时（10s），自动降级到 GitHub Issues Relay
3. 对话层无感知，仅链接格式从 `acp://` 变为 `acp+gh://`

**未来可扩展传输**：
- `acp+redis://` — Redis Pub/Sub（内网场景，延迟 <1ms）
- `acp+mqtt://` — MQTT broker（IoT 场景）
- `acp+wss://` — WebSocket over TLS（跨域沙箱，通过 HTTPS CONNECT 隧道）

---

## 设计禁忌（红线，不做）

- ❌ OAuth 2.0 / PKCE — 个人场景用不上，增加接入门槛
- ❌ 多租户架构（`/{tenant}/tasks`）— P2P 不需要
- ❌ gRPC 绑定 — 保持 JSON over HTTP，可调试
- ❌ Push Notification 配置 CRUD（4 个端点）— 用 SSE 足够
- ❌ 8 种 Task 状态 — 5 种够用，不过度设计
- ❌ 中心注册表 / 服务发现中心 — 真 P2P，不需要
