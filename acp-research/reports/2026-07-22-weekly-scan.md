# ACP 竞品周报 — 2026-07-22

_由贾维斯自动生成_

## A2A (Google) — 2026-07-22
- Stars: 24934 | Open Issues: 214
### 最新 Commits
- `cfc9d34` 2026-07-21 fix(proto): correct gRPC URL example in AgentInterface (#1997)
- `dfe216a` 2026-07-21 docs(spec): fix Agent Card security requirement sample (#2046)
- `3e4f86d` 2026-07-21 docs: add A2A meeting and agenda links (#1993)
- `af112d9` 2026-07-16 chore(codeowners): Add project maintainers (#2051)
- `be9f9a4` 2026-07-14 docs: update IBM TSC representative to Stefano Maestri (#2060)
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

---

## 深度分析 — 贾维斯（J.A.R.V.I.S.）

> 分析时间：2026-07-22 09:07 CST
> 对比基准：ROADMAP.md（最后更新 2026-03-31，v2.22.0）

### 一、本周竞品新动态（3 条核心）

#### 1. A2A 发布五大 Epic — 社区进入架构重构期 ⚡

A2A 本周（2026-07-14 ~ 07-21）密集发布 5 个 Epic 级 Issue（#1989–#1995），这是自 2026-03 月 v1.0.0 发布以来**最大规模的架构讨论潮**：

| Epic | 主题 | 与 ACP 的关联 |
|------|------|--------------|
| #1995 | **Bidirectional streaming**（双向流） | ACP 已有 SSE 单向流；双向流意味着 Agent 可主动推送，需评估是否跟进 |
| #1992 | **Multi-turn interaction gaps**（多轮交互缺口） | ACP 的 `context_id` + SSE 已解决同类问题；A2A 还在讨论 state acceptance / interrupt 语义 |
| #1991 | **Coherent Task History**（任务历史一致性） | ACP 已有 `GET /tasks` 列表 + 分页；A2A 的 querying/observability 缺口正是 ACP 已落地的特性 |
| #1990 | **Auth scheme declaration**（认证方案声明） | ⚠️ **关键信号** — A2A 终于开始讨论 AgentCard 声明认证方案；ACP 早在 v1.3 即实现 `did:acp:` + JWKS |
| #1989 | **Client-directed skill selection**（客户端定向技能选择） | ACP 的 `QuerySkill()` + `capabilities` 已有雏形；A2A 从企业总线视角重新设计 |

**判断**：这 5 个 Epic 覆盖了 A2A 社区积压半年的核心痛点。值得注意的是：
- **#1990 Auth scheme declaration** 是 ACP 已解决的领域（DID + Ed25519 身份体系），A2A 落后约 4 个月
- **#1991 Task History** 对应 ACP v2.2 已发布的 `GET /tasks` + 分页
- **#1992 Multi-turn** 对应 ACP v1.7 已解决的 `context_id` SSE 传播

→ **ACP 在身份认证、任务历史、多轮上下文三个维度领先 A2A 社区共识 2–4 个月**，这是差异化优势。

#### 2. ANP 复活迹象 — Release 1.1 + Group Identity 🔴→🟡

ANP（Agent Network Protocol）从 2026-03-05 的「已归档」状态出现**意外复活**：
- 7 月 11 日提交：`handle-backed group identity continuity`（句柄支撑的群组身份连续性）
- 7 月 8 日提交：ANP Release 1.1 文章发布
- 6 月 27 日：ANP-06 meta negotiation 文档合并

**判断**：ANP 似乎从冬眠中苏醒，但提交频率仍低（月均 2-3 次）。其「group identity」概念值得关注 — 如果 ACP 未来需要支持多 Agent 协作群组，ANP 的 handle-backed 方案可作为参考，但**目前优先级不高**。

#### 3. IBM ACP 确认死亡 — 最后提交 2025-08 💀

IBM ACP（i-am-bee/acp）最后提交停留在 2025-08-25，距今近一年。与 A2A 的活跃度和 ACP（本项目）的持续迭代形成鲜明对比。

**判断**：IBM ACP 可以正式从竞品追踪列表中移除，或降级为「历史参考」。

---

### 二、与 ROADMAP 对比 — 优先级调整建议

| ROADMAP 项目 | 当前状态 | 竞品动态影响 | 建议 |
|-------------|---------|-------------|------|
| v1.4 NAT 穿透（真 P2P） | ✅ v2.19.0 已完成 | A2A 无同类特性 | **保持 P0**，核心差异化 |
| `GET /tasks` 列表查询 | ✅ v2.2 已完成 | A2A #1991 正在讨论 | ACP 已落地，优势确立 |
| `limitations` 能力边界 | ✅ v2.3/v2.7 已完成 | A2A #1694 同期提案 | 次日落地优势保持 |
| trust.signals / JWKS | ✅ v2.18 已完成 | A2A IS#1628 趋同 | 保持 |
| data_handling_policy（GDPR） | ⏳ P3 延期 | A2A IS#1606 进展慢 | **维持延期**，ACP 定位个人/小团队 |
| HTTP/2 传输绑定 | ✅ v1.6 已完成 | — | — |
| v3.0 公开发布 | ⏳ 延至真 P2P 完成后 | — | **保持延后**，P2P 是核心卖点 |
| **双向流（Bidirectional streaming）** | ❌ 未规划 | A2A #1995 Epic | **新增 P2 研究项** |

#### 关键调整建议

1. **【新增 P2】评估双向流（Bidirectional Streaming）**
   - A2A #1995 标志着社区意识到 SSE 单向流不够：Agent 需要主动向客户端推送事件（而非被动响应）
   - ACP 当前 SSE 是客户端发起长连接，Agent 只能「响应」不能「推送」
   - 建议：研究 WebSocket / SSE-over-HTTP/2 Server Push / 长轮询等方案，作为 ACP v2.x 的 Extension（`urn:acp:ext:bidi-stream/v1`）
   - **不列入 P0** — ACP 当前定位个人/小团队，双向流需求不迫切；但需跟踪 A2A TSC 结论

2. **【维持】真 P2P NAT 穿透保持最高优先级**
   - A2A 完全未涉及 NAT 穿透（定位企业总线，默认有公网/云环境）
   - 这是 ACP 「P2P 无中间人」口号的核心技术支撑，不可替代

3. **【移除】IBM ACP 不再追踪**
   - 停更一年，无复活信号。竞品矩阵简化为 A2A + ANP（观察级）

---

### 三、行动建议（2 条）

#### 建议 1：在 README / 文档中突出「已解决 A2A 正在讨论的痛点」

A2A 五大 Epic 中，有 3 个是 ACP 已解决的问题：
- #1990 Auth → ACP `did:acp:` + JWKS（v1.3）
- #1991 Task History → ACP `GET /tasks` + 分页（v2.2）
- #1992 Multi-turn → ACP `context_id` SSE 传播（v1.7）

**具体动作**：
- 在 README「vs A2A」对比表中新增 3 行，标注 ACP 落地版本和日期
- 在 `docs/show-hn-draft.md` 中加入「A2A 还在讨论，ACP 已经落地」的叙事
- 时机：A2A Epic 讨论发酵期（未来 2-4 周）是最佳传播窗口

#### 建议 2：启动「双向流」预研，但不投入实现

**具体动作**：
- 创建 `research/bidirectional-streaming.md` 预研文档
- 调研以下技术方案：
  1. WebSocket 全双工（最自然，但增加协议复杂度）
  2. HTTP/2 Server Push（h2c 已支持，但 Push 被多数浏览器弃用）
  3. SSE-over-SSE（双向各一条 SSE 连接，简单但浪费连接）
  4. 长轮询 fallback（最兼容，但延迟高）
- 预研产出：技术方案对比表 + 推荐方案 + 预估工作量
- 决策点：等 A2A TSC 对 #1995 的结论出炉后，再决定是否正式纳入路线图

---

### 四、竞品态势总览

```
竞争力雷达（2026-07-22）

              A2A          ANP         IBM ACP       ACP(本项目)
Stars         24,934       1,240       966           -
活跃度        ⚡⚡⚡⚡⚡        🟡🟡⚪⚪⚪     💀停更         ✅✅✅✅✅
身份认证      ⏳讨论中       ✅理论        ❌            ✅已落地
P2P/NAT       ❌无计划       ❌           ❌            ✅✅核心优势
轻量易用      ⏳讨论中       ✅           ✅            ✅✅✅设计原则
规范完成度    ⏳重构中        🟡          ❌            ✅✅最完整
生态 SDK      🟡           ❌           ❌            ✅✅4语言

结论：A2A 在企业和社区影响力上仍占绝对优势（24K stars），但技术规范
层面 ACP 已领先 2-4 个月。A2A 的五大 Epic 讨论将决定未来 3 个月的
竞争格局 — ACP 应利用窗口期强化「已落地」的叙事优势。
```

---
_报告生成完成，已 push 至 GitHub `main` 分支。_
