# ACP 竞品周报 — 2026-11-11

_由贾维斯自动生成_

## A2A (Google) — 2026-11-11
- Stars: 26481 | Open Issues: 309
### 最新 Commits
- `9fff3e0` 2026-11-05 docs: publish the a2a-cli OAuth Client ID Metadata Document (#2405)
- `4735f48` 2026-10-30 docs: removing broken link (#2413)
- `d924e07` 2026-10-29 docs: fixing partner link (#2368)
- `8969939` 2026-10-27 docs: add LF Projects antitrust policy (#2395)
- `98279d6` 2026-10-20 chore: Add Bloomberg as a member of the Technical Steering Committee (
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

## 深度分析（贾维斯，2026-11-11）

### 1. A2A — v1.1 静默期第 3 周，CLI OAuth 元数据落地

- 本周仅 1 个新 commit：`9fff3e0`（2026-11-05）发布 **a2a-cli OAuth Client ID Metadata Document**（#2405）。这是老 Epic **#1990「Auth scheme declaration & credential discovery in AgentCard」的首个可交付成果**——A2A 的认证路线已明确收敛到 OAuth 2.0 客户端元数据（RFC 7591 风格），CLI 工具先行落地。
- 其余全部为文档杂务（broken link / partner link / antitrust policy）。自 10-15 以来 **3 周无任何实质特性 commit**，v1.1 发布前静默期判断成立且在延长——核心团队大概率仍在内部评审。
- Enhancement 榜前 5 与上周完全一致，**#2125 Steering 仍居榜首、仍挂 `v1.1-candidate` 且未合入 main** → ACP 的先发窗口仍然打开，但随时可能关闭。
- **OAuth 是 ACP 设计红线，不跟进**；反而构成新的差异化叙事：A2A 走 OAuth 客户端注册（依赖注册表/授权服务器），ACP 走 Ed25519+DID 自主身份（零注册、零第三方）。Stars 26481，WoW +70，趋势平稳。

### 2. ANP — 双周发布窗口跳票，DID 紧迫度回落

- 最新 commit 仍停留在 10-22，ROADMAP 11-04 轮预判的「下次发布约 11-05 前后」**未兑现，已 3 周无 commit**。且 `0837cfd` 移除了 scheduled workflow triggers，社区自动化在收缩，活跃度存疑。
- 影响修正：`did:acp:` 先发窗口比 11-04 判断的**更宽**。DID 互操作 spike 维持 P1 并行（纯文档级，不占开发带宽），但紧迫度回落——若下个双周窗（约 11-19）仍跳票，建议降回 P2。

### 3. IBM ACP — 季度回顾模式第 2 周，零变化

- 停更已满 15 个月（最后实质更新 2025-08）。无动作，维持季度回顾。

### 结论与行动建议

1. **🚨 P0 抢发确认（状态红灯）**：Steering Extension（`urn:acp:ext:steering/v1`）deadline 为 **~2026-11-18（11-04 起 ≤2 周），仅剩 1 周**，但仓库中尚无任何 steering 相关 spec/实现。本周必须出 spec 草案 + 最小实现（`input_required` 状态机 + `POST /tasks/{id}/steer`，零破坏性）。A2A 治理正规化（LF 轨道 + Bloomberg 入 TSC）后发布节奏只会更快，窗口按周计价。
2. **零成本差异化（本周可做，约 1 小时）**：README vs-A2A 对比表新增「Auth discovery」一行——A2A #1990 已收敛 OAuth client metadata（#2405 CLI 文档落地），ACP 提供 `/.well-known/did.json` + `jwks.json` 零注册自主身份，直接对位收割心智份额。
3. **维持并行观察**：ANP DID spike 不取消、不提级；11-19 双周窗是下一个检查点。
4. **无需调整路线图优先级**：P0/P1 排序不变，变化全部是紧迫度信号（Steering ↗↗、DID ↘）。
