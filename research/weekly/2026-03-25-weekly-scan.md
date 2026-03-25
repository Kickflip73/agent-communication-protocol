# ACP 竞品周报 — 2026-03-25

_由贾维斯自动生成_

## A2A (Google) — 2026-03-25
- Stars: 22790 | Open Issues: 219
### 最新 Commits
- `7b900e7` 2026-03-16 Update CODEOWNERS (#1644)
- `3c1a5ff` 2026-03-16 docs: add WritBase to partners list (#1634)
- `7df7685` 2026-03-12 Update main.html
- `b750332` 2026-03-12 Update main.html
- `625146e` 2026-03-12 Update main.html (#1623)
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

## 本周行动建议
_(需贾维斯人工分析后补充)_

---

## 🔍 贾维斯深度分析（2026-03-25）

### 竞品动态解读

**A2A（Google）——活跃度极高，持续企业化**

本周 A2A 最值得关注的是 Issue #563：`[Feat]: Support multi-agent composition by registering HostAgent via c...`。这意味着 A2A 社区正在推动 **HostAgent 注册式多 Agent 编排**，即支持一个 Agent 作为"宿主"动态注册并组合其他子 Agent。这是典型的中心化总线路线——与 ACP 去中心化 P2P 定位形成鲜明分野。Stars 已达 22,790，生态吸附力持续增强，但复杂度也在持续上升（219 open issues）。

上月 v1.0.0 正式发布（2026-03-12）带来的 `tasks/list` 已在 ACP ROADMAP 中列为 v1.1 Backlog，进展方向正确。本周 A2A 动作偏向运营（CODEOWNERS 更新、partners 合作伙伴增加），无突破性协议变更，ACP 可继续保持差异化。

**ANP——事实停更，最后挣扎**

本周扫描确认 ANP 最后一次有效 commit 仍停留在 2026-03-05（`failed_msg_id` + 幂等性），与上周一致。ACP 在 2026-03-21 已从 ANP 借鉴了 `failed_message_id` 机制并完成实现（commit `e281790`），该灵感已被充分吸收。ANP 已可从主动追踪降为"存档参考"，不再占用研究带宽。

**IBM ACP——完全停滞**

最新 commit 停留在 2025-08-25，距今已超 7 个月无任何活动。IBM ACP 在本轮周报中可正式标记为"停止追踪"，仅作历史协议参考保留。

---

### 路线图对比与优先级建议

**当前状态**：v1.4 NAT 穿透专项版本进行中，signaling 层已完成（22/22 tests pass），剩余核心任务为 `DCUtRPuncher` 集成 HTTP 反射降级 + 端到端打洞测试。

**对比本周竞品动态，两点判断：**

1. **v1.4 优先级维持 P0，无需调整。** A2A 的 HostAgent 注册方向走的是中心化路线，ACP 的真 P2P 差异化战略仍是正确的核心赌注。v1.4 真正实现"无中间人"后，发布时的对比叙事将非常清晰。

2. **`GET /tasks` 列表查询（当前 v1.1 Backlog）建议提升为 v1.4 并行 P1。** A2A 的 tasks/list 功能已发布，且这是一个独立改动（不影响 NAT 穿透主线），实现成本低（参数化过滤 + 分页），可在 v1.4 开发周期内作为"小目标"并行完成，增强与 A2A 的功能对等性。

---

## 🎯 本周行动建议

1. **立即**：推进 `DCUtRPuncher` HTTP 反射降级集成——这是 v1.4 P0 剩余最大 gap，完成后即可开展 NAT 环境集成测试。
2. **本周内**：将 `GET /tasks` 列表查询从 v1.1 Backlog 升为 v1.4 并行实现——低成本、高价值，可趁 v1.4 开发窗口一并完成。
