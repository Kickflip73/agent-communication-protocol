# ACP 竞品周报 — 2026-06-03

_由贾维斯自动生成_

## A2A (Google) — 2026-06-03
- Stars: 24103 | Open Issues: 273
### 最新 Commits
- `7475dd0` 2026-06-02 docs: add Rust SDK (a2a-rs) reference to README and update linter work
- `663a7e5` 2026-06-02 docs: fix Tutorial 8 AgentExecutor import path (#1884)
- `ae3d1c3` 2026-05-29 docs: clarify MCP reference in A2A overview (#1873)
- `72a0dbc` 2026-05-29 ci: Minor updates for workflows/automation (#1889)
- `678e0a4` 2026-05-29 ci: Update guidelines for commit messages (#1890)
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

## 🔍 贾维斯深度分析（2026-06-03 09:04）

### 一、竞品动态总览

#### A2A（Google）— 本周关键动态

**1. Rust SDK 正式进入 README 引用（commit 7475dd0, 2026-06-02）🦀**
- A2A 的 Rust SDK (`a2a-rs`) 从"存在"升级为"官方推荐"，被写入 README 主文档
- 同时更新了 linter 工作流配置
- **贾维斯评估**：A2A 在 Rust 生态的投入加大。ACP 的 Rust SDK（`sdk/rust/`，v1.2, commit `4f62ae6`）更早落地，但 A2A 背靠 Google 品牌效应，社区采用率可能反超。建议关注 `a2a-rs` 的 API 设计是否引入了值得借鉴的模式。

**2. 文档质量持续打磨（commits 663a7e5, ae3d1c3）📝**
- Tutorial 8 AgentExecutor 导入路径修复（#1884）
- MCP 参考说明澄清（#1873）—— 明确 A2A 与 MCP 的关系定位
- CI/CD 工作流微调（#1889, #1890）
- **贾维斯评估**：纯维护性提交。A2A 进入"稳定期+慢速迭代"模式——规范基本定型，重心转向生态和文档完善。这对 ACP 是利好：短期内不会出现颠覆性协议变更。

**3. Stars 突破 24K（24013 → 24103，+90/周）📈**
- 增速约 90 stars/周，与上月持平
- Open Issues 从 265 → 273（+8），新增 Issue 速度略高于关闭速度
- **贾维斯评估**：健康增长。A2A 社区活跃度稳定在高位。

**4. 持续关注的 Issues 无突破性进展：**
- #1811 TaskMessageUpdateEvent — 上周已记录，本周无新评论
- #1794 Task version number — 同上
- #830 OAuth 2.1 — 长期讨论，无实质推进
- #563 multi-agent composition via HostAgent — 有趣但遥远

#### ANP（社区）
- 本周有新活动！`a0a7d2f`（2026-05-30）—— **add json payload**
- 这是 ANP 自 2026-04-22 以来的首次代码提交（间隔 ~6 周）
- 但仅一次提交，内容也较轻量（JSON payload 支持），不足以判断项目复活
- **结论：标记为"微弱信号"，继续观察 2-3 周再定**

#### IBM ACP
- 停更第 **10 个月**（最后活跃 2025-08-25）
- **结论：无变化，维持"仅参考"状态**

---

### 二、路线图对比 & 优先级评估

| A2A 本周动态 | ACP 现状 | 需要调整？ |
|---|---|---|
| Rust SDK 官方推荐化 | ✅ 已有（v1.2, 更早落地） | ❌ 保持领先即可 |
| MCP 关系文档澄清 | ✅ ACP 定位清晰（MCP=Tool, ACP=Agent↔Agent） | ❌ 不受影响 |
| CI/CD 完善 | ✅ ACP 有 Docker GHCR + 测试管道 | ❌ 维持现状 |
| TaskMessageUpdateEvent (#1811) | ✅ SSE 事件机制已有 | ❌ 已具备 |
| ANP 微弱复活信号 | N/A | 🟡 观察，不行动 |

**路线图结论：本周无需调整 ROADMAP.md 优先级。** ACP 当前版本 v2.78+（SINT quad complete + token revocation）在 trust & security 方向的技术深度持续领先。A2A 本周无任何威胁性动作。

---

### 三、行动建议

#### 📋 本周建议执行项（2 条）

**1. 【P3 可选】调研 A2A Rust SDK (`a2a-rs`) API 设计模式**
- 背景：A2A 刚将 Rust SDK 写入 README 官方推荐，可能代表其 SDK API 设计的最新思路
- 行动：clone `a2a-rs` 仓库，快速 review 其 client 类型定义、error handling、async 模式
- 目的：对比 ACP `sdk/rust/` 的 API 设计，识别可改进点（如有）
- 工作量：~30min code review
- 优先级：P3（纯优化，不影响功能）

**2. 【观察】ANP 复活信号监控升级**
- ANP 出现了 6 周来的首次提交（`a0a7d2f`, 2026-05-30, "add json payload"）
- 虽然单次提交不能判定复活，但值得提高扫描频率中的关注度
- 行动：下周 scan 时特别检查 ANP 是否有连续第 2 次提交；若有，触发一次深度 review
- 风险：低。ANP 即使复活，其去中心化身份方向与 ACP DID 体系有交集但非直接竞争

#### 📊 竞品健康度评分（周环比）

| 协议 | 活跃度 | 创新速度 | 与 ACP 竞争重叠 | 趋势 |
|------|--------|----------|----------------|------|
| A2A | ⭐⭐⭐⭐⭐ | ⭐⭐⭐（维护期） | ⭐⭐⭐（企业场景） | → 稳定增长，生态扩张 |
| ANP | ⭐⭐（微弱回升） | ⭐ | ⭐⭐（DID 身份） | ↗️ 单次提交，待观察 |
| IBM ACP | ☆ | ☆ | ⭐ | → ⊘ 保持停更 |

---

*分析完成时间：2026-06-03 09:05 CST*
*分析引擎：J.A.R.V.I.S. v2.8.0-research*
