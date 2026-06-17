# ACP 竞品周报 — 2026-06-17

_由贾维斯自动生成_

## A2A (Google) — 2026-06-17
- Stars: 24316 | Open Issues: 283
### 最新 Commits
- `69dd57c` 2026-06-12 docs: restructure homepage information and add missing sections (#1874
- `2e0a4e5` 2026-06-05 docs: add A2A & generative UI hackathon banner (#1906)
- `91071e0` 2026-06-04 docs: reorganize navigation structure and update theme features (#1871
- `1be9b56` 2026-06-04 docs: escape timestamp format to prevent emoji rendering in `whats-new
- `7475dd0` 2026-06-02 docs: add Rust SDK (a2a-rs) reference to README and update linter work
### 新 Issues（功能请求）
- #1811 [Feat]: Add TaskMessageUpdateEvent to notify observers when messages a
- #1794 [Feat]: Add generation/version number field to Task for event ordering
- #830 [Feat]: OAuth 2.1-compliant Authorization for A2A
- #563 [Feat]: Support multi-agent composition by registering HostAgent via c

## ANP (社区)
- `15d41c9` 2026-06-10 update wns Protocol：add did profile
- `a0a7d2f` 2026-05-30 add json payload
- `b15ec29` 2026-05-13 Make the AP2 analysis available to English readers
- `aabc276` 2026-05-13 Make the IM protocol upgrade accessible to English readers
- `28c7dd4` 2026-05-13 add blogs

## IBM ACP
- `e5265ca` 2025-08-25 docs: A2A announcement (#230)
- `e8299f8` 2025-08-21 chore: bump version
- `00afccd` 2025-08-21 fix(python): revert cachetools version bump to avoid conflicts

## 本周行动建议
_(需贾维斯人工分析后补充)_

---

## 贾维斯深度分析

### 一、A2A (Google) — 本周关键动态

**1. TaskMessageUpdateEvent (#1811)**：社区提议新增消息变更通知事件，让 observer 能在 Task 消息被追加/修改时收到实时推送。这是 A2A 向"可观测性"方向的重要演进——当前 ACP 的 SSE 流已天然支持此场景（Task 状态变更即推送），但 ACP 缺少细粒度的"仅消息体变更"事件类型。**评估：P3 级借鉴**，可在 v2.8x 中新增 `message_updated` SSE event type，与现有 `task_updated` 互补。

**2. Task generation/version 字段 (#1794)**：为 Task 添加单调递增的版本号，用于事件排序和冲突检测。ACP 当前有 `server_seq` 做消息排序，但 Task 整体缺少版本号概念。**评估：P2 级借鉴**，可在 `GET /tasks/{id}` 响应中新增 `task_version: int` 字段，轻量实现、解决多端同步歧义。

**3. Rust SDK 正式纳入 README (#7475dd0)**：A2A 社区贡献的 a2a-rs 已被官方文档引用，标志着 Rust 作为一等公民语言被认可。ACP 已在 v1.1 提供 Rust SDK（`sdk/rust/`），**现状持平**，无需额外行动。

**4. OAuth 2.1 授权 (#830)**：此 Issue 持续活跃但未收敛，与 ACP 设计禁忌（❌ OAuth）冲突。**无需行动**，继续观察 TSC 结论。

**5. 文档重构潮（#1874, #1871, #1906）**：A2A 在做大量文档整理和 Hackathon 推广，技术协议本身本周无实质变更，说明正处于"稳定期"——**这是 ACP 加速差异化的窗口期**。

### 二、ANP (社区) — 复活信号

**6. WNS Protocol + DID Profile 更新 (15d41c9, 2026-06-10)**：ANP 在沉寂近 3 个月后有新 commit，更新了 WNS（Web Name Service）协议，增加了 DID Profile 支持。此前 ANP 已归档（ROADMAP 标记 🔴），但此动态表明项目仍有微弱生命力。

**评估**：ANP 的 WNS/DID 方向与 ACP 的 `did:acp:` 体系有理念重叠（去中心化身份），但 ANP 仍停留在文档层面，无可用代码。**行动：维持"观察"状态**，暂不恢复主动追踪；若 ANP WNS 出现可参考的实现再评估。

### 三、IBM ACP — 持续停更

最后 commit 仍是 2025-08-25，近 10 个月无任何更新。**已确认死亡**，从下周扫描可降频至月度检查。

### 四、ROADMAP 对比 & 优先级建议

| ROADMAP 项目 | 现状 | 本周评估 |
|-------------|------|---------|
| v1.4 NAT 穿透主流程 | ✅ v2.19.0 已完成 | 稳定，无需调整 |
| P2 trust.signals JWKS | ✅ v2.18.0 已完成 | 稳定 |
| P3 data_handling_policy | 待开发 | **建议暂缓**——A2A #1606 无新进展，个人场景需求弱 |
| broadcast/history + target_peers | ✅ v2.23.0 已完成 | 稳定 |
| **🆕 Task version 字段** | 未规划 | **建议 P2 纳入 v2.80**——轻量高价值，解决多端同步歧义 |
| **🆕 message_updated 事件** | 未规划 | **建议 P3 纳入 v2.81**——细粒度可观测性，SSE 生态补全 |
| v3.0 公开发布 | 待 v1.4 完成后 | **可启动 Show HN 草稿修订**——A2A 处于文档稳定期，是发布窗口 |

### 五、行动建议

1. **🟢 短期（v2.80）**：新增 `task_version` 整数版本号字段到 Task 模型，`GET /tasks/{id}` 和 `GET /tasks` 响应均包含，每次 Task 状态/消息变更自增。参考 A2A #1794 但更轻量（无需 generation 概念）。预计 1 个 commit 搞定。

2. **🟢 短期（v2.81）**：新增 SSE event type `message_updated`，当已有消息的 content 或 metadata 被修改时推送，与现有 `task_updated` 互补。参考 A2A #1811。预计 1-2 个 commit。

3. **🟡 中期**：启动 Show HN 草稿修订，梳理 v2.19–v2.78 的全部新特性，把握 A2A 文档稳定期的发布窗口。

4. **⚪ 长期**：data_handling_policy Extension 继续暂缓，等 A2A #1606 方案收敛或企业用户需求驱动时再启动。

---

_分析完成时间：2026-06-17 09:06 CST_
_下期扫描：2026-06-24_
