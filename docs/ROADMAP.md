# ACP 协议研发路线图

> 持续更新。贾维斯每周自动扫描竞品动态，每月产出一个新版本。
> 最后更新：2026-04-12（v3.11.0：async task queue workers — POST /tasks/queue/worker + GET /tasks/queue/workers + DELETE；auto-dispatch；TQW1-TQW12 全 PASS；当前版本 3.11.0，commit a4b31ca）

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

### ✅ v0.8（已完成，2026-04-03）
**主题：生态建设 + 可选身份增强**

| 特性 | 优先级 | 状态 | Commit |
|------|--------|------|--------|
| Node.js SDK RelayClient（零依赖，TS 类型，19 tests） | P0 | ✅ 已完成 | `fd8c02a` |
| 兼容性测试套件（tests/compat/，黑盒 HTTP） | P0 | ✅ 已完成 | `98197cf` |
| Ed25519 可选身份扩展（spec/identity-v0.8.md） | P1 | ✅ 已完成 | f25a00b |
| 规范文档正式发布（三层架构） | P2 | ✅ 已完成 | 06cd624 |

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

### ✅ v1.4（已完成，2026-03-23/24 → 最终完成 2026-04-08）
**主题：三级 NAT 穿透（DCUtR 风格 UDP 打洞）**

| 特性 | 状态 | Commit |
|------|------|--------|
| `DCUtRPuncher` 类（~200 行，UDP 打洞状态机） | ✅ | `8c162d4` |
| `_connect_with_nat_traversal()` 三级自动降级主流程 | ✅ | `d90b328` |
| Level 1: 直接 WebSocket（`ws://IP:port/token`，3s 超时） | ✅ | — |
| Level 2: DCUtR UDP 打洞（STUN + 信令 WS，12s 超时） | ✅ | `8c162d4` |
| Level 3: Relay 兜底（Cloudflare Worker，自动触发） | ✅ | `8c162d4` |
| Cloudflare Worker v2.1（NAT 信令端点） | ✅ | `8c162d4` |
| HTTP reflection 备用 IP 发现（STUN 失败时） | ✅ | `b3da914` |
| `--relay` 语义更新：现触发强制 L3 bypass（不再手动） | ✅ | `d90b328` |
| `spec/nat-traversal-v1.4.md` + `docs/nat-traversal.md` | ✅ | — |
| 测试：34 项全绿（test_dcutr_t1~t6, test_nat_traversal_integration T1~T5, test_nat_signaling, test_nat_http_reflect） | ✅ | `d90b328` |

