# ACP 协议研发路线图

> 持续更新。贾维斯每周自动扫描竞品动态，每月产出一个新版本。  
> 最后更新：2026-04-06 15:20（开发轮 #17：v2.65.0 完成；IE-1..20 PASS，BUG-052 修复，843 全量回归；当前版本 v2.65.0，commit c5e53e3）

---

## 战略定位（2026-03-19 Stark 先生确认）

| 特性 | 含义 | 设计原则 |
|------|------|---------|
| **① 轻量级，简单开箱即用** | 最小化接入成本，无需学习曲线 | 单文件 Skill，一个命令即运行 |
| **② P2P 无中间人** | Agent 直连，不经过任何第三方 | Relay 只做连接打洞，消息直通 |
| **③ 实用性，任意 Agent 可接入** | 不限框架、平台、语言 | curl 可接入，3 个端点最小集 |
| **④ 面向个人和团队** | 对标 A2A 企业级，做个人/小团队场景 | 零运维、零注册、即用即走 |
| **⑤ 标准化** | 像 MCP 标准化 Agent↔Tool，ACP 标准化 Agent↔Agent | 开放规范，任意实现可互通 |

> **口号：MCP 标准化了 Agent 与 Tool 的通信，ACP 标准化 Agent 与 Agent 的通信。**

---

## 竞品生态现状（更新：2026-03-29）

| 协议 | Stars | 活跃度 | 定位 | 身份认证 | 态度 |
|------|-------|--------|------|----------|------|
| **ACP** (本项目) | — | ✅ 持续开发 | 轻量 P2P Agent 通信 | ✅ Ed25519+`did:acp:` DID（v1.3，**领先 A2A 2-3 月**） | — |
| **A2A** (a2aproject) | 22,643+ | ✅ 活跃 | 企业级 Agent 总线 | 🔴 Issue #1672 讨论中（未合并）| 借鉴概念，不复制复杂度；**仓库已从 google/ 迁移到 a2aproject/** |
| **ANP** (社区) | 1,240 | 🔴 已归档 | 去中心化身份 | ✅ 理论设计（停更）| 停更，不再追踪 |
| **IBM ACP** | 966 | 🔴 停更 | 多模态消息 | ❌ 无 | 参考即可 |
| **MCP** (Anthropic) | — | ✅ 稳定 | 工具调用 | ❌ 无 | 不同赛道，可互补 |

### ACP 差异化领先点（2026-04-06 更新）

| 功能 | ACP | A2A | 领先方 |
|------|-----|-----|--------|
| Agent 身份认证（Ed25519/DID） | ✅ v1.3 已实现 | 🔴 #1672 讨论中（未合并）| **ACP 领先 ~2 月** |
| `limitations` 结构化字段 | ✅ v2.20(LimitationObject[]) + **v2.21 运行时PATCH+过滤** | 🔴 #1694 提案未合并 | **ACP 领先（stable/runtime 分离 + 动态更新 + 过滤查询）** |
| WebSocket 原生推送 | ✅ v2.12 已实现 | 🔴 #1029 提案中 | **ACP 领先** |
| **事件回放 `?since=<seq>`** | ✅ **v2.13 已实现** | ❌ 无 | **ACP 领先（首创）** |
| **`trust.signals[]` 结构化信任证据** | ✅ **v2.14 已实现** | ❌ #1628 仍在提案 | **ACP 领先** |
| **`GET /context/<id>/messages`** | ✅ **v2.15 已实现** | ❌ 无 | **ACP 首创** |
| **`delegation_chain` 身份委托链** | ✅ **v2.16 已实现** | ❌ #1696 Future Considerations | **ACP 首创** |
| **`availability.schedule` CRON 调度** | ✅ **v2.17 已实现** | ❌ #1667 heartbeat 仍在提案 | **ACP 首创** |
| **`/.well-known/jwks.json` JWKS 密钥发现** | ✅ **v2.18 已实现（RFC 7517/8037）** | ❌ IS#1628 仍在提案阶段 | **ACP 领先** |
| **`capability_token` SINT-format 能力令牌** | ✅ **v2.57 已实现（POST /skills/{id}/capability-token + T0-T3 enforcement gate）** | ❌ #1716 提案讨论中 | **ACP 抢先实现** |
| **`effective_tier` 三因子动态计算** | ✅ **v2.58 已实现（max(tier_rule, depth_floor, rep_adj)）** | ❌ #1716 @64R3N 公式未合并 | **ACP 抢先实现** |
| **`interaction_records` 双边交互记录** | ✅ **v2.59 已实现（relay_signature + caller_token_hash + sha256 链）** | ❌ #1718 0💬 时 ACP 已发布 | **ACP 抢先实现** |
| **`governance_metadata` 治理元数据** | ✅ **v2.60 已实现（trust_score + capability_manifest + GET/PATCH endpoints + CLI）** | ❌ #1717 0💬（Microsoft 提案）时 ACP 已发布 | **ACP 抢先实现** |
| **`caller_signature` 完整双边签名** | ✅ **v2.61 已实现（Ed25519 caller_sig + bilateral=true 语义 + CS-1..12 PASS）** | ❌ #1718 外部评论指出 unilateral 弱点，ACP 先于 spec 完成实现 | **ACP 抢先实现** |
| **`wtrmrk_sequence_root` 外部 attestation** | ✅ **v2.62 已实现（Factor 4 + asymmetric safety rule + WA-1..14 PASS）** | ❌ #1716 @64R3N 建议时 ACP 已发布完整实现 | **ACP 抢先实现** |
| **跨协议 token 验证** | ✅ **v2.63 已实现（GET /identity/did-key + POST /verify/external-token，7步验证流水线，ETV-1..16 PASS）** | ❌ #1713 SINT↔APS 互验发布时 ACP 已完整兼容，零代码修改 | **ACP 抢先实现** |
| `tasks/list` 分页过滤 | ✅ v2.11 | ✅ v1.0.0 | 持平（ACP 超前实现）|
| Python SDK | ✅ v1.7+ | 🟡 v1.0.0-alpha.0 | 版本号差距，ACP 更轻量 |

---

## 版本路线图

### ✅ v0.4（完成，2026-03-18）
- P2P Relay 直连（本地守护进程）
- SSE 流式端点
- AgentCard 能力声明（基础版）
- 安全加固（Unbounded Consumption 防护）

---

### ✅ v0.5（完成，2026-03-19，提前于截止日 2026-03-26）
**主题：消息结构化 + 任务追踪**

- ✅ Task 状态机（5 种：submitted/working/completed/failed/input_required）
- ✅ 结构化消息 Part 模型（text/file/data）
- ✅ 消息幂等性（message_id 客户端生成 + server_seq 有序）
- ✅ QuerySkill() API（`POST /skills/query`）
- ✅ AgentCard 标准发现端点（`GET /.well-known/acp.json`）
- ✅ 双向 Task 同步（`spec/core-v0.5.md` §5b）

Key commit: `bb6aba3`

---

### ✅ v0.6（完成，2026-03-19）
**主题：外部 Agent 接入 + 多 session Relay + 错误码规范**

