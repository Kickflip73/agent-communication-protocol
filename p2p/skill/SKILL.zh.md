# ACP-P2P 使用指南 v0.3
## 轻量级去中心化 Agent 通信 · 点对点 + 群聊 · 随时建立和退出

**语言**：[English](SKILL.md) · **中文**

**一句话**：知道对方的 `acp://` URI，就能直接发消息；群聊无需服务器，随时加入/退出。

---

## 安装

```bash
pip install aiohttp          # 需要接收消息时才需要（纯发送无需任何依赖）
```

下载 SDK（单文件，复制即用）：

```bash
curl -o acp_p2p.py \
  https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/p2p/sdk/acp_p2p.py
```

---

## 两种使用模式

| 模式 | 依赖 | 适用场景 |
|------|------|---------|
| **仅发送** | 零依赖（Python 标准库）| 只需要发出消息，不接收 |
| **收发双向** | `pip install aiohttp` | 需要接收消息、处理任务 |

---

## 场景一：两个 Agent 互相通信

### Agent A：启动，打印 URI，等待消息

```python
from acp_p2p import P2PAgent
import asyncio

async def main():
    alice = P2PAgent("alice", port=7700)

    @alice.on_task
    async def handle(task: str, input_data: dict) -> dict:
        # 在这里写你自己的处理逻辑
        return {"result": f"处理完成: {task}"}

    async with alice:                  # 服务器自动启动
        print(f"URI: {alice.uri}")     # acp://192.168.1.42:7700/alice
        # 把这个 URI 发给 Bob（IM/配置文件/环境变量均可）
        await asyncio.sleep(3600)      # 持续运行
    # with 块结束 → 服务器自动停止

asyncio.run(main())
```

### Agent B：连接 A，发消息，断开

```python
from acp_p2p import P2PAgent
import asyncio

async def main():
    bob = P2PAgent("bob", port=7701)

    async with bob:
        # 建立连接（握手确认对方在线）
        session = await bob.connect("acp://192.168.1.42:7700/alice")
        print(session)   # Session(bob ↔ alice, CONNECTED)

        # 发消息
        result = await bob.send(session, "请处理这个", {"data": 42})
        print(result["body"]["output"])   # {'result': '处理完成: 请处理这个'}

        # 断开
        await bob.disconnect(session)
        print(session)   # Session(bob ↔ alice, CLOSED)

asyncio.run(main())
```

**最简发送（不需要 connect，不需要启动服务器）：**

```python
# 知道 URI 就能直接发，零配置
result = await bob.send("acp://192.168.1.42:7700/alice", "任务", {"data": 1})
```

---

## 场景二：多 Agent 群聊（≥3 人）

### 群主：创建群，邀请成员，发消息

```python
async with alice, bob, charlie:
    # 注册群消息处理
    @alice.on_group_message
    async def on_msg(group_id: str, from_uri: str, body: dict):
        sender = from_uri.split("/")[-1]
        print(f"[{sender}]: {body.get('text')}")

    # 1. 创建群
    group = alice.create_group("我的群")

    # 2. 邀请成员（推送，对方自动加入，无需对方主动操作）
    await alice.invite(group, str(bob.uri))
    await alice.invite(group, str(charlie.uri))

    # 3. 群发消息（自动广播给所有成员）
    await alice.group_send(group, {"text": "大家好！"})
    await alice.group_send(group, {"text": "今天开会", "time": "15:00"})
```

### 成员：接收群消息，发言

```python
@bob.on_group_message
async def on_msg(group_id: str, from_uri: str, body: dict):
    sender = from_uri.split("/")[-1]
    print(f"[{sender}]: {body.get('text')}")

    # 回复
    group = bob.get_group(group_id)
    await bob.group_send(group, {"text": "Bob 收到！"})
```

### 动态加入（通过邀请链接）

```python
# Alice 生成邀请链接
invite_link = group.to_invite_uri()
# 把 invite_link 通过任何渠道发给 Dave

# Dave 加入（自动通知所有现有成员）
dave_group = await dave.join_group(invite_link)
await dave.group_send(dave_group, {"text": "Dave 加入！大家好 👋"})
```

