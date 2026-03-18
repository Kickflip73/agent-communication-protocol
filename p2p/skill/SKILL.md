# ACP-P2P Skill
## 去中心化 Agent 通信协议 · 点对点 + 群聊

**版本**: 0.2 | **依赖**: Python 3.10+ + aiohttp

---

## 这是什么

ACP-P2P 让任意 Agent 之间直接通信，**无需任何第三方服务器**。

- 每个 Agent 有一个 `acp://` URI（即它的地址）
- 知道对方 URI → 直接发消息
- 多个 Agent → 建立无服务器群聊

---

## 安装（1条命令）

```bash
pip install aiohttp
curl -o acp_p2p.py \
  https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/p2p/sdk/acp_p2p.py
```

---

## 场景一：两个 Agent 互相通信

### Agent A（接收方）— 启动并分享 URI

```python
from acp_p2p import P2PAgent

agent = P2PAgent("alice", port=7700)

@agent.on_task
async def handle(task: str, input_data: dict) -> dict:
    # 在这里写你自己的处理逻辑
    return {"result": f"Alice 处理了: {task}"}

agent.start()
# 输出: 🔗 ACP URI: acp://192.168.1.42:7700/alice
# 把这个 URI 发给 Bob（复制粘贴、IM 消息、配置文件均可）
```

### Agent B（发送方）— 用 URI 直接联系 A

```python
from acp_p2p import P2PAgent

agent = P2PAgent("bob", port=7701)

# 把 Alice 的 URI 填进去，直接发消息
result = await agent.send(
    to="acp://192.168.1.42:7700/alice",   # Alice 的 URI
    task="请处理这个请求",
    input={"data": "some input"},
)

print(result["body"]["output"])
# → {'result': 'Alice 处理了: 请处理这个请求'}
```

**就这两步。两个 Agent 通信完毕。**

---

## 场景二：多 Agent 群聊（≥3人）

### 群主（Alice）创建群并邀请成员

```python
from acp_p2p import P2PAgent
import asyncio

async def main():
    alice = P2PAgent("alice", port=7700)

    # 注册群消息处理函数
    @alice.on_group_message
    async def on_msg(group_id: str, from_uri: str, body: dict):
        print(f"[群消息] {from_uri.split('/')[-1]}: {body.get('text')}")

    async with alice:
        # 1. 创建群
        group = alice.create_group("my-group")
        print(f"邀请链接: {group.to_join_uri()}")

        # 2. 邀请其他 Agent（推送邀请，对方自动加入）
        await alice.invite(group, "acp://192.168.1.43:7701/bob")
        await alice.invite(group, "acp://192.168.1.44:7702/charlie")

        # 3. 发群消息（自动广播给所有成员）
        await alice.group_send(group, {"text": "大家好！"})

asyncio.run(main())
```

### Bob / Charlie（被邀请方）

```python
from acp_p2p import P2PAgent
import asyncio

async def main():
    bob = P2PAgent("bob", port=7701)

    @bob.on_group_message
    async def on_msg(group_id: str, from_uri: str, body: dict):
        print(f"[群消息] {from_uri.split('/')[-1]}: {body.get('text')}")
        # 可以直接回复
        group = bob.get_group(group_id)
        await bob.group_send(group, {"text": f"Bob 收到了！"})

    async with bob:
        # Bob 只需要启动并监听，等待 Alice 的邀请消息
        await asyncio.sleep(3600)

asyncio.run(main())
```

### 主动加入（通过邀请链接）

```python
# 如果 Alice 把 to_join_uri() 的结果发给了你
group = await agent.join_group("acpgroup://my-group:acp://...?members=...")
await agent.group_send(group, {"text": "我加入了！"})
```

---

## ACP URI 格式

```
acp://<host>:<port>/<agent-name>?caps=<能力列表>&key=<认证密钥>
```

| 字段 | 必须 | 说明 | 示例 |
|------|------|------|------|
| host | ✅ | IP 或域名 | `192.168.1.42`、`myagent.com` |
| port | ✅ | 监听端口 | `7700`（默认）|
| name | ✅ | Agent 名称 | `alice`、`worker-1` |
| caps | ❌ | 能力声明 | `summarize,translate` |
| key  | ❌ | 预共享认证密钥 | `mysecret` |

---

## 消息格式（标准 JSON）

所有通信都是 HTTP POST，消息体格式如下：

### 发送任务

```json
{
  "acp": "0.1",
  "id": "msg_abc123",
  "type": "task.delegate",
  "from": "acp://192.168.1.10:7701/bob",
  "to":   "acp://192.168.1.42:7700/alice",
  "ts": "2026-03-18T10:00:00Z",
  "body": {
    "task": "任务描述",
    "input": { "key": "value" }
  }
}
```

### 返回结果

```json
{
  "acp": "0.1",
  "type": "task.result",
  "from": "acp://192.168.1.42:7700/alice",
  "to":   "acp://192.168.1.10:7701/bob",
  "body": {
    "status": "success",
    "output": { "result": "..." }
  }
}
```

