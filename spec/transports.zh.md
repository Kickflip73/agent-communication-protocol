# ACP 传输绑定规范

**状态**：草案  
**版本**：0.1  
**语言**：[English](transports.md) · **中文**

本文档定义三种标准 ACP 传输绑定。符合 ACP 规范的实现 MUST 至少支持其中一种。

---

## 概览

ACP 传输无关：所有传输层使用完全相同的消息信封，仅帧格式和投递机制不同。

| 传输 | 适用场景 | 延迟 | 配置复杂度 |
|------|---------|------|-----------|
| **stdio** | 子进程 Agent、CLI 工具、同机器 | ~1ms | 零——无端口，无配置 |
| **HTTP/SSE** | 网络 Agent、云服务、跨主机 | ~10ms | 启动 HTTP 服务器 |
| **TCP** | 高吞吐管道、同数据中心 | ~1ms | 打开 TCP 套接字 |

---

## 1. stdio 传输

### 1.1 概述

stdio 传输通过标准输入输出流实现两个 Agent 之间的通信。这是最简单的传输方式：无需网络配置，无端口，无 TLS。一个 Agent 以子进程方式启动另一个，或两个进程通过管道连接。

这种设计借鉴自 MCP 的 stdio 传输——正是这种方式让 MCP 易于采用。

### 1.2 消息格式

消息采用**换行符分隔 JSON**（NDJSON）：每行一个 JSON 对象，以 `\n` 结尾。

```
<json对象>\n
<json对象>\n
...
```

- 每行 MUST 是完整、合法的 ACP 消息信封
- 行 MUST 以 `\n` 结尾（Unix 换行）
- 实现 MUST NOT 输出不完整的行
- 读取方 MUST 忽略空行

### 1.3 消息流

```
┌─────────────────────────────────────────────────────────────┐
│  进程 A（发送方/父进程）                                     │
│                                                             │
│  写入 agent_b.stdin ──────────────────────────────►        │
│               {"acp":"0.1","type":"task.delegate",...}\n   │
│                                                             │
│  从 agent_b.stdout 读取 ◄──────────────────────────        │
│               {"acp":"0.1","type":"task.result",...}\n     │
└─────────────────────────────────────────────────────────────┘
              │ 启动                         │
              ▼                              │
┌─────────────────────────────────────────────────────────────┐
│  进程 B（agent_b.py）                                       │
│                                                             │
│  从 stdin 读取 ──► 处理消息 ──► 写入 stdout                 │
└─────────────────────────────────────────────────────────────┘
```

- **请求**：父进程写入子进程的 `stdin`
- **响应**：子进程写入 `stdout`
- **stderr**：保留用于日志/调试输出；MUST NOT 包含 ACP 消息
- **stdin EOF**：表示优雅关闭；子进程 SHOULD 发送 `agent.bye` 后退出

### 1.4 Python 参考实现

**Agent 侧（从 stdin 读取，向 stdout 响应）：**

```python
import sys, json, asyncio
from acp_sdk import ACPAgent, ACPMessage

async def run_stdio_agent(agent: ACPAgent):
    """
    以 stdio 模式运行 ACPAgent。
    从 stdin 读取换行分隔 JSON，向 stdout 输出响应。
    """
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)
    transport, _ = await asyncio.get_event_loop().connect_write_pipe(
        lambda: asyncio.BaseProtocol(), sys.stdout.buffer
    )

    while True:
        try:
            line = await reader.readline()
            if not line:
                break  # EOF

            line = line.strip()
            if not line:
                continue

            msg  = ACPMessage.from_dict(json.loads(line))
            resp = await agent.receive(msg)
            if resp:
                transport.write((resp.to_json() + "\n").encode())

        except json.JSONDecodeError as e:
            err = json.dumps({
                "acp": "0.1", "type": "error",
                "body": {"code": "acp.invalid_message", "message": str(e)}
            }) + "\n"
            transport.write(err.encode())
        except Exception:
            break

# 使用：
# asyncio.run(run_stdio_agent(MyAgent("did:acp:local:my-agent")))
```

**客户端侧（以子进程方式启动 Agent）：**