- ✅ 轻量接入规范（`spec/v0.6-minimal-agent.md`）：3 端点最小集
- ✅ 多 session peer 注册表（`/peers`, `/peer/{id}/send`, `/peers/connect`）
- ✅ 标准错误码（6 种 ERR_* 常量 + `_err()` 辅助函数，`spec/error-codes.md`）
- ✅ 自动降级策略（P2P 超时 10s → HTTP 公共中继，commit `74de528`）
- ✅ Cloudflare Worker v2（多房间并发 + KV 过期清理）
- ✅ Python mini-SDK（`sdk/python/`）

Key commit: `c816cb5`（错误码）

---

### ✅ v0.7（完成，2026-03-20）
**主题：安全扩展 + LAN 发现 + 多轮上下文**

- ✅ 可选 HMAC-SHA256 消息签名（`--secret`，`spec/transports.md` §3.x）
- ✅ mDNS LAN 对等发现（`--advertise-mdns`，UDP 224.0.0.251:5354）
- ✅ context_id 多轮对话支持
- ✅ `spec/transports.md` v0.3（§3.6 HTTP headers 分类澄清）

Key commits: `87dad51`（HMAC），`aabfae5`（mDNS），`68db641`（spec）

---

### ✅ v0.8（完成，2026-03-21）🎉
**主题：生态扩展 + 可选 Ed25519 身份**

所有 P0 目标 **全部完成**：

- ✅ **Node.js SDK**（`sdk/node/`）：零依赖，TS 类型，19 单元测试通过（commit `fd8c02a`）
- ✅ **兼容性测试套件**（`tests/compat/`）：7 个测试文件，黑盒 HTTP 验证，`ACP_BASE_URL` 参数化（commit `98197cf`）
- ✅ **Ed25519 可选身份扩展**（commit `1a13dec`）：
  - 自主权密钥对（`~/.acp/identity.json`，chmod 0600）
  - canonical JSON 签名，出站自动附加 `identity` 块
  - 入站 warn-only 验证（不丢弃），向后兼容 v0.7
  - `--identity [path]` CLI 标志
  - `spec/identity-v0.8.md` 完整规范（230 行，含 APS 对比）
- ✅ VERSION：`0.7-dev` → `0.8-dev`

Deferred to v0.9: `spec/core-v0.8.md` 综合规范文档（P2）

---

### ✅ v0.9（完成，2026-03-21）
**主题：规范整合 + 分发就绪 + 生产可用性**

- ✅ `spec/core-v0.9.md` 综合规范文档（v0.5–v0.8 统一整合）
- ✅ `role` 字段服务端强校验（缺失/非法 → 400 ERR_INVALID_REQUEST）
- ✅ `pip install acp-relay`（`pyproject.toml` + `acp-relay` CLI 入口）
- ✅ `npm install acp-relay-client`（ESM + CJS + TypeScript types）
- ✅ CLI 扩展：`--version`、`--verbose`、`--config <FILE>`（JSON/YAML，stdlib）
- ✅ 63 个单元测试（`tests/unit/`）
- ✅ 7 个兼容性测试套件（`tests/compat/`）

---

### ✅ v1.0（完成，2026-03-21）🎉 GA
**主题：生产稳定版**

- ✅ `spec/core-v1.0.md`——权威 1.0 规范
  - `[stable]` 13 个端点 · `[experimental]` 1 个（`/discover`）
  - §13：v1.0 兼容性保证（4 条 MUST 级要求）
- ✅ 安全审计（`docs/security.md`）
  - HMAC-SHA256 + Ed25519 正式审计：11 PASS · 1 PARTIAL（replay-window，v1.1 修复）
- ✅ **Go SDK**（`sdk/go/`）——stdlib only，Go 1.21+，零外部依赖，24 个测试
  - 包名：`acprelay`，8 个方法：Send/Recv/GetStatus/GetTasks/CancelTask/QuerySkills
  - `httptest.Server` 真实 HTTP round-trip 测试
- ✅ **端到端集成测试**（`tests/integration/`）——30 个测试，真实 relay 子进程
- ✅ **CHANGELOG**——完整版本历史 v0.1.0 → v1.0.0
- ✅ **README v1.0**——版本徽章、v0.9/v1.0 特性节、Go SDK 示例、集成测试说明

Key commits: `bcf6b75`（Go SDK）, `641bae6`+`81bc73c`（集成测试）, `a97b2bd`（README v1.0）

**总测试数：97（30 集成 + 63 单元 + 4 新增）**

---

### 🔧 v1.1 Backlog（持续迭代）

- ✅ **场景测试里程碑（2026-03-23）——真实多 Agent 通信验证**
  - 场景A（2026-03-22）：双 Agent P2P 通信，发现并修复 BUG-001~006 (commit `643450c`)
  - 场景B（2026-03-23）：Orchestrator→Worker1+Worker2，发现 BUG-007/008，修复后 5/5 ✅
  - 场景C（2026-03-23）：A→B→C→A 环形流水线，8/8 全绿 ✅（同步修复 BUG-007 part2, commit `638f778`）
  - 遗留：BUG-009 SSE 延迟 ~950ms（P1，threading.Event 方案已设计，待下个修复轮）
- ✅ `failed_message_id` 覆盖所有 /message:send 错误码（commit `e281790`，2026-03-21）
  - 灵感：ANP commit 99806f45（failed_msg_id in e2ee_error）
  - 覆盖：ERR_INVALID_REQUEST × 4 + ERR_NOT_CONNECTED + ERR_INTERNAL
- ✅ replay-window：HMAC 重放攻击防护（PARTIAL → PASS）（commit `e263f52`，2026-03-22）
- ✅ Docker 官方镜像（commit `9d590a7`，2026-03-22）
- ✅ DID 身份（`did:acp:<base64url(pubkey)>`，commit pending，2026-03-22）
  - _pubkey_to_did_acp()，AgentCard identity.did 字段，capabilities.did_identity 标志
  - GET /.well-known/did.json（W3C DID Document，Ed25519VerificationKey2020 + ACPRelay service）
  - 14 个新单元测试
- ✅ **`GET /tasks` 时间窗口过滤器**（commit `a187471`，2026-03-24）
  - `created_after=<ISO-8601>` + `updated_after=<ISO-8601>` 新查询参数
  - 可与 state/peer_id/cursor/sort 组合使用
  - 修复 BUG-014：`peer_id` 过滤失效（payload 嵌套层级问题）
  - 灵感：A2A v1.0.0 `tasks/list` `last_updated_after`（scan #4）
  - Tests: 6/6 PASS（tests/test_tasks_filtering.py）
- ✅ **v1.4 NAT traversal signaling layer**（commit `8c162d4`，2026-03-24）
  - Cloudflare Worker v2.1：`GET /acp/myip`、`POST /acp/announce`、`GET /acp/peer?token=`
  - Python signaling helpers（stdlib-only）：`_relay_get_public_ip` / `_relay_announce` / `_relay_get_peer_addr`
  - Privacy-first：ephemeral 30s 记录，one-time-read 自删除，无持久地址存储
  - 22/22 tests PASS（test_nat_signaling.py）
