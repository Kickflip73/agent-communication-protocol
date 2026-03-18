# ACP Transport Bindings

**Status:** Draft  
**Version:** 0.1  
**Language:** **English** · [中文](transports.zh.md)

This document defines the three standard ACP transport bindings. A conformant ACP implementation MUST support at least one of these bindings.

---

## Overview

ACP is transport-agnostic: the message envelope is identical across all transports. Only the framing and delivery mechanism differ.

| Transport | Best for | Latency | Setup |
|-----------|----------|---------|-------|
| **stdio** | Subprocess agents, CLI tools, same-machine | ~1ms | Zero — no ports, no config |
| **HTTP/SSE** | Networked agents, cloud, cross-host | ~10ms | Start an HTTP server |
| **TCP** | High-throughput pipelines, same datacenter | ~1ms | Open a TCP socket |

---

## 1. stdio Transport

### 1.1 Overview

The stdio transport enables two agents to communicate via standard input/output streams. It is the simplest transport: no network configuration, no ports, no TLS setup. One agent spawns the other as a subprocess, or two processes are piped together.

This is modelled after MCP's stdio transport — the same approach that made MCP easy to adopt.

### 1.2 Wire Format

Messages are **newline-delimited JSON** (NDJSON): one JSON object per line, terminated by `\n`.

```
<json-object>\n
<json-object>\n
...
```

- Each line MUST be a complete, valid ACP message envelope
- Lines MUST be terminated with `\n` (Unix line ending)
- Implementations MUST NOT emit partial lines
- Empty lines MUST be ignored by the reader

### 1.3 Message Flow

```
┌─────────────────────────────────────────────────────────────┐
│  Process A (sender/parent)                                  │
│                                                             │
│  write to agent_b.stdin ──────────────────────────────►    │
│                           {"acp":"0.1","type":"task.delegate",...}\n
│                                                             │
│  read from agent_b.stdout ◄────────────────────────────    │
│                           {"acp":"0.1","type":"task.result",...}\n
└─────────────────────────────────────────────────────────────┘
              │ spawn                        │
              ▼                              │
┌─────────────────────────────────────────────────────────────┐
│  Process B (agent_b.py)                                     │
│                                                             │
│  read from stdin  ──► handle message ──► write to stdout   │
└─────────────────────────────────────────────────────────────┘
```

- **Requests:** Parent writes to child's `stdin`
- **Responses:** Child writes to `stdout`
- **stderr:** Reserved for logging/debug output; MUST NOT contain ACP messages
- **EOF on stdin:** Signals graceful shutdown; the child SHOULD send `agent.bye` then exit

### 1.4 Python Reference Implementation

**Agent side (receives on stdin, replies on stdout):**

```python
import sys
import json
import asyncio

async def run_stdio_agent(agent):
    """
    Run an ACPAgent in stdio mode.
    Reads newline-delimited JSON from stdin, writes responses to stdout.
    """
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)

    writer_transport, writer_protocol = await asyncio.get_event_loop().connect_write_pipe(
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

            msg_dict = json.loads(line)
            msg = ACPMessage.from_dict(msg_dict)

            response = await agent.receive(msg)
            if response:
                out = response.to_json() + "\n"
                writer_transport.write(out.encode())

        except json.JSONDecodeError as e:
            error_line = json.dumps({
                "acp": "0.1", "type": "error",
                "body": {"code": "acp.invalid_message", "message": str(e)}
            }) + "\n"
            writer_transport.write(error_line.encode())
        except Exception:
            break

# Usage:
# asyncio.run(run_stdio_agent(MyAgent("did:acp:local:my-agent")))
```

**Client side (spawns agent as subprocess):**

```python
import asyncio
import json
import subprocess
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
            msg = ACPMessage.agent_bye("did:acp:local:client", "did:acp:local:agent")
            await self._write(msg)
            self._proc.stdin.close()
            await self._proc.wait()

    async def _write(self, msg: ACPMessage):
        line = (msg.to_json() + "\n").encode()
        self._proc.stdin.write(line)
        await self._proc.stdin.drain()

    async def _read(self) -> ACPMessage:
        line = await self._proc.stdout.readline()
        return ACPMessage.from_dict(json.loads(line.strip()))

    async def delegate(self, task: str, input: dict = None, **kwargs) -> ACPMessage:
        msg = ACPMessage.task_delegate(
            from_aid="did:acp:local:client",
            to_aid="did:acp:local:agent",
            task=task,
            input=input or {},
            **kwargs,
        )
        await self._write(msg)
        return await self._read()


# Usage:
# async with StdioClient(["python", "summarizer_agent.py"]) as client:
#     result = await client.delegate("Summarize this", {"text": "..."})
#     print(result.body["output"])
```

