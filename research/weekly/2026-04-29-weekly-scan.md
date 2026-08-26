# ACP 竞品周报 — 2026-04-29

_由贾维斯自动生成_

## A2A (Google) — 2026-04-29
- Stars: 23486 | Open Issues: 243
### 最新 Commits
- `ae6a562` 2026-04-23 docs: rename "Stream Message" to "Send Streaming Message" and replace 
- `434d1fe` 2026-04-23 docs: use `127.0.0.1` in tutorial as in the referenced sample (#1783)
- `c5104ce` 2026-04-23 docs: update Python helloworld tutorial for a2a-sdk v1.0 (#1775)
- `7ff1004` 2026-04-21 fix(spec): prefer application/a2a+json in HTTP binding (#1753)
- `757f0ec` 2026-04-14 fix(spec): recent transcoding-related error changes (#1627)
### 新 Issues（功能请求）
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

## 本周行动建议
_(需贾维斯人工分析后补充)_

---

## 📊 深度分析 — 贾维斯研判（2026-04-29）

### 一、竞品新动态

#### 1. A2A（Google）— Stars 破 23,486，持续高速迭代

**本周核心变化：**

- **Issue #1794：Task `generation` 字段（乐观并发 + 事件定序）**  
  这是本周 A2A 最重要的提案。核心问题：SSE 事件流没有序列号，客户端无法检测丢失事件，也无法实现乐观并发写入（lost-update 竞态）。提案借鉴 Kubernetes `resourceVersion` / GCS `generation` / HTTP ETag 模式，为 Task 对象增加单调递增 `generation` 字段，同时支持长轮询（`GetTask(current_generation=N)`，服务端 hold 直到 generation > N）。  
  > **ACP 影响评估**：ACP 已有 `server_seq` 有序序列号（v0.5 消息幂等性），但**任务级 generation** 概念尚未实现。这是 A2A 的 P0 需求，短期内将成标准，值得跟进。

- **docs 重构：Python helloworld 教程升级 a2a-sdk v1.0，端点命名规范化**  
  A2A 正大力投入开发者体验（DX），SDK 配套文档趋于成熟，已对社区形成明显拉力。

- **Issue #563：HostAgent 多 Agent 编排注册**  
  多 Agent 组合（Composition）的讨论持续活跃，HostAgent 作为协调者注册机制是 A2A 企业场景的核心差异点。ACP 定位 P2P 不涉及中央协调，暂无竞争压力，持续观察。

#### 2. ANP（社区）— 意外复活，关注 WNS 更新

ANP 上周（2026-04-22）新增了"消息协议流程图"commit，4 月份共有 4 次提交，包括 DataIntegrityProof 更新和 WNS（Web Node Spec）同步。这与 ROADMAP 中"2026-03-05 最后活跃，停更"的判断有出入——**ANP 未完全停更，处于低活跃维护状态**。核心关注点是 `DataIntegrityProof` 字段，与 ACP 的 `trust.signals` 信任体系有一定重叠。

#### 3. IBM ACP — 确认停更

最新 commit 仍为 2025-08-25，无变化。可从 ROADMAP 竞品跟踪表中降为"归档"状态，腾出监控资源。

---

### 二、ROADMAP 对比与优先级研判

**当前 ROADMAP 版本：v2.78.0（2026-04-07），距今约 3 周无更新。**

| 维度 | 现状 | 建议 |
|------|------|------|
| **Task generation 字段** | ACP 有 `server_seq` 但无 Task 级 generation | ➕ 升为 P1，加入 v2.8x 计划 |
| **A2A SDK DX 竞争** | ACP SDK 已有 Python/Node/Go/Rust，但文档偏弱 | 📝 补充 tutorial 级文档 |
| **ANP 复活监控** | ROADMAP 标注"停更，不再追踪" | ⚠️ 调整为"低活跃，季度扫描" |
| **v1.4 NAT 穿透** | 打洞集成测试（真实 NAT 环境）仍未完成 | 🔥 继续 P0，是 v3.0 发布前提 |
| **data_handling_policy** | 已识别 P3，来源 A2A IS#1606 | 维持 P3，暂无变化 |

---

### 三、行动建议

**建议 1：实现 Task `generation` 字段（目标 v2.80）**

A2A Issue #1794 的 generation 方案设计完善（乐观并发 + 长轮询 + 事件定序三合一），很可能进入 A2A 正式规范。ACP 应优先跟进：
- 在 Task 对象增加 `generation: int`（创建为 0，每次状态变更 +1）
- 在 SSE 事件（StatusUpdateEvent / ArtifactUpdateEvent）中携带 generation
- `GET /tasks/{id}?wait_generation=N` 支持长轮询语义
- 同步更新 `spec/core` 规范和测试套件
- **差异化点**：可比 A2A 先落地，延续"ACP 比 A2A 社区快 2-3 个月"的节奏优势

**建议 2：将 ANP 监控从"已归档"调整为"季度低频扫描"**

ANP 本月有实质性更新（DataIntegrityProof、WNS），完全停跟可能错过去中心化身份方向的信号。建议每季度（而非每周）抓取一次 ANP commits，重点关注 `DataIntegrityProof` 字段是否与 ACP `trust.signals` 存在互操作机会。同时，可将 ROADMAP 竞品表中 ANP 状态从 "🔴 已归档" 更新为 "🟡 低活跃维护"。

---

_分析完成时间：2026-04-29 09:06 CST_
