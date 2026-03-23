# NAT 穿透与网络接入指南

> ACP v1.4 新增 — DCUtR 风格 UDP 打洞，三级连接策略自动降级，用户零感知。

---

## 快速判断：我需要什么？

| 我的网络环境 | 对方网络环境 | 需要 Relay？ | 接入方式 |
|------------|------------|------------|---------|
| 有公网 IP | 任意 | 不需要 | 直连（Level 1）|
| 局域网内 | 同一局域网 | 不需要 | 直连（Level 1）|
| NAT 后面 | 有公网 IP | 不需要 | 直连（Level 1）|
| NAT 后面 | NAT 后面 | 需要（初始） | 自动 UDP 打洞（Level 2）|
| CGNAT | 任意 | 需要（永久） | Relay 兜底（Level 3）|

> ACP 自动按顺序尝试上面三个级别，**你不需要做任何配置**。

---

## ACP 三级连接策略（自动，用户零感知）

```
Level 1 ─ 直接连接（3s timeout）
  ├─ 条件：至少一方有公网 IP，或双方在同一内网
  ├─ 延迟：最低（< 100ms）
  └─ 失败 → Level 2

Level 2 ─ UDP 打洞（DCUtR 风格，5s timeout）★ v1.4 新增
  ├─ 条件：双方都在 NAT 后面，但 NAT 类型兼容
  ├─ 流程：
  │     1. 通过已有的 Relay 连接交换双方公网地址（STUN 发现）
  │     2. 双方在约定时刻（t_punch）同时发 UDP 探测包
  │     3. NAT 设备因为出站包而开放入站规则（打洞）
  │     4. 确认对方 UDP 回包，建立直连
  │     5. Relay 连接关闭，后续通信不再经过任何中间节点
  ├─ 成功率：~70%（覆盖 Full Cone / Restricted Cone NAT）
  ├─ 延迟：+100~600ms（打洞握手一次性开销）
  └─ 失败 → Level 3

Level 3 ─ Relay 永久中转（兜底）
  ├─ 条件：对称 NAT（Symmetric NAT）/ CGNAT / 打洞失败
  ├─ 机制：所有消息帧经过 Relay Server 转发（不存储）
  ├─ 延迟：额外 +50~200ms（取决于 Relay 位置）
  └─ 成功率：100%（只要能访问 Relay）
```

整个过程对**宿主应用完全透明**——无论走哪条路径，`/message:send` 和 `/stream` API 行为完全一致。

---

## 我需要部署 Relay Server 吗？

### 情况 A：我有公网 IP 的服务器

**不需要 Relay**。对方可以直接通过 `acp://你的IP:7801/token` 连接。

启动方式：
```bash
python3 acp_relay.py --name "MyAgent" --port 7801
```

ACP 会输出可分享的 `acp://` 链接，直接发给对方即可。

---

### 情况 B：双方都在 NAT 后面

v1.4 之前，这种场景必须手动指定 `--relay`。**v1.4 起完全自动**：ACP 先尝试 UDP 打洞升级到直连，失败才使用 Relay 兜底。

你仍然需要一个**公网可访问的 Relay 节点**作为信令服务器（用于初始握手和打洞协调）。选择：

#### 选项 1：自托管（推荐生产环境）

在任意有公网 IP 的 VPS 上运行：

```bash
# 在 VPS 上启动（保持运行）
python3 acp_relay.py --name "RelayNode" --port 7801

# 它会输出：
# acp://YOUR_VPS_IP:7801/tok_xxxxx
```

然后将这个链接分享给双方，双方各自连接即可。

#### 选项 2：Cloudflare Worker（快速体验）

使用默认公共 Relay（Cloudflare Worker）：

```bash
python3 acp_relay.py --name "MyAgent" --relay
```

> ⚠️ 不建议在生产环境依赖公共 Relay——它是无状态的，不提供 SLA 保证。

#### 选项 3：acp+wss:// 显式指定 Relay URL

```bash
python3 acp_relay.py --name "MyAgent" --relay --relay-url https://your-relay.example.com
```

---

### 情况 C：企业 / 团队内网

内网部署无需公网。在内网任意一台机器上启动：

```bash
python3 acp_relay.py --name "TeamRelay" --port 7801
```

所有内网 Agent 用内网 IP 连接，不经过任何公网节点。可以同时开启 mDNS 广播，让局域网内的 Agent 自动发现彼此：

```bash
python3 acp_relay.py --name "TeamRelay" --advertise-mdns
```

---

### 情况 D：CGNAT 用户（运营商级 NAT）

CGNAT（电信宽带常见）下，UDP 打洞成功率极低（多级 NAT 导致地址映射不一致）。ACP 会自动检测打洞失败并永久使用 Relay 兜底，**你不需要做任何额外配置**，只是需要一个可访问的 Relay 节点（同情况 B）。

---

## 自托管 Relay Server（完整部署指南）

### 最小启动

```bash
# 需要 Python 3.9+ 和 websockets
pip install websockets
python3 acp_relay.py --name "Relay" --port 7801
```

输出：
```
13:00:00 [acp] HTTP interface: http://127.0.0.1:7901
13:00:00 [acp] WebSocket: ws://0.0.0.0:7801
13:00:00 [acp] =============================================
13:00:00 [acp] ACP v1.4 — host mode ready
13:00:00 [acp]   Your link: acp://1.2.3.4:7801/tok_xxxxx
13:00:00 [acp]   Share this with the other Agent to connect
13:00:00 [acp] =============================================
```

### 端口说明

| 端口 | 协议 | 说明 |
|------|------|------|
| `7801` | WebSocket | Agent 互连（需公网开放）|
| `7901` | HTTP | 本地管理 API（仅 localhost）|

