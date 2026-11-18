# ACP 竞品周报 — 2026-11-18

_由贾维斯自动生成_

## A2A (Google) — 2026-11-18
- Stars: 26571 | Open Issues: 319
### 最新 Commits
- `b30ab16` 2026-11-16 docs: point the a2a-cli blog post at the new documentation site (#2466
- `4d7cda4` 2026-11-13 docs: add Raven to partners list (#2340)
- `7a0dd85` 2026-11-13 docs: add A2A Market to partners list (#2455)
- `d18aa92` 2026-11-11 docs: adding custom 404 page (#2379)
- `ff00f96` 2026-11-11 docs(spec): main page revamp (#2194)
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

## 深度分析（贾维斯，2026-11-18）

### 1. A2A — 静默期出现首批"发布预热"信号：docs 体系重构 + 生态合作提速

- 本周 5 个 commit 全部为 docs，但**性质发生变化**：`d18aa92`（自定义 404 页）+ `ff00f96`（spec 主页 revamp）+ `b30ab16`（a2a-cli 博文指向**全新文档站点**）是典型的**发布前站点/文档准备动作**。连续三周观察的"v1.1 静默期"很可能正在转入发布预热阶段，**v1.1（含 #2125 Steering）随时可能合入 main 并正式发布**。
- **生态侧明显提速**：单周连加 2 个 partner（Raven #2340、A2A Market #2455），叠加此前 Bloomberg 入 TSC、LF antitrust 政策——治理与生态双轨并进，是标准争夺战进入"抢实现者"阶段的标志。
- Enhancement 榜前 5 与近 4 周完全一致（#2125 Steering 仍居首、仍挂 `v1.1-candidate` 未合入）。Stars 26571，WoW +90（vs 上周 +70），关注度随发布临近回升。
- **影响**：ROADMAP 中 Steering Extension（`urn:acp:ext:steering/v1`）的 **≤2 周 deadline（2026-11-04 设定，即 ~11-18）本周恰好到期**。窗口判断从"随时关闭"升级为"大概率已进入关闭倒计时"，本周是最后抢发机会。

### 2. ANP — 连续第 4 周零 commit，双周节奏疑似中断

- 自 10-22（anp05 DID 绑定 CIMD + 移除 scheduled workflow）后，ANP main 分支已 **27 天无任何提交**，原定 ~11-05 前后的双周发布窗**已实质跳票**。auth draft（10-15）之后无后续修订，活跃度判断从"双周节奏固化"下修为"**节奏中断、待验证**"。
- **影响**：`did:acp:` DID 互操作 spike（P1）的紧迫度进一步下降——ANP DID 生态推进停滞，先发窗口不再按周收窄，spike 可降回 P2 观察，下次检查点后移至 12 月。
- 风险提示：也可能是在憋大版本（如 anp-06）。weekly-scan 保持追踪即可。

### 3. IBM ACP — 停更满 15 个月，季度回顾确认无价值

- 最新 commit 仍为 2025-08-25 的 A2A 宣言（仓库已自我宣告被 A2A 取代）。上季评级的"季度回顾模式"实际执行中无任何新信息产出，**建议降级为半年回顾**，把扫描算力留给 A2A/ANP。

### 4. 结论：无技术情报变化，唯一变化是"倒计时"

对比 11-04 路线图：P0/P1 排序无需调整，三条新增信号（A2A docs 重构预热、partner 提速、ANP 停滞）全部指向同一个动作——**Steering Extension 必须本周落地 spec 草案**。这是本季度 ACP 相对 A2A 最后一个"明确领先且可先发"的叙事点（cancel 语义、limitations 均已收割完毕）。

## 本周行动建议

1. **🚨 P0 — Steering Extension 本周落地（deadline 今日到期，最后窗口）**：立即产出 `spec/steering-ext-v1.md` 草案 + 最小实现——复用 `input_required` 状态机 + `POST /tasks/{id}/steer`（运行中任务注入指令/中断），零破坏性，预估 1 个开发日。若 A2A v1.1 本周发布同日推出，仍能以"独立扩展、无需大版本"作为差异化叙事。
2. **DID 互操作 spike 降级 P1 → P2**：ANP 停更 27 天，`did:acp:` 先发窗口压力解除，改为观察模式，检查点后移至 12 月（等 ANP 下一次 commit 或确认大版本动向）。
3. **IBM ACP 季度回顾 → 半年回顾**：扫描脚本 IBM 节保留但仅做存在性检查，减少无效输出。
4. **README 备一行差异化弹药**（零成本，~30 min）：待 A2A v1.1 发布时，在 vs-A2A 表新增 "Task steering" 行（ACP 扩展按需启用 vs A2A v1.1 核心强制），文案本周可先备好。
