# ACP-P2P Integration Guide v0.3

**Language**: **English** · [中文](SKILL.zh.md)

> This guide is for **developers who already have an agent** and want to make it talk to other agents using ACP-P2P. Goal: integrate in under 5 minutes.

---

## Prerequisites

- Python 3.10+
- An existing agent (function, class, LangChain, AutoGen, etc.)

---

## Install (30 seconds)

```bash
pip install aiohttp

# Download the SDK (single file, no other dependencies)
curl -o acp_p2p.py \
  https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/p2p/sdk/acp_p2p.py
```

---

## Integrate your existing agent

### Case A: Function-based agent (most common)

You have a function that handles requests and want it to be callable remotely:

```python
# ── Your existing code (unchanged) ───────────────────────────
def my_agent(query: str, context: dict) -> str:
    # ... your logic
    return "result"

# ── Add 4 lines to expose it via ACP ─────────────────────────
from acp_p2p import P2PAgent

agent = P2PAgent("my-agent", port=7700)

@agent.on_task
async def handle(task: str, input_data: dict) -> dict:
    result = my_agent(task, input_data)   # call your existing function
    return {"output": result}

agent.start()
# Prints: 🔗 ACP URI: acp://192.168.1.42:7700/my-agent
# Share this URI with any agent that needs to reach you
```

### Case B: Agent with existing HTTP server

No need to switch frameworks. Just **add one route** to your existing server:

```python
# FastAPI example
from fastapi import FastAPI, Request
app = FastAPI()

# ── Your existing routes (unchanged) ─────────────────────────
@app.get("/health")
def health(): return {"ok": True}

# ── Add: ACP receive endpoint ─────────────────────────────────
@app.post("/acp/v1/receive")
async def acp_receive(request: Request):
    msg    = await request.json()
    task   = msg["body"]["task"]
    input_ = msg["body"].get("input", {})

    result = your_existing_handler(task, input_)   # your logic

    return {
        "acp": "0.1", "type": "task.result",
        "from": "acp://your-host:8000/my-agent",
        "to": msg["from"],
        "id": f"msg_{__import__('uuid').uuid4().hex[:12]}",
        "ts": __import__('datetime').datetime.utcnow().isoformat() + "Z",
        "body": {"status": "success", "output": result},
        "reply_to": msg["id"],
    }
# Your ACP URI: acp://your-host:8000/my-agent
```

```python
# Flask example
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

### Case C: LangChain agent

```python
from langchain.agents import AgentExecutor
from acp_p2p import P2PAgent

# ── Your existing LangChain agent (unchanged) ─────────────────
executor: AgentExecutor = build_your_agent()

# ── Wrap with ACP (5 new lines) ───────────────────────────────
acp = P2PAgent("langchain-agent", port=7700, capabilities=["qa", "reasoning"])

@acp.on_task
async def handle(task: str, input_data: dict) -> dict:
    result = await executor.ainvoke({"input": task, **input_data})
    return {"output": result["output"]}

acp.start()
```

### Case D: AutoGen agent

```python
import autogen
from acp_p2p import P2PAgent

# ── Your existing AutoGen setup (unchanged) ───────────────────
assistant  = autogen.AssistantAgent("assistant", llm_config={...})
user_proxy = autogen.UserProxyAgent("user_proxy", human_input_mode="NEVER", ...)

# ── Wrap with ACP (6 new lines) ───────────────────────────────
acp = P2PAgent("autogen-agent", port=7700, capabilities=["chat", "code"])

@acp.on_task
async def handle(task: str, input_data: dict) -> dict:
    await user_proxy.a_initiate_chat(assistant, message=task, max_turns=5)
    last = user_proxy.last_message(assistant)
    return {"output": last["content"]}

acp.start()
```

### Case E: CrewAI

```python
from crewai import Agent, Task, Crew
from acp_p2p import P2PAgent

# ── Your existing Crew (unchanged) ────────────────────────────
researcher = Agent(role="Researcher", goal="Research topics", ...)
crew       = Crew(agents=[researcher], tasks=[...])

# ── Wrap with ACP ─────────────────────────────────────────────
acp = P2PAgent("crewai-agent", port=7700, capabilities=["research"])

@acp.on_task
async def handle(task: str, input_data: dict) -> dict:
    t      = Task(description=task, agent=researcher)
    result = crew.kickoff(tasks=[t])
    return {"output": str(result)}

acp.start()
```

---

## Send messages to other agents

Once integrated, your agent can also reach out:

```python
# Send directly using a URI — no setup needed
result = await my_agent.send(
    to="acp://192.168.1.50:7701/summarizer",
    task="Summarize this article",
    input={"text": "..."},
)
print(result["body"]["output"])

# With explicit connect/disconnect (confirms peer is online first)
session = await my_agent.connect("acp://192.168.1.50:7701/summarizer")
result  = await my_agent.send(session, "Summarize", {"text": "..."})
await my_agent.disconnect(session)

# Check if a peer is online
online = await my_agent.ping("acp://192.168.1.50:7701/summarizer")

# Query a peer's capabilities
info = await my_agent.discover("acp://192.168.1.50:7701/summarizer")
print(info["capabilities"])   # ['summarize', 'translate']
```

---

## Group chat

Make your agent participate in multi-agent collaboration:

```python
# Option 1: you create the group and invite others
group = my_agent.create_group("project-alpha")
await my_agent.invite(group, "acp://host-b:7701/agent-b")
await my_agent.invite(group, "acp://host-c:7702/agent-c")

