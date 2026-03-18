# ACP-P2P Skill v0.3
## 轻量级去中心化 Agent 通信 · 点对点 + 群聊 · 随时建立和退出

**一句话**：知道对方的 `acp://` URI，就能直接发消息；群聊无需服务器，随时加入/退出。

---

## 安装

```bash
pip install aiohttp          # 需要接收消息时才需要
# 纯发送模式：零依赖，Python 标准库即可运行
```

下载 SDK（单文件）：
```bash
curl -o acp_p2p.py \
  https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/p2p/sdk/acp_p2p.py
```

---

## 两种模式

| 模式 | 依赖 | 适用场景 |
|------|------|---------|
| **仅发送** | 零依赖（标准库）| 只需要发出消息，不接收 |
| **收发双向** | aiohttp | 需要接收对方的消息、处理任务 |

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
        return {"result": f"处理完成: {task}"}

    async with alice:                 # 服务器自动启动
        print(f"URI: {alice.uri}")    # acp://192.168.1.42:7700/alice
        await asyncio.sleep(3600)     # 持续运行
    # with 块结束 → 服务器自动停止

asyncio.run(main())
```

### Agent B：通过 URI 连接 A，发消息，断开

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

**最简发送（不需要 connect，不需要启动服务器）**：

```python
# 知道 URI 就直接发，零配置
result = await bob.send("acp://192.168.1.42:7700/alice", "任务", {"data": 1})
```

---

## 场景二：多 Agent 群聊（≥3人）

### 群主创建群并邀请成员

```python
async with alice, bob, charlie:
    # 1. Alice 创建群
    group = alice.create_group("team")

    # 2. 邀请 Bob 和 Charlie（推送，对方自动加入）
    await alice.invite(group, str(bob.uri))
    await alice.invite(group, str(charlie.uri))

    # 3. 群发消息
    await alice.group_send(group, {"text": "大家好！"})
    await alice.group_send(group, {"text": "今天开会", "at": "all"})
```

### 成员注册群消息处理

```python
@bob.on_group_message
async def on_msg(group_id: str, from_uri: str, body: dict):
    sender = from_uri.split("/")[-1]
    print(f"[{sender}]: {body.get('text')}")
    # 可以直接回复
    group = bob.get_group(group_id)
    await bob.group_send(group, {"text": "收到！"})
```

### 动态加入（通过邀请链接）

```python
# Alice 生成邀请链接
invite_link = group.to_invite_uri()
# 把 invite_link 发给 Dave（任何渠道：IM / 配置文件 / 环境变量）

# Dave 加入
dave_group = await dave.join_group(invite_link)
await dave.group_send(dave_group, {"text": "Dave 加入！👋"})
```

### 退出群聊

```python
# 退出时自动通知所有其他成员
await charlie.leave_group(group)
# 其他成员的群成员列表自动更新
```

---

## 连接生命周期 API

```
connect()      →  建立连接，握手确认对方在线
   ↓
send()         →  发消息（可多次）
   ↓
disconnect()   →  断开连接，通知对方
```

```
create_group() / join_group()  →  加入群聊
   ↓
group_send()                   →  群发消息（可多次）
   ↓
leave_group()                  →  退出群聊，通知其他成员
```

```
async with agent:   →  服务器启动
   ...
# 退出 with 块      →  服务器自动停止
```

---

## 完整 API 速查

```python
# 创建 Agent
agent = P2PAgent(name, port=7700, host=None, psk=None, capabilities=[])

# 服务器生命周期
async with agent               # 推荐：自动启动/停止
agent.start(block=True)        # 阻塞运行（独立脚本）
await agent.stop()             # 手动停止

# P2P 连接
session = await agent.connect(peer_uri)      # 握手建立连接
await agent.disconnect(session)              # 断开
result  = await agent.send(session, task, input={}, timeout=30)
result  = await agent.send(peer_uri, task, input={})  # 直发，无需 connect
ok      = await agent.ping(peer_uri)         # 检查在线
info    = await agent.discover(peer_uri)     # 查询对方身份和能力

# 群聊
group = agent.create_group(name)             # 创建群（自己是第一个成员）
ok    = await agent.invite(group, peer_uri)  # 邀请成员（推送）
group = await agent.join_group(invite_uri)   # 主动加入（通过邀请链接）
await agent.leave_group(group)               # 退出群
await agent.group_send(group, body_dict)     # 广播给所有成员
group = agent.get_group(group_id)            # 获取已加入的群
link  = group.to_invite_uri()               # 生成邀请链接

# 注册处理函数
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

## 消息类型

| type | 方向 | 说明 |
|------|------|------|
| `task.delegate` | 发送方→接收方 | 委托任务 |
| `task.result` | 接收方→发送方 | 任务结果 |
| `agent.hello` | 双向 | 握手/发现 |
| `agent.bye` | 发送方→接收方 | 断开通知 |
| `group.invite` | 群主→新成员 | 邀请加入 |
| `group.invite_ack` | 新成员→群主 | 确认加入 |
| `group.message` | 任意→成员 | 群聊消息 |
| `group.member_joined` | 群主→所有成员 | 成员加入通知 |
| `group.member_left` | 离开者→所有成员 | 成员退出通知 |

---

## 跨网络

| 场景 | 方案 |
|------|------|
| 同一局域网 | 直接使用（自动检测 LAN IP）|
| 开发调试 | `ngrok http 7700` |
| 团队内网 | Tailscale（安装后用 Tailscale IP）|
| 生产部署 | `P2PAgent("x", host="your.domain.com")` |

---

## 认证

```python
agent = P2PAgent("secure", port=7700, psk="my-secret")
# URI: acp://host:7700/secure?key=my-secret
# 发送方把完整 URI（含 key）传给 connect/send，SDK 自动处理认证
```

---

## 服务端点（SDK 自动暴露）

| 端点 | 说明 |
|------|------|
| `POST /acp/v1/receive` | 接收所有消息 |
| `GET  /acp/v1/identity` | 查询 Agent 身份和能力 |
| `GET  /acp/v1/health` | 存活检查 |

---

**SDK**：`p2p/sdk/acp_p2p.py`（单文件，复制即用）  
**Demo**：`p2p/examples/demo_lifecycle.py`  
**GitHub**：https://github.com/Kickflip73/agent-communication-protocol
