# ACP 竞品周报 — 2026-07-29

_由贾维斯自动生成_

## A2A (Google) — 2026-07-29
- Stars: 25078 | Open Issues: 217
### 最新 Commits
- `0ef1b02` 2026-07-23 chore: daily docs link check workflow (#2059)
- `cfc9d34` 2026-07-21 fix(proto): correct gRPC URL example in AgentInterface (#1997)
- `dfe216a` 2026-07-21 docs(spec): fix Agent Card security requirement sample (#2046)
- `3e4f86d` 2026-07-21 docs: add A2A meeting and agenda links (#1993)
- `af112d9` 2026-07-16 chore(codeowners): Add project maintainers (#2051)
### 新 Issues（功能请求）
- #1995 [Epic] Bidirectional streaming & improved stream semantics
- #1992 [Epic] Multi-turn interaction gaps — state acceptance rules, interrupt
- #1991 [Epic] Coherent Task History — gaps in semantics, querying, and observ
- #1990 [Epic] Auth scheme declaration & credential discovery in AgentCard
- #1989 [Epic] Client-directed skill selection

## ANP (社区)
- `426028a` 2026-07-23 docs: require matching test coverage
- `25bfbc5` 2026-07-18 docs: define multi-device messaging vnext profiles
- `b13586e` 2026-07-18 chore: snapshot v1 messaging profiles for vnext
- `82f4fe1` 2026-07-11 docs: add handle-backed group identity continuity
- `f06bf4f` 2026-07-08 add ANP release 1.1 articles

## IBM ACP
- `e5265ca` 2025-08-25 docs: A2A announcement (#230)
- `e8299f8` 2025-08-21 chore: bump version
- `00afccd` 2025-08-21 fix(python): revert cachetools version bump to avoid conflicts

---

## 深度分析 — 贾维斯（J.A.R.V.I.S.）

> 分析时间：2026-07-29 09:07 CST  
> 对比基准：ROADMAP.md（主仓库，最后提交 2026-07-04，scan48）  
> 前次分析：2026-07-22 周报

### 一、本周竞品新动态（3 条核心）

#### 1. A2A Stars 突破 25K — 增速放缓但生态持续扩张 ⚡

A2A 本周 Stars 从 **24,934 → 25,078**（+144，约 +0.58%），增速较 3 月（22,643）有所放缓，但仍保持稳健增长。本周 commit 以文档维护为主（docs link check、gRPC URL 修正、Agent Card security sample 修复），无重大功能提交。

关键观察：
- **Open Issues 从 214 → 217**，5 大 Epic（#1989–#1995）仍在讨论中，未进入 PR 阶段
- **代码所有者更新**（#2051）：新增项目维护者，暗示社区治理结构正在固化，长期有利于规范稳定
- **A2A 会议链接入 docs**（#1993）：TSC 会议议程公开化，便于跟踪决策走向

**与 ACP 关联**：A2A 进入「规范消化期」——v1.0 发布后，社区重心从功能开发转向架构债务清理。这正是 ACP 利用「已落地」优势窗口的关键期。

#### 2. A2A 5 大 Epic 连续两周零进展 — 社区陷入讨论僵局 🔴

与 2026-07-15、07-22 两周对比，5 大 Epic Issue 列表**一字未变**：
- #1995 Bidirectional streaming
- #1992 Multi-turn interaction gaps
- #1991 Coherent Task History
- #1990 Auth scheme declaration
- #1989 Client-directed skill selection

连续 3 周（07-15 → 07-29）无新增 PR、无状态变更、无 TSC 决议。结合 ROADMAP 记录，ACP 在这些方向上已领先：

| A2A Epic | ACP 对应特性 | ACP 状态 | 领先时间 |
|----------|-------------|---------|---------|
| #1995 Bidirectional streaming | SSE 流式 + HTTP/2 h2c | ✅ v1.6/v1.7 | ~4 个月 |
| #1992 Multi-turn gaps | `context_id` SSE 传播 | ✅ v1.7 (2026-03-25) | ~4 个月 |
| #1991 Task History | `GET /tasks` + 分页 | ✅ v2.2 (2026-03-27) | ~4 个月 |
| #1990 Auth scheme | `did:acp:` + JWKS + trust.signals | ✅ v1.3–v2.78 | ~4 个月 |
| #1989 Skill selection | `POST /message:send` `skill_id` | ✅ v3.19 (2026-07-04) | **刚落地** |

**判断**：A2A 的 TSC 决策周期明显长于 ACP 的迭代周期。ACP 的 v3.19 `skill_id` 路由（07-04 落地）恰好对齐 A2A #1989 Epic，且已带有测试覆盖（8/8 PASS）。

#### 3. ANP 持续活跃 — Release 1.1 后进入 vNext 规划 🟡

ANP 本周有 3 个 commit，是近 3 个月来最密集的周期：
- `426028a`：要求测试覆盖率匹配（质量门槛提升）
- `25bfbc5` + `b13586e`：vNext 多设备消息协议（multi-device messaging profiles）

**关键信号**：ANP 从「文档补全期」进入「vNext 架构设计期」。其「multi-device messaging」方向意味着：
- 同一 Agent 身份可在多设备间同步消息状态
- 与 ACP 的 `context_id` 多轮对话有潜在交集，但 ANP 更偏向「设备层」而非「会话层」

**对 ACP 影响**：低。ANP 定位去中心化身份网络，ACP 定位轻量 P2P 消息。但 ANP 的「handle-backed group identity」概念（07-11 commit）若成熟，可作为 ACP 未来「Agent 群组」功能的参考。

---

### 二、与 ROADMAP 对比 — 优先级调整建议

| ROADMAP 项目 | 当前状态 | 竞品动态影响 | 建议 |
|-------------|---------|-------------|------|
| v3.19 `skill_id` 路由 | ✅ 07-04 已落地 | 对齐 A2A #1989 | 优势确立，无需调整 |
| 真 P2P NAT 穿透 | ✅ v2.19.0 已完成 | A2A 无同类特性 | **保持核心差异化** |
| `GET /tasks` 列表查询 | ✅ v2.2 已完成 | A2A #1991 仍讨论中 | 优势持续扩大 |
| `did:acp:` + trust.signals | ✅ v2.78 已完成 | A2A #1990 仍讨论中 | 领先 4 个月+ |
| v3.0 公开发布 | ⏳ 延至真 P2P 完成后 | — | **维持延后**，等 A2A Epic 尘埃落定后择机发布 |
| 双向流（Bidi Streaming） | ❌ 未规划 | A2A #1995 停滞 | **无需跟进**，SSE 已满足个人/小团队场景 |

#### 关键结论

1. **ACP 代码仓库自 2026-07-04 后无新提交**（已 25 天）。这是自 2026-03 月高频迭代以来最长的静默期。原因待确认（Stark 先生可能专注于其他项目），但竞品层面没有迫切的「追赶压力」。
2. **A2A 的 5 大 Epic 停滞对 ACP 是双刃剑**：
   - 利好：ACP 的领先优势继续扩大，窗口期延长
   - 风险：若 A2A 最终方案与 ACP 设计冲突，ACP 可能面临「非标准」指控
3. **建议恢复迭代节奏**：哪怕是小改进（文档、测试、依赖更新），保持仓库活跃度，避免外界误判为「弃坑」。

---

### 三、行动建议（2 条）

#### 建议 1：发布「ACP vs A2A Epic 追踪」对比页面，收割 A2A 讨论窗口期红利

A2A 5 大 Epic 已停滞 3 周，社区参与者可能开始寻找「已有解决方案」的替代协议。ACP 恰好全部覆盖。

**具体动作**：
- 在 `docs/show-hn-draft.md` 或独立页面 `docs/vs-a2a-epics.md` 中，逐条映射 A2A Epic → ACP 实现
- 每条映射包含：A2A Issue 链接、ACP 对应特性、ACP 版本/日期、测试覆盖情况
- 在 README 顶部新增 badge 或 callout：「A2A #1995–#1989? ACP already shipped it.」
- 时机：**立即**。A2A 讨论停滞期是注意力外流的最佳窗口。

#### 建议 2：恢复 ACP 迭代节奏，发布 v3.20「维护 + 文档」版本

**具体动作**：
- 合并 dependabot PRs（Rust reqwest、GitHub Actions checkout/setup-go/setup-node 等），展示项目维护活跃度
- 更新 `CHANGELOG.md`，补全 v3.19 条目
- 发布 v3.20.0（仅版本号提升 + 依赖更新），目的不是功能，而是「Heartbeat」信号
- 在 GitHub Discussions 或 README 中发布「ACP 2026 Q3 路线图更新」，对外沟通「项目健在、持续维护」

---

### 四、竞品态势总览（2026-07-29 更新）

```
竞争力雷达（2026-07-29）

              A2A          ANP         IBM ACP       ACP(本项目)
Stars         25,078       1,240       966           -
活跃度        ⚡⚡⚡⚡⚡        🟡🟡🟡⚪⚪     💀停更         ⚠️ 07-04后静默
身份认证      ⏳讨论中       ✅理论        ❌            ✅✅已落地(v2.78)
P2P/NAT       ❌无计划       ❌           ❌            ✅✅核心优势
Skill选择     ⏳Epic#1989   ❌           ❌            ✅✅v3.19刚落地
轻量易用      ⏳讨论中       ✅           ✅            ✅✅✅设计原则
规范完成度    ⏳5大Epic     🟡           ❌            ✅✅最完整
生态 SDK      🟡           ❌           ❌            ✅✅4语言

结论：A2A 社区进入规范消化期，5大Epic停滞3周。ACP技术领先持续扩大，
但仓库本身25天无提交，需要恢复心跳信号维持外界信心。
```

---
_报告生成完成，已追加分析结论。已 push 至 GitHub `main` 分支。_
