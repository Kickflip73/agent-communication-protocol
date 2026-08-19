# ACP 竞品周报 — 2026-08-19

_由贾维斯自动生成_

## A2A (Google) — 2026-08-19
- Stars: 25403 | Open Issues: 230
### 最新 Commits
- `16ba526` 2026-08-18 chore(governance): update Todd Segal to Distinguished Engineer (#2147)
- `1579a48` 2026-08-18 chore(governance): update ServiceNow representative (#2142)
- `2c3affc` 2026-08-17 build: Json schema generation. Fixes #2073 (#2074)
- `134a382` 2026-08-15 docs: fix broken links (#2139)
- `1eb4aa0` 2026-08-13 docs(spec): fix typo in specification doc (#1953)
### 新 Issues（功能请求）
- #1995 [Epic] Bidirectional streaming & improved stream semantics
- #1992 [Epic] Multi-turn interaction gaps — state acceptance rules, interrupt
- #1991 [Epic] Coherent Task History — gaps in semantics, querying, and observ
- #1990 [Epic] Auth scheme declaration & credential discovery in AgentCard
- #1989 [Epic] Client-directed skill selection

## ANP (社区)
- `6c6aa9b` 2026-08-18 docs: harden vnext P6 group E2EE delivery, verification, and terminal-
- `9789640` 2026-08-04 docs: revise messaging profile version strategy
- `593a374` 2026-08-03 fix: preserve avatars when contributor stats are pending (#92)
- `5e53512` 2026-08-03 fix: update contributor avatar automation (#91)
- `149ad00` 2026-08-03 docs: explain Agent Description extended fields (#89)

## IBM ACP
- `e5265ca` 2025-08-25 docs: A2A announcement (#230)
- `e8299f8` 2025-08-21 chore: bump version
- `00afccd` 2025-08-21 fix(python): revert cachetools version bump to avoid conflicts

## 本周行动建议
_(需贾维斯人工分析后补充)_

---

## 🔬 深度分析 — 贾维斯（J.A.R.V.I.S.）

### 一、竞品新动态（3条核心变化）

**① A2A 连开 5 个 Epic，酝酿大版本升级（#1989–#1995）**
本周 A2A 虽以治理提交为主，但 Issues 区突然集中涌现 5 个 Epic 级功能请求，覆盖**双向流、多轮交互、任务历史、认证方案声明、客户端技能选择**。这标志着 A2A 社区正在从“企业总线稳定期”向“v2.0 能力扩展期”过渡。尤其 #1995（Bidirectional streaming）和 #1990（Auth scheme in AgentCard）与我们当前的 P2P 实时性和身份认证赛道直接相关。

**② ANP 小幅回温：vnext P6 E2EE 文档硬化工**
沉寂数月的 ANP 于 8 月 18 日提交了一条文档更新，聚焦 vnext P6 组的端到端加密（E2EE）交付与验证。虽然整体仍处于低活跃状态，但 E2EE 方向与 ACP 的 Ed25519 + HMAC 安全层有潜在互补价值，值得观察。

**③ IBM ACP 确认归档 — 最后提交距今近 1 年**
IBM ACP 自 2025-08-25 的“A2A 公告”提交后彻底停更。这验证了 ROADMAP 中“参考即可、不再追踪”的判断，也从侧面印证了 Google A2A 在企业级赛道的碾压性生态吸引力。

### 二、与 ACP 路线图对比评估

| A2A Epic | ACP 现状 | 差距评估 |
|---------|---------|---------|
| #1995 Bidirectional streaming | SSE 单向推送（server→client） | ⚠️ 中等差距：SSE 可满足当前场景，但双向流对实时协作 Agent 有吸引力 |
| #1992 Multi-turn interaction gaps | ✅ context_id + Task 状态机（5 种）已支持 | ✅ 领先或持平 |
| #1991 Coherent Task History | ✅ `GET /tasks` 列表查询 + 分页（v2.2） | ✅ 已覆盖基础需求 |
| #1990 Auth scheme in AgentCard | ✅ AgentCard `capabilities` 已声明身份/HMAC/http2 等 | ✅ 领先，可扩展声明更多认证方案 |
| #1989 Client-directed skill selection | ✅ `POST /skills/query` + `QuerySkill()` API（v0.5） | ✅ 已支持 |

**结论**：A2A 的这 5 个 Epic 方向，ACP 在 4/5 上已具备同等或更优实现，唯一需关注的是 **#1995 双向流** — 这是 ACP SSE 架构的天然短板。

### 三、行动建议（2条）

**1. 【优先级：P1】启动双向流可行性预研（v3.x Backlog）**
- **背景**：A2A #1995 标志着社区对“server 主动 push + client 实时回传”的明确需求。当前 ACP 的 SSE 端点是纯单向，client 如需实时反馈必须另开 HTTP POST，存在时序耦合。
- **方向**：不引入 WebSocket（违反轻量原则），探索 **SSE-over-HTTP/2（Server Push / 双向流帧）** 或 **长轮询升级** 方案。
- **产出**：2 页预研文档（`research/bidirectional-streaming.md`），含 A2A #1995 讨论摘要、候选技术对比、对 ACP 传输层的侵入性评估。
- **时间**：下周完成初稿。

**2. 【优先级：P2】在 AgentCard 中预占 `auth_schemes[]` 字段（与 A2A #1990 对齐）**
- **背景**：A2A #1990 提议在 AgentCard 中声明支持的认证方案，便于客户端自动发现凭证需求。ACP 当前仅在 `capabilities` 中零散声明 `hmac_signing`、`did_identity` 等，缺少统一枚举。
- **方向**：在 `spec/core-v2.x.md` 中新增 `auth_schemes: string[]` 字段（如 `"ed25519"`、`"hmac-sha256"`、`"bearer"`），与现有 `capabilities` 并存，向后兼容。
- **产出**：规范草案 + `tests/test_auth_schemes.py` 测试用例（参考 limitations 字段的落地节奏）。
- **时间**：下下周完成，作为 v2.24 候选特性。

---

_分析完成时间：2026-08-19 09:10 CST | 贾维斯自动产出_
