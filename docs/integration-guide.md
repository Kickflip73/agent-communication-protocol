# ACP Integration Guide

## 接入方式总览

| 场景 | 方案 | 代码量 |
|------|------|--------|
| 纯 Python，新项目 | `ACPAgent` + `InProcessBus` | **10 行** |
| 已有 FastAPI 服务 | `ACPMiddleware` | **5 行** |
| LangChain / LangGraph | `expose_as_acp()` | **2 行** |
| AutoGen | `expose_autogen_as_acp()` | **2 行** |
| 任意语言 | Docker Gateway + HTTP POST | **0 行代码** |
| 跨机器/跨网络 | Docker Gateway + WebSocket | **0 行代码** |

---

## 方案一：纯 Python（最简单）

适合：单机多 Agent，测试，快速原型

```python
from acp_sdk import ACPMessage, ACPAgent, InProcessBus

# 1. 定义你的 Agent（只需实现一个方法）
class MyAgent(ACPAgent):
    async def handle_task_delegate(self, msg: ACPMessage) -> ACPMessage:
        result = do_your_work(msg.body["input"])
        return ACPMessage.task_result(
            from_aid=self.aid, to_aid=msg.from_aid,
            status="success", output=result, reply_to=msg.id,
        )

# 2. 连接两个 Agent
bus = InProcessBus()
agent_a = MyAgent("did:acp:local:agent-a", bus)
agent_b = MyAgent("did:acp:local:agent-b", bus)

# 3. 发消息
result = await agent_a.send(
    ACPMessage.task_delegate("did:acp:local:agent-a", "did:acp:local:agent-b", "Do X", input={...})
)
```

**完整示例：** [examples/quickstart/demo_two_agents.py](../examples/quickstart/demo_two_agents.py)

---

## 方案二：Gateway + HTTP（跨机器/跨框架）

适合：不同语言的 Agent 互通，生产环境

```bash
# Step 1: 启动 ACP Gateway（一行命令）
docker run -p 8765:8765 acpprotocol/gateway:latest

# Step 2: 你的 Agent A 注册自己
curl -X POST http://localhost:8765/acp/v1/agents/register \
  -H "Content-Type: application/json" \
  -d '{
    "aid": "did:acp:local:agent-a",
    "info": {"name": "Agent A", "capabilities": ["summarize"]},
    "callback_url": "http://agent-a-host:8001/acp/callback"
  }'

# Step 3: Agent B 发消息给 Agent A
curl -X POST http://localhost:8765/acp/v1/messages \
  -H "Content-Type: application/json" \
  -d '{
    "acp": "0.1",
    "id": "msg_001",
    "type": "task.delegate",
    "from": "did:acp:local:agent-b",
    "to": "did:acp:local:agent-a",
    "ts": "2026-03-18T10:00:00Z",
    "body": {
      "task": "Summarize this text",
      "input": {"text": "..."}
    }
  }'
```

**你的 Agent 只需要：**
1. 暴露一个 `POST /acp/callback` 接口接收消息
2. 启动时注册到 Gateway

---

## 方案三：FastAPI 中间件（已有服务快速接入）

适合：你已经有一个 FastAPI 服务，想让它能被其他 Agent 调用

```python
from fastapi import FastAPI
from acp_sdk.integrations.fastapi_middleware import ACPMiddleware

app = FastAPI()

# 加这 5 行 👇
acp = ACPMiddleware(
    app,
    aid="did:acp:local:my-service",
    gateway="http://localhost:8765",
    capabilities=["summarize"],
)

@acp.task_handler("summarize")
async def handle_summarize(task: str, input: dict) -> dict:
    return {"summary": your_existing_logic(input["text"])}

# 你原有的路由完全不受影响 ✅
```

---

## 方案四：LangChain 集成（2 行）

```python
from acp_sdk.integrations.langchain import expose_as_acp, acp_agent_tool

# 把你的 LangGraph agent 暴露为 ACP agent（1 行）
expose_as_acp(your_langgraph_agent, aid="did:acp:local:lc-agent", gateway="http://localhost:8765")

# 把远程 ACP agent 当作 LangChain tool 来用（1 行）
remote_tool = acp_agent_tool("did:acp:local:remote-agent", gateway="http://localhost:8765")
```

---

## 方案五：任意语言（纯 HTTP，0 行 SDK 代码）

ACP 消息就是普通 JSON，任何能发 HTTP 请求的语言都能用。

**Go 示例：**
```go
body := map[string]interface{}{
    "acp": "0.1", "id": "msg_001", "type": "task.delegate",
    "from": "did:acp:local:go-agent", "to": "did:acp:local:py-agent",
    "ts": time.Now().Format(time.RFC3339),
    "body": map[string]interface{}{
        "task": "Analyze this data",
        "input": map[string]interface{}{"data": data},
    },
}
jsonBody, _ := json.Marshal(body)
http.Post("http://gateway:8765/acp/v1/messages", "application/json", bytes.NewBuffer(jsonBody))
```

**Java 示例：**
```java
String msg = """
    {"acp":"0.1","id":"msg_001","type":"task.delegate",
     "from":"did:acp:local:java-agent","to":"did:acp:local:py-agent",
     "ts":"%s","body":{"task":"Process invoice","input":{"id":123}}}
    """.formatted(Instant.now());
HttpClient.newHttpClient().send(
    HttpRequest.newBuilder()
        .uri(URI.create("http://gateway:8765/acp/v1/messages"))
        .POST(HttpRequest.BodyPublishers.ofString(msg))
        .header("Content-Type", "application/json").build(),
    HttpResponse.BodyHandlers.ofString()
);
```

---

## Agent 接入 Checklist

- [ ] 定义你的 Agent ID：`did:acp:<namespace>:<name>`
- [ ] 选择接入方式（见上表）
- [ ] 实现 `task.delegate` 处理逻辑
- [ ] 注册到 Gateway（或使用 InProcessBus）
- [ ] 测试：发一条 `task.delegate`，验证收到 `task.result`

完成！你的 Agent 现在可以和任何其他 ACP Agent 通信。
