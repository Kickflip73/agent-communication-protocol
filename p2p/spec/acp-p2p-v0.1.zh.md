# ACP-P2P 协议规范 v0.1

**状态**：草案  
**语言**：[English](acp-p2p-v0.1.md) · **中文**  
**日期**：2026-03-18  
**许可**：Apache 2.0

---

## 核心设计原则

1. **零中心化**：任意两个 Agent 之间无需任何第三方服务器
2. **URI 即身份**：一个 `acp://` URI 包含连接所需的全部信息
3. **带外信令**：连接信息可通过任何渠道交换（IM 消息、配置文件、环境变量、二维码）
4. **传输无关**：底层可以是 HTTP、WebSocket、Unix Socket，乃至 stdin/stdout
5. **显式生命周期**：连接有明确的建立（`connect`）和关闭（`disconnect`）过程

---

## ACP URI 格式

```
acp://<host>:<port>/<agent-name>?key=<psk>&caps=<cap1,cap2>
```

**示例：**
```
acp://192.168.1.42:7700/summarizer
acp://192.168.1.42:7700/summarizer?caps=summarize,translate
acp://agent.example.com:7700/orchestrator?key=mysecret&caps=delegate
```

### 字段说明

| 字段 | 必须 | 默认值 | 说明 |
|------|------|--------|------|
| host | ✅ | — | IP 地址或域名 |
| port | ✅ | 7700 | Agent HTTP 监听端口 |
| agent-name | ✅ | — | Agent 唯一名称（URI path 部分）|
| key | ❌ | — | 预共享认证密钥（PSK）|
| caps | ❌ | — | 能力列表，逗号分隔 |

---

## 消息格式

所有消息均为 JSON，通过 HTTP POST 发送到对方的 `/acp/v1/receive`。

### 基础信封

```json
{
  "acp": "0.1",
  "id": "msg_<随机字符串>",
  "type": "<消息类型>",
  "from": "acp://发送方URI",
  "to":   "acp://接收方URI",
  "ts":   "2026-03-18T10:00:00Z",
  "body": { ... },
  "correlation_id": "可选，关联同一会话的多条消息",
  "reply_to":       "可选，回复哪条消息的ID"
}
```

### 消息类型一览

| type | 方向 | 说明 |
|------|------|------|
| `task.delegate` | A → B | 委托任务 |
| `task.result` | B → A | 返回任务结果 |
| `agent.hello` | 双向 | 握手/探活 |
| `agent.bye` | 发送方 → 接收方 | 断开连接通知 |
| `group.invite` | 群主 → 新成员 | 邀请加入群聊 |
| `group.invite_ack` | 新成员 → 群主 | 确认加入 |
| `group.message` | 任意成员 → 其他成员 | 群聊消息 |
| `group.member_joined` | 群主 → 全体成员 | 新成员加入通知 |
| `group.member_left` | 离开者 → 全体成员 | 成员退出通知 |
| `error` | 任意 | 错误回复 |

---

## 点对点通信流程

### Phase 1：发现（建立连接前，获取对方 URI）

| 方式 | 适用场景 |
|------|---------|
| 直接配置 | 固定拓扑，写入配置文件或环境变量 |
| 带外交换 | 把 URI 通过 IM/邮件发给对方 |
| 共享文件 | 写入共享 Git 仓库的 `agents.json` |
| mDNS 广播 | 局域网内自动发现（zeroconf）|
| 二维码 | URI 编码为二维码，扫码建立连接 |

### Phase 2：握手（connect）

```
发送方                              接收方
  │                                    │
  │  POST /acp/v1/receive              │
  │  Body: agent.hello                 │
  │ ─────────────────────────────────► │
  │                                    │
  │  200 OK                            │
  │  Body: agent.hello (reply)         │
  │ ◄───────────────────────────────── │
```

握手确认对方在线，返回对方的名称和能力列表。

### Phase 3：消息收发

**同步模式（请求-响应）：**

```
发送方                              接收方
  │  POST /acp/v1/receive              │
  │  Body: task.delegate               │
  │ ─────────────────────────────────► │
  │                                    │  处理任务
  │  200 OK                            │
  │  Body: task.result                 │
  │ ◄───────────────────────────────── │
```

**异步模式（发送后回调）：**

