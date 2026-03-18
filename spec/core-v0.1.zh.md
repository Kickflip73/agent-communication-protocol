# ACP 核心规范 v0.1

**状态**：草案  
**语言**：[English](core-v0.1.md) · **中文**  
**作者**：ACP 社区  
**日期**：2026-03-18  
**许可**：Apache 2.0

---

## 1. 简介

### 1.1 目标

**Agent 通信协议（ACP）** 是一个开放的应用层通信协议，定义了自主 AI Agent 之间互相通信的标准格式和交互模型。

ACP 的设计目标是：
- **通用**：任何 Agent 框架、任何语言、任何部署方式都能实现
- **实用**：解决真实的 Agent 间通信问题，而非学术概念
- **轻量**：核心规范极简，扩展能力通过消息类型叠加

一句话定位：**ACP 之于 Agent 间通信，如同 MCP 之于 Agent 调用工具。**

### 1.2 适用范围

ACP 涵盖：
- **Agent 间（A2A）消息传递** — 任务委托、结果上报
- **能力协商** — 连接建立时双方声明自己能做什么
- **事件广播与订阅** — 发布/订阅模式的 Agent 事件
- **协调机制** — 多 Agent 投票、共识
- **人机协作** — 需要人工介入的升级流程
- **错误处理** — 标准错误码和重试语义

ACP **不涵盖**：
- Agent 调用工具（参见 MCP）
- Agent 内部推理过程
- LLM 推理接口
- 人机交互 UX

### 1.3 与现有协议的关系

| 协议 | 解决什么问题 | 与 ACP 的关系 |
|------|------------|--------------|
| MCP（Anthropic）| Agent ↔ 工具 | 互补，不同场景 |
| Google A2A | Agent ↔ Agent | 竞争；ACP 厂商中立 |
| JSON-RPC 2.0 | 通用 RPC | ACP 借鉴了部分设计 |
| FIPA-ACL（1990年代）| Agent 通信 | ACP 是其现代继承者，JSON 原生、异步优先 |
| HTTP / WebSocket | 传输层 | ACP 运行于其上 |

---

## 2. 核心概念

### 2.1 Agent 身份标识（AID）

每个参与 ACP 通信的 Agent 拥有全局唯一的 **Agent 身份标识（AID）**。

**格式：**
```
did:acp:<namespace>:<agent-name>
```

**示例：**
```
did:acp:local:summarizer-agent
did:acp:mycompany:customer-support-v2
did:acp:global:7f3a9b2c-1234-5678-abcd-ef0123456789
```

**命名空间语义：**

| 命名空间 | 含义 | 信任级别 |
|---------|------|---------|
| `local` | 同进程或同机器，无需外部验证 | 本地信任 |
| `<组织名>` | 组织范围内，由组织注册中心验证 | 组织信任 |
| `global` | 全局公开，可选 DID 文档背书 | 公开验证 |

### 2.2 消息信封

每条 ACP 消息 MUST 包含标准信封：

```json
{
  "acp":            "0.1",
  "id":             "msg_7f3a9b2c",
  "type":           "task.delegate",
  "from":           "did:acp:local:orchestrator",
  "to":             "did:acp:local:summarizer",
  "ts":             "2026-03-18T10:00:00Z",
  "correlation_id": "workflow_abc123",
  "reply_to":       "msg_001",
  "ttl":            300,
  "trace": {
    "trace_id":      "abc123def456",
    "span_id":       "7f3a9b2c",
    "parent_span_id": "1a2b3c4d"
  },
  "body": { ... }
}
```

**字段定义：**

| 字段 | 必须 | 类型 | 说明 |
|------|------|------|------|
| `acp` | ✅ | string | 协议版本，当前 `"0.1"` |
| `id` | ✅ | string | 消息唯一 ID（UUID 或 `msg_<random>`）|
| `type` | ✅ | string | 消息类型（见第 3 节）|
| `from` | ✅ | string | 发送方 AID |
| `to` | ✅ | string | 接收方 AID 或广播 topic |
| `ts` | ✅ | string | ISO 8601 UTC 时间戳 |
| `correlation_id` | ☑️ | string | 关联同一会话/工作流的多条消息 |
| `reply_to` | ☑️ | string | 回复哪条消息的 `id` |
| `ttl` | ☑️ | integer | 消息过期秒数，超时后视为过期 |
| `trace` | ☑️ | object | 分布式链路追踪（OpenTelemetry 兼容）|
| `body` | ✅ | object | 消息内容，格式由 type 决定 |

---

## 3. 初始化与能力协商

