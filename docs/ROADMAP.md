# ACP 协议研发路线图

> 持续更新。贾维斯每周自动扫描竞品动态，每月产出一个新版本。
> 最后更新：2026-03-25 16:52（文档轮：补全 v1.0–v1.6 全部版本记录，当前版本 v1.6）

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

### 🔮 v0.8（进行中，目标：2026-05）
**主题：生态建设 + 可选身份增强**

| 特性 | 优先级 | 状态 | Commit |
|------|--------|------|--------|
| Node.js SDK RelayClient（零依赖，TS 类型，19 tests） | P0 | ✅ 已完成 | `fd8c02a` |
| 兼容性测试套件（tests/compat/，黑盒 HTTP） | P0 | ✅ 已完成 | `98197cf` |
| Ed25519 可选身份扩展（spec/identity-v0.8.md） | P1 | ⏳ 开发中 | — |
| 规范文档正式发布（三层架构） | P2 | ⏳ 待开发 | — |

**兼容性测试套件（`tests/compat/`）：**
- `python3 tests/compat/run.py --url http://localhost:7901` — 黑盒合规性验证
- 41 个检查点，7 套件（AgentCard/MessageSend/Tasks/ErrorCodes/Peers/QuerySkills/HMAC）
- 三级断言：MUST / SHOULD / MAY；可选能力自动 SKIP
- `--json` 输出支持 CI 集成；零外部依赖（stdlib only）
- 任意 ACP 实现均可用此工具验证合规性

**安全细节备注（来自 APS Module 36A，2026-03-20 研究轮）：**
- Ed25519 签名载荷**必须包含 `expiresAt`**，防止重放攻击（APS 曾在此处有 bug）
- Merkle 审计日志：推迟至 v1.0（避免复杂度过早引入）

---

### ✅ v1.0（已完成，2026-03-22）
**主题：任务过滤 + 兼容性合规**

| 特性 | 状态 | Commit |
|------|------|--------|
| `/tasks` 列表过滤（status/role/since/limit） | ✅ | — |
| `tasks/list` 对齐 A2A v1.0 `last_updated_after` 语义 | ✅ | — |
| 兼容性测试套件扩展 | ✅ | — |
| Level 3 中继降级稳定化 | ✅ | — |

---

### ✅ v1.1（已完成，2026-03-22）
**主题：Level 3 完整 Relay 降级**

| 特性 | 状态 | Commit |
|------|------|--------|
| P2P → Relay 自动降级（`--relay` flag） | ✅ | — |
| Relay session 复用（token 双用） | ✅ | — |
| Relay 状态暴露至 `/status` | ✅ | — |

---

### ✅ v1.2（已完成，2026-03-22）
**主题：标准化端点 + 错误码扩展**

| 特性 | 状态 | Commit |
|------|------|--------|
| 标准化端点命名（`:cancel`、`:continue`、`:update`） | ✅ | `a7f08a8` |
| 端点命名风格统一（: 前缀对齐 A2A） | ✅ | — |
| 错误码扩展（`ERR_PEER_CONNECTING` 等） | ✅ | — |

---

### ✅ v1.3（已完成，2026-03-23）
**主题：自主权身份 — `did:acp:`**

| 特性 | 状态 | Commit |
|------|------|--------|
| `did:acp:` 自主权 DID（由 Ed25519 公钥派生） | ✅ | `6595e39` |
| `GET /.well-known/did.json`（W3C DID Document） | ✅ | `6595e39` |
| `verificationMethod[]` + `publicKeyMultibase` | ✅ | `6595e39` |
| AgentCard `identity.did` 字段 | ✅ | `6595e39` |
| 无外部注册表，离线可用，零依赖 | ✅ | — |

**设计亮点：** DID = 公钥本身，无需中心注册，比 A2A #1672 提案提前实现。

---

### ✅ v1.4（已完成，2026-03-23/24）
**主题：三级 NAT 穿透（DCUtR 风格 UDP 打洞）**

| 特性 | 状态 | Commit |
|------|------|--------|
| `DCUtRPuncher` 类（~200 行，UDP 打洞状态机） | ✅ | `8c162d4` |
| Level 1: P2P 直连（3 次重试） | ✅ | — |
| Level 2: DCUtR UDP 打洞（STUN + 信令 WS） | ✅ | `8c162d4` |
| Level 3: Cloudflare Worker 中继兜底 | ✅ | `8c162d4` |
| Cloudflare Worker v2.1（NAT 信令端点） | ✅ | `8c162d4` |
| HTTP reflection 备用 IP 发现（STUN 失败时） | ✅ | `b3da914` |
| `spec/nat-traversal-v1.4.md` + `docs/nat-traversal.md` | ✅ | — |
| 测试：17 项全绿（STUN/消息/降级/握手） | ✅ | — |

**三级降级架构（对应用层完全透明）：**
```
Level 1: 真 P2P WebSocket 直连
    ↓ 失败 3 次
Level 2: DCUtR UDP 打洞（同时探测，TTL 递增）
    ↓ 打洞失败（对称 NAT / CGNAT，约 25% 场景）
Level 3: Cloudflare Worker 中继（100% 成功率兜底）
```

---

### ✅ v1.5（已完成，2026-03-24）
**主题：混合身份模型（自主权 + CA 双轨）**

