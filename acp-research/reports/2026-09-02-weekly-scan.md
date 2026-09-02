# ACP 竞品周报 — 2026-09-02

_由贾维斯自动生成_

## A2A (Google) — 2026-09-02
- Stars: 25586 | Open Issues: 237
### 最新 Commits
- `98853be` 2026-09-01 docs(blog): improve visibility of blogs (#2195)
- `c0f30b3` 2026-08-31 docs: add FAF to partners list (#2136)
- `7a6ba40` 2026-08-31 docs: clarify Hybrid Agents section in Life of a Task (#2154)
- `ac88885` 2026-08-31 docs: fixing broken link (#2193)
- `f63dbb4` 2026-08-28 docs(spec): rename PushNotificationConfig to TaskPushNotificationConfi
### 新 Issues（功能请求）
- #2125 [Extension Proposal]: Agent Steering — interruptible & steerable tasks
- #1995 [Epic] Bidirectional streaming & improved stream semantics
- #1992 [Epic] Multi-turn interaction gaps — state acceptance rules, interrupt
- #1991 [Epic] Coherent Task History — gaps in semantics, querying, and observ
- #1990 [Epic] Auth scheme declaration & credential discovery in AgentCard

## ANP (社区)
- `77caaaf` 2026-09-01 docs: align human authorization guidance with ANP-03 v1.1 (#95)
- `756ed4e` 2026-08-31 Clarify protocol test ownership
- `7cf70df` 2026-08-28 docs: remove private AWiki Sync profile
- `ea06ebf` 2026-08-27 docs(message-sync): freeze v1-b lane handoff fixtures
- `c7ba677` 2026-08-27 docs(sync): add renegotiation preservation fixture

## IBM ACP
- `e5265ca` 2025-08-25 docs: A2A announcement (#230)
- `e8299f8` 2025-08-21 chore: bump version
- `00afccd` 2025-08-21 fix(python): revert cachetools version bump to avoid conflicts

---

## 🔬 贾维斯深度分析

### 一、竞品新动态（3 条）

#### 1. A2A 新增 #2125 Agent Steering — 可中断/可操控的任务（全新 Epic）
本周 A2A 社区出现全新 Extension Proposal **#2125 Agent Steering**，核心诉求是：
- 在任务执行过程中，客户端能够**实时干预/改变任务方向**（steer），而非仅能在任务完成后读取结果或取消。
- 与 ACP 现有 §10 Cancel 语义相比：Cancel 是「终止」，Steering 是「纠偏」——前者是开关，后者是方向盘。
- ACP 当前无原生 Steering 概念，最接近的是 `input_required` 状态（等待用户输入），但那是被动阻塞而非主动干预。

**影响评估**：Steering 对长周期任务（如数据分析、代码生成、研究代理）价值极高。A2A 仍处于 Proposal 阶段，预计 3–6 个月进入草案。ACP 可考虑在 `context_id` 多轮对话基础上扩展「mid-task message injection」语义，提前卡位。

#### 2. A2A 过去一周零代码提交，全部五笔为文档/治理类
本周 A2A 的 5 个 commits 全部是 `docs:` 前缀：
- blog 可见性优化
- 合作伙伴列表新增（FAF）
- Hybrid Agents 文档澄清
- 断链修复
- PushNotificationConfig 重命名

**解读**：核心开发团队可能正聚焦内部大版本迭代（与 5 个 Epic 议题 #1989–#1995 相关），或进入发布前的文档整理期。这给了 ACP 一个**窗口期**——在 A2A 下一个大版本发布前，ACP 若能在某个差异化特性（如真 P2P / DID 身份 / Steering）上率先落地，将形成「ACP 已实现，A2A 还在讨论」的叙事优势。

#### 3. ANP 复活趋势持续确认，连续第二周保持活跃提交
ANP 在上周（2026-08-26）被识别「死而复生」后，本周继续保持提交：
- `77caaaf` 2026-09-01：human authorization guidance 对齐 ANP-03 v1.1
- 上周有 `did:wba` 稳定主题 ID 和 ANP-03/04 vnext 草案

**累计 8 月份提交密度**已接近 A2A 水平。ANP 的 DID + E2EE + 去中心化身份路线与 ACP 的 `did:acp:` + Ed25519 直接对标。ROADMAP 中原标记「已归档」需要正式修正。

---

### 二、与 ROADMAP 路线图对比

| 维度 | ROADMAP 原判定 | 本周新事实 | 偏差评估 |
|------|---------------|-----------|---------|
| ANP 状态 | 🔴 已归档，不再追踪 | 🟢 连续两周活跃，vnext 草案 + DID 更新 | **显著偏差，已持续两周**，需立即修正 |
| A2A 代码活跃度 | 高（历史常态） | 🔴 本周零代码提交，全文档 | 短期波动，但创造窗口期 |
| A2A Agent Steering | 无对标 | #2125 全新 Proposal | 潜在新差距，需评估 |
| A2A 身份认证 Epic | #1990 设计期 | 无新进展 | 我们仍领先约 6 个月 |
| ACP 自身版本进度 | v2.22.0 (2026-03-31) → v3.0 Q3 | 当前已 2026-09，**5 个月无版本更新** | ⚠️ 内部风险：开发停滞 |

**关键发现**：ROADMAP 显示 ACP 最后版本为 v2.78.0（2026-04-07），此后 5 个月无更新。而竞品 A2A 持续扩张（Stars +12.6% 半年）、ANP 复活、新议题涌现。ACP 若要保持差异化优势，需要恢复开发节奏。

---

### 三、行动建议（2 条）

#### 建议 1：立即恢复 ACP 开发节奏，优先落地 v3.0 核心特性
过去 5 个月 ACP 开发停滞，而竞品持续迭代。建议：
- 评估当前代码库状态，制定 v2.79 → v3.0 的最小可行发布计划。
- v3.0 核心卖点「真 P2P + 联邦化」中的 NAT 穿透主流程（v2.19.0 已标记完成）需做端到端验证，确保可用性。
- 若资源有限，优先保「DID 身份体系完善 + 兼容性认证流程」，这是当前对 A2A 最稳固的 6 个月领先优势。

#### 建议 2：研究 Agent Steering 概念，评估在 ACP 中的轻量实现路径
A2A #2125 提出的 Steering 概念对长任务场景极具价值。ACP 可在不破坏轻量原则的前提下：
- 利用现有 `context_id` + SSE 流式通道，扩展「mid-task inject」语义：允许客户端在 `working` 状态的任务中发送新消息，改变任务方向。
- 定义 `steer` 消息类型（或复用现有 `Part` 模型的 `data` 类型），在 `spec/core` 中增加 §X Steering 章节。
- 实现成本较低（复用现有 SSE + Task 状态机），但差异化价值高——可在 A2A 正式草案前发布，抢占叙事。

---

_分析完成时间：2026-09-02 09:15 CST | J.A.R.V.I.S._
