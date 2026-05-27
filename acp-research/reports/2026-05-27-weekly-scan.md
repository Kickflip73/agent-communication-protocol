# ACP 竞品周报 — 2026-05-27

_由贾维斯自动生成_

## A2A (Google) — 2026-05-27
- Stars: 24013 | Open Issues: 265
### 最新 Commits
- `cd87b93` 2026-05-26 docs: add multi-tenancy guide and clarify tenant field semantics (#184
- `8ecf8e8` 2026-05-26 docs: update SDK count to 6 (added Rust) and resolve lint violations (
- `dc7cf37` 2026-05-23 docs(fix): align push notification auth examples with protocol behavio
- `e997516` 2026-05-19 fix: TaskStatus values in the specification (#1801)
- `26818eb` 2026-05-19 docs: remove deprecated stateTransitionHistory references (#1834)
### 新 Issues（功能请求）
- #1811 [Feat]: Add TaskMessageUpdateEvent to notify observers when messages a
- #1794 [Feat]: Add generation/version number field to Task for event ordering
- #830 [Feat]: OAuth 2.1-compliant Authorization for A2A
- #563 [Feat]: Support multi-agent composition by registering HostAgent via c

## ANP (社区)
- `b15ec29` 2026-05-13 Make the AP2 analysis available to English readers
- `aabc276` 2026-05-13 Make the IM protocol upgrade accessible to English readers
- `28c7dd4` 2026-05-13 add blogs
- `5f01846` 2026-04-22 add message protocol flow chart
- `cf38083` 2026-04-15 docs: sync WNS spec updates

## IBM ACP
- `e5265ca` 2025-08-25 docs: A2A announcement (#230)
- `e8299f8` 2025-08-21 chore: bump version
- `00afccd` 2025-08-21 fix(python): revert cachetools version bump to avoid conflicts

## 🔍 贾维斯深度分析（2026-05-27 09:06）

### 一、竞品动态总览

#### A2A（Google）— 本周关键动态

**1. 多租户架构正式落地（#1848, commit cd87b93）⚡ 重要**
- A2A 将 `tenant` 字段从 "Tenant ID" 重命名为 **"Opaque routing identifier"**
- 语义变更：从「租户隔离」弱化为「路由标识符」，协议层不定义格式或语义
- 影响范围：AgentInterface、TaskPushNotificationConfig、SendMessageRequest、GetTaskRequest、ListTasksRequest、CancelTaskRequest 等全部核心消息
- **贾维斯评估**：这是 A2A 向企业级多租户方向的关键一步。虽然语义被弱化（避免协议过度设计），但 `tenant` 字段已渗透到所有 API，说明 Google 内部（可能 Gemini/AgentSpace）有强需求驱动。ACP 的定位是个人/小团队，**不需要跟进此特性**——这反而强化了我们的差异化。

**2. SDK 生态扩展至 6 种语言（commit 8ecf8e8）📦**
- 新增 **Rust SDK**，SDK 总数达到 6 种
- 同时修复了文档 lint 问题
- **贾维斯评估**：ACP 已有 Python/Node/Go/Rust 四种 SDK（v1.2 完成），与 A2A 的 SDK 覆盖面差距在缩小。A2A 多出的主要是 Java 和 .NET——企业级语言。ACP 不需要刻意追赶数量，当前矩阵已覆盖主流开发者群体。

**3. TaskStatus 规范修复 + Push Notification 认证对齐（commits e997516, dc7cf37）🔧**
- TaskStatus 枚举值在 spec 中修正（#1801）
- Push Notification 认证示例与协议行为对齐
- **贾维斯评估**：常规维护性提交。A2A 在持续打磨规范质量，但无突破性变化。

**4. 新 Issue 值得关注：**
- **#1811 [Feat] TaskMessageUpdateEvent**：提议新增事件类型通知观察者消息更新——ACP 已有 SSE context_id 传播机制（v1.7），类似能力已具备
- **#1794 [Feat] generation/version number field for Task**：为 Task 增加版本号用于事件排序——ACP 可借鉴，用于离线队列消息排序
- **#830 OAuth 2.1 Authorization**：仍在讨论中（长期 Issue），ACP 设计禁忌明确排除 OAuth ✅

#### ANP（社区）
- 最后活跃 **2026-05-13**，更新内容为英文翻译和 IM 协议流程图
- 活跃度极低，基本处于维护模式
- **结论：继续不追踪**

#### IBM ACP
- 最后活跃 **2025-08-25**，停更已超过 **9 个月**
- **结论：仅作参考，无需投入研究资源**

---

### 二、路线图对比 & 优先级评估

| A2A 本周动态 | ACP 现状 | 需要调整？ |
|---|---|---|
| 多租户 tenant 字段全覆盖 | 无（且设计禁忌排除多租户） | ❌ 不需要 |
| Rust SDK 上线 | ✅ 已有（v1.2, sdk/rust/） | ❌ 已领先 |
| TaskMessageUpdateEvent 提案 | ✅ SSE 事件机制已有（v1.7） | ❌ 已具备 |
| Task version number 提案 (#1794) | ⚠️ 离线队列缺少版本排序 | 🟡 可借鉴 |
| OAuth 2.1 讨论 (#830) | ✅ 设计明确排除 | ❌ 坚持不动摇 |

**路线图结论：本周无需调整 ROADMAP.md 优先级。** ACP 当前 v2.77 的 trust/capability token 体系（SINT quad complete）在技术深度上领先 A2A 社区讨论约 2-4 周。A2A 的多租户方向与我们轻量 P2P 定位正交，不构成竞争压力。

---

### 三、行动建议

#### 📋 本周建议执行项（2 条）

**1. 【P2 可选】为离线队列消息增加 `version` 序号字段**
- 灵感来源：A2A #1794（Task generation/version for event ordering）
- 实现方式：在 Offline Delivery Queue 的每条消息上加 `version: int` 单调递增序号
- 收益：peer 重连后 flush 离线消息时，接收方可检测消息顺序和丢失
- 工作量：~2h（改 OQ 数据结构 + 5 个测试用例）
- 优先级：P2（enhancement，不影响现有功能正确性）

**2. 【观察】持续追踪 A2A 多租户文档演进**
- A2A #1848 只是第一步（字段重命名+语义澄清），后续大概率会出现：
  - Tenant isolation best practices 文档
  - Tenant-scoped AgentCard 发现
  - 可能的 Tenant auth 中间件提案
- 行动：每周 scan 时增加对 `tenant`/`multi-tenancy` 关键词的 grep 监控
- 目的：确保 ACP 在被问及"是否支持企业场景"时有清晰的差异化话术

#### 📊 竞品健康度评分（周环比）

| 协议 | 活跃度 | 创新速度 | 与 ACP 竞争重叠 | 趋势 |
|------|--------|----------|----------------|------|
| A2A | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐（企业场景） | → 企业化加速，与 ACP 正交 |
| ANP | ⭐ | ⭐ | ⭐ | → 接近死亡 |
| IBM ACP | ☆ | ☆ | ⭐ | → 已停止呼吸 |

---

*分析完成时间：2026-05-27 09:08 CST*
*分析引擎：J.A.R.V.I.S. v2.7.0-research*
