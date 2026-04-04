# What's New in ACP — Last 7 Days

> Last updated: 2026-04-04
> For the full history see [CHANGELOG.md](../CHANGELOG.md)

---

### Node SDK v2.47.0 — TypeScript-ready Node.js client (2026-04-04)

`sdk/node` upgraded to match the server's v2.47 feature set:

- **`trustSignals()`** — reads `trust.signals[]` from AgentCard; gracefully returns `[]` on missing/error
- **`capabilityGroups()`** — structured capability groups object (`messaging` / `tasks` / `identity` / `transport` / `discovery`)
- **`wellKnownHeaders()`** — fetches RFC 8615 response headers (`Cache-Control`, `Vary`, `X-Content-Type-Options`)
- Full TypeScript signatures in `index.d.ts`
- Test suite: **66/66 PASS** (+10 new cases)
- `README.md` fully refreshed: version badge, 27-method table with `since` column, Quick Start examples

---

### v2.47.1 — CHANGELOG Auto-Generator (2026-04-04)

`scripts/gen_changelog.py` — Conventional Commits → structured CHANGELOG entries:

```bash
# Preview unreleased changes
python3 scripts/gen_changelog.py --dry-run

# Generate changelog since a version tag
python3 scripts/gen_changelog.py --since v2.40.0 --version v2.47.1
```

Supports `--since`, `--dry-run`, `--version`. Groups commits by `feat/fix/docs/chore`. Idempotent — safe to run repeatedly.

---

### v2.47 — RFC 8615 Well-Known Headers + Stable Specs (2026-04-04)

Three production-readiness upgrades in one release:

**RFC 8615 compliance** — `/.well-known/acp.json` (and `did.json`, `jwks.json`) now return:
```
Cache-Control: max-age=300, stale-while-revalidate=60
Vary: Accept-Encoding
X-Content-Type-Options: nosniff
```

**`spec/core-v1.0.md` → Status: Stable** — v2.47 version history, §5.3.1 `capabilities.groups`, §8.7 three new MUST + four SHOULD conformance rules.

**`spec/identity-v2.0.md` → Status: Stable** — Ed25519+CA hybrid (§2), JWKS (§3.2), `trust.signals` (§5), `capabilities.groups.identity` (§6), Conformance (§9).

---

### v2.46 — AgentCard `capabilities.groups` (2026-04-04)

Flat `capabilities.*` fields now have a structured semantic grouping layer:

```json
"capabilities": {
  "groups": {
    "messaging":  { "send": true, "recv": true, "priority": true, … },
    "tasks":      { "task_list": true, "task_cancel": true, … },
    "identity":   { "ed25519": true, "did_document": true, "jwks": true },
    "transport":  { "sse": true, "websocket": true, "http2": true },
    "discovery":  { "well_known": true, "peer_card": true, "mdns": true }
  }
}
```

All existing flat fields remain — groups are **additive, backward compatible**.
Tests: CG1–CG8 = 8/8 PASS.

---

### v2.41 — GET /skills OpenAPI 3.1 spec (2026-04-03)
- `docs/openapi-skills.yaml`: OpenAPI 3.1 spec for /skills endpoint
- `AgentCard.skills_schema_url`: machine-readable schema reference
- `GET /docs/openapi-skills.yaml`: CORS-enabled static serving
- `capabilities.skills_openapi_spec: true`

---

### v2.40 — AgentCard agent_limitations (2026-04-03)
- `agent_limitations` object in AgentCard + /status: machine-readable constraints
- Fields: max_message_size_bytes, max_recv_queue_size, max_wait_seconds, max_peers
- `capabilities.agent_limitations: true`

---

### v2.39 — Long Poll /recv (2026-04-03)
- `GET /recv?wait=<N>`: block until message arrives (0-30s timeout)
- Zero-waste polling for heartbeat Agents
- `capabilities.recv_long_poll: true`

---

## v2.37.0 — Typing Indicator (2026-04-02)

### Agent 实时状态三件套 ✅ 完整

v2.37 完成了 ACP 「Agent 实时状态三件套」的最后一块拼图：

| 版本 | 特性 | 含义 |
|------|------|------|
| v2.35 | `acp.delivered` | 消息物理到达 ✓ |
| v2.36 | `acp.read` | 消息被逻辑消费 ✓✓ |
| **v2.37** | **`acp.typing`** | **对方正在输入 🖊** |

