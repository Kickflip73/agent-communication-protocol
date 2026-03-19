# A2A 协议深度研究报告

> 研究日期：2026-03-19
> 来源：https://a2a-protocol.org/latest/ + https://github.com/a2aproject/A2A
> 研究者：贾维斯

---

## 1. A2A 架构总览

A2A 分三层设计，这个分层思路值得我们借鉴：

```
Layer 1: 数据模型（Data Model）
  Task / Message / AgentCard / Part / Artifact / Extension

Layer 2: 抽象操作（Abstract Operations）
  SendMessage / StreamMessage / GetTask / ListTasks / CancelTask / GetAgentCard

Layer 3: 协议绑定（Protocol Bindings）
  JSON-RPC / gRPC / HTTP+REST / 自定义绑定
```

**对我们的启示**：我们目前只有「绑定层」（HTTP over SSE），缺乏清晰的数据模型层和操作层定义。应该补上。

---

## 2. 核心数据结构（必须研究）

### 2.1 Task —— 核心工作单元

```protobuf
message Task {
  string id = 1;          // 唯一 ID，服务端生成
  string context_id = 2;  // 上下文 ID（用于分组关联任务）
  TaskStatus status = 3;  // 当前状态
  repeated Artifact artifacts = 4;  // 输出产物
  repeated Message history = 5;     // 交互历史
  google.protobuf.Struct metadata = 6;  // 自定义元数据
}
```

### 2.2 TaskState —— 8 种状态（精华！）

| 状态 | 含义 | 类型 |
|------|------|------|
| `TASK_STATE_SUBMITTED` | 已提交，等待处理 | 中间态 |
| `TASK_STATE_WORKING` | 正在处理 | 中间态 |
| `TASK_STATE_COMPLETED` | 成功完成 | **终态** |
| `TASK_STATE_FAILED` | 处理失败 | **终态** |
| `TASK_STATE_CANCELED` | 已取消 | **终态** |
| `TASK_STATE_REJECTED` | Agent 拒绝执行 | **终态** |
| `TASK_STATE_INPUT_REQUIRED` | 需要用户补充输入 | 中断态 |
| `TASK_STATE_AUTH_REQUIRED` | 需要认证才能继续 | 中断态 |

**关键洞察**：A2A 区分了「终态」和「中断态」。中断态意味着任务可以在用户响应后继续，不是失败。`REJECTED` 是 Agent 主动拒绝（vs `FAILED` 是处理过程中出错）——这个区分非常有价值。

### 2.3 Part —— 多模态内容单元

```protobuf
message Part {
  oneof content {
    string text = 1;        // 纯文本
    bytes raw = 2;          // 原始字节（图片/文件，base64 in JSON）
    string url = 3;         // 文件 URL 引用
    google.protobuf.Value data = 4;  // 任意 JSON 结构化数据
  }
  string filename = 6;
  string media_type = 7;   // MIME type
}
```

**关键洞察**：Part 是最小内容单元，同时支持 text/bytes/url/structured_data，用 `oneof` 保证类型安全。

### 2.4 AgentCard —— 能力声明

AgentCard 是 Agent 的「名片」，包含：
- `name`, `description`, `version`
- `supportedInterfaces`：支持的协议绑定列表
- `capabilities`：`streaming`, `pushNotifications`, `extendedAgentCard`
- `skills`：具体能力列表（每个 Skill 有 id/name/description/tags/examples）
- `securitySchemes`：支持的认证方案
- `extensions`：扩展声明

### 2.5 Message —— 通信单元

```protobuf
message Message {
  string message_id = 1;    // 客户端生成的消息 ID（幂等性关键）
  string context_id = 2;    // 可选，关联上下文
  string task_id = 3;       // 可选，关联任务
  Role role = 4;            // ROLE_USER / ROLE_AGENT
  repeated Part parts = 5;
  repeated string extensions = 7;
  repeated string reference_task_ids = 8;  // 引用其他任务（跨任务上下文）
}
```

---

## 3. 核心操作（API 设计）

### HTTP/REST Endpoints

| 操作 | 端点 |
|------|------|
| 发送消息（同步） | `POST /message:send` |
| 发送消息（流式） | `POST /message:stream` |
| 获取任务 | `GET /tasks/{id}` |
| 列出任务 | `GET /tasks` |
| 取消任务 | `POST /tasks/{id}:cancel` |
| 订阅任务更新 | `GET /tasks/{id}:subscribe` (SSE) |
| 获取扩展 AgentCard | `GET /extendedAgentCard` |
| Push 通知配置 | `POST /tasks/{id}/pushNotificationConfigs` |

**设计亮点**：REST 端点用 `:action` 后缀（`/message:send`，`:cancel`，`:subscribe`），比普通 CRUD 更清晰。

### return_immediately 参数

```protobuf
message SendMessageConfiguration {
  bool return_immediately = 4;
  // false（默认）= 等任务到终态/中断态再返回
  // true = 立即返回任务 ID，客户端自己轮询/订阅
}
```