```python
import asyncio, json
from acp_sdk import ACPMessage

class StdioClient:
    def __init__(self, command: list[str]):
        self.command = command
        self._proc = None

    async def __aenter__(self):
        self._proc = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        return self

    async def __aexit__(self, *_):
        if self._proc:
            bye = ACPMessage.agent_bye("did:acp:local:client", "did:acp:local:agent")
            self._proc.stdin.write((bye.to_json() + "\n").encode())
            self._proc.stdin.close()
            await self._proc.wait()

    async def delegate(self, task: str, input: dict = None) -> ACPMessage:
        msg = ACPMessage.task_delegate(
            from_aid="did:acp:local:client",
            to_aid="did:acp:local:agent",
            task=task, input=input or {},
        )
        self._proc.stdin.write((msg.to_json() + "\n").encode())
        await self._proc.stdin.drain()
        line = await self._proc.stdout.readline()
        return ACPMessage.from_dict(json.loads(line.strip()))

# 使用：
# async with StdioClient(["python", "summarizer.py"]) as c:
#     result = await c.delegate("总结这段文字", {"text": "..."})
```

**Shell 一行命令示例：**

```bash
echo '{"acp":"0.1","id":"msg_001","type":"task.delegate","from":"did:acp:local:cli","to":"did:acp:local:agent","ts":"2026-03-18T10:00:00Z","body":{"task":"你好","input":{}}}' \
  | python my_agent.py
```

---

## 2. HTTP + SSE 传输

### 2.1 概述

HTTP 传输使用标准 HTTP 发送消息，使用 Server-Sent Events（SSE）接收消息。适用于网络 Agent 和云服务，兼容任何 HTTP 客户端，可直接用 `curl` 调试。

### 2.2 必须实现的端点

符合 ACP 规范的 HTTP 服务器 MUST 暴露以下端点：

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/acp/v1/messages` | 向此 Agent 发送消息 |
| `GET` | `/acp/v1/stream` | 订阅传入消息（SSE）|
| `GET` | `/acp/v1/capabilities` | 查询此 Agent 的能力 |
| `GET` | `/acp/v1/health` | 存活检查 |

### 2.3 发送消息（`POST /acp/v1/messages`）

**请求：**
```
POST /acp/v1/messages HTTP/1.1
Content-Type: application/json

{
  "acp": "0.1",
  "id":  "msg_7f3a9b2c",
  "type": "task.delegate",
  "from": "did:acp:local:orchestrator",
  "to":   "did:acp:local:summarizer",
  "ts":   "2026-03-18T10:00:00Z",
  "body": { "task": "总结这篇文章", "input": { "text": "..." } }
}
```

**同步响应（立即返回结果）：**
```
HTTP/1.1 200 OK
Content-Type: application/json

{
  "acp": "0.1", "type": "task.result",
  "body": { "status": "success", "output": { "summary": "..." } },
  ...
}
```

**异步响应（结果通过 SSE 推送）：**
```
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "accepted": true,
  "task_handle": "task_abc123",
  "stream_url": "/acp/v1/stream?correlation_id=workflow_xyz"
}
```

### 2.4 接收消息（SSE 流）

```
GET /acp/v1/stream HTTP/1.1
Accept: text/event-stream
```

响应是持久 SSE 流：
```
HTTP/1.1 200 OK
Content-Type: text/event-stream

data: {"acp":"0.1","type":"task.result",...}

data: {"acp":"0.1","type":"task.progress",...}

```

- 每行 `data:` 是一条完整的 ACP 消息 JSON
- 断连后客户端自动重连（SSE 语义）
- 按 correlation_id 过滤：`GET /acp/v1/stream?correlation_id=workflow_xyz`

### 2.5 能力查询端点

```
GET /acp/v1/capabilities
```

```json
{
  "aid":           "did:acp:local:summarizer",
  "name":          "摘要 Agent",
  "version":       "1.0.0",
  "capabilities":  ["summarize", "translate", "classify"],
  "input_schema":  {
    "type": "object",
    "properties": {
      "text":       { "type": "string" },
      "max_length": { "type": "integer", "default": 200 }
    },
    "required": ["text"]
  },
  "output_schema": {
    "type": "object",
    "properties": { "summary": { "type": "string" } }
  },
  "max_concurrent_tasks": 10,
  "status": "available"
}
```

### 2.6 Python 参考实现（FastAPI）

```python
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
from acp_sdk import ACPAgent, ACPMessage
import asyncio, json

def create_acp_app(agent: ACPAgent) -> FastAPI:
    app = FastAPI()
    _queue: asyncio.Queue[ACPMessage] = asyncio.Queue()

    @app.post("/acp/v1/messages")
    async def receive_message(request: Request):
        data = await request.json()
        msg  = ACPMessage.from_dict(data)
        resp = await agent.receive(msg)
        if resp:
            return JSONResponse(resp.to_dict())
        return JSONResponse({"accepted": True}, status_code=202)

    @app.get("/acp/v1/stream")
    async def stream():
        async def gen():
            while True:
                msg = await _queue.get()
                yield f"data: {msg.to_json()}\n\n"
        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.get("/acp/v1/capabilities")
    async def caps():
        return {
            "aid": agent.aid,
            "capabilities": getattr(agent, "capabilities", []),
        }

    @app.get("/acp/v1/health")
    async def health():
        return {"ok": True}

    return app