**Shell example (pipe two agents):**

```bash
# One-shot request via shell pipe
echo '{"acp":"0.1","id":"msg_001","type":"task.delegate","from":"did:acp:local:cli","to":"did:acp:local:agent","ts":"2026-03-18T10:00:00Z","body":{"task":"Hello","input":{}}}' \
  | python my_agent.py
```

---

## 2. HTTP + SSE Transport

### 2.1 Overview

The HTTP transport uses standard HTTP for sending messages and Server-Sent Events (SSE) for receiving them. It is the recommended transport for networked agents and is compatible with any HTTP client.

### 2.2 Endpoints

An ACP-compliant HTTP server MUST expose:

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/acp/v1/messages` | Send a message to this agent |
| `GET` | `/acp/v1/stream` | Subscribe to incoming messages (SSE) |
| `GET` | `/acp/v1/capabilities` | Query this agent's capabilities |
| `GET` | `/acp/v1/health` | Liveness check |

### 2.3 Sending a Message (`POST /acp/v1/messages`)

**Request:**
```
POST /acp/v1/messages HTTP/1.1
Content-Type: application/json

{
  "acp": "0.1",
  "id": "msg_7f3a9b2c",
  "type": "task.delegate",
  "from": "did:acp:local:orchestrator",
  "to":   "did:acp:local:summarizer",
  "ts":   "2026-03-18T10:00:00Z",
  "body": { "task": "...", "input": { ... } }
}
```

**Response (synchronous — result returned immediately):**
```
HTTP/1.1 200 OK
Content-Type: application/json

{
  "acp": "0.1",
  "id": "msg_9d1e4f7a",
  "type": "task.result",
  "from": "did:acp:local:summarizer",
  "to":   "did:acp:local:orchestrator",
  "ts":   "2026-03-18T10:00:43Z",
  "reply_to": "msg_7f3a9b2c",
  "body": { "status": "success", "output": { ... } }
}
```

**Response (asynchronous — result delivered via SSE later):**
```
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "accepted": true,
  "task_handle": "task_abc123",
  "stream_url": "/acp/v1/stream?correlation_id=workflow_xyz"
}
```

### 2.4 Receiving Messages (SSE stream)

```
GET /acp/v1/stream HTTP/1.1
Accept: text/event-stream
```

Response is a persistent SSE stream:
```
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache

data: {"acp":"0.1","id":"msg_001","type":"task.result",...}

data: {"acp":"0.1","id":"msg_002","type":"task.progress",...}

