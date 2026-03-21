# ACP 协议研发路线图

> 持续更新。贾维斯每次研究轮扫描竞品动态，每月产出新版本。
> 最后更新：2026-03-21（文档轮：v0.9 进度同步，v0.8 全部 P0 完成）

---

## 战略定位

### 四大核心特性方向

| 特性 | 含义 | 设计原则 |
|------|------|---------|
| **① 轻量级，简单开箱即用** | 最小化接入成本，无需学习曲线 | 单文件，一个命令运行，JSON over HTTP/SSE |
| **② P2P 无中间人** | Agent 直连，不经过任何第三方服务器 | Relay 只做连接打洞，消息直通，无持久化 |
| **③ 实用性，解决任意 Agent 通信** | 不限框架、不限平台、不限语言 | 协议最小集 + 渐进扩展，curl 可接入 |
| **④ 面向个人和团队** | 对标 A2A 企业级，做个人/小团队场景 | 零运维、零注册、即用即走 |
| **⑤ 标准化** | 像 MCP 标准化了 Agent↔Tool，ACP 标准化 Agent↔Agent | 开放规范，任意实现可互通 |

### 定位口号
> **MCP 标准化了 Agent↔Tool 通信，ACP 标准化 Agent↔Agent 通信。**
> P2P、轻量、开放、人人可用。

### 设计禁忌（红线，永远不做）
- ❌ OAuth 2.0 / PKCE — 个人场景用不上，增加接入门槛
- ❌ 多租户架构 — P2P 不需要
- ❌ gRPC 绑定 — 保持 JSON over HTTP，可调试
- ❌ 8 种 Task 状态 — 5 种够用，不过度设计
- ❌ 中心注册表 / 服务发现中心 — 真 P2P，不需要

---

## 竞品现状

| 协议 | 活跃度 | 定位 | 我们的态度 |
|------|--------|------|-----------|
| **A2A** (Google) | ⚡ 极高 (v1.0, 22k+ stars) | 企业级 Agent 总线 | 借鉴概念，不复制复杂度 |
| **ANP** (社区) | 🟡 中 | 去中心化身份 | 借鉴 idempotency 思路 |
| **IBM ACP** | 🔴 停更 (2025-08) | 多模态消息 | 参考即可 |
| **MCP** (Anthropic) | ✅ 稳定 | 工具调用 | 不同赛道，可互补 |

---

## 版本路线图

### ✅ v0.1–v0.4（已完成，2026-03-05 ~ 2026-03-18）
- P2P WebSocket 直连，AgentCard 能力声明
- SSE 流式端点，JSONL 消息持久化，自动重连
- Task 生命周期（3 状态），多 session 支持
- Cloudflare Worker 中继备用传输，自动降级（P2P → relay）
- 多模态 Parts（text / file / data）

---

### ✅ v0.5（已完成，2026-03-19）
**主题：消息结构化 + 任务追踪**
- Task 状态机（5 种：submitted/working/completed/failed/input_required）
- 结构化 Part 模型（text/file/data）
- 消息幂等性（client `message_id` + server `server_seq`）
- QuerySkill() API（`POST /skills/query`）
- 双向 Task 同步（`create_task: true` 消息自动在对端注册同 id task）

---

### ✅ v0.6（已完成，2026-03-20）
**主题：多 peer 注册 + 错误码规范**
- **多 session Peer 注册**：同时维护多个 peer 连接
  - `GET /peers`、`GET /peer/{id}`、`POST /peer/{id}/send`、`POST /peers/connect`
- **标准化错误码**（`ERR_NOT_CONNECTED` / `ERR_MSG_TOO_LARGE` / `ERR_NOT_FOUND` / `ERR_INVALID_REQUEST` / `ERR_TIMEOUT` / `ERR_INTERNAL`）
  - 统一 `{ok, error_code, error, failed_message_id}` 响应格式
  - 参考：`spec/error-codes.md`
- **最小接入规范**：`spec/v0.6-minimal-agent.md`（3 端点即可接入 ACP）

---

### ✅ v0.7（已完成，2026-03-20）
**主题：信任 + LAN 发现**
- **HMAC-SHA256 消息签名**（`--secret`）：闭合部署完整性校验，warn-only 不丢包
- **mDNS LAN 自动发现**（`--advertise-mdns`）：UDP 多播，无需 zeroconf 库，`GET /discover`
- **context_id 多轮对话**：跨消息上下文分组，`POST /message:send` 支持 `context_id` 字段

---

### ✅ v0.8（已完成，2026-03-21）
**主题：生态建设 + 自主权身份**
- **Ed25519 可选身份扩展**（`--identity`）：自主权密钥对，签名/验证，无 PKI
  - 自动生成 `~/.acp/identity.json`（chmod 0600）
  - AgentCard 发布 `identity.public_key`，每条消息附 sig
  - 参考：`spec/identity-v0.8.md`
