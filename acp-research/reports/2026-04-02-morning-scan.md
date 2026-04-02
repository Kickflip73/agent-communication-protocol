# ACP 竞品扫描报告 — 2026-04-02（上午）

> 扫描时间：2026-04-02 09:51 Asia/Shanghai  
> 扫描员：J.A.R.V.I.S.（研究轮）

---

## A2A (google-a2a/A2A)

### 最新 commit
- **c1169f4** (2026-03-31) — `fix: update OSPO action references to canonical org path (#1705)`
  - 仅 CI/CD GitHub Actions 路径更新，无功能变更
  - `github/issue-metrics` → `github-community-projects/issue-metrics`
  - **结论：无实质性更新，上次扫描（2026-04-01）以来无协议变更**

### 热门 Issue 动态
- **IS#1672** — "Proposal: Agent Identity Verification for Agent Cards"（2026-03-22 开启）
  - 当前 **213 条评论**（较上次 +若干），仍最活跃讨论帖
  - 核心诉求：Agent Card 缺乏密码学身份验证，当前仅靠 HTTPS/OAuth 做传输层信任
  - 提案方向：在 Agent Card 中嵌入公钥/DID，支持签名验证
  - **ACP 启示**：我们的 `peer_card_signature` 特性（v2.16）已先行实现类似机制；可在 IS#1672 中发声展示差异化

### PR 跟踪
- PR#1655 (QuerySkill) — **仍未合并**（已 6+ 周）；无最新活动
- PR#1694 — 状态无变化

### 趋势判断
A2A 近期维护重心偏向 CI/基础设施，协议核心规范无实质演进。**IS#1672 身份验证讨论**是当前最重要的协议走向信号。

---

## ANP (agent-network-protocol/AgentNetworkProtocol)

### 最新 commit
- **99806f4** (2026-03-05) — `feat: add failed_msg_id field to e2ee_error protocol message`
  - 允许接收方上报解密失败的具体消息 ID，发送方据此重传
  - Co-Authored-By: Claude Opus 4.6（有趣：ANP 也在用 AI 写代码）
  - **ACP 关联**：我们的 `failed_message_id`（v2.30）+ `message_dedup`（v2.32）在语义上与此高度一致，但 ACP 更进一步（dedup 窗口 + server_seq 回传）
  - ANP 自 2026-03-05 起无新 commit —— 停更超过 4 周

### 结论
ANP 活跃度持续下降，ACP 与其差距进一步扩大。

---

## 综合评估

| 维度 | A2A | ANP | ACP（我们） |
|------|-----|-----|-------------|
| 近期活跃度 | 低（CI 维护） | 极低（4周无更新） | ✅ 高（v2.32 今日完成） |
| 身份验证 | 讨论中（IS#1672） | E2EE 加密 | ✅ peer_card_signature v2.16 |
| 消息幂等 | 无 | failed_msg_id（e2ee层） | ✅ 30s TTL dedup v2.32 |
| Skill 发现 | PR 阻塞中（6周+） | 无 | ✅ GET /skills + limitations v2.28-2.31 |
| 运行时能力更新 | 无 | 无 | ✅ PATCH /skills/<id>/limitations v2.31 |

---

## 值得关注的信号

1. **IS#1672 身份验证（213评论，极热）**：A2A 社区对 Agent 身份验证呼声极高。ACP 已有 `peer_card_signature`，可考虑：
   - 在 IS#1672 中以 ACP 为参考发声（提升曝光度）
   - 规划 ROADMAP 中的 "AgentCard DID/公钥绑定" 特性

2. **ANP 停更**：ANP 的 `failed_msg_id` 思路已被 ACP 超越（我们有完整的 30s dedup 窗口）。可在 README 的竞品对比表中进一步强化这一差距。

3. **A2A PR#1655 长期阻塞**：QuerySkill 6周未合并，说明 A2A 审批流程沉重。ACP 船小好掉头，应利用这一窗口期快速迭代。

---

## 建议下一步

| 优先级 | 建议 |
|--------|------|
| P1 | ROADMAP 新增：AgentCard 公钥/签名发现（对标 IS#1672，强化 v2.16 能力） |
| P2 | 考虑在 A2A IS#1672 中发声，展示 ACP peer_card_signature 的实现参考 |
| P3 | README 竞品表增加「消息幂等」行（ANP e2ee 层 vs ACP HTTP 层 30s TTL） |

---

**本轮无需更新 ROADMAP 里程碑（下一个里程碑待 Stark 先生确认方向）。**
