# ACP 核心规范 v0.1（草案）

**状态**：草案  
**语言**：[English](core-v0.1.md) · **中文**  
**作者**：ACP 社区  
**日期**：2026-03-18  
**许可**：Apache 2.0

---

## 1. 简介

**Agent 通信协议（ACP）** 定义了多智能体系统（MAS）中自主 AI Agent 之间通信的标准消息格式和交互模型。

### 1.1 适用范围

ACP 涵盖：
- **Agent 间（A2A）消息传递**
- **任务委托与结果上报**
- **事件广播**
- **能力声明与发现**
- **错误处理与升级**

ACP **不涵盖**：
- Agent 调用工具（参见 MCP）
- Agent 内部推理过程
- LLM 推理协议
- 人机交互 UX 界面

### 1.2 与现有协议的关系

| 协议 | 定位 | 与 ACP 的关系 |
|------|------|--------------|
| MCP（Anthropic）| Agent ↔ 工具 | 互补，不同场景 |
| Google A2A | Agent ↔ Agent | 竞争，但 ACP 厂商中立 |
| OpenAI API | 人 → LLM | 不同层级 |
| gRPC / HTTP | 传输层 | ACP 运行其上 |

---

## 2. 核心概念

### 2.1 Agent 身份（AID）

每个 Agent 有一个唯一身份标识（Agent Identity，AID）。

**格式：**
```
did:acp:<namespace>:<agent-name>
```

**示例：**
```
did:acp:myorg:summarizer-v2
did:acp:local:worker-1
did:acp:acme-corp:orchestrator
```

在 P2P 模式中，AID 扩展为包含网络地址的 URI：
```
acp://<host>:<port>/<agent-name>
```

### 2.2 消息信封

所有 ACP 消息共享同一信封结构：

```json
{
  "acp": "0.1",
  "id": "msg_<随机>",
  "type": "<消息类型>",
  "from": "<发送方 AID 或 URI>",
  "to":   "<接收方 AID 或 URI>",
  "ts":   "2026-03-18T10:00:00Z",
  "body": { },
  "correlation_id": "可选",
  "reply_to":       "可选"
}
```

| 字段 | 必须 | 说明 |
|------|------|------|
| `acp` | ✅ | 协议版本（当前 `"0.1"`）|
| `id` | ✅ | 消息唯一 ID，格式 `msg_<hex>`|
| `type` | ✅ | 消息类型（见 §3）|
| `from` | ✅ | 发送方身份标识 |
| `to` | ✅ | 接收方身份标识 |
| `ts` | ✅ | UTC 时间戳，ISO 8601 格式 |
| `body` | ✅ | 消息内容，格式由 type 决定 |
| `correlation_id` | ❌ | 关联同一会话/任务的多条消息 |
| `reply_to` | ❌ | 回复哪条消息的 `id` |

---

## 3. 消息类型

### 3.1 任务类

#### `task.delegate` — 委托任务

Agent A 请求 Agent B 执行某项任务。

```json
{
  "acp": "0.1",
  "type": "task.delegate",
  "from": "did:acp:local:orchestrator",
  "to":   "did:acp:local:summarizer",
  "body": {
    "task": "对以下文章进行摘要",
    "input": {
      "text": "...",
      "max_length": 200
    },
    "constraints": {
      "deadline": "2026-03-18T10:05:00Z",
      "max_tokens": 500
    }
  }
}
```

#### `task.result` — 任务结果

```json
{
  "acp": "0.1",
  "type": "task.result",
  "body": {
    "status": "success",
    "output": {
      "summary": "..."
    }
  }
}
```

`status` 取值：`success` | `partial` | `failed`

#### `task.progress` — 任务进度（长任务）

```json
{
  "acp": "0.1",
  "type": "task.progress",
  "body": {
    "percent": 45,
    "message": "正在处理第 3/7 章节..."
  }
}
```

#### `task.cancel` — 取消任务

```json
{
  "acp": "0.1",
  "type": "task.cancel",
  "body": {
    "reason": "deadline_exceeded"
  }
}
```

---

### 3.2 事件类

#### `event.broadcast` — 广播事件

```json
{
  "acp": "0.1",
  "type": "event.broadcast",
  "body": {
    "event": "data.updated",
    "payload": { "table": "orders", "count": 1523 }
  }
}
```