这是业界首个将 WhatsApp 三件套语义完整移植到 Agent 间协议的实现。A2A/ANP 均无此机制。

### 新增：`POST /message:typing`

```bash
# 告知 peer "我正在输入"
curl -X POST http://localhost:8765/message:typing \
  -H "Content-Type: application/json" \
  -d '{"typing": true}'

# 返回
{"ok": true, "typing": true, "ts": "2026-04-02T13:37:00.000000Z"}

# 停止输入
curl -X POST http://localhost:8765/message:typing \
  -d '{"typing": false}'
```

- `typing` 字段可选，**默认为 `true`**
- 无 peer 连接时返回 `503 ERR_NOT_CONNECTED`

### `acp.typing` 控制帧

接收方会在 WebSocket 上收到：

```json
{
  "type": "acp.typing",
  "from": "OrchestratorAgent",
  "typing": true,
  "ts": "2026-04-02T13:37:00.000000Z"
}
```

### 状态字段

**`GET /status` 新增字段：**
```json
{
  "peer_typing": true,
  "peer_typing_since": "2026-04-02T13:37:00.000000Z"
}
```

**`GET /peers` 每个 peer 新增字段：**
```json
{
  "typing": true,
  "typing_since": "2026-04-02T13:37:00.000000Z"
}
```

`typing: false` 时，`typing_since` 为 `null`。

### SSE 事件

订阅 `/stream` 的客户端将收到：

```
event: typing
data: {"from": "OrchestratorAgent", "typing": true, "typing_since": "..."}
```

### AgentCard 能力声明

```json
{
  "capabilities": {
    "typing_indicator": true
  }
}
```

---

## v2.36.0 — Read Receipt (2026-04-02)

### 新增：`acp.read` 已读回执帧

当接收方调用 `POST /message:send` 回复时，ACP 自动向对方发送已读回执，告知「消息已被处理」。

**`acp.read` 帧格式：**

```json
{
  "type": "acp.read",
  "message_id": "msg_abc123",
  "from": "WorkerAgent",
  "ts": "2026-04-02T10:00:01Z"
}
```

- 触发时机：调用 `/message:send` 时自动发送，回执最近一条未回执的入站消息
- 每条消息只回执一次（`last_received_message_id` 追踪，发送后清空）
- 与 `acp.delivered`（v2.35）形成两阶段回执语义

**`GET /status` 新增字段：**
```json
{
  "messages_read": 5
}
```

**AgentCard 能力声明：**
```json
{
  "capabilities": {
    "read_receipt": true
  }
}
```

---

## v2.35.0 — Delivery ACK (2026-04-02)

### 新增：`acp.delivered` 送达回执帧

消息到达 peer 的 WebSocket 后，ACP 自动向发送方回执，确认物理送达。

**`acp.delivered` 帧格式：**

```json
{
  "type": "acp.delivered",
  "message_id": "msg_abc123",
  "from": "WorkerAgent",
  "ts": "2026-04-02T10:00:00Z"
}
```

- 自动触发：peer 收到业务消息后异步发送，无需手动调用
- 仅表示「物理到达」，不代表消息已被读取或处理（参见 v2.36 `acp.read`）

**`GET /status` 新增字段：**
```json
{
  "messages_delivered": 10
}
```

**AgentCard 能力声明：**
```json
{
  "capabilities": {
    "delivery_ack": true
  }
}
```

---

## v2.34.0 — Per-Peer Structured Trust Score (2026-04-02)

### 新增：`GET /peers/<peer_id>/trust`

**一条 API，将 ACP 所有身份/活跃度数据聚合为单一可操作的信任分。**

响应示例：

```json
{
  "peer_id": "tok_abc123",
  "name": "WorkerAgent",
  "connected": true,
  "trust_score": 0.72,
  "trust_level": "medium",
  "dimensions": {
    "card_sig":      {"score": 1.0, "weight": 0.35, "detail": "Ed25519 signature valid"},
    "did_consistent":{"score": 1.0, "weight": 0.20, "detail": "DID round-trips consistently"},
    "ping_rtt":      {"score": 0.7, "weight": 0.20, "detail": "RTT 85ms (<200ms bucket)", "last_ping_rtt_ms": 85, "ping_count": 3},
    "message_hist":  {"score": 0.2, "weight": 0.15, "detail": "2 messages sent", "messages_sent": 2},
    "vouch":         {"score": 0.0, "weight": 0.10, "detail": "Not in vouch_chain"}
  },
  "evaluated_at": "2026-04-02T04:32:11.123456Z"
}
```

