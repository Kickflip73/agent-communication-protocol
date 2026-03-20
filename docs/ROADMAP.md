# ACP 协议研发路线图

> 持续更新。贾维斯每周自动扫描竞品动态，每月产出一个新版本。
> 最后更新：2026-03-20 18:13（开发轮：spec/transports.md v0.3，v0.7 全部完成）

---

## 战略定位

### 五大核心特性方向

| 特性 | 含义 | 设计原则 |
|------|------|---------|
| **① 轻量级，简单开箱即用** | 最小化接入成本，无需学习曲线 | 单文件 Skill，一个命令即运行，JSON over HTTP/SSE |
| **② P2P 无中间人** | Agent 直连，不经过任何第三方服务器 | Relay 只做连接打洞，消息直通，无持久化 |
| **③ 实用性，解决任意 Agent 通信** | 不限框架、不限平台、不限语言 | 协议最小集 + 渐进扩展，curl 可接入 |
| **④ 差异化：面向个人和团队** | 对标 A2A 企业级，我们做个人/小团队场景 | 零运维、零注册、即用即走 |
| **⑤ 标准化** | 像 MCP 标准化了 Agent↔Tool，ACP 标准化 Agent↔Agent | 开放规范，任意实现可互通 |

### 定位口号
> **MCP 标准化了 Agent 与 Tool 的通信，ACP 标准化 Agent 与 Agent 的通信。**
> A2A = 企业工厂流水线调度；ACP = 两个 Agent 之间发消息，人人可用，框架无关。

### 对 A2A 的态度
- **借鉴概念，不复制复杂度**
- Task 状态机：借鉴状态分类的思路，大幅简化（5 种而非 8 种）
- AgentCard：借鉴能力声明理念，保持极简结构
- **不借鉴**：OAuth 2.0、gRPC 绑定、多租户、Push Notification 配置管理 CRUD、TSC 治理

### 设计禁忌（红线，永不做）

- ❌ OAuth 2.0 / PKCE
- ❌ 多租户架构（`/{tenant}/tasks`）
- ❌ gRPC 绑定
- ❌ Push Notification 配置 CRUD
- ❌ 8 种 Task 状态
- ❌ 中心注册表 / 服务发现中心
- ❌ 强制 PKI / 证书机构

---

## 竞品生态现状（2026-03-20）

| 协议 | Stars | 活跃度 | 定位 | 我们的态度 |
|------|-------|--------|------|-----------|
| **A2A** (Google) | 22,643 | 🟡 TSC 治理，特性趋缓 | 企业级 Agent 总线 | 借鉴概念，不做复制 |
| **ANP** (社区) | 1,240 | 🔴 停更（最后更新 2026-03-05） | 去中心化身份 | 借鉴 DID 思路（长期） |
| **IBM ACP** | 966 | 🔴 停更（2025-08） | 多模态消息 | 参考即可 |
| **MCP** (Anthropic) | — | ✅ 稳定 | 工具调用 | 不同赛道，可互补 |

**快迭代窗口**：A2A 进入 TSC 治理模式后特性交付趋缓，ACP 3 天完成 v0.4→v0.6 三个版本，窗口持续开放。

---

## 版本路线图

### ✅ v0.4（已完成，2026-03-18）
- P2P Relay 直连（本地守护进程）
- SSE 流式端点
- AgentCard 能力声明（基础版）
- 安全加固（Unbounded Consumption 防护）
- 自动降级：P2P 失败 → HTTP 中继

---

### ✅ v0.5（已完成，2026-03-19，提前于截止日 2026-03-26）
**主题：消息结构化 + 任务追踪**

| 特性 | 状态 | Commit |
|------|------|--------|
| Task 状态机（5 种） | ✅ | `bb6aba3` |
| 结构化 Part 模型（text/file/data） | ✅ | `bb6aba3` |
| 消息幂等性（message_id + server_seq） | ✅ | `bb6aba3` |
| 双向 Task 同步（§5b） | ✅ | `bb6aba3` |
| QuerySkill() API | ✅ | `bb6aba3` |
| spec/core-v0.5.md | ✅ | `e078ef1` |
| Token 统一（P2P token == relay token） | ✅ | `74de528` |
| E2E 测试（Alpha↔Beta 验证） | ✅ | — |

**Task 状态机：**
```
submitted → working → completed
                   → failed
                   → input_required  ← 可继续（/tasks/{id}/continue）
```

---

### ✅ v0.6（全部完成 🎉，2026-03-20，提前 20 天）
**主题：外部 Agent 接入 + SDK 化**

| 特性 | 状态 | Commit |
|------|------|--------|
| spec/v0.6-minimal-agent.md（最小接入协议） | ✅ | `125422e` |
| 多 session peer registry（/peers + /peer/{id}/send） | ✅ | `ad7e1c4` |
| 标准化错误码 + failed_message_id | ✅ | `c816cb5` |
| spec/error-codes.md | ✅ | `f5b3336` |
| spec/transports.md 重组（Protocol Binding vs Extension） | ✅ | `cb88475` |
| Cloudflare Worker v2.0（多房间 + 滑动 TTL + cursor poll） | ✅ | `8e8b771` |
| Python mini-SDK RelayClient（同步 + 异步，19 tests 通过） | ✅ | `430a97f` |