- ✅ **v1.5 hybrid identity**（2026-03-24）
  - `--ca-cert` 选项：`identity.scheme: ed25519+ca`，CA 证书混合信任
  - Java SDK（commit `28813ed`）
  - 6/6 tests PASS（test_v15_hybrid_identity.py 直接运行）
- ✅ **v1.5.2 cancel 语义明确化**（commit `0d19a11`，2026-03-25）
  - `spec/core-v1.3.md` §10：Task Cancel Semantics 新章节
  - cancel 同步即时：一次调用返回 `canceled`，无 async/deferred 机制
  - cancel 幂等：已取消任务再次 `:cancel` 返回 200
  - 新错误码：`ERR_TASK_NOT_CANCELABLE` (409) 用于 terminal 状态任务
  - 差异化文档：与 A2A #1680（async cancel 无结论）形成鲜明对比
- ✅ **v1.7 Python SDK RelayClient 升级**（commit `00e4a09`，2026-03-25 18:36）
  - `tasks()` v1.4 时间窗口过滤（created_after/updated_after/peer_id/sort/cursor/limit）
  - `cancel_task()` v1.5.2 §10 幂等语义（raise_on_terminal 选项）
  - 新方法：`capabilities()` / `identity()` / `did_document()`
  - AsyncRelayClient 同步升级
  - 新测试：`test_relay_client_v17.py` 10/10 PASS
- ✅ **v1.6 HTTP/2 传输绑定**（commit `cf578e3`，2026-03-25）
- ✅ **v1.8 AgentCard 自签名**（commit `fe80ea4`，2026-03-26）
  - `_sign_agent_card()`: Ed25519 私钥在 serve time 签名整张 AgentCard，result → `identity.card_sig`
  - `_verify_agent_card()`: 验证任意 AgentCard，返回 `{valid, did, did_consistent, error}`
  - `GET /.well-known/acp.json`: 启用 `--identity` 时自动附加 `card_sig`
  - `GET /verify/card`: 本地自验端点
  - `POST /verify/card`: 验证任意外部 AgentCard（raw 或 wrapped 形式）
  - `capabilities.card_sig` + `endpoints.verify_card` 字段
  - CS1-CS10: 11/11 PASS；全回归 219 passed, 3 skipped, 0 failed
  - **动机**：A2A issue #1672（62 评论，3 个第三方实现竞争，无合并）——ACP 直接补齐，无 CA，无注册服务
- ✅ **v1.9 Peer AgentCard 自动验证**（commit `97b6128`，2026-03-26）
  - `acp.agent_card` 收到即自动调用 `_verify_agent_card()`，结果写 `_status["peer_card_verification"]`
  - `_send_agent_card()` 整合 v1.8：发送前签名，peer 收到即可验证
  - `GET /peer/verify`：返回 `{peer_name, peer_did, verified, did_consistent, scheme, error}`；无 peer 时 404
  - `capabilities.auto_card_verify: true` + `endpoints.peer_verify: "/peer/verify"` 声明
  - 断连时清理 `peer_card_verification`（host+guest 两路径都覆盖）
  - PV1–PV8：7/8 PASS（PV5 sandbox-skip）；全回归 226 passed, 4 skipped, 0 failed
  - **完整身份故事**：v1.8 签自己的 card + v1.9 连接时自动验对方 card = 握手即完成双向身份验证，零额外调用
  - `--http2` CLI 标志：启用 h2c（HTTP/2 cleartext，无需 TLS）
  - 实现：`_ThreadingH2Server` + `_H2Handler`（纯 `h2` 状态机，独立于 main thread）
  - `capabilities.http2: true/false` 广播给对端 AgentCard
  - 全桥接：h2 frames ↔ HTTP/1.1 wire format ↔ LocalHTTP 路由逻辑（零路由改动）
  - Graceful fallback：`h2` 库缺失时自动降级 HTTP/1.1 + warning log
  - 新测试：`tests/test_http2_transport.py`（6 场景 H1-H6，原始 h2c socket 验证）
  - 全套回归：**12/12 ✅**（含新 HTTP/2 测试）
- ✅ Rust SDK stub（sdk/rust/，commit pending，2026-03-22）
  - lib.rs：RelayClient, MessageRequest, AgentCard, AvailabilityPatch, RelayStatus + 10 structs/enums
  - 全部 API：send_message / agent_card / patch_availability / status / link / ping
  - 8 单元测试，Cargo.toml 含 reqwest 0.12 (blocking+rustls) + serde + thiserror
  - README.md 含完整使用说明、API 参考表、类型参考表

### 🔮 v1.2 规划（目标：2026-Q2）
**主题：Heartbeat Agent 支持 + 生态完善**

灵感来源：A2A issue #1667（2026-03-21），A2A 协议层尚无此能力，ACP 可率先实现。

- ✅ **AgentCard `availability` 块**（P1）——heartbeat/cron 型 Agent 可用性元数据（commit `c10c230`，2026-03-22）
  - `mode`: persistent / heartbeat / cron / manual
  - `interval_seconds`: 心跳间隔（秒）
  - `next_active_at` / `last_active_at`: ISO-8601 UTC 时间戳
  - `task_latency_max_seconds`: 最大预期延迟
  - 全部可选字段，向后兼容 v1.0
- ✅ AgentCard 自动更新 API：PATCH `/.well-known/acp.json`（P2）（commit `cd67181`，2026-03-22）
- ✅ Rust SDK stub（sdk/rust/，P2，commit pending，2026-03-22）

---

### ✅ v2.4（完成，2026-03-28~29）
**主题：Node.js SDK 完善 + WebSocket 原生支持**

- ✅ Node.js SDK v2.4：`tasks/cancel` + `capabilities()` API（commit `c6afb91`，2026-03-28）
- ✅ `GET /ws/stream`：WebSocket 原生消息推送端点（commit `1de1a96`，2026-03-29）
  - RFC 6455 握手，ThreadingHTTPServer worker 模式
  - `capabilities.ws_stream: true` + `endpoints.ws_stream: "/ws/stream"`
  - WS2/WS3 根因修复（proxy bypass + acp.peer 过滤），5/5 PASS（commit `e60c6fa`，2026-03-29）
- ✅ 全套测试 0 failed 保持（快速回归 17 passed in 31.47s）

---

### ✅ v2.16（完成，2026-03-29）
**主题：签名委托链（delegation_chain）**

- ✅ `_build_delegation_entry()`: Ed25519 签名委托记录（canonical JSON payload）
- ✅ `_verify_delegation_entry()`: 从 `did:acp:` 提取公钥，零注册表验证
- ✅ `_delegation_chain_status()`: 链摘要 + 过期标记
- ✅ `POST /identity/delegate`: 创建委托，按 delegator_did 去重
- ✅ `GET /identity/delegation`: 查询链状态
- ✅ `POST /identity/delegation/verify`: 验证任意委托条目
- ✅ AgentCard `identity.delegation` + `capabilities.delegation_chain`
- ✅ 测试：DC1~DC13 **13/13 PASS**（单元 + HTTP 集成）
- **差异化**：A2A #1696 (2026-03-28) 仅将 delegation chain 列为 future work，ACP 率先实现

