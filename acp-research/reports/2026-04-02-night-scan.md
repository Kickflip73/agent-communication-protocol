# ACP 竞品情报扫描报告 — 2026-04-02 夜间

*生成时间：2026-04-02 21:35 CST*

---

## A2A（a2aproject/A2A）

### 最新 Commit
- **2026-03-31** `c1169f4` — `fix: update OSPO action references to canonical org path (#1705)`
  - CI 工作流路径维护（`github/issue-metrics` → `github-community-projects/issue-metrics`）
  - **无 spec 变更，无功能变更**

### 核心 Issue 动态
| Issue | 标题 | 状态 | 评论数 | 变化 |
|-------|------|------|--------|------|
| IS#1672 | Proposal: Agent Identity Verification for Agent Cards | 🟡 Open | **241** | +5（上次 236） |

- IS#1672 连续活跃 11 天，241 评论，**仍无 PR**
- 社区对身份验证需求强烈，但 A2A 核心团队未给出时间表

### 开放 PR 动态
- PR#418 — `docs: A2A Agent Registrar implementation for Curated Agent Discovery`
  - 作者：`liuzengh`，创建于 2025-05-06，上次更新 2025-08-27
  - **超过 7 个月未合并，处于停滞状态**

### 结论
A2A 本周**零 spec 进展**。仅有 CI 配置维护。IS#1672（身份验证）社区持续施压，但核心团队无明确响应。

---

## ANP（agent-network-protocol/AgentNetworkProtocol）

### 最新 Commit
- **2026-03-05** `99806f4` — `feat: add failed_msg_id field to e2ee_error protocol message`
  - 允许接收方在解密失败时报告具体哪条消息失败
  - 协作者：`Co-Authored-By: Claude Opus 4.6`（值得关注：ANP 已使用 AI 辅助开发）
  - **距今 28 天，ANP 持续低活跃状态**

### 结论
ANP 连续 6 周无实质性 spec 更新。E2EE 错误恢复是小修补，不影响主协议方向。

---

## ACP 竞争优势评估（截至 2026-04-02）

| 维度 | A2A | ANP | **ACP** |
|------|-----|-----|---------|
| Agent 身份验证 | ❌ IS#1672 讨论中，无 PR | ✅ DID+E2EE | **✅ card_sig+DID+五维信任评分(v2.34)** |
| 消息回执 | ❌ 无 | ❌ 无 | **✅ 三件套(v2.35/v2.36/v2.37)** |
| 打字状态指示 | ❌ 无 | ❌ 无 | **✅ acp.typing(v2.37)** |
| Skill 动态更新 | ❌ 无 | ❌ 无 | **✅ PATCH /skills/<id>/limitations(v2.29)** |
| 零配置接入 | ❌ 需 OAuth/Card 配置 | ❌ 需 DID 配置 | **✅ --local-only 单命令启动** |
| P2P 无中心服务器 | ❌ 需中央注册表 | 部分 | **✅ 纯 P2P，Relay 仅打洞** |

---

## v2.38 候选方向

基于竞品分析，三个方向：

### 选项 A：消息优先级（`priority` 字段）
- `POST /message:send` 支持 `priority: critical|high|normal|low`
- SSE 推送排队 + `/recv` 排序按优先级
- 适合 Orchestrator→Worker 任务调度场景
- A2A/ANP 均无此机制
- **代码量：中（需修改消息队列逻辑）**

### 选项 B：会话历史分页（`GET /context/<id>/messages`）
- 补齐已有 context_id 但无历史查询的 gap
- `?page=N&limit=M&from_ts=<iso>` 参数
- 调试/审计场景高价值
- **代码量：中（需 context 消息持久化）**

### 选项 C：Agent 在线状态（`acp.presence`）
- `POST /message:presence` 设置状态（online/away/busy/offline）
- 与 acp.typing 三件套形成第四件套
- 帧：`{type:"acp.presence", status:"online|away|busy|offline", ts:"<iso>"}`
- **代码量：小（与 typing 同模式）**

**推荐：选项 A（消息优先级）**  
差异化价值最高，对多 Agent 协作场景（Orchestrator→Worker）有实际意义，A2A/ANP 均无，与 ACP 「轻量级实用主义」定位契合。

---

*下轮：文档轮（更新 docs/whats-new.md 补充 v2.37 Typing Indicator + docs/spec/typing-indicator-v2.37.md）*