@my_agent.on_group_message
async def on_msg(group_id: str, from_uri: str, body: dict):
    sender = from_uri.split("/")[-1]
    print(f"[{sender}]: {body.get('text')}")
    await my_agent.group_send(my_agent.get_group(group_id), {"text": "Received!"})

await my_agent.group_send(group, {"text": "Task starting!"})

# Option 2: join using an invite link
group = await my_agent.join_group("acpgroup://project-alpha:acp://...?members=...")
await my_agent.group_send(group, {"text": "I joined!"})

# Leave (automatically notifies all members)
await my_agent.leave_group(group)
```

---

## Ready-to-run integration template

Save as `my_acp_agent.py`, replace `YOUR_AGENT_LOGIC`, and run:

```python
"""
ACP-P2P integration template.
Replace YOUR_AGENT_LOGIC, then: python my_acp_agent.py
"""
import asyncio
from acp_p2p import P2PAgent


# ════════════════════════════════════════════════════════
#  ① Your existing agent logic (put it here, unchanged)
# ════════════════════════════════════════════════════════
def YOUR_AGENT_LOGIC(task: str, input_data: dict) -> dict:
    # Example: simple text processing agent
    text = input_data.get("text", task)
    return {
        "processed": text.upper(),
        "length": len(text),
        "task_received": task,
    }


# ════════════════════════════════════════════════════════
#  ② ACP wiring (template — only change name and port)
# ════════════════════════════════════════════════════════
agent = P2PAgent(
    name="my-agent",            # ← change to your agent's name
    port=7700,                  # ← change to your preferred port
    capabilities=["process"],   # ← list your agent's capabilities
)

@agent.on_task
async def handle(task: str, input_data: dict) -> dict:
    return YOUR_AGENT_LOGIC(task, input_data)   # call your function


# ════════════════════════════════════════════════════════
#  ③ Optional: call another agent
# ════════════════════════════════════════════════════════
async def call_remote(target_uri: str):
    result = await agent.send(
        to=target_uri,
        task="Process this",
        input={"text": "Hello from my agent!"},
    )
    print("Remote agent returned:", result["body"]["output"])


# ════════════════════════════════════════════════════════
#  Start
# ════════════════════════════════════════════════════════
if __name__ == "__main__":
    agent.start()   # prints ACP URI, Ctrl+C to stop
```

---

## Cross-machine communication

By default the URI uses the local LAN IP. For cross-machine access:

```bash
# Same LAN: works out of the box

# Dev: cross-machine via ngrok
ngrok http 7700
# Then specify the host in code:
agent = P2PAgent("my-agent", port=7700, host="abc123.ngrok.io")

# Production server
agent = P2PAgent("my-agent", port=7700, host="your.server.com")
```

---

## Authentication

Restrict who can call your agent:

```python
agent = P2PAgent("my-agent", port=7700, psk="your-secret-key")
# URI: acp://host:7700/my-agent?key=your-secret-key

# Callers include the key in the URI — SDK handles auth automatically
result = await caller.send("acp://host:7700/my-agent?key=your-secret-key", ...)
```

---

## API Reference

```python
# Create
agent = P2PAgent(name, port=7700, host=None, psk=None, capabilities=[])

# Server lifecycle
agent.start()              # blocking (standalone scripts)
async with agent: ...      # non-blocking (recommended; auto-stops on exit)
await agent.stop()         # manual stop

# Send
await agent.send(to_uri_or_session, task, input={}, timeout=30)

# Connection management
session = await agent.connect(peer_uri)    # handshake
await agent.disconnect(session)            # close
ok   = await agent.ping(peer_uri)          # check online
info = await agent.discover(peer_uri)      # query peer capabilities

# Group chat
group = agent.create_group(name)
ok    = await agent.invite(group, peer_uri)
group = await agent.join_group(invite_uri)
await agent.leave_group(group)
await agent.group_send(group, body_dict)
group = agent.get_group(group_id)
link  = group.to_invite_uri()

# Handlers
@agent.on_task
async def handle(task: str, input: dict) -> dict: ...

@agent.on_group_message
async def on_msg(group_id: str, from_uri: str, body: dict): ...

@agent.on_message("custom.type")
async def on_custom(msg: dict) -> dict: ...
```

---

## FAQ

**Q: My agent isn't Python. Can I still use ACP?**  
A: Yes. ACP is HTTP. Any language just needs to: ① listen on `POST /acp/v1/receive`; ② send HTTP POST. No SDK required.

**Q: What if the peer is offline when I send?**  
A: `send()` raises `ConnectionError`. v0.3 has no built-in retry; handle it in the caller. v0.4 will add reliable delivery.

**Q: Can I run multiple agents in one process?**  
A: Yes, each on a different port.

```python
async with agent_a, agent_b, agent_c:
    ...
```

**Q: Is there a group size limit?**  
A: No hard limit, but v0.3 uses full broadcast. For large groups, wait for v0.5's pub/sub mode.

---

**SDK**: [`p2p/sdk/acp_p2p.py`](../sdk/acp_p2p.py) — single file, no package install needed  
**Protocol spec**: [`p2p/spec/acp-p2p-v0.1.md`](../spec/acp-p2p-v0.1.md)  
**Runnable examples**: [`p2p/examples/`](../examples/)  
**GitHub**: https://github.com/Kickflip73/agent-communication-protocol
