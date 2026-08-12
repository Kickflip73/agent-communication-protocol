# ACP 竞品周报 — 2026-08-12

_由贾维斯自动生成_

## A2A (Google) — 2026-08-12
- Stars: 25301 | Open Issues: 227
### 最新 Commits
- `84ba07f` 2026-08-11 docs(spec): fix missing contextId in streaming example (#2083)
- `7608bd0` 2026-08-11 docs(spec): fix grammar error in Metadata section (#2092)
- `e096c85` 2026-08-11 docs: add Noorle to A2A community Integrations (#1930)
- `4f82944` 2026-08-10 docs: show per-language SDK repo links in the site header (#2112)
- `19598c4` 2026-08-06 docs: add Dealer Handshake to partners list (#2116)
### 新 Issues（功能请求）
- #1995 [Epic] Bidirectional streaming & improved stream semantics
- #1992 [Epic] Multi-turn interaction gaps — state acceptance rules, interrupt
- #1991 [Epic] Coherent Task History — gaps in semantics, querying, and observ
- #1990 [Epic] Auth scheme declaration & credential discovery in AgentCard
- #1989 [Epic] Client-directed skill selection

## ANP (社区)
- `9789640` 2026-08-04 docs: revise messaging profile version strategy
- `593a374` 2026-08-03 fix: preserve avatars when contributor stats are pending (#92)
- `5e53512` 2026-08-03 fix: update contributor avatar automation (#91)
- `149ad00` 2026-08-03 docs: explain Agent Description extended fields (#89)
- `38926dc` 2026-08-02 add English Agentic Web ten-talks translations

## IBM ACP
- `e5265ca` 2025-08-25 docs: A2A announcement (#230)
- `e8299f8` 2025-08-21 chore: bump version
- `00afccd` 2025-08-21 fix(python): revert cachetools version bump to avoid conflicts


---

## 贾维斯深度分析 — 竞品对比与行动建议

> 基于当前报告 + ROADMAP 路线图综合研判，生成时间：2026-08-12 09:08 CST

### 一、竞品动态评估（3 条核心变化）

#### 1. A2A 五大 Epic 级方向锁定，认证短板加速补齐 ⚠️
A2A 本周集中抛出 5 个 Epic Issue（#1991–#1995），核心信号：
- **认证方案声明**（#1990）：A2A 正在追赶 ACP 领先的 Ed25519+DID 身份体系。若 Google 选择嵌入 OAuth 2.0 / PKCE 路径，会与 ACP 的轻量无中间人设计产生分叉；若选择声明式信任信号模型，则与 ACP 的 `trust.signals[]` 路线趋同，需警惕兼容战。
- **客户端主导技能选择**（#1989）：与 ACP `POST /skills/query` 直接对位，但 A2A 可能走更重的"技能市场"路线（企业级目录 + 权限管理）。ACP 的轻量 `query→match→invoke` 三元组在简单场景仍有优势。
- **双向流式传输**（#1995）：A2A 从 SSE 半双工向全双工升级，对 ACP 当前的 SSE 单向流构成潜在压力。评估：ACP 的 `context_id` 多轮上下文 + 离线队列机制可覆盖大部分场景，但真·全双工在语音/实时协作场景有不可替代性。长期需考虑 WebTransport 或双向 WebSocket 扩展。

Stars 增量：22,643 → 25,301（+2,658，约 5 周），月增速 ~11%，生态引力持续扩大。

#### 2. ANP 实质归档，IBM ACP 彻底停更 🔴
- ANP 最后活跃 2026-08-04（修订 messaging profile），此前 3 月已停更，无需再投入追踪资源。
- IBM ACP 最后提交 2025-08-25，距现在已接近 **1 年**无更新。多模态消息赛道可被 ACP Extension 机制（`urn:acp:ext:multimodal/v1`）渐进覆盖，无需专门跟进。

**结论**：三方竞品格局已收敛为 **A2A vs ACP** 双轨竞争。ANP/IBM 退出，减少噪音，利好聚焦。

#### 3. A2A 多轮交互语义进入深水区，ACP 有领先窗口 🏆
- Issue #1992（Multi-turn interaction gaps）触及"中断规则、状态接受、任务恢复"等复杂语义。这与 ACP v1.5.2 已落地的 §10 Cancel 语义 + 5 状态机（submitted/working/completed/failed/input_required）直接对标。
- **关键优势**：ACP 在 2026-03-25 已解决 Cancel 语义（commit `0d19a11`），比 A2A 社区 #1680 的讨论快约 2 个月。当前 A2A 仍在"Epic 讨论"阶段，ACP 可趁窗口期将 §10 语义固化为行业参考实现，提升规范影响力。

### 二、与 ROADMAP 对照：优先级调整建议

| 路线图条目 | 原计划 | 建议调整 | 依据 |
|-----------|--------|---------|------|
| **v1.4 NAT 穿透**（P0） | 持续推进 | **保持最高优先级** | P2P 是 ACP 核心差异化，A2A 无此路线。当前 `/peers/connect` 已集成 `connection_type` 字段（v2.19），但自动降级集成和真实 NAT 环境测试仍 open。建议 8 月内完成 `tests/integration/test_p2p_behind_nat.py` 并通过。 |
| **双向流式传输** | 未列入 | **新增远期跟踪项（P2）** | A2A #1995 表明全双工是下一代 Agent 通信标配。ACP 的 SSE 覆盖 80% 场景，但语音/实时场景需要 WebTransport 或 WebSocket 扩展。不急于实现，但需在 `spec/backlog.md` 预留接口设计。 |
| **身份认证** | v1.3 DID 已完成 | **升级为"推荐级"特性** | A2A #1990 正在追赶认证，ACP 的 `did:acp:` + Ed25519 自签名 + AgentCard 握手验证是护城河。建议从"可选 `--identity`" 转向 README 首页核心卖点，增加用例文档。 |
| **GET /tasks** 列表查询 | v2.2 已完成 | 无需调整 | A2A 的 `tasks/list` 已对标，ACP 已提前实现（v2.2），保持即可。 |
| **data_handling_policy** | v2.23 候选 P3 | **降级或延后** | 企业 GDPR 场景非 ACP 主攻方向，A2A 的 IS#1606 进展缓慢。可等 A2A 方案收敛后再评估，避免分散资源。 |
| **v3.0 公开发布** | 等真 P2P 完成 | **保持延后策略** | 正确。A2A 当前热度在文档/规范层，而非发布冲击。等 NAT 穿透完成后，ACP 以"唯一真 P2P Agent 协议"定位推出，声量最大。 |

### 三、本周行动建议（2 条）

#### 建议 1：巩固身份认证护城河，发布 `did:acp:` 最佳实践文档（本周内）
- A2A 在 #1990 追认证，窗口期约 2–3 个月。ACP 需将技术领先转化为**叙事领先**。
- 具体动作：
  - 在 `docs/` 下新增 `identity-guide.md`：从零生成 Ed25519 密钥 → 发布 `did:acp:` → AgentCard 自签名 → 跨 Agent 握手验证的完整教程。
  - 在 README 首页增加"Identity-First"卖点段落，引用 vs-A2A 对比表（当前 12 行，可扩展）。
- 预期效果：抢占"Agent 身份认证标准"心智，延缓 A2A 追赶速度。

#### 建议 2：启动 NAT 穿透集成测试收尾，目标 8 月底前关闭 v1.4 里程碑
- v1.4 是 ACP 唯一真 P2P 的核心承诺，也是 v3.0 发布的前提。当前信号层（`tests/test_nat_signaling.py` 22 PASS）和 HTTP 反射降级（`tests/test_nat_http_reflect.py` 12 PASS）已完成，但**自动降级集成**和**真实 NAT 环境集成测试**仍 open。
- 具体动作：
  - 完成 `_connect_with_nat_traversal()` 替换现有直连逻辑。
  - 在 CI（GitHub Actions）中引入 NAT 模拟环境（如 `nstx` 或 Docker 双容器模拟对称 NAT），跑通 `tests/integration/test_p2p_behind_nat.py`。
  - 更新 `spec/nat-traversal-v1.4.md`，标记 Level 1/2/3 策略为 `[stable]`。
- 预期效果：v1.4 完成后，ACP 可宣称"全球首个真 NAT 穿透 Agent 通信协议"，与 A2A 的 Relay/Hub 架构形成不可复制的差异化。

### 四、风险监控

- **A2A 认证方案路线**：若 A2A #1990 选择声明式信任信号（类似 ACP `trust.signals[]`），可能引发社区兼容压力；若选择 OAuth 2.0，则与 ACP 轻量路线分叉，无直接竞争。建议每周扫描该 Issue 评论，持续跟踪。
- **A2A 双向流式传输**：若 A2A 在 2026-Q4 前推出测试实现，ACP 需将 WebTransport 扩展从 P2 提升至 P1。目前看 Epic 阶段至少持续 2–3 个月，不紧迫。
- **Stars 增速**：A2A 月增速 11%，若持续加速，可能在 2026 年底突破 30k。ACP 当前无公开 Stars（私有阶段），但 v3.0 发布时需准备好与 A2A 的规模对比叙事——建议以"技术深度"（真 P2P / DID 身份 / 零依赖 SDK）对冲"生态规模"。

---
_本分析由 J.A.R.V.I.S. 自动完成，如有需要进一步深挖某个竞品方向，请指示，Stark 先生。_
