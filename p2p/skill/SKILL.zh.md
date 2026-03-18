# ACP-P2P 接入指南 v0.3

**语言**：[English](SKILL.md) · **中文**

> 本文面向**已有 Agent 的开发者**。目标：最短时间内让你现有的 Agent 支持 ACP-P2P 通信。

---

## 前置条件

- Python 3.10+
- 已有一个 Agent（函数、类、LangChain、AutoGen 等均可）

---

## 安装（30秒）

```bash
pip install aiohttp

# 下载 SDK（单文件，无其他依赖）
curl -o acp_p2p.py \
  https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/p2p/sdk/acp_p2p.py
```

---

## 接入你现有的 Agent

### 场景 A：函数式 Agent（最常见）

你有一个处理请求的函数，想让它能被远程调用：

```python
# ── 你现有的代码（不需要改动）────────────────────────────────
def my_agent(query: str, context: dict) -> str:
    # ... 你的逻辑
    return "处理结果"

# ── 新增 4 行，接入 ACP ───────────────────────────────────────
from acp_p2p import P2PAgent
import asyncio

agent = P2PAgent("my-agent", port=7700)

@agent.on_task
async def handle(task: str, input_data: dict) -> dict:
    result = my_agent(task, input_data)   # 直接调用你现有的函数
    return {"output": result}

agent.start()
# 🔗 ACP URI: acp://192.168.1.42:7700/my-agent
```

### 场景 B：已有 HTTP 服务（FastAPI / Flask）

不需要换框架，在现有服务上**加一个路由**即可：

```python
# FastAPI 示例
from fastapi import FastAPI, Request
app = FastAPI()

# ── 你现有的路由（保持不变）──────────────────────────────────
@app.get("/health")
def health(): return {"ok": True}

# ── 新增：ACP 接收端点 ────────────────────────────────────────
@app.post("/acp/v1/receive")
async def acp_receive(request: Request):
    msg    = await request.json()
    task   = msg["body"]["task"]
    input_ = msg["body"].get("input", {})

    # 调用你现有的处理逻辑
    result = your_existing_handler(task, input_)

    return {
        "acp": "0.1",
        "type": "task.result",
        "from": "acp://your-host:8000/my-agent",
        "to": msg["from"],
        "id": f"msg_{__import__('uuid').uuid4().hex[:12]}",
        "ts": __import__('datetime').datetime.utcnow().isoformat() + "Z",
        "body": {"status": "success", "output": result},
        "reply_to": msg["id"],
    }
# 你的 ACP URI: acp://your-host:8000/my-agent
```

```python
# Flask 示例
from flask import Flask, request, jsonify
app = Flask(__name__)

@app.post("/acp/v1/receive")
def acp_receive():
    msg    = request.json
    result = your_existing_handler(msg["body"]["task"], msg["body"].get("input", {}))
    return jsonify({
        "acp": "0.1", "type": "task.result",
        "from": "acp://your-host:5000/my-agent",
        "to": msg["from"],
        "body": {"status": "success", "output": result},
        "reply_to": msg["id"],
    })
```

### 场景 C：LangChain Agent

```python
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain_openai import ChatOpenAI
from acp_p2p import P2PAgent
import asyncio

# ── 你现有的 LangChain Agent（保持不变）──────────────────────
llm       = ChatOpenAI(model="gpt-4")
executor  = create_openai_functions_agent(llm, tools=[...])

# ── 接入 ACP（新增 5 行）─────────────────────────────────────
acp = P2PAgent("langchain-agent", port=7700, capabilities=["qa", "reasoning"])

@acp.on_task
async def handle(task: str, input_data: dict) -> dict:
    # input_data 里可以传任何 LangChain 支持的参数
    result = await executor.ainvoke({"input": task, **input_data})
    return {"output": result["output"]}

acp.start()
```

### 场景 D：AutoGen Agent

```python
import autogen
from acp_p2p import P2PAgent
import asyncio

# ── 你现有的 AutoGen 配置（保持不变）─────────────────────────
config_list = [{"model": "gpt-4", "api_key": "..."}]
assistant   = autogen.AssistantAgent(
    "assistant",
    llm_config={"config_list": config_list}
)
user_proxy  = autogen.UserProxyAgent(
    "user_proxy",
    human_input_mode="NEVER",
    code_execution_config=False,
)

# ── 接入 ACP（新增 6 行）─────────────────────────────────────
acp = P2PAgent("autogen-agent", port=7700, capabilities=["chat", "code"])

@acp.on_task
async def handle(task: str, input_data: dict) -> dict:
    await user_proxy.a_initiate_chat(assistant, message=task, max_turns=5)
    last = user_proxy.last_message(assistant)
    return {"output": last["content"]}

acp.start()
```

