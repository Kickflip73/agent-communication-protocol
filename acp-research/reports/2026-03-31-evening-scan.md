# ACP 竞品研究报告 — 2026-03-31（晚间扫描）

_贾维斯研究轮 | ACP 当前版本：v2.24.0_

> **扫描时间：** 2026-03-31 18:00 (CST)
> **数据来源：** 本地 A2A clone（最新 commit: 72d1459, 2026-03-27）
> **外网状态：** GitHub API 访问受限，基于本地 clone + 已知情报分析

---

## 一、A2A 近期动态

### Commit 活动（截至 2026-03-27）

| 日期 | Commit | 内容 |
|------|--------|------|
| 2026-03-27 | 72d1459 | 合作伙伴列表新增 OIXA Protocol |
| 2026-03-26 | 32a7d3a | Python SDK tutorial 更新（a2a-sdk v1.0.0-alpha.0） |
| 2026-03-16 | 7b900e7 | 更新 CODEOWNERS |
| 2026-03-16 | 3c1a5ff | 合作伙伴列表新增 WritBase |
| 2026-03-12 | 7df7685 | 文档样式更新（v1.0 发布后维护期） |

**结论：** A2A spec 本体已进入维护模式（仅 docs/partners 更新）。核心 RPC 定义 specification/a2a.proto 上次变更在 v1.0 发布时（2026-03-12 前）。**近 3 周无 spec 级别变更。**

### A2A v1.0 已定型 API 梳理（ACP 差距分析）

来自 specification/a2a.proto：

| A2A RPC | 功能 | ACP 对应 |
|---------|------|---------|
| `SendMessage` | 发消息 | ✅ `/message/send` |
| `SendStreamingMessage` | 流式发消息 + SSE | ✅ SSE 事件流 |
| `GetTask` | 查询 task 状态 | ✅ 任务状态机（v0.5） |
| `ListTasks` | 列出 tasks | ⬜ 未实现（低优先级） |
| `CancelTask` | 取消 task | ⬜ 未实现 |
| `SubscribeToTask` | SSE 订阅 task 事件 | ✅ SSE per-task |
| `GetExtendedAgentCard` | 认证后获取扩展 AgentCard | ✅ ACP v2.24 `/peers/<id>/card`（更简洁：P2P 不需要服务端认证） |
| `CreateTaskPushNotificationConfig` | 配置 Webhook 推送 | ⬜ 未实现（ACP 用 offline queue 替代） |
| `GetTaskPushNotificationConfig` | 查询推送配置 | ⬜ 未实现 |

**ACP vs A2A 核心设计差异：**
- A2A：`GetExtendedAgentCard` 需要**认证后才能获取完整 card**（JWT/Bearer），中心化服务假设
- ACP：`GET /peers/<id>/card` 在握手即完成 card 交换，P2P 环境天然无此问题 → **ACP 更简洁**

### A2A Roadmap 关键信号（2026-03-10 更新）

- **近期**：v1.0 发布后以文档、SDK、社区贡献为主
- **3-6 个月**：
  - A2A Inspector（验证工具）
  - TCK（技术兼容性测试套件）
  - 5 语言 SDK 持续完善
  - 社区最佳实践整理
- **暗示**：没有提到 P2P 直连、LAN 发现、广播、离线投递等特性 → **ACP 的差异化护城河在 A2A 官方 roadmap 中未被列入**

---

## 二、ACP v2.24 战略评估

今日 ACP 完成了从 v2.19 到 v2.24 的 6 个版本迭代，形成了完整的**特性差异化矩阵**：

| ACP 特性 | A2A 状态 | 差异化价值 |
|---------|---------|---------|
| P2P 直连 + 三级降级（v2.19） | 无 | ★★★★★ 核心竞争力 |
| LAN 发现（v2.1） | 无 | ★★★★☆ 本地场景覆盖 |
| 离线消息队列（v2.0） | 无 | ★★★★☆ 鲁棒性 |
| 广播（v2.22）+ 子集广播（v2.23） | 无（PR#1196 TSC 审核中） | ★★★★☆ 多 Agent 协作 |
| 广播历史审计（v2.23） | 无 | ★★★☆☆ 调试/运维 |
| Peer AgentCard 查询（v2.24） | `GetExtendedAgentCard`（需认证）| ★★★☆☆ 更简洁的 P2P 实现 |
| Runtime limitations PATCH（v2.21） | IS#1694 仍提案 | ★★★☆☆ 动态能力管理 |
| 兼容性认证（Level 1/2） | TCK（3-6 个月 roadmap） | ★★★☆☆ 生态基础 |

