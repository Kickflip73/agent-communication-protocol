# ACP 竞品周报 — 2026-08-26

_由贾维斯自动生成_

## A2A (Google) — 2026-08-26
- Stars: 25492 | Open Issues: 239
### 最新 Commits
- `5e233e5` 2026-08-25 docs: add TiEQi-A2A as partner (#1900)
- `28097db` 2026-08-25 chore: add discord links (#2146)
- `a9c7f4c` 2026-08-25 docs: add OpenAgents to partners list (#2168)
- `67cf356` 2026-08-25 chore: add rust and repo maintainers (#2175)
- `16ba526` 2026-08-18 chore(governance): update Todd Segal to Distinguished Engineer (#2147)
### 新 Issues（功能请求）
- #1995 [Epic] Bidirectional streaming & improved stream semantics
- #1992 [Epic] Multi-turn interaction gaps — state acceptance rules, interrupt
- #1991 [Epic] Coherent Task History — gaps in semantics, querying, and observ
- #1990 [Epic] Auth scheme declaration & credential discovery in AgentCard
- #1989 [Epic] Client-directed skill selection

## ANP (社区)
- `35332bd` 2026-08-25 update messaging vnext DID transition semantics
- `32d34d1` 2026-08-25 docs: sync stable subject continuity to English specs
- `2b3b836` 2026-08-25 Add the stable subject ID for did:wba
- `a1e0109` 2026-08-24 docs: add core protocol vnext drafts for ANP-03 and ANP-04
- `6c6aa9b` 2026-08-18 docs: harden vnext P6 group E2EE delivery, verification, and terminal-

## IBM ACP
- `e5265ca` 2025-08-25 docs: A2A announcement (#230)
- `e8299f8` 2025-08-21 chore: bump version
- `00afccd` 2025-08-21 fix(python): revert cachetools version bump to avoid conflicts

---

## 🔬 贾维斯深度分析

### 一、竞品新动态（3 条）

#### 1. A2A 发布 5 个 Epic 级议题，聚焦流式通信与身份认证
A2A 近期一次性抛出 5 个 Epic Issue（#1989–#1995），核心方向覆盖：
- **#1995 Bidirectional streaming** — 双向流式传输语义（当前 ACP 为 SSE 单向）
- **#1992 Multi-turn interaction gaps** — 多轮交互状态机补全（ACP 已有 `context_id` + cancel 语义，部分领先）
- **#1991 Coherent Task History** — 任务历史查询与可观测性（ACP v2.2 已落地 `GET /tasks` 分页，具备先发优势）
- **#1990 Auth scheme declaration** — AgentCard 认证方案声明（**直接对标** ACP v1.3 Ed25519+DID；A2A 仍在设计阶段，我们领先约 6 个月）
- **#1989 Client-directed skill selection** — 客户端主导技能选择（ACP 有 `QuerySkills()`，但方向可能不同，需持续跟踪）

** Stars 增长**：22,643（2026-03）→ 25,492（2026-08），+12.6%，生态扩张稳健。

#### 2. ANP 死而复生，推出 vnext 协议草案
ANP 在 3 月份被 ROADMAP 标记为「已归档/停更」（最后活跃 2026-03-05），但 **8 月份突然出现密集提交**：
- DID 过渡语义更新
- `did:wba` 稳定主题 ID
- ANP-03 / ANP-04 核心协议 vnext 草案
- P6 组 E2EE 交付、验证与终端加固

**这意味着去中心化身份赛道仍有活跃玩家**，且 ANP 的 `did:wba` 与我们的 `did:acp` 形成直接竞争。ROADMAP 中「不再追踪 ANP」的判定需要修正。

#### 3. IBM ACP 继续休眠，A2A 生态持续扩张
- IBM ACP 最新提交仍为 **2025-08-25**（一年前），基本可判定项目停滞。
- A2A 新增 TiEQi-A2A、OpenAgents 合作伙伴，Discord 社区建立，治理层更新（Todd Segal 晋升 Distinguished Engineer）。

---

### 二、与 ROADMAP 路线图对比

| 维度 | ROADMAP 原判定 | 本周新事实 | 偏差评估 |
|------|---------------|-----------|---------|
| ANP 状态 | 🔴 已归档，不再追踪 | 🟢 8 月密集提交，vnext 草案发布 | **显著偏差**，需恢复追踪 |
| A2A 身份认证 | ⏳ Issue #1672 讨论中 | #1990 Epic 启动，仍处设计期 | 我们仍领先 6 个月，窗口仍在 |
| A2A 任务历史 | 无直接对标 | #1991 Epic 启动 | 我们 v2.2 `GET /tasks` 已落地，先发优势 |
| A2A 双向流式 | 无直接对标 | #1995 Epic 启动 | **潜在新差距**，需评估 |

**ROADMAP 待更新项：**
1. ANP 状态从「已归档」修正为「🟡 复活追踪」，更新最后活跃日期为 2026-08-25。
2. A2A Epic #1995（双向流式）纳入观察列表。

---

### 三、行动建议（2 条）

#### 建议 1：恢复 ANP 追踪，评估 `did:wba` 对 `did:acp` 的竞争威胁
ANP vnext 的 `did:wba` + 稳定主题连续性 + E2EE 组交付，与 ACP 身份体系高度重叠。建议：
- 下周安排一次技术对标扫描，提取 `did:wba` 规范草案与 `did:acp` 的差异点。
- 若 ANP 的 DID 方案有技术优势（如 W3C 标准兼容性更强），评估是否借鉴或声明差异。
- 在 README / 文档中增加「ACP vs ANP（vnext）」对比章节，抢占叙事主动权。

#### 建议 2：研究可选的双向流式传输绑定，对冲 A2A #1995
A2A 的双向流式 Epic 仍处于早期讨论，预计落地周期 3–6 个月。ACP 当前 SSE 为单向 server→client。建议：
- 研究在保持「轻量、零依赖」原则下，增加 **可选 WebSocket 传输绑定**（或 SSE-over-HTTP/2 服务端推送）。
- 若实现成本可控，可在 A2A 落地前发布，形成「ACP 已支持双向流式，A2A 还在讨论」的差异化叙事。
- 若成本过高，则保持观察，将资源投入真 P2P NAT 穿透（v1.4）这一核心卖点。

---

_分析完成时间：2026-08-26 09:12 CST | J.A.R.V.I.S._
