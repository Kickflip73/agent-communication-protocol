# ACP NAT Traversal Specification — v1.4

> Status: **Signaling Layer Complete** (v1.4 in progress — Worker v2.1 + Python helpers shipped; DCUtR integration pending)  
> Author: J.A.R.V.I.S. / Stark  
> Last updated: 2026-03-24  
> Implementation: `relay/acp_relay.py` — classes `STUNClient`, `DCUtRPuncher`; helpers `_relay_get_public_ip()`, `_relay_announce()`, `_relay_get_peer_addr()`; function `connect_with_holepunch()`  
> Worker: `relay/acp_worker.js` v2.1 — endpoints `/acp/myip`, `/acp/announce`, `/acp/peer`  
> Constraint: **stdlib only** — `asyncio`, `socket`, `struct`, `os`, `time`, `uuid`, `urllib` — no third-party deps

## Changelog

| Date | Change |
|------|--------|
| 2026-03-23 | Initial spec + STUNClient + DCUtRPuncher + connect_with_holepunch() |
| 2026-03-24 | Worker v2.1: `/acp/myip`, `/acp/announce`, `/acp/peer` (ephemeral, one-time-read) |
| 2026-03-24 | Python helpers: `_relay_get_public_ip()`, `_relay_announce()`, `_relay_get_peer_addr()` |
| 2026-03-24 | Tests: `test_nat_signaling.py` — 22/22 PASS |

## Implementation Status

| Component | Status | Commit |
|-----------|--------|--------|
| `STUNClient` (UDP STUN RFC 5389) | ✅ | 2026-03-23 |
| `DCUtRPuncher` (UDP hole punch state machine) | ✅ | 2026-03-23 |
| `connect_with_holepunch()` (3-level API) | ✅ | 2026-03-23 |
| Worker v2.1 signaling endpoints | ✅ | `8c162d4` |
| Python HTTP reflection helpers | ✅ | `8c162d4` |
| DCUtRPuncher: integrate HTTP reflection fallback | ⏳ | — |
| Integration test (real NAT environment) | ⏳ | — |

---

## 背景与动机

ACP 的核心设计原则是 **P2P 无中间人**。当前实现存在一个根本缺陷：

```
当前行为：
  acp:// → 直接 ws://IP:7801/token
  → 仅在 Agent A 的 IP:Port 对 Agent B 可路由时才成功
  → 双方都在 NAT 后面时必然失败
  → 用户被迫使用 --relay（Cloudflare Worker 转发）
  → 每条消息都经过第三方节点 ← 违背 P2P 初衷
```

**目标**：实现真正的 NAT 穿透，使 Relay 退化为真正的最后降级手段，而非常用路径。

---

## 技术选型

### 排除方案

| 方案 | 排除原因 |
|------|---------|
| WebRTC DataChannel | 浏览器生态遗产，依赖重，不适合 Agent 场景 |
| ICE/TURN 完整实现 | 过重，破坏「单文件零配置」原则 |
| 第三方 STUN 库（aiortc 等）| 违反 stdlib-only 约束 |

### 选定方案（v1.4 实现）：DCUtR-style UDP Hole Punching + Relay Signaling

**核心思路**：
1. 使用已有 Relay WebSocket 连接作为信令通道（无需额外信令基础设施）
2. 通过 stdlib-only STUN 实现发现公网 UDP 地址
3. 双方在协商的时刻 `t_punch` 同时发 UDP 探测包，打洞
4. 打洞成功后，在 NAT 映射上升级为直连 WebSocket（TCP）
5. Relay 连接关闭

**关键差异（相比原规划的 TCP 打洞方案）**：
- 用 UDP 打洞替代 TCP SYN 打洞（UDP 状态机更简单，NAT 支持更广）
- Relay 本身兼任 Signaling（不需要额外的 Cloudflare Worker 端点改造）
- 地址发现使用 STUN 而非 HTTP 反射（无需服务端改造）

---

## 架构设计

### 连接建立流程

```
Phase 1: Signaling（Cloudflare Worker，一次性地址交换）

  Agent A                Signaling               Agent B
    │                       │                       │
    ├──[POST /acp/new]──────►│                       │
    │◄──[session_id, token]──┤                       │
    │                        │                       │
    │  A 开放端口 7801        │    B 获得 token        │
    ├──[POST /acp/announce]──►│                       │
    │  body: {token, addr: "A的公网IP:port"}          │
    │                        │◄──[POST /acp/join]────┤
    │                        │   body: {token}        │
    │◄──[A的地址]─────────────┤──[B的地址]────────────►│
    │                        │                       │
    │  Signaling 完成，退出   │                       │
    │                        ×                       │

Phase 2: TCP Direct Connect（无服务器参与）

  Agent A ◄════════════ TCP WebSocket ════════════► Agent B
              真 P2P，消息不经过任何第三方
```

### 地址发现（获取公网 IP:Port）

