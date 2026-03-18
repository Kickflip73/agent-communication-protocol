# ACP-P2P Skill — 去中心化 Agent 通信

## 这是什么

ACP-P2P 让任意两个 Agent 直接通信，**无需任何第三方服务器**。

一个 `acp://` URI 就是一个 Agent 的完整"地址"——知道对方的 URI，就能直接发消息。

---

## 快速接入（3步）

### Step 1：安装

```bash
pip install aiohttp
```

下载 SDK 文件（单文件，无其他依赖）：

```bash
curl -o acp_p2p.py https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/p2p/sdk/acp_p2p.py
```

---

### Step 2：让你的 Agent 能接收消息

```python
from acp_p2p import P2PAgent

# 1. 创建 Agent（只需名字和端口）
agent = P2PAgent("my-agent", port=7700)

# 2. 注册任务处理函数（这是你自己的逻辑）
@agent.on_task
async def handle(task: str, input_data: dict) -> dict:
    # task = 对方发来的任务描述
    # input_data = 对方发来的输入数据
    # 返回任何 dict 作为结果
    result = your_own_logic(task, input_data)
    return {"output": result}

# 3. 启动（会打印你的 ACP URI）
agent.start()
# 输出: 🔗 ACP URI: acp://192.168.1.42:7700/my-agent
```

把打印出来的 **ACP URI** 分享给任何想联系你的 Agent。

---

### Step 3：主动发消息给另一个 Agent

```python
from acp_p2p import P2PAgent

agent = P2PAgent("caller", port=7701)

# 只要知道对方的 URI，就能直接发
result = await agent.send(
    to="acp://192.168.1.50:7700/other-agent",   # 对方的 URI
    task="Summarize this article",
    input={"text": "Long article content..."},
)

print(result["body"]["output"])  # 对方返回的结果
```

---

## ACP URI 格式说明

```
acp://<host>:<port>/<agent-name>?caps=<能力1,能力2>&key=<认证密钥>
```

| 部分 | 说明 | 示例 |
|------|------|------|
| `host` | IP 或域名 | `192.168.1.42`、`agent.example.com` |
| `port` | 监听端口（默认 7700）| `7700` |
| `agent-name` | Agent 唯一标识 | `summarizer`、`worker-a` |
| `caps` | 能力声明（可选）| `summarize,translate` |
| `key` | 认证密钥（可选）| `mysecret123` |

---

## 消息格式

所有消息都是标准 JSON，通过 HTTP POST 发送到对方的 `/acp/v1/receive`：

### 发送任务（task.delegate）

```json
{
  "acp": "0.1",
  "id": "msg_abc123",
  "type": "task.delegate",
  "from": "acp://192.168.1.10:7701/caller",
  "to":   "acp://192.168.1.42:7700/worker",
  "ts": "2026-03-18T10:00:00Z",
  "body": {
    "task": "Summarize this text",
    "input": { "text": "..." }
  }
}
```

### 返回结果（task.result）

```json
{
  "acp": "0.1",
  "id": "msg_xyz789",
  "type": "task.result",
  "from": "acp://192.168.1.42:7700/worker",
  "to":   "acp://192.168.1.10:7701/caller",
  "ts": "2026-03-18T10:00:01Z",
  "body": {
    "status": "success",
    "output": { "summary": "This article discusses..." }
  }
}
```

---

## 五种 Agent 发现方式

| 方式 | 适合场景 | 操作 |
|------|---------|------|
| **直接配置** | 固定拓扑 | 把 URI 写入 `.env` 或配置文件 |
| **带外交换** | 临时协作 | 把 URI 粘贴给对方（IM/邮件） |
| **共享文件** | 团队内部 | 把 URI 写入共享 Git 仓库的 `agents.json` |
| **mDNS** | 局域网 | 自动广播（见高级用法） |
| **二维码** | 移动/物理场景 | URI 编码为二维码 |

---

## 跨网络穿透

默认情况下 ACP URI 使用局域网 IP，跨网络需要穿透：

```bash
# 方案1：ngrok（最简单，适合开发测试）
ngrok http 7700
# 得到: https://abc123.ngrok.io → 你的 URI 变成 acp://abc123.ngrok.io:443/my-agent

# 方案2：Tailscale（团队推荐）
# 安装 Tailscale 后，用 Tailscale IP 替换局域网 IP

# 方案3：公网服务器
P2PAgent("my-agent", port=7700, host="your.public.ip")
```

---

## 带认证的安全连接

