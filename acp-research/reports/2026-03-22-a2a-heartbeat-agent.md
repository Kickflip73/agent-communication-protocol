# 研究报告：A2A Issue #1667 — Heartbeat Agent 可用性元数据

**日期**：2026-03-22  
**来源**：https://github.com/a2aproject/A2A/issues/1667  
**标题**：[Protocol Question] Heartbeat-based agents: availability metadata and offline-first task handling

---

## 问题摘要

A2A spec 假设 Agent 是持续运行的服务，但大量真实部署是 **heartbeat / cron 型 Agent**（如每隔数小时唤醒一次，处理完任务后休眠）。这类 Agent 没有持久化服务器，导致：

1. **调用方不知道 Agent 是否在线**——`tasks/send` 可能打到一个不存在的端点
2. **无可用性元数据**——AgentCard 没有 `scheduleType`、`nextActiveAt`、`lastActiveAt`、`taskLatencyMaxSeconds`
3. **任务延迟不可预测**——延迟是心跳周期的函数，不是网络 RTT

### A2A 当前 AgentCard 缺失字段
```
scheduleType         (cron / interval / persistent / manual)
nextActiveAt         ISO-8601 时间戳
lastActiveAt         ISO-8601 时间戳
taskLatencyMaxSeconds  预期最大处理延迟
```

---

## ACP 视角分析

### 我们的优势
ACP 的目标用户是**个人和小团队**，heartbeat/cron Agent 是典型用例（比如 J.A.R.V.I.S. 自身就是 heartbeat 型）。A2A 在协议层面甚至没有考虑这个场景——而 ACP 天然适配。

### 行动项（建议加入 v1.2 规划）

**AgentCard 扩展：`availability` 块**

```json
{
  "agent_card": {
    "name": "my-agent",
    "availability": {
      "mode": "heartbeat",          // persistent | heartbeat | cron | manual
      "interval_seconds": 3600,      // 心跳间隔（heartbeat/cron 时有效）
      "next_active_at": "2026-03-22T06:00:00Z",  // 下次唤醒时间（可选）
      "last_active_at": "2026-03-22T05:00:00Z",  // 上次唤醒时间（可选）
      "task_latency_max_seconds": 7200            // 最大预期延迟
    }
  }
}
```

**设计原则**：
- 所有字段均为可选（保持向后兼容）
- `mode: persistent` = 当前默认行为（无变化）
- `next_active_at` 由 Agent 自行更新（每次唤醒时写入 AgentCard）
- 调用方可用 `task_latency_max_seconds` 设置超时预期

### 差异化价值
A2A 在 issues 层面讨论这个问题，我们可以在 **spec/core-v1.0.md 的 `experimental` 扩展章节**先行实现，成为第一个支持 heartbeat 元数据的 Agent 通信协议。

---

## 优先级建议

| 优先级 | 任务 | 原因 |
|--------|------|------|
| P1（v1.2） | AgentCard `availability` 块规范 + 实现 | ACP 核心用户场景，A2A 空白区 |
| P2 | AgentCard 自动更新 API（Agent 启动时 PATCH `/.well-known/acp.json`） | 让 next_active_at 保持最新 |

---

## ANP 状态
- 2026-03-05 以来无新 commits，停滞

---

*贾维斯研究存档*
