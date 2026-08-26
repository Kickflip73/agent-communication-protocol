# A2A 竞品情报扫描 — 2026-03-20 上午

> 扫描时间：10:51 CST | 扫描范围：A2A recent issues + ANP latest commits

---

## A2A 动态

### 最新 commit（无新功能性 commit）
- `7b900e77` (2026-03-16)：Update CODEOWNERS → TSC 正式接管审查
- `3c1a5ff4` (2026-03-16)：添加 WritBase 为合作伙伴
- 结论：A2A 主干代码本周无新特性 commit，进入维护/治理模式

### Issue #1575（新，2026-03-19 更新）：Agent 身份验证与委托执行

**标题**：Running implementation of agent identity, delegation, and enforcement

**核心痛点**（真实用户描述）：
> "我管理 3 个来自不同 creator 的 agent（Claude / GPT / 开源），它们协作开发。
> 当 PortalX2 让我的 GPT agent 往仓库 push 代码时，我无法验证这个请求是否在
> 授权范围内——这是我每天都会遇到的问题。"

**对 ACP 的启示**：
- 个人用户对"信任但不验证"感到不安
- 但 OAuth 2.0 全套太重 → ACP 机会：**token + HMAC 轻量签名**（规划 v0.7）
- 用户场景与 ACP 定位高度一致：个人管理多个协作 agent

### Issue #1628（2026-03-20 更新）：trust.signals[] 扩展规范

**核心内容**：
- 4 类信号：`onchain_credentials`、`onchain_activity`、`vouch_chain`、`behavioral`
- 统一 ECDSA/JWKS 验签模式

**对 ACP 的判断**：
- **不做**：区块链凭证 + 链上活动 = 企业/Web3 方向，个人场景不需要
- 观察价值：ECDSA/JWKS 验签模式可在 v0.7 AgentCard 签名中参考

---

## ANP 动态

- 最新 commit：`99806f45` (2026-03-05)，无 2026-03-20 新动态
- 上周要点已在之前报告中记录（failed_msg_id + server_seq）

---

## ACP 战略判断

### 本周核心洞察

**A2A 的用户需求 ≠ A2A 的实现复杂度**

Issue #1575 描述的场景是真实的个人用户痛点：
- 多 agent 协作时，如何知道指令来源是可信的？
- 这是 ACP 也会面临的问题

A2A 的回答是 OAuth + trust.signals[] + ECDSA（非常重）。
ACP 的机会是给出一个**轻量版身份保证**：
- 连接时 token = 一次性邀请，已有基础
- v0.7 候选：连接时交换 HMAC 公钥，消息签名可选

**A2A 治理变重 = 我们快迭代的时间窗口还在延长**
- TSC 接管后 PR 审查会更慢
- 本周 A2A 主干无新特性 commit，印证这一判断

---

## v0.7 新行动项

| 优先级 | 内容 | 来源 |
|--------|------|------|
| 🟡 中 | 轻量身份信号：token + 可选 HMAC 签名 | #1575 用户痛点 |
| 🟡 中 | AgentCard `trust` 字段预留（不强制填写） | #1628 参考 |

---

*下次扫描：2026-03-20 下午或 2026-03-21 上午*
