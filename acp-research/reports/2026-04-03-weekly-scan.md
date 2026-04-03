# ACP 竞品周报 — 2026-04-03

_由贾维斯自动生成_

## A2A (Google) — 2026-04-03
- Stars: 22979 | Open Issues: 222
### 最新 Commits
- `c1169f4` 2026-03-31 fix: update OSPO action references to canonical org path (#1705)
- `f991a08` 2026-03-31 docs: add Community SDKs (#1698)
- `5ac9d2c` 2026-03-30 docs: add Strale to partners list (#1702)
- `72d1459` 2026-03-27 Add OIXA Protocol to partners list (#1692)
- `32a7d3a` 2026-03-26 docs: update python tutorial for a2a-sdk v1.0.0-alpha.0 (#1678)
### 新 Issues（功能请求）
- #563 [Feat]: Support multi-agent composition by registering HostAgent via c

## ANP (社区)
- `99806f4` 2026-03-05 feat: add failed_msg_id field to e2ee_error protocol message
- `761087d` 2026-03-05 add handle feature
- `1f0abd2` 2026-03-03 feat: add client_msg_id idempotency and server_seq ordering to E2EE IM
- `b1c1c76` 2026-03-01 update e2ee protocol
- `eb4a10f` 2026-02-27 docs: rename signature field `service` to `aud` in DID-WBA spec

## IBM ACP
- `e5265ca` 2025-08-25 docs: A2A announcement (#230)
- `e8299f8` 2025-08-21 chore: bump version
- `00afccd` 2025-08-21 fix(python): revert cachetools version bump to avoid conflicts

## 深度分析（J.A.R.V.I.S. 2026-04-03）

### A2A（Google）— 本周动态解读

**SDK v1.0.0-alpha.0 正式发布**（commit `32a7d3a`，2026-03-26）：A2A Python SDK 到达首个 alpha 里程碑，说明 Google 正在将 A2A 从纯规范推向落地工具链。ACP 的 Python/Node/Go/Rust SDK 均已稳定，**工具链完备度领先**，但需关注 A2A SDK 的快速追赶。

**社区 SDK 文档化**（commit `f991a08`）：A2A 开始系统整理社区第三方 SDK，生态扩展加速。对 ACP 而言，这是一个信号——**协议生态化竞争**即将进入正面战场，ACP 的 Show HN 发布时间窗口宝贵。

**多 Agent 组合 Issue #563**：社区提议通过 HostAgent 注册支持 multi-agent composition，说明 A2A 正在向更复杂的编排场景演进。ACP 当前路线图偏 P2P 轻量，**无需跟进此方向**（违反设计原则），但可在文档差异化中明确阐明 ACP 是"通信协议"而非"编排框架"。

**OIXA / Strale 合作方加入**：A2A 合作伙伴生态扩展，影响力继续扩大。ACP 处于早期，专注技术差异化而非生态覆盖，属正常阶段差距。

---

### ANP（社区）— 现状评估

最新 commit 仍停在 2026-03-05，且内容为 E2EE IM 增强——与 ROADMAP.md 中"停更，已归档"判断一致。**本周无新动态，维持现有判断，不再重点追踪。**

ANP 的 E2EE 消息方向与 ACP 的轻量 P2P 通信定位存在分歧，借鉴价值有限。

---

### IBM ACP — 现状评估

最新 commit 为 2025-08-25，内容为关于 A2A 发布的公告——该项目实质上已停止独立发展，并将注意力转向 A2A 生态。**IBM ACP 本周无实质更新，参考价值继续下降。**

---

### 路线图对比与优先级判断

**当前版本**：v2.22.0（`/peers/broadcast` 已完成），v2.23 候选特性已规划。

对比 A2A 本周动态，以下路线图优先级建议：

| 优先级 | 特性 | 建议 | 理由 |
|--------|------|------|------|
| 🔥 P0 | Show HN 发布 | **立即启动** | A2A SDK alpha 发布后，窗口期正在收窄；ACP 技术优势需趁早建立先发认知 |
| ✅ P1 | `/peers/broadcast/history` | 继续按计划 | 功能闭环，不受竞品影响 |
| ✅ P1 | 子集广播 `target_peers[]` | 继续按计划 | 差异化能力 |
| ⚠️ 新增 | ACP vs A2A 差异化文档强化 | **建议本周完成** | A2A SDK alpha 发布会带来大量新关注者比较两个协议 |
| 📋 P2 | data_handling_policy（GDPR） | 低优先级维持 | A2A 企业场景，ACP 个人定位无需优先 |

**无需调整的部分**：
- NAT 穿透（v1.4 主流程剩余工作）维持 P0 不变，这是 ACP 核心差异化
- v3.0 公开发布继续等待 NAT 穿透完成
- 多 Agent 编排方向继续回避（A2A 赛道，ACP 无意跟进）

---

## 本周行动建议

### 建议 1 — 启动 Show HN 发布准备（优先级提升至本周）

**背景**：A2A Python SDK v1.0.0-alpha.0 发布后，开发者社区对 Agent 通信协议的关注度正在快速提升。`docs/show-hn-draft.md` 草稿已完成，当前时机是 ACP 建立先发认知的最佳窗口。

**具体行动**：
1. 最终审阅 `docs/show-hn-draft.md`，确认 v2.22 特性均已覆盖
2. 更新 README 的版本徽章和特性节至 v2.22（`/peers/broadcast`）
3. 确定发布日期（建议本周五或下周一，工作日早上 US-PT 时间）
4. 准备 HN 标题：建议突出 "Ed25519 DID + NAT traversal + zero-dependency"

### 建议 2 — 补全 ACP vs A2A 文档差异化（对应 A2A SDK alpha 发布）

**背景**：A2A SDK alpha 发布意味着更多开发者将会主动比较 ACP 和 A2A。当前 README vs-A2A 对比表有 12 行，覆盖安全和规范差异，但缺少**工具链和部署复杂度**对比。

**具体行动**：
1. 在 README vs-A2A 对比表中新增行：
   - "SDK 稳定性"：ACP 四语言 SDK 均已 GA vs A2A Python alpha
   - "部署方式"：ACP `pip install acp-relay` 单命令 vs A2A 需配置 Agent 服务
2. 考虑在 `docs/` 下新增 `acp-vs-a2a.md` 独立对比文档，供有深度需求的开发者参考
3. 结合 A2A Issue #563（multi-agent composition）明确阐明定位差异：ACP 是通信协议，不是编排框架
