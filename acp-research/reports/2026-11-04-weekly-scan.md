# ACP 竞品周报 — 2026-11-04

_由贾维斯自动生成_

## A2A (Google) — 2026-11-04
- Stars: 26411 | Open Issues: 297
### 最新 Commits
- `4735f48` 2026-10-30 docs: removing broken link (#2413)
- `d924e07` 2026-10-29 docs: fixing partner link (#2368)
- `8969939` 2026-10-27 docs: add LF Projects antitrust policy (#2395)
- `98279d6` 2026-10-20 chore: Add Bloomberg as a member of the Technical Steering Committee (
- `1205f45` 2026-10-15 chore(deps): bump the github-actions group across 1 directory with 4 u
### 新 Issues（功能请求）
- #2125 [Extension Proposal]: Agent Steering — interruptible & steerable tasks
- #1990 [Epic] Auth scheme declaration & credential discovery in AgentCard
- #1989 [Epic] Client-directed skill selection
- #1988 [Epic] Push-notification config — security & semantics
- #1987 [Epic] Idempotency & safe retries

## ANP (社区)
- `0837cfd` 2026-10-22 Remove scheduled workflow triggers
- `9001338` 2026-10-22 Merge pull request #107 from agent-network-protocol/docs/anp05-cimd-di
- `4aa8664` 2026-10-22 docs: associate ANP-05 DIDs with standard CIMD clients
- `6683793` 2026-10-15 update auth draft
- `01c481d` 2026-10-14 Merge release/0929 into main for the October 14 release

## IBM ACP
- `e5265ca` 2025-08-25 docs: A2A announcement (#230)
- `e8299f8` 2025-08-21 chore: bump version
- `00afccd` 2025-08-21 fix(python): revert cachetools version bump to avoid conflicts

## 深度分析（贾维斯，2026-11-04）

### 1. A2A — 本周纯治理例行公事，v1.1 窗口静默压缩

- 本周三个 commit（`4735f48`/`d924e07`/`8969939`）全部是文档修链、链接修复、antitrust 政策类杂务，**零新特性动作**。但结合前两周信号（Bloomberg 入 TSC、LF 治理落地、#2125 挂上 `v1.1-candidate`），判断是 **v1.1 发布前的静默期**：核心团队大概率在 v1.1 分支/内部评审中，公开仓库只做维护性提交。
- **这对 ACP 是利好也是警报**：利好在于 Steering spec 草案的先发窗口仍然开着；警报在于静默期往往意味着即将有大动作，**A2A v1.1（含 Steering）可能在 2–6 周内落地**。
- Enhancement 榜（#2125/#1990/#1989/#1988/#1987）与上周完全一致，无新增热门议题——进一步佐证「讨论已收敛、进入实现阶段」的判断。
- Stars 26,411（+96/周），增速平稳，无异常。

### 2. ANP — ANP-05 DID 生态绑定完成，双周节奏固化

- 10-22 一批提交（`0837cfd`/`9001338`/`4aa8664`）后，本周无新动作，符合自 9 月以来的双周发布节奏（10-14 → 10-22 两波）。
- 关键点重申：`anp-05` DID 已与标准 **CIMD client** 关联（上周合入）——ANP 的 DID 互操作不再只是文档格式，而是**有真实客户端生态承接**。`did:acp:` 的先发叙事压力为实打实的两周一个台阶。
- **判断维持上周结论但紧迫度 +1**：DID 互操作 spike（`did:acp:` vs `anp-05` DID 文档一页对比）必须与 Steering 冲刺**并行**启动，不能再排在其后。若 Steering 草案因任何原因跳票，DID spike 是唯一能保住「身份领先」心智的备用叙事。

### 3. IBM ACP — 停更确认（第 3 个月）

- 最新 commit 仍是 2025-08-25。上周已建议降频为季度回顾，本周维持执行：**从 weekly-scan.sh 输出中保留但不再逐条分析**，下一条有效信息预计要等季度回顾。

### 结论与行动建议（2026-11-04）

1. **P0 维持 + 警报升级**：Steering Extension（`urn:acp:ext:steering/v1`）保持本月冲刺。上周定的「2–3 周内出 spec 草案」deadline **本周必须收紧为 ≤2 周**——A2A 静默期 + `v1.1-candidate` 标签是最强的倒计时信号，先发窗口随时可能关闭。最小实现路径不变：复用 `input_required` 状态机 + 新增 `POST /tasks/{id}/steer`。
2. **P2 → P1 提级执行**：DID 互操作 spike 本周立即启动（文档级工作，不占开发带宽）：`did:acp:` W3C DID Document vs ANP-05 DID 文档逐字段对比 + CIMD client 兼容性评估，产出一页评估文档。ANP 的双周节奏意味着我们每拖两周，就落后一个台阶。
3. **零成本差异化（上周建议 #2 核销检查）**：上周建议的 README「Idempotency & safe retries」对比行，本周扫描仍未在 A2A 侧看到落地动作（#1987 仍是 Epic）——若该文档工作已完成，核销；若未完成，本周补上，这是对 A2A 静默期最廉价的舆论占位。
4. **扫描降本执行确认**：IBM ACP 分析段落自本周起进入「季度回顾模式」，weekly-scan.sh 中 git log 保留（历史对账用），深度分析不再覆盖。

### ROADMAP 维护备注

- ROADMAP「最后更新」标记建议从 2026-10-07 更新至 2026-11-04：A2A 静默期判断 + Steering deadline 收紧至 ≤2 周 + DID spike 提级为 P1 并行启动。
- 下周扫描重点：A2A 是否破静默（v1.1 分支动作或 release notes）、ANP 双周窗口（11-05 前后）是否有新提交。
