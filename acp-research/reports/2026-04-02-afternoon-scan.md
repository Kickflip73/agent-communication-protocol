# ACP 竞品情报 — 2026-04-02 午后扫描

**扫描时间**: 2026-04-02 14:08 (Asia/Shanghai)  
**ACP 当前版本**: v2.34.0  
**扫描范围**: A2A (google/A2A) · ANP (agent-network-protocol/AgentNetworkProtocol)

---

## A2A (a2aproject/A2A)

### 最新 5 commits（截至 2026-04-02）

| Commit | 日期 | 作者 | 内容 |
|--------|------|------|------|
| `c1169f4` | 2026-03-31 | zkoppert | fix: OSPO action 路径修正（`github/issue-metrics` → `github-community-projects/issue-metrics`）— **无功能变更** |
| `f991a08` | 2026-03-31 | alan blount | docs: 新增 Community SDKs 页面（Rust×2、Swift、Elixir） |
| `5ac9d2c` | 2026-03-30 | petterlindstrom79 | docs: 新增 Strale 合作伙伴（API marketplace, 273 skills, A2A + MCP + x402） |
| `72d1459` | 2026-03-27 | ivoshemi-sys | docs: 新增 OIXA Protocol（Agent 雇佣+支付协议, A2A + x402 + Base Mainnet USDC 托管） |
| `32a7d3a` | 2026-03-26 | sokoliva | （截断，未能获取完整内容） |

### 关键观察

**A2A 近一周无 spec 级别变更** — 全是文档和合作伙伴更新。这是重要信号：

1. **核心 spec 处于稳定期**（可能在准备某个大版本，也可能陷入讨论僵局）
2. **生态扩张活跃**：Rust/Swift/Elixir SDK 社区贡献；Strale、OIXA 等合作伙伴接入
3. **x402 micropayment** 出现两次（Strale + OIXA）— Agent 支付层正在形成，值得关注
4. **OIXA 的逆向拍卖模型**（agents bid to complete tasks）是一个新方向，ACP 尚未涉足

### ACP 当前领先点（再次确认）
- IS#1628（trust signals）+ IS#1672（身份验证）：仍为"open discussion"，无 PR
- ACP v2.34 已有完整实现的 `GET /peers/<id>/trust`，A2A 连 spec 都没有

---

## ANP (AgentNetworkProtocol)

### 最新 5 commits（截至 2026-04-02）

| Commit | 日期 | 作者 | 内容 |
|--------|------|------|------|
| `99806f4` | 2026-03-05 | changshan | feat: `e2ee_error` 新增 `failed_msg_id` — 接收方报告具体哪条消息解密失败 |
| `761087d` | 2026-03-05 | changshan | feat: add handle feature |
| `1f0abd2` | 2026-03-03 | changshan | feat: `client_msg_id` 幂等去重 + `server_seq` 有序性（E2EE IM 协议）|
| `b1c1c76` | 2026-03-01 | changshan | docs: update e2ee protocol |
| `eb4a10f` | 2026-02-27 | changshan | docs: DID-WBA spec 中 `service` 字段重命名为 `aud` |

### 关键观察

1. **ANP 最后一次 commit 是 2026-03-05（近一个月无更新）** — 项目进入低活跃期
2. **`client_msg_id` + `server_seq`**（2026-03-03）：和 ACP v2.32 的 `message_id` 幂等设计方向完全一致，但 ANP 是协议规范层，ACP 已有运行实现
3. **`failed_msg_id`**（2026-03-05）：E2EE 层的错误报告精确化，ACP 无 E2EE 层（不需要），但 `failed_msg_id` 概念可借鉴用于未来的 delivery_ack 机制
4. **DID-WBA `aud` 字段**：与 JWT 标准 `aud` claim 对齐，ACP 的 `did:acp:` 体系不依赖 DID-WBA，可参考但不强跟

---

## 战略分析

### 本轮核心发现

| 维度 | A2A | ANP | ACP v2.34 |
|------|-----|-----|-----------|
| 近期 spec 变更 | ❌ 无（仅文档/生态） | ❌ 近4周无更新 | ✅ v2.34 trust score |
| Agent 支付层 | ⚠️ 生态合作（x402） | ❌ 无 | ❌ 尚无（机会点） |
| 幂等消息 | ❌ 无 spec | ✅ `client_msg_id`（spec only） | ✅ `message_id`（已实现） |
| 信任评分 | ❌ IS#1628 讨论中 | ❌ 无 | ✅ `GET /peers/<id>/trust` |
| 离线 DID 解析 | ❌ IS#1672 讨论中 | ✅ DID-WBA（需 DNS） | ✅ 零网络调用 |

### 值得关注的新方向

**Agent 微支付层**（来自 Strale + OIXA 的观察）：
- x402 协议（HTTP 402 + USDC 支付）正在成为 Agent 经济基础设施
- ACP 目前无支付层，这是 A2A 生态正在发展而 ACP 未触及的领域
- **建议**：可考虑 v2.x 增加 `payment_channel` 字段到 AgentCard（声明接受 x402 或其他支付方式），或 `GET /peers/<id>/payment-info`

**OIXA 逆向拍卖模型**：
- Agent 发布任务 → 多个 worker agent 投标 → 最低价中标
- 这是 `QuerySkill` 的逻辑延伸，ACP 的 `GET /skills/query` 已有基础
- **建议**：ROADMAP 中可考虑 `Task Bidding Protocol` 作为 v2.x 特性

---

## ACP 下一步优先级建议

| 优先级 | 特性 | 理由 |
|--------|------|------|
| P1 | **Delivery ACK**（`message_delivered` 回执）| ANP `failed_msg_id` 和 A2A IS#1628 都在收敛到这个方向；ACP 先跑 |
| P2 | **AgentCard `payment_channel` 字段** | 顺应 x402 生态趋势，声明式，无需强依赖 |
| P3 | **Task Bidding 草案** | OIXA 模式有意思，但依赖 `QuerySkill` 成熟，可放 v3.x |

---

## 数据来源
- A2A commits: https://github.com/a2aproject/A2A/commits/main (via GitHub API)
- ANP commits: https://github.com/agent-network-protocol/AgentNetworkProtocol/commits/main (via GitHub API)
- 扫描日期: 2026-04-02
