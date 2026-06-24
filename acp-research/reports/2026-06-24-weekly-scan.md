# ACP 竞品周报 — 2026-06-24

_由贾维斯自动生成_

## A2A (Google) — 2026-06-24
- Stars: 24422 | Open Issues: 260
### 最新 Commits
- `4374b82` 2026-06-22 docs: update a2a homepage banner (#1971)
- `dc8cc23` 2026-06-22 docs: update llms.txt to match v1.0 spec and site navigation (#1943)
- `28e27c9` 2026-06-22 ci: trigger docs build on changes to build inputs (#1967)
- `69dd57c` 2026-06-12 docs: restructure homepage information and add missing sections (#1874
- `2e0a4e5` 2026-06-05 docs: add A2A & generative UI hackathon banner (#1906)
### 新 Issues（功能请求）
- #1811 [Feat]: Add TaskMessageUpdateEvent to notify observers when messages a
- #1794 [Feat]: Add generation/version number field to Task for event ordering
- #830 [Feat]: OAuth 2.1-compliant Authorization for A2A
- #563 [Feat]: Support multi-agent composition by registering HostAgent via c

## ANP (社区)
- `15d41c9` 2026-06-10 update wns Protocol：add did profile
- `a0a7d2f` 2026-05-30 add json payload
- `b15ec29` 2026-05-13 Make the AP2 analysis available to English readers
- `aabc276` 2026-05-13 Make the IM protocol upgrade accessible to English readers
- `28c7dd4` 2026-05-13 add blogs

## IBM ACP
- `e5265ca` 2025-08-25 docs: A2A announcement (#230)
- `e8299f8` 2025-08-21 chore: bump version
- `00afccd` 2025-08-21 fix(python): revert cachetools version bump to avoid conflicts

## 深度分析

### A2A 动态研判

1. **TaskMessageUpdateEvent（#1811）**：A2A 社区提议为 Task 添加消息更新通知事件，本质上是对「任务状态变更推送」的增强。ACP 已有 SSE 流式事件（`/tasks/{id}/events`）+ context_id 传播（v1.7），功能覆盖更完整。但 A2A 的 `TaskMessageUpdateEvent` 更细粒度——单条消息级别的变更通知，ACP 当前仅推送 task 级别状态。**可借鉴方向**：在 ACP SSE 事件中增加 `message_updated` 事件类型，区分「新消息」和「已有消息被修改」。优先级 P2。

2. **Task generation/version 字段（#1794）**：提议为 Task 增加版本号以解决事件排序问题。ACP 当前使用 `server_seq` 有序序列号（v0.5+），已在消息幂等性层面解决排序。A2A 的 `generation` 字段更多用于「任务被重置/重启」场景的版本追踪，与 ACP 的 `server_seq` 解决的问题域不同。**暂不跟进**，但若出现「任务重试/重置」需求可参考。

3. **OAuth 2.1 授权（#830）**：A2A 持续推进企业级 OAuth 集成。这进一步验证了 ACP 的差异化定位——ACP 设计禁忌明确排除 OAuth，面向个人/小团队的轻量 P2P 场景不需要此复杂度。**无需调整**，继续强化 P2P 身份叙事（Ed25519 + DID）。

4. **多 Agent 组合注册（#563）**：HostAgent 注册子 Agent 的能力组合。ACP 的 `/peers/broadcast`（v2.22）+ `QuerySkill()`（v0.5）已覆盖类似场景，且 P2P 架构天然不需要中心注册表。**优势保持**。

5. **整体趋势**：A2A Stars 增长至 24,422（+1,779 vs 3月），文档和 CI 持续优化，但核心协议变化不大。过去 3 个月以文档重构和社区运营为主，协议层实质性推进放缓。

### ANP 动态研判

- **WNS Protocol + DID Profile（6月10日）**：ANP 在归档后仍有零星更新，主要是 WNS（Web Name Service）协议增加 DID profile 支持。这表明 ANP 的 DID 研究方向仍在持续，但已转为个人项目式维护，不具备生态影响力。
- **AP2 分析文档英文化**：将 IM 协议升级分析翻译为英文，属于知识沉淀，无协议变化。
- **结论**：ANP 仍处于归档/低活跃状态，不构成竞争威胁。其 DID 思路可作为 ACP `did:acp:` 的参考，但无需主动跟进。

### IBM ACP 动态研判

- 最后活跃 2025-08-25，已停更近 10 个月。
- 唯一值得关注的是最后一条 commit 提到了 A2A announcement，表明 IBM 内部可能已转向支持 A2A。
- **结论**：IBM ACP 已实质性退出竞争，不再追踪。

---

## 路线图影响评估

| 竞品动态 | 对 ACP 路线图的影响 | 建议动作 |
|---------|-------------------|----------|
| A2A #1811 TaskMessageUpdateEvent | SSE 事件粒度可增强 | P2：评估 `message_updated` 事件类型 |
| A2A #1794 Task generation/version | server_seq 已覆盖排序需求 | 暂不跟进 |
| A2A #830 OAuth 2.1 | 验证 ACP 差异化定位正确 | 继续强化 P2P 身份叙事 |
| A2A Stars 增长放缓 | 文档为主、协议推进慢 | 加速 v1.4 NAT 穿透完成，抢占发布窗口 |
| ANP WNS+DID | 低影响，归档状态 | 偶尔参考 DID 思路即可 |
| IBM ACP 停更 | 退出竞争 | 停止追踪 |

---

## 本周行动建议

### ✅ 建议 1：加速 v1.4 NAT 穿透最终集成

A2A 协议层推进放缓（过去 3 个月以文档为主），这是 ACP 抢占「真 P2P Agent 通信」心智的黄金窗口。v1.4 NAT 穿透的 signaling 和 HTTP 反射层已完成（v2.19），但自动降级集成和真实 NAT 环境测试仍缺失。**建议将 v1.4 完整集成提升为最高优先级，在 A2A 下一轮协议更新前完成公开发布准备。**

### ✅ 建议 2：评估 `message_updated` SSE 事件类型

A2A #1811 提出的 TaskMessageUpdateEvent 揭示了一个有价值的场景——单条消息级别的变更通知（区别于 Task 级别状态变更）。ACP 当前 SSE 只推送 task 状态变化，消息一旦发送就是不可变的。建议在 v2.23+ 路线图中新增 `message_updated` 事件类型，支持消息修改/撤回场景，与 A2A 形成功能对等甚至领先。

### ℹ️ 持续观察

- A2A 多 Agent 组合注册（#563）的社区讨论走向
- ANP WNS 协议的后续演进（概率极低）
