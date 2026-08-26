# ACP 竞品研究扫描报告

**日期**：2026-04-02（晚间扫描）  
**扫描范围**：A2A（a2aproject/A2A）、ANP（agent-network-protocol/AgentNetworkProtocol）  
**周期**：2026-03-26 以来

---

## A2A

### Commits（3/26 后）

| SHA | 日期 | 内容 |
|-----|------|------|
| `c1169f4` | 2026-03-31 | `fix: update OSPO action refs`（CI 配置路径修正，**无 spec 变更**） |

**结论**：本周 A2A 无协议层变更，仅 CI 维护。

### Issues（近期活跃）

| Issue | 标题 | 评论数 | 状态 |
|-------|------|--------|------|
| #1672 | Proposal: Agent Identity Verification for Agent Cards | 236 | 🟡 Open，持续活跃 |

**IS#1672 摘要（截至 2026-04-02 11:21 UTC）**：
- 提案：在 AgentCard 加 `verifiedIdentity` 字段，携带 ECDSA P-256 证书 + 第三方 issuer（getagentid.dev）
- 核心矛盾：需要中心化证书颁发机构（CA），与 ACP 离线优先/去中心化哲学相悖
- 评论量 236 条，仍无 PR，社区分歧明显（中心化 vs 去中心化）

**ACP 差异化优势**：
- ACP v1.8 已实现 Ed25519 自签名（无需第三方 CA）
- ACP v2.33 已实现 DID 离线公钥发现（`did:acp:<base64url(pubkey)>`）
- ACP v2.34 已实现五维度加权信任评分（`GET /peers/<id>/trust`）
- A2A 在身份验证上停留在讨论阶段，ACP 已完整落地 3 个版本

---

## ANP

**本周 commits**：0（空返回）  
**连续零更新**：5 周以上

---

## 本周 ACP 进展（自我评估）

| 版本 | 特性 | 测试 |
|------|------|------|
| v2.35 | Delivery ACK（`acp.delivered`） | DA1–DA10 10/10 ✅ |
| v2.36 | Read Receipt（`acp.read`）两阶段回执 | RR1–RR8 8/8 ✅ |

---

## 下期建议（v2.37 候选）

### 选项 A：`acp.typing` 打字状态指示
- WhatsApp/iMessage 体验："对方正在输入…"
- 帧：`{"type":"acp.typing","from":"<name>","ts":"<iso>"}`
- 轻量，无持久化，纯信号
- 差异化：A2A/ANP 均无此机制

### 选项 B：消息优先级（`priority` 字段）
- `priority: critical|high|normal|low`（4 级）
- 影响：SSE 推送排队优先级 + `/recv` 排序
- 适合 Orchestrator→Worker 任务调度场景

### 选项 C：`context_id` 归档与会话历史分页
- `GET /context/<id>/messages?page=N&limit=M`
- 补齐已有 context_id 但无分页的 gap

**推荐**：选项 A（`acp.typing`）— 完成两阶段回执后，打字状态是天然的第三阶段信号，代码量小，差异化明显，可与 v2.35/v2.36 并列形成「Agent 实时状态三件套」。

---

*生成时间：2026-04-02 19:43 CST*