---

### ✅ v2.15（完成，2026-03-29）
**主题：多轮对话上下文查询（GET /context/<id>/messages）**

- ✅ `GET /context/<context_id>/messages`：按 context_id 查询历史消息
  - params: `limit` (max 200), `since_seq`（增量拉取）, `sort=asc|desc`
  - 返回: `{context_id, messages[], count, total, has_more}`
- ✅ `capabilities.context_query: true` 声明到 AgentCard
- ✅ 测试：8/8 PASS

---

### ✅ v2.14（完成，2026-03-29）
**主题：结构化信任证据（trust.signals[]）**

- ✅ `_build_trust_signals()`: 6 个 signal 类型（commit `06f82cd`，2026-03-29）
  - `hmac_message_signing`、`ed25519_identity`、`agent_card_signature`
  - `peer_card_verification`（始终启用）、`replay_window`、`did_document`
- ✅ `capabilities.trust_signals: true` 声明到 AgentCard
- ✅ 测试：TS1~TS8 8/8 PASS，回归 41/41 PASS 5 SKIPPED
- **差异化**：A2A #1628 提案仍未合并，ACP 率先实现结构化信任证据

---

### ✅ v2.13（完成，2026-03-29）
**主题：断线重连无数据丢失（Event Replay）**

- ✅ `GET /stream?since=<seq>`：SSE 断线重连回放（commit `4aa78ce`，2026-03-29）
  - 立即交付所有 `seq > since` 的历史事件，然后切换为 live 流
  - `_event_log` 环形缓冲区（500 条，线程安全）
- ✅ `GET /ws/stream?since=<seq>`：WebSocket 版本相同语义
- ✅ `capabilities.event_replay: true` 声明到 AgentCard
- ✅ 测试：RP1~RP6 6/6 PASS，快速回归 23/23 PASS
- **Bug fix**：`client.send_ws_text()` → `client.send()`（方法名拼写错误，WS replay 从未执行）
- **差异化**：A2A 完全无此概念，ACP 首创

---

### ✅ v2.5（目标：2026-04，下一里程碑）
**主题：测试稳定性 + ADR 规范化**

- [x] `test_reconnect.py` 完整重写（local relay，无需公网 IP）（✅ BUG-038 已修复，2026-03-30）
- [ ] WS2/WS3 本地 peer 测试（消除 P2P skip）
- [x] `trust.signals[]` 兼容格式（✅ v2.14 已实现，commit `06f82cd`）
- [x] `adrs/` 目录初始化（✅ v2.13 文档轮已完成：ADR-001/002/003 + template）
- [x] JWKS 兼容层（✅ v2.18 已实现：`trust.signals[type=jwks]` + `/.well-known/jwks.json`）
- [ ] 全套测试 0 failed 稳定化

---

### ✅ v2.20（完成，2026-03-31）
**主题：结构化 limitations[] — LimitationObject**

- ✅ `LimitationObject` schema：`kind(capability|modality|scale|domain|access|other)` + `code` + `message` + `permanent`
- ✅ **stable/runtime 分离**：`permanent=true` = 持久约束（路由决策）；`permanent=false` = 运行时降级（重试/降级）
- ✅ `_parse_limitation()` 工具函数：string/dict 统一归一化，invalid kind → `"other"`
- ✅ `--limitations-json` CLI：完整 JSON array 输入，优先级高于 `--limitations`
- ✅ `--limitations` CSV（v2.7 兼容）：string 自动提升为 `LimitationObject`
- ✅ `capabilities.limitations_structured: true` 能力标志
- ✅ 18/18 新测试 + 48/48 回归全 PASS（commit `14831b4`，2026-03-31）
- **对比 A2A IS#1694**：A2A 提案仍在讨论（2026-03-27 开启，未合并）；ACP 已率先发布完整实现

---

### ✅ v2.19（完成，2026-03-31）
**主题：NAT 穿透主流程集成**

- ✅ **`connection_type`** 字段集成到 `/status` + `/peers/connect` 响应
  - 值：`"host"` (默认) | `"p2p_direct"` | `"dcutr_direct"` | `"relay"`
  - 三级自动降级：L1直连 → L2 dCUTR打洞 → L3 Relay兜底
- ✅ `availability-cron` CLI 参数（CRON 可直接通过 `--availability-cron` 传入）
- ✅ `test_nat_integration.py` NI1~NI6：6/6 PASS（commit `175e7ad`）
- **对比 A2A**：A2A 无 NAT 穿透策略；ACP 自动三级降级，零手动端口转发

---

### ✅ v2.21（完成，2026-03-31）
**主题：limitations 运行时动态管理**

- ✅ **limitations[] PATCH 支持**（commit `b85a0b9`）
  - `PATCH /.well-known/acp.json {"limitations":[...]}` — 替换整个 limitations 列表
  - `PATCH ... {"limitations":[...], "limitations_merge":true}` — 按 (kind,code) 合并/追加
  - dict 条目 kind 严格校验；纯字符串向后兼容自动提升
  - 可在同一请求中同时 patch availability + limitations
- ✅ **limitations 过滤查询**（commit `b85a0b9`）
  - `GET /.well-known/acp.json?filter_limitations=permanent` — 只返回 permanent=true 条目
  - `GET ...?filter_limitations=transient` — 只返回非永久条目（降级状态感知）
  - `GET ...?filter_limitations=<kind>` — 按 kind 精准过滤
  - 无效 filter 值 → HTTP 400
- ✅ **capabilities 声明**：`limitations_patch=true` + `limitations_filter=true`
- ✅ **13 新测试** LP1-LP13，全部 PASS
- [ ] **Show HN 发布**（P0，待 Stark 先生确认）
  - 草稿：`docs/show-hn-draft.md`（2026-03-25，已更新）
  - 发布时机窗口：✅ 已开启（A2A 规范滞后，ACP 多项特性领先）

### ✅ v2.22（完成，2026-03-31）
**主题：POST /peers/broadcast — 全员广播**

- ✅ **`POST /peers/broadcast`** — 一次调用向所有已连接 peers 广播消息（commit `d396969`）
  - `capabilities.peers_broadcast: true` + `endpoints.peers_broadcast`
  - BC1-BC10: 10/10 PASS

### ✅ v2.23（完成，2026-03-31）
**主题：target_peers[] 子集广播 + 广播历史**

- ✅ **`POST /peers/broadcast` — `target_peers[]` 可选子集广播**（commit `0edd74f`）
  - 指定 peer_id 列表时仅向这些 peer 发送；未知 peer_id → 400；空列表 → 503
  - 响应新增 `broadcast_id` 字段（与 history 关联用）
- ✅ **`GET /peers/broadcast/history`** — 广播审计日志（内存环形缓冲区，最多 200 条）
  - 支持 `?limit=N` 参数；每条记录含 broadcast_id/ts/target_peers/delivered/failed
- ✅ `capabilities.peers_broadcast_subset/peers_broadcast_history` + `endpoints.peers_broadcast_history`
- BH1-BH11: 11/11 PASS；全回归 BC1-10 ✅ + 核心52 ✅

