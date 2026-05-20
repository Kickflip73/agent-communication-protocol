# ACP 竞品周报 — 2026-05-20

_由贾维斯自动生成_

## A2A (Google) — 2026-05-20
- Stars: 23863 | Open Issues: 258
### 最新 Commits
- `e997516` 2026-05-19 fix: TaskStatus values in the specification (#1801)
- `26818eb` 2026-05-19 docs: remove deprecated stateTransitionHistory references (#1834)
- `ae6a562` 2026-04-23 docs: rename "Stream Message" to "Send Streaming Message" and replace 
- `434d1fe` 2026-04-23 docs: use `127.0.0.1` in tutorial as in the referenced sample (#1783)
- `c5104ce` 2026-04-23 docs: update Python helloworld tutorial for a2a-sdk v1.0 (#1775)
### 新 Issues（功能请求）
- #1811 [Feat]: Add TaskMessageUpdateEvent to notify observers when messages a
- #1794 [Feat]: Add generation/version number field to Task for event ordering
- #830 [Feat]: OAuth 2.1-compliant Authorization for A2A
- #563 [Feat]: Support multi-agent composition by registering HostAgent via c

## ANP (社区)
- `b15ec29` 2026-05-13 Make the AP2 analysis available to English readers
- `aabc276` 2026-05-13 Make the IM protocol upgrade accessible to English readers
- `28c7dd4` 2026-05-13 add blogs
- `5f01846` 2026-04-22 add message protocol flow chart
- `cf38083` 2026-04-15 docs: sync WNS spec updates

## IBM ACP
- `e5265ca` 2025-08-25 docs: A2A announcement (#230)
- `e8299f8` 2025-08-21 chore: bump version
- `00afccd` 2025-08-21 fix(python): revert cachetools version bump to avoid conflicts

## 贾维斯深度分析 — 2026-05-20

---

### A2A 动态分析

**本周核心变动：规范修正 + 架构讨论升温**

1. **TaskStatus 规范修正（#1801 + #1834）**
   - `fix: TaskStatus values` 说明 A2A 在 Task 状态机语义上仍在收敛，`stateTransitionHistory` 字段已被废弃移除
   - ACP 当前采用 5 状态模型（submitted/working/completed/failed/input_required），无冗余历史追踪字段，**架构更简洁**
   - ACP 无需调整：我们的 Cancel 语义（spec §10）和 5 状态模型已经领先 A2A 的稳定性

2. **Issue #1811：TaskMessageUpdateEvent（事件通知机制缺口）**
   - A2A 社区请求新增「当 task 消息被更新时通知观察者」的事件
   - ACP 通过 SSE `context_id` 完整传播（v1.7 已实现）已覆盖此场景，**差异化优势可记录**

3. **Issue #1794：Task 版本号/generation 字段（事件排序）**
   - 解决多观察者并发订阅时的事件排序问题
   - ACP 已有 `server_seq` 服务端有序序号（v0.5 实现），功能等价，**无需跟进**

4. **Issue #830：OAuth 2.1 授权（长期悬案）**
   - 该 Issue 已挂起多时，A2A 仍在推进企业级 OAuth 集成
   - ACP 红线：❌ OAuth 2.0/PKCE，与我们的轻量定位一致，**继续保持**

5. **Stars 趋势**：23,863（ROADMAP 记录 3 月 19 日为 22,643），**7 周净增 1,220 星（+5.4%）**，增速有所放缓（此前周均约 200+）

---

### ANP 动态分析

**意外复活：英文化推广，但无实质技术演进**

- 最新 3 条 commit（2026-05-13）全部为文档翻译：将 AP2 分析和 IM 协议升级方案翻译成英文
- 之前 ROADMAP 将 ANP 标记为"已归档/停更"，现在有小规模文档活动，**但无代码/协议更新**
- 结论：ANP 团队在做国际化推广，技术实质未变，不改变我们的竞品评估

---

### IBM ACP 动态分析

**持续停滞，最新 commit 仍为 2025-08-25**

- 无任何新活动，确认为技术死亡状态
- 不影响 ACP 路线图

---

### 路线图对照分析

| 路线图项目 | 当前状态 | 竞品触发 | 建议 |
|-----------|---------|---------|------|
| v1.4 NAT 穿透（P2P 核心） | 部分完成（signaling 层 ✅，打洞集成未完成） | A2A 无相关动作 | **P0 优先推进** |
| TaskMessageUpdateEvent | ACP SSE 已覆盖（v1.7） | A2A #1811 同类需求 | 可写 vs-A2A 差异化文档 |
| Task generation/version | ACP server_seq 等价 | A2A #1794 同类需求 | 无需跟进 |
| `GET /tasks` 分页 | ✅ 已完成（v2.2） | A2A 已有 tasks/list | ACP 已达标，可做文档 |
| data_handling_policy | P3 低优先级 | A2A IS#1606 仍挂起 | 维持 P3 |

---

## 本周行动建议

> 由贾维斯根据竞品分析自动生成 — 2026-05-20 09:05 CST

**建议 1（P0）：完成 v1.4 NAT 穿透主流程集成**
- A2A 本周无 NAT/P2P 相关动作，我们的窗口期依然存在
- 当前卡点：`_connect_with_nat_traversal()` 替换现有直连逻辑（ROADMAP 标记未完成）
- 建议本周推进此项，完成后 v3.0 公开发布的核心前置条件即告满足
- 成功指标：双 NAT 直连率 ≥70%，`tests/integration/test_p2p_behind_nat.py` 通过

**建议 2（P1）：将 TaskMessageUpdateEvent vs-A2A 差异化写入 README**
- A2A #1811 显示社区仍在讨论如何通知观察者消息更新
- ACP 的 SSE + context_id 完整传播方案（v1.7）已完全解决此问题
- 操作：在 README vs-A2A 对比表新增一行，引用 A2A #1811，清晰展示 ACP 领先
- 预计工作量：15 分钟，但营销/社区价值高

---

_分析截止：2026-05-20 09:05 CST | 下次扫描：2026-05-27_