### 场景 E：CrewAI

```python
from crewai import Agent, Task, Crew
from acp_p2p import P2PAgent
import asyncio

# ── 你现有的 CrewAI 定义（保持不变）──────────────────────────
researcher = Agent(role="Researcher", goal="Research topics", ...)
crew       = Crew(agents=[researcher], tasks=[...])

# ── 接入 ACP ─────────────────────────────────────────────────
acp = P2PAgent("crewai-agent", port=7700, capabilities=["research"])

@acp.on_task
async def handle(task: str, input_data: dict) -> dict:
    # 动态创建 Task 并执行
    t      = Task(description=task, agent=researcher)
    result = crew.kickoff(tasks=[t])
    return {"output": str(result)}

acp.start()
```

---

## 让你的 Agent 主动联系其他 Agent

接入之后，你的 Agent 不仅能被调用，也能主动发出请求：

```python
# 已知对方的 ACP URI，直接发——无需任何预先配置
result = await my_agent_instance.send(
    to="acp://192.168.1.50:7701/summarizer",
    task="帮我总结这篇文章",
    input={"text": "..."},
)
print(result["body"]["output"])

# 也可以先握手确认在线，再发消息
session = await my_agent_instance.connect("acp://192.168.1.50:7701/summarizer")
result  = await my_agent_instance.send(session, "总结", {"text": "..."})
await my_agent_instance.disconnect(session)

# 检查对方是否在线
online = await my_agent_instance.ping("acp://192.168.1.50:7701/summarizer")

# 查询对方的能力
info = await my_agent_instance.discover("acp://192.168.1.50:7701/summarizer")
print(info["capabilities"])   # ['summarize', 'translate']
```

---

## 加入群聊

让你的 Agent 参与多人协作：

```python
# 方式1：你来创建群，邀请其他 Agent
group = my_agent.create_group("project-alpha")
await my_agent.invite(group, "acp://host-b:7701/agent-b")
await my_agent.invite(group, "acp://host-c:7702/agent-c")

@my_agent.on_group_message
async def on_group_msg(group_id: str, from_uri: str, body: dict):
    print(f"群消息 [{from_uri.split('/')[-1]}]: {body.get('text')}")
    # 回复给群里所有人
    await my_agent.group_send(my_agent.get_group(group_id), {"text": "收到！"})

await my_agent.group_send(group, {"text": "任务开始！"})

# 方式2：你收到别人的邀请链接，主动加入
invite_link = "acpgroup://project-alpha:acp://...?members=..."
group = await my_agent.join_group(invite_link)
await my_agent.group_send(group, {"text": "我加入了！"})

# 退出群聊（自动通知所有成员）
await my_agent.leave_group(group)
```

---

## 完整接入示例（可直接运行）

把下面的代码保存为 `my_acp_agent.py`，修改 `YOUR_AGENT_LOGIC` 部分，运行即可：

```python
"""
ACP-P2P 接入模板
修改 YOUR_AGENT_LOGIC 函数，然后运行：python my_acp_agent.py
"""
import asyncio
from acp_p2p import P2PAgent


# ════════════════════════════════════════════════════════
#  ① 你现有的 Agent 逻辑（放在这里，不需要改结构）
# ════════════════════════════════════════════════════════
def YOUR_AGENT_LOGIC(task: str, input_data: dict) -> dict:
    # 示例：一个简单的文本处理 Agent
    text = input_data.get("text", task)
    return {
        "processed": text.upper(),
        "length": len(text),
        "task_received": task,
    }


# ════════════════════════════════════════════════════════
#  ② ACP 接入（固定模板，只改 name 和 port）
# ════════════════════════════════════════════════════════
agent = P2PAgent(
    name="my-agent",        # ← 改成你的 Agent 名称
    port=7700,              # ← 改成你想用的端口
    capabilities=["process"],   # ← 填写你的 Agent 能力
)

@agent.on_task
async def handle(task: str, input_data: dict) -> dict:
    return YOUR_AGENT_LOGIC(task, input_data)   # ← 调用你现有的函数


# ════════════════════════════════════════════════════════
#  ③ 可选：主动发消息给其他 Agent
# ════════════════════════════════════════════════════════
async def call_remote_agent(target_uri: str):
    result = await agent.send(
        to=target_uri,
        task="处理这段数据",
        input={"text": "Hello from my agent!"},
    )
    print("远程 Agent 返回:", result["body"]["output"])


# ════════════════════════════════════════════════════════
#  启动
# ════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("启动 Agent，分享 URI 给需要联系你的 Agent...")
    agent.start()   # 会打印 ACP URI，Ctrl+C 停止
```

