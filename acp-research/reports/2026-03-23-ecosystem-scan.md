# ACP 竞品情报扫描 — 2026-03-23 05:23

## 扫描摘要

| 竞品 | 最新 commit | 较上次变化 |
|------|------------|-----------|
| A2A  | `7b900e77`（2026-03-16） | 无新 commit |
| ANP  | `99806f45`（2026-03-05） | 无新 commit |

---

## 重要发现：A2A 生态扩张 — WritBase 加入合作伙伴

**PR #1634**（merged 2026-03-16）：WritBase 正式加入 A2A 合作伙伴列表。

### WritBase 是什么？
- GitHub: https://github.com/Writbase/writbase
- 定位：**MCP-native 任务管理控制平面**，专为 AI Agent 集群设计
- 技术特征：
  - Postgres 后端，多租户，完整溯源追踪（full provenance tracking）
  - **双向 A2A↔WritBase 状态映射对齐**（bidirectional status mapping）
  - 支持 Agent 间任务委托（inter-agent task delegation）
  - 含委托追踪和委托安全保证（assignment tracking + delegation safety）

### 战略意义
1. **A2A 生态正在快速扩张**：合作伙伴列表不断增长，这会形成 网络效应护城河。
2. **WritBase 的"MCP-native + A2A"组合**揭示了一个新方向：工具调用层（MCP）+ Agent 通信层（A2A）协同使用正在成为行业标准。
3. **ACP 机会**：ACP 的 P2P 定位恰好与 WritBase 这类"控制平面"形成互补——WritBase 面向企业级集群管理，ACP 面向轻量个人/小团队场景，**两者并不竞争**。

### ACP 行动项
- [ ] 考虑在 `docs/comparison.md` 中增加"ACP vs 企业级 Agent 编排工具（WritBase/A2A）"对比说明，突出 ACP 的轻量 P2P 定位
- [ ] WritBase 的"任务委托 + 溯源追踪"思路可作为 ACP v2.0 的灵感来源（可选，长期）

---

## ANP 动态

无新 commit。最新仍是 `99806f45`（2026-03-05）：`failed_msg_id` 字段添加——这已被 ACP v1.1 借鉴并实现（`failed_message_id` 覆盖所有错误码，commit `e281790`）。

---

## ACP 自身进展对比

| 时间 | ACP | A2A |
|------|-----|-----|
| 2026-03-05 | v0.5 完成（Task 状态机 + 幂等性） | 无变化 |
| 2026-03-16 | v1.3 完成（Extension + DID） | CODEOWNERS + WritBase 合作伙伴 |
| 2026-03-23 | CHANGELOG v1.3 + VERSION bump | 无变化 |

**结论：ACP 迭代速度显著领先竞品，且每个版本都有真实的技术产出（非文档更新）。**
