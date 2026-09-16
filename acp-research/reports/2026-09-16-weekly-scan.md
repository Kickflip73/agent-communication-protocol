# ACP 竞品周报 — 2026-09-16

_由贾维斯自动生成_

## A2A (Google) — 2026-09-16
- Stars: 25785 | Open Issues: 253
### 最新 Commits
- `6d6640c` 2026-09-10 docs: improve readability and wording in life-of-a-task (#2226)
- `1e8a97a` 2026-09-10 docs: improve readability and wording in key-concepts (#2225)
- `7e66bae` 2026-09-10 docs: improve readability and wording in a2a-and-mcp (#2224)
- `ee4ec1c` 2026-09-10 docs: improve readability and wording in what-is-a2a (#2223)
- `98853be` 2026-09-01 docs(blog): improve visibility of blogs (#2195)
### 新 Issues（功能请求）
- #2125 [Extension Proposal]: Agent Steering — interruptible & steerable tasks
- #1995 [Epic] Bidirectional streaming & improved stream semantics
- #1992 [Epic] Multi-turn interaction gaps — state acceptance rules, interrupt
- #1991 [Epic] Coherent Task History — gaps in semantics, querying, and observ
- #1990 [Epic] Auth scheme declaration & credential discovery in AgentCard

## ANP (社区)
- `ee32805` 2026-09-10 Merge feat/anp-02-did-authentication into main
- `dbfded5` 2026-09-10 docs: extract DID authentication and generalize messaging methods
- `222429c` 2026-09-09 docs: introduce AWiki identity and messaging implementations
- `b7ba3ff` 2026-09-06 docs: align shared agent and verification guidance
- `541e4e7` 2026-09-03 docs: remove DID provider transition assertion object

## IBM ACP
- `e5265ca` 2025-08-25 docs: A2A announcement (#230)
- `e8299f8` 2025-08-21 chore: bump version
- `00afccd` 2025-08-21 fix(python): revert cachetools version bump to avoid conflicts

## 本周深度分析（贾维斯 · 2026-09-16）

### 1. A2A (Google) — 稳定迭代，方向性议题浮出水面

**动态判断：协议核心趋稳，创新转向「交互语义」层。**

- 近期 commits 全部是文档可读性打磨（#2223–#2226），无 spec 破坏性变更 → v1.x 核心语义已固化，社区重心转向补齐边角语义。
- Stars 25,785（3 月基线 22,643，半年 +14%），生态仍高速扩张。

**值得关注的 4 个新 Epic/提案：**

| Issue | 主题 | 对 ACP 的含义 |
|-------|------|--------------|
| #2125 | **Agent Steering**（可中断、可引导的任务执行） | 全新交互语义：任务运行中注入指令/纠偏。我们仅有 §10 Cancel（终止），无 Steering（干预）。差异化机会 ⭐ |
| #1995 | 双向流式 + stream 语义增强 | ACP 已有 SSE + context_id 传播（v1.7），基本对齐，暂无需动作 |
| #1991 | Coherent Task History（历史查询/可观测性） | 我们已有 `GET /tasks` 分页列表（v2.2），领先；可观测性扩展观察即可 |
| #1990 | **AgentCard Auth 声明 + 凭证发现** | ACP 的 Ed25519+DID+card_sig（v1.3/v1.8）已领先 6 个月+；建议关注其收敛方案，反向验证我们设计 |

**结论：** A2A 正在补交互与信任语义，恰好是我们 v1.5–v2.7x 已覆盖的领域。核心风险点是 #2125 Agent Steering——这是我们没有的新原语。

### 2. ANP (社区) — ⚠️ 重要变化：已复活

**动态判断：ROADMAP 标记「停更/不再追踪」已过时。**

- 2026-09-03 ~ 09-10 连续 5 次提交，且是实质性内容：
  - `feat/anp-02-did-authentication` 合入 main（DID 认证落地）
  - AWiki 身份 + 消息实现（`222429c`）
  - 移除 DID provider transition 断言（`541e4e7`）——正在收敛 DID 规范
- ANP 的 DID 方向与我们 `did:acp:` 高度同赛道，其认证实现细节值得重新评估（兼容/互操作机会）。

**结论：** 需要恢复每周追踪，并更新 ROADMAP 竞品表（ANP 状态改为「复活，DID 认证落地中」）。

### 3. IBM ACP — 确认死亡

- 最后 commit 2025-08-25，已停滞 13 个月。维持「参考即可」，不再消耗扫描精力（可考虑降低扫描频率或移出主线）。

---

## 行动建议

1. **【P1】重启 ANP 追踪 + DID 对标**：更新 ROADMAP 竞品表；重点读 `anp-02-did-authentication` 实现，评估与 `did:acp:` 的互操作可能性（若 ANP DID 可映射，将成为「跨协议互通」卖点）。
2. **【P2】立项调研 Agent Steering（A2A #2125）**：以 Extension 形式探索 `urn:acp:ext:steering/v1`（运行中任务注入指令），与既有 §10 Cancel 语义组合成完整的任务干预矩阵；先出 spec 草案再实现，避免过度设计。
3. **【P3】清理扫描配置**：IBM ACP 移出主线扫描或降频；A2A #1990 auth 声明保持观察，待其方案收敛后再决定是否在 AgentCard 中增加 `auth_schemes` 兼容字段。

_（本节由贾维斯自动分析生成，重大方向调整请 Stark 先生拍板）_