```
发送方                              接收方
  │  POST /acp/v1/receive              │
  │  Body: task.delegate               │
  │ ─────────────────────────────────► │
  │  202 Accepted                      │
  │ ◄───────────────────────────────── │
  │                                    │  处理中...
  │  POST /acp/v1/receive              │
  │  Body: task.result (回调)          │
  │ ◄───────────────────────────────── │
```

### Phase 4：断开（disconnect）

```
发送方                              接收方
  │  POST /acp/v1/receive              │
  │  Body: agent.bye                   │
  │ ─────────────────────────────────► │
  │  202 Accepted                      │
  │ ◄───────────────────────────────── │
```

---

## 群聊流程

### 建群与邀请

```
Alice.create_group("team")
  → group_id = "team:acp://alice_uri"
  → invite_uri = "acpgroup://team:acp://...?members=acp://alice"

Alice.invite(group, Bob_URI)
  → POST Bob /acp/v1/receive  {type: "group.invite", invite_uri: ...}
  ← 200 {type: "group.invite_ack", status: "joined"}
  → POST Charlie /acp/v1/receive  {type: "group.member_joined", new_member: Bob, all_members: [...]}

Alice.invite(group, Charlie_URI)
  → （同上）
```

### 动态加入（通过邀请链接）

```
invite_uri = group.to_invite_uri()
# 通过任何渠道传给 Dave

Dave.join_group(invite_uri)
  → 解析出所有现有成员
  → POST 每个成员 {type: "group.member_joined", new_member: Dave}
  → 所有成员更新本地成员列表
```

### 群发消息

```
Alice.group_send(group, {"text": "大家好！"})
  → 并发 POST 给 Bob、Charlie、Dave
  → 每人的 on_group_message 回调触发
```

### 退出群聊

```
Charlie.leave_group(group)
  → POST 每个其他成员 {type: "group.member_left", leaving_member: Charlie}
  → 所有成员从本地列表移除 Charlie
  → Charlie 的本地群状态标记为 inactive
```

---

## Agent 必须暴露的接口

```
POST /acp/v1/receive          接收所有 ACP 消息（必须）
GET  /acp/v1/identity         返回自身 URI、名称、能力列表（推荐）
GET  /acp/v1/health           存活检查（推荐）
```

### `/acp/v1/identity` 响应示例

```json
{
  "uri": "acp://192.168.1.42:7700/summarizer",
  "name": "Summarizer Agent",
  "capabilities": ["summarize", "translate"],
  "acp_version": "0.1",
  "protocol": "acp-p2p",
  "active_sessions": 2,
  "groups": ["dev-team:acp://..."]
}
```

---

## 安全模型

### v0.1：预共享密钥（PSK）

URI 中携带密钥：`acp://host:7700/agent?key=my-secret`

发送方请求头：
```
X-ACP-PSK: my-secret
```

接收方校验，不匹配返回 401。

### v0.4（规划中）：Ed25519 签名

- 每个 Agent 生成 Ed25519 密钥对
- 消息体携带签名字段 `sig`
- 接收方用发送方公钥验签，防止伪造

---

## 跨网络穿透

当两个 Agent 不在同一局域网时：

| 方案 | 适用场景 | 操作 |
|------|---------|------|
| 公网 IP | 服务器部署 | 直接使用公网 IP |
| ngrok | 开发测试 | `ngrok http 7700` → 得到公网 URI |
| frp / nps | 自建穿透 | 配置内网穿透规则 |
| Tailscale | 团队内网 | 安装后直接用 Tailscale IP |
| Cloudflare Tunnel | 生产环境 | 零开放端口，安全性高 |

---

## 与 ACP Gateway 模式对比

| 维度 | Gateway 模式（中心化）| P2P 模式（去中心化）|
|------|----------------------|---------------------|
| 第三方依赖 | 需要 Gateway 服务 | 零依赖 |
| Agent 发现 | 注册中心 | URI 带外交换 |
| 通信延迟 | 多一跳 | 最低延迟 |
| 适用场景 | 动态 Agent 池、大规模 | 已知拓扑、小规模 |
| 离线能力 | 依赖 Gateway | 完全离线可用 |
| 部署复杂度 | 需运维 Gateway | 无需运维 |

两种模式**互补而非替代**：固定拓扑用 P2P，动态发现用 Gateway。

---

## 变更历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v0.1 | 2026-03-18 | 初始草案：URI 格式、消息类型、P2P 流程 |
| v0.2 | 2026-03-18 | 增加群聊：create/invite/join/group_send |
| v0.3 | 2026-03-18 | 增加生命周期：connect/disconnect/leave_group |