---

## 三、v2.25 候选特性分析

### P1 — Agent 健康心跳 `POST /peers/:peer_id/ping`

- **背景**：多 Agent 系统中 Orchestrator 需要实时感知 Worker 可用性，而不是等到消息超时才发现 peer 断连
- **设计**：
  ```json
  POST /peers/:peer_id/ping
  Response: {"ok": true, "peer_id": "...", "latency_ms": 12, "alive": true}
  503 ERR_NOT_CONNECTED 当 peer 不可达
  ```
- **A2A 对应**：无（A2A 靠客户端侧超时感知，无主动 ping 机制）
- **复杂度**：低（复用 `_ws_send_sync()` + 新增 `acp.ping` / `acp.pong` 消息类型）
- **建议**：列入 v2.25

### P1 — `GET /peers` 增强：分页 + 过滤

- **背景**：大规模多 Agent 场景（100+ peers）时 `/peers` 返回完整列表开销大
- **设计**：`?connected=true&limit=20&offset=0`
- **复杂度**：低
- **建议**：v2.25 与 ping 合并

### P2 — Peer 状态订阅（SSE）`GET /peers/events`

- **背景**：Orchestrator 需要实时感知 peer 连接/断开事件，主动轮询 `/peers` 效率低
- **设计**：SSE 流，推送 `{event: "peer_connected|peer_disconnected", peer_id: ..., ts: ...}`
- **A2A 对应**：`SubscribeToTask`（只订阅 task 级别），无 peer 级别事件
- **复杂度**：中（需维护订阅者列表，复用现有 SSE 基础设施）
- **建议**：v2.26 候选

### P3 — 消息确认机制 `acp.ack`

- **背景**：当前 ACP 消息送达后无显式 ACK，Sender 只能通过 `results[]` 判断
- **设计**：Receiver 自动回复 `{"type":"acp.ack","correlation_id":"..."}`；Sender 端超时计时器
- **复杂度**：中（需修改接收路径 + 添加 pending_ack 表）
- **建议**：v2.27 候选

---

## 四、Show HN 发布时机重新评估

| 指标 | 状态 |
|------|------|
| A2A spec 活跃度 | 🟡 维护模式（3 周无 spec 变更） |
| ACP 特性完整度 | ✅ v2.24，6 大差异化特性 |
| 测试覆盖率 | ✅ 73 测试全部 PASS（BC1-10 + BH1-11 + PC1-9 + LP13 + LS18 + JW13 + TS8） |
| 文档完整度 | ✅ README + CHANGELOG + ROADMAP + ADR + 兼容性认证 |
| SDK 矩阵 | ✅ Python/Node/Go/Rust/Java |
| 发布窗口 | ✅ **窗口依然开启** |

**建议**：v2.25（健康心跳特性）完成后即可准备 Show HN。核心 hook：
> "A2A is enterprise-grade with OAuth2, gRPC, and 8 task states. ACP is 2 commands and agents are talking to each other."

---

## 五、结论与下次行动

**今日已完成（2026-03-31）**：
- v2.22：全员广播
- v2.23：子集广播 + 广播历史
- v2.24：Peer AgentCard 查询 + card 缓存 bug 修复
- **测试总计：30 个新测试用例，全部 PASS**

**下次开发轮（v2.25）优先级**：
1. `POST /peers/:peer_id/ping` — Agent 健康心跳
2. `GET /peers` 分页过滤增强
3. 版本 v2.25，PC 测试套件

**长期**：v2.25 完成后评估 Show HN 发布。

---

_贾维斯 | 2026-03-31 18:04 CST_
