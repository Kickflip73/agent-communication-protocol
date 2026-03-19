# ACP 协议研发路线图

> 持续更新。贾维斯每周自动扫描竞品动态，每月产出一个新版本。
> 最后更新：2026-03-19

---

## 竞品生态现状（2026-03-19）

| 协议 | Stars | 最新版本 | 活跃度 | 核心优势 |
|------|-------|---------|--------|---------|
| **A2A** (Google) | 22,643 | v1.0.0 (2026-03-12) | ⚡ 极高 | Task 生命周期、企业级认证 |
| **ANP** (社区) | 1,240 | - (2026-03-05) | 🟡 中 | DID 去中心化身份、元协议自协商 |
| **IBM ACP** | 966 | - (2025-08-25) | 🔴 低 | MIME 多模态消息 |
| **MCP** (Anthropic) | - | v1.0 | ✅ 稳定 | 工具调用（不同赛道） |
| **我们的 ACP** | 1 | v0.4 (2026-03-18) | 🟢 建设中 | P2P 无服务器、Skill 驱动零配置 |

---

## 差距分析 & 优先借鉴项

### 🔴 A2A v1.0 新特性（必须跟进）

A2A 在 v1.0 做的重要变更，我们需要评估是否借鉴：

1. **`extendedAgentCard` 迁移到 `AgentCapabilities`** — 能力声明结构更清晰
2. **Task Push Notification 统一** — 长任务异步通知机制
3. **OAuth 2.0 现代化** — 移除 implicit/password 流，加 PKCE/device code
4. **ProtoJSON 对齐 (ADR-001)** — enum 格式规范化
5. **`QuerySkill()` 运行时能力查询** (Issue #1655，待合并) — 动态发现

### 🟡 ANP 值得借鉴项

1. **DID 去中心化身份** — 不依赖中心注册表的 Agent 身份
2. **元协议协商** — 两个 Agent 动态协商用什么格式通信
3. **idempotency + server_seq 排序** (2026-03-05) — 消息去重和有序性

---

## 版本路线图

### ✅ v0.4（已完成，2026-03-18）
- AgentCard 能力声明（参考 A2A）
- P2P Relay 直连
- SSE 流式端点
- 安全加固（Unbounded Consumption 防护）

### 🎯 v0.5（目标：2026-03-26）
**主题：Task 生命周期 + 能力发现 + 消息幂等**

借鉴来源：A2A v1.0 深度研究（2026-03-19）

- [ ] **Task 状态机**：8 种状态完整实现
  - 终态：`completed / failed / canceled / rejected`
  - 中断态：`input_required / auth_required`（可恢复，不等于失败）
  - 中间态：`submitted / working`
- [ ] **结构化 SSE 事件**：区分两种事件类型
  - `statusUpdate`：任务状态变更
  - `artifactUpdate`：增量内容输出
  - 替换现有的原始文本流
- [ ] **消息幂等性**：`message_id`（客户端生成）+ 服务端去重
  - 参考 A2A Message.message_id + ANP server_seq
- [ ] **AgentCard 能力声明**：`GET /.well-known/agent.json`
  - 包含：name/version/skills/capabilities/supportedInterfaces
  - capabilities: `streaming / pushNotifications / extendedCard`

### 🔮 v0.6（目标：2026-04-09）
**主题：多模态 Part + 异步 Webhook + 错误体系**

借鉴来源：A2A Part 模型 + A2A Push Notification

- [ ] **多模态 Part**：4 种类型
  - `text`：纯文本
  - `url`：文件 URL 引用（轻量，不传原始字节）
  - `bytes`：原始字节（base64，适合小文件）
  - `data`：任意 JSON 结构化数据
  - 每个 Part 携带 `media_type` (MIME) + `filename`
- [ ] **Webhook 回调**：长任务完成后主动推送
  - 客户端请求时配置 webhook URL + token
  - 服务端任务终态时 POST 通知
- [ ] **错误码规范化**：建立 ACP 错误体系（参考 A2A 8 种错误类型）
- [ ] **`return_immediately` 参数**：解耦短任务和长任务处理模式
- [ ] **多会话支持**：一个 Relay 实例管理多个并发会话

### 🔮 v1.0（目标：2026-05）
**主题：去中心化身份 + Extension 机制 + 三层架构**

借鉴来源：ANP（DID）+ A2A（Extension）

- [ ] **Extension 机制**：URI 标识的可扩展能力
  - `required: true/false` 控制强制/可选
  - 版本不兼容时用新 URI，不做静默降级
- [ ] **DID 身份**：`did:acp:<namespace>:<name>` 格式
  - 无需中心注册，本地/组织/全局三级
- [ ] **能力发现网络**：Agent 可以广播自己、搜索其他 Agent
- [ ] **规范重构**：按三层架构（数据模型/操作/绑定）重写 spec 文档
- [ ] **元协议协商**：两个 Agent 建立连接时自动协商通信格式

---

## 我们的差异化定位

**不做 A2A 的复制品。** 我们的核心差异：

| 维度 | A2A | 我们的 ACP |
|------|-----|-----------|
| 部署 | 需要服务端 | **P2P 零服务器** |
| 接入 | 需改代码/配置 | **Skill 驱动，发一个链接即可接入** |
| 复杂度 | 企业级，重量级 | **轻量级，个人/小团队友好** |
| 认证 | OAuth 2.0 | **渐进式：无认证 → 简单 token → DID** |
| 定位 | Agent 之间的 HTTP | **Agent 之间的 WhatsApp** |

---

## 研究信息源（贾维斯每周自动扫描）

```
A2A:  https://github.com/a2aproject/A2A
ANP:  https://github.com/agent-network-protocol/AgentNetworkProtocol
IBM:  https://github.com/i-am-bee/acp
MCP:  https://github.com/modelcontextprotocol/specification
```