- **Node.js SDK**（`sdk/node/`）：零外部依赖，TypeScript 类型，19 个测试
- **兼容性测试套件**（`tests/compat/`）：黑盒规范合规验证，`ACP_BASE_URL` 参数化
- **综合规范**：`spec/core-v0.8.md`（515 行，supersedes v0.1/v0.5 spec）
- **Python async SDK 重写**：AsyncRelayClient stdlib-only（去掉 aiohttp 依赖），v0.8 全特性，35 个测试
- **CLI 参考文档**：`docs/cli-reference.md`（所有 flag、usage pattern、port layout）

---

### 🚧 v0.9（目标：2026-04-16）
**主题：规范整合 + 开发者体验**

#### P0（必做）
- [x] `spec/core-v0.8.md` 综合规范（超前完成于 v0.8 阶段）
- [x] Python async SDK 重写（stdlib-only，35 tests）
- [x] **CLI 改进**：`--version` 标志、`--verbose` 日志级别、`--config` 文件支持（YAML/JSON）

#### P1（计划）
- [x] **`acp_relay.py` 单测**：`tests/unit/test_relay_core.py`，63 tests，全部通过
  覆盖：`_err()`、ID/token 生成、Part 构造器/校验、HMAC 签名/验证、Task 状态常量、`_load_config_file()`、`parse_link()`
- [x] **CHANGELOG.md**：从 v0.1 至今的完整变更历史
- [x] **`docs/integration-guide.md` 更新**：v0.7/v0.8/v0.9 全面重写

#### P2（可选）
- [x] `sdk/python/` 支持 `pip install acp-relay`（setup.py → pyproject.toml，acp-relay CLI 入口）（setup.py / pyproject.toml 完善）
- [x] `sdk/node/` 发布到 npm（`acp-relay-client`，package.json + ESM + .npmignore + LICENSE）
- [ ] HTTP/2 transport binding 探索

---

### 📋 v1.0（目标：2026-05-05）
**主题：生产发布 + 稳定性保证**  
详细规划：[spec/v1.0-planning.md](../spec/v1.0-planning.md)（commit `167d67d`，2026-03-21）

#### P0（必须）
- [x] `spec/core-v1.0.md`：纳入所有 v0.9 修订，API 稳定性标注（commit `20aa1ed`，2026-03-21）
- [ ] 端点稳定性标注：stable / experimental / internal（审计 `acp_relay.py`）
- [ ] 版本号 1.0.0 bump：`acp_relay.py` + `pyproject.toml` + `sdk/node/package.json` + git tag

#### P1（随 1.0 发布）
- [ ] HMAC 安全审计（常量时间比较、无 timing oracle）
- [ ] Ed25519 安全审计（canonical form、key 权限、graceful fallback）
- [ ] `docs/security.md`：安全模型、限制说明、TLS 建议
- [ ] Go SDK stub（`sdk/go/`，stdlib `net/http` + `bufio` SSE，零依赖）

#### P2（可选 / v1.1）
- [ ] Rust SDK stub + crates.io 发布（`acp-relay-client`）
- [ ] DID 可选扩展（`did:acp:` 格式，`spec/did-v1.0.md`）
- [ ] HTTP/2 transport binding 探索
- [ ] Docker + systemd 部署示例（`relay/examples/`）

**Timeline：** 规范草稿 2026-04-01 → API 标注 2026-04-07 → 安全审计 2026-04-14 → Go SDK 2026-04-21 → RC 2026-04-28 → GA 2026-05-05

---

## 竞品情报档案

| 报告 | 日期 | 关键发现 |
|------|------|---------|
| [2026-03-19-a2a-evening-scan.md](reports/2026-03-19-a2a-evening-scan.md) | 2026-03-19 | A2A #1619 Binding/Extension 分层 + #1655/#1658 AgentCard 标准化 |
| [2026-03-19-late-scan.md](reports/2026-03-19-late-scan.md) | 2026-03-19 | A2A v1.0.0 发布 + ANP failed_msg_id + APS Ed25519 深度分析 |
| [2026-03-21-a2a-scan.md](reports/2026-03-21-a2a-scan.md) | 2026-03-21 | A2A #883 SQLAlchemy 隐式依赖 + #876 REQUIRED 字段未校验 |

---

## 研究信息源

```
A2A:  https://github.com/google-a2a/a2a-python
ANP:  https://github.com/agent-network-protocol/agentnetworkprotocol
MCP:  https://github.com/modelcontextprotocol/specification
```