**关键洞察**：这个参数解决了短任务和长任务的统一问题。

---

## 4. 流式交互模式

### SSE 流响应结构

```
data: {"task": {"id": "xxx", "status": {"state": "TASK_STATE_WORKING"}}}

data: {"artifactUpdate": {"taskId": "xxx", "artifact": {"parts": [{"text": "..."}]}}}

data: {"statusUpdate": {"taskId": "xxx", "status": {"state": "TASK_STATE_COMPLETED"}}}
```

**关键洞察**：流式响应有两种事件类型——`TaskStatusUpdateEvent` 和 `TaskArtifactUpdateEvent`，分别推送状态变更和增量内容。我们目前只有原始文本流，缺乏结构化的事件类型。

---

## 5. 扩展机制（Extension System）

```json
{
  "capabilities": {
    "extensions": [
      {
        "uri": "https://example.com/extensions/geolocation/v1",
        "description": "Location-based search",
        "required": false  // true = 不支持就报错，false = 优雅降级
      }
    ]
  }
}
```

客户端通过 HTTP Header 声明使用哪些扩展：
```http
A2A-Extensions: https://example.com/extensions/geolocation/v1
```

**关键洞察**：扩展通过 URI 标识（带版本），`required` 字段控制强制/可选，URI 破坏性变更时必须用新 URI。这是一套非常优雅的前向兼容机制。

---

## 6. 推送通知（Push Notification）

```json
// 客户端请求时配置 webhook
{
  "configuration": {
    "pushNotificationConfig": {
      "url": "https://client.example.com/webhook",
      "token": "secure-token",
      "authentication": {"schemes": ["Bearer"]}
    }
  }
}
```

服务端在任务完成后 POST 到 webhook：
```http
POST /webhook HTTP/1.1
Authorization: Bearer server-jwt
X-A2A-Notification-Token: secure-token

{"statusUpdate": {"taskId": "xxx", "status": {"state": "TASK_STATE_COMPLETED"}}}
```

---

## 7. 错误码体系

| 错误类型 | HTTP 状态码 | 含义 |
|---------|------------|------|
| `TaskNotFoundError` | 404 | 任务不存在 |
| `TaskNotCancelableError` | 409 | 任务无法取消（已终态） |
| `PushNotificationNotSupportedError` | 400 | Agent 不支持 Push |
| `UnsupportedOperationError` | 400 | 操作不支持 |
| `ContentTypeNotSupportedError` | 415 | 媒体类型不支持 |
| `InvalidAgentResponseError` | 502 | Agent 内部响应异常 |
| `ExtensionSupportRequiredError` | 400 | 必须扩展但不支持 |
| `VersionNotSupportedError` | 400 | 协议版本不支持 |

---

## 8. 版本协商

客户端通过 Header 声明期望版本：
```http
A2A-Version: 0.3
```

服务端如果不支持，返回：
```json
{
  "type": "https://a2a-protocol.org/errors/version-not-supported",
  "supportedVersions": ["0.3"]
}
```

---

## 9. 对我们 ACP 的行动建议

### 🔴 立刻借鉴（v0.5，本周）

1. **Task 状态机**：完整实现 8 种状态，尤其是 `INPUT_REQUIRED` + `REJECTED` 区分
2. **消息 ID 幂等性**：`message_id` 由客户端生成，服务端去重
3. **结构化 SSE 事件**：区分 `statusUpdate` 和 `artifactUpdate` 两种事件类型

### 🟡 中期借鉴（v0.6）

4. **Part 多模态**：支持 text/url/bytes/data 四种类型
5. **`return_immediately` 参数**：解耦短任务和长任务处理
6. **错误码规范化**：建立我们自己的错误码体系（参考 A2A 的 8 个错误类型）

### 🟢 长期借鉴（v1.0）

7. **Extension 机制**：URI 标识 + required 字段 + 优雅降级
8. **三层架构**：明确分离数据模型层、操作层、绑定层
9. **Push Notification**：Webhook 回调机制

### 🚫 刻意不借鉴

- **gRPC 绑定**：我们定位是轻量级 P2P，JSON over HTTP 足够
- **OAuth 2.0 全套**：我们做渐进式认证（无认证 → token → DID）
- **企业级 ACL/多租户**：`{tenant}/tasks/{id}` 这种多租户设计不符合我们 P2P 理念

---

## 10. 我们的核心差异化（更加清晰了）

A2A 是「企业级 Agent 服务总线」，需要服务端、需要注册、需要运维。

我们的 ACP 是「Agent 之间的 WhatsApp」——**零服务器，Skill 驱动，发链接即连接**。

A2A 解决的是「企业内不同系统的 Agent 如何互通」，我们解决的是「两个 Agent 如何即时 P2P 通信」。这两个赛道并不冲突，可以互补。