### 退出群聊

```python
# 退出时自动通知所有其他成员，他们的成员列表自动更新
await charlie.leave_group(group)
```

---

## 连接生命周期

```
【点对点】
connect(peer_uri)  →  建立连接，握手确认在线，返回 Session
send(session, ...) →  发消息（可多次）
disconnect(session)→  断开连接，通知对方

【群聊】
create_group(name)          →  创建群（自己是第一个成员）
invite(group, peer_uri)     →  邀请成员（推送，对方自动加入）
join_group(invite_uri)      →  主动加入（通过邀请链接）
group_send(group, body)     →  广播给所有成员
leave_group(group)          →  退出，通知所有成员

【服务器】
async with agent:  →  服务器启动
   ...
# 退出 with 块    →  服务器自动停止
await agent.stop() →  手动停止
```

---

## 完整 API 速查

```python
# ── 创建 Agent ──────────────────────────────────────────────────
agent = P2PAgent(
    name,
    port=7700,          # 监听端口
    host=None,          # None = 自动检测局域网 IP
    psk=None,           # 预共享认证密钥（可选）
    capabilities=[],    # 能力声明（可选）
)

# ── 服务器 ──────────────────────────────────────────────────────
async with agent               # 推荐：自动启动/停止
agent.start(block=True)        # 阻塞运行（独立脚本）
await agent.stop()             # 手动停止

# ── P2P 连接 ────────────────────────────────────────────────────
session = await agent.connect(peer_uri)          # 握手建立连接
await agent.disconnect(session)                  # 断开
result  = await agent.send(session, task, input={}, timeout=30)
result  = await agent.send(peer_uri, task, input={})  # 直发，无需 connect
ok      = await agent.ping(peer_uri)             # 检查在线（True/False）
info    = await agent.discover(peer_uri)         # 查询对方身份和能力

# ── 群聊 ────────────────────────────────────────────────────────
group  = agent.create_group(name)                # 创建群
ok     = await agent.invite(group, peer_uri)     # 邀请成员
group  = await agent.join_group(invite_uri)      # 主动加入
await agent.leave_group(group)                   # 退出群
await agent.group_send(group, body_dict)         # 广播消息
group  = agent.get_group(group_id)               # 获取已加入的群
link   = group.to_invite_uri()                   # 生成邀请链接

# ── 注册处理函数 ─────────────────────────────────────────────────
@agent.on_task
async def handle(task: str, input: dict) -> dict: ...

@agent.on_group_message
async def on_msg(group_id: str, from_uri: str, body: dict): ...

@agent.on_message("custom.type")
async def on_custom(msg: dict) -> dict: ...
```

---

## ACP URI 格式

```
acp://<host>:<port>/<name>?caps=<能力>&key=<认证密钥>
```

| 字段 | 必须 | 说明 |
|------|------|------|
| host | ✅ | IP 或域名 |
| port | ✅ | 监听端口（默认 7700）|
| name | ✅ | Agent 唯一名称 |
| caps | ❌ | 能力声明，逗号分隔 |
| key  | ❌ | 预共享认证密钥 |

---

## 消息格式参考

```json
{
  "acp": "0.1",
  "id": "msg_abc123",
  "type": "task.delegate",
  "from": "acp://192.168.1.10:7701/bob",
  "to":   "acp://192.168.1.42:7700/alice",
  "ts":   "2026-03-18T10:00:00Z",
  "body": {
    "task": "任务描述",
    "input": { "key": "value" }
  }
}
```

| 字段 | 说明 |
|------|------|
| `acp` | 协议版本 |
| `id` | 消息唯一 ID |
| `type` | 消息类型（见下表）|
| `from` / `to` | 发送方 / 接收方 ACP URI |
| `ts` | UTC 时间戳（ISO 8601）|
| `body` | 消息内容（任意 JSON）|
| `correlation_id` | 会话关联 ID（可选）|
| `reply_to` | 回复哪条消息的 ID（可选）|

