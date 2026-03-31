# ACP 协议研发路线图

> 持续更新。贾维斯每周自动扫描竞品动态，每月产出一个新版本。  
> 最后更新：2026-03-31 13:30（文档轮；v2.22 /peers/broadcast 完成；当前版本 v2.22.0 commit d396969）

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

## 竞品生态现状（2026-03-19，身份对比更新 2026-03-28）

| 协议 | Stars | 活跃度 | 定位 | 身份认证 | 态度 |
|------|-------|--------|------|----------|------|
| **ACP** (本项目) | - | ✅ 活跃开发 | 轻量 P2P Agent 通信 | ✅ Ed25519+DID（v1.3） | - |
| **A2A** (Google) | 22,643 | ⚡ 极高 | 企业级 Agent 总线 | ⏳ 讨论中（Issue #1672，71评论） | 借鉴概念，不复制复杂度 |
| **ANP** (社区) | 1,240 | 🔴 已归档 | 去中心化身份 | ✅ 理论设计（但停更） | 停更（最后活跃 2026-03-05），不再追踪 |
| **IBM ACP** | 966 | 🔴 停更 | 多模态消息 | ❌ 无 | 参考即可 |
| **MCP** (Anthropic) | - | ✅ 稳定 | 工具调用 | ❌ 无 | 不同赛道，可互补 |

> 🏆 **ACP 差异化优势**：在 Agent 身份认证方向，ACP 已实现完整 Ed25519 自主权密钥 + `did:acp:` DID 体系（v1.3），领先 A2A 社区约 2-3 个月。

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

- ✅ `failed_message_id` 覆盖所有 /message:send 错误码（commit `e281790`，2026-03-21）
  - 灵感：ANP commit 99806f45（failed_msg_id in e2ee_error）
  - 覆盖：ERR_INVALID_REQUEST × 4 + ERR_NOT_CONNECTED + ERR_INTERNAL
- ✅ replay-window：HMAC 重放攻击防护（PARTIAL → PASS）（commit `e263f52`，2026-03-22）
  - `--hmac-window <seconds>`，默认 300s；超时消息硬拒绝（drop）
  - 安全审计从 1 PARTIAL → 0 PARTIAL，9 PASS
- ✅ Rust SDK（`sdk/rust/`，commit `4f62ae6`，2026-03-22）
- ✅ DID 身份（`did:acp:` 格式，commit `6595e39`，2026-03-22，v1.3）
- ✅ Docker 官方镜像 + GHCR CI 发布管道（commit 见 v1.3，2026-03-23）
  - `Dockerfile` 版本升至 v1.3.0；v1.3 运行示例 + GHCR pull 指引
  - `.github/workflows/docker-publish.yml`：多平台（amd64/arm64）build + push + smoke test
  - `docker-compose.yml`：新增 v1.3 DID + Extension 演示注释块；`volumes.acp-identity` 声明
- [ ] HTTP/2 传输绑定（可选，长期）
- [ ] **`GET /tasks` 列表查询 + 分页**（参考 A2A v1.0 `tasks/list`）
  - 灵感：A2A 1.0.0 发布（2026-03-12）新增 tasks/list，含过滤和分页
  - 参数：`?status=working&limit=20&offset=0`
  - 响应：`{"tasks":[...], "total": N, "has_more": bool}`
  - 当前 ACP 只有 `GET /tasks/{id}`，缺少列表视图

---

### 🔥 v1.4（目标：2026-04，P0 优先）
**主题：真 P2P NAT 穿透 — 协议初衷的核心实现**

> **背景**：当前 `acp://` 直连在双方都位于 NAT 后面时必然失败，用户被迫使用
> `--relay`（Cloudflare Worker 转发），每条消息都经过第三方，违背 P2P 无中间人原则。
> v1.4 是修复这一根本缺陷的专项版本。

**三级连接策略（自动选择，用户零感知）：**