### ✅ v2.24（完成，2026-04-01）
**主题：Peer AgentCard 查询**
- ✅ `GET /peers/<peer_id>/card` — 查询指定 peer 的 AgentCard
  - 从 `_peers[peer_id]` 取已缓存 card；peer 不存在 → 404；card 未交换 → 202
  - capabilities.peer_card_query=true + endpoints.peer_card 声明

### ✅ v2.25（完成，2026-04-01）
**主题：应用层 liveness probe + RTT 测量**
- ✅ `POST /peers/<peer_id>/ping` — 通过 WS 发送 acp.ping，等待 acp.pong，返回 rtt_ms
  - 404/503/408 错误码；可选 body: {"timeout": <float>}
  - 每 peer ping 统计：last_ping_rtt_ms / last_ping_at / ping_count
  - capabilities.peer_ping=true + endpoints.peer_ping 声明
- 测试：PP1–PP10 10/10 PASS（commit 0496a36）
- 修复 BUG-048：test_limitations.py LimitationObject 兼容性（commit 6685a8e）

### ✅ v2.26（完成，2026-04-01）
**主题：QuerySkill constraints 扩展**
- ✅ 每个 skill 对象新增 `constraints` 字段：`{max_file_size_bytes, concurrent_tasks, context_window}`（均可 null 表示无限制）
- ✅ `POST /skills/query` 新增三维 constraint 检查：
  - `max_file_size_bytes`：先检查 relay 级别限制，再检查 skill 级别限制
  - `concurrent_tasks`：检查 skill 级别 concurrent_tasks 上限
  - `context_window`：检查 skill 级别 context_window 上限
- ✅ 响应新增 `skill_constraints_declared` 字段（回显 skill 声明的限制）
- ✅ `capabilities.skills_query_constraints = true`
- ✅ 向后兼容（无 constraints 字段的 skill 全部默认 null，不产生误判）
- 测试：QC1–QC12 12/12 PASS（commit `76534b5`）
- 领先 A2A PR#1655（open 第 5 周）

### ✅ v2.28（完成，2026-04-01）
**主题：Per-skill `limitations[]` 字段（ref A2A #1694）**

- ✅ **每个 skill 对象增加 `limitations: LimitationObject[]`**（与 AgentCard 顶层 schema 一致）
  - 字符串简写自动提升：`"no_audio"` → `{kind:"capability", code:"no_audio", ...}`
  - 声明方式：`--skills '[{"id":"x","limitations":[{"kind":"modality","code":"..."}]}]'`
  - 默认为 `[]`，完全向后兼容
- ✅ **`GET /skills?has_limitation=<kind|code>`** — 按限制类型或代码过滤技能列表
- ✅ **`POST /skills/query`** 响应增加 `skill_limitations_declared[]`
- ✅ **`capabilities.skill_limitations: True`**
- ✅ A2A #1694 互操作对齐（A2A 提案仍未合并）
- 测试：SL1–SL12 = 12/12 PASS；v2.26 回归 33/33 PASS

---

### ✅ v2.27（完成，2026-04-01）
**主题：GET /peers 分页 + vouch_chain trust signal**

- ✅ **`GET /peers` 分页**（P1）：`?limit=N&offset=N&filter=all|connected|disconnected`
  - 响应增加 `pagination{limit,offset,filter,has_more,next_offset}` + `total_filtered` 字段
  - filter=invalid → 400 ERR_INVALID_FILTER；limit=非整数 → 默认 50，不报错
  - `capabilities.peers_pagination=True`
- ✅ **trust.signals vouch_chain**（P2，来自 A2A IS#1628）
  - `POST /trust/vouch` — 添加背书条目（voucher_did/comment/sig）
  - `GET /trust/vouch` — 列出背书链（支持 limit/offset 分页）
  - AgentCard `trust.signals[]` 含 `type=vouch_chain` + `enabled/count/vouches[-5:]`
  - `capabilities.peers_vouch_chain=True`
- 测试：PP1-PP12 + VC1-VC5 = 17/17 PASS（smoke 验证）

---

### ✅ v2.34（完成 — 2026-04-02，开发轮）
**主题：Per-Peer 结构化信任评分**

- ✅ **`GET /peers/<peer_id>/trust`** — 综合五维度加权信任评分（commit `09a034a`）
  - 维度 + 权重：`card_sig`(0.35) + `did_consistent`(0.20) + `ping_rtt`(0.20) + `message_hist`(0.15) + `vouch`(0.10)
  - `trust_score` (0.0–1.0) = 加权和；`trust_level` = high/medium/low 三档分类
  - `ping_rtt`：分桶 <50ms→1.0, <200ms→0.7, <500ms→0.4, else→0.1, 无数据→0.0
  - `message_hist`：消息量 ≥100→1.0, ≥20→0.7, ≥5→0.4, >0→0.2, 0→0.0
  - `vouch`：peer DID 在 `_vouch_chain` 中存在则 1.0
  - 404 `ERR_PEER_NOT_FOUND` 处理未知 peer_id
  - `capabilities.peer_trust: True` + `endpoints.peer_trust` 声明
  - PT1–PT10：10/10 PASS
- **差异化**：A2A IS#1628（trust signals）和 IS#1672（identity）均停留在讨论阶段（219+评论，无 PR）；ACP 提供可操作的加密锚定信任评分

---

### ✅ v2.35（完成 — 2026-04-02，开发轮）
**主题：Delivery ACK — acp.delivered 回执帧**

- ✅ **`acp.delivered` 帧**：接收方收到业务消息后自动回执，sender 感知消息已送达（commit `d444585`）
  - 帧格式：`{"type":"acp.delivered","message_id":"<id>","from":"<name>","ts":"<iso8601>"}`
  - 发送方 `_on_message` 处理 `acp.delivered`：全局 + 按 peer `messages_delivered` 计数器自增
  - 无 ACK 循环：`acp.delivered` 不触发再次回执（loop-safe）
  - 仅业务消息触发回执；控制帧（`acp.ping/pong` 等）不触发
- ✅ **`capabilities.delivery_ack: true`** + `messages_delivered` 计数器（`/status` 全局 + `/peers` 按 peer）
- ✅ **`--local-only` 标志**：跳过公网 IP 检测 + Cloudflare relay 注册，立即生成 `acp://127.0.0.1:PORT/TOKEN`（CI/沙箱友好）
- ✅ **DA1–DA10**：10/10 PASS，12.5s

---

### ✅ v2.36（完成 — 2026-04-02，开发轮）
**主题：Read Receipt — acp.read 已读回执帧**

- ✅ **`acp.read` 帧**：接收方 Agent 在"消费"消息后（回复时）发送已读回执（commit `232aafd`）
  - 帧格式：`{"type":"acp.read","message_id":"<id>","from":"<name>","ts":"<iso8601>"}`
  - 触发时机：调用 `/message:send` 回复时，自动附带 `acp.read` 回执对方最近一条消息
  - 两阶段回执：delivered（物理到达）→ read（逻辑消费）
  - `last_received_message_id` 追踪，发送后清空，避免重复回执
  - 修复 v2.35 `asyncio.ensure_future` 线程安全 bug → `run_coroutine_threadsafe`
