# ACP 竞品周报 — 2026-08-05

_由贾维斯自动生成_

## A2A (Google) — 2026-08-05
- Stars: 25187 | Open Issues: 230
### 最新 Commits
- `6dad7a1` 2026-08-04 docs: broken links and link checker workflow fine tuning (#2106)
- `2cdf197` 2026-07-31 docs: fix hybrid agent grammar (#2077)
- `7f9c951` 2026-07-31 docs(fix): PR links workfow failing (#2091)
- `23abcd9` 2026-07-31 chore(security): move vulnerability intake to GitHub Security Advisori
- `6550d34` 2026-07-30 docs(spec): clarify in-task authorization scope semantics (#2081)
### 新 Issues（功能请求）
- #1995 [Epic] Bidirectional streaming & improved stream semantics
- #1992 [Epic] Multi-turn interaction gaps — state acceptance rules, interrupt
- #1991 [Epic] Coherent Task History — gaps in semantics, querying, and observ
- #1990 [Epic] Auth scheme declaration & credential discovery in AgentCard
- #1989 [Epic] Client-directed skill selection

## ANP (社区)
- `9789640` 2026-08-04 docs: revise messaging profile version strategy
- `593a374` 2026-08-03 fix: preserve avatars when contributor stats are pending (#92)
- `5e53512` 2026-08-03 fix: update contributor avatar automation (#91)
- `149ad00` 2026-08-03 docs: explain Agent Description extended fields (#89)
- `38926dc` 2026-08-02 add English Agentic Web ten-talks translations

## IBM ACP
- `e5265ca` 2025-08-25 docs: A2A announcement (#230)
- `e8299f8` 2025-08-21 chore: bump version
- `00afccd` 2025-08-21 fix(python): revert cachetools version bump to avoid conflicts

---

## 深度分析 — 贾维斯（2026-08-05）

### 竞品态势总览

| 协议 | Stars | 活跃度 | 本周动态 |
|------|-------|--------|----------|
| **A2A** | 25,187 (↑2,544) | ⚡ 极高 | 5 个 Epic 级 Issue 新立案，聚焦核心语义完善 |
| **ANP** | ~1,240 | 🟡 低 | 仅文档和自动化修复，无架构级变动 |
| **IBM ACP** | ~966 | 🔴 停更 | 最后提交 2025-08，可忽略 |

> A2A Stars 4 个月增长 2,544，增速稳定（月均 ~636），社区热度持续升温。

### 关键发现

#### 1. A2A 开启「语义补完」阶段 — 5 个 Epic 暴露其架构债务

A2A 本周同时立案 5 个 Epic，主题高度集中：**流式、状态、历史、认证、技能选择**。这表明 A2A 在快速扩张后进入「基础语义夯实期」。

| Epic | 主题 | ACP 现状 | 差距评估 |
|------|------|----------|----------|
| #1995 | 双向流 & 流语义改进 | SSE 单向流 ✅ | A2A 要全双工；ACP 需评估 WebSocket 需求 |
| #1992 | 多轮交互缺口（中断、状态接受规则）| `context_id` + 5 状态机 ✅（v1.7）| **ACP 领先 3~4 个月** |
| #1991 | 任务历史（查询、语义、可观测）| `GET /tasks` 列表+分页 ✅（v2.2）| **ACP 已解决** |
| #1990 | AgentCard 认证方案声明 | Ed25519+DID ✅（v1.3），但缺「声明支持哪些 auth」| 小幅跟进即可 |
| #1989 | 客户端导向技能选择 | `QuerySkill()` ✅（v0.5），但非客户端驱动 | 概念差异，风险低 |

**结论**：A2A 正在经历的「语义补完」，ACP 已在 v0.5–v2.2 期间分批解决。这是 ACP 轻量迭代策略的验证：**小步快跑、先发制人**。

#### 2. A2A 安全 & 文档持续收敛

- #2081 明确「in-task authorization scope」语义 → ACP 的 `capability-token` 信号体系（v2.74–v2.78）已覆盖类似场景，且更细粒度（SINT 四元组 + revocation）。
- 安全漏洞接收迁移到 GitHub Security Advisories → 流程成熟化，但技术层面无新意。

#### 3. ANP 边缘化，IBM ACP 实质死亡

- ANP 最后架构级变动为 2026-03-05 的「Agent Description 扩展字段」，此后仅维护性提交。
- IBM ACP 距上次提交已近 1 年，不构成竞争参考。

### 与 ROADMAP 对比 & 路线判断

#### 无需调整优先级

- **v1.4 NAT 穿透**（v2.19 已完成）和 **HTTP/2**（v1.6 已完成）仍是核心护城河，竞品均未涉足。
- **身份认证**（Ed25519+DID，v1.3/v1.8/v1.9）ACP 领先窗口继续扩大 — A2A 连「声明认证方案」都还在 Epic 阶段。

#### 建议轻度跟进（P2）

1. **AgentCard `auth_schemes[]` 声明**（响应 A2A #1990）
   - 在现有 AgentCard 中增加可选字段：`auth_schemes: ["did:acp", "hmac-sha256", "bearer"]`
   - 工作量低，零破坏性，可提升与 A2A 生态的互认度。

2. **双向流评估备忘录**
   - A2A #1995 若在未来 2–3 个月内落地，可能对「实时协作 Agent」场景形成吸引力。
   - ACP 当前 SSE 为单向 server→client；评估 WebSocket upgrade 路径，但**不纳入近期版本**（违反轻量原则）。
   - 建议：在 `docs/research/` 下创建 `websocket-eval.md` 技术备忘录，记录 trade-off，供 Q3/Q4 决策参考。

#### 暂缓（与路线图一致）

- `data_handling_policy` GDPR 扩展（ROADMAP P3）：A2A 仍在讨论（IS#1606），无实质推进，维持观望。
- 原生 Pub/Sub：A2A 无新动向，维持「不跟进」决策。

### 本周行动建议

1. **【P2 — 轻量跟进】AgentCard 新增 `auth_schemes` 可选字段**
   - 对标 A2A Epic #1990，强化 ACP 身份体系的「可声明性」。
   - 预计 1 个开发轮次（2–3 小时），可在 v2.x 补丁版本中发布。

2. **【P3 — 研究储备】创建 `docs/research/websocket-eval.md`**
   - 评估 WebSocket 作为可选传输层的可行性、与现有 SSE 的共存方案、对轻量原则的冲击。
   - 若 A2A 双向流 Epic 进入 Implementation 阶段，此文档将成为快速响应的决策依据。

3. **【维持】继续押注「身份认证」差异化**
   - A2A 在 auth 上至少落后 ACP 2–3 个月，这是 v3.0 公开发布前的核心叙事支撑。
   - 建议在 Show HN 草稿中强化「ACP 是唯一内置自主权身份的标准」这一卖点。