**三级降级架构（对应用层完全透明）：**
```
Level 1: 直接 WebSocket (ws://IP:port/token)   [3s timeout]
    ↓ 超时/失败
Level 2: DCUtR UDP 打洞（STUN 发现地址 → 信令 WS 协商 → 同时探测）  [12s timeout]
    ↓ 打洞失败（对称 NAT / CGNAT，约 30% 场景）
Level 3: Cloudflare Worker 中继兜底（100% 成功率）
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

### ✅ v1.7（已完成，2026-03-28）
**主题：Python acp-client SDK + 文档站**

| 特性 | 优先级 | 状态 |
|------|--------|------|
| `acp-client` Python 包（pip 可安装，类型注解完整） | P0 | ✅ 已完成 |
| `acp_client/` 子模块拆分（client / async_client / models / exceptions） | P0 | ✅ 已完成 |
| `AgentCard`, `Message`, `Task`, `TaskStatus`, `Part` 数据模型 | P0 | ✅ 已完成 |
| `ACPError` 异常层次体系 | P0 | ✅ 已完成 |
| `acp-client` CLI 入口点（status/peers/send/recv/tasks/stream） | P1 | ✅ 已完成 |
| `pyproject.toml` PEP 517 构建配置 | P0 | ✅ 已完成 |
| `README-sdk.md` 完整 SDK 文档（安装 + 快速入门 + API 参考） | P0 | ✅ 已完成 |
| `tests/test_sdk_package.py`（60 测试用例，全部通过） | P0 | ✅ 已完成 |
| `pip install -e .` 可用，零强制依赖 | P0 | ✅ 已完成 |
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

### ✅ v2.4（已完成，2026-03-27）
**主题：AgentCard 拓扑声明**

| 特性 | 优先级 | 状态 | Commit |
|------|--------|------|--------|
| `transport_modes` 顶层字段 — AgentCard 声明路由拓扑 `["p2p", "relay"]` | P1 | ✅ 已完成（2026-03-27） | `cf16664` |
| `--transport-modes` CLI 标志（逗号分隔子集） | P1 | ✅ 已完成（2026-03-27） | `cf16664` |
| spec/core-v1.0.md 更新：§5.2 顶层字段表、§5.4 transport_modes 专节 | P0 | ✅ 已完成（2026-03-27） | `cf16664` |
| 15 个单元测试（test_transport_modes_v24.py） | P1 | ✅ 已完成（2026-03-27） | `cf16664` |

**设计核心区别：**
- `transport_modes`（路由拓扑）≠ `capabilities.supported_transports`（协议绑定）
  - `supported_transports`: `["http", "ws", "h2c"]` — *如何传输字节*（协议层）
  - `transport_modes`: `["p2p", "relay"]` — *数据走哪条路径*（拓扑层）
- 默认 `["p2p", "relay"]`，沙箱环境可声明 `["relay"]`，公网节点可声明 `["p2p"]`

---

### ✅ v2.7（已完成，2026-03-28）
**主题：AgentCard `limitations` 字段 — 三元能力边界声明**

| 特性 | 优先级 | 状态 | Commit |
|------|--------|------|--------|
| `limitations: string[]` 顶层 AgentCard 字段（声明 agent 不能做的事） | P0 | ✅ 已完成 | — |
| `--limitations` CLI flag（逗号分隔，e.g. `--limitations "no_file_access,no_internet"`） | P0 | ✅ 已完成 | — |
| `/status` 端点响应包含 `limitations` 数组 | P1 | ✅ 已完成 | — |
| `_limitations` 全局变量初始化为 `[]`（向后兼容默认值） | P1 | ✅ 已完成 | — |
| spec/core-v1.3.md §11：`limitations` 字段 Schema、well-known values 表、三元边界说明 | P0 | ✅ 已完成 | — |
| docs/whats-new.md：v2.7 区块（用法示例 + A2A #1694 对比） | P1 | ✅ 已完成 | — |
| README：vs-A2A 对比表新行 + v2.7 亮点段落（ref A2A #1694） | P1 | ✅ 已完成 | — |
| `tests/test_limitations.py`：20 个测试用例 LM1–LM5（全通过） | P1 | ✅ 已完成 | — |

**差异化亮点：**
- A2A issue [#1694](https://github.com/a2aproject/A2A/issues/1694)（2026-03-27）：提案在 AgentCard 中添加 `limitations` 字段，尚未合并
- ACP v2.7 当天即发布可运行代码，比 A2A 提案早落地
- 三元能力边界完整声明：`capabilities`（能做）+ `availability`（何时）+ `limitations`（不能做）
- 完全向后兼容：旧客户端忽略可选的 `limitations` 字段

---

### ✅ v2.6（已完成，2026-03-27）
**主题：Task `cancelling` 中间状态 + spec 更新**

| 特性 | 优先级 | 状态 | Commit |
|------|--------|------|--------|
| `TASK_CANCELLING = "cancelling"` 常量 + `CANCELLING_STATES` 集合 | P0 | ✅ 已完成 | TBD |
| `:cancel` 端点两阶段取消（phase-1: `cancelling` SSE，phase-2: 异步 `canceled`） | P0 | ✅ 已完成 | TBD |
| 幂等取消：`cancelling`/`canceled` → 200 + 当前状态 | P0 | ✅ 已完成 | TBD |
| AgentCard `capabilities.task_cancelling = true` | P1 | ✅ 已完成 | TBD |
| spec/core-v1.0.md §3.2 新增 `cancelling` 状态行 | P0 | ✅ 已完成 | TBD |
| spec/core-v1.0.md §3.3.1 两阶段取消协议（时序图） | P0 | ✅ 已完成 | TBD |
| spec/core-v1.0.md §8.2 更新 cancel 路径：`working → cancelling → canceled` | P1 | ✅ 已完成 | TBD |
| spec/core-v1.0.md Appendix B A2A 对比表更新（cancel 语义差异化） | P1 | ✅ 已完成 | TBD |
| `tests/test_task_cancel.py`（10 个测试用例） | P1 | ✅ 已完成 | TBD |

**差异化亮点：**
- A2A issue [#1684](https://github.com/google-a2a/A2A/issues/1684)：`CancelTaskRequest` 无正式定义
- A2A issue [#1680](https://github.com/google-a2a/A2A/issues/1680)：缺少「正在取消中」中间状态
- ACP v2.6 提前补全上述两个语义缺口，形成**协议差异化**

**两阶段取消时序：**
```
Client                          Server
  |                               |
  |-- POST /tasks/{id}:cancel --> |
  |                               | phase-1: state → cancelling
  |                               |   SSE: {"type":"status","state":"cancelling"}
  |<-- 200 {status:cancelling} -- |
  |                               | phase-2 (async): stop work → canceled
  |                               |   SSE: {"type":"status","state":"canceled"}
