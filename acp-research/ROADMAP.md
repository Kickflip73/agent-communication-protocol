# ACP 协议研发路线图

> 持续更新。贾维斯每周自动扫描竞品动态，每月产出一个新版本。  
> 最后更新：2026-03-21 22:51（文档轮：v1.0 GA 完成，v1.1 backlog #1 交付）

---

## 战略定位（2026-03-19 Stark 先生确认）

| 特性 | 含义 | 设计原则 |
|------|------|---------|
| **① 轻量级，简单开箱即用** | 最小化接入成本，无需学习曲线 | 单文件 Skill，一个命令即运行 |
| **② P2P 无中间人** | Agent 直连，不经过任何第三方 | Relay 只做连接打洞，消息直通 |
| **③ 实用性，任意 Agent 可接入** | 不限框架、平台、语言 | curl 可接入，3 个端点最小集 |
| **④ 面向个人和团队** | 对标 A2A 企业级，做个人/小团队场景 | 零运维、零注册、即用即走 |
| **⑤ 标准化** | 像 MCP 标准化 Agent↔Tool，ACP 标准化 Agent↔Agent | 开放规范，任意实现可互通 |

> **口号：MCP 标准化了 Agent 与 Tool 的通信，ACP 标准化 Agent 与 Agent 的通信。**

---

## 竞品生态现状（2026-03-19）

| 协议 | Stars | 活跃度 | 定位 | 态度 |
|------|-------|--------|------|------|
| **A2A** (Google) | 22,643 | ⚡ 极高 | 企业级 Agent 总线 | 借鉴概念，不复制复杂度 |
| **ANP** (社区) | 1,240 | 🟡 中 | 去中心化身份 | 借鉴 DID 思路（长期） |
| **IBM ACP** | 966 | 🔴 停更 | 多模态消息 | 参考即可 |
| **MCP** (Anthropic) | - | ✅ 稳定 | 工具调用 | 不同赛道，可互补 |

---

## 版本路线图

### ✅ v0.4（完成，2026-03-18）
- P2P Relay 直连（本地守护进程）
- SSE 流式端点
- AgentCard 能力声明（基础版）
- 安全加固（Unbounded Consumption 防护）

---

### ✅ v0.5（完成，2026-03-19，提前于截止日 2026-03-26）
**主题：消息结构化 + 任务追踪**

- ✅ Task 状态机（5 种：submitted/working/completed/failed/input_required）
- ✅ 结构化消息 Part 模型（text/file/data）
- ✅ 消息幂等性（message_id 客户端生成 + server_seq 有序）
- ✅ QuerySkill() API（`POST /skills/query`）
- ✅ AgentCard 标准发现端点（`GET /.well-known/acp.json`）
- ✅ 双向 Task 同步（`spec/core-v0.5.md` §5b）

Key commit: `bb6aba3`

---

### ✅ v0.6（完成，2026-03-19）
**主题：外部 Agent 接入 + 多 session Relay + 错误码规范**

- ✅ 轻量接入规范（`spec/v0.6-minimal-agent.md`）：3 端点最小集
- ✅ 多 session peer 注册表（`/peers`, `/peer/{id}/send`, `/peers/connect`）
- ✅ 标准错误码（6 种 ERR_* 常量 + `_err()` 辅助函数，`spec/error-codes.md`）
- ✅ 自动降级策略（P2P 超时 10s → HTTP 公共中继，commit `74de528`）
- ✅ Cloudflare Worker v2（多房间并发 + KV 过期清理）
- ✅ Python mini-SDK（`sdk/python/`）

Key commit: `c816cb5`（错误码）

---

### ✅ v0.7（完成，2026-03-20）
**主题：安全扩展 + LAN 发现 + 多轮上下文**

- ✅ 可选 HMAC-SHA256 消息签名（`--secret`，`spec/transports.md` §3.x）
- ✅ mDNS LAN 对等发现（`--advertise-mdns`，UDP 224.0.0.251:5354）
- ✅ context_id 多轮对话支持
- ✅ `spec/transports.md` v0.3（§3.6 HTTP headers 分类澄清）

Key commits: `87dad51`（HMAC），`aabfae5`（mDNS），`68db641`（spec）

---

### ✅ v0.8（完成，2026-03-21）🎉
**主题：生态扩展 + 可选 Ed25519 身份**

所有 P0 目标 **全部完成**：

- ✅ **Node.js SDK**（`sdk/node/`）：零依赖，TS 类型，19 单元测试通过（commit `fd8c02a`）
- ✅ **兼容性测试套件**（`tests/compat/`）：7 个测试文件，黑盒 HTTP 验证，`ACP_BASE_URL` 参数化（commit `98197cf`）
- ✅ **Ed25519 可选身份扩展**（commit `1a13dec`）：
  - 自主权密钥对（`~/.acp/identity.json`，chmod 0600）
  - canonical JSON 签名，出站自动附加 `identity` 块
  - 入站 warn-only 验证（不丢弃），向后兼容 v0.7
  - `--identity [path]` CLI 标志
  - `spec/identity-v0.8.md` 完整规范（230 行，含 APS 对比）
