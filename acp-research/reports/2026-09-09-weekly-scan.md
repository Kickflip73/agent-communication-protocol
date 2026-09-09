# ACP 竞品周报 — 2026-09-09

_由贾维斯自动生成_

## A2A (Google) — 2026-09-09
- Stars: 25696 | Open Issues: 247
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

## 本周行动建议
_(需贾维斯人工分析后补充)_

---

# 贾维斯深度分析 — 2026-09-09

## 竞品新动态（Top 3）

### 1. A2A 五大 Epic 议题同期爆发，聚焦「流式 + 身份 + 可操控性」
A2A 社区在 2026-08 底至 09 初集中提出了 5 个 Epic 级议题（#1990–#1995 + #2125），涵盖：
- **AgentCard 认证方案声明**（#1990）：与 ACP DID/Ed25519 身份体系直接对标
- **双向流式传输**（#1995）：A2A 当前 SSE 单向，欲补全双向实时通道
- **多轮交互 & 任务历史**（#1991–#1992）：补全状态机缺口，与 ACP context_id + Task 状态机同源
- **Agent Steering**（#2125）：可中断 + 可引导的任务执行，超越单纯的 cancel 语义

**判断**：A2A 正在从「企业级 Agent 总线」向「全功能 Agent 操作系统」进化，功能广度在扩张，但复杂度同步攀升。ACP 的轻量定位反而形成差异化护城河。

### 2. A2A Stars 25,696，社区仍在高速膨胀
自 2026-03-19（22,643 Stars）以来，A2A 增长 **+3,053 Stars（+13.5%）**，月均 ~500 Stars。作为对比，ACP 无公开 Stars（私有开发），但 A2A 的高热度说明 Agent-to-Agent 通信赛道正在进入主流视野，**窗口期仍在**。

### 3. IBM ACP 实质死亡，ANP 归档后仅剩文档维护
IBM ACP 最后提交 2025-08-25，已停更多年，可正式从追踪列表移除。ANP 虽然归档，但 2026-09 仍有文档提交（human authorization guidance 对齐），说明社区仍有零星维护，但不再具备竞争力。

**→ 结论：双竞品格局（A2A vs ACP）已确立，ANP/IBM 退出牌桌。**

## 与 ROADMAP 对比 & 优先级判断

| A2A 新动向 | ACP 现状 | 差距判断 |
|-----------|---------|---------|
| #1990 AgentCard Auth 声明 | ✅ DID + Ed25519 + JWKS 兼容层（v2.18） | **领先 2–3 个月** |
| #1995 双向流式 | ⚠️ SSE 单向（server→client） | **有缺口，但非 P0** |
| #1992 多轮交互 / #1991 Task History | ✅ context_id SSE 传播（v1.7）+ `GET /tasks` 分页（v2.2） | **已覆盖核心需求** |
| #2125 Agent Steering | ✅ Cancel 语义（v1.5.2），但无「引导/调整」能力 | **部分领先，部分可扩展** |

### 路线图调整建议

**1. 暂不跟进「双向流式」（#1995）→ 维持 P2/P3 优先级**
- ACP 的 SSE 单向流式已满足 90% 场景（任务状态推送、artifact 流）
- 双向流式会显著增加传输层复杂度（WebSocket / gRPC），与「轻量」设计原则冲突
- **行动**：保持观察，若 A2A 成为事实标准再评估兼容层

**2. 扩展 Cancel 语义 → 「Task Steering」轻量提案（P1）**
- A2A #2125 提出的「steerable tasks」概念有价值：不仅是取消，还包括「变更目标」「注入新 input」「分支子任务」
- ACP 可在现有 Task 状态机（5 种状态）基础上，增加 `steering` 消息类型，无需打破状态机
- **行动**：起草 `spec/task-steering-v2.x.md`，作为 v2.24+ 候选特性

**3. 身份体系对标 A2A #1990 → 发布「ACP Identity 互操作白皮书」（P1）**
- A2A 正在讨论 AgentCard 中的 auth scheme declaration，ACP 已实现的 DID + JWKS 兼容层（v2.18）正好可输出为对标文档
- 提升 ACP 在企业/混合场景的可信度
- **行动**：撰写 `docs/interop/a2a-identity-mapping.md`，展示 ACP ↔ A2A 身份互操作路径

## 最终行动建议（2 条）

1. **启动 Task Steering 规范草案** — 将 ACP v1.5.2 的 Cancel 语义扩展为「任务引导」能力（steer/inject/branch），对标 A2A #2125，保持 ACP 在任务控制层面的领先性。预计投入：1 个开发轮（3–4 天）。

2. **输出 ACP Identity 互操作白皮书** — 将 v2.18 JWKS 兼容层 + DID 体系整理为 `docs/interop/a2a-identity-mapping.md`，向 A2A 社区展示 ACP 身份方案的前瞻性和兼容性，争取混合部署场景的话语权。预计投入：1–2 天文档工作。

> 下周扫描重点：关注 A2A #1990 和 #2125 的 TSC 讨论进展，以及是否有 PR 提交。

---
_分析完成时间：2026-09-09 09:07 CST | J.A.R.V.I.S. 自动研究系统_
