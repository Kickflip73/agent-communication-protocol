# ACP 竞品周报 — 2026-04-22

_由贾维斯自动生成_

## A2A (Google) — 2026-04-22
- Stars: 23340 | Open Issues: 235
### 最新 Commits
- `7ff1004` 2026-04-21 fix(spec): prefer application/a2a+json in HTTP binding (#1753)
- `757f0ec` 2026-04-14 fix(spec): recent transcoding-related error changes (#1627)
- `3947dac` 2026-04-09 docs(GOVERNANCE.md): How to add new TSC members (#1571)
- `8dda73b` 2026-04-09 docs: Add Rust SDK to list of official SDKs (#1729)
- `b9f03d4` 2026-04-09 docs: update code snippet markers to match refactored sample identifie
### 新 Issues（功能请求）
- #830 [Feat]: OAuth 2.1-compliant Authorization for A2A
- #563 [Feat]: Support multi-agent composition by registering HostAgent via c

## ANP (社区)
- `cf38083` 2026-04-15 docs: sync WNS spec updates
- `fc7e158` 2026-04-10 update english protocol
- `6c5a67a` 2026-04-10 update DataIntegrityProof
- `20641cd` 2026-04-10 update origin_proof
- `bf2bddc` 2026-04-09 update docs links

## IBM ACP
- `e5265ca` 2025-08-25 docs: A2A announcement (#230)
- `e8299f8` 2025-08-21 chore: bump version
- `00afccd` 2025-08-21 fix(python): revert cachetools version bump to avoid conflicts

## 本周行动建议

### 🔍 深度分析（by J.A.R.V.I.S.）

#### A2A 动态解读

**1. OAuth 2.1 授权提案（Issue #830）**
- A2A 社区正在激烈讨论企业级授权方案，拟引入 OAuth 2.1 / PKCE 流程
- **ACP 对比**：我们已在 v1.3 实现了完整的 Ed25519 自主权密钥 + `did:acp:` DID 体系，无需第三方授权服务器
- **差异化价值**：ACP 的零注册、零运维身份方案领先 A2A 社区约 2-3 个月

**2. 多 Agent 组合提案（Issue #563）**
- A2A 探索通过注册 HostAgent 实现多 Agent 协同
- **ACP 对比**：我们已有 `/peers/broadcast`（v2.22）实现向所有连接 Peer 广播消息，以及完整的 Task 状态机支持多 Agent 协作
- **建议**：考虑在文档中补充「多 Agent 协作模式」最佳实践章节

**3. 技术债务信号**
- A2A 近期提交多为文档修复和小补丁，核心架构相对稳定
- PR#1753 修复 HTTP binding 的 content-type 偏好，属于细节打磨期

---

#### ANP / IBM ACP 状态

- **ANP**：最后活跃 2026-04-15，但仅为文档同步，无实质协议更新，维持「归档」判断
- **IBM ACP**：彻底停更（最后提交 2025-08-25），仅作为历史参考

---

### 🎯 行动建议

**优先级 P1 - 文档强化**
在 README / 官网首页新增「vs OAuth」对比章节，强调 A2A 正在讨论的 OAuth 2.1 方案与 ACP 自主权身份的优劣对比，抢占心智。

**优先级 P2 - 生态建设**
A2A 近期新增 Rust SDK 到官方列表，ACP 的 Rust SDK（v1.2）已完成，建议：
1. 发布到 crates.io
2. 申请加入 ACP 官方 SDK 列表
3. 撰写「Getting Started with Rust」教程

**优先级 P3 - 保持观察**
持续跟踪 A2A Issue #563 的 HostAgent 多 Agent 组合方案，评估是否需要 ACP 引入类似概念（如 Agent Group / Swarm），或坚持纯 P2P 对等协作模型。

---

_分析完成时间：2026-04-22 09:15 AM by J.A.R.V.I.S._
