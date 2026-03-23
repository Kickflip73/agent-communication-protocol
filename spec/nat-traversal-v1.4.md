# ACP NAT Traversal Specification — v1.4

> Status: **Planned** (target: v1.4)  
> Author: J.A.R.V.I.S. / Stark  
> Last updated: 2026-03-23

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
| 纯 UDP 打洞 | websockets 库基于 TCP，切换传输层成本高 |

### 选定方案：TCP Hole Punching + Signaling-assisted

**核心思路**：利用现有 Signaling Server（Cloudflare Worker）做一次性地址交换，然后双方直接 TCP 连接。Signaling Server 不转发任何消息帧。

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
Level 1: 直接连接（当前）
  条件：至少一方有公网 IP（或同内网）
  机制：ws://IP:7801/token 直连
  延迟：最低

Level 2: TCP 打洞（v1.4 新增）★ 核心改进
  条件：双方都在 NAT 后面，但 NAT 类型兼容（Full Cone / Restricted Cone）
  机制：Signaling 交换公网地址 → 双方同时 SYN → NAT 打洞
  延迟：+100~500ms（打洞握手）
  成功率：~70%（覆盖主流家用/企业 NAT）

Level 3: Relay 转发（当前 --relay）
  条件：对称 NAT 或打洞失败（约 30% 场景）
  机制：Cloudflare Worker 转发所有帧
  延迟：最高（+50~200ms 额外跳）
  触发：自动，无需用户手动 --relay
```

**关键变化**：`--relay` 从「用户主动选择」变为「自动最后降级」，用户无感知。

---

## 实现规划

### acp_relay.py 改动

```python
async def _connect_with_nat_traversal(link: str) -> websockets.WebSocketClientProtocol:
    """
    三级连接策略：
    1. 尝试直连（Level 1）
    2. 尝试 TCP 打洞（Level 2）
    3. 降级 Relay（Level 3）
    """
    # Level 1: 直连（现有逻辑，timeout 降至 3s）
    try:
        return await asyncio.wait_for(
            _proxy_ws_connect(link_to_ws_uri(link)), timeout=3.0
        )
    except (OSError, asyncio.TimeoutError):
        pass

    # Level 2: TCP 打洞
    try:
        peer_addr = await _signaling_get_peer_addr(token)
        my_addr   = await _signaling_announce(token)
        return await asyncio.wait_for(
            _tcp_hole_punch(peer_addr, my_addr), timeout=8.0
        )
    except Exception:
        pass

    # Level 3: Relay 降级（自动，无需 --relay）
    return await _relay_connect(token)
```

### 新增函数

```python
async def _get_public_addr() -> tuple[str, int]:
    """通过 Signaling Server HTTP 反射获取公网 IP:Port"""

async def _signaling_announce(token: str) -> str:
    """向 Signaling Server 注册公网地址，返回自己的地址字符串"""

async def _signaling_get_peer_addr(token: str) -> str:
    """从 Signaling Server 获取对方地址"""

async def _tcp_hole_punch(peer_addr: str, my_addr: str) -> websockets.WebSocketClientProtocol:
    """TCP 打洞：双方同时发起 SYN，利用 NAT 映射建立直连"""
```

### Cloudflare Worker 改造

```javascript
// 新增端点（现有转发逻辑不变，向后兼容）
router.post('/acp/announce', handleAnnounce)   // 注册地址（TTL 30s）
router.get('/acp/peer',      handleGetPeer)    // 查询对方地址
router.get('/acp/myip',      handleMyIp)       // 返回请求方 IP
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