- ✅ `capabilities.read_receipt: true` + `messages_read` 计数（`/status` + 按 peer）
- ✅ **RR1–RR8**：8/8 PASS，10.6s

---

### ✅ v2.37（完成 — 2026-04-02，开发轮）
**主题：Typing Indicator — acp.typing 打字状态帧**

- ✅ **`POST /message:typing`** + **`acp.typing` 帧**（commit `232aafd`）
  - 帧格式：`{"type":"acp.typing","from":"<name>","typing":<bool>,"ts":"<iso8601>"}`
  - 接收时更新 `_status.peer_typing` + `peer_typing_since` + per-peer 字段 + SSE 广播
  - 503 `ERR_NOT_CONNECTED` 当无 peer 连接
- ✅ `capabilities.typing_indicator: true` + `/peers.typing` + `/peers.typing_since`
- ✅ **Agent 实时状态三件套完整**：delivered(v2.35)✓ → read(v2.36)✓✓ → typing(v2.37)🖊
- ✅ **TI1–TI8**：8/8 PASS，5.0s
- **差异化**：完整 WhatsApp 语义三件套，A2A/ANP 均无此机制

---

### ✅ v2.38（完成 — 2026-04-03，开发轮）
**主题：Message Priority — priority 字段**

- ✅ **`priority` 字段** in `POST /message:send`：`critical | high | normal | low`（默认 `normal`）
  - 非法值返回 400 `ERR_INVALID_REQUEST`
  - `priority` 嵌入 `acp.message` 帧，透传给对端 peer
- ✅ **`GET /recv` 优先级排序**：`critical > high > normal > low`
  - `_PRIORITY_ORDER = {critical:0, high:1, normal:2, low:3}`
  - 适用于 Orchestrator→Worker 场景的任务调度
- ✅ **`_status.priority_counts`**：每级发送计数 `{critical, high, normal, low: int}`
- ✅ `capabilities.message_priority: true` 声明
- ✅ **MP1–MP9**：9/9 PASS，5.7s（commit `63af768`）
- **差异化**：A2A 和 ANP 均无消息优先级机制；ACP 首个轻量级协议支持 per-message 优先级路由

---

### 🚧 v2.0（进行中，目标：2026-Q3）
**主题：联邦化与生态扩展**

- ✅ **v2.1-alpha.1 LAN Port-Scan Discovery**（commit `d9a6b76`，2026-03-26）
  - `_lan_port_scan()` — 64 线程 TCP probe + `/.well-known/acp.json` 指纹验证
  - `_tcp_open()` / `_probe_acp()` / `_get_lan_ip()` — 底层工具函数
  - `GET /peers/discover` — HTTP 端点，支持 ?subnet ?ports ?workers 参数
  - 合并 mDNS 缓存，按 host 去重，skip_self_port 避免自发现
  - `capabilities.lan_port_scan=true` + `endpoints.peers_discover` 声明
  - 扫描速度：~1-3s（/24 子网，64 线程）
  - LD1-LD10：10/10 PASS；全回归 246 passed, 4 skipped, 0 failed
  - **对比 A2A**：A2A spec 无 LAN 发现机制；ACP 无需 mDNS opt-in，发现任意 relay
- ✅ **v2.0-alpha.1 Offline Delivery Queue**（commit `8a58041`，2026-03-26）
  - `_offline_enqueue(msg, peer_id)` — peer 断连时自动缓存消息（per-peer deque maxlen=100）
  - `_offline_flush(ws, peer_id)` — peer 重连时 FIFO 自动交付（host+guest 双路径）
  - `GET /offline-queue` — 检查缓冲区 `{total_queued, max_per_peer, queue}`
  - `capabilities.offline_queue=true` + `endpoints.offline_queue` 声明
  - API 合同不变（503 ERR_NOT_CONNECTED 仍返回）
  - OQ1-OQ10：10/10 PASS；全回归 236 passed, 4 skipped, 0 failed
  - **对比 A2A**：A2A 无离线投递机制，peer 离线时消息直接丢失
- [ ] 公开发布（博客文章 + GitHub README + Hacker News）
  - Show HN 草稿：`docs/show-hn-draft.md`（2026-03-24，待 Stark 先生确认）
- ✅ Extension 机制（URI 标识扩展，向 A2A 靠拢）（commit pending，2026-03-22）
  - AgentCard extensions[] 数组、--extension CLI flag
  - POST /extensions/register（upsert）/ /extensions/unregister
  - GET /extensions 列表查询、capabilities.extensions 能力标志
- ✅ 多语言 SDK 完整矩阵（Python / Node.js / Go / Rust / **Java**）（Java commit `28813ed`，2026-03-24）
- ✅ 兼容性认证流程（commit `a333f35`，2026-03-24）
  - `spec/compatibility-certification.md`：Level 1/2 完整认证规范
  - `tests/cert/test_level1.py`：24/24 PASS，参考 relay ✅ CERTIFIED
- ✅ **Show HN 草稿强化**（commit `0d19a11`，2026-03-25）
  - 加入 A2A #1681（PushNotification 凭证泄露安全漏洞）对比分析
  - 加入 A2A #1680（cancel 设计空白）对比分析
  - Key Talking Points + Anti-trolling prep 各新增 2 条
  - 状态：`docs/show-hn-draft.md`，待 Stark 先生确认发布
- ✅ **竞品 scan #8**（commit `d89bbda`，2026-03-25 07:36）
  - A2A 连续 **10 天**无代码合并（年初以来最长停滞期）
  - ANP 2026-03-05 `failed_msg_id` E2E 精确失败报告机制（Co-Author: Claude Opus 4.6）
  - A2A #1681（凭证泄露）、#1680（cancel 设计空白）依然无官方回应
  - Show HN 发布时机评估：✅ 窗口开启
- ✅ **docs/whats-new.md**（commit `42456f3`，2026-03-25 08:06）
  - HN 读者专用"最近 7 天"速览页面
  - 覆盖 2026-03-22~25 所有重要特性
  - ACP vs A2A 实时对比表格（5 维度）
  - 状态：✅ 已发布，随 Show HN 一起呈现

---

### ✅ v2.29（已发布 — 2026-04-01）
**主题：错误精确报告 + skill 级别可用性探测**

来源分析：
- ANP 2026-03-05 引入 `failed_msg_id`（精确标识失败消息）
- A2A 社区 #1685 讨论 error response Content-Type 规范化
- ACP 内部：多 skill 场景下缺乏"该 skill 当前是否可用"的轻量探测接口

#### P1 特性

**1. `failed_msg_id` in error response（ref ANP 2026-03-05）**  ⏳ 待开发（v2.30 顺延）
- `POST /message:send` 失败时，error response 增加 `failed_msg_id` 字段
- 使调用方无需维护本地 sequence mapping，直接知道哪条消息失败
- 格式：`{"error": "...", "failed_msg_id": "<client_msg_id>", "server_seq": <n>}`
- `capabilities.error_failed_msg_id: True`

