# Agent 通信协议全景研究报告 v2
**Date:** 2026-03-18  
**Scope:** MCP · A2A · IBM ACP · ANP — 最新动态 + 对 ACP P2P 的优化启示  

---

## 一、行业格局快照（截至 2026 年 3 月）

### 重大事件
| 时间 | 事件 | 影响 |
|------|------|------|
| 2025-04-09 | Google 发布 A2A Protocol | 首个专注 Agent-to-Agent 的企业级开放协议 |
| 2025-04-11 | A2A 2025.1 发布 | 新增流式传输、增强任务状态管理、安全特性 |
| 2025-03 | IBM 发布 ACP | REST+MIME 多部分消息，session 管理，DID 集成 |
| 2025-05-04 | arxiv 四协议综合调研论文 | MCP→ACP→A2A→ANP 分层采用路线图被学界认可 |
| 2025-12-09 | Anthropic 将 MCP 捐赠给 Linux Foundation (AAIF) | MCP 成为行业事实标准，Anthropic/Block/OpenAI 共同治理 |
| 2026-02 | MCP 生态突破 1000+ 服务器 | Agent-to-Tool 层已进入企业级生产部署 |

### 四大协议定位矩阵（arxiv 2505.02279 总结）

```
                   Tool Access     Agent-to-Agent    Open Network
                       ↓                ↓                ↓
   MCP ──────────── ████████
   IBM ACP ──────────────── ████████
   A2A ─────────────────────────── ████████
   ANP ────────────────────────────────────── ████████
   
   部署建议：MCP → IBM ACP → A2A → ANP（分层递进）
```

---

## 二、各协议最新技术要点

### 1. Google A2A（最新 2025.1 版本）

**核心机制：**
- **AgentCard**：`/.well-known/agent.json` 自动发现，包含 capabilities/skills/auth 声明
- **任务生命周期**：`submitted → working → completed/failed/cancelled`（与 ACP P2P v0.3 已对齐）
- **通信模式**：`message/send`（同步）+ `message/stream`（SSE）+ `tasks/get`（轮询）+ Push Webhook
- **2025.1 新增**：增强安全特性、流式传输改进、不向后兼容的任务状态变更

**与 ACP P2P 的差距：**
- ❌ A2A 依赖 HTTP 服务器（需要域名/公网服务），我们是纯 P2P
- ❌ A2A 的 AgentCard 是静态 well-known URL，不适合临时 P2P 连接
- ✅ 我们 v0.3 已实现其四种通信模式
- 🔧 **待补**：AgentCard 格式标准化（当前仅有简单的 name/skills）

### 2. IBM ACP（Agent Communication Protocol）

**核心特性（我们命名冲突需要关注）：**
- REST-based HTTP（不是 WebSocket），支持 MIME 多部分消息（文件/图片/结构化数据）
- Session 管理（有状态会话）
- RBAC + DID 混合认证
- Agent Discovery：runtime API + 离线 manifest + metadata
- 兼容多种 agent 框架（无框架耦合）

**对 ACP P2P 的启示：**
- 🔧 **多模态消息**：当前 content 字段是纯文本/JSON，应支持 MIME type 声明
- 🔧 **Session 概念**：当前每次连接是单 session，缺乏 session ID 显式管理
- 🔧 **离线 Manifest**：可以在 acp:// link 中附带 AgentCard 摘要，减少首次握手开销

### 3. ANP（Agent Network Protocol）

**三层架构：**
1. **身份与加密通信层**：W3C DID + 端对端加密（主要贡献）
2. **元协议协商层**：动态协商交互格式
3. **应用协议层**：ADP（Agent Description Protocol）+ Agent 发现协议

**核心创新：**
- 去中心化 Agent 发现（不依赖中心注册表）
- 多 DID 隐私保护（主 DID + 多个场景子 DID）
- JSON-LD 语义图谱描述 Agent 能力
- 目标：成为 "Agentic Web 的 HTTP"

**对 ACP P2P 的启示：**
- 🔧 **DID 身份**：当前 token 是随机 hex，缺乏身份验证；引入轻量 DID 可大幅提升安全性
- 🔧 **能力语义化**：skills 当前是字符串数组，用 JSON-LD 或结构化 schema 描述能力更利于自动匹配

