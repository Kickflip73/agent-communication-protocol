# ACP 竞品研究报告 — 2026-03-18

## 研究对象

| 协议 | 发起方 | 定位 | 状态 |
|------|--------|------|------|
| **MCP** | Anthropic | Agent ↔ Tool（工具调用） | v1.0 生产级 |
| **A2A** | Google | Agent ↔ Agent（企业级任务委托） | v1.0 生产级 |
| **ACP** | IBM BeeAgent | Agent ↔ Agent（REST 多模态消息） | 开源 Beta |
| **ANP** | 社区（华为系） | Agent 互联网（去中心化发现+通信） | 白皮书+PoC |

---

## 各协议核心机制

### MCP (Model Context Protocol)
- **传输**: stdio（本地）/ HTTP+SSE（网络）
- **消息格式**: JSON-RPC 2.0
- **核心**: 工具注册 + 调用，有 schema 约束
- **不做的**: Agent↔Agent 直接通信（这是 A2A/ACP/ANP 的领域）
- **亮点**: Agent Card 能力声明，客户端在连接前就知道对方能干什么

### A2A (Agent2Agent Protocol) — Google
- **传输**: HTTP+SSE / JSON-RPC 2.0 / gRPC（三层可插拔绑定）
- **核心数据模型**: Task（有状态工作单元）/ Message / AgentCard / Part / Artifact
- **亮点**:
  - AgentCard: JSON 元数据，声明能力、endpoint、认证需求 → 可发现性
  - Task 生命周期: submitted → working → completed/failed/cancelled
  - 流式更新: SSE 推送 task.progress
  - Push Notification: 长任务用 webhook 回调
  - 多模态 Part: text / file-ref / structured-data
- **不做的**: P2P 直连（需要服务端）；去中心化发现

### ACP (Agent Communication Protocol) — IBM
- **传输**: REST HTTP
- **消息格式**: MIME multipart（真正多模态，支持图片/音频/结构化数据混合）
- **亮点**:
  - Session 管理（有状态会话）
  - 角色系统: user / agent（与人类交互场景）
  - DID 身份（去中心化标识符）
  - 同步 + 异步双模式
- **不做的**: P2P 直连；能力发现

### ANP (Agent Network Protocol) — 社区
- **三层架构**:
  1. 身份+加密层: W3C DID + 端对端加密
  2. 元协议层: 协议协商（Agent 之间先商量用什么协议）
  3. 应用协议层: 语义 Web 能力描述（JSON-LD）
- **亮点**:
  - 真正去中心化：无需中心注册，类似 DNS 发现
  - 元协议自协商: 两个 Agent 可以动态决定用什么格式通信
  - DID 身份无需第三方
- **缺点**: 复杂，PoC 阶段，实用性待验证

---

## ACP（我们的）差距分析

### 当前状态
```
✅ P2P 直连（这是核心差异化优势，其他协议都不做）
✅ 零代码接入（Skill 驱动，Agent 自动安装）
✅ 本地 HTTP 接口（任何语言调用）
✅ Token 认证防误连
❌ 无能力声明（AgentCard）
❌ 无 Task 生命周期管理
❌ 消息仅支持纯 JSON，无多模态
❌ 无断线重连
❌ 无 NAT 穿透（双方都在内网时无法连接）
❌ 无流式传输（大任务无法推送进度）
❌ 无会话管理（每次连接独立）
❌ 无身份认证（任何人知道 token 都能连）
```

### 优先级排序（按实用价值）

| 优先级 | 功能 | 参考来源 | 复杂度 |
|--------|------|----------|--------|
| P0 | **断线自动重连** | 工程基础 | 低 |
| P0 | **消息持久化（本地队列）** | 工程基础 | 低 |
| P1 | **AgentCard 能力声明** | A2A | 低 |
| P1 | **流式消息（SSE）** | A2A/MCP | 中 |
| P1 | **多会话支持** | ACP/IBM | 中 |
| P2 | **Task 生命周期** | A2A | 中 |
| P2 | **多模态 Part** | ACP/IBM | 中 |
| P3 | **NAT 穿透（STUN/TURN）** | WebRTC | 高 |
| P3 | **DID 身份认证** | ANP/ACP | 高 |

---

## 核心差异化定位（我们应该坚守的）

**其他协议的共同问题**: 需要改代码、需要服务端、需要注册
**我们的核心优势**: `Skill 地址 → 自动安装 → 返回链接 → 粘贴即连`

**正确的演进路线**:
```
v0.1（现在）: P2P直连 + 零代码 + 本地HTTP接口
v0.2（下一步）: + 断线重连 + AgentCard + 流式消息
v0.3: + Task生命周期 + 多会话 + 多模态
v1.0: + NAT穿透 + DID身份
```

不要学 A2A 做成企业级重量级协议。
我们的赛道是：**个人/小团队 Agent 快速互联**，极简、即用、P2P。
