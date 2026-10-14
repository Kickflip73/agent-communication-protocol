# ACP 竞品周报 — 2026-10-14

_由贾维斯自动生成_

## A2A (Google) — 2026-10-14
- Stars: 26138 | Open Issues: 279
### 最新 Commits
- `7c861a5` 2026-10-12 docs(spec): make the 8.4.1 canonicalization example a valid Agent Card
- `12e9d2f` 2026-10-07 docs: replace removed A2AStarletteApplication and v0.3 TaskState names
- `523c526` 2026-10-07 docs: add MusedIn to partners list (#2294)
- `2133c2b` 2026-10-07 docs: add Agent Commerce Gateway to partners list (#2299)
- `3fabd23` 2026-10-07 docs: add ADEXTO to partners list (#2303)
### 新 Issues（功能请求）
- #2125 [Extension Proposal]: Agent Steering — interruptible & steerable tasks
- #1995 [Epic] Bidirectional streaming & improved stream semantics
- #1992 [Epic] Multi-turn interaction gaps — state acceptance rules, interrupt
- #1991 [Epic] Coherent Task History — gaps in semantics, querying, and observ
- #1990 [Epic] Auth scheme declaration & credential discovery in AgentCard

## ANP (社区)
- `c6a467b` 2026-10-01 Merge pull request #97 from agent-network-protocol/alert-autofix-1
- `31ce828` 2026-10-01 Merge pull request #104 from agent-network-protocol/feature/anp05-root
- `6c0cf06` 2026-10-01 docs: reframe white paper platform and openness sections
- `b3772f8` 2026-10-01 fix: repeat HTML tag stripping in release doc anchor slugs
- `eeab088` 2026-10-01 Merge branch 'main' into alert-autofix-1

## IBM ACP
- `e5265ca` 2025-08-25 docs: A2A announcement (#230)
- `e8299f8` 2025-08-21 chore: bump version
- `00afccd` 2025-08-21 fix(python): revert cachetools version bump to avoid conflicts

---

## 深度分析（贾维斯 · 2026-10-14）

### A2A (Google) — 本周显著降温，Steering 窗口仍开放
- **Spec 层零变化**：10-07 → 10-12 仅 5 个 docs 类 commit（AgentCard 规范化示例修正、partners 列表扩充），无 spec/SDK 变更。
- **#2125 Steering**（v1.1-candidate）：本周 **0 新评论**（issue 更新停在 2026-09-01），社区方案尚未收敛，正式 spec 未落地。先发窗口仍在，但 v1.1-candidate 标签意味着窗口可能在 1-2 个月内随 v1.1 发布关闭。
- **新 Epic 议题群**（#1990–1995：auth scheme 声明、双向流式、多轮状态接受规则、任务历史语义）表明 A2A 核心语义仍未稳定——印证 ACP "轻量、核心语义先行" 的差异化路线正确。
- **生态信号**：partners 新增 Agent Commerce Gateway / MusedIn / ADEXTO，商业结算赛道持续升温，维持红线（x402 支付不跟进）。

### ANP (社区) — v0.5 工作区落地，DID 窗口继续收窄
- `anp05-root`（PR #104）已于 10-01 合入 main，ANP v0.5 协议工作区正式建立；白皮书重构 platform/openness 章节。
- 对 ACP 的直接影响：ANP 的 DID 认证叙事从"规划"变为"落地"，我们 `did:acp:` 的 2-3 个月领先窗口进一步收窄，DID 互操作 spike 不宜再拖。

### IBM ACP — 确认停更
- 最近 commit 停留在 2025-08-25，连续 14 个月无活动。建议从每周扫描的重点对象降级为"仅记录"，节省扫描噪音。

### 路线图对照结论
- ROADMAP 的 Steering 冲刺（P1）判断依然成立且时间敏感，无需调整优先级。
- P2 DID 互操作 spike（vs ANP v0.5）应紧随其后启动。
- 无需借鉴的新特性：A2A 本周无 spec 级新增；ANP v0.5 细节待 spike 时评估。

## 本周行动建议
1. **【P1 · 保持】Steering Extension 本周出 spec 草案**：`spec/steering-extension-v1.md`，URI `urn:acp:ext:steering/v1`，双模式（interruptible / steerable），复用现有 `input_required` 状态 + 新增 `POST /tasks/{id}/steer`，复刻 limitations（A2A #1694）的先发落地打法，抢在 A2A v1.1 发布前发布。
2. **【P2 · 启动】DID 互操作 spike**：对比 ANP `anp-02` DID 文档格式与 `did:acp:` W3C DID Document，产出 1 页评估报告；同时将 IBM ACP 从 weekly-scan 重点降级为仅记录。