所有 ACP 连接在开始交换业务消息前，MUST 完成一次能力协商握手。

### 3.1 握手流程

```
发起方（Initiator）              接受方（Responder）
        │                              │
        │  agent.hello ────────────────►│
        │  {name, version, caps, ...}  │
        │                              │
        │◄──────────── agent.hello     │
        │  {name, version, caps, ...}  │
        │                              │
        │  ← 握手完成，可发业务消息 →  │
```

**握手规则：**
1. 连接建立后，发起方首先发送 `agent.hello`
2. 接受方回复自己的 `agent.hello`
3. 双方记录对方的能力列表
4. 任意一方可在任何时候发送 `agent.bye` 关闭连接

### 3.2 能力协商机制

`agent.hello` 的 `capabilities` 字段是一个字符串列表，声明该 Agent 支持哪些任务类型。

**发起方（Initiator）：**
```json
{
  "acp": "0.1",
  "id":  "msg_init_001",
  "type": "agent.hello",
  "from": "did:acp:local:orchestrator",
  "to":   "did:acp:local:summarizer",
  "ts":   "2026-03-18T10:00:00Z",
  "body": {
    "name":    "Orchestrator Agent",
    "version": "1.0.0",
    "acp_version": "0.1",
    "capabilities": ["orchestrate", "delegate"],
    "metadata": {
      "framework": "LangChain",
      "language":  "Python 3.12"
    }
  }
}
```

**接受方（Responder）：**
```json
{
  "acp": "0.1",
  "id":  "msg_init_002",
  "type": "agent.hello",
  "from": "did:acp:local:summarizer",
  "to":   "did:acp:local:orchestrator",
  "ts":   "2026-03-18T10:00:00Z",
  "reply_to": "msg_init_001",
  "body": {
    "name":    "Summarizer Agent",
    "version": "1.0.0",
    "acp_version": "0.1",
    "capabilities": ["summarize", "translate", "classify"],
    "input_schema": {
      "type": "object",
      "properties": {
        "text":       { "type": "string" },
        "max_length": { "type": "integer", "default": 200 }
      },
      "required": ["text"]
    },
    "output_schema": {
      "type": "object",
      "properties": { "summary": { "type": "string" } }
    },
    "max_concurrent_tasks": 10,
    "metadata": {
      "model":     "gpt-4o",
      "framework": "AutoGen",
      "language":  "Python 3.12"
    }
  }
}
```

### 3.3 版本协商

- `acp_version` 字段声明实现支持的最高 ACP 版本
- 如果双方版本不兼容（主版本号不同），接受方 MUST 回复 `error`（`acp.version_mismatch`）
- 如果版本兼容，以**较低版本**为准进行通信

---

## 4. 消息类型

### 4.1 任务类消息

任务类消息实现了 Agent 间最核心的交互模式：委托 → 接受/拒绝 → 执行 → 上报结果。

#### `task.delegate` — 委托任务

发送方请求接收方执行某项任务。

```json
{
  "type": "task.delegate",
  "body": {
    "task": "对以下文档生成摘要",
    "input": {
      "text": "...",
      "max_length": 200
    },
    "constraints": {
      "deadline":   "2026-03-18T10:05:00Z",
      "max_tokens": 500,
      "priority":   "high",
      "budget":     { "usd": 0.05 }
    },
    "context":  [ ],
    "callback": "did:acp:local:orchestrator"
  }
}
```

#### `task.accept` — 接受任务

接收方确认将执行该任务。

```json
{
  "type": "task.accept",
  "body": {
    "estimated_completion": "2026-03-18T10:01:30Z",
    "task_handle": "task_abc123"
  }
}
```

#### `task.reject` — 拒绝任务

接收方拒绝执行任务。

```json
{
  "type": "task.reject",
  "body": {
    "reason":  "overloaded",
    "message": "当前任务队列已满，请 30 秒后重试",
    "retry_after": "2026-03-18T10:01:00Z"
  }
}
```

`reason` 取值：`overloaded` | `unauthorized` | `capability_mismatch` | `deadline_infeasible` | `budget_exceeded`

#### `task.result` — 任务结果

接收方上报任务完成情况。

```json
{
  "type": "task.result",
  "body": {
    "status": "success",
    "output": {
      "summary": "..."
    },
    "artifacts": [
      { "type": "inline", "name": "summary.txt", "content": "..." }
    ],
    "usage": {
      "tokens_in":   234,
      "tokens_out":  512,
      "duration_ms": 1243
    },
    "error": null
  }
}
```

`status` 取值：`success` | `partial` | `failed`