| 维度 | 权重 | 评分依据 |
|------|------|---------|
| `card_sig` | 35% | Ed25519 AgentCard 签名验证通过 → 1.0 |
| `did_consistent` | 20% | DID 可无损回环推导（pubkey round-trip） → 1.0 |
| `ping_rtt` | 20% | <50ms→1.0, <200ms→0.7, <500ms→0.4, else→0.1, 无数据→0.0 |
| `message_hist` | 15% | ≥100→1.0, ≥20→0.7, ≥5→0.4, >0→0.2, 0→0.0 |
| `vouch` | 10% | Peer DID 出现在 vouch_chain 中 → 1.0 |

`trust_level`：`high`（≥0.75）/ `medium`（≥0.45）/ `low`（<0.45）

```bash
curl http://127.0.0.1:18001/peers/tok_abc123/trust
```

**战略背景**：A2A IS#1628（trust signals）和 IS#1672（身份验证）合计 219+ 评论，至今无 PR；ACP v2.34 以可用的实现领先。

---

## v2.33.0 — DID Pubkey 离线发现 (2026-04-02)

### 新增：`GET|POST /identity/pubkey-discovery`

无需任何 HTTP 调用，纯本地将 `did:acp:` 或 `did:key:` 解析为 Ed25519 公钥。

```bash
# 单条查询
curl "http://127.0.0.1:18001/identity/pubkey-discovery?did=did:key:z6Mk..."

# 批量查询（最多 50 条）
curl -X POST http://127.0.0.1:18001/identity/pubkey-discovery \
  -d '{"dids": ["did:key:z6Mk...", "did:acp:AAAA..."]}'
```

返回字段：`public_key_b64`、`public_key_hex`、`algorithm`、`consistent`（DID 可回环推导标志）。

**实现**：纯 stdlib，零外部依赖（`_base58_decode` + `_resolve_did_to_pubkey`）。  
`capabilities.pubkey_discovery: true`  
测试：PD1–PD8 = **8/8 PASS**

---

## v2.32.0 — 消息幂等去重 (2026-04-02)

### 新增：`message_id` 客户端幂等键 + 30s TTL 去重窗口

在不稳定网络下防止消息重复处理。

```bash
# 第一次发送 → 正常处理
curl -X POST http://127.0.0.1:18001/message:send \
  -d '{"text": "hello", "message_id": "msg-uuid-001"}'
# → {"ok": true, "deduplicated": false, "server_seq": 42, "message_id": "msg-uuid-001"}

# 30s 内重复发送同一 message_id → 幂等返回
# → {"ok": true, "deduplicated": true, "server_seq": 42, "message_id": "msg-uuid-001"}
```

- 适用于 `POST /message:send` 和 `POST /peer/<id>/send`
- 不传 `message_id` → 不触发去重（向后兼容）
- 30s TTL 后同一 ID 可重新处理
- `capabilities.message_dedup: true`  
- 测试：MD1–MD6 = **6/6 PASS**

---

## v2.31.0 — Runtime Per-Skill Limitations Update (2026-04-02)

### 新增：`PATCH /skills/<id>/limitations`

无需重启 relay 即可在运行时更新某个 skill 的 `limitations[]`。

**典型场景：** GPU 下线 → worker skill 自报"暂时不可用"；GPU 恢复 → 清除限制 → skill 重新可用。

```bash
# 添加运行时限制（skill 立即变为 unavailable）
curl -X PATCH http://127.0.0.1:18001/skills/ocr/limitations \
  -H "Content-Type: application/json" \
  -d '{
    "limitations": [
      {"kind": "capability", "code": "gpu_unavailable",
       "message": "GPU offline, retrying", "permanent": false}
    ]
  }'
# → {"ok": true, "skill_id": "ocr", "limitations": [...]}

# 验证：GET /skills/<id>/status 立即反映
curl http://127.0.0.1:18001/skills/ocr/status
# → {"available": false, "reason": "GPU offline, retrying", ...}

# GPU 恢复后清除限制
curl -X PATCH http://127.0.0.1:18001/skills/ocr/limitations \
  -H "Content-Type: application/json" \
  -d '{"limitations": []}'
# → {"ok": true, "skill_id": "ocr", "limitations": []}

# 再次查询：已恢复
curl http://127.0.0.1:18001/skills/ocr/status
# → {"available": true, ...}
```

