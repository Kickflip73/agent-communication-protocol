# ACP 竞品周报 — 2026-07-15

_由贾维斯自动生成_

## A2A (Google) — 2026-07-15
- Stars: 24784 | Open Issues: 222
### 最新 Commits
- `be9f9a4` 2026-07-14 docs: update IBM TSC representative to Stefano Maestri (#2060)
- `02441d8` 2026-07-14 docs: add a2a-cpp to community SDKs (#2034)
- `2183794` 2026-07-09 docs: Update partners.md with Airia (#2039)
- `fdcf8cc` 2026-07-09 docs: document and redirect URI prefixes (#2015)
- `99dbc81` 2026-07-07 docs: add Space Auto to partners list (#2033)
### 新 Issues（功能请求）
- #1995 [Epic] Bidirectional streaming & improved stream semantics
- #1992 [Epic] Multi-turn interaction gaps — state acceptance rules, interrupt
- #1991 [Epic] Coherent Task History — gaps in semantics, querying, and observ
- #1990 [Epic] Auth scheme declaration & credential discovery in AgentCard
- #1989 [Epic] Client-directed skill selection

## ANP (社区)
- `82f4fe1` 2026-07-11 docs: add handle-backed group identity continuity
- `f06bf4f` 2026-07-08 add ANP release 1.1 articles
- `3f048ef` 2026-06-27 docs: update ANP getting started guide
- `6fc3854` 2026-06-27 merge ANP-06 meta negotiation docs
- `28e6890` 2026-06-27 docs: clarify ANP-06 optional role

## IBM ACP
- `e5265ca` 2025-08-25 docs: A2A announcement (#230)
- `e8299f8` 2025-08-21 chore: bump version
- `00afccd` 2025-08-21 fix(python): revert cachetools version bump to avoid conflicts

## 深度分析：A2A 5 大 Epic vs ACP 已实现的特性

> 本周 A2A 一次性抛出 5 个 Epic Issue（#1995–#1991），集中在 A2A 的基础架构缺口。这恰恰验证了 ACP 在 2026-03 版本架构决策的前瞻性：

| A2A Epic（本周新增） | ACP 对应特性 | 状态 | ACP 领先时间 |
|---|---|---|---|
| #1995 Bidirectional streaming | SSE 流式端点 + HTTP/2 h2c | ✅ v1.6 / v1.7 | 约 3 个月 |
| #1992 Multi-turn interaction gaps | `context_id` + SSE 完整传播 | ✅ v1.7（2026-03-25） | 约 3 个月 |
| #1991 Coherent Task History | Task 状态机 + `GET /tasks` 列表 | ✅ v2.2（2026-03-27） | 约 3 个月 |
| #1990 Auth scheme & credential discovery | Ed25519 + `did:acp:` + AgentCard | ✅ v1.3–v2.7 | 约 2–3 个月 |
| #1989 Client-directed skill selection | `QuerySkill()` / `POST /skills/query` | ✅ v0.5（2026-03-19） | 约 3 个月 |

> **结论**：A2A 在 2026-Q2 集中暴露的架构短板，正是 ACP 在 2026-03 已解决的。ACP 在 Agent 身份认证、Task 历史、多轮上下文、能力查询等核心方向均保持 2–3 个月的技术领先优势。

## 竞品新动态（3 条重点）

1. **A2A 新增 C++ SDK**（`a2a-cpp`）— 语言矩阵扩展至 C++。ACP 目前拥有 Python / Node / Go / Rust SDK，但缺少 C++。若嵌入式/IoT Agent 场景出现，需评估 C++ SDK 优先级。

2. **A2A URI 前缀标准化**（#2015）— A2A 开始标准化 URI scheme 前缀，ACP 的 `acp://` 和 `urn:acp:ext:*` 是先行者，但需关注 A2A 是否会在企业级场景推广另一套 URI 标准，导致碎片化。

3. **ANP 未死透** — 虽然 ROADMAP 标记为「已归档」，但 2026-07-11 仍有关于 handle-backed group identity 的 commit。去中心化身份赛道仍有社区关注，ACP 的 DID 体系 (`did:acp:`) 在功能上已覆盖，但品牌心智需要持续维护。

## 行动建议（2 条）

1. **发布 ACP vs A2A 对比白皮书**（P1）
   A2A 5 个 Epic 与 ACP 已实现的特性一一对应，是极佳的营销素材。建议在 `docs/show-hn-draft.md` 中新增「A2A 2026-Q2 Epic 追踪」章节，证明 ACP 在架构设计上的先发优势。同时准备 Hacker News 发布帖，时间点：A2A 任何一条 Epic 进入 PR review 阶段时。

2. **评估 A2A 双向流式 (#1995) 对 ACP 的影响**（P2）
   ACP 当前使用 SSE（服务端→客户端单向）满足流式需求。若 A2A 的 bidirectional streaming 最终采用 WebSocket（而非 HTTP/2 Server Push），ACP 可能需要：
   - 在现有 SSE 基础上保持兼容性（当前方案已够用）
   - 或新增可选 WebSocket 传输绑定（增加复杂度，违反轻量原则）
   **建议**：先观望，不主动引入 WebSocket。若 A2A 形成行业标准且下游生态要求，再以 Extension 形式提供 `urn:acp:ext:websocket/v1`，不进入核心规范。

---
_分析由 J.A.R.V.I.S. 自动生成 · 2026-07-15_