**2. `GET /skills/<id>/status` — skill 可用性探测** ✅ 已完成（commit 585a792）
- 轻量接口：查询单个 skill 当前是否处于可服务状态
- 响应：`{skill_id, available, reason?, last_checked}`
- 场景：orchestrator 在分配任务前先探测 worker skill 是否在线
- `capabilities.skill_status_probe: True`
- Tests: SS1–SS12 = 12/12 PASS

#### P2 特性

**3. `limitations[]` PATCH 支持 skill 级别**（v2.21 已支持 AgentCard 顶层）⏳ 待开发
- `PATCH /.well-known/acp.json` 支持 `skills[i].limitations` 部分更新
- 运行时动态标记某 skill 为"暂时不可用"（`permanent: false`）

---

### ✅ v2.30（已发布 — 2026-04-01）
**主题：error 精确追踪能力声明 + skill 运行时动态更新**

#### P1 特性

**1. `error_failed_msg_id` 能力声明** ✅ 已完成（commit ad0521e）
- 发现：`failed_message_id` 功能自 v0.6 已实现（ref ANP），v2.30 补 `capabilities` 声明
- `capabilities.error_failed_msg_id: True` in AgentCard
- 覆盖：`POST /message:send` + `POST /peer/<id>/send`
- 有 `message_id` → error 回显 `failed_message_id`；无则不出现
- Tests: FM1–FM8 = 8/8 PASS

**2. `PATCH /skills/<id>/limitations` — 运行时动态标记 skill 不可用** ⏳ 顺延 v2.31
- 不重启 relay 即可将某 skill 标记为 `permanent: false` 的 limitation
- 与 `GET /skills/<id>/status` 联动：PATCH 后 status 即时反映
- 场景：worker 负载过高时自报"暂时不可用"

---

### ✅ v2.31（进行中 — 2026-04-02，开发轮）
**主题：skill 运行时动态更新 + 消息幂等强化**

#### ✅ 已完成

**1. `PATCH /skills/<id>/limitations`** ✅ 已实现（2026-04-02，commit 待 push）
- 不重启 relay 即可运行时修改 skill 的 `limitations[]`
- `_skill_limitations_overrides` 全局字典存储运行时覆盖
- `GET /skills/<id>/status` 自动合并 overrides，实时反映
- `GET /skills` 列表也合并 overrides
- `limitations_merge: true` 支持追加模式（by kind+code de-dup）
- 空数组 `[]` 清除 override，恢复声明默认值
- 测试 SU1–SU8 = 8/8 PASS

#### ⏳ 待开发

**2. 消息幂等强化 — `message_id` 去重窗口** ✅ 已完成 (v2.32, 2026-04-02)
- 相同 `message_id` 在 30s 窗口内重复投递 → 返回 `{ok:true, deduplicated:true}` 而非重复处理
- 参考 ANP `client_msg_id` 幂等语义（commit 1f0abd2d）
- `capabilities.message_dedup: True`
- 关键语义：dedup 在 request-parse 时触发（路由前），503 错误也记录 cache
- commit: a79fa8f

#### 测试目标
- ✅ SU1–SU8（PATCH /skills/<id>/limitations）8/8
- ✅ MD1–MD7（消息幂等去重）7/7 PASS
- ✅ 回归：FM1-8 + SS1-12 + unit + scenario-BC = 210/210 PASS

---

### ✅ v2.34–v2.48（完成 — 2026-04-02 至 2026-04-05）