---

### 3.3 系统类

#### `agent.hello` — 握手/探活

```json
{
  "acp": "0.1",
  "type": "agent.hello",
  "body": {
    "name": "Summarizer Agent",
    "capabilities": ["summarize", "translate"],
    "acp_version": "0.1"
  }
}
```

#### `agent.bye` — 断开通知

```json
{
  "acp": "0.1",
  "type": "agent.bye",
  "body": {
    "reason": "normal_close"
  }
}
```

#### `error` — 错误回复

```json
{
  "acp": "0.1",
  "type": "error",
  "body": {
    "code": "acp.capability_missing",
    "message": "该 Agent 不支持请求的能力",
    "retryable": false
  }
}
```

---

### 3.4 群聊类（P2P 扩展）

| type | 说明 |
|------|------|
| `group.invite` | 邀请加入群聊 |
| `group.invite_ack` | 确认加入 |
| `group.message` | 群聊消息 |
| `group.member_joined` | 新成员加入通知 |
| `group.member_left` | 成员退出通知 |

---

## 4. 交互模式

### 4.1 请求-响应（同步）

```
Agent A                     Agent B
  │  task.delegate  ───────►  │
  │                            │  处理...
  │  task.result   ◄───────  │
```

发送方阻塞等待响应（超时由发送方自行控制）。

### 4.2 异步回调

```
Agent A                     Agent B
  │  task.delegate  ───────►  │
  │  202 Accepted  ◄───────  │
  │                            │  处理中...
  │  task.result   ◄───────  │  （完成后主动回调）
```

### 4.3 流式进度

```
Agent A                     Agent B
  │  task.delegate  ───────►  │
  │  task.progress ◄───────  │  （进度 20%）
  │  task.progress ◄───────  │  （进度 60%）
  │  task.result   ◄───────  │  （完成）
```

### 4.4 人机协作（Human-in-the-Loop）

```
Agent A          Human          Agent B
  │  task.delegate ──────────────►  │
  │                                  │  需要人工审批
  │           approval.request ────► │ → human
  │                      ◄──────── approval.granted
  │  task.result  ◄──────────────  │
```

---

## 5. 错误码

| 错误码 | HTTP 状态 | 说明 |
|--------|----------|------|
| `acp.unauthorized` | 401 | 认证失败 |
| `acp.capability_missing` | 400 | Agent 不支持该能力 |
| `acp.rate_limited` | 429 | 请求过于频繁 |
| `acp.timeout` | 504 | 任务超时 |
| `acp.handler_error` | 500 | Agent 内部处理错误 |
| `acp.invalid_message` | 400 | 消息格式错误 |

---

## 6. 传输绑定

ACP 消息可运行在任何传输层之上：

| 传输层 | 端点 | 说明 |
|--------|------|------|
| HTTP/1.1 | `POST /acp/v1/receive` | 默认，最广泛支持 |
| WebSocket | `ws://host:port/acp/v1/ws` | 低延迟双向通信 |
| MQTT | topic `acp/<agent-id>/in` | IoT / 嵌入式场景 |
| gRPC | `ACPService.Send(ACPMessage)` | 高性能内网场景 |

---

## 7. 安全

### 7.1 v0.1（当前）：预共享密钥

```
请求头: X-ACP-PSK: <shared_secret>
```

### 7.2 v0.4（规划）：Ed25519 签名

每条消息附带签名字段：
```json
{
  "sig": {
    "alg": "Ed25519",
    "kid": "did:acp:myorg:agent-a#key-1",
    "value": "<base64url signature>"
  }
}
```

---

## 8. 版本与兼容性

- 版本字段 `"acp": "0.1"` 必须存在
- 接收方**必须**接受高于自身版本的消息（向前兼容）
- 接收方**应该**忽略不认识的字段（扩展友好）
- 破坏性变更使用新的主版本号（`1.0`、`2.0`）

---

## 变更历史

| 版本 | 日期 | 主要变更 |
|------|------|---------|
| v0.1 | 2026-03-18 | 初始草案：信封格式、任务类型、错误码 |
| v0.2 | 2026-03-18 | P2P 模式：URI 格式、群聊消息类型 |
| v0.3 | 2026-03-18 | 生命周期：connect/disconnect/leave |
