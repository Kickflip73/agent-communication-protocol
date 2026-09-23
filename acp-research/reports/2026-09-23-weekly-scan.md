# ACP 竞品周报 — 2026-09-23

_由贾维斯自动生成_

## A2A (Google) — 2026-09-23
- Stars: 25895 | Open Issues: 257
### 最新 Commits
- `43e0c87` 2026-09-22 docs: add MolTrust to partners (#2252)
- `afda831` 2026-09-16 docs: update roadmap (#2237)
- `6d6640c` 2026-09-10 docs: improve readability and wording in life-of-a-task (#2226)
- `1e8a97a` 2026-09-10 docs: improve readability and wording in key-concepts (#2225)
- `7e66bae` 2026-09-10 docs: improve readability and wording in a2a-and-mcp (#2224)
### 新 Issues（功能请求）
- #2125 [Extension Proposal]: Agent Steering — interruptible & steerable tasks
- #1995 [Epic] Bidirectional streaming & improved stream semantics
- #1992 [Epic] Multi-turn interaction gaps — state acceptance rules, interrupt
- #1991 [Epic] Coherent Task History — gaps in semantics, querying, and observ
- #1990 [Epic] Auth scheme declaration & credential discovery in AgentCard

## ANP (社区)
- `ee32805` 2026-09-10 Merge feat/anp-02-did-authentication into main
- `dbfded5` 2026-09-10 docs: extract DID authentication and generalize messaging methods
- `222429c` 2026-09-09 docs: introduce AWiki identity and messaging implementations
- `b7ba3ff` 2026-09-06 docs: align shared agent and verification guidance
- `541e4e7` 2026-09-03 docs: remove DID provider transition assertion object

## IBM ACP
- `e5265ca` 2025-08-25 docs: A2A announcement (#230)
- `e8299f8` 2025-08-21 chore: bump version
- `00afccd` 2025-08-21 fix(python): revert cachetools version bump to avoid conflicts

## 贾维斯深度分析（2026-09-23）

### 一、竞品新动态解读

**1. A2A — 平台化加速，社区焦点转向「可控性」（Steering）**
- 核心动态：`MolTrust` 加入官方 partners 列表（#2252，09-22）。MolTrust 从名字看是信任/身份方向的服务商，说明 A2A 正在补齐企业信任层拼图——这与我们的 DID/v1.3+trust.signals 赛道直接重叠。
- 社区热度信号：4 个未完结的 Epic（双向流式、多轮交互缺口、任务历史、认证方案声明）+ #2125 Agent Steering 提案。#2125（可中断、可转向的任务）是本周最值得关注的方向性提案：它把「人在环中/Agent 中断接管」上升为协议能力，我们当前 5 态状态机中的 `input_required` 是天然挂载点。
- 提醒：A2A 官方 repo 本周 commits 全是文档与 partner 列表，规格层无实质变更 → 对我们无破坏性影响。

**2. ANP — DID 认证正式落地，与我们从「参考」变为「对标」**
- `anp-02-did-authentication` 于 09-10 合入 main，并系统化抽取为通用文档（DID authentication + messaging methods + AWiki identity）。
- 这是 ANP 复活后的第一个实质性里程碑：去中心化身份从提案变成默认实现。上周观察已确认该方向，本周确认「已落地」。
- 影响：我们 `did:acp:` 的差异化窗口在收窄。上次判断「领先 2-3 个月」，现在应下调为「领先约 1-2 个月」。互操作性（跨 DID method 互通）将成为下一个分水岭。

**3. IBM ACP — 连续 13 个月停更，维持降级为「参考即可」**
- 最新 commit 仍是 2025-08-25 的 A2A announcement 文档，无任何新动态。 roadmap 中的降级决策正确，维持不变，每月扫一次即可。

### 二、路线图对照结论

| 检查项 | 结论 |
|--------|------|
| 现有优先级是否需要调整？ | **无需大调**。v1.4 NAT 穿透收尾（打洞集成测试）、v3.0 公开发布两条主线仍正确 |
| 是否需要借鉴新特性？ | **需要**：#2125 Agent Steering 建议升级为正式候选 Extension（上周仅「候选观察」，本周 A2A Epic 化倾向明显，价值上升） |
| ANP 对标项 | ROADMAP 的 ANP 态度「恢复追踪，对标 DID 互操作」仍然有效，但建议把「跨 DID method 互操作」从观察项升为 v3.0 后备特性 |
| 风险 | MolTrust 入伙 A2A → 企业信任层赛道竞争加剧，我们的 trust.signals（13 种信号 + SINT 能力令牌四件套）是先发优势，应尽快在 Show HN 叙事中前置 |

### 三、行动建议（本周执行项）

1. **【P1】启动 Steering Extension 设计**：`urn:acp:ext:steering/v1`，最小实现 = 基于现有 `input_required` 状态 + 新增 `POST /tasks/{id}/steer`（运行中任务注入指令/中断），零破坏性。目标 v3.0 发布前完成 spec 草案，让「ACP 先于 A2A 落地 Steering」成为又一个差异化案例（复刻 #1694 limitations 次日落地打法）。
2. **【P2】DID 互操作性 spike**：调研 ANP `anp-02` 的 DID 文档格式与我们 `did:acp:` W3C DID Document（`/.well-known/did.json`）的字段差异，输出一页对比 + 兼容性评估，为 v3.0 后的跨生态互通做技术储备。
3. **【P2·提醒】Show HN 发布窗口**：A2A 本周无规格级变更，窗口仍开放；但建议等 Steering Extension spec 草案完成后再发布，叙事更完整（NAT 穿透 + DID + trust.signals + Steering 四张牌）。

---

_分析：贾维斯 J.A.R.V.I.S. · 2026-09-23 周报轮_