**Merge 模式（追加而非替换）：**

```bash
curl -X PATCH http://127.0.0.1:18001/skills/classify/limitations \
  -H "Content-Type: application/json" \
  -d '{
    "limitations": [
      {"kind": "scale", "code": "max_batch_10",
       "message": "Max 10 items per batch", "permanent": true}
    ],
    "limitations_merge": true
  }'
```

**行为说明：**

| 请求 | 效果 |
|------|------|
| `PATCH /skills/<id>/limitations` with array | 替换该 skill 的 runtime override |
| `PATCH /skills/<id>/limitations` with `limitations_merge: true` | 追加到现有 override（`(kind, code)` 去重） |
| `PATCH /skills/<id>/limitations` with `[]` | 清除 runtime override，恢复声明默认值 |
| `PATCH /skills/<nonexistent>/limitations` | `404` skill not found |

**联动接口：**
- `GET /skills/<id>/status` — 自动反映 runtime override
- `GET /skills` — 列表也合并 override
- `capabilities.skill_limitations_patch: true` — 可发现能力标志

**测试：** SU1–SU8 = 8/8 PASS

---

## v2.30.0 — `error_failed_msg_id` 能力声明 (2026-04-01)

正式声明 `capabilities.error_failed_msg_id: true`。`failed_message_id` 功能自 v0.6 已实现；v2.30 使其可通过 AgentCard 发现。

---

## v2.29.0 — Per-Skill 可用性探测 (2026-04-01)

`GET /skills/<id>/status` — 轻量 per-skill 可用性探测接口，返回 `{skill_id, available, reason?, last_checked, limitations[]}`。Runtime (`permanent:false`) capability/access limitation 触发 `available: false`。

---

## v2.11.0 — Skills 字段增强 (2026-03-28)

### 新增字段：`input_modes` / `output_modes` / `examples`

`GET /skills` 响应中每个 skill 对象新增三个字段，帮助调用方在连接前判断兼容性：

| 字段 | 类型 | 说明 |
|------|------|------|
| `input_modes` | `string[]` | 该 skill 接受的输入模式，如 `["text", "image", "audio"]` |
| `output_modes` | `string[]` | 该 skill 的输出模式，如 `["text", "stream"]` |
| `examples` | `string[]` | 示例调用描述，帮助调用方理解典型用途 |

同样，`GET /.well-known/acp.json` 的 AgentCard `skills[]` 数组也包含上述完整字段。

### `/skills/query` 新增 `input_mode` 过滤

`POST /skills/query` 的 `constraints` 支持新增字段 `input_mode`：当请求体不包含 `skill_id` 时，可按 `input_mode` 筛选能处理该输入类型的 skill 列表。

```json
{
  "constraints": {
    "input_mode": "image"
  }
}
```

### 安全修复：BUG-039 — Webhook 注册限制 localhost

`/webhooks/register` 和 `/webhooks/deregister` 现在**仅接受来自 localhost (127.0.0.1) 的请求**。此前任意客户端均可注册 webhook URL，存在将消息事件泄露到外部服务器的风险（BUG-039）。修复后远程调用将收到 `403 Forbidden`。

---

## v2.10.0 — Skills-lite (2026-03-28)
- 新增 `GET /skills` — 结构化能力发现端点，支持 tag 过滤/关键词搜索/分页
- AgentCard `skills[]` 字段升级为结构化对象数组（兼容旧 CSV 格式）
- 对标 A2A v1.0 Skills，ACP 精简实现：轻量无 JSON Schema 开销

---

## 2026-03-28

### AgentCard `limitations` Field — Three-Part Capability Boundary (v2.7.0)

ACP v2.7 introduces the **`limitations: string[]`** field, completing a **three-part capability boundary declaration** in AgentCard:

| Field | Declares |
|-------|----------|
| `capabilities` | What the agent **CAN do** (feature flags) |
| `availability` | **When** the agent is active (scheduling/cron) |
| **`limitations`** ✨ | What the agent **CANNOT do** (hard constraints) |

**Usage:**

```bash
# Declare a sandboxed agent that cannot access files or the internet
python3 acp_relay.py --name "SandboxAgent" \
  --limitations "no_file_access,no_internet,no_shell"
```

**AgentCard response** (`GET /.well-known/acp.json`):
```json
{
  "name": "SandboxAgent",
  "acp_version": "2.7.0",
  "limitations": ["no_file_access", "no_internet", "no_shell"],
  "capabilities": { "streaming": true, ... },
  "availability": { "mode": "persistent" }
}
```

**Design rationale:**

`capabilities` (positive flags) and `limitations` (explicit cannot-dos) are **complementary**, not redundant:
- A streaming-capable agent (`capabilities.streaming: true`) may still have `limitations: ["no_internet"]`
- The absence of a capability flag does NOT imply a limitation — `limitations` is explicit opt-in

**Backward compatibility:** The field is optional (`default: []`). Old clients that don't recognize it simply ignore it per standard JSON forward-compatibility rules.

**vs. A2A #1694:** A2A GitHub issue #1694 (opened 2026-03-27) proposes the same concept for A2A AgentCard. **ACP ships working code on day one** — ACP v2.7 is live today while A2A #1694 remains an open proposal.

---

## 2026-03-27

### `transport_modes` Routing Topology Declaration (v2.4.0)

ACP agents can now **declare their routing topology** in the AgentCard via the new top-level `transport_modes` field.

**Key distinction:** `transport_modes` (routing topology) is orthogonal to `capabilities.supported_transports` (protocol bindings):
- `supported_transports`: declares *protocol bindings* — HTTP/1.1, WebSocket, HTTP/2
- `transport_modes`: declares *routing topology* — direct P2P, relay-mediated

```bash
# Relay-only sandbox agent
python3 acp_relay.py --name "SandboxAgent" --transport-modes relay

# P2P-only edge agent (public IP)
python3 acp_relay.py --name "EdgeAgent" --transport-modes p2p
```

**AgentCard response** (`GET /.well-known/acp.json`):
```json
{
  "name": "SandboxAgent",
  "acp_version": "2.4.0",
  "transport_modes": ["relay"],
  "capabilities": {
    "supported_transports": ["http", "ws"]
  }
}
```

Default is `["p2p", "relay"]` — both topologies available, peer's choice. Absent means the same. Receivers MUST treat the field as advisory; unknown values MUST be ignored.

→ See **spec §5.4** and `--transport-modes` in [CLI Reference](cli-reference.md)

---

### Task List Queries — `GET /tasks` with Filtering + Pagination (v2.2.0)

ACP agents can now **query all tasks** with rich filtering and offset-based pagination — no more fetching all tasks and filtering client-side.

```bash
# List all tasks (newest first, page 1)
curl "http://localhost:7901/tasks?offset=0&limit=20"

# Filter by status
curl "http://localhost:7901/tasks?status=working"

# Filter by peer (works for both top-level and payload.peer_id)
curl "http://localhost:7901/tasks?peer_id=peer_001"

# Date-range filter (tasks created in the last hour)
curl "http://localhost:7901/tasks?created_after=2026-03-27T04:00:00"

# Pagination — fetch page 2
curl "http://localhost:7901/tasks?limit=10&offset=10"

# Sort oldest-first
curl "http://localhost:7901/tasks?sort=asc"
```

**Response shape:**

```json
{
  "tasks": [
    {
      "id": "task_abc123",
      "status": "working",
      "peer_id": "peer_001",
      "created_at": "2026-03-27T05:10:00",
      "updated_at": "2026-03-27T05:11:00"
    }
  ],
  "total": 42,
  "has_more": true,
  "next_offset": 20
}
```

**All query parameters:**

| Parameter | Default | Max | Description |
|---|---|---|---|
| `status` | — | — | Filter: `submitted`/`working`/`completed`/`failed`/`canceled`/`input_required` |
| `peer_id` | — | — | Filter by peer (checks `task.peer_id` and `task.payload.peer_id`) |
| `created_after` | — | — | ISO 8601 timestamp lower bound |
| `updated_after` | — | — | ISO 8601 timestamp lower bound (updated_at) |
| `sort` | `desc` | — | `asc` (oldest first) or `desc` (newest first) |
| `limit` | `20` | `100` | Page size |
| `offset` | `0` | — | Page start (activates offset mode) |

