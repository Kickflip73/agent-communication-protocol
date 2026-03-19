# ACP 竞品情报 — 2026-03-19（研究轮 #3）

**扫描时间：** 2026-03-19 13:28 CST  
**覆盖：** A2A PR #1655、ANP 最新 commit

---

## 1. A2A PR #1655 — QuerySkill() 深度解析

**状态：** Open（2026-03-18 更新）  
**链接：** https://github.com/a2aproject/A2A/pull/1655

### 核心设计（三层）

| 层 | 内容 |
|----|------|
| **Proto** | `SkillQueryRequest` + `SkillQueryResult` + `SkillSupportLevel` 枚举（SUPPORTED/PARTIAL/UNSUPPORTED） |
| **协议绑定** | JSON-RPC = `skills/query`；gRPC = `QuerySkill`；HTTP = `POST /skills/{skill_id}/query` |
| **缓存语义** | `cache_ttl_seconds` 字段；`stale-if-error`：临时失败时可使用 2×TTL 的缓存结果 |

### ADR-002 关键洞察

**问题**：AgentCard 是静态文档，无法表达运行时约束（如"现在能处理 500MB 音频吗"）

**设计决策**：
- QuerySkill = **能力声明**，不是任务执行
- `PARTIAL` 状态 + `constraints` map：Agent 可以表达"能做80%，请求客户端分块"
- 必须在 AgentCard 里 `capabilities.skill_query: true` 才能启用（向后兼容）
- 被拒绝的方案：GetExtendedAgentCard（太粗粒度）、在 SendMessage 里加 `supports` 字段（要先构建完整 payload）

### 对我们 ACP 的启示

**值得借鉴（精简版）：**
- `PARTIAL` 状态是个好概念：Agent 不是只有"能"/"不能"，还有"部分支持+协商"
- `constraints` map 用于运行时协商：比我们现在的 AgentCard 静态 skills 列表更灵活
- 分离"能力查询"和"任务执行"：避免无效任务创建

**不借鉴：**
- gRPC 绑定（我们保持 JSON over HTTP）
- `cache_ttl_seconds` 服务端控制缓存（个人场景不需要，连接是即时的）
- 三种协议绑定同时支持（我们只做 HTTP）

**ACP v0.6 计划动作（来自此次分析）：**

```
POST /skills/query
{
  "skill_id": "summarize",
  "constraints": {
    "file_size_bytes": 52428800,
    "language": "zh"
  }
}

Response:
{
  "skill_id": "summarize",
  "support_level": "partial",       // supported | partial | unsupported
  "reason": "Max file size is 10MB, please chunk",
  "constraints_applied": {...}
}
```

这比我们 v0.5 里的 `QuerySkill()` 占位设计更具体，直接用这个接口设计。

---

## 2. ANP 2026-03-05 更新回顾

**最新 commit：** `feat: add failed_msg_id field to e2ee_error protocol message`  
**关键 commit（1f0abd2d）：** client_msg_id 幂等 + server_seq 有序性

我们在 v0.5 已实现 `message_id` 客户端生成去重，与 ANP 方向一致。
ANP 的 `server_seq` 有序性（防乱序）是一个我们还未实现的点：
- 当网络抖动时，消息可能乱序到达
- `server_seq` 让接收方知道消息的全局顺序
- ACP v0.6 可以加：每条消息附带 `seq` 字段，接收方可按 seq 重排

---

## 3. 当前竞品状态（2026-03-19 快照）

| 协议 | 最新活动 | 关键动向 |
|------|---------|---------|
| A2A | 2026-03-18 | QuerySkill PR open；文档 UX 改进 issue 多 |
| ANP | 2026-03-05 | 幂等 + server_seq；后续较安静 |
| IBM ACP | 2025-08 | 停更 |

---

## 4. ACP v0.6 设计输入（来自本轮研究）

基于 A2A PR #1655 + ANP server_seq，为 v0.6 新增两个设计点：

### 4A. `/skills/query` 端点（QuerySkill 精简版）
- 三级支持状态：`supported` / `partial` / `unsupported`
- `constraints` 双向：请求方传运行时参数，响应方返回调整建议
- 在 AgentCard `capabilities.query_skill: true` 标记支持

### 4B. `server_seq` 消息有序性（借鉴 ANP）
- 发送方每条消息附带 `seq`（单调递增整数）
- 接收方检测跳号：可选重排或报告丢失
- 与 `message_id` 幂等配合：id 防重，seq 保序