### 群聊消息

```json
{
  "acp": "0.1",
  "type": "group.message",
  "from": "acp://192.168.1.42:7700/alice",
  "to":   "acp://192.168.1.43:7701/bob",
  "body": {
    "group_id": "dev-team:acp://...",
    "text": "消息内容",
    "任何其他字段": "均可"
  }
}
```

---

## Agent 必须暴露的接口

你的 Agent 需要监听以下 HTTP 端点（SDK 自动处理）：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/acp/v1/receive` | POST | 接收所有 ACP 消息（必须）|
| `/acp/v1/identity` | GET | 返回身份和能力（推荐）|
| `/acp/v1/health` | GET | 存活检查 |

---

## 跨网络通信

| 场景 | 方案 | 操作 |
|------|------|------|
| 同一局域网 | 直接使用 | 用局域网 IP |
| 开发/调试 | ngrok | `ngrok http 7700` |
| 团队内网 | Tailscale | 安装后用 Tailscale IP |
| 生产部署 | 公网服务器 | `P2PAgent("x", host="1.2.3.4")` |

```python
# 指定公网/自定义 host
agent = P2PAgent("alice", port=7700, host="your.domain.com")
# → acp://your.domain.com:7700/alice
```

---

## 认证（可选）

```python
# 创建带密钥的 Agent
agent = P2PAgent("secure", port=7700, psk="my-secret-key")
# URI 自动包含密钥: acp://host:7700/secure?key=my-secret-key

# 发送方：URI 里带 key，SDK 自动处理
result = await caller.send("acp://host:7700/secure?key=my-secret-key", ...)
```

---

## API 速查

### P2PAgent

```python
# 创建
agent = P2PAgent(name, port=7700, host=None, psk=None, capabilities=[])

# 启动
agent.start(block=True)           # 阻塞运行（独立脚本）
async with agent:                  # 非阻塞（嵌入 async 代码）

# 点对点
await agent.send(to_uri, task, input={}, timeout=30)  # 发送任务，返回响应
await agent.discover(uri)          # 查询对方身份

# 群聊
group = agent.create_group(name)               # 创建群（自己是第一个成员）
await agent.invite(group, peer_uri)            # 邀请成员
group = await agent.join_group(join_uri)       # 主动加入（通过邀请链接）
await agent.group_send(group, body_dict)       # 广播给群里所有人
group = agent.get_group(group_id)              # 获取已加入的群

# 注册处理函数
@agent.on_task                                 # 处理 task.delegate
async def handle(task: str, input: dict) -> dict: ...

@agent.on_group_message                        # 处理群消息
async def on_msg(group_id: str, from_uri: str, body: dict): ...

@agent.on_message("custom.type")              # 处理自定义消息类型
async def on_custom(msg: dict) -> dict: ...
```

### ACPGroup

```python
group.group_id          # 群唯一 ID
group.members           # 成员 URI 列表
group.to_join_uri()     # 生成邀请链接
ACPGroup.from_join_uri(uri)  # 从链接恢复群对象
```

---

## 完整运行示例

```python
"""三个 Agent 群聊，复制即可运行"""
import asyncio
from acp_p2p import P2PAgent

async def main():
    alice   = P2PAgent("alice",   port=7810)
    bob     = P2PAgent("bob",     port=7811)
    charlie = P2PAgent("charlie", port=7812)

    @alice.on_group_message
    async def a(gid, src, body): print(f"Alice   ← {src.split('/')[-1]}: {body['text']}")

    @bob.on_group_message
    async def b(gid, src, body): print(f"Bob     ← {src.split('/')[-1]}: {body['text']}")

    @charlie.on_group_message
    async def c(gid, src, body): print(f"Charlie ← {src.split('/')[-1]}: {body['text']}")

    async with alice, bob, charlie:
        group = alice.create_group("team")
        await alice.invite(group, str(bob.uri))
        await alice.invite(group, str(charlie.uri))
        await asyncio.sleep(0.1)

        await alice.group_send(group, {"text": "Hello everyone!"})
        await asyncio.sleep(0.1)
        await bob.group_send(bob.get_group(group.group_id), {"text": "Hi Alice & Charlie!"})
        await asyncio.sleep(0.2)

asyncio.run(main())
```

---

## 故障排查

| 问题 | 原因 | 解决 |
|------|------|------|
| `ConnectionError: Cannot reach acp://...` | 对方未启动或端口被防火墙拦截 | 检查对方是否在运行；检查端口 |
| `401 Unauthorized` | PSK 不匹配 | 确认 URI 中的 `key=` 参数正确 |
| 群消息只有部分人收到 | 某成员离线 | 正常现象，v0.3 会加入重试 |
| 跨网收不到消息 | 使用了局域网 IP | 用 ngrok 或公网 IP |

---

**GitHub**: https://github.com/Kickflip73/agent-communication-protocol  
**SDK 单文件**: `p2p/sdk/acp_p2p.py`（复制即用）