### 4. MCP（Model Context Protocol，现 AAIF 标准）

**最新状态：**
- 2025-12 捐赠给 Linux Foundation AAIF，Anthropic + Block + OpenAI 共治
- 生态 1000+ 服务器，进入企业级生产
- 核心定位：Agent-to-Tool（不是 Agent-to-Agent），JSON-RPC 接口

**与 ACP P2P 的关系：**
- 无竞争，互补：MCP 解决 Agent 调用工具，ACP 解决 Agent 互联
- ACP 可以作为 MCP server 暴露 Agent 能力给工具调用方

---

## 三、ACP P2P 优化路线图

基于研究结论，分三个阶段推进：

### Phase 1（v0.4）— 多模态 + Session 显式化
| 优化点 | 来源 | 实现方式 |
|--------|------|---------|
| 多模态消息 MIME 支持 | IBM ACP | message 添加 `mime_type` 字段；支持 base64 编码二进制 |
| Session ID 显式管理 | IBM ACP | 连接建立时生成 `session_id`，所有消息携带 |
| AgentCard 结构标准化 | A2A 2025.1 | 对齐 A2A AgentCard schema：`name/version/skills/capabilities/auth` |
| 消息大小限制 | 安全审计 | 配置 `--max-msg-size`（默认 1MB）；超限返回 413 |

### Phase 2（v0.5）— 安全 + 发现
| 优化点 | 来源 | 实现方式 |
|--------|------|---------|
| 轻量 DID 身份 | ANP | 生成 `did:key:` 标准 DID，作为 Agent 永久身份；token 作为会话密钥 |
| 连接鉴权 | A2A / ANP | acp:// link 中携带 token，连接时验证签名 |
| AgentCard 摘要内嵌 link | IBM ACP | `acp://host:port/token?name=X&skills=a,b` 参数化 |
| `/.well-known/acp.json` | A2A | 支持静态 AgentCard 发现（可选，兼容 A2A 生态） |

### Phase 3（v1.0）— 互操作 + 去中心化
| 优化点 | 来源 | 实现方式 |
|--------|------|---------|
| A2A 协议网关模式 | A2A | 可作为 A2A Agent 运行，接受来自 A2A 客户端的连接 |
| MCP server 模式 | MCP | 将对端 Agent 的能力暴露为 MCP tools |
| 多 session 并发 | IBM ACP | 单守护进程支持多个并发连接（当前只支持 1:1） |
| ANP-style 发现 | ANP | 基于 DID Document 的去中心化能力发现 |

---

## 四、立即可做的 Quick Wins（v0.4 优先级）

1. **Session ID**：连接时生成 UUID session_id，所有消息/任务携带，便于日志关联和多会话区分
2. **MIME 消息**：`{"type":"file","mime_type":"image/png","content":"<base64>","size":1234}`
3. **消息大小限制**：`--max-msg-size 1048576`（1MB 默认）防止 OOM
4. **AgentCard 标准化**：新增 `version`、`capabilities`（声明支持的通信模式）、`auth` 字段
5. **`/.well-known/acp.json`**：HTTP 接口新增该路由，返回 AgentCard，兼容 A2A 发现机制

---

## 五、命名冲突说明

IBM 的协议也叫 "ACP"（Agent Communication Protocol），两者同名但设计完全不同：

| 维度 | IBM ACP | ACP P2P（我们） |
|------|---------|----------------|
| 传输 | REST HTTP | WebSocket P2P |
| 拓扑 | Client-Server | Peer-to-Peer |
| 发现 | Manifest/Runtime API | acp:// link |
| 身份 | RBAC + DID | Token（→ DID 演进） |
| 定位 | 企业级框架集成 | 零服务器 Agent 直连 |

建议在 README 中增加一节说明两者差异，避免混淆。

---

*Research by J.A.R.V.I.S. · Sources: arxiv:2505.02279, a2acn.com, agent-network-protocol.com, research.ibm.com, aaif.io*
