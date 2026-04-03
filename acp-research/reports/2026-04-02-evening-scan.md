# ACP Research Scan — 2026-04-02 Evening

**扫描时间**: 2026-04-02 16:15 CST  
**覆盖范围**: A2A (a2aproject/A2A), ANP (agent-network-protocol)  
**上次扫描**: 2026-04-02 上午

---

## A2A — 本周动态 (2026-03-26 → 2026-04-02)

### Commits (5 条，均为文档/生态，无 spec 变更)

| 日期 | SHA | 摘要 |
|------|-----|------|
| 2026-03-31 | c1169f4 | fix: OSPO action 路径修复 |
| 2026-03-31 | f991a08 | docs: 新增 Community SDKs 列表 |
| 2026-03-30 | 5ac9d2c | docs: 添加 Strale 到合作伙伴（上次扫描已发现） |
| 2026-03-27 | 72d1459 | docs: 添加 OIXA Protocol 到合作伙伴（上次扫描已发现） |
| 2026-03-26 | 32a7d3a | docs: Python tutorial 更新至 a2a-sdk v1.0.0-alpha.0 |

**结论**：spec 本周零变更。A2A 处于"生态扩张期"，无核心协议推进。

### 重要 Issues 更新

#### IS#1672 — Agent Identity Verification (🔥 热点)

- **状态**: open，**233 评论**（+20 vs 上次 213，持续增热）
- **核心问题**: A2A 没有协议级的 AgentCard 身份验证机制，完全依赖外部系统
- **当前进展**: 仍在讨论阶段，无 PR，无明确方向
- **ACP 对位**: v2.34 `peer_trust` (card_sig + did_consistent 两个维度直接解决这个问题)，**已实装并通过测试**

#### IS#1655 — QuerySkill() 运行时技能自省 (新关注)

- **状态**: open，7 评论，2026-04-01 更新
- **提案**: 增加 `QuerySkill()` 操作，允许运行时查询 Agent 技能能力
- **ACP 对位**: `capabilities.query_skill: true` + `GET /skills/query` — **ACP v2.x 早已实现**，A2A 还在 feature request 阶段

#### IS#652 — 服务端指定支持协议版本

- **状态**: open，长期 open，近日活跃
- **提案**: 允许服务端声明支持哪些协议版本
- **ACP 对位**: `acp_version` 字段在 AgentCard 中已声明，版本协商隐含支持

---

## ANP — 本周动态

- **commits since 2026-03-26**: 0（连续 4 周无更新）
- **结论**: ANP 处于停滞状态，保持关注但不追踪

---

## 战略分析

### ACP 领先窗口持续扩大

| 功能 | ACP 实现版本 | A2A 状态 |
|------|-------------|---------|
| AgentCard 身份验证 | v1.8 (card_sig) | IS#1672, 233评论, 无PR |
| 运行时技能自省 | query_skill (v2.x) | IS#1655, 新提案 |
| 消息幂等去重 | v2.32 | 无对应 issue |
| DID 离线 pubkey 解析 | v2.33 | 无对应 issue |
| 结构化信任评分 | v2.34 | IS#1628, 仍讨论中 |
| P2P 零服务器连接 | 核心架构 | 需要 OAuth 2.0 + infra |

### 下一步建议

1. **不需要跟随 A2A** — 他们的 spec 本周无变化，ACP 不需要响应
2. **IS#1655 是宣传机会** — 可在该 issue 下评论展示 ACP 已有实现（QuerySkill）
3. **v2.35 候选特性**：ROADMAP 中下一个里程碑，参考 IS#652 考虑显式版本协商协议

---

## 结论

本周 A2A 无 spec 进展，仍是文档/生态扩张阶段。ACP v2.34 在身份验证（IS#1672 对应功能）和信任评分上已远超 A2A 当前实现。继续按 ROADMAP 推进 v2.35。
