# ACP 竞品周报 — 2026-10-07

_由贾维斯自动生成_

## A2A (Google) — 2026-10-07
- Stars: 26033 | Open Issues: 279
### 最新 Commits
- `84c1e39` 2026-10-06 docs: improve agent-readiness signals for a2a-protocol.org (#2285)
- `679ab3a` 2026-10-05 docs: fix daily link checker run (#2298)
- `fe182ee` 2026-10-02 docs: add Salt to partners list (#2265)
- `27860f6` 2026-10-02 docs: introduce the A2A CLI with a blog post and home page entry (#228
- `65dadbd` 2026-10-02 docs: updating llms.txt and  (#2278)
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

## 本周行动建议

### 深度分析（贾维斯 · 2026-10-07）

#### 1. A2A：Steering 升级为 `v1.1-candidate`（🔥 重大信号）
- #2125 Agent Steering 已被打上 **`v1.1-candidate`** 标签（本周核实），从社区提案正式进入 A2A v1.1 版本路线图。连续三周居 enhancement 榜首后终于落地候选，官方认可度极高。
- 同期 A2A 于 10-02 发布**官方 A2A CLI**（博客 + 主页入口），生态工具化加速；新增 partner Salt。
- **影响**：我们 vNext P1 Steering Extension（`urn:acp:ext:steering/v1`）的"先发落地"窗口收窄。此前 limitations（#1694）我们能次日落地是因为当时它还只是提案；这次 #2125 已进官方版本路线，时间压力完全不同。

#### 2. ANP：`anp05-root` v0.5 协议工作区合入 main（PR #104）
- ANP 于 10-01 合入 `feature/anp05-root`，同日作者 chgaowei 亲自重构白皮书 platform/openness 章节，社区维持活跃。
- DID 方向持续推进（anp-02 已落地 → anp-05 根协议工作中），我们 `did:acp:` 的领先窗口从此前评估的 1-2 个月进一步收窄。

#### 3. IBM ACP：持续停更
- 最后 commit 仍为 2025-08-25，无新动态。维持"参考即可"定位，零投入。

### ROADMAP 对照结论
| 路线图项 | 本周信号 | 判定 |
|---------|---------|------|
| P1 Steering Extension | #2125 升级 v1.1-candidate | ⬆️ **升级为本月冲刺**，spec 草案 deadline 从"v3.0 前"提前到未来 2-3 周 |
| P2 DID 互操作 spike | ANP anp05-root 合入 main | 维持 P2，紧随 Steering 之后执行 |
| 新特性跟进 | A2A 官方 CLI 发布 | ❌ 不跟进（工具链赛道，我们已有 pip/npm 分发） |
| x402 Agent 支付 | 无新动态 | 维持不跟进判定 |

### 行动建议
1. **【本周】启动 Steering Extension spec 草案**：`POST /tasks/{id}/steer` 最小端点 + 复用现有 `input_required` 状态，复刻 limitations 的先发落地打法，抢在 A2A v1.1 发布前出 `urn:acp:ext:steering/v1` 规范。
2. **【下周】DID 互操作 spike**：ANP anp05-root DID 文档格式 vs `did:acp:` W3C DID Document 一页对比评估，确认互通成本。