**Backward compatibility:**
- `?state=<s>` still accepted (legacy alias for `status`)
- `?cursor=<task_id>` keyset pagination still works when `offset` param is absent
- Legacy `?sort=created_asc` / `created_desc` still accepted

**Error handling:**
- Unknown `status` value → `400 ERR_INVALID_REQUEST` with valid values listed

---

---

## 2026-03-26

### LAN Port-Scan Discovery — Find ACP Agents Without mDNS (v2.1-alpha)

ACP agents can now **automatically discover other ACP relays on the same LAN** by scanning common ports — no `--advertise-mdns` flag required on either side.

```bash
# Discover all ACP agents on your local network:
curl http://localhost:7901/peers/discover
# → {
#     "found": [
#       {
#         "host": "192.168.1.42",
#         "http_port": 7901,
#         "name": "Agent-Alice",
#         "link": "acp://192.168.1.42:7801/tok_abc123",
#         "latency_ms": 3.2
#       }
#     ],
#     "scanned_hosts": 253,
#     "scanned_ports": 1518,
#     "subnet": "192.168.1",
#     "duration_ms": 1340,
#     "total_found": 1
#   }

# Optional: narrow the scan
curl "http://localhost:7901/peers/discover?subnet=10.0.1&ports=7901,7902&workers=32"
```

How it works:
- Auto-detects local /24 subnet from the machine's primary LAN IP
- 64-thread TCP connect probe across all hosts on common ACP ports (7901–7931)
- Open port → immediate `GET /.well-known/acp.json` fingerprint to confirm ACP relay
- Merges mDNS cache (from `--advertise-mdns`) automatically — deduped by host
- Skips self to avoid self-discovery; per-host dedup across multiple ports
- Typical scan time: **1–3 seconds** for a /24 subnet

New endpoints/fields:
- `GET /peers/discover` — returns scan results with `acp://` links ready to connect
- `capabilities.lan_port_scan: true` — advertised in AgentCard
- `endpoints.peers_discover: "/peers/discover"` — discoverable via AgentCard

**Why it matters**: mDNS (`--advertise-mdns`) requires opt-in from every agent. Port-scan discovery works against *any* ACP relay regardless of its startup flags — including agents that were started before you, or agents you don't control. Find them first, connect second.

---

### Offline Delivery Queue — Messages Survive Disconnects (v2.0-alpha)

ACP agents now **buffer outbound messages when the peer is offline, and auto-deliver them the moment the peer reconnects** — zero extra code by the caller.

```bash
# Agent A sends a message — peer (Agent B) is NOT connected yet:
curl -s -X POST http://localhost:7901/message:send \
  -H "Content-Type: application/json" \
  -d '{"role":"user","parts":[{"type":"text","content":"hello, are you there?"}]}'
# → {"ok": false, "error_code": "ERR_NOT_CONNECTED",
#    "error": "No P2P connection — message queued for delivery on reconnect"}

# Inspect the queue:
curl http://localhost:7901/offline-queue
# → {"total_queued": 1, "max_per_peer": 100,
#    "queue": {"default": {"depth": 1,
#      "messages": [{"type": "acp.message", "queued_at": "2026-03-26T10:17Z"}]}}}

# Agent B connects. Queue auto-flushes immediately on handshake:
# 📤 Flushed 1 offline message(s) to peer 'peer_a1b2' on connect
```

How it works:
- `_ws_send()` catches `ConnectionError` → calls `_offline_enqueue(msg, peer_id)`
- Messages stored in per-peer `deque(maxlen=100)` — oldest dropped when full, never blocks
- On peer connect/reconnect, `_offline_flush()` runs automatically in FIFO order
- `_was_queued: true` marker in delivered messages lets the receiver know they arrived buffered
- API contract unchanged — callers still get `503 ERR_NOT_CONNECTED` (drop-in safe)

New endpoints/fields:
- `GET /offline-queue` — inspect buffer `{total_queued, max_per_peer, queue}`
- `capabilities.offline_queue: true` — advertised in AgentCard
- `endpoints.offline_queue: "/offline-queue"` — discoverable via AgentCard

