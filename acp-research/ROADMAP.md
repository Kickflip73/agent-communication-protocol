# ACP 协议研发路线图

> 持续更新。贾维斯每周自动扫描竞品动态，每月产出一个新版本。  
> 最后更新：2026-03-29 12:17（文档轮：v2.14 trust.signals[] 完成标记，v2.5 任务划线，差异化表新增 trust_signals 行）

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

### ACP 差异化领先点（2026-03-29 更新）

| 功能 | ACP | A2A | 领先方 |
|------|-----|-----|--------|
| Agent 身份认证（Ed25519/DID） | ✅ v1.3 已实现 | 🔴 #1672 讨论中（未合并）| **ACP 领先 ~2 月** |
| `limitations` 字段 | ✅ v2.7 已实现 | 🔴 #1694 提案未合并 | **ACP 领先** |
| WebSocket 原生推送 | ✅ v2.12 已实现 | 🔴 #1029 提案中 | **ACP 领先** |
| **事件回放 `?since=<seq>`** | ✅ **v2.13 已实现** | ❌ 无 | **ACP 领先（首创）** |
| **`trust.signals[]` 结构化信任证据** | ✅ **v2.14 已实现** | ❌ #1628 仍在提案 | **ACP 领先** |
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

### 🎯 v2.5（目标：2026-04，下一里程碑）
**主题：测试稳定性 + ADR 规范化**

- [ ] `test_reconnect.py` 完整重写（local relay，无需公网 IP）
- [ ] WS2/WS3 本地 peer 测试（消除 P2P skip）
- [x] `trust.signals[]` 兼容格式（✅ v2.14 已实现，commit `06f82cd`）
- [x] `adrs/` 目录初始化（✅ v2.13 文档轮已完成：ADR-001/002/003 + template）
- [ ] 全套测试 0 failed 稳定化

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
