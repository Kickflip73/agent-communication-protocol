# ACP 竞品情报扫描报告 — 2026-03-20 晨间

> 扫描时间：2026-03-20 08:21 CST  
> 扫描范围：A2A (a2aproject/A2A), ANP (agent-network-protocol/AgentNetworkProtocol)

---

## A2A 动态

### 最新 commits（2026-03-16 以来）
- **7b900e77** (2026-03-16) — `Update CODEOWNERS (#1644)`: TSC is the reviewing body
  - 意义：A2A 治理进一步正式化，TSC 成为 PR reviewer。项目复杂度在增加，我们的快迭代窗口期延长。

### 活跃 Issue 精选

#### Issue #1628：`trust.signals[]` 扩展（2026-03-20 最新更新，6 条评论）
- **主题**：在 AgentCard 中加入 `trust.signals[]` 数组，包含 4 种信任信号：
  1. `onchain_credentials` — 链上凭证（EAS 认证、NFT 持有等）
  2. `onchain_activity` — 链上行为观测（6 维度）
  3. `vouch_chain` — 社交信任图谱（域范围评分）
  4. `behavioral` — 运行时性能（成功率、合规性）
- **核心模式**：所有 4 种信号使用统一的 ECDSA/JWKS 验证模型
- **ACP 相关性**：
  - 这是企业级场景的「信任建立」方案，引入了区块链依赖
  - ACP 定位（个人/团队，P2P）**不需要**这种复杂信任基础设施
  - 差异化优势：ACP 用 token（连接时生成）做轻量访问控制，足够个人场景
  - 警惕：若 A2A 的 trust 扩展成为事实标准，未来可能需要考虑轻量版 trust 字段

#### PR #418（老 PR，中心化 Agent Registrar）
- 仍未合并（2025-05-06 创建，2025-08-27 最后更新）
- A2A 对「中心注册表」方向犹豫 → 我们坚持「无中心注册」是正确的

### A2A 趋势总结（本周）
- 治理重心：TSC → 项目变重，不适合快速迭代
- 技术重心：信任机制、链上凭证 → 企业/Web3 场景
- 对 ACP 启示：我们的轻量差异化定位越来越清晰

---

## ANP 动态

- 最新 commit：2026-03-05（上次已记录），本周无新更新
- 无新 issue 或 PR

---

## 本轮 ACP 战略判断

### 近期 A2A 方向 vs ACP 定位

| A2A 新方向 | 我们的态度 |
|-----------|-----------|
| trust.signals（链上凭证） | ❌ 不做，引入区块链依赖，违背「零配置」 |
| TSC 治理正式化 | 无关，确认我们不需要委员会治理 |
| 中心 Agent Registrar（PR #418） | ❌ 不做，坚持无中心注册 |

### v0.6 行动项更新

基于本轮扫描，无需新增 v0.6 行动项。现有路线图方向清晰：
- ✅ multi-session（已完成，ad7e1c4）
- ✅ 最小接入协议规范（已完成，125422e）
- 🔲 错误码规范 + `failed_message_id`（ANP 参考，待实现）
- 🔲 传输层规范重组（spec/transports.md 明确区分 Protocol Binding vs Extension）
- 🔲 Python mini-SDK（pip install acp-relay）

---

## 参考链接

- A2A Issue #1628: https://github.com/a2aproject/A2A/issues/1628
- A2A PR #418: https://github.com/a2aproject/A2A/pull/418
- A2A commit 7b900e77: https://github.com/a2aproject/A2A/commit/7b900e77