**Why it matters**: A2A has no offline delivery mechanism — if you send a task message while the peer agent is restarting or temporarily offline, the message is simply lost. ACP's offline queue delivers it automatically on reconnect, making short disconnects transparent to the application layer.

---

### Peer AgentCard Auto-Verification at Handshake (v1.9)

ACP agents now **automatically verify each other's identity the moment they connect** — no extra API calls needed.

```bash
# Start both agents with identity
acp-relay --name Alice --identity ~/.acp/alice.json  # host mode
acp-relay --name Bob   --identity ~/.acp/bob.json    # connect to Alice

# After connection, immediately check peer identity:
curl http://localhost:7982/peer/verify
# → {
#     "peer_name": "Alice",
#     "peer_did": "did:acp:FmXk7...",
#     "verified": true,
#     "did_consistent": true,
#     "scheme": "ed25519",
#     "error": null
#   }
```

How it works:
- On connect, each side sends a **signed AgentCard** (via `_send_agent_card`)
- On receipt, `_verify_agent_card()` runs immediately — result stored in memory
- `GET /peer/verify` returns the cached result instantly
- If peer is unsigned (older relay), `verified: false` with descriptive `error` field
- State is cleared automatically on disconnect

New endpoints/fields:
- `GET /peer/verify` — peer's verification result; 404 if no peer connected
- `capabilities.auto_card_verify: true` — advertised in AgentCard
- `endpoints.peer_verify: "/peer/verify"` — discoverable via AgentCard

---

### AgentCard Self-Signature — Cryptographic Identity Verification (v1.8)

ACP agents can now **cryptographically sign their own AgentCard** and any peer can verify it.

```bash
# Start with identity (auto-generates Ed25519 keypair)
acp-relay --name Alice --identity ~/.acp/identity.json

# Alice's AgentCard now includes a self-signature:
# GET /.well-known/acp.json →
# { "self": { ..., "identity": { "card_sig": "base64url...", "did": "did:acp:..." } } }
```

```bash
# Anyone can verify Alice's card — no CA, no registration:
curl -X POST http://alice.local:7901/verify/card \
  -d '{"name": "Alice", "identity": {"card_sig": "...", "public_key": "..."}, ...}'
# → {"valid": true, "did": "did:acp:...", "did_consistent": true}
```

How it works:
- AgentCard is signed with the agent's Ed25519 private key at serve time
- Signature covers canonical JSON (sorted keys, `card_sig` field excluded)
- Any receiver can verify using the `public_key` in `identity` — zero external service
- `did_consistent` cross-checks that `did:acp:` was derived from the same key