```
Level 1: 直连        — ws://IP:7801/token，3s 超时
Level 2: TCP 打洞 ★  — Signaling 交换公网地址 → 双方 SYN 打洞（新增）
Level 3: Relay 降级  — Cloudflare Worker 转发（兜底，约 30% 场景触发）
```

- [x] **Python 侧 HTTP 反射 + signaling helpers**（commit `8c162d4`，2026-03-24）
  - ✅ `_relay_get_public_ip()` — HTTP 反射公网 IP（STUN 降级方案）
  - ✅ `_relay_announce()` — 地址注册
  - ✅ `_relay_get_peer_addr()` — 对方地址读取
  - ✅ `tests/test_nat_signaling.py` — 22/22 PASS
- [x] **DCUtRPuncher 集成 HTTP 反射降级**（commit `b3da914`，2026-03-25）
  - STUN 失败后调用 `_relay_get_public_ip(_status["relay_base_url"])` 获取公网 IP
  - 将 `{http_ip}:{local_port}` 加入候选地址列表，继续尝试 Level 2 打洞
  - `_status["relay_base_url"]` 在两个 relay 启动路径（`--relay` flag + P2P guest_mode fallback）写入
  - SSE 事件 `dcutr_http_reflect` 可观测
  - `tests/test_nat_http_reflect.py`：12/12 PASS（R1-R6，全 mock，无需网络）
- [x] **Cloudflare Worker 改造** → Worker v2.1（commit `8c162d4`，2026-03-24）
  - ✅ `GET /acp/myip`：反射公网 IP（CF-Connecting-IP header）
  - ✅ `POST /acp/announce`：注册 {token,ip,port,nat_type}，TTL 30s，自动过期
  - ✅ `GET /acp/peer?token=`：一次性读取+删除（防地址爬取）
- [ ] **自动降级集成**：`_connect_with_nat_traversal()` 替换现有直连逻辑
- [ ] **链接格式不变**：`acp://` 底层透明升级，向后完全兼容
- [ ] **`--relay` 语义变更**：从「用户主动选择」→「自动最后降级」，用户无需手动指定
- [x] **测试（signaling 层）**：`tests/test_nat_signaling.py` — 22/22 PASS（2026-03-24）
- [ ] **测试（打洞集成）**：`tests/integration/test_p2p_behind_nat.py`（需要真实 NAT 环境）
- [x] **规范文档**：`spec/nat-traversal-v1.4.md`（已创建 2026-03-23，signaling 层已更新 2026-03-24）

**成功指标：**
- 双 NAT 场景直连成功率 ≥70%（覆盖 Full Cone / Restricted Cone NAT）
- 消息经过第三方节点 ≤30%（对称 NAT 兜底场景）
- 连接建立延迟 <600ms（含打洞握手）
- `--relay` 用户操作：从必须手动指定 → 零感知自动降级

**参考规范**：`spec/nat-traversal-v1.4.md`

---

### ✅ v1.5.2-dev（完成，2026-03-25）
**主题：取消语义规范化 + 测试基础设施**

- ✅ **spec §10 Cancel 语义**（commit `0d19a11`）
  - 三种取消场景：立即取消、无法立即取消（`input_required`）、已完成任务取消（幂等）
  - 与 A2A issue #1680 同期：A2A 社区仍在讨论，ACP 已有明确方案，差异化优势
  - `cancel_semantics` AgentCard 能力声明
- ✅ **Show HN 草稿更新**（`docs/show-hn-draft.md`）
  - 补充 v1.5 特性：DID、Docker、conformance
  - 发布窗口：A2A 无大版本冲击，可在近期发布

Key commit: `0d19a11`

---

### ✅ v1.6（完成，2026-03-25）
**主题：HTTP/2 传输绑定（h2c）**