```python
# 方法一：HTTP 反射（复用 Signaling Server）
GET https://signaling.host/acp/myip
→ {"ip": "1.2.3.4", "port": 54321}

# 方法二：STUN-lite（UDP echo，stdlib socket，无需 stun 库）
# 向 Signaling Server 发 UDP 包，Server 回显源地址
```

### Signaling Server 改造（Cloudflare Worker）

新增 3 个轻量端点，**不存储消息，不转发帧**：

```
POST /acp/announce  — 注册本机公网地址（TTL 30s）
GET  /acp/peer      — 获取对方的公网地址
GET  /acp/myip      — 获取本机公网 IP（HTTP 反射）
```

Worker 内存中的地址记录仅用于握手，握手完成后立即删除。

---

## 降级策略（三级）

```
Level 1: 直接连接（已有）
  条件：至少一方有公网 IP（或同内网）
  机制：ws://IP:7801/token 直连（3s timeout）
  延迟：最低

Level 2: UDP 打洞（v1.4 实现）★ DCUtR 风格
  条件：双方都在 NAT 后面，但 NAT 类型兼容
        （Full Cone / Restricted Cone / Port-Restricted Cone）
  机制：Relay WS 作信令 → STUN 发现公网地址 → 双方同时发 UDP 探测包
        → 打洞成功 → 在映射上升级 WebSocket 直连 → Relay 关闭
  延迟：+100~600ms（打洞握手一次性开销）
  成功率：~70%（覆盖主流家用/企业 NAT）
  超时：5s（打洞协调）+ 3s（UDP 等待回包）

Level 3: Relay 永久中转（已有，现为自动兜底）
  条件：对称 NAT / CGNAT / 打洞失败（约 30% 场景）
  机制：Relay 转发所有消息帧（不存储）
  延迟：最高（+50~200ms 额外跳）
  触发：自动，无需用户手动 --relay
```

**关键变化**：`--relay` 从「用户主动选择」变为「自动最后降级」，用户无感知。

---

## DCUtR 消息格式规范（v1.4）

### 消息传输

所有 DCUtR 消息在**现有 Relay WebSocket 连接**上传输，使用与普通 ACP 消息相同的 JSON 帧格式。接收方通过 `type` 字段区分 DCUtR 控制消息和业务消息。

### dcutr_connect（发起打洞请求）

```json
{
  "type":       "dcutr_connect",
  "addresses":  ["1.2.3.4:9001", "192.168.1.1:9001"],
  "session_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

| 字段 | 类型 | 必须 | 说明 |
|------|------|------|------|
| `type` | string | ✅ | 固定值 `"dcutr_connect"` |
| `addresses` | string[] | ✅ | 发起方的地址列表（`"IP:Port"` 格式）<br>顺序：公网优先，本地地址次之 |
| `session_id` | string | ✅ | UUID v4，标识此次打洞会话 |

### dcutr_sync（响应并同步打洞时刻）

```json
{
  "type":       "dcutr_sync",
  "addresses":  ["5.6.7.8:9002"],
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "t_punch":    1711180800.500
}
```

| 字段 | 类型 | 必须 | 说明 |
|------|------|------|------|
| `type` | string | ✅ | 固定值 `"dcutr_sync"` |
| `addresses` | string[] | ✅ | 响应方的地址列表 |
| `session_id` | string | ✅ | 与 `dcutr_connect` 相同的 UUID |
| `t_punch` | float | ✅ | Unix 时间戳（秒，含小数），双方同时发 UDP 的时刻<br>值为 `dcutr_sync` 发送时刻 + 500ms + 信令缓冲 |

### dcutr_result（打洞结果通知，可选）

```json
{
  "type":        "dcutr_result",
  "session_id":  "550e8400-e29b-41d4-a716-446655440000",
  "success":     true,
  "direct_addr": "5.6.7.8:9002"
}
```

| 字段 | 类型 | 必须 | 说明 |
|------|------|------|------|
| `type` | string | ✅ | 固定值 `"dcutr_result"` |
| `session_id` | string | ✅ | 与会话 UUID 对应 |
| `success` | bool | ✅ | 是否打洞成功 |
| `direct_addr` | string \| null | ✅ | 成功时为 `"IP:Port"`，失败时为 `null` |

### UDP 探测包格式

```
Payload (bytes): b"ACP-DCUtR-PROBE"   (15 bytes)
ACK     (bytes): b"ACP-DCUtR-ACK"     (13 bytes)
```

接收方通过 `data.startswith(b"ACP-DCUtR")` 识别探测包。

---

## UDP 打洞状态机

```
                    ┌──────────────────────────────────────────────────┐
                    │             DCUtRPuncher State Machine            │
                    └──────────────────────────────────────────────────┘

  ┌──────┐   start    ┌─────────────┐   STUN ok   ┌───────────┐
  │ IDLE │ ─────────► │ DISCOVERING │ ──────────► │ SIGNALING │
  └──────┘            └─────────────┘             └─────┬─────┘
                       STUN fails ──────────────────────┘ (use local addr only)
                                                          │
                                               send/recv dcutr_connect/sync
                                                          │
                                                    ┌─────▼──────┐
                                                    │  PUNCHING  │
                                                    └─────┬──────┘
                                                          │
                                          ┌───────────────┴───────────────┐
                                          │ UDP reply received             │ timeout (3s)
                                          ▼                                ▼
                                    ┌───────────┐                  ┌────────────┐
                                    │ CONNECTED │                  │   FAILED   │
                                    └───────────┘                  └────────────┘
                                  (return direct addr)          (return None → Level 3)