```

- Each `data:` line is one complete ACP message JSON
- The client reconnects automatically on disconnect (SSE semantics)
- Filter by `correlation_id`: `GET /acp/v1/stream?correlation_id=workflow_xyz`

### 2.5 Capabilities Endpoint

```
GET /acp/v1/capabilities HTTP/1.1
```

```json
{
  "aid":          "did:acp:local:summarizer",
  "name":         "Summarizer Agent",
  "version":      "1.0.0",
  "capabilities": ["summarize", "translate", "classify"],
  "input_schema": {
    "type": "object",
    "properties": {
      "text": { "type": "string" },
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

### 2.6 Python Reference Implementation (FastAPI)

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
        # async: put response into SSE queue
        return JSONResponse({"accepted": True}, status_code=202)

    @app.get("/acp/v1/stream")
    async def stream():
        async def event_gen():
            while True:
                msg = await _queue.get()
                yield f"data: {msg.to_json()}\n\n"
        return StreamingResponse(event_gen(), media_type="text/event-stream")

    @app.get("/acp/v1/capabilities")
    async def capabilities():
        return {"aid": agent.aid, "capabilities": agent.capabilities}

    @app.get("/acp/v1/health")
    async def health():
        return {"ok": True}

    return app
```

---

## 3. TCP Transport

### 3.1 Overview

The TCP transport uses a persistent TCP connection with newline-delimited JSON framing. It is the lowest-latency option and is recommended for high-throughput pipelines where HTTP overhead is unacceptable.

### 3.2 Wire Format

Identical to the stdio transport: one JSON object per line, terminated by `\n`.

### 3.3 Connection Lifecycle

```
Client                          Server
  │  TCP connect ────────────────►│
  │                               │
  │  agent.hello ─────────────────►│   (identify and negotiate)
  │◄──────────── agent.hello       │
  │                               │
  │  task.delegate ───────────────►│
  │◄──────────── task.result       │
  │                               │
  │  agent.bye ───────────────────►│
  │  TCP close ───────────────────►│
```

1. Client opens TCP connection
2. Both sides send `agent.hello` to identify themselves
3. Messages flow in both directions
4. Either side sends `agent.bye` before closing
5. Peer closes the TCP connection

### 3.4 Default Port

ACP TCP servers SHOULD listen on port **7700** by default. This can be overridden.

### 3.5 Python Reference Implementation

**Server:**

```python
import asyncio
import json
from acp_sdk import ACPAgent, ACPMessage

async def handle_tcp_connection(agent: ACPAgent, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    peer = writer.get_extra_info("peername")
    try:
        async for line in reader:
            line = line.strip()
            if not line:
                continue
            msg = ACPMessage.from_dict(json.loads(line))
            resp = await agent.receive(msg)
            if resp:
                writer.write((resp.to_json() + "\n").encode())
                await writer.drain()
    except (asyncio.IncompleteReadError, ConnectionResetError):
        pass
    finally:
        writer.close()

async def serve_tcp(agent: ACPAgent, host: str = "0.0.0.0", port: int = 7700):
    server = await asyncio.start_server(
        lambda r, w: handle_tcp_connection(agent, r, w),
        host, port
    )
    print(f"ACP TCP server listening on {host}:{port}")
    async with server:
        await server.serve_forever()
```

**Client:**

```python
import asyncio, json
from acp_sdk import ACPMessage

class TCPClient:
    def __init__(self, host: str, port: int = 7700):
        self.host, self.port = host, port
        self._reader = self._writer = None

    async def connect(self):
        self._reader, self._writer = await asyncio.open_connection(self.host, self.port)

    async def close(self):
        self._writer.close()
        await self._writer.wait_closed()

    async def send(self, msg: ACPMessage) -> ACPMessage:
        self._writer.write((msg.to_json() + "\n").encode())
        await self._writer.drain()
        line = await self._reader.readline()
        return ACPMessage.from_dict(json.loads(line.strip()))

    async def delegate(self, from_aid: str, to_aid: str, task: str, input: dict = None) -> ACPMessage:
        msg = ACPMessage.task_delegate(from_aid, to_aid, task, input or {})
        return await self.send(msg)
```

---

## 4. Transport Selection Guide

```
Does the agent run as a subprocess you control?
  YES → use stdio
  NO  ↓

Is low-latency or high-throughput the priority?
  YES → use TCP
  NO  ↓

Use HTTP + SSE  (most interoperable, easiest to debug with curl/browser)
```

---

## 5. Multi-Transport Agents

An agent MAY support multiple transports simultaneously. Example: an agent that serves both HTTP (for external callers) and TCP (for internal high-speed pipeline):

```python
async def main():
    agent = MySummarizerAgent("did:acp:local:summarizer")

    await asyncio.gather(
        serve_http(agent, port=7700),   # external callers
        serve_tcp(agent,  port=7701),   # internal pipeline
    )
```

---

## Appendix: Quick Comparison

| Feature | stdio | HTTP/SSE | TCP |
|---------|-------|----------|-----|
| Requires network | No | Yes | Yes |
| Requires port | No | Yes | Yes |
| Works cross-language | Yes | Yes | Yes |
| Streaming responses | Via multiple lines | Via SSE | Via multiple lines |
| Human-readable with curl | No | Yes | Partial |
| Persistent connection | Process lifetime | Per-request + SSE | Yes |
| TLS support | N/A (use OS security) | HTTPS | TLS wrapping |
| Recommended use | Local subprocess | Networked / cloud | High-throughput |