---

## 跨网络通信

| 场景 | 方案 |
|------|------|
| 同一局域网 | 直接使用（SDK 自动检测 LAN IP）|
| 开发调试 | `ngrok http 7700`，得到公网 URI |
| 团队内网 | Tailscale（安装后用 Tailscale IP）|
| 生产部署 | `P2PAgent("alice", host="your.domain.com")` |

---

## 认证

```python
# 创建带密钥的 Agent
agent = P2PAgent("secure", port=7700, psk="my-secret")
# URI 自动包含密钥: acp://host:7700/secure?key=my-secret

# 发送方：完整 URI 传入，SDK 自动处理
result = await caller.send("acp://host:7700/secure?key=my-secret", "任务", {})
```

---

## 服务端点（SDK 自动暴露）

| 端点 | 方法 | 说明 |
|------|------|------|
| `/acp/v1/receive` | POST | 接收所有 ACP 消息（必须）|
| `/acp/v1/identity` | GET | 返回身份和能力 |
| `/acp/v1/health` | GET | 存活检查 |

---

## 完整运行示例（复制即可运行）

```python
"""
3 个 Agent 群聊 + 动态加入/退出
运行：python this_file.py
"""
import asyncio
from acp_p2p import P2PAgent

async def main():
    alice   = P2PAgent("alice",   port=7810)
    bob     = P2PAgent("bob",     port=7811)
    charlie = P2PAgent("charlie", port=7812)
    dave    = P2PAgent("dave",    port=7813)

    @alice.on_group_message
    async def a(gid, src, body): print(f"Alice   ← {src.split('/')[-1]}: {body.get('text')}")
    @bob.on_group_message
    async def b(gid, src, body): print(f"Bob     ← {src.split('/')[-1]}: {body.get('text')}")
    @charlie.on_group_message
    async def c(gid, src, body): print(f"Charlie ← {src.split('/')[-1]}: {body.get('text')}")
    @dave.on_group_message
    async def d(gid, src, body): print(f"Dave    ← {src.split('/')[-1]}: {body.get('text')}")

    async with alice, bob, charlie, dave:
        # 建群
        group = alice.create_group("team")
        await alice.invite(group, str(bob.uri))
        await alice.invite(group, str(charlie.uri))
        await asyncio.sleep(0.1)

        # 群聊
        await alice.group_send(group, {"text": "项目启动！"})
        await asyncio.sleep(0.1)
        await bob.group_send(bob.get_group(group.group_id), {"text": "Bob ready ✅"})
        await asyncio.sleep(0.1)

        # Dave 动态加入
        dave_group = await dave.join_group(group.to_invite_uri())
        await dave.group_send(dave_group, {"text": "Dave 加入 👋"})
        await asyncio.sleep(0.1)

        # Charlie 退出
        await charlie.leave_group(charlie.get_group(group.group_id))
        print(f"\n剩余成员: {[m.split('/')[-1] for m in group.members]}")
        await asyncio.sleep(0.1)

asyncio.run(main())
```

---

## 故障排查

| 问题 | 原因 | 解决 |
|------|------|------|
| `ConnectionError: Cannot reach` | 对方未启动或端口被防火墙拦截 | 检查对方是否运行；检查端口 |
| `401 Unauthorized` | PSK 不匹配 | 确认 URI 中 `key=` 参数正确 |
| 群消息部分成员收不到 | 对方暂时离线 | 正常现象，v0.4 加入重试 |
| 跨网收不到消息 | 使用了局域网 IP | 改用 ngrok 或公网 IP |
| `No module named 'aiohttp'` | 未安装依赖 | `pip install aiohttp` |

---

**SDK 单文件**：[`p2p/sdk/acp_p2p.py`](../sdk/acp_p2p.py)（复制即用）  
**协议规范**：[`p2p/spec/acp-p2p-v0.1.zh.md`](../spec/acp-p2p-v0.1.zh.md)  
**GitHub**：https://github.com/Kickflip73/agent-communication-protocol
