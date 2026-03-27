# ACP 竞品扫描报告 — 2026-03-27（晚）

> 扫描时间：2026-03-27 20:17 CST  
> 执行者：J.A.R.V.I.S. 研究子 Agent（acp-research-evening-2026-03-27）

---

## A2A 动态

### 近期 Commits（最近 10 条）

| 日期 | SHA | 摘要 |
|------|-----|------|
| 2026-03-26 | 32a7d3a | docs: update python tutorial for a2a-sdk v1.0.0-alpha.0 (#1678) |
| 2026-03-16 | 7b900e7 | Update CODEOWNERS — TSC 成为 reviewing body |
| 2026-03-16 | 3c1a5ff | docs: add WritBase to partners list (#1634) |
| 2026-03-12 | 7df7685 | Update main.html — reverted announcement |
| 2026-03-12 | 4f77f1b | docs: Blog post announcing V1.0 🎉 |
| 2026-03-12 | 6845a87 | docs: Update Specification.md for 1.0.0 from release candidate |

**关键事件：A2A 于 2026-03-12 正式发布 V1.0 规范。**  
最新 commit（2026-03-26）是 Python SDK `a2a-sdk v1.0.0-alpha.0` 的教程同步更新，表明官方 SDK 处于 Alpha 阶段快速迭代中。

---

### 近期 Issues（最新 10 条，截至 2026-03-27）

| 日期 | Issue | 类型 | 摘要 |
|------|-------|------|------|
| 2026-03-27 | #1694 | Feature | 提议在 AgentCard 增加 `limitations` 字段，描述 Agent 的能力边界/限制 |
| 2026-03-27 | #1693 | Bug/Docs | 协议规范文档中 TaskPushNotificationConfig 表格重复 |
| 2026-03-27 | #1692 | Feature | 申请将 OIXA Protocol（AI Agent 经济协议，基于 A2A + Base 链）加入 partners |
| 2026-03-26 | #1690 | 规范模糊 | Tenant 传输机制在不同 binding（HTTP/gRPC）中描述不一致 |
| 2026-03-26 | #1689 | Bug/Docs | HTTP+JSON 错误响应的 Content-Type 未明确（application/json vs application/problem+json） |
| 2026-03-25 | #1685 | Bug | 同上，Content-Type 错误规范缺失 |
| 2026-03-25 | #1684 | Bug | `CancelTaskRequest` 定义缺失；取消任务后 SSE 状态返回不明确 |
| 2026-03-25 | #1683 | Bug | SSE streaming 示例中 `contextId` 字段缺失（但 TaskArtifactUpdateEvent 中为必填） |
| 2026-03-24 | #1681 | Security | `GetTaskPushNotificationConfig` API 会暴露敏感凭证（credentials）！ |
| 2026-03-24 | #1680 | Feature | 取消任务无法立即完成时的响应机制缺失 |

**安全高亮：** Issue #1681 指出推送通知配置 API 会泄露安全凭证，属于 V1.0 规范的安全漏洞，需关注修复进展。

---

### 近期 PRs（Open，按时间排序）

长期挂起的 Open PR 中有多个值得关注的功能提案：

| 日期 | PR | 摘要 |
|------|-----|------|
| 2026-01-19 | #1385 | docs: Add specification versioning guidelines |
| 2025-12-23 | #1322 | docs: AgentCard security configuration and signing examples |
| 2025-11-08 | #1196 | feat: Introduce native Pub/Sub primitives for scalable multi-agent collaboration |
| 2025-10-01 | #1120 | feat: Proposal for bidirectional streaming over gRPC |
| 2025-09-17 | #1079 | feat: Unique identifier for an agent in Agent Card |
| 2025-08-12 | #976 | fix: Comprehensive error handling for gRPC |
| 2025-07-30 | #939 | feat: Add correlation ID support for idempotent task creation |
| 2025-06-30 | #814 | feat: add optional `inputFields` and `outputFields` to `AgentSkill` |
| 2025-05-23 | #642 | feat: open agent discovery under shared base URL via API Catalog |
| 2025-05-06 | #418 | docs: A2A Agent Registrar for Curated Agent Discovery |

---

## ANP 动态

### 近期 Commits（最近 5 条）

| 日期 | SHA | 摘要 |
|------|-----|------|
| 2026-03-05 | 99806f4 | feat: add `failed_msg_id` field to e2ee_error protocol message（允许接收方报告失败的消息 ID）|
| 2026-03-05 | 761087d | add handle feature |
| 2026-03-03 | 1f0abd2 | feat: add `client_msg_id` idempotency + `server_seq` ordering to E2EE IM protocol |
| 2026-03-01 | b1c1c76 | update e2ee protocol |
| 2026-02-27 | eb4a10f | docs: rename signature field `service` → `aud` in DID-WBA spec |

**ANP 观察：** 近期活动集中在 **E2EE（端对端加密）IM 协议**层面的细化，引入幂等性（`client_msg_id`）和服务器端消息有序性（`server_seq`）。DID-WBA 规范字段命名调整（`service` → `aud`）表明身份认证层仍在演进。

### ANP 近期 Issues

| 日期 | Issue | 摘要 |
|------|-------|------|
| 2026-03-22 | #75 | Feature: AgentID 用于网络层 Agent 认证 |
| 2026-03-01 | #74 | 官网文档 404 错误（installation guide） |
| 2025-12-12 | #70 | did:wba format 示例与 DID 文档不兼容 |

**ANP 整体活跃度低于 A2A**，Issue 数量少，以规范细化和文档修复为主。

---

## 对 ACP 影响评估

### 关键发现

1. **A2A V1.0 已正式发布（2026-03-12）**  
   规范已趋于稳定，但发布仅 2 周已暴露出多个 Bug（#1683, #1684, #1685）和一个安全漏洞（#1681）。说明 V1.0 仍处于"稳定但不完善"阶段。ACP 可借此建立更完整的边界情况处理规范。

2. **AgentCard `limitations` 字段提案（#1694）**  
   A2A 社区正在讨论让 Agent 自声明其能力边界。ACP 协议设计中应考虑是否在 Agent 元数据中引入类似的"能力约束声明"机制。

3. **推送通知安全漏洞（#1681）**  
   A2A 的 `PushNotificationConfig` 会暴露敏感凭证。ACP 在设计推送/回调机制时，应将凭证读写权限与查询权限分离，避免相同问题。

4. **CancelTask 语义不完整（#1684, #1680）**  
   A2A 的任务取消机制缺少"异步取消"的状态描述（任务已收到取消请求但还未完成取消）。ACP 在 Task 状态机设计中应明确此中间态（如 `cancelling`）。

5. **ANP 持续强化 E2EE + DID-WBA**  
   ANP 的技术路线更偏向点对点加密通信（E2EE IM）和去中心化身份（DID），与 A2A 的 HTTP/JSON-RPC 中心化路线形成差异化。ACP 若定位于企业内网，可暂不优先支持 DID-WBA，但需预留扩展点。

### 建议

- **短期（dev 轮优先级）：**
  - 在 ACP Task 状态机中补充 `cancelling` 中间状态
  - Review ACP 推送配置 API 的凭证隔离设计
  - 参考 A2A Issue #1694，考虑在 ACP AgentCard 中加入 `limitations` 或 `constraints` 字段

- **中期：**
  - 跟踪 A2A PR #1196（Pub/Sub primitives）和 #1120（双向 gRPC streaming）进展，评估是否纳入 ACP v3.x 路线图
  - 关注 A2A #1681 安全漏洞修复方案，同步审计 ACP 相关设计

---

*报告生成时间：2026-03-27 20:17 CST*  
*数据来源：GitHub API（google-a2a/A2A, agent-network-protocol/AgentNetworkProtocol）*