- ✅ VERSION：`0.7-dev` → `0.8-dev`

Deferred to v0.9: `spec/core-v0.8.md` 综合规范文档（P2）

---

### ✅ v0.9（完成，2026-03-21）
**主题：规范整合 + 分发就绪 + 生产可用性**

- ✅ `spec/core-v0.9.md` 综合规范文档（v0.5–v0.8 统一整合）
- ✅ `role` 字段服务端强校验（缺失/非法 → 400 ERR_INVALID_REQUEST）
- ✅ `pip install acp-relay`（`pyproject.toml` + `acp-relay` CLI 入口）
- ✅ `npm install acp-relay-client`（ESM + CJS + TypeScript types）
- ✅ CLI 扩展：`--version`、`--verbose`、`--config <FILE>`（JSON/YAML，stdlib）
- ✅ 63 个单元测试（`tests/unit/`）
- ✅ 7 个兼容性测试套件（`tests/compat/`）

---

### ✅ v1.0（完成，2026-03-21）🎉 GA
**主题：生产稳定版**

- ✅ `spec/core-v1.0.md`——权威 1.0 规范
  - `[stable]` 13 个端点 · `[experimental]` 1 个（`/discover`）
  - §13：v1.0 兼容性保证（4 条 MUST 级要求）
- ✅ 安全审计（`docs/security.md`）
  - HMAC-SHA256 + Ed25519 正式审计：11 PASS · 1 PARTIAL（replay-window，v1.1 修复）
- ✅ **Go SDK**（`sdk/go/`）——stdlib only，Go 1.21+，零外部依赖，24 个测试
  - 包名：`acprelay`，8 个方法：Send/Recv/GetStatus/GetTasks/CancelTask/QuerySkills
  - `httptest.Server` 真实 HTTP round-trip 测试
- ✅ **端到端集成测试**（`tests/integration/`）——30 个测试，真实 relay 子进程
- ✅ **CHANGELOG**——完整版本历史 v0.1.0 → v1.0.0
- ✅ **README v1.0**——版本徽章、v0.9/v1.0 特性节、Go SDK 示例、集成测试说明

Key commits: `bcf6b75`（Go SDK）, `641bae6`+`81bc73c`（集成测试）, `a97b2bd`（README v1.0）

**总测试数：97（30 集成 + 63 单元 + 4 新增）**

---

### 🔧 v1.1 Backlog（持续迭代）

- ✅ `failed_message_id` 覆盖所有 /message:send 错误码（commit `e281790`，2026-03-21）
  - 灵感：ANP commit 99806f45（failed_msg_id in e2ee_error）
  - 覆盖：ERR_INVALID_REQUEST × 4 + ERR_NOT_CONNECTED + ERR_INTERNAL
- [ ] replay-window：HMAC 重放攻击防护（PARTIAL → PASS）
- [ ] Rust SDK stub
- [ ] DID 身份（`did:acp:` 格式，向 ANP 靠拢）
- [ ] HTTP/2 传输绑定
- [ ] Docker 官方镜像

### 🔮 v1.2 规划（目标：2026-Q2）
**主题：Heartbeat Agent 支持 + 生态完善**

灵感来源：A2A issue #1667（2026-03-21），A2A 协议层尚无此能力，ACP 可率先实现。

- ✅ **AgentCard `availability` 块**（P1）——heartbeat/cron 型 Agent 可用性元数据（commit `c10c230`，2026-03-22）
  - `mode`: persistent / heartbeat / cron / manual
  - `interval_seconds`: 心跳间隔（秒）
  - `next_active_at` / `last_active_at`: ISO-8601 UTC 时间戳
  - `task_latency_max_seconds`: 最大预期延迟
  - 全部可选字段，向后兼容 v1.0
- ✅ AgentCard 自动更新 API：PATCH `/.well-known/acp.json`（P2）（commit `cd67181`，2026-03-22）
- [ ] Rust SDK stub（P2）

---

### 🔮 v2.0（目标：2026-Q3）
**主题：联邦化与生态扩展**

- [ ] 公开发布（博客文章 + GitHub README + Hacker News）
- [ ] Extension 机制（URI 标识扩展，向 A2A 靠拢）
- [ ] 多语言 SDK 完整矩阵（Python/Node/Go/Rust）
- [ ] 兼容性认证流程（「如何认证你的实现」文档）

---

## 设计禁忌（红线）

- ❌ OAuth 2.0 / PKCE
- ❌ 多租户架构
- ❌ gRPC 绑定
- ❌ Push Notification 配置 CRUD
- ❌ 8 种 Task 状态（5 种够用）
- ❌ 中心注册表 / 服务发现中心

---

## 研究信息源（自动扫描）

```
A2A:  https://github.com/a2aproject/A2A
ANP:  https://github.com/agent-network-protocol/AgentNetworkProtocol
IBM:  https://github.com/i-am-bee/acp
MCP:  https://github.com/modelcontextprotocol/specification
```