```python
# 接收方设置密钥
agent = P2PAgent("secure-agent", port=7700, psk="my-secret-key")
# URI 自动包含密钥: acp://192.168.1.42:7700/secure-agent?key=my-secret-key

# 发送方：URI 中已包含 key，SDK 自动处理认证
result = await sender.send(
    to="acp://192.168.1.42:7700/secure-agent?key=my-secret-key",
    task="...",
    input={},
)
```

---

## 查询对方身份

```python
# 发现对方的能力和信息
identity = await agent.discover("acp://192.168.1.42:7700/other-agent")
print(identity)
# {
#   "uri": "acp://...",
#   "name": "other-agent",
#   "capabilities": ["summarize", "translate"],
#   "acp_version": "0.1"
# }
```

---

## 完整示例：两个 Agent 协作

```python
import asyncio
from acp_p2p import P2PAgent

async def main():
    # ── Agent A：数据处理器 ──────────────────────────────────────
    processor = P2PAgent("processor", port=7700, capabilities=["process"])

    @processor.on_task
    async def process_data(task: str, input_data: dict) -> dict:
        numbers = input_data.get("numbers", [])
        return {"sum": sum(numbers), "avg": sum(numbers)/len(numbers) if numbers else 0}

    # ── Agent B：分析器（调用 A）────────────────────────────────
    analyzer = P2PAgent("analyzer", port=7701, capabilities=["analyze"])

    @analyzer.on_task
    async def analyze(task: str, input_data: dict) -> dict:
        # 委托给 processor
        result = await analyzer.send(
            to=str(processor.uri),
            task="Calculate statistics",
            input={"numbers": input_data.get("data", [])},
        )
        stats = result["body"]["output"]
        return {"report": f"Sum={stats['sum']}, Avg={stats['avg']:.2f}"}

    # 启动两个 Agent
    async with processor, analyzer:
        print(f"Processor: {processor.uri}")
        print(f"Analyzer:  {analyzer.uri}")

        # 外部触发 Analyzer
        result = await analyzer.send(
            to=str(analyzer.uri),
            task="Analyze this dataset",
            input={"data": [10, 20, 30, 40, 50]},
        )
        print(f"Report: {result['body']['output']['report']}")

asyncio.run(main())
```

---

## 接口参考

### P2PAgent

| 方法 | 说明 |
|------|------|
| `P2PAgent(name, port, host, psk, capabilities)` | 创建 Agent |
| `agent.start(block=True)` | 启动服务器 |
| `await agent.send(to, task, input, timeout)` | 发送任务，返回结果 |
| `await agent.discover(uri)` | 查询对方身份 |
| `@agent.on_task` | 注册任务处理函数 |
| `@agent.on_message(type)` | 注册特定消息类型处理函数 |
| `agent.uri` | 获取自己的 ACPURI 对象 |
| `str(agent.uri)` | 获取 URI 字符串 |

### ACPURI

| 属性/方法 | 说明 |
|-----------|------|
| `ACPURI.parse("acp://...")` | 解析 URI 字符串 |
| `uri.host`, `uri.port`, `uri.name` | 各字段 |
| `uri.caps` | 能力列表 |
| `str(uri)` | 转回 URI 字符串 |
| `uri.receive_url` | HTTP 接收端点 URL |

### 服务端点（自动暴露）

| 端点 | 说明 |
|------|------|
| `POST /acp/v1/receive` | 接收消息（核心） |
| `GET  /acp/v1/identity` | 返回自身信息 |
| `GET  /acp/v1/health` | 存活检查 |

---

## 常见问题

**Q: 需要公网 IP 才能用吗？**
A: 不需要。局域网内两个 Agent 直接用内网 IP 通信。跨网络才需要穿透。

**Q: 支持哪些语言？**
A: Python SDK 已就绪。其他语言只需实现：① 监听 `POST /acp/v1/receive`；② 发送 HTTP POST。任何语言都可以，无需 SDK。

**Q: 消息丢了怎么办？**
A: v0.1 不包含重试机制，调用方自行处理。v0.3 会加入可靠传输选项。

**Q: 和 ACP Gateway 模式可以混用吗？**
A: 完全兼容。消息格式相同，切换只需改连接方式。

---

## 源码

- SDK: `p2p/sdk/acp_p2p.py`（单文件，零依赖除 aiohttp）
- 示例: `p2p/examples/demo_p2p.py`
- 规范: `p2p/spec/acp-p2p-v0.1.md`
- GitHub: https://github.com/Kickflip73/agent-communication-protocol