| 版本 | 日期 | 主题 |
|------|------|------|
| v2.34 | 2026-04-02 | Per-Peer Structured Trust Score — `GET /peers/<id>/trust` 五维度加权评估 |
| v2.35 | 2026-04-02 | Delivery ACK — `acp.delivered` 自动投递确认帧 |
| v2.36 | 2026-04-02 | Read Receipt — `acp.read` 已读回执帧 |
| v2.37 | 2026-04-02 | Typing Indicator — `POST /message:typing` + `capabilities.typing_indicator` |
| v2.38 | 2026-04-03 | Message Priority — critical/high/normal/low，`/recv` 按优先级排序 |
| v2.39 | 2026-04-03 | Long Poll `/recv` — `?wait=<N>` 长轮询（最大 30s） |
| v2.40 | 2026-04-03 | AgentCard `agent_limitations` — 运行时能力限制声明 |
| v2.41 | 2026-04-03 | GET /skills OpenAPI 3.1 spec — 技能规范发现端点 |
| v2.42 | 2026-04-03 | Ed25519 身份集成测试套件（全回归） |
| v2.43 | 2026-04-03 | BUG-050 h2c graceful skip（HTTP/2 不可用时优雅降级） |
| v2.45 | 2026-04-04 | GET /tasks pagination（page_size/after/status，对齐 A2A v1.0） |
| v2.46 | 2026-04-04 | AgentCard capabilities groups 重组（messaging/tasks/identity/transport/discovery） |
| v2.47 | 2026-04-04 | RFC 8615 well-known 响应头 + `capabilities.well_known_rfc8615`，spec/core-v1.0.md 升为 Stable |
| v2.47.1 | 2026-04-04 | 修复 `datetime.utcnow()` 废弃警告（Python 3.12） |
| **v2.48** | **2026-04-05** | **GET /peers/<id>/messages — per-peer 消息历史（direction/since_seq/sort/pagination）+ `--test-mode` 调试注入，PMH1-10=10/10** |
| **v2.49** | **2026-04-05** | **skill.authorization_tier T0-T3 — per-skill 授权层（ref A2A #1716）+ ERR_AUTHORIZATION_TIER + POST /tasks 执行，SAT1-12=12/12** |
| **v2.50** | **2026-04-05** | **skill.param_constraints — 参数级调用约束（ref SINT Protocol / A2A #1716 constraints 字段）+ ERR_PARAM_CONSTRAINT，SPC1-18=18/18** |
| **v2.51** | **2026-04-05** | **T3 human_confirmation — confirmation_pending 状态 + :confirm/:reject 端点 + trust_override debug + --auto-confirm-t3，T3C1-14=14/14** |
| **v2.52** | **✅ 2026-04-05** | **任务审计日志 `GET /tasks/{id}/audit-log` + `skill.deprecation_notice` — 三层防护可追溯 + Skill 优雅废弃** |
| **v2.53** | **✅ 2026-04-05** | **`skill.rate_limit` 调用频率限制（RPM/RPD/burst）+ ERR_RATE_LIMIT 429 — 防滥用，per-peer 隔离，A2A 完全没有** |
| **v2.54** | **✅ 2026-04-05** | **`POST /verify-card` (v2) — batch + fetch_and_verify + TTL cache + trust_integration — A2A #1672（292评论）完整落地，16/16 VC2 测试 PASS，237 全量回归** |
| **v2.55** | **✅ 2026-04-05** | **`GET /peers/{peer_id}/verify-card` — on-demand per-peer AgentCard 重新验证 + force/trust/ttl 参数 — PVC-1..10 PASS，238 全量回归** |
| **v2.56** | **✅ 2026-04-05** | **`principal_chain[]` OBO 委托链 — trust block 注入 + GET/POST/DELETE /principal-chain + 消息级传播（on_behalf_of）+ --principal CLI — PC-1..10 PASS，A2A #1713 零基础设施替代方案** |
| **v2.57** | **✅ 2026-04-06** | **`capability_token` — SINT-format Ed25519 signed capability tokens，POST /skills/{id}/capability-token 发行，GET /capability-tokens 列表，POST /tasks enforcement gate（required 先检查 + 签名验证 + tier 绕过），CT-1..12 PASS — A2A #1716 抢先实现** |
| **v2.58** | **✅ 2026-04-06** | **`effective_tier` 三因子动态计算 — `_compute_effective_tier()`: max(tier_rule, depth_floor(chain.len), rep_adj) + GET /skills/{id}/effective-tier 调试端点 + DELETE /principal-chain URL-decode 修复 + ET-1..12 PASS — A2A #1716 @64R3N 公式抢先实现** |
| **v2.59** | **✅ 2026-04-06** | **双边交互记录（Bilateral Signed Interaction Record）轻量版：`_create_interaction_record()` + `POST /tasks?record=true` + `GET /interaction-records` + relay Ed25519 签名 + sha256 链 + caller_token_hash — A2A #1718 抢先实现（0💬 时 ACP 已发布），IR-1..12 PASS** |
| **v2.60** | **✅ 2026-04-06** | **governance_metadata in AgentCard（`_build_governance_metadata()`：trust_score 启发式 + capability_manifest auto-derive + policy_compliance + audit_trail_reference + live runtime counters）+ GET/PATCH /governance-metadata + `--governance-metadata` CLI + GM-1..14 PASS — A2A #1717（Microsoft，0💬）抢先实现** |
| **v2.61** | **✅ 2026-04-06** | **`caller_signature` 完整双边签名：`_create_interaction_record()` 扩展接受 caller_signature + caller_public_key，Ed25519 验证 canonical payload（relay_did\|caller_did\|task_id\|sequence_a\|ts），`bilateral: true` 仅当双方签名均有效 + CS-1..12 PASS + BUG FIX: POST /tasks role 从顶层 body 取值 — A2A #1718 外部验证：unilateral attestation 可伪造，bilateral closes the gap** |
| **v2.62** | **✅ 2026-04-06** | **`wtrmrk_sequence_root` Factor 4：`_query_wtrmrk()` + `_wtrmrk_to_adj()` + combined_adj 四因子公式（asymmetric safety rule: either +1 wins; both -1 needed to lower floor）+ `POST /tasks metadata.wtrmrk_sequence_root` + `GET /skills/{id}/effective-tier?wtrmrk_sequence_root=` + AgentCard `wtrmrk_attestation:true` + WA-1..14 PASS + 525+ 全量回归 — A2A #1716 @64R3N/@MoltyCel/@aeoess 验证** |
| **v2.63** | **✅ 2026-04-06** | **跨协议 token 验证：`GET /identity/did-key`（W3C did:key，multicodec 0xed01 + base58btc，algorithm/multicodec/hex/b64）+ `POST /verify/external-token`（SINT-format 7步校验：fields→expiry→decode→did:key→canonical→sig→MoltTrust-optional）+ `_verify_sint_token()` helper + AgentCard endpoints.did_key/external_token_verify + capabilities.external_token_verify + ETV-1..16 PASS + **843 全量回归** — A2A #1713 SINT↔APS 跨协议互验 9/9 PASS，零代码修改** |
| **v2.64** | **✅ 2026-04-06** | **双边 IR 测试向量 + governance live_endpoint（APS 对齐）：`GET /ir/test-vectors`（4 个确定性 Ed25519 测试向量：tv-ir-001 双边有效/tv-ir-002 单边/tv-ir-003 篡改负面测试/tv-ir-004 did:key 格式）+ SHA-256 seeded 确定性密钥对 + 哈希链 previous_hash + canonical_bytes_hex 一致性 + `governance_metadata.live_endpoint: /governance-metadata`（APS serviceEndpoint 对齐，A2A #1717）+ AgentCard capabilities.ir_test_vectors + endpoints.ir_test_vectors + 503 无 identity 时 + ITV-1..18 PASS + **860 全量回归** — commit a61f9f0** |
| **v2.65** | **✅ 2026-04-06** | **`POST /ir/import-evidence` — APS importBilateralEvidence() 对齐（A2A #1718）：接受外部双边 IR → 验证 relay_signature + caller_signature（Ed25519）→ 返回 trust_delta（+1 双边验证/0 单边/−1 篡改）+ freshness_hint + aps_schema:v1；`GET /ir/imported-evidence`（列表/过滤/分页）；`_verify_ir_signatures()` + `_build_reputation_update()` 内部 helper；AgentCard capabilities.import_evidence + endpoints.import_evidence；BUG-052 修复（test_t3c3 端口竞争：`_kill_port()` + `websockets.serve(reuse_address=True)` + timeout 20s）；IE-1..20 PASS + **843 全量回归** — commit c5e53e3** |

---

### ✅ v2.33（完成 — 2026-04-02，开发轮）
**主题：DID 公钥离线发现 — Agent Identity 完整闭环**

#### ✅ 已完成

**`GET|POST /identity/pubkey-discovery` — 离线 DID → Ed25519 公钥解析** ✅ 已实现（2026-04-02，commit a298492）
- 无需任何 HTTP 调用，纯 stdlib 实现
- 支持 `did:acp:<base64url-pubkey>` 和 `did:key:z<base58btc(0xed01+pubkey)>` 两种 DID 方案
- `GET ?did=<did>` — 单条查询；`POST {dids:[...]}` — 批量查询（max 50）
- 返回 `public_key_b64`、`public_key_hex`、`algorithm`、`consistent`（DID 可回环推导标志）
- `capabilities.pubkey_discovery: True`；`endpoints.pubkey_discovery: "/identity/pubkey-discovery"`

**战略意义**：
- A2A IS#1672（213 条评论）在讨论 agent 身份验证时，ACP 已率先完整实现：
  - v1.8：AgentCard Ed25519 自签名（`card_sig`）
  - v2.33：DID 离线公钥发现（无注册中心）
- ACP 差异化：**offline-first** — 无 CA、无注册表、无网络调用

#### 测试目标
- ✅ PD1–PD8（DID pubkey discovery）8/8 PASS
- ✅ 全回归：dedup 8/8 + failures 8/8 + skill limitations 8/8 + skill status 12/12 = 36/36 PASS

---

## 设计禁忌（红线）

- ❌ OAuth 2.0 / PKCE
- ❌ 多租户架构
- ❌ gRPC 绑定
- ❌ Push Notification 配置 CRUD
- ❌ 8 种 Task 状态（5 种够用）
- ❌ 中心注册表 / 服务发现中心

---

## 研究信息源（自动扫描）

```
A2A:  https://github.com/a2aproject/A2A
ANP:  https://github.com/agent-network-protocol/AgentNetworkProtocol
IBM:  https://github.com/i-am-bee/acp
MCP:  https://github.com/modelcontextprotocol/specification
```
