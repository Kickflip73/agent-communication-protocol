# ACP 竞品周报 — 2026-07-08

_由贾维斯自动生成_

## A2A (Google) — 2026-07-08
- Stars: 24671 | Open Issues: 209
### 最新 Commits
- `99dbc81` 2026-07-07 docs: add Space Auto to partners list (#2033)
- `a7d12d1` 2026-07-07 docs: add AlgoVoi to partners list (#1994)
- `66048d8` 2026-07-07 chore(deps): bump the github-actions group across 1 directory with 3 u
- `f52a194` 2026-07-07 ci: migrate from deprecated buf-setup-action to buf-action (#1999)
- `a3bc1b6` 2026-07-07 docs: remove broken partner links (OIXA, Pinchwork) (#2017)
### 新 Issues（功能请求）
- #1995 [Epic] Bidirectional streaming & improved stream semantics
- #1992 [Epic] Multi-turn interaction gaps — state acceptance rules, interrupt
- #1991 [Epic] Coherent Task History — gaps in semantics, querying, and observ
- #1990 [Epic] Auth scheme declaration & credential discovery in AgentCard
- #1989 [Epic] Client-directed skill selection

## ANP (社区)
- `3f048ef` 2026-06-27 docs: update ANP getting started guide
- `6fc3854` 2026-06-27 merge ANP-06 meta negotiation docs
- `28e6890` 2026-06-27 docs: clarify ANP-06 optional role
- `000fc9b` 2026-06-27 docs: deprecate legacy ANP-06 negotiation
- `a41c579` 2026-06-27 docs: update README for ANP-06 negotiation

## IBM ACP
- `e5265ca` 2025-08-25 docs: A2A announcement (#230)
- `e8299f8` 2025-08-21 chore: bump version
- `00afccd` 2025-08-21 fix(python): revert cachetools version bump to avoid conflicts

## 深度分析：本周竞品动态与 ACP 路线调整

_贾维斯分析，2026-07-08_

### 1. A2A 本周五大 Epic 方向——ACP 的启示与差距

A2A 本周在 Issues 中一次性提出 5 个 Epic 级功能请求，显示其社区正在从「基础协议稳定」向「企业级扩展」快速演进。逐条分析：

| A2A Epic | 核心诉求 | ACP 现状 | 差距/启示 |
|---------|---------|---------|---------|
| **#1995 Bidirectional streaming** | 双向流式通信，服务器主动向客户端推送 | SSE（单向）+ HTTP/2 可选 | 长期：调研 WebSocket / h2 服务端推送升级；短期：SSE 够用，无紧急差距 |
| **#1992 Multi-turn interaction** | 状态接受规则、打断语义、对话状态机 | `context_id` 已支持（v0.7），Task 5 状态机完整 | 中度差距：需要增加「打断/中断」的 Task 状态语义（当前没有 `interrupted` 状态） |
| **#1991 Coherent Task History** | 任务历史语义一致性、查询、可观测性 | `GET /tasks` 已支持（v2.2），但无历史版本/变更轨迹 | 轻度差距：增加 `GET /tasks/{id}/history` 或 `versions` 字段可补齐 |
| **#1990 Auth scheme in AgentCard** | AgentCard 声明支持的认证方案，客户端自动发现 | **ACP 领先**：Ed25519 + DID 已完整（v1.3），但 AgentCard 无 `auth_schemes` 声明字段 | 差距：A2A 从「无认证」追赶，ACP 可从「领先」到「标准化声明」——在 AgentCard 中新增 `auth_schemes` 字段，让客户端自动选择认证方式 |
| **#1989 Client-directed skill selection** | 客户端显式选择 Agent 技能，而非被动协商 | `QuerySkill()` 已支持（v0.5），但客户端无法「指定」skill | 轻度差距：扩展 `QuerySkill` 参数或增加 `skill_id` 直达调用路径 |

**结论**：A2A 的 5 个 Epic 中，ACP 在 **身份认证**（Ed25519/DID）和 **Task 状态机** 上已有实质性领先；但 A2A 的「Auth scheme 声明」和「Multi-turn 打断语义」值得在下一版本（v2.24+）跟进。

### 2. ANP / IBM ACP：彻底停更

- **ANP**：最后一次提交 2026-06-27，但只是文档更新，且之后无活动。ROADMAP 已标注「归档」，不再追踪。
- **IBM ACP**：2025-08-25 后彻底停止。不再投入研究精力。

> ACP 目前唯一的竞品参照系是 **A2A**。ANP 和 IBM ACP 已退出赛道。

### 3. A2A 增长数据

| 指标 | ROADMAP 记录（2026-03-19） | 本周（2026-07-08） | 增幅 |
|------|---------------------------|-------------------|------|
| Stars | 22,643 | 24,671 | **+8.9%**（+2,028） |
| Open Issues | — | 209 | — |

A2A 社区仍在高速增长，Stars 突破 2.4 万。需注意其 Issue 中 Epic 的 TSC 采纳节奏——若 A2A 在 Q3 实现双向流和认证声明，ACP 的差异化窗口会缩小。

### 4. ROADMAP 调整建议

#### 建议 1（高优先级）：AgentCard 新增 `auth_schemes` 字段
- **目标版本**：v2.24
- **内容**：在 AgentCard 中声明支持的认证方式列表（如 `["ed25519_identity", "hmac_sha256", "none"]`）
- **价值**：呼应 A2A #1990，将 ACP 的认证领先优势从「已实现」升级为「可发现」，让客户端自动匹配认证方式
- **工作量**：低（1 天，扩展 AgentCard 结构 + 文档 + 测试）

#### 建议 2（中优先级）：Task 状态机增加 `interrupted` 状态
- **目标版本**：v2.25 或 v2.26
- **内容**：新增 `interrupted` 状态，定义多轮对话中「用户/Agent 主动打断」的语义；与 `input_required` 区分（打断 = 外部干预，输入等待 = 正常流程等待）
- **价值**：回应 A2A #1992，增强多轮交互能力
- **工作量**：中（需更新状态机、SSE 事件、规范文档，2-3 天）

---

_分析完毕。本报告已自动 push 到 GitHub。_

