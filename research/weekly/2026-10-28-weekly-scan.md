# ACP 竞品周报 — 2026-10-28

_由贾维斯自动生成_

## A2A (Google) — 2026-10-28
- Stars: 26315 | Open Issues: 298
### 最新 Commits
- `8969939` 2026-10-27 docs: add LF Projects antitrust policy (#2395)
- `98279d6` 2026-10-20 chore: Add Bloomberg as a member of the Technical Steering Committee (
- `1205f45` 2026-10-15 chore(deps): bump the github-actions group across 1 directory with 4 u
- `6b66881` 2026-10-15 docs: add CUGA to A2A community Integrations (#2345)
- `5eced49` 2026-10-15 docs: add Agent Commons to partners list (#2338)
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

## 深度分析（贾维斯，2026-10-28）

### 1. A2A — 治理升级进入 LF 基金会轨道，v1.1 特性集收敛

- **治理层面重大信号**：`8969939` 合入 LF Projects antitrust policy，加上上周 Bloomberg 加入 TSC（`98279d6`）——A2A 正式向 Linux 基金会中立治理模型靠拢。这意味着后续 A2A 的 spec 演进会有更正式的流程和更强的企业背书，ACP「小快灵」的差异化打法窗口依然存在，但时间在变贵。
- **v1.1 特性集收敛**：老牌 Epic 集中冒头（#1987–#1990 均为 2026 年中开的老 Epic）：
  - **#1987 Idempotency & safe retries**：A2A 仍在 Epic 讨论阶段；**ACP 自 v0.5 已落地** `message_id` 客户端生成 + `server_seq` 有序 + v1.1 的 `failed_message_id` 回传，这是一个「已领先但没宣传」的点，建议立即写入 README 差异化表。
  - **#1990 Auth scheme declaration & credential discovery in AgentCard**：A2A 把身份/凭证发现搬进 AgentCard。ACP 已有 Ed25519+DID+`card_sig`+JWKS 全链路，无需跟进实现，但建议在 spec 中加一小节声明 ACP 的 auth 发现路径（`/.well-known/did.json` + `jwks.json`），对齐读者预期。注意红线：不引入 OAuth。
  - **#1988 Push-notification config**：红线已明确不跟进，维持。
  - **#1989 Client-directed skill selection**：与 ACP `QuerySkill()` 对位，ACP 已有基础实现，暂不需动作。
- **#2125 Steering 仍居 enhancement 榜首**，已挂 `v1.1-candidate`——ROADMAP 中 P0 冲刺方向判断正确，时间压力确认。

### 2. ANP — DID 战线加速，领先窗口进一步收窄

- `4aa8664`（2026-10-22）：**ANP-05 DID 与标准 CIMD client 关联**——ANP 不但在做 DID，还在向标准客户端生态靠拢，可互操作性进展实质化。auth draft 同期更新（`6683793`）。
- ROADMAP 判断更新：原「P2 DID 互操作 spike，排期紧随 Steering 之后」的优先级判断成立但**紧迫度上升**。若 Steering 两周内交付，spike 应提前启动，否则 `did:acp:` 的先发叙事（README 核心卖点之一）会被 anp05 反超。

### 3. IBM ACP — 确认战略性放弃

- 最后一次实质更新停留在 2025-08（A2A 发布公告）。本周建议：从「参考即可」降级为「停止逐周扫描 git log，仅保留季度回顾」，把扫描预算让给 A2A/ANP 深度项。

### 结论与行动建议

1. **确认 P0**：Steering Extension（`urn:acp:ext:steering/v1`）保持本月冲刺不变，deadline 维持 2–3 周内出 spec 草案，目标仍是抢在 A2A v1.1 发布前。A2A 治理正规化后发布节奏只会更快，先发窗口比预想更短。
2. **零成本差异化（本周可做）**：针对 A2A #1987（幂等仍是 Epic），在 README vs-A2A 对比表新增「Idempotency & safe retries」一行，声明 ACP 自 v0.5 起的完整方案（message_id + server_seq + replay-window + failed_msg_id）。纯文档工作，1 小时内完成，直接收割心智份额。
3. **P2 提级评估**：ANP DID 互操作 spike（`did:acp:` vs `anp-05` DID 文档对比，一页评估）建议从「Steering 之后」提前为「与 Steering 并行的文档级 spike」，不占开发带宽。
4. **降本**：IBM ACP 扫描降频至季度。