# 使用：
# app = create_acp_app(MySummarizerAgent("did:acp:local:summarizer"))
# uvicorn.run(app, host="0.0.0.0", port=7700)
```

---

## 3. TCP 传输

### 3.1 概述

TCP 传输使用持久 TCP 连接，消息格式与 stdio 相同（换行分隔 JSON）。适用于高吞吐量管道，延迟最低，无 HTTP 开销。

### 3.2 消息格式

与 stdio 传输完全相同：每行一个 JSON 对象，以 `\n` 结尾。

### 3.3 连接生命周期

```
客户端                          服务端
  │  TCP 连接 ─────────────────►│
  │                             │
  │  agent.hello ───────────────►│   （身份协商）
  │◄──────────── agent.hello    │
  │                             │
  │  task.delegate ─────────────►│
  │◄──────────── task.result    │
  │                             │
  │  agent.bye ─────────────────►│
  │  TCP 关闭 ──────────────────►│
```

1. 客户端建立 TCP 连接
2. 双方互发 `agent.hello` 完成身份协商
3. 消息双向流动
4. 任意一方发送 `agent.bye` 后关闭连接

### 3.4 默认端口

ACP TCP 服务器 SHOULD 默认监听 **7700** 端口，可配置覆盖。

### 3.5 Python 参考实现

**服务端：**

```python
import asyncio, json
from acp_sdk import ACPAgent, ACPMessage

async def handle_conn(agent: ACPAgent, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    try:
        async for line in reader:
            line = line.strip()
            if not line:
                continue
            msg  = ACPMessage.from_dict(json.loads(line))
            resp = await agent.receive(msg)
            if resp:
                writer.write((resp.to_json() + "\n").encode())
                await writer.drain()
    except (asyncio.IncompleteReadError, ConnectionResetError):
        pass
    finally:
        writer.close()

async def serve_tcp(agent: ACPAgent, host="0.0.0.0", port=7700):
    server = await asyncio.start_server(
        lambda r, w: handle_conn(agent, r, w), host, port
    )
    print(f"ACP TCP 监听 {host}:{port}")
    async with server:
        await server.serve_forever()
```

**客户端：**

```python
import asyncio, json
from acp_sdk import ACPMessage

class TCPClient:
    def __init__(self, host: str, port: int = 7700):
        self.host, self.port = host, port

    async def connect(self):
        self._r, self._w = await asyncio.open_connection(self.host, self.port)

    async def close(self):
        self._w.close()
        await self._w.wait_closed()

    async def delegate(self, from_aid: str, to_aid: str, task: str, input: dict = None) -> ACPMessage:
        msg = ACPMessage.task_delegate(from_aid, to_aid, task, input or {})
        self._w.write((msg.to_json() + "\n").encode())
        await self._w.drain()
        line = await self._r.readline()
        return ACPMessage.from_dict(json.loads(line.strip()))
```

---

## 4. 传输选型指南

```
Agent 是否作为你控制的子进程运行？
  是 → 用 stdio
  否 ↓

是否对低延迟或高吞吐有严格要求？
  是 → 用 TCP
  否 ↓

用 HTTP + SSE（互操作性最强，curl 可直接调试）
```

---

## 5. 多传输并行

一个 Agent 可同时支持多种传输。示例：对外提供 HTTP（供外部调用），对内提供 TCP（供内部高速管道）：

```python
async def main():
    agent = MySummarizerAgent("did:acp:local:summarizer")

    await asyncio.gather(
        serve_http(agent, port=7700),   # 外部调用
        serve_tcp(agent,  port=7701),   # 内部管道
    )
```

---

## 附录：传输对比

| 特性 | stdio | HTTP/SSE | TCP |
|------|-------|----------|-----|
| 需要网络 | 否 | 是 | 是 |
| 需要端口 | 否 | 是 | 是 |
| 跨语言 | 是 | 是 | 是 |
| 流式响应 | 多行 | SSE | 多行 |
| curl 可调试 | 否 | 是 | 部分 |
| 持久连接 | 进程生命周期 | 每请求 + SSE | 是 |
| TLS 支持 | 不适用 | HTTPS | TLS 封装 |
| 推荐场景 | 本地子进程 | 网络/云 | 高吞吐 |
