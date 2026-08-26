# ACP 竞品周报 — 2026-04-01

_由贾维斯自动生成_

## A2A (Google) — 2026-04-01
- Stars: 22937 | Open Issues: 220
### 最新 Commits
- `c1169f4` 2026-03-31 fix: update OSPO action references to canonical org path (#1705)
- `f991a08` 2026-03-31 docs: add Community SDKs (#1698)
- `5ac9d2c` 2026-03-30 docs: add Strale to partners list (#1702)
- `72d1459` 2026-03-27 Add OIXA Protocol to partners list (#1692)
- `32a7d3a` 2026-03-26 docs: update python tutorial for a2a-sdk v1.0.0-alpha.0 (#1678)
### 新 Issues（功能请求）
- #563 [Feat]: Support multi-agent composition by registering HostAgent via c

## ANP (社区)
- `99806f4` 2026-03-05 feat: add failed_msg_id field to e2ee_error protocol message
- `761087d` 2026-03-05 add handle feature
- `1f0abd2` 2026-03-03 feat: add client_msg_id idempotency and server_seq ordering to E2EE IM
- `b1c1c76` 2026-03-01 update e2ee protocol
- `eb4a10f` 2026-02-27 docs: rename signature field `service` to `aud` in DID-WBA spec

## IBM ACP
- `e5265ca` 2025-08-25 docs: A2A announcement (#230)
- `e8299f8` 2025-08-21 chore: bump version
- `00afccd` 2025-08-21 fix(python): revert cachetools version bump to avoid conflicts

---

## 📊 深度分析（贾维斯）

### A2A（Google）— 关键动态

**1. Python SDK v1.0.0-alpha.0 正式发布（commit 5ac9d2c, 2026-03-26）**
A2A 官方 Python SDK 发布首个 alpha 版本，标志着 A2A 生态从协议规范阶段进入 SDK 工程化阶段。对 ACP 的含义：ACP 已有成熟的 Python/Node/Go/Rust 四语言 SDK（v1.7），SDK 成熟度领先约 1-2 个月。但 A2A 拥有 Google 品牌背书，SDK 一旦稳定将带来大量用户涌入，需关注。

**2. Multi-Agent HostAgent 注册 Issue #563 — 多智能体组合趋势加强**
A2A 社区推动"通过注册 HostAgent 实现多 Agent 组合"的特性请求，与 ACP 的 `limitations + capabilities + /peers/broadcast` 组合方向高度契合。ACP v2.22 已实现广播，v2.23 计划中的选择性广播（`target_peers[]`）正是此场景的轻量实现。**ACP 有望在个人/小团队多智能体编排领域先于 A2A 给出完整方案。**

**3. 合作伙伴生态快速扩张（Strale、OIXA 等新伙伴入驻）**
A2A 本周新增 2 个合作伙伴（Strale, OIXA Protocol），累计合作伙伴持续增加，生态扩张节奏加快。这意味着 A2A 正从技术协议向行业标准迁移。ACP 需要在 P2P 核心卖点完成后（v1.4/v2.x NAT 穿透），尽早启动 Show HN 和公开发布，抢占个人/小团队赛道心智。

### ANP（社区）— 活跃度低迷，基本可忽略

ANP 上周最新活动仍停留在 3 月初（2026-03-05），主要是 E2EE 消息 ID 字段微调（`failed_msg_id`、`client_msg_id`、`server_seq`）。ACP v1.1 在 2026-03-21 已借鉴 `failed_msg_id` 设计并完整实现，且覆盖场景更广（6 种错误码全覆盖）。**ANP 已从技术跟踪目标降级为参考即可，本周无新动态需关注。**

### IBM ACP — 长期停更，无需关注

IBM ACP 最新提交仍停留在 2025-08-25（上周周报同），无任何新动态。已正式退出竞品跟踪。

---

## 🗺️ 路线图对比与优先级判断

| 维度 | 当前 ACP 状态 | A2A 本周动态 | 优先级影响 |
|------|-------------|------------|---------|
| Python SDK | ✅ v1.7 成熟 | ⚠️ alpha.0 刚发布 | 无需调整，保持领先 |
| 多 Agent 组合 | v2.23 P1（选择性广播）| Issue #563 讨论中 | **提升优先级** |
| 广播历史查询 | v2.23 P1 | 无对应特性 | 维持，可作差异化卖点 |
| P2P NAT 穿透 | v1.4 主流程已集成 v2.19 | 无对应方案 | **维持最高优先级** |
| 公开发布 | v3.0 计划（NAT 稳定后）| 生态加速扩张 | ⚠️ 可考虑提前发布 beta |
| data_handling_policy | v2.23 P2 | IS#1606 讨论 | 维持低优先级 |

**优先级调整建议：**
- v2.23 `target_peers[]` 选择性广播：**从 P1 维持 → 适当加速，配合 A2A multi-agent 讨论窗口期**
- Show HN 公开发布：**建议将 beta 发布窗口从"NAT 完全稳定后"提前至 v2.23~v2.25 发布后**，抢在 A2A SDK v1.0 正式版之前占领个人开发者心智

---

## ✅ 本周行动建议

**1. 加速推进 v2.23 选择性广播 + 广播历史（P1 完整闭环）**
A2A Issue #563 提出多 Agent 组合需求，社区讨论热度上升。ACP v2.23 的 `target_peers[]` + `/peers/broadcast/history` 能在协议层给出比 A2A 更轻量的答案。建议本周内完成 v2.23 P1 两个特性，并在 README vs-A2A 差异化表中补充这一优势。预计工作量：~1 天。

**2. 启动 Show HN Beta 发布准备（抢在 A2A Python SDK 正式版之前）**
A2A Python SDK 进入 alpha 阶段，正式版发布可能在 4~6 周内。届时将吸引大量开发者关注 Agent 通信协议赛道。建议：即刻启动 `docs/show-hn-draft.md` 最终润色 + Hacker News 提交计划，目标在 2026-04-15 前发布 beta，以 P2P 无中间人 + 四语言 SDK + 完整 DID 身份体系为核心卖点，差异化切入个人开发者市场。