- ✅ **可选 HTTP/2 cleartext (h2c) 支持**
  - 依赖：`hypercorn` + `h2`（可选，graceful fallback 到 HTTP/1.1）
  - 实现：原生 `h2` 状态机 over `socketserver.ThreadingTCPServer`（避免 hypercorn signal handler 限制）
  - `_HTTP2_AVAILABLE` 全局标志，`--http2` CLI flag
  - `capabilities.http2: true` 在 AgentCard 声明
  - `_H2Handler._dispatch()`：h2c 请求桥接到 `LocalHTTP` handler（fake socket pattern）
- ✅ **测试套件**：`tests/test_http2_transport.py`（H1–H6，全部 PASS）
  - H1: HTTP/2 server 启动，H2: AgentCard via h2c, H3: SSE over h2c
  - H4: POST /tasks via h2c, H5: /status endpoint, H6: /.well-known/acp.json
- ✅ **全套测试**：**15 passed, 3 skipped (P2P), 0 failed**（commit `21e3e7d`）

Key commits: `3f06b24`, `e8974b2`, `cf578e3`, `394b71c`（HTTP/2 实现）, `21e3e7d`（测试基础设施）

**测试基础设施改进（同期）**：
- `tests/conftest.py`：全局 http_proxy 清除 + `clean_subprocess_env()` 工具函数
- `pytest.mark.p2p`：P2P 依赖测试沙箱 skip 标记（`--with-p2p` 启用）
- `test_scenario_h`：重写为 HTTP-only 并发隔离测试（无需 P2P）

---

### ✅ v1.7（完成，2026-03-25 20:30）
**主题：Python SDK 升级 + SSE context_id 传播 + vs-A2A 差异化文档**

- ✅ **Python SDK `RelayClient` v1.7**（commit `00e4a09`）
  - `tasks()`: `created_after`/`updated_after` 时间窗口过滤 + `peer_id`/`sort`/`cursor`/`limit` 全参数
  - `cancel_task()`: 幂等语义 + 409 `ERR_TASK_NOT_CANCELABLE` 优雅处理（`raise_on_terminal` 参数）
  - `capabilities()`: 从 AgentCard 提取 http2/did_identity/hmac_signing/mdns 能力标志
  - `identity()`: 返回 `did:acp:` DID 字段（v1.3+）
  - `did_document()`: 获取 `/.well-known/did.json` W3C DID Document
  - `AsyncRelayClient`: 以上所有方法同步更新
  - 测试：10/10 PASS（`sdk/python/tests/test_relay_client_v17.py`）
- ✅ **SSE context_id 完整传播**（commit `b91f642`）
  - `_create_task()`: 存储 `context_id`，initial status 事件携带它
  - `_update_task()`: 所有后续 status/artifact SSE 事件传播 `context_id`
  - `/tasks/create` + `/send` 端点均透传 `context_id`
  - 无 `context_id` 的任务：事件干净不含该字段（无 null 污染）
  - 修复 A2A Issue #1683 同类问题（A2A spec §4.2.2 vs §6.2 矛盾）
  - 测试：17/17 PASS（`tests/test_context_id_sse.py`）
- ✅ **README vs-A2A 差异化**（commit `b91f642`）
  - 新增对比行："Cancel task semantics" — ACP §10 已解决，A2A #1680/#1684 仍争议
  - 新增 callout 段落引用 A2A Issues，清晰展示 ACP 领先优势
- ✅ **全套：140 passed, 0 failed**
- ✅ **scan #13**（commit `21362a4`）：A2A cancel 语义争议情报，验证 ACP 优势

Key commits: `00e4a09`（Python SDK）, `b91f642`（SSE context_id + README）, `21362a4`（scan #13）

---

### 🔄 v1.7.x — post-v1.7 持续改进（2026-03-25 22:45）
**主题：规范性文档 + vs-A2A 安全差异化**

- ✅ **spec/error-codes.md Content-Type 明确化**（commit `81ffd30`）
  - 显式文档化 `application/json; charset=utf-8`（全部响应，含错误）
  - 明确拒绝 `application/problem+json`，引用 A2A #1685 对比
