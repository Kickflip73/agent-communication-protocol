# ACP 竞品周报 — 2026-05-06

_由贾维斯自动生成_

## A2A (Google) — 2026-05-06
- Stars: 23602 | Open Issues: 252
### 最新 Commits
- `ae6a562` 2026-04-23 docs: rename "Stream Message" to "Send Streaming Message" and replace 
- `434d1fe` 2026-04-23 docs: use `127.0.0.1` in tutorial as in the referenced sample (#1783)
- `c5104ce` 2026-04-23 docs: update Python helloworld tutorial for a2a-sdk v1.0 (#1775)
- `7ff1004` 2026-04-21 fix(spec): prefer application/a2a+json in HTTP binding (#1753)
- `757f0ec` 2026-04-14 fix(spec): recent transcoding-related error changes (#1627)
### 新 Issues（功能请求）
- #1811 [Feat]: Add TaskMessageUpdateEvent to notify observers when messages a
- #1794 [Feat]: Add generation/version number field to Task for event ordering
- #830 [Feat]: OAuth 2.1-compliant Authorization for A2A
- #563 [Feat]: Support multi-agent composition by registering HostAgent via c

## ANP (社区)
- `5f01846` 2026-04-22 add message protocol flow chart
- `cf38083` 2026-04-15 docs: sync WNS spec updates
- `fc7e158` 2026-04-10 update english protocol
- `6c5a67a` 2026-04-10 update DataIntegrityProof
- `20641cd` 2026-04-10 update origin_proof

## IBM ACP
- `e5265ca` 2025-08-25 docs: A2A announcement (#230)
- `e8299f8` 2025-08-21 chore: bump version
- `00afccd` 2025-08-21 fix(python): revert cachetools version bump to avoid conflicts

## 深度分析（贾维斯，2026-05-06）

### A2A 动态解读

**本周 A2A 整体处于文档巩固期，无协议级大变动，但社区需求侧有值得关注的信号：**

1. **Issue #1811 — TaskMessageUpdateEvent**  
   A2A 社区提议新增 `TaskMessageUpdateEvent`，用于在 Task 执行过程中通知观察者消息已更新（而非仅 status 变化）。这说明 A2A 的事件模型仍在演化中——消息级 SSE 推送粒度不足的问题社区已察觉。  
   **ACP 现状对比**：ACP 已有 `context_id` SSE 完整传播（v1.7），消息更新通过 `message_id` 序列可追踪。但 ACP 尚无专用的「消息内容变更事件」类型，是潜在跟进点。

2. **Issue #1794 — Task 事件排序版本号**  
   A2A 提议在 Task 对象中增加 `generation/version number` 用于 SSE 事件全局排序，解决多 SSE 客户端乱序问题。  
   **ACP 现状对比**：ACP v0.5 已有 `server_seq` 服务端有序序号机制（commit `bb6aba3`），此问题 ACP 已解决，**领先 A2A 约 3 个月**。

3. **Issue #830 — OAuth 2.1 授权**  
   老 Issue 仍未合入，A2A OAuth 2.1 流程至今仍是讨论稿。ACP 设计禁忌中明确拒绝 OAuth 2.0/PKCE，路线坚定，无需跟进。

4. **Commit fix(spec) #1753 — `application/a2a+json`**  
   A2A 将 HTTP 绑定中的内容类型改为专用 MIME `application/a2a+json`。ACP 当前使用标准 `application/json; charset=utf-8`（在 error-codes.md 中明确文档化，v1.7.x，commit `81ffd30`）。  
   **评估**：专用 MIME type 有利于网关路由，但增加接入复杂度，与 ACP「curl 可接入」定位相悖，暂不跟进。

### ANP 动态解读

**ANP 本周有实质性更新，出乎意料——此前 ROADMAP.md 标记为「已归档/停更」。**

- `5f01846` — 新增消息协议流程图（2026-04-22）
- `cf38083` — 同步 WNS 规范更新（2026-04-15）
- `fc7e158` / `6c5a67a` / `20641cd` — 更新英文协议、DataIntegrityProof、origin_proof（2026-04-10）

**解读**：ANP 在 4 月份再度活跃，重点围绕 **W3C 去中心化身份（DID/DataIntegrityProof）和 origin_proof 证明机制**。这与 ACP 的 `did:acp:` DID 体系（v1.3）方向高度重叠。  
**建议**：将 ANP 状态从「停更」重新标记为「低频活跃」，持续关注 WNS（Web Native Specification）方向，避免 ANP 在去中心化身份细分赛道悄悄完成差异化后被忽视。

### IBM ACP 动态解读

IBM ACP 最新 commit 停留在 2025-08-25，已停止活跃开发，仅做 A2A 公告引流。保持「参考即可」态度，无需追踪。

---

## 路线图对比 & 优先级建议

### 当前路线图状态（截至本周）
- 最后文档更新：v2.73.0 / v2.78.0（2026-04-07）
- v1.4 NAT 穿透：signaling 层完成，主流程自动降级集成（`_connect_with_nat_traversal()`）尚未完成
- v3.0 公开发布：等待真 P2P 完成

### 本周建议调整

| 优先级 | 行动 | 来源 |
|--------|------|------|
| 🔴 P0 | **完成 v1.4 NAT 穿透主流程集成**（`_connect_with_nat_traversal()` 替换现有直连）——这是通往 v3.0 发布的唯一阻塞项 | ROADMAP.md 待办 |
| 🟡 P1 | **跟进 A2A #1811 消息更新事件**：在 ACP 中定义 `MessageUpdateEvent` SSE 类型，补全事件模型粒度，可作为 v2.80+ 小版本快速落地 | A2A #1811 |
| 🟡 P1 | **重新追踪 ANP**：将 `ROADMAP.md` 中 ANP 状态从「停更」改为「低频活跃」，重点关注其 DataIntegrityProof / origin_proof 实现，防止在 DID 赛道被超越 | ANP 4 月复活 |
| 🟢 P2 | **差异化宣传 server_seq**：A2A #1794 证明事件排序是业界痛点，ACP 已有完整方案，应在 README vs-A2A 对比表中新增此行 | A2A #1794 |

---

## 本周行动建议（简版）

1. **集中火力完成 NAT 穿透自动降级集成**（P0）：编写 `_connect_with_nat_traversal()` 并替换 `/peers/connect` 现有直连逻辑，完成 v1.4 最后一个阻塞项，解锁 v3.0 发布窗口。

2. **更新 ROADMAP.md — 重激活 ANP 追踪 + 新增 MessageUpdateEvent 特性项**（P1）：ANP 已复活，需修正状态标记；同步将 A2A #1811 的 `MessageUpdateEvent` 列入 v2.80 backlog，保持事件模型领先。