```

---

### ✅ v2.5（已完成，2026-03-27，commit `a76ede6`）
**主题：Task 事件序列规范 + SSE 字段完整性**

| 特性 | 优先级 | 状态 | Commit |
|------|--------|------|--------|
| **Task 事件序列规范**（spec §8）— 定义 submitted→working→completed 的 SSE 事件发送顺序及必填字段 | P0 | ✅ 已完成 | `a76ede6` |
| SSE 示例字段完整性审查 — 检查 spec 中所有 SSE 示例是否包含 `task_id`、`seq`、`ts` 等必要字段 | P0 | ✅ 已完成 | `a76ede6` |
| `task_id` 在 SSE 事件中的必填语义正式化（status/artifact 事件中为 MUST） | P1 | ✅ 已完成 | `a76ede6` |
| spec/core-v1.0.md §8.7 Conformance Requirements（7 MUST + 2 SHOULD + 3 MAY） | P1 | ✅ 已完成 | `a76ede6` |
| `tests/test_task_event_sequence.py` — Task 事件序列集成测试（10 用例，9 通过，1 skip） | P1 | ✅ 已完成 | `a76ede6` |
| relay v2.5.0 — SSE 全局 seq、命名 event 行、AgentCard supported_interfaces | P1 | ✅ 已完成 | `a76ede6` |

**完成摘要：**
- spec §8 Task 事件序列规范：§8.1 Envelope 字段表、§8.2 生命周期顺序图、§8.3-§8.5 各类型 Schema + 完整 JSON 示例、§8.6 Wire Format 全流示例、§8.7 Conformance
- relay v2.5.0：每条 SSE 事件携带全局单调递增 `seq`；task 相关事件发送 named `event:` 行（`acp.task.status` / `acp.task.artifact`）
- 测试覆盖：TES1（完整生命周期）TES2（必填字段）TES3（seq 单调性）TES4（状态顺序）TES5（failed.error）TES6（artifact.parts）TES7（message 字段）TES8（同 task seq 递增）TES9（终态后无新事件）TES10（首事件为 submitted）

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

### ✅ v2.4 — Skills 能力发现（✅ 2026-03-28）
**主题：Skills-lite — 结构化能力发现端点**

> Skills-lite v2.10.0, GET /skills + structured AgentCard skills, 2026-03-28

- `GET /skills` 端点：tag/q/limit/offset 过滤 + 分页
- AgentCard `skills[]` 结构化对象数组
- `--skills` CLI 向后兼容（CSV 自动转换）
- 测试：SK1–SK6，6/6 PASS

---

### ✅ v2.8（已完成，2026-03-28）
**主题：Extension 机制 — URI 标识扩展点，向 A2A 靠拢**

| 特性 | 优先级 | 状态 | Commit |
|------|--------|------|--------|
| `_make_builtin_extensions()` — 内置扩展自动注册（hmac/mdns/h2c 对应 `acp:ext:*-v1` URI） | P0 | ✅ 已完成 | — |
| `_make_agent_card()` 始终输出 `extensions: []`（v2.8 前为 opt-in，现强制包含） | P0 | ✅ 已完成 | — |
| `--extensions URI[,URI,...]` 新 CLI flag（批量声明自定义扩展） | P1 | ✅ 已完成 | — |
| URI 去重：相同 URI 在内置+用户声明中只保留一次 | P1 | ✅ 已完成 | — |
| SDK：`Extension` 数据类（uri/required/params，to_dict/from_dict，__repr__） | P0 | ✅ 已完成 | — |
| SDK：`AgentCard.extensions: List[Extension]` 字段（默认 `[]`） | P0 | ✅ 已完成 | — |
| SDK：`has_extension(uri)` / `get_extension(uri)` / `required_extensions()` 便捷方法 | P1 | ✅ 已完成 | — |
| SDK：向后兼容——旧响应无 `extensions` 字段时正常解析为 `[]` | P0 | ✅ 已完成 | — |
| spec/core-v1.0.md §5.5：完整 Extension 机制说明（Schema/URI 规范/well-known 表/语义规则） | P0 | ✅ 已完成 | — |
| `tests/test_extensions.py`：39 个测试用例（全通过，无回归） | P1 | ✅ 已完成 | — |

**差异化亮点：**
- URI 命名约定：`acp:ext:<name>-v<version>`（内置）/ HTTPS URL（外部）
- 非强制默认：`required: false` — 客户端不认识的扩展直接忽略，完全向后兼容
- 无注册中心：轻量设计，URI 唯一性由扩展定义方负责
- 内置扩展（hmac/mdns/h2c）自动注册，无需用户手动声明

---

### ✅ v2.0（已完成，2026-03-28）
**主题：生产可用 + 生态**

- [x] `acp-client` 作为 Agent 框架标准插件（LangChain / AutoGen 集成）
  - ✅ `ACPTool` — LangChain BaseTool 适配器（lazy import, zero hard dependency）
  - ✅ `ACPCallbackHandler` — LangChain CallbackHandler（tool 通信日志）
  - ✅ `create_acp_tool()` — 工厂辅助函数（顶层导出）
  - ✅ `sdk/python/acp_client/integrations/langchain.py` — acp_client v1.8.0 发布
- [x] Extension 机制（URI 标识扩展点，向 A2A 靠拢）
  - ✅ `acp:ext:hmac-v1` / `acp:ext:mdns-v1` / `acp:ext:h2c-v1` 内置扩展自动注册
  - ✅ `Extension` 数据类 + `AgentCard.extensions` 字段 + 向后兼容
  - ✅ relay v2.8.0 上线
- [ ] 完整 DID 文档站 + 合规认证工具公开

---

### ✅ v2.9 — GET /messages 端点（✅ 2026-03-28）
**主题：统一消息查询接口**

- `GET /messages` 端点：查询历史消息，支持 peer_id/since/limit/offset 过滤 + 分页
- 消息 envelope 标准化：每条消息携带 `message_id`、`seq`、`ts`、`from` 字段
- 向后兼容：旧版 `/recv` 端点继续支持
- AgentCard `capabilities.message_history: true` 声明

---

### ✅ v2.17（已完成，2026-03-30）
**主题：Availability Schedule — CRON 调度 Agent 在线窗口**

| 特性 | 状态 |
|------|------|
| stdlib-only CRON 解析器（`*`, `/`, `-`, `,`）| ✅ |
| `_next_cron_datetime()` 计算下次在线时刻 | ✅ |
| AgentCard `availability.schedule` 字段（CRON 表达式）| ✅ |
| AgentCard `availability.timezone` 字段（IANA 时区）| ✅ |
| `GET /availability` 专用端点（返回 `has_schedule` + `next_active_at`）| ✅ |
| `POST /availability/heartbeat` 端点（更新 `last_active_at`）| ✅ |
| `capabilities.availability_schedule: bool` 能力声明 | ✅ |
| `tests/test_availability_schedule.py` AS1–AS15：22/22 PASS | ✅ |
| 全量回归：171/171 PASS | ✅ |

**差异化：** A2A IS#1667 `availability_metadata` 提案仍在讨论中，ACP 以零外部依赖纯 stdlib 实现抢先落地。

---

### ✅ v2.18（已完成，2026-03-30）
**主题：trust.signals JWKS 兼容层（对齐 A2A IS#1628）**

| 特性 | 状态 |
|------|------|
| `GET /.well-known/jwks.json` — RFC 7517 JWK Set 端点 | ✅ |
| `_build_jwks()` — Ed25519 公钥转 JWK（kty=OKP, crv=Ed25519, alg=EdDSA, RFC 8037）| ✅ |
| `trust.signals[]` 新增 `type=jwks` 信号 | ✅ |
| AgentCard `capabilities.trust_jwks: true` + `endpoints.jwks` 声明 | ✅ |
| 旧信号 `type=ed25519_identity` 保留，双信号并存向后兼容 | ✅ |
| `tests/test_jwks.py` JW1–JW10：13/13 PASS | ✅ |
| `test_trust_signals.py` 回归：8/8 PASS | ✅ |

**差异化：** A2A IS#1628（JWKS 密钥发现）仍在讨论，ACP 率先交付可运行实现。

---

### ✅ v2.19（已完成，2026-03-30）
**主题：Auto NAT Traversal Integration + BUG-047 修复**

| 特性 | 状态 |
|------|------|
| `POST /peers/connect` 自动三级 NAT 穿透（Level1 → Level2 → Level3）| ✅ |
| `GET /status` 返回 `connection_type` 字段（`host` / `p2p_direct` / `dcutr_direct` / `relay`）| ✅ |
| SSE 事件：`dcutr_started` / `dcutr_connected` / `relay_fallback` | ✅ |
| `connection_type` 初始值修复（BUG-047：null → `"host"`）| ✅ |
| `tests/test_nat_integration.py`：9 项全通过 | ✅ |

**主要修复（BUG-047）：** `GET /status` 在 host 模式启动时 `connection_type` 由 `null` 正确初始化为 `"host"`，peer 断开时自动重置。

---

### 🔮 v3.0 — NAT Auto-Traversal（✅ 2026-03-28）
**主题：零配置 NAT 穿透完整方案**

- 三级 NAT 穿透策略（Direct → DCUtR UDP hole-punch → Relay）已完整实现
- Level 1: 公网 IP / 局域网直连（延迟 < 1ms）
- Level 2: DCUtR 风格 UDP 打洞（~70% 真实 NAT 场景成功）
- Level 3: Cloudflare Worker 无状态中继（100% 成功率兜底）
- 信令服务器：一次性地址交换（TTL 30s），零消息帧存储
- SSE 实时反映连接级别：`dcutr_started` → `dcutr_connected` / `relay_fallback`
- `GET /status` 返回 `connection_type`: `p2p_direct` | `dcutr_direct` | `relay`

---

### ✅ v2.38（完成 — 2026-04-03，开发轮）
**主题：Message Priority — 消息优先级路由**

- ✅ **`priority` 字段**：`POST /message:send` 支持 `critical | high | normal | low`（默认 `normal`）
- ✅ **`GET /recv` 优先级排序**：按 `critical > high > normal > low` 返回消息
- ✅ `_status.priority_counts`：统计各级别已发送消息数
- ✅ `capabilities.message_priority: true`
- ✅ **MP1–MP9**：9/9 PASS（~5.7s）
- **差异化**：A2A 和 ANP 均无消息优先级机制；ACP 是首个支持 per-message 优先级路由的轻量协议

---

### ✅ v2.39（完成 — 2026-04-03，开发轮）
**主题：Long Poll /recv — 订阅式消息接收**

- ✅ **`GET /recv?wait=<seconds>`**：长轮询端点（commit `7fbf469`）
  - 队列为空时挂起等待，有消息即刻返回；`wait` 参数 0-30s，默认 0
  - 超时返回 `{timed_out: true}`；有消息返回 `{timed_out: false}`
  - 使用 `_sse_notify` threading.Event 基础设施（零新开销）
  - Deadline 循环防止 spurious wakeup 误判
- ✅ `capabilities.recv_long_poll: true`
- ✅ **LP1–LP9**：9/9 PASS
- **修复**：spurious wakeup bug；测试端口冲突（_free_port 同时检查 WS+HTTP 端口）
- **差异化**：A2A 和 ANP 均无 long-poll 机制；ACP 支持订阅式消息接收，零浪费轮询

---

### ✅ v2.40（完成 — 2026-04-03，开发轮）
**主题：AgentCard `agent_limitations` — 机器可读约束声明**

- ✅ **`agent_limitations` 对象**：AgentCard 和 `/status` 中新增机器可读约束字段（commit `e3aa6a8`）
  - `max_message_size_bytes`: 65536（64 KB 单条消息限制）
  - `max_recv_queue_size`: 1000（接收队列容量上限）
  - `max_wait_seconds`: 30（long-poll 最大等待，与 v2.39 一致）
  - `max_peers`: 100（并发 peer 连接上限）
  - `supported_message_roles`: ["user", "agent", "system"]
  - `supported_priorities`: ["critical", "high", "normal", "low"]
- ✅ `capabilities.agent_limitations: true`
- ✅ **AL1–AL6**：6/6 PASS；回归 18/18 PASS
- **设计决策**：字段命名为 `agent_limitations`（非 `limitations`），避免与 v2.20 的 `LimitationObject[]` 冲突，两套语义清晰共存
- **差异化**：受 A2A IS#1694 启发，ACP 是首个实现机器可读约束声明的轻量 Agent 协议

---

### ✅ v2.41（完成 — 2026-04-03，开发轮）
**主题：`GET /skills` OpenAPI 3.1 spec — 标准化技能发现接口**

- ✅ **`docs/openapi-skills.yaml`**：OpenAPI 3.1 完整规范（commit `6697919`）
  - `SkillsResponse` 和 `Skill` 完整 Schema
  - 查询参数：`filter`（名称过滤）、`format`（full/names）
  - 内置完整示例
- ✅ **`AgentCard.skills_schema_url`**：`/docs/openapi-skills.yaml`
- ✅ **`GET /docs/openapi-skills.yaml`**：CORS 开放的静态文件服务端点
- ✅ `capabilities.skills_openapi_spec: true`
- ✅ **SO1–SO5**：5/5 PASS；回归 15/15 PASS
- **战略意义**：为 A2A IS#1655 技术布道提供可引用的标准化 Schema，ACP 是首个提供 OpenAPI spec 的轻量 Agent 协议

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

---

### ✅ v2.80（完成 — 2026-04-08，开发轮）
**主题：heartbeat_period_ms — AgentCard 心跳周期声明**

| 特性 | 状态 |
|------|------|
| `heartbeat_period_ms` AgentCard 顶层字段 | ✅ |
| `--heartbeat-period-ms` CLI flag | ✅ |
| `capabilities.heartbeat_period_declared` | ✅ |
| `/availability` + `/availability/heartbeat` 响应同步 | ✅ |
| `tests/test_heartbeat_period.py` HP1–HP10：10/10 PASS | ✅ |

**差异化**：A2A Issue #1667 heartbeat agents 讨论中，ACP 率先落地可声明 heartbeat 周期的 AgentCard 字段。

---

### ✅ v2.81（完成 — 2026-04-08，开发轮）
**主题：task_evidence — 任务生命周期证据锚点**

| 特性 | 状态 |
|------|------|
| `POST /tasks/{id}/evidence`（提交证据） | ✅ |
| `GET /tasks/{id}/evidence`（列表查询） | ✅ |
| `GET /tasks/{id}/evidence/latest`（最新证据） | ✅ |
| `capabilities.task_evidence: true` | ✅ |
| `tests/test_task_evidence.py` TE1–TE12：12/12 PASS | ✅ |

**差异化**：A2A Issue #1721 Assay 框架任务证据讨论中，ACP 率先落地完整任务证据锚点系统，
形成 trust signals → capability token → task evidence 完整可信执行闭环。

---

### ✅ v2.82 — evidence_stream: SSE lifecycle subscription (2026-04-08)

| 特性 | 状态 | Commit |
|------|------|--------|
| `GET /tasks/{id}/evidence-stream` — SSE real-time subscription for task lifecycle evidence | ✅ 已完成 | 98bf92f |
| Replay on connect: pushes all existing evidence entries before live stream | ✅ 已完成 | 98bf92f |
| Multi-subscriber support per task | ✅ 已完成 | 98bf92f |
| Keepalive interval: 5s | ✅ 已完成 | 98bf92f |
| `capabilities.evidence_stream: true` in status and AgentCard | ✅ 已完成 | 98bf92f |
| `test_evidence_stream.py`: ES1–ES12 = **12/12 PASS** | ✅ 已完成 | 98bf92f |

---

### 🔮 v2.83（候选）
**候选特性（待 Stark 先生确认）**：

| 候选 | 来源 | 说明 |
|------|------|------|
| `GET /protocol-binding/compatibility` | A2A #1723 SLIMRPC | 多协议绑定兼容性矩阵，声明 ACP 与 gRPC/REST/WebSocket 等协议的兼容性级别 |
| `PUT /agent-card/schedule` | A2A #1667 延伸 | 完整调度元数据（scheduleType/cronExpression/nextActiveAt/taskLatencyMaxSeconds） |
| `POST /tasks/{id}/evidence/batch` | ACP 内生 | 批量提交多条证据（减少 RTT） |

---

### ✅ v2.84（2026-04-08 完成）
**来源：NAT 穿透完成后的后续方向 + A2A/ANP 竞品研究**

| 特性 | 来源 | 优先级 | 状态 | Commit |
|------|------|--------|------|--------|
| Show HN 发布准备（README polish + ROADMAP 更新） | 内生 | P0 | ✅ 已完成 | 本轮 |
| AgentCard `protocol_bindings[]` 数组字段（A2A §5.8 对齐） | A2A §5.8 §1619 | P1 | ✅ 已完成 | `2f42022` |
| `client_msg_id` 幂等性增强（ANP §3.2 借鉴） | ANP 借鉴 | P2 | ✅ 已完成 | `2f42022` |

**实现说明：**
- `protocol_bindings[]`：AgentCard 顶层新增数组字段，单元素 `urn:acp:binding:p2p-relay/v1`；保留单数 `protocol_binding` 向后兼容；新 capability flag `protocol_bindings_array=true`
- `client_msg_id`：`/message:send` 接受 `client_msg_id` 作为 `message_id` 别名（优先级：`message_id` > `client_msg_id` > 自动生成）；所有发送响应回显 `client_msg_id`；dedup 缓存覆盖两种形式
- README version badge 更新 v2.82.0 → v2.84.0

---

### ✅ v2.85（完成 — 2026-04-08，开发轮）
**主题：Ed25519 Identity 默认化 + 协议兼容性矩阵**

| 特性 | 来源 | 优先级 | 状态 | Commit |
|------|------|--------|------|--------|
| Ed25519 keypair 默认生成（移除 `--identity` 手动开启限制） | ACP 核心 | P0 | ✅ 已完成 | `397823e` |
| `--no-identity` 新 flag（测试/嵌入场景禁用） | ACP 核心 | P0 | ✅ 已完成 | `397823e` |
| `capabilities.identity_default=True` | ACP 核心 | P0 | ✅ 已完成 | `397823e` |
| `GET /protocol-binding/compatibility` 多协议兼容矩阵 | A2A #1723 延伸 | P1 | ✅ 已完成 | `397823e` |
| ID-01..ID-10 + PBC-01..PBC-10 测试 | 测试轮 | — | ✅ 20/20 PASS | `397823e` |

**实现说明：**
- `~/.acp/identity.json` 首次运行自动生成，跨重启持久化；`--identity <path>` 向后兼容
- `/protocol-binding/compatibility`：6 协议兼容矩阵（websocket/http-sse: native, a2a/anp: partial, mcp/grpc: none）；`aligned_sections[]` 声明对齐章节
- README badge 更新: v2.84.0 → v2.85.0，1072/1072 → 1092/1092

**战略意义**：
- 对标 A2A #1672（Ed25519 互操作性 PR 持续活跃）先发制人
- Show HN pitch：「零配置 P2P Agent 通信，默认 Ed25519 身份验证，一行启动」

---

### ✅ v2.86（完成 — 2026-04-08，开发轮 + 测试轮）
**主题：Show HN 发布冲刺 — README polish + Show HN 稿件最终版 + BUG-031 修复**

| 特性 | 优先级 | 状态 | Commit | 说明 |
|------|--------|------|--------|------|
| Show HN draft v2.86 全面更新 | P0 | ✅ | `4bd71d3` | Ed25519 default-on 角度重写；A2A #1672 更新至 403 评论；v2.85 测试数 1092；删除过时 v3.0.0 内容 |
| README A2A 对比表 — 评论数更新 | P0 | ✅ | `4bd71d3` | #1672: 62→403 comments (2026-04-08 实测) |
| BUG-031 修复：test_cs10 适配 v2.85 | P2 | ✅ | `11c5eb4` | v2.85 Ed25519 default-on 导致 CS10 测试预期过时；改用 `--no-identity` 逃生舱；11/11 PASS |
| 竞品扫描报告 2026-04-08 | P1 | ✅ | `c9c48ba` | A2A v1.0.1 bugfix-only；#1672 仍 open（403 评论）；SLIMRPC 新提案 |
| Hacker News 发布 | P0 | ⏳ 待批准 | — | 等 Stark 先生 review + 2-Agent demo 录制 |

**测试结果**：场景 A+B+F+G+H 全部 PASS；card_signature 11/11；identity 全套通过

### ✅ v2.87–v2.95（完成 — 2026-04-08 至 2026-04-10）
**主题：信任基础设施深化 — 身份、治理、反操控**

> 最后更新：2026-04-10（v2.95 skill-scoped trust scores 完成）

| 版本 | 主题 | 关键交付 | Commit |
|------|------|---------|--------|
| v2.87 | 协议绑定兼容性 | `GET /protocol-binding/compatibility` — A2A/ANP/MCP 兼容性声明；JSON-RPC 2.0 子集支持 | — |
| v2.88 | 身份跨协议 | `GET /identity/cross-protocol` — multi-DID 跨协议身份声明；OpenID Connect 桥接评估 | — |
| v2.89 | WTRMRK 证明 | `POST /wtrmrk/attest` — WTRMRK 证明提交；A2A #1716 @64R3N 对齐 | — |
| v2.90 | 卡片验证 | `POST /identity/verify-card` — 离线跨实例 AgentCard 验证（无 CA，无网络）| — |
| v2.91 | 对抗性夹具 | `GET /ir/adversarial-fixtures` — 5 个对抗场景 fixture（AF-001~005）；A2A #1718 aeoess 提案对齐 | — |
| v2.92 | RFC-003 治理元数据 | `GET /governance-metadata` — `derivation_rights` + `credential_lifecycle`；A2A #1717 + aeoess SDK v1.37.0 对齐；16测试GM01-16全通 | — |
| v2.93 | RFC-004 无CA身份 | `docs/rfc/identity-without-ca.md` — Ed25519 自签名，三层信任模型，9维 vs CA 对比，multi-provider DID；A2A #1712 社区草稿 | `f384752` |
| v2.94 | 主体多样性防御 | `GET /trust/bilateral-ir/diversity` — 共谋对惩罚（concentration>60%→0.10x权重）；`principal_diversity_defense: true`；16测试PD01-16全通 | `b9f638e` |
| v2.95 | Skill 信任评分 | `_compute_skill_trust_scores()` + `GET /trust/skill-scores` + QuerySkill `skill_trust_score` + `governance_metadata.trust_scores` dict；`skill_scoped_v1` 算法；16测试SS01-16全通 | `070e0d3` |

**当前版本**: `3.11.0` | **最新 commit**: `a4b31ca`

> 版本演进：v2.95 → v3.0（NAT Auto-Traversal, 2026-03-28）→ v3.1–v3.6（签名/安全系列, 2026-04-11）→ v3.7（CI压测+Authorization Hook）→ v3.8（heartbeat-agent三件套）→ v3.9（topic Pub/Sub, A2A #1196 首实现）→ v3.10（multi-relay federation）→ **v3.11（async task queue workers）**

---

### 🔮 v2.96（候选，目标：2026-04-15）
**主题：Show HN 发布 + 2-Agent demo**

| 候选特性 | 优先级 | 状态 | Commit | 说明 |
|---------|--------|------|--------|------|
| 2-Agent demo 终端录屏 | P0 | ✅ 已完成 | `f940cb9` / `64b7106` | `demos/two_agent_demo.sh` + `.cast` + `.gif` (98K) + `.svg` (34K) |
| README demo gif 嵌入 | P1 | ✅ 已完成 | `64b7106` | 首屏 tagline 下方嵌入；版本徽章 v2.95；测试数 1637 |
| Hacker News 发布 | P0 | ⏳ 待批准 | — | 最佳时间：周一/周二早 9-10 AM ET；需 Stark 先生最终批准 |
| A2A #1712 评论发布 | P1 | ⏳ 待发布 | — | `docs/community/a2a-1712-comment.md` 草稿已就绪 |
| BUG-007/BUG-009/BUG-003b 修复 | P1 | ⏳ 待处理 | — | 三个 P1 bug 积压，需在 Show HN 前清理 |

---

### 🔮 v0.9（规划中，目标：2026-06）
**主题：协议健壮性 + 开发者体验**

> 来源：2026-04-03 研究轮 A2A v1.0 扫描 Action Items + 技术债清理

| 特性 | 优先级 | 状态 | Commit |
|------|--------|------|--------|
| `datetime.utcnow()` → timezone-aware 迁移（Python 3.12 废弃警告） | P1 | ✅ 已完成 | 7b53401 |
| `GET /tasks` 分页参数（`page_size` / `after` / `status` 过滤对齐 A2A v1.0） | P1 | ✅ 已完成 | cd958d7 |
| AgentCard `capabilities` 字段重组（对齐 A2A v1.0 `AgentCapabilities` 结构） | P2 | ✅ 已完成 | 255ed59 |
| spec/transport-spec.md 独立文档（L1 传输层从 core spec 正式分离） | P2 | ✅ 已完成 | v0.4，§8 priority/delivery_ack，§10 capabilities.groups.transport，§11 tasks_pagination |
| OAuth 2.0 PKCE 评估文档（ACP 轻量替代方案分析） | P3 | ✅ 已完成 | spec/auth-evaluation.md，决策：不采用，理由：P2P拓扑不兼容AS+三级轻量替代方案已覆盖 |

**设计约束**（不动摇）：
- 不引入中心注册表
- 不强制 OAuth（评估文档只是分析，不实现）
- 不引入 gRPC（保持 HTTP/WS 兼容性）
- `datetime` 迁移必须 backward compatible（不改 API 输出格式）

---

### 🔮 v1.0（规划中，目标：2026-09）
**主题：生产就绪 — 稳定性、互操作性、开发者生态**

> 来源：2026-04-04 研究轮（v0.9 完成后规划）+ A2A #1672/#1628 持续观察

| 特性 | 优先级 | 状态 | 说明 |
|------|--------|------|------|
| SDK 多语言支持（Python 稳定版 + TypeScript MVP） | P1 | ⏳ 待开发 | acp_relay.py 已是参考实现，需正式发布 pip/npm 包 |
| `GET /.well-known/acp.json` 标准化（RFC 8615 对齐） | P1 | ✅ 已完成 | v2.47，`_json_well_known()` 新增 Cache-Control/Vary/X-Content-Type-Options；覆盖 acp.json/did.json/jwks.json；WH1-10 = 10/10 |
| spec/core-v1.0.md 升版同步 | P1 | ✅ 已完成 | v2.47，Status=Stable，§5.3.1 capabilities.groups，§8.7 新增3条MUST+4条SHOULD，版本历史v2.7-v2.47，commit e9bcb1f |
| AgentCard `identity` 字段正式规范化 | P2 | ✅ 已完成 | identity-v2.0.md (Stable)：Ed25519+CA hybrid §2, JWKS §3.2, trust.signals §5, capabilities.groups.identity §6, Conformance §9，commit 04fe33d |
| `trust.signals[]` 枚举值最终确认 | P2 | ✅ 已完成 | v2.70 (2026-04-07): A2A #1628 @douglasborthwick 布林层设计确认；12 种 type 名称最终稳定；新增 severity+category 元数据字段；TRUST_SIGNAL_SCHEMA 常量；commit 12bbbdd |
| CHANGELOG.md 自动生成（git log → 结构化） | P3 | ✅ 已完成 | v2.47.1，`scripts/gen_changelog.py`（Conventional Commits → 结构化条目，支持 `--since`/`--dry-run`/`--version`），commit 07a34c0 |
| 兼容性测试矩阵（跨版本 AgentCard 互操作） | P3 | ✅ 已完成 | `docs/compatibility-matrix.md`：6版本矩阵、逐字段兼容表、连接矩阵、降级规则、升级路径，commit 见下 |
| **Per-Peer Structured Trust Score** `GET /peers/<id>/trust` | P2 | ✅ 已完成 | v2.34，五维度加权信任评估（card_sig/did/ping/history/vouch），commit 2026-04-02 |
| **Delivery ACK** `acp.delivered` frame | P2 | ✅ 已完成 | v2.35，消息投递确认帧，自动发送，commit 2026-04-02 |
| **Read Receipt** `acp.read` frame | P2 | ✅ 已完成 | v2.36，已读回执帧，`/message:send` 自动触发，commit 2026-04-02 |
| **Typing Indicator** `POST /message:typing` | P3 | ✅ 已完成 | v2.37，打字状态指示，`capabilities.typing_indicator: True`，commit 2026-04-02 |
| **Long Poll `/recv`** `?wait=<N>` | P1 | ✅ 已完成 | v2.39，长轮询支持，最大等待 30s，避免空轮询，commit 2026-04-03 |
| **Message Priority** `priority` field | P1 | ✅ 已完成 | v2.38，critical/high/normal/low 四级，`/recv` 按优先级排序，commit 2026-04-03 |
| **AgentCard `agent_limitations`** field | P2 | ✅ 已完成 | v2.40，运行时能力限制声明（rate_limit/offline/maintenance），commit 2026-04-03 |
| **GET /skills OpenAPI 3.1 spec** | P2 | ✅ 已完成 | v2.41，技能 OpenAPI 规范发现端点，commit 2026-04-03 |
| **Ed25519 Identity integration tests** | P1 | ✅ 已完成 | v2.42，身份系统集成测试套件，commit 2026-04-03 |
| **h2c graceful skip** BUG-050 | P2 | ✅ 已完成 | v2.43，HTTP/2 cleartext 不可用时优雅降级，commit 2026-04-03 |
| **GET /tasks pagination** `page_size/after/status` | P1 | ✅ 已完成 | v2.45，对齐 A2A v1.0 Tasks List，commit 2026-04-04 |
| **AgentCard capabilities groups** 重组 | P1 | ✅ 已完成 | v2.46，messaging/tasks/identity/transport/discovery 分组，对齐 A2A v1.0 AgentCapabilities，commit 2026-04-04 |
| **GET /peers/<id>/messages** per-peer 消息历史 | P1 | ✅ 已完成 | v2.48，direction/since_seq/sort/pagination，`--test-mode` 调试注入，PMH1-10=10/10，commit 7bada9f |

**设计约束**（不动摇）：
- 保持 P2P 优先，relay 仅作 fallback
- SDK 不引入强依赖，保持"单文件可运行"精神
- spec 升版必须向后兼容（无 breaking change）
- 生产就绪不意味着企业化（OAuth/多租户不在 v1.0 范围）

---

## 签名安全版本路线图（v3.x 系列）

### ✅ v3.0 — Message Signature（2026-03-28）
- `msg_sig`：每条消息的 Ed25519 per-message 签名
- `POST /verify/message` 第三方验证端点
- `capabilities.msg_sig: true`

### ✅ v3.1 — Origin Proof（2026-04-11）
- `origin_proof`：绑定接收方 peer_id 的 Ed25519 签名，防消息重放攻击
- `capabilities.origin_proof: true`；向后兼容（`to=""` 退回 v3.0 canonical）

### ✅ v3.2 — W3C DataIntegrityProof（2026-04-11）
- `_build_proof_object()` 输出标准 `Ed25519Signature2020` proof 对象
- 出站消息并存 `msg_sig`（ACP 原生）+ `proof`（W3C 格式）双字段
- `POST /verify/proof`：W3C 格式验证端点
- `capabilities.data_integrity_proof: true`
- 对标 ANP DataIntegrityProof（2026-04-10 落地）；DIP-01–DIP-06 = 6/6

### ✅ v3.3 — Capability Token & OBO Authorization（2026-04-11）
- `capability_token` 可选字段透传：A2A #1716 SINT Protocol Ed25519 格式，relay 不验证直接转发
- `POST /capability/issue`：本地辅助端点，使用 relay 身份私钥签发 `Ed25519CapabilityToken`
- `origin_proof` OBO 扩展字段：`principal_id`、`operator_id`、`governance_framework_ref`（A2A #1713 对齐）
- `capabilities.capability_token: true`；CT-01–CT-06 = 6/6
- 修复：`origin_proof` 构建时机 bug（CT-06 回归）
- 完全向后兼容

### ✅ v3.4 — AgentCard Governance Block（2026-04-11）
- **`AgentCard.governance`**：`/status` 新增顶层治理对象，包含 `framework`、`version`、`credential_lifecycle`（`ttl_seconds`/`revocation_endpoint`/`credential_ttl_seconds`）、`audit_mode`、`policy_ref`
- `credential_lifecycle.ttl_seconds` 默认 3600（1h）；`audit_mode` 支持 `static`（声明式）和 `live`（未来 REST 扩展）
- 完全向后兼容；对齐 A2A #1717 `CredentialLifecyclePolicy`

### ✅ v3.5.0 ✅ 已完成 — 2026-04-11
- **`governance.proof_suite`**（eddsa-jcs-2022 互操作）：声明节点支持的签名套件（`Ed25519Signature2020`、`eddsa-jcs-2022`），含 W3C 互操作引用
- **`transport_bindings.experimental`**（SlimRPC 扩展口预留）：AgentCard 新增 `transport_bindings` 字段，`supported: ["http","websocket"]` + `experimental: []` 扩展口
- `capabilities.transport_bindings: true`；CLI `--experimental-transport` flag
- 测试：V35-01–V35-06 = 6/6 PASS

## v3.6.0 ✅ 已完成 — 2026-04-11
- BUG-007 P1 修复：multi-peer 发送歧义
- BUG-009 P1 修复：SSE 推送延迟 <50ms
- BUG-003b P1 修复：重复连接幂等

## v3.7.0 ✅ 已完成 — 2026-04-12
- **CI 压力测试 + Authorization Hook**: `test_scenario_d.py` local-relay 20-msg burst（P99 latency assertion，全 CI-safe）；`_check_authorization()` stub 预留（A2A #1716 watchlist）
- 测试：48 tests PASS

## v3.8.0 ✅ 已完成 — 2026-04-12
- **Heartbeat-Agent 三件套闭环（A2A IS#1667）**: `GET /offline-queue/summary`（轻量 polling 端点）；`--heartbeat-agent` CLI 标志（implies `--local-only` + `availability.mode=heartbeat`）；`capabilities.heartbeat_agent`
- 测试：HA1–HA8 = 8/8 PASS

## v3.9.0 ✅ 已完成 — 2026-04-12
- **Topic-based Pub/Sub subset（A2A #1196 对标）**: `POST /peers/subscribe/{topic}`、`POST /peers/unsubscribe/{topic}`、`POST /peers/broadcast/{topic}`、`GET /peers/topics`；`capabilities.topic_broadcast: true`
- A2A #1196 首个工作参考实现（上游仅 proposal，无实现）
- 测试：TP1–TP10 = 10/10 PASS

## v3.10.0 ✅ 已完成 — 2026-04-12
- **Multi-relay Federation（跨 relay 实例消息路由）**: `GET /federation`、`POST /federation`（idempotent）、`POST /federation/route`；`acp.federation.route` WS 消息处理；offline-queue fallback 组合；`capabilities.federation: true`
- Commit: `68bf6f6`
- 测试：FED1–FED12 = 12/12 PASS

## v3.11.0 ✅ 已完成 — 2026-04-12
- **Async Task Queue Workers**: `POST /tasks/queue/worker`（注册 callback_url + peer_id/skill_id 过滤器，幂等）、`GET /tasks/queue/workers`（列出 workers + stats）、`DELETE /tasks/queue/worker/{id}`（注销）；入队自动派发；`capabilities.task_queue_worker: true`
- 修复 filter 逻辑 bug：worker 有 peer_id 过滤器时，无 from_peer_id 的任务不应被派发
- Commit: `a4b31ca`
- 测试：TQW1–TQW12 = 12/12 PASS

## v3.12.0 候选特性
- **P1**: Governance metadata block（A2A #1717，Microsoft AGT 团队）— `trust_score`、`capability_manifest`、`policy_compliance`、`audit_trail_reference`；ACP 现有覆盖 ~60%，扩展 `bilateral_proof` 支持
- **P2**: Bilateral Signed Interaction Records（A2A #1718）— 双边签名交互记录，统一 trust/audit/delegation/Sybil-resistance
- **P3**: SlimRPC CPB 实验性绑定（跟踪 A2A #1723）