#### `task.progress` — 任务进度

长时间任务的中间进度更新。

```json
{
  "type": "task.progress",
  "body": {
    "percent": 45,
    "message": "正在处理第 3/7 章节...",
    "partial_output": { }
  }
}
```

#### `task.cancel` — 取消任务

发送方取消已委托的任务。

```json
{
  "type": "task.cancel",
  "body": { "reason": "deadline_exceeded" }
}
```

---

### 4.2 生命周期消息

#### `agent.hello` — 握手/能力声明

见第 3 节。

#### `agent.bye` — 优雅关闭

```json
{
  "type": "agent.bye",
  "body": { "reason": "normal_close" }
}
```

#### `agent.heartbeat` — 心跳

```json
{
  "type": "agent.heartbeat",
  "body": {
    "status": "healthy",
    "load":   0.35,
    "active_tasks": 3
  }
}
```

---

### 4.3 事件消息

#### `event.broadcast` — 广播事件

```json
{
  "type": "event.broadcast",
  "to":   "topic:market-data-updates",
  "body": {
    "event_name": "price.updated",
    "payload":    { "symbol": "AAPL", "price": 182.5 }
  }
}
```

#### `event.subscribe` / `event.unsubscribe` — 订阅/取消订阅

```json
{
  "type": "event.subscribe",
  "to":   "did:acp:local:event-bus",
  "body": {
    "topic":  "topic:market-data-updates",
    "filter": { "event_name": "price.updated" }
  }
}
```

---

### 4.4 协调消息

#### `coord.propose` — 提案

```json
{
  "type": "coord.propose",
  "body": {
    "proposal_id":     "prop_abc123",
    "action":          { "type": "deploy", "target": "prod" },
    "voting_deadline": "2026-03-18T10:05:00Z",
    "required_votes":  3
  }
}
```

#### `coord.vote` — 投票

```json
{
  "type": "coord.vote",
  "body": {
    "proposal_id": "prop_abc123",
    "vote":        "approve",
    "reason":      "符合安全策略"
  }
}
```

`vote` 取值：`approve` | `reject` | `abstain`

---

### 4.5 人机协作消息

#### `hitl.escalate` — 升级到人工

```json
{
  "type": "hitl.escalate",
  "to":   "did:acp:human:alice",
  "body": {
    "reason":  "approval_required",
    "context": { "action": "删除生产数据库", "impact": "high" },
    "options": [
      { "id": "approve", "label": "批准并继续" },
      { "id": "reject",  "label": "取消操作" },
      { "id": "modify",  "label": "修改参数" }
    ],
    "deadline":          "2026-03-18T10:10:00Z",
    "default_on_timeout": "reject"
  }
}
```

`reason` 取值：`approval_required` | `ambiguity` | `ethical_concern` | `budget_exceeded`

#### `hitl.response` — 人工响应

```json
{
  "type": "hitl.response",
  "body": {
    "choice":        "approve",
    "modifications": { }
  }
}
```

---

### 4.6 错误消息

#### `error` — 错误

```json
{
  "type": "error",
  "body": {
    "code":        "acp.capability_missing",
    "message":     "该 Agent 不支持 'translate' 能力",
    "details":     { "requested_capability": "translate" },
    "retry_after": null,
    "retryable":   false
  }
}
```

---

## 5. 标准错误码

| 错误码 | HTTP 状态 | 说明 |
|--------|----------|------|
| `acp.unknown_agent` | 404 | 接收方 AID 未找到 |
| `acp.unauthorized` | 401 | 发送方无权联系接收方 |
| `acp.invalid_message` | 400 | 信封格式错误或缺少必填字段 |
| `acp.unsupported_type` | 400 | 不支持的消息类型 |
| `acp.capability_missing` | 400 | 所需能力不可用 |
| `acp.task_not_found` | 404 | task_handle 不存在 |
| `acp.overloaded` | 429 | Agent 负载已满，稍后重试 |
| `acp.deadline_exceeded` | 504 | 任务截止时间已过 |
| `acp.handler_error` | 500 | Agent 内部处理错误 |
| `acp.version_mismatch` | 400 | ACP 版本不兼容 |

---

## 6. 交互模式

### 6.1 同步请求-响应

```
发送方                     接收方
  │  task.delegate ─────────►│
  │                          │  处理中...
  │◄──────── task.result     │
```

发送方发出 `task.delegate` 后等待响应（通过 HTTP 同步返回，或 TCP/stdio 下读取下一行）。

### 6.2 异步回调