```

**时序（正常流程）：**

```
Initiator                                    Responder
    │                                             │
    │── STUN query ──────────────────────────────►│ (concurrent)
    │                                             │── STUN query
    │                                             │
    │── dcutr_connect (via Relay WS) ────────────►│
    │                                             │── send dcutr_sync (t_punch = now + 700ms)
    │◄─── dcutr_sync (via Relay WS) ─────────────│
    │                                             │
    │  wait until t_punch                         │  wait until t_punch
    │── UDP probe ×3 (100ms interval) ───────────►│
    │◄─────────────────────── UDP probe ×3 ───────│
    │                                             │
    │◄─────────────────────── UDP ACK ───────────│
    │── UDP ACK ──────────────────────────────────►│
    │                                             │
    │== upgrade to WebSocket (direct) ============│
    │── dcutr_result (success=true) ─────────────►│
    │                                             │
    │  close Relay WS                             │  close Relay WS
```

---

## 实现（v1.4）

### acp_relay.py 新增组件

```python
class STUNClient:
    """stdlib-only STUN Binding Request client (RFC 5389/8489)"""
    async def get_public_address(stun_host, stun_port, timeout=3.0) -> tuple[str,int] | None

class DCUtRPuncher:
    """DCUtR-style UDP hole punching state machine"""
    async def attempt(relay_ws, local_port) -> tuple[str,int] | None
    async def listen_for_dcutr(relay_ws, local_port) -> tuple[str,int] | None

async def connect_with_holepunch(ws_uri, relay_ws=None, local_udp_port=0):
    """Three-level connection strategy. Returns (websocket, is_direct: bool)"""
```

### stdlib-only 约束

| 模块 | 用途 |
|------|------|
| `asyncio` | 异步 I/O，事件循环，executor |
| `socket` | UDP socket，DNS 解析 |
| `struct` | STUN 二进制协议解析 |
| `os` | `os.urandom()` 生成 STUN 事务 ID |
| `time` | 打洞时刻同步 (`t_punch`) |
| `uuid` | DCUtR session_id 生成 |

**不引入任何第三方库。** `websockets` 库（已有依赖）仅用于 WebSocket 升级，不用于 UDP 打洞阶段。

### Cloudflare Worker 改造

```javascript
// 新增端点（现有转发逻辑不变，向后兼容）
// 注意：v1.4 实现中 Relay WS 本身兼任 Signaling，以下端点为可选增强
router.post('/acp/announce', handleAnnounce)   // 注册地址（TTL 30s）
router.get('/acp/peer',      handleGetPeer)    // 查询对方地址
router.get('/acp/myip',      handleMyIp)       // 返回请求方 IP（HTTP 反射备选）
```

---

## 链接格式兼容性

v1.4 不改变链接格式，向后完全兼容：

```
acp://IP:7801/tok_xxx     — 仍是主格式，v1.4 在底层尝试打洞
acp+wss://relay/acp/tok   — 仍然有效（用户显式指定 Relay）
```

自动降级对用户完全透明，链接格式不变。

---

## 成功指标

| 指标 | 当前 | v1.4 目标 |
|------|------|----------|
| 双 NAT 成功率 | 0%（必须 --relay） | ≥70% |
| 消息经过第三方 | 100%（--relay 时） | ≤30% |
| 连接建立延迟（P2P） | <100ms | <600ms（含打洞） |
| 用户操作变化 | 需手动 --relay | 零感知，自动选择 |

---

## 测试计划

1. `tests/unit/test_nat_traversal.py` — mock Signaling、打洞逻辑单元测试
2. `tests/integration/test_p2p_behind_nat.py` — 用 `iptables` 模拟 NAT 环境的集成测试
3. 真实环境验证：两台不同网络的机器各启动 Agent，验证打洞成功率

---

## 依赖

- **Python stdlib only**：`socket`、`asyncio`、`http.client`
- **无新第三方依赖**（保持「websockets only」原则）
- Cloudflare Worker 改造：约 50 行 JavaScript

---

## 关联

- 战略原则 §②：P2P 无中间人
- 现有 Relay 降级逻辑：`acp_relay.py` line 1107, 2595
- Cloudflare Worker：`black-silence-11c4.yuranliu888.workers.dev`