- ✅ **README vs-A2A 新增 2 行安全差异化**（commit `81ffd30`）
  - "Error response Content-Type"：ACP 统一 vs A2A #1685 模糊
  - "Webhook security"：ACP URL-only vs A2A #1681 凭证泄露
  - vs-A2A 对比表累计 12 行差异化优势
- ✅ **scan #14**（commit `0f84785`）：A2A Content-Type + 凭证泄露安全漏洞，ACP 设计免疫
- ✅ **全套：141 passed, 0 failed**（第八循环 Round 1 测试轮）

Key commits: `81ffd30`（spec + README）, `0f84785`（scan #14）

---

### ✅ v1.8（完成，2026-03-26）
**主题：AgentCard 自签名（Ed25519 身份完整体）**

- ✅ `_sign_agent_card()`：Ed25519 对 AgentCard 自身做 canonical JSON 签名
- ✅ `_verify_agent_card()`：验证 AgentCard 签名（摘除 `card_sig` 后重建 payload）
- ✅ `POST /verify/card`：提交任意 AgentCard 验证端点
- ✅ `identity.card_sig` 字段（base64url，`--identity` 模式下自动附加）
- ✅ AgentCard `capabilities.card_sig: true`
- ✅ 测试：`tests/test_card_signature.py`（全部 PASS）

Key commit: `fe80ea4`, `bd07033`（docs）

---

### ✅ v1.9（完成，2026-03-26）
**主题：Peer AgentCard 握手自动验证**

- ✅ `GET /peer/verify`：获取当前已连接 peer 的 AgentCard 验证结果
- ✅ 握手时自动触发 `_send_agent_card()` + 自动执行 `_verify_agent_card()`
- ✅ 验证结果存入 `_status["peer_card"]`，零额外 API 调用
- ✅ `capabilities.auto_card_verify: True`（无论是否启用 `--identity`）
- ✅ `endpoints.peer_verify: "/peer/verify"` 在 AgentCard 声明
- ✅ 测试：`tests/test_peer_card_verify.py`（PV1–PV8，7p/1s）
- ✅ 文档：`docs/whats-new.md` + `docs/show-hn-draft.md`

Key commit: `97b6128`

---

### ✅ v2.0-alpha（完成，2026-03-26）
**主题：离线消息队列**

- ✅ **Offline Delivery Queue**：peer 离线时缓冲消息，重连后自动 flush
- ✅ `GET /queue`：查看离线队列内容（含 depth、messages[]、peer_id）
- ✅ `capabilities.offline_queue: True`
- ✅ 队列有界（`maxlen=100`），防无限堆积
- ✅ `/message:send` 和 `/send`（legacy）均自动入队
- ✅ 测试：`tests/test_offline_queue.py`（OQ1–OQ10，10/10 PASS）
- ✅ 文档：`docs/whats-new.md` + `docs/show-hn-draft.md` + README

Key commit: `8a58041`

---

### ✅ v2.1-alpha（完成，2026-03-26）
**主题：LAN 端口扫描发现（无 mDNS）**

- ✅ **`GET /peers/discover`**：TCP 端口扫描 LAN 段发现 ACP relay
  - 扫描当前机器所有网卡 → 提取 /24 段 → 并发 TCP SYN 探测默认端口 (7801/7901)
  - 返回 `{"found": [{"host": "192.168.1.x", "port": 7901, "acp_version": "...", "name": "..."}]}`
- ✅ `capabilities.lan_port_scan: True`
- ✅ 无需 mDNS（`--advertise-mdns`），无需组播权限，纯 TCP
- ✅ 测试：`tests/test_lan_discovery.py`（LD1–LD10，10/10 PASS）
- ✅ 文档：`docs/whats-new.md` + `docs/show-hn-draft.md` + README + ROADMAP

Key commit: `d9a6b76`, `5bd7382`（docs）

---

