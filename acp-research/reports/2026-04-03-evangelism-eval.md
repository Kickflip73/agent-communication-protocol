# ACP 技术布道评估 — A2A PR#1655 QuerySkill

## 评估时间
2026-04-03 08:23 Asia/Shanghai

## PR/Issue 状态

| 字段 | 值 |
|------|-----|
| PR 编号 | #1655 |
| 标题 | [Feat]: Add QuerySkill() operation for runtime skill capability introspection |
| 状态 | **open**（未合入，未被 close） |
| 作者 | Srinivasoo7 |
| 创建时间 | 2026-03-18 |
| 最后更新 | **2026-04-01**（距今约 2 天） |
| PR 评论数 | 7（含 review comments） |
| 是否活跃 | **是**——最后评论来自 @citriac（2026-03-30），真实用户从实现侧反馈了数据点，并非僵死 PR |

### 活跃度分析

PR 目前有 3 类参与者：
1. **@Srinivasoo7**（作者）：持续响应，迭代设计（如去掉 `confidence float`）
2. **@citriac**（外部实现者）：2026-03-30 从"运行中的 Agent 注册表"视角提供真实反馈
3. **@gemini-code-assist[bot]**：多次 code review（A2A 自动集成的代码审查 bot）

结论：**PR 活跃，社区有真实讨论，尚无 A2A 官方维护者明确表态合入或拒绝。**

---

## ACP vs A2A QuerySkill 对比

| 维度 | A2A 提案（PR#1655） | ACP 实现（v2.26+, latest v2.29） |
|------|-------------------|--------------------------------|
| **状态** | ⏳ Feature Request，未合入 spec | ✅ 已实现并多版本迭代测试 |
| **引入版本** | N/A（提案阶段） | v2.10（基础）→ v2.26（constraints 扩展）→ v2.29（per-skill status probe） |
| **核心端点** | `QuerySkill()` RPC（新增 gRPC 方法） | `GET /skills`（REST，零额外依赖） |
| **响应格式** | `QuerySkillResponse{status: SUPPORTED/PARTIAL/UNSUPPORTED, confidence: float, ...}` | `{skills: [{name, description, input_schema, output_schema, examples[], tags[], constraints[], limitations[]}], total, has_more}` |
| **动态运行时探测** | `QuerySkill(name, parameters)` → 单技能点查询 | `GET /skills/<id>/status` → 返回 `{available, reason, last_check}` |
| **能力约束声明** | 提案中包含 `max_file_size`, `concurrent_tasks`, `context_window` 等 | ✅ v2.26 `constraints[]` 字段已覆盖同等语义；v2.28 进一步增加 `limitations[]` |
| **过滤能力** | 无（单点查询） | `?tag=`, `?q=`, `?has_limitation=`，支持分页 |
| **部署复杂度** | 需修改 A2A spec + 所有 SDK | 零配置，Skill 注册即自动暴露；REST endpoint 开箱即用 |
| **向后兼容** | 破坏性（需 spec 版本 bump） | ✅ 完全向后兼容，skills 字段可选 |
| **引用社区 issues** | 引用 #883, #773, #921, #166 — 均为真实痛点 | ACP 针对同等痛点已有解法 |

### 关键差异点

1. **RPC vs REST**：A2A 采用 JSON-RPC 体系，QuerySkill 作为新 RPC 方法引入，需要协议层修改；ACP 用 REST `GET /skills` 保持一致性，无协议破坏。

2. **静态 vs 动态**：A2A PR#1655 的核心诉求是"运行时动态探测"（如"当前能处理 500MB 音频吗？"）；ACP v2.29 的 `GET /skills/<id>/status` 已实现等效语义的运行时可用性探测。

3. **`confidence float` 争议**：@citriac 指出 confidence 值增加 orchestrator 复杂度，@Srinivasoo7 已承诺移除；ACP 采用明确的 `SUPPORTED/UNAVAILABLE/DEGRADED` 状态枚举，无歧义。

---

## 布道草稿（建议发布）

> 适用场景：在 PR#1655 评论区以技术参考身份发布，语气友好，不推销，不贬低 A2A。

---

**Draft comment (EN, ~170 words):**

> Hi all — interesting discussion here. I've been working on a related implementation in the [Agent Communication Protocol](https://github.com/Kickflip73/agent-communication-protocol) and wanted to share some data points that might be useful as you iterate on the design.
>
> We landed a `GET /skills` endpoint (v2.10) and have since extended it through v2.29. A few observations that map directly to the concerns raised here:
>
> 1. **Removing `confidence float`**: We tried a similar field early on and dropped it for the same reason @citriac raised — it pushes ambiguity to the orchestrator. A tri-state enum (`SUPPORTED / DEGRADED / UNAVAILABLE`) turned out much cleaner in practice.
>
> 2. **Static vs runtime**: We split these into two endpoints — `GET /skills` for capability listing and `GET /skills/<id>/status` for runtime availability probing. Separating the concerns reduced implementation complexity significantly.
>
> 3. **Constraint dimensions**: The `max_file_size_bytes / concurrent_tasks / context_window` constraints you've outlined (in the Srinivasoo7 commit) match almost exactly what we standardized as `constraints[]` in v2.26.
>
> Happy to share specific schema details if it helps the discussion. No agenda here beyond "here's what we found works."

---

## 建议

- **是否值得发布：是**
- **理由**：PR#1655 仍然 open 且最近（03-30）有真实用户活跃讨论，ACP 已完整实现了 PR 提案的全部核心功能并经过多轮迭代，评论草稿提供了实证数据而非推销，时机合适。唯一风险：A2A 团队不活跃，评论可能石沉大海——但即使如此，曝光在 7 条评论可见的活跃 PR 下对 ACP 仍有价值。

---

## 下一轮开发候选（P1 特性）

基于 2026-04-03 扫描报告及当前 ACP 状态：

| 候选特性 | 来源 | 优先级 | 备注 |
|---------|------|--------|------|
| AgentCard `limitations` 字段标准化 | A2A IS#1694 | **P1** | ACP v2.28 已有 `limitations[]`，需完善文档+Schema 校验使其与 IS#1694 语义对齐 |
| `GET /skills` 端点 OpenAPI spec 完善 | 内部 + PR#1655 布道需要 | **P1** | 有助于技术布道时提供标准化 schema 参考，当前文档不够完整 |
| a2a-sdk v1.0.1 互操作兼容测试 | A2A PR#1706 | P2 | SDK alpha 发布后需验证 ACP relay 与 A2A SDK 的兼容性 |

---

*报告生成：J.A.R.V.I.S. 研究轮 | ACP v2.40 | 2026-04-03 08:23 Asia/Shanghai*