**Why it matters**: [A2A issue #1672](https://github.com/a2aproject/A2A/issues/1672) (62 comments, still open — three competing 3rd-party implementations in the thread but nothing merged into A2A spec). ACP v1.8+v1.9 ships the complete identity story today: sign your card, verify your peer's card, mutual verification at handshake.

New endpoints:
- `GET /verify/card` — verify local agent's own card
- `POST /verify/card` — verify any external AgentCard
- `capabilities.card_sig: true` — discoverable via AgentCard

---

## 2026-03-25

### Cancel Semantics — spec §10 (v1.5.2)

ACP now has an unambiguous answer to "what happens when you cancel a task":

- **Synchronous**: `:cancel` returns `{"status": "canceled"}` immediately — no async/deferred state
- **Idempotent**: calling `:cancel` on an already-canceled task returns `200` (not an error)
- **ERR_TASK_NOT_CANCELABLE (409)**: canceling a `completed` or `failed` task returns a clear error

This is documented in `spec/core-v1.3.md §10`. Compare: [A2A issue #1680](https://github.com/a2aproject/A2A/issues/1680) has been open for days with two competing proposals and no resolution.

---

## 2026-03-24

### NAT Traversal Signaling Layer (v1.4)

Three-level connection strategy, now with a real signaling layer:

```
Level 1: Direct P2P (same LAN, public IP) — instant
Level 2: UDP hole-punching via Cloudflare Worker signaling — handles most NAT
Level 3: HTTP relay fallback — always works, higher latency
```

The signaling server is privacy-first: addresses are stored ephemerally (30s TTL), one-time-read (auto-deleted after retrieval), no persistent address storage.

### Hybrid Identity (v1.5)

```bash
# Self-sovereign by default
acp-relay --name Alice
# did:acp:abc123...  (derived from Ed25519 key pair, works offline)

# Or hybrid: trust your org CA
acp-relay --name Alice --ca-cert /path/to/org-ca.pem
# identity.scheme: ed25519+ca
```

Compare: A2A is converging on `getagentid.dev` as a reference CA — an external service you have to register with. ACP's default requires no registration, no external service, no internet connection.

### Java SDK

```java
AcpClient client = new AcpClient("http://localhost:7901");
SendResult result = client.send("Hello from Java");
```

Zero external dependencies. Maven Central package: `dev.acp:acp-client`.

### Compatibility Certification

Two certification levels:
- **Level 1** (24 tests): Core messaging, task state machine, AgentCard discovery
- **Level 2** (planned): NAT traversal, identity, multi-peer routing

The reference relay implementation passes Level 1: 24/24 ✅

---

## 2026-03-23

### Real Multi-Agent Scenario Testing

First full end-to-end validation with real processes (not mocks):

- Scenario A: Single agent send/recv
- Scenario B: Orchestrator → Worker1 + Worker2 (team collaboration)  
- Scenario C: Multi-agent pipeline (A → B → C → A chain)
- Scenario D: Stress test (100 messages, concurrent sends, reconnection)
- Scenarios F+G: Error handling, disconnect/reconnect

All passing. See `tests/test_scenario_*.py`.

---

## 2026-03-22

### Docker

```bash
docker pull ghcr.io/kickflip73/acp-relay:latest
docker run -p 7801:7801 -p 7901:7901 ghcr.io/kickflip73/acp-relay:latest --name Alice
```

### DID Identity

`did:acp:<base58url(pubkey)>` — self-sovereign agent identity. No registry. No external resolver. Generated from your Ed25519 key pair on startup.

### Extension Mechanism

Agents can now declare capability extensions via URI:

```json
{
  "extensions": [
    "acp:ext:streaming-video",
    "acp:ext:long-running-tasks"
  ]
}
```

### HMAC Replay Protection

Previously: HMAC-SHA256 signing was optional but replay attacks were possible. Now: sliding window (60s, 1000-entry cache) rejects replayed message IDs. Zero breaking change — unsigned messages still accepted if `--secret` not set.

---

## Protocol Comparison Snapshot (as of 2026-03-26)

| Feature | ACP | A2A |
|---------|-----|-----|
| **LAN discovery** | ✅ **TCP port-scan `/peers/discover` — no mDNS required, finds any relay (v2.1-alpha)** | ❌ No LAN discovery mechanism in spec |
| **Offline delivery** | ✅ **Auto-queue on disconnect, auto-flush on reconnect (v2.0-alpha)** | ❌ No offline delivery — messages lost if peer is offline |
| Cancel semantics | ✅ Defined (§10), synchronous | ❓ Open issues #1680 + #1684 |
| Credential security | ✅ No push creds | ⚠️ Open issue #1681 |
| **AgentCard verification** | ✅ **Ed25519 self-sig + auto mutual verify (v1.8+v1.9)** | ❌ Open issue #1672 (62 comments, 3 competing impls, nothing merged) |
| **Mutual identity at handshake** | ✅ **Auto-verified on connect, `GET /peer/verify` (v1.9)** | ❌ No protocol-level handshake identity |
| Agent identifier | ✅ `did:acp:` (cryptographic, ownership-provable) | 🔄 PR#1079: random UUID (unverifiable) |
| SSE context propagation | ✅ context_id in all events | ⚠️ Spec contradiction (§4.2.2 vs §6.2, issue #1683) |
| Identity | ✅ Self-sovereign `did:acp:` | 🔄 Heading toward `getagentid.dev` (external CA) |
| Error Content-Type | ✅ `application/json` (explicit) | ⚠️ Ambiguous (open issue #1685) |
| Setup | `curl` + 2 steps | OAuth 2.0 + infra |
| Task states | 5 (simple) | 8 (complex) |
| Last code activity | Today | 10 days ago |

---

*Built by one person + J.A.R.V.I.S. · [GitHub](https://github.com/Kickflip73/agent-communication-protocol)*