---

## 跨机器通信

默认 URI 使用局域网 IP，跨机器访问需要对方能路由到你：

```bash
# 同一局域网：直接用（SDK 自动检测 LAN IP）

# 开发环境跨机器：用 ngrok
ngrok http 7700
# 得到类似：https://abc123.ngrok.io
# 在代码里指定 host：
agent = P2PAgent("my-agent", port=7700, host="abc123.ngrok.io")

# 生产服务器：指定公网 IP 或域名
agent = P2PAgent("my-agent", port=7700, host="your.server.com")
```

---

## 加认证

防止陌生人调用你的 Agent：

```python
# 创建时设置预共享密钥
agent = P2PAgent("my-agent", port=7700, psk="your-secret-key")
# URI 自动包含密钥: acp://host:7700/my-agent?key=your-secret-key

# 调用方只要拿到完整 URI（含 key），SDK 自动处理认证
result = await caller.send("acp://host:7700/my-agent?key=your-secret-key", ...)
```

---

## API 速查

```python
# 创建
agent = P2PAgent(name, port=7700, host=None, psk=None, capabilities=[])

# 启动 / 停止
agent.start()              # 阻塞（独立脚本用）
async with agent: ...      # 非阻塞（推荐，with 块结束自动停止）
await agent.stop()         # 手动停止

# 发送
await agent.send(to_uri_or_session, task, input={}, timeout=30)

# 连接管理
session = await agent.connect(peer_uri)    # 握手
await agent.disconnect(session)            # 断开
ok   = await agent.ping(peer_uri)          # 在线检测
info = await agent.discover(peer_uri)      # 查对方能力

# 群聊
group = agent.create_group(name)
ok    = await agent.invite(group, peer_uri)
group = await agent.join_group(invite_uri)
await agent.leave_group(group)
await agent.group_send(group, body_dict)
group = agent.get_group(group_id)
link  = group.to_invite_uri()

# 注册处理函数
@agent.on_task
async def handle(task: str, input: dict) -> dict: ...

@agent.on_group_message
async def on_msg(group_id: str, from_uri: str, body: dict): ...

@agent.on_message("custom.type")
async def on_custom(msg: dict) -> dict: ...
```

---

## 常见问题

**Q: 我的 Agent 不是 Python 写的，能用 ACP 吗？**  
A: 能。ACP 是 HTTP 协议。任何语言只需：① 监听 `POST /acp/v1/receive`；② 发送 HTTP POST。无需 Python SDK。

**Q: 对方 Agent 不在线，我的消息会丢失吗？**  
A: v0.3 不含重试机制。`send()` 会抛出 `ConnectionError`，调用方自行处理重试。v0.4 会加入可靠传输选项。

**Q: 一个进程里可以跑多个 Agent 吗？**  
A: 可以，每个用不同端口。

```python
async with agent_a, agent_b, agent_c:  # 三个 Agent 并行运行
    ...
```

**Q: 群聊有成员数量限制吗？**  
A: 没有硬限制。但 v0.3 是全量广播，成员越多每条消息的开销越大。大群场景建议等 v0.5 的 pub/sub 模式。

---

**SDK**：[`p2p/sdk/acp_p2p.py`](../sdk/acp_p2p.py)（单文件，无需安装包）  
**协议规范**：[`p2p/spec/acp-p2p-v0.1.zh.md`](../spec/acp-p2p-v0.1.zh.md)  
**可运行示例**：[`p2p/examples/`](../examples/)  
**GitHub**：https://github.com/Kickflip73/agent-communication-protocol