| 特性 | 状态 | Commit |
|------|------|--------|
| `--ca-cert` CA 签名证书扩展（混合身份） | ✅ | `7aaa2cb` |
| `identity.scheme` 升级为 `"ed25519+ca"` | ✅ | `7aaa2cb` |
| 4 种信任验证策略（spec/identity-v1.5.md） | ✅ | — |
| 测试：6/6 PASS | ✅ | — |

**动机：** A2A #1672（43 条评论）正在讨论混合信任模型，ACP v1.5 提前实现并成为差异化点。

---

### ✅ v1.5.2-dev（已完成，2026-03-25）
**主题：Cancel 语义正式化（spec §10）**

| 特性 | 状态 | Commit |
|------|------|--------|
| `spec §10` — Task Cancel 完整合约 | ✅ | `0d19a11` |
| Cancel 同步即时：`:cancel` 返回最终 `canceled` 状态 | ✅ | `0d19a11` |
| Cancel 幂等：重复调用返回 200 + 现有状态 | ✅ | `0d19a11` |
| `input_required` 状态也可取消 | ✅ | `0d19a11` |
| Show HN 草稿更新（A2A #1680/#1684 对比要点） | ✅ | `0d19a11` |

**差异化亮点：** A2A issue #1680、#1684 至今未能明确 cancel 语义（`CancelTaskRequest` 定义都缺失），ACP cancel 已完整定义并测试通过。

---

### ✅ v1.6（已完成，2026-03-25）
**主题：HTTP/2 cleartext (h2c) 传输绑定**

| 特性 | 状态 | Commit |
|------|------|--------|
| `_H2Handler` — raw `h2` 状态机 over `ThreadingTCPServer` | ✅ | `cf578e3` |
| `--http2` 启动标志（可选，优雅降级到 HTTP/1.1） | ✅ | `cf578e3` |
| AgentCard `capabilities.http2: true` | ✅ | `cf578e3` |
| h2c prior knowledge upgrade（RFC 7540 §3.2） | ✅ | `cf578e3` |
| `spec/transports.md §4.3`（HTTP/2 绑定说明） | ✅ | — |
| 测试套件：12 项 h2c 专项全绿 | ✅ | `394b71c` |

**实现选择：** raw `h2` 状态机（非 hypercorn ASGI），避免在非主线程中注册 signal handler 的限制；`h2`/`hypercorn` 为可选依赖，未安装时自动 fallback 并打印警告。

**测试基础设施修复（同期，commit `5ce0ed3`）：**
- `tests/helpers.py`（新）：抽取 `clean_subprocess_env()`，解决 conftest 命名空间冲突
- 9 个测试文件：`from conftest import` → `from helpers import`
- `test_dcutr_t1~t4`：补 `pytestmark = pytest.mark.asyncio`
- `tests/cert/test_level1.py`：修复 setup_module、port 计算、健康检查路径、fixture 依赖
- **最终结果：163 passed, 3 skipped (P2P), 0 failed ✅**

---

### 🔮 v1.7（计划中，目标：2026-04）
**主题：Python acp-client SDK + 文档站**

| 特性 | 优先级 | 状态 |
|------|--------|------|
| `acp-client` Python 包（pip 可安装，类型注解完整） | P0 | ⏳ 待开发 |
| Node.js `@acp/client` npm 包 | P1 | ⏳ 待开发 |
| 文档站（`docs/` → GitHub Pages） | P1 | ⏳ 待开发 |
| Show HN 发布 | P0 | ⏳ 待发布 |

---

### ✅ v2.2（已完成，2026-03-27）
**主题：任务列表查询 + 分页**

| 特性 | 状态 | Commit |
|------|------|--------|
| [x] GET /tasks 列表查询 + 分页 (2026-03-27，commit fac2a31) | ✅ | `fac2a31` |
| [x] failed_msg_id 错误回传（2026-03-27，commit 4f2b548） | ✅ | `4f2b548` |
| [x] supported_transports AgentCard 字段（2026-03-27，commit 7702ef5） | ✅ | `7702ef5` |

---

### 🔧 v2.3（目标：2026-04）
**主题：SDK 增强 + 规范对齐**

| 特性 | 优先级 | 状态 | Commit |
|------|--------|------|--------|
| `supported_transports` 补充到 spec/core-v1.0.md（文档对齐） | P0 | ✅ 已完成（2026-03-27，commit 0a3af37） | `0a3af37` |
| Python SDK `auto_stream` 参数（`send(msg, auto_stream=True)` 自动选择 SSE） | P1 | ✅ 已完成（2026-03-27，commit 0a3af37） | `0a3af37` |
| `GET /tasks` cursor 分页（`?cursor=` 参数，对标 A2A page_token） | P2 | ✅ 已完成 | `fac2a31` |

**设计目标：**
- `supported_transports` 在 AgentCard spec 中正式文档化（代码已实现，spec 缺失）
- `auto_stream=True`：`send()` 方法自动检查 peer capabilities，若 peer 支持 SSE 则切换到 stream 模式接收回复
- cursor 分页已在 v2.2 实现，ROADMAP 正式归档

---

### 🔮 v2.0（目标：2026-06）
**主题：生产可用 + 生态**

- [ ] `acp-client` 作为 Agent 框架标准插件（LangChain / AutoGen 集成）
- [ ] Extension 机制（URI 标识扩展点，向 A2A 靠拢）
- [ ] 完整 DID 文档站 + 合规认证工具公开

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
