# ACP Bug Tracker

> 来源：真实双 Agent 通信测试（2026-03-23，贾维斯 vs AgentA/AgentB）
> 测试环境：本地两个 acp_relay.py 实例，真实 HTTP + WebSocket 通信

---

## 🔴 P0 — 严重（核心功能失效）

### BUG-001: SSE stream 不推送消息事件
- **现象**：`/stream` 只返回 `: keepalive` 注释行，发送 `/message:send` 后无任何 SSE 事件推送
- **期望**：每条收到的消息应推送 `event: acp.message\ndata: {...}` 事件
- **影响**：流式场景完全不可用；`test_stream.py` 的 SHOULD 测试全部 SKIP/FAIL
- **文件**：`relay/acp_relay.py` SSE handler
- **状态**：🔴 待修复

### BUG-002: Task cancel 返回 `failed` 而非 `canceled`
- **现象**：`POST /tasks/{id}:cancel` 响应 `{"status": "failed"}`，后续 GET 也是 `failed`
- **期望**：状态应变为 `canceled`（spec §3 明确定义 5 种状态）
- **影响**：Task 状态机语义错误，下游逻辑无法区分「取消」和「失败」
- **文件**：`relay/acp_relay.py` task cancel handler
- **状态**：🔴 待修复

---

## 🟡 P1 — 重要（行为不符合 spec）

### BUG-003: 重复连接同一 link 创建两个 peer
- **现象**：`POST /peers/connect` 对同一 `acp://` link 调用一次，AgentA 的 /peers 显示 peer_001 和 peer_002 两个条目，均指向相同 link
- **期望**：幂等连接，相同 link 只创建一个 peer 记录
- **影响**：peer 列表膨胀，重复投递风险
- **文件**：`relay/acp_relay.py` peers/connect handler
- **状态**：🟡 待修复

### BUG-004: `/message:send` 响应缺少 `server_seq`
- **现象**：响应只有 `{"ok": true, "message_id": "...", "task": null}`，没有 `server_seq` 字段
- **期望**：spec §4 SHOULD 要求响应包含 `server_seq` 整数
- **影响**：客户端无法追踪消息序号，幂等重发校验失效
- **文件**：`relay/acp_relay.py` message send handler
- **状态**：🟡 待修复

### BUG-005: peer.messages_received 统计不更新
- **现象**：AgentB 收到消息后，`/peers` 中 `peer_001.messages_received` 仍为 0
- **期望**：每收到一条来自该 peer 的消息，计数器 +1
- **影响**：监控/调试时无法判断 peer 通道是否正常工作
- **文件**：`relay/acp_relay.py` peer message tracking
- **状态**：🟡 待修复

---

## 🟢 P2 — 轻微（体验问题）

### BUG-006: 创建 Task 时传入的 `task_id` 被忽略
- **现象**：`POST /tasks` 传入 `{"task_id": "task_001", ...}`，但服务端生成新 ID `task_2564d56105ac`，`task_001` 被忽略
- **期望**：若客户端提供 `task_id`，服务端应使用该 ID（幂等语义）；若已存在则返回现有 task
- **影响**：客户端无法预知 task ID，需要额外解析响应
- **文件**：`relay/acp_relay.py` task create handler
- **状态**：🟢 待讨论（行为是否符合设计意图）

---

## ✅ 验证通过的功能

| 功能 | 测试结果 |
|------|---------|
| AgentCard (`/.well-known/acp.json`) | ✅ 正确返回完整结构 |
| 双向消息收发（A→B, B→A） | ✅ 消息正确到达 inbox |
| 消息持久化（inbox JSONL） | ✅ 正确写入磁盘 |
| P2P 连接建立（acp:// link） | ✅ `{"ok": true, "peer_id": "peer_001"}` |
| role 校验（拒绝 superagent） | ✅ 返回 ERR_INVALID_REQUEST |
| role 缺失校验 | ✅ 返回 ERR_INVALID_REQUEST |
| Task 创建（submitted 状态） | ✅ 正确 |
| Task 查询 | ✅ 正确 |
| SSE keepalive | ✅ 正常发送 |
| AgentB 的 acp:// link 可读 | ✅ `/peers` 返回 link 字段 |

---

## 修复优先级

```
P0: BUG-001 SSE 事件推送 → BUG-002 cancel 状态
P1: BUG-004 server_seq → BUG-003 重复 peer → BUG-005 统计
P2: BUG-006 task_id 语义讨论
```

---

*最后更新：2026-03-23 11:58 by J.A.R.V.I.S.*
