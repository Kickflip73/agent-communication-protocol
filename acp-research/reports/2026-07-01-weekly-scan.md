# ACP 竞品周报 — 2026-07-01

_由贾维斯自动生成_

## A2A (Google) — 2026-07-01
- Stars: 24551 | Open Issues: 247
### 最新 Commits
- `5d2676e` 2026-06-30 docs: add Auto Agent Protocol and Lumika to partners list (#1907)
- `4374b82` 2026-06-22 docs: update a2a homepage banner (#1971)
- `dc8cc23` 2026-06-22 docs: update llms.txt to match v1.0 spec and site navigation (#1943)
- `28e27c9` 2026-06-22 ci: trigger docs build on changes to build inputs (#1967)
- `69dd57c` 2026-06-12 docs: restructure homepage information and add missing sections (#1874
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

---

## 贾维斯深度分析

### 一、A2A 五大 Epic 解读 — v2.0 规范方向浮出水面

本周 A2A 集中发布了 5 个 Epic 级 Issue（#1989–#1995），这是自 v1.0 发布以来**最密集的方向性信号**，预示 A2A v2.0 规范的核心关注点：

| Epic | 核心诉求 | ACP 现状 | 差异化评估 |
|------|----------|----------|------------|
| #1995 双向流式 | 任务执行中 Agent→Client 实时推送 | ✅ SSE 已实现（v0.4+），但为单向 | ACP 可快速补全双向流（SSE + client POST），复杂度低 |
| #1992 多轮交互缺陷 | 状态接受规则、中断语义 | ✅ context_id（v0.7）+ cancel 语义（v1.5）已解决 | **ACP 领先**。A2A 仍在讨论 ACP 已落地的问题 |
| #1991 Task History 语义 | 查询、可观测性 | ✅ GET /tasks 分页（v2.2）+ 离线队列（v2.0） | ACP 已有基础能力，可增强 history 事件流 |
| #1990 Auth 声明 | AgentCard 中声明认证方案 | ✅ Ed25519+DID（v1.3）+ JWKS（v2.18） | **ACP 领先**。但 A2A 探索的是「发现」层（credential discovery），ACP 可借鉴 |
| #1989 客户端 Skill 选择 | Client 指定调用 Agent 的哪个 Skill | ✅ QuerySkill()（v0.5） | ACP 已有，A2A 追赶中 |

**关键洞察**：A2A v2.0 的 5 个 Epic 中，ACP 已有 3 个的实现（#1992/#1991/#1989），1 个可快速补全（#1995），1 个需关注（#1990 credential discovery）。**ACP 在功能完备性上仍然领先 A2A 约 1-2 个版本周期。**

### 二、ANP 复活 — ANP-06 Meta Negotiation 机制值得关注

ANP 自 2026-03 月归档后，本周突然出现 5 个连续 commit（6 月 27 日），全部围绕 **ANP-06 Meta Negotiation**：

- **ANP-06 是什么**：Agent 之间在通信前协商协议参数（编码、压缩、加密方式、版本号等）的元协议层
- **战略意义**：这是 ACP 和 A2A 都**没有**的协议层——当前两者都假设通信参数是固定的
- **评估**：
  - 优势：理论上更灵活，可支持异构 Agent 间协议适配
  - 劣势：增加握手复杂度，与 ACP「零配置即用」原则有张力
  - **ACP 立场**：暂不跟进作为核心特性，但可作为 **Extension**（`urn:acp:ext:meta-negotiation/v1`）预留扩展点

### 三、IBM ACP — 已死，无需追踪

最后一次 commit 为 2025-08-25，距今近 11 个月无任何活动。正式移出每周扫描范围。

### 四、ROADMAP 对比 — 是否需要调整？

| ROADMAP 现有项 | 本周竞品动态 | 调整建议 |
|-----------------|-------------|----------|
| v1.4 NAT 穿透 | 无竞品相关动态 | 维持，P0 不变 |
| v3.0 公开发布 | A2A 生态持续扩张（24.5k stars，新增 partners） | **建议加速**：真 P2P 完成后尽快发布，A2A 生态优势在扩大 |
| trust.signals | A2A #1990 Auth 声明 | 已领先，维持 |
| data_handling_policy | A2A #1606 GDPR 字段 | 维持 P3，不升优先 |
| ❌ 无 | A2A #1995 双向流式 | **新增 P1 候选**：ACP SSE 单向流 → 双向流，补全后差异化更强 |
| ❌ 无 | ANP-06 Meta Negotiation | **新增 P3 候选**：Extension 预留，暂不核心化 |
| IBM ACP 追踪 | 已停更 11 个月 | **移除**：不再追踪 IBM ACP |

### 五、行动建议

1. **[P1 新增] 双向流式通信**：在现有 SSE 基础上增加 Client→Agent 的流式消息通道（`POST /tasks/{id}/stream`），使任务执行中双方可实时交互。A2A #1995 刚启动讨论，ACP 若快速落地可再次形成「A2A 讨论中 → ACP 已落地」的差异化。预估工作量：1-2 天。

2. **[P3 新增] Meta Negotiation Extension 预留**：在 Extension 机制中注册 `urn:acp:ext:meta-negotiation/v1`，定义最小协商端点（`GET /negotiate`），但不作为核心特性。ANP 复活动向需持续观察，若社区采纳可升级优先级。

3. **[战略] 加速 v3.0 公开发布**：A2A stars 从 22.6k→24.5k（+8.4%），生态效应在加速。ACP 需在真 P2P 完成后尽快发布 Show HN，抢占「轻量 P2P Agent 通信」品类心智。

4. **[维护] 移除 IBM ACP 扫描**：`weekly-scan.sh` 中移除 IBM ACP 仓库追踪，减少无效 API 调用。

5. **[观察] A2A #1990 Auth Scheme Discovery**：A2A 探索 AgentCard 中声明认证方案和凭证发现，这是 ACP JWKS 端点（v2.18）未覆盖的「发现层」。若 A2A 形成规范，ACP 可通过 Extension 适配，暂不主动投入。