```
发送方                     接收方
  │  task.delegate ─────────►│
  │◄──────── task.accept     │  （立即确认）
  │                          │  处理中...
  │◄──────── task.result     │  （完成后主动推送）
```

适用于长时间任务。接收方通过 `task.accept` 立即响应，完成后主动发回 `task.result`。

### 6.3 流式进度

```
发送方                     接收方
  │  task.delegate ─────────►│
  │◄──── task.progress (20%) │
  │◄──── task.progress (60%) │
  │◄──── task.result (100%)  │
```

适用于需要实时反馈的长任务。

### 6.4 并行分发

```
编排 Agent
  │  task.delegate ─────────► Worker-A
  │  task.delegate ─────────► Worker-B   （同时发出，correlation_id 相同）
  │  task.delegate ─────────► Worker-C
  │
  │◄──────── task.result (A)
  │◄──────── task.result (B)
  │◄──────── task.result (C)
  │
  │  聚合结果 → 最终输出
```

同一 `correlation_id` 下的多条 `task.delegate` 表示同一工作流的并行分支。

### 6.5 人机协作流程

```
Agent A           人类            Agent B
  │  task.delegate ─────────────────►│
  │                                  │  需要审批
  │          hitl.escalate ─────────►│→ 人类
  │                     ◄──────────── hitl.response (approve)
  │◄──────────────── task.result    │
```

---

## 7. 安全

### 7.1 v0.1 基础安全要求

- 消息 SHOULD 通过 TLS 传输（生产环境 MUST）
- Agent SHOULD 验证 `from` 字段与连接凭证一致
- `did:acp:local` 的 Agent 在同一进程/机器内互相信任
- 生产环境 MUST 使用消息签名（v0.4+）

### 7.2 v0.4 规划：消息签名（Ed25519）

```json
{
  "acp": "0.1",
  "...",
  "sig": {
    "alg":   "Ed25519",
    "kid":   "did:acp:myorg:orchestrator#key-1",
    "value": "<base64url 签名>"
  }
}
```

---

## 8. 版本控制与兼容性

- `acp` 字段 MUST 存在，值为字符串版本号（如 `"0.1"`）
- 接收方 MUST 拒绝主版本号不支持的消息
- 接收方 SHOULD 忽略不认识的字段（向前兼容）
- 破坏性变更使用新主版本号（`1.0`、`2.0`）

---

## 9. 一致性要求

符合 ACP 规范的实现 MUST：
1. 对所有发出的消息生成合法的消息信封（§2.2）
2. 在发送业务消息前完成能力协商握手（§3）
3. 支持并处理所有核心消息类型（§4）
4. 对不支持的消息类型回复 `acp.unsupported_type` 错误
5. 至少实现一种传输绑定（见传输规范）

---

## 附录 A：完整消息流示例

### A.1 编排器向两个并行 Worker 分发任务

```json
// 编排器 → Worker-搜索
{
  "acp": "0.1", "id": "msg_001", "type": "task.delegate",
  "from": "did:acp:local:orchestrator",
  "to":   "did:acp:local:worker-search",
  "ts":   "2026-03-18T10:00:00Z",
  "correlation_id": "workflow_xyz",
  "body": {
    "task": "搜索近期 AI 记忆机制的相关论文",
    "input": { "query": "AI agent memory 2025", "max_results": 10 },
    "constraints": { "deadline": "2026-03-18T10:02:00Z" }
  }
}

// 编排器 → Worker-摘要（同时发出）
{
  "acp": "0.1", "id": "msg_002", "type": "task.delegate",
  "from": "did:acp:local:orchestrator",
  "to":   "did:acp:local:worker-summarizer",
  "ts":   "2026-03-18T10:00:00Z",
  "correlation_id": "workflow_xyz",
  "body": {
    "task": "准备摘要模板",
    "input": { "format": "academic", "max_length": 500 }
  }
}
```

### A.2 带进度上报的长时间任务

```json
// 进度 45%
{ "acp":"0.1","type":"task.progress","correlation_id":"workflow_xyz",
  "body":{"percent":45,"message":"已分析 45/100 份文档"} }

// 完成
{ "acp":"0.1","type":"task.result","correlation_id":"workflow_xyz",
  "body":{"status":"success","output":{"findings":[...]},"usage":{"duration_ms":222000}} }
```

---

## 变更历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v0.1 | 2026-03-18 | 初始草案：信封格式、核心消息类型、错误码 |
| v0.2 | 2026-03-18 | P2P 模式、群组消息 |
| v0.3 | 2026-03-18 | 连接生命周期、能力协商握手 |