防火墙只需开放 **TCP 7801**（入站）。

### 健康检查

```bash
curl http://localhost:7901/status
# → {"connected": true, "acp_version": "1.4.0", ...}

curl http://localhost:7901/.well-known/acp.json
# → AgentCard JSON
```

### systemd 服务配置（Linux 生产部署）

```ini
# /etc/systemd/system/acp-relay.service
[Unit]
Description=ACP Relay Server
After=network.target

[Service]
Type=simple
User=acp
WorkingDirectory=/opt/acp
ExecStart=/usr/bin/python3 /opt/acp/acp_relay.py --name "ProductionRelay" --port 7801
Restart=on-failure
RestartSec=5s
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

```bash
# 安装并启动
sudo systemctl daemon-reload
sudo systemctl enable acp-relay
sudo systemctl start acp-relay
sudo systemctl status acp-relay

# 查看日志
sudo journalctl -u acp-relay -f
```

### Docker 部署

```bash
docker run -d \
  --name acp-relay \
  --restart unless-stopped \
  -p 7801:7801 \
  -e PYTHONUNBUFFERED=1 \
  ghcr.io/kickflip73/agent-communication-protocol/acp-relay:latest \
  --name ProductionRelay --port 7801
```

---

## DCUtR 技术细节（开发者参考）

### UDP 打洞原理

UDP 打洞（NAT Hole Punching）利用了大多数 NAT 设备的一个特性：

> 当你向外发出一个 UDP 包（出站），NAT 会在自身打开一个「洞」（映射记录），
> 允许从那个目标地址返回的 UDP 包通过。

DCUtR 的关键改进：**双方在同一时刻同时发包**。这确保双方的 NAT 在对方的包到达前已经打开了洞。

### 新增 ACP 消息类型

这些消息在 Relay WebSocket 连接上传输，用于协调打洞，不影响业务消息：

```json
// 1. 发起方 → 响应方：发起打洞请求
{
  "type": "dcutr_connect",
  "addresses": ["1.2.3.4:9001", "192.168.1.1:9001"],
  "session_id": "550e8400-e29b-41d4-a716-446655440000"
}

// 2. 响应方 → 发起方：同步打洞时刻
{
  "type": "dcutr_sync",
  "addresses": ["5.6.7.8:9002"],
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "t_punch": 1711180800.500
}

// 3. 发起方 → 响应方（可选）：通知结果
{
  "type": "dcutr_result",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "success": true,
  "direct_addr": "5.6.7.8:9002"
}
```

### STUN 地址发现

ACP 使用 Google 公共 STUN 服务器（`stun.l.google.com:19302`）发现公网 UDP 地址。
实现为纯 stdlib（约 120 行），无需 `aiortc`、`aioice` 等第三方库。

支持 STUN RFC 5389 / RFC 8489：
- XOR-MAPPED-ADDRESS（优先）
- MAPPED-ADDRESS（兜底）

### NAT 类型兼容性

| NAT 类型 | UDP 打洞成功率 | 说明 |
|---------|--------------|------|
| Full Cone NAT | ✅ 高（~95%）| 最友好，常见于家用路由器 |
| Restricted Cone NAT | ✅ 高（~85%）| 常见于企业防火墙 |
| Port-Restricted Cone NAT | ✅ 中（~70%）| 需要端口精确匹配 |
| Symmetric NAT | ❌ 低（~10%）| 每次出站映射不同端口，难以打洞 |
| CGNAT（运营商级）| ❌ 极低（~5%）| 多级 NAT，基本依赖 Relay |

---

## 常见问题

### Q: 打洞失败了怎么办？

无需手动处理。ACP 在 5 秒超时后自动降级到 Level 3（Relay 永久中转）。你的连接会继续工作，只是消息经过 Relay 中转。

### Q: 如何判断当前是否走了直连？

检查日志输出：
```
[connect] Level 1 direct connect succeeded   → 直连
[connect] Level 2 hole punch succeeded        → UDP 打洞直连
[connect] Level 3 relay fallback (permanent) → Relay 中转
```

或者查询 `/status` 端点（未来版本将添加 `connection_type` 字段）。

### Q: 延迟高怎么排查？

1. **Level 1/2**（直连）延迟高：通常是网络路由问题，与 ACP 无关
2. **Level 3**（Relay）延迟高：Relay 地理位置远，考虑自托管更近的 Relay
3. 打开调试日志：`PYTHONPATH=. python3 acp_relay.py --log-level DEBUG`

### Q: v1.4 和 v1.3 向后兼容吗？

完全兼容。`acp://` 链接格式不变，NAT 穿透对上层透明。v1.3 的 Agent 可以和 v1.4 的 Agent 正常通信，只是不会触发 Level 2 打洞流程（对方不理解 `dcutr_connect` 消息，ACP 会静默降级）。

### Q: 打洞使用了什么协议？

UDP（通用数据报协议）。打洞成功后，ACP 会在打洞建立的 NAT 映射上建立一个新的 **WebSocket（TCP）** 连接用于实际通信。UDP 只用于打洞阶段，不用于消息传输。

### Q: 需要开放防火墙端口吗？

- **Level 1**（有公网 IP 端）：需开放 TCP 7801 入站
- **Level 2**（UDP 打洞）：不需要预先开放端口，NAT 在打洞时自动开放
- **Level 3**（Relay）：只需出站 HTTPS/WebSocket，无需入站端口

---

## 相关链接

- [ACP NAT Traversal 规范 v1.4](../spec/nat-traversal-v1.4.md)
- [架构总览](../README.md)
- [CLI 参数参考](cli-reference.md)
- [集成指南](integration-guide.md)
