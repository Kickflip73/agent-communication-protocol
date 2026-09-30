# ACP 竞品周报 — 2026-09-30

_由贾维斯自动生成_

## A2A (Google) — 2026-09-30
- Stars: 25966 | Open Issues: 264
### 最新 Commits
- `1ae57a6` 2026-09-29 docs(spec): fix link-checker findings and re-enable partners.md checki
- `72b3761` 2026-09-25 docs: add x402-list to partners (#2202)
- `43e0c87` 2026-09-22 docs: add MolTrust to partners (#2252)
- `afda831` 2026-09-16 docs: update roadmap (#2237)
- `6d6640c` 2026-09-10 docs: improve readability and wording in life-of-a-task (#2226)
### 新 Issues（功能请求）
- #2125 [Extension Proposal]: Agent Steering — interruptible & steerable tasks
- #1995 [Epic] Bidirectional streaming & improved stream semantics
- #1992 [Epic] Multi-turn interaction gaps — state acceptance rules, interrupt
- #1991 [Epic] Coherent Task History — gaps in semantics, querying, and observ
- #1990 [Epic] Auth scheme declaration & credential discovery in AgentCard

## ANP (社区)
- `de99d26` 2026-09-28 docs: add release status heading to READMEs
- `6e9216a` 2026-09-28 docs: adjust README introduction formatting
- `1891480` 2026-09-28 docs: move release notes after contributors
- `711bb29` 2026-09-24 Align ANP copyright notices with community attribution
- `21bd928` 2026-09-24 docs: consolidate vNext protocol workspace

## IBM ACP
- `e5265ca` 2025-08-25 docs: A2A announcement (#230)
- `e8299f8` 2025-08-21 chore: bump version
- `00afccd` 2025-08-21 fix(python): revert cachetools version bump to avoid conflicts

## 贾维斯深度分析（2026-09-30）

### 一、竞品新动态解读

**1. A2A — 生态接入 Agent 支付（x402），规格层无实质变更**
- 核心动态：`x402-list` 加入官方 partners（#2202，09-25）。x402 是基于 HTTP 402 状态码的 Agent 原生支付协议，这标志着 A2A 生态开始向 **Agent 商业化/结算** 赛道延伸——Agent 之间不仅通信，还要交易。
- 规格层：`1ae57a6`（09-29）仅是 spec 链接检查修复 + partners.md 检查重启用，属仓库治理性变更，**无破坏性影响**。
- 增长信号：Stars 25895 → 25966（+71/周，平稳）；enhancement 榜单与上周完全一致（#2125 Agent Steering 仍居首），说明社区处于「吸收期」，无新方向性提案。
- 判定：**Agent 支付与 ACP 轻量 P2P 定位不符，观察不跟进**（处理方式同原生 Pub/Sub，记入暂不跟进清单）。

**2. ANP — vNext 协议工作区整合，酝酿下一版本**
- 核心动态：`21bd928`（09-24）"consolidate vNext protocol workspace"——ANP 正在整合 vNext 协议工作区，配合本周一批 README/release-status 工程化整理，**疑似在酝酿下一版协议**。
- 复活势头延续（anp-02 DID 认证 09-10 落地后），但本周无协议实质变更。
- 判定：升级观察等级。若 ANP vNext 涉及 DID 互操作新格式，将直接影响我们 `did:acp:` 的差异化窗口（当前判断领先约 1-2 个月，仍在收窄）。

**3. IBM ACP — 停更超过 13 个月，维持「参考即可」降级**
- 最新 commit 仍停留在 2025-08-25，无任何新动态。维持每月扫一次即可，无需投入。

### 二、路线图对照结论

| 检查项 | 结论 |
|--------|------|
| 现有优先级是否需要调整？ | **无需大调**。v1.4 NAT 穿透收尾（打洞集成测试）+ v3.0 公开发布两条主线仍正确 |
| 上周建议执行情况 | ⚠️ 上周 P1 建议（Steering Extension spec 草案）尚未体现在 ROADMAP（其最后更新停在 2026-09-16），**本周应正式立项并更新 ROADMAP** |
| 是否需要借鉴新特性？ | 无新可借鉴项。#2125 Steering 仍是最值得先发的方向；x402 支付判定为不跟进 |
| 新增观察项 | ① ANP vNext 协议工作区整合（升级观察）；② x402/Agent 支付生态（低优先观察，仅记录行业信号） |
| 风险 | ANP vNext 若在 DID 互操作上出新格式，我们的 W3C DID Document 兼容层需快速响应——DID 互操作 spike（上周 P2）不宜再拖 |

### 三、行动建议（本周执行项）

1. **【P1】Steering Extension 正式立项 + spec 草案**：#2125 连续两周居 A2A enhancement 榜首，而 A2A 规格层本周零动作——**先发窗口仍开着**。落地 `urn:acp:ext:steering/v1`：基于现有 `input_required` 状态 + 新增 `POST /tasks/{id}/steer`（运行中任务注入指令/中断），零破坏性；同步更新 ROADMAP（复刻 limitations #1694 次日落地打法）。
2. **【P2】DID 互操作 spike 排期 + ANP vNext 观察哨**：本周完成 ANP `anp-02` DID 文档格式 vs `did:acp:` W3C DID Document（`/.well-known/did.json`）字段对比的一页评估；同时在 weekly-scan 中为 ANP vNext 建立跟踪条目，防止其大版本发布后我们陷入被动。

---

_分析：贾维斯 J.A.R.V.I.S. · 2026-09-30 周报轮_
