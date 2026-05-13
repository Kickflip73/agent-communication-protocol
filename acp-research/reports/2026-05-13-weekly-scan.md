# ACP 竞品周报 — 2026-05-13

_由贾维斯自动生成_

## A2A (Google) — 2026-05-13
- Stars: 23738 | Open Issues: 259
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

## 本周行动建议
_(需贾维斯人工分析后补充)_

---

## 📊 深度分析 — J.A.R.V.I.S.

### 一、竞品新动态（本周 Top 3）

#### 1️⃣ A2A #1811: TaskMessageUpdateEvent — 消息历史变更事件
**关键发现**：A2A 社区意识到任务历史（Task.history）变更缺乏事件通知机制，导致观察者模式存在盲区。

**技术细节**：
- 当客户端发送跟进消息（follow-up）但状态不变时，观察者完全收不到通知
- 提案新增 `TaskMessageUpdateEvent`，在每条消息追加到历史时触发
- 与状态更新事件（TaskStatusUpdateEvent）解耦，独立传输

**与 ACP 对比**：
- ✅ **ACP 优势**：已实现完整的 SSE 流式事件机制，所有消息变更天然携带在事件流中
- ✅ **ACP 领先**：ACP 的 `context_id` 多轮上下文已在 v1.7 完成（commit `b91f642`），无需额外事件类型

#### 2️⃣ A2A #1794: Task Generation/Version 字段 — 乐观并发控制
**关键发现**：A2A 考虑为 Task 添加版本号字段，用于事件排序、长轮询和乐观并发。

**技术细节**：
- 解决多客户端并发修改任务的竞态条件
- 支持长轮询（long-polling）的增量同步

**与 ACP 对比**：
- ✅ **ACP 已有**：`server_seq` 机制（v0.5 引入）已实现消息级序列号排序
- ⚠️ **待完善**：Task 级别的版本号 ACP 尚未显式暴露，可考虑在 `GET /tasks/{id}` 响应中添加 `version` 字段

#### 3️⃣ A2A #830: OAuth 2.1 授权 — 企业级认证路径
**关键发现**：A2A 持续推进 OAuth 2.1 授权方案，社区讨论已持续数月。

**技术细节**：
- 定位企业级多租户场景
- 引入授权服务器和令牌交换流程

**与 ACP 对比**：
- ✅ **ACP 差异化**：坚持 Ed25519 自主权密钥 + `did:acp:` DID 体系（v1.3 完成）
- ✅ **轻量优势**：无需授权服务器，单文件 Skill 即可运行
- 🎯 **战略判断**：ACP 与 A2A 在此分道扬镳，A2A 追求企业合规，ACP 追求个人/小团队开箱即用

---

### 二、ROADMAP 对照检查

| A2A 新特性 | ACP 现状 | 是否需要跟进 |
|-----------|---------|-------------|
| TaskMessageUpdateEvent | ✅ 已实现（SSE 流式事件） | 无需跟进，已有优势 |
| Task Generation/Version | ⚠️ 部分实现（server_seq） | 可考虑显式暴露 Task version |
| OAuth 2.1 授权 | ❌ 明确不做 | 保持差异化，继续完善 DID |

**ANP/IBM ACP 动态**：
- ANP 维持低频维护，4 月提交集中在文档和协议流程图
- IBM ACP 已实质性停更（最后提交 2025-08-25），参考意义有限

---

### 三、行动建议（2 条）

#### 🔧 建议 1：显式 Task Version 字段（P2，v2.24 候选）
在 `GET /tasks/{id}` 和 `GET /tasks` 列表响应中增加 `version: integer` 字段：
- 每次任务更新（状态、消息、工件）自动递增
- 支持客户端乐观并发：`If-Match: <version>` 头
- 与现有 `server_seq` 互补（seq 用于消息排序，version 用于任务级乐观锁）

**预期收益**：
- 对标 A2A #1794，展示 ACP 响应速度
- 为多设备同步场景提供基础设施

#### 📝 建议 2：发布技术博客《Why ACP Doesn't Need OAuth》
基于 A2A #830 的持续讨论，撰写一篇立场文章：
- 阐述 Ed25519 + DID 的设计哲学
- 对比 OAuth 2.1 的复杂度（授权服务器、令牌刷新、PKCE）
- 强调 ACP 的 "零注册、零运维" 定位

**发布时机**：
- 可与 v2.24 版本发布配合
- 投稿目标：Hacker News、Reddit r/selfhosted、个人博客

---

### 四、长期趋势判断

1. **A2A 企业化加速**：从功能请求分布看，A2A 社区正在向企业级特性倾斜（OAuth、多租户、审计日志），这可能为 ACP 留下个人/小团队市场的真空地带。

2. **协议碎片化风险**：如果 A2A 最终绑定 OAuth，与轻量 P2P 场景的天然不匹配可能催生 ACP 这类替代方案的需求。

3. **身份体系竞争**：Ed25519/DID vs OAuth/JWKS 可能成为 Agent 协议的核心分歧点。ACP 需要持续打磨 DID 开发者体验，保持领先优势。

---

_分析完成时间：2026-05-13 09:15 (Asia/Shanghai)_  
_分析者：J.A.R.V.I.S._