### ✅ v2.2（完成，2026-03-27）
**主题：任务列表 + 错误追踪增强**

- ✅ **`GET /tasks` 列表查询 + 分页**（commit `9f3e931`，2026-03-27）
  - 参数：`?status=&limit=20&offset=0&peer_id=&sort=asc|desc&created_after=&updated_after=`
  - 响应：`{"tasks":[...], "total": N, "has_more": bool, "next_offset": N}`
- ✅ **`failed_msg_id` 错误回传**（commit `4f2b548`，2026-03-27）
  - `/message:send` + `/peer/{id}/send` 所有错误路径全覆盖（9 种错误码）
  - 新增集成测试 `TestPeerSendFailedMessageId`
- ✅ **VERSION 同步至 `2.2.0`**（commit `fac2a31`）

---

### ✅ v2.3（完成，2026-03-28）
**主题：AgentCard `limitations` — 三元能力边界完整声明**

灵感来源：A2A GitHub #1694（2026-03-27）— 提议 AgentCard 新增 `limitations` 字段

- ✅ **`limitations: string[]` 顶层 AgentCard 字段**
  - 含义：声明该 Agent **不能做什么**（如 `["no_file_access", "no_internet"]`）
  - 与 `capabilities`（能做什么）+ `availability`（当前状态）构成三元完整能力边界
  - 可选字段，缺省 = `[]`（空数组），完全向后兼容
- ✅ **`--limitations` CLI flag**（逗号分隔字符串）
  - 示例：`--limitations "no_file_access,no_internet,no_shell"`
- ✅ **`_status["limitations"]` 写入** → `/status` 端点自动包含
- ✅ **`_limitations` 全局变量**（默认 `[]`）
- ✅ **spec/core-v1.3.md §11**：完整 limitations 字段规范，含 well-known 值表、三元组关系说明、A2A #1694 对比
- ✅ **docs/whats-new.md v2.3（v2.7）节**：用法示例 + A2A 差异化说明
- ✅ **README 差异化**：vs-A2A 对比表新增行 + callout 段落
- ✅ **tests/test_limitations.py**：20 个测试（LM1–LM5），**20/20 PASS**
- ✅ **CHANGELOG v2.7.0 条目**
- ✅ **VERSION：`2.6.0` → `2.7.0`**

**差异化价值**：A2A #1694 同日（2026-03-27）提案，ACP 次日即落地 ✈️

Key commit: TBD（本轮）

---

### 🔮 v3.0（目标：2026-Q3，真 P2P 完成后）
**主题：公开发布 + 联邦化**

- [ ] 公开发布（博客文章 + GitHub README + Hacker News）
  - ⚠️ 延后至真 P2P 完成后：P2P 是核心卖点，先做到再发布
- ✅ Extension 机制（URI 标识扩展，v1.3，commit `88d00fc`）
- ✅ 多语言 SDK 完整矩阵（Python/Node/Go/Rust，v1.2 完成）
- ✅ 兼容性认证流程（`docs/conformance.md`，2026-03-23，v1.3 开发轮）
  - 三级认证：Core/Recommended/Full Compliant
  - 测试套件运行指南（本地/远程/Docker/CI）
  - 实现者参考（必须端点、AgentCard 字段、错误格式）
  - 自认证 badge 方案（Shields.io 静态 + 动态 endpoint）

---

## ✅ 已完成里程碑摘要（v2.19–v2.22）

| 版本 | 特性 | Commit | 日期 |
|------|------|--------|------|
| v2.19.0 | NAT Auto-Traversal Integration in `/peers/connect`（`connection_type` 字段）| f46ca52 + b0e70ce | 2026-03-31 |
| v2.20.0 | Structured `limitations[]` — LimitationObject（kind/code/message/permanent）| — | 2026-03-31 |
| v2.21.0 | `PATCH /.well-known/acp.json` + `?filter_limitations=` query | — | 2026-03-31 |
| v2.22.0 | `POST /peers/broadcast` — fanout to all connected peers | d396969 | 2026-03-31 |