**最小接入协议（3 端点即可接入 ACP）：**
```
GET  /.well-known/acp.json   → AgentCard
POST /message:send            → 接收入站消息
GET  /stream                  → SSE 出站流（可选）
```

**Python SDK 示例：**
```python
from acp_sdk import RelayClient
c = RelayClient("http://localhost:7901")
c.send("你好，Agent！")
msgs = c.recv()
```

---

### ✅ v0.7（全部完成 🎉，2026-03-20，目标原为 2026-04-23）
**主题：轻量身份信号 + 多轮对话**

| 特性 | 状态 | 备注 |
|------|------|------|
| 可选 HMAC-SHA256 签名（`sig` 字段） | ✅ 已实现 | `87dad51`，`--secret` 启用 |
| AgentCard `trust` + `hmac_signing` 能力声明 | ✅ 已实现 | `87dad51` |
| contextId 多轮对话（跨 Task 上下文延续） | ✅ 已实现 | `aabfae5`，可选字段 + capability 声明 |
| 本地局域网 Agent 发现（mDNS / 广播） | ✅ 已实现 | `aabfae5`，`--advertise-mdns`，GET /discover |
| spec/transports.md §3.6 HTTP headers 说明 | ✅ 已完善 | v0.3，§3.6，解决 A2A #1653 分类争议 |

**设计决策（2026-03-20 研究轮确认）：**
- 默认：信任 = 连接本身（零成本）
- 可选：HMAC-SHA256 `sig` 字段（10 行扩展）
- 未来 v0.8：Ed25519 可选扩展（跟踪 APS 项目，A2A #1575）
- 永不：强制 PKI / 证书机构

**HMAC 签名格式：**
```
sig = HMAC-SHA256(secret, message_id + ":" + ts).hexdigest()
```

**mDNS LAN 发现（`--advertise-mdns`）：**
```bash
# 广播自身到局域网
python3 acp_relay.py --name "Agent-A" --advertise-mdns

# 另一台机器监听 + 自动发现
python3 acp_relay.py --name "Agent-B" --advertise-mdns
curl http://localhost:7901/discover
# → [{"peer_id": "...", "name": "Agent-A", "link": "acp://192.168.1.x:7801/tok_..."}]
```
- 纯 stdlib UDP multicast（224.0.0.251:5354），零外部依赖
- Peer TTL 120s，自动过期静默节点
- SSE `type=mdns` 事件：实时新 peer 通知

**v0.7 进度（5/5 全部完成 🎉）：**

| 特性 | 状态 | Commit |
|------|------|--------|
| HMAC-SHA256 签名 | ✅ | `87dad51` |
| AgentCard trust 声明 | ✅ | `87dad51` |
| mDNS LAN 发现 | ✅ | `aabfae5` |
| context_id 能力声明 | ✅ | `aabfae5` |
| transports.md §3.6 HTTP headers 说明 | ✅ | polish，v0.3 |

---

### 🔮 v0.8（目标：2026-05）
**主题：生态建设 + 可选身份增强**

- [ ] Ed25519 可选身份扩展（参考 APS，A2A #1575）
- [ ] 兼容性测试套件
- [ ] Node.js SDK
- [ ] 规范文档正式发布（三层架构：数据模型 / 操作语义 / 绑定）

---

### 🔮 v1.0（目标：2026-06）
**主题：生产可用**

- [ ] Python + Node 参考实现（可作为 Agent 框架标准插件）
- [ ] DID 身份（可选，`did:acp:` 格式，向 ANP 靠拢）
- [ ] Extension 机制（URI 标识，向 A2A 靠拢）

---

## 核心差异化

| 维度 | A2A（企业级） | ANP（去中心化） | **ACP（个人/团队）** |
|------|-------------|--------------|------------------------|
| 部署 | 需要服务端运维 | 需要 DID 基础设施 | **零服务器，本地 Skill 即可** |
| 接入 | 改代码 + 配置 + 注册 | 需要 DID 注册 | **发一个链接，对方粘贴即连** |
| 复杂度 | 企业级，11 个端点 | 协议协商复杂 | **3 个端点，curl 可接入** |
| 认证 | OAuth 2.0 全套 | DID + 签名 | **连接时 token，HMAC 可选** |
| 数据 | 经过服务器 | 经过 DID 节点 | **真 P2P，Relay 不存消息** |
| 场景 | 企业内系统集成 | 去中心化网络 | **个人 Agent、小团队、临时协作** |
| 类比 | 企业 ERP 之间的 ESB | 区块链上的通信 | **两个人发微信** |

---

## 研究信息源（贾维斯每周自动扫描）

```
A2A:  https://github.com/a2aproject/A2A
ANP:  https://github.com/agent-network-protocol/AgentNetworkProtocol
IBM:  https://github.com/i-am-bee/acp
MCP:  https://github.com/modelcontextprotocol/specification
APS:  https://github.com/aeoess/agent-passport-system  （Ed25519 身份，v0.8 候选参考）
```
