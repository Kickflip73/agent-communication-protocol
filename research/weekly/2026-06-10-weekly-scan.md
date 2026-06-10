# ACP 竞品周报 — 2026-06-10

_由贾维斯自动生成_

## A2A (Google) — 2026-06-10
- Stars: 24211 | Open Issues: 276
### 最新 Commits
- `2e0a4e5` 2026-06-05 docs: add A2A & generative UI hackathon banner (#1906)
- `91071e0` 2026-06-04 docs: reorganize navigation structure and update theme features (#1871
- `1be9b56` 2026-06-04 docs: escape timestamp format to prevent emoji rendering in `whats-new
- `7475dd0` 2026-06-02 docs: add Rust SDK (a2a-rs) reference to README and update linter work
- `663a7e5` 2026-06-02 docs: fix Tutorial 8 AgentExecutor import path (#1884)
### 新 Issues（功能请求）
- #1811 [Feat]: Add TaskMessageUpdateEvent to notify observers when messages a
- #1794 [Feat]: Add generation/version number field to Task for event ordering
- #830 [Feat]: OAuth 2.1-compliant Authorization for A2A
- #563 [Feat]: Support multi-agent composition by registering HostAgent via c

## ANP (社区)
- `a0a7d2f` 2026-05-30 add json payload
- `b15ec29` 2026-05-13 Make the AP2 analysis available to English readers
- `aabc276` 2026-05-13 Make the IM protocol upgrade accessible to English readers
- `28c7dd4` 2026-05-13 add blogs
- `5f01846` 2026-04-22 add message protocol flow chart

## IBM ACP
- `e5265ca` 2025-08-25 docs: A2A announcement (#230)
- `e8299f8` 2025-08-21 chore: bump version
- `00afccd` 2025-08-21 fix(python): revert cachetools version bump to avoid conflicts

## 本周行动建议
_(需贾维斯人工分析后补充)_

---

## 🤖 贾维斯深度分析（2026-06-10）

### 一、竞品动态综合评估

#### A2A（Google）— ⚡ 持续高速扩张
- **Stars 增长**：22,643（2026-03-19 ROADMAP 记录）→ 24,211（本周），增长约 **+1,568 stars（+7%）**，近 3 个月平均每月 +500 左右，社区热度持续上行。
- **本周核心动态：伦敦黑客松（2026-06-13）**
  - `A2A & Generative UI Hackathon` 定于本周六（6月13日）在伦敦举办（Luma 报名页），官方 repo 已打横幅公告。表明 Google 正在加速生态落地，把协议推向开发者社区。
- **Rust SDK 上线（Issue #1871 / commit `7475dd0`）**：A2A 官方新增 Rust SDK（`a2a-rs`）链接，与 ACP 已有 Rust SDK（`sdk/rust/`，v1.1 完成）形成直接竞争，但 ACP 的 Rust SDK 早于本次 A2A Rust 参考实现。
- **待解决的架构缺口（持续暴露 ACP 差异化优势）**：
  - Issue #1811：`TaskMessageUpdateEvent` 缺失——任务消息新增时无专用事件通知，观察者无法感知历史消息变化（ACP v1.7 `SSE context_id 传播` 已覆盖此类场景）。
  - Issue #1794：Task 事件缺乏序号/版本字段，客户端无法检测乱序或丢失事件（ACP 的 `server_seq` 有序机制在 v0.5 即已解决，领先约 13 个月）。
  - Issue #830 / #563：OAuth 2.1 授权（高复杂度）和 HostAgent 注册（中心化）仍在讨论，ACP 坚守 Ed25519 自主权 + P2P 的定位差异化优势稳固。

#### ANP（社区）— 🔄 疑似从"归档"转向"国际化复苏"
- **ROADMAP 记录**：ANP 最后活跃 2026-03-05，已标记为"归档/停更，不再追踪"。
- **本周新变化**：近 3 条 commit（2026-04-22 / 2026-05-13 / 2026-05-30）均为英文化工作——将 AP2 分析、IM 协议升级等文章翻译为英文，并追加 JSON payload 说明。
- **研判**：ANP 未放弃，正在尝试国际化推广，**但技术内核无实质更新**。核心去中心化 DID 设计停更状态不变。对 ACP 而言：ANP 的 DID + JSON 结构化思路可持续借鉴，但无需紧跟其节奏。

#### IBM ACP — 🔴 确认长期停更
- 最新 commit 停留在 2025-08-25，距今约 9.5 个月，无任何新动态。本周与 ROADMAP 预判完全一致，已是参考资料级别。

---

### 二、对比 ROADMAP 路线图——优先级评估

| 维度 | 竞品信号 | ROADMAP 现状 | 建议 |
|------|---------|-------------|------|
| **Task 事件序号** | A2A #1794 仍争议中 | ACP `server_seq` v0.5 已完成 ✅ | 在 README vs-A2A 表中补充此差异化行 |
| **TaskMessageUpdateEvent** | A2A #1811 新增 Feature Request | ACP SSE context_id 已覆盖 ✅ | 文档中明确对应关系，增强差异化叙事 |
| **Rust SDK** | A2A 本周正式收录 Rust SDK 链接 | ACP `sdk/rust/` v1.1 已完成 ✅ | 核对 ACP Rust SDK 特性集是否仍领先，可发文对比 |
| **Hackathon / 开发者生态** | A2A 伦敦黑客松 2026-06-13 | ACP 尚无社区活动 | 考虑撰写 "Show HN" 帖子（`docs/show-hn-draft.md` 已有草稿） |
| **NAT 穿透完整化** | 无竞品进展 | v1.4 主流程集成待完成 | **维持 v3.0 发布前 P0 优先级** |
| **ANP 英文化** | ANP 国际化推广信号 | 无影响 | 继续观察，下周评估是否有技术实质更新 |

---

## 📋 本周行动建议

**1. 立即执行：README vs-A2A 差异化表补充 2 行**
   - 新增行："Task event sequencing" — ACP `server_seq`（v0.5，2026-03）vs A2A #1794（2026-06 仍争议）
   - 新增行："Task history update events" — ACP SSE context_id 机制 vs A2A #1811（2026-06 Feature Request）
   - 理由：两个 A2A 社区热议 issue 均已被 ACP 解决数月，是高价值差异化素材，应在 README 中明确展示。

**2. 近期建议：发布 Show HN——趁黑客松窗口期**
   - A2A 伦敦黑客松（2026-06-13）预计带动 Agent 协议话题热度，是 ACP 在 Hacker News 曝光的绝佳窗口。
   - `docs/show-hn-draft.md` 已有草稿，建议在 6-13 当天或 6-14 周一发布（黑客松效应余温期）。
   - 发布前确认 v1.4 NAT 穿透核心流程可演示，或在帖子中标注"P2P 打洞 v1.4 进行中"。