---

## 🔭 v2.18 候选待办（2026-03-30 研究轮识别）

> 更新时间：2026-03-30 05:24 研究轮

### [x] P0 — v1.4 NAT 穿透主流程集成 ✅ v2.19.0 (commit f46ca52, 2026-03-31)
- `connection_type` 字段（host/p2p_direct/dcutr_direct/relay）集成到 `/peers/connect` 主流程
- `capabilities.nat_traversal: true`
- 测试：`test_nat_integration.py` NI1~NI6: **6/6 PASS**

### [x] P2 — trust.signals JWKS 兼容层 ✅ v2.18.0 (commit 1cce353, 2026-03-30)
- **背景**: A2A IS#1628 趋向使用 ECDSA P-256 / JWKS 标准；ACP 使用 Ed25519
- **实现**: `GET /.well-known/jwks.json` — RFC 7517 JWK Set endpoint（Ed25519/OKP/EdDSA）
  - `_build_jwks()` helper；`capabilities.trust_jwks=True`；`endpoints.jwks` 声明
  - `trust.signals[type=jwks]` 信号（与 type=ed25519_identity 并存，互补）
  - `kid = "<agent_name>:<pubkey_prefix_8>"` 格式
  - 无 identity 时返回 `{"keys": []}` 空集（端点始终可用）
- **测试**: `tests/test_jwks.py` JW1–JW10，**13/13 PASS**
- **来源**: 2026-03-30 扫描，IS#1628 已有 18 评论，方案趋于收敛

### [ ] P3 — data_handling_policy（GDPR 字段，轻量 Extensions）
- **背景**: A2A IS#1606 提议 AgentCard 声明数据处理政策（retention, processing_locations, model_training）
- **方向**: 作为 ACP Extension 实现，`urn:acp:ext:data-handling/v1`，可选字段，零破坏性
- **优先级低原因**: ACP 定位个人/小团队，监管合规压力较小；但中期可跟进增强企业可信度
- **来源**: 2026-03-30 扫描，IS#1606

### ❌ 暂不跟进 — 原生 Pub/Sub（A2A PR#1196）
- A2A 探索将 Kafka/SQS 纳入协议原语，属企业消息总线赛道
- ACP 定位轻量 P2P，Pub/Sub 引入会增加复杂度，违反设计原则
- 持续观察 TSC 结论，若成 A2A 核心特性再评估

---

## 设计禁忌（红线）

- ❌ OAuth 2.0 / PKCE
- ❌ 多租户架构
- ❌ gRPC 绑定
- ❌ Push Notification 配置 CRUD
- ❌ 8 种 Task 状态（5 种够用）
- ❌ 中心注册表 / 服务发现中心

---

## 🔭 v2.23 候选特性（2026-03-31 规划）

> 当前版本 v2.22.0，下一轮开发优先级：

### [ ] P1 — `GET /peers/broadcast/history` — 广播历史查询
- 按需查询最近 N 条广播记录（message_id、delivered/failed、parts、ts）
- 便于调试和审计，补全 broadcast 功能闭环

### [ ] P1 — `POST /peers/broadcast` 支持 `target_peers[]` 选择性广播
- 当前广播到所有 peer，v2.23 支持指定 peer_id 列表（子集广播）
- `{"text": "...", "role": "agent", "target_peers": ["peer_001", "peer_003"]}`

### [ ] P2 — data_handling_policy（GDPR 字段，轻量 Extension）
- 来源：A2A IS#1606，`urn:acp:ext:data-handling/v1`
- 优先级低，中期跟进

---

## 研究信息源（自动扫描）

```
A2A:  https://github.com/a2aproject/A2A
ANP:  https://github.com/agent-network-protocol/AgentNetworkProtocol
IBM:  https://github.com/i-am-bee/acp
MCP:  https://github.com/modelcontextprotocol/specification
```
