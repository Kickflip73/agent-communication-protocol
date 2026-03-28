# Quick Start

Get two agents talking in under 60 seconds.

## Prerequisites

- Python 3.9+
- Two terminal windows (or two machines)

## Step 1: Get the Relay

```bash
git clone https://github.com/Kickflip73/agent-communication-protocol.git
cd agent-communication-protocol
```

No package installation required — `acp_relay.py` uses Python stdlib only.

## Step 2: Start Agent A

```bash
python3 relay/acp_relay.py --name AgentA --http-port 7901 --ws-port 7801
```

You'll see:

```
[ACP] Detecting public IP...
[ACP] AgentA ready on ws://0.0.0.0:7801, http://0.0.0.0:7901
✅ Ready.  Your link: acp://1.2.3.4:7801/tok_xxxxxxxx
           Send this link to any other Agent to connect.
```

Copy the `acp://...` link — this is Agent A's address.

## Step 3: Start Agent B

In a second terminal:

```bash
python3 relay/acp_relay.py --name AgentB --http-port 7902 --ws-port 7802
```

## Step 4: Connect B → A

```bash
curl -X POST http://localhost:7902/peers/connect \
     -H "Content-Type: application/json" \
     -d '{"link": "acp://1.2.3.4:7801/tok_xxxxxxxx"}'
```

Response:
```json
{"ok": true, "peer_id": "peer_001"}
```

## Step 5: Subscribe on Agent A (optional)

In a third terminal, watch Agent A's incoming stream:

```bash
curl -N http://localhost:7901/stream
```

## Step 6: Agent B Sends a Message

```bash
curl -X POST http://localhost:7902/message:send \
     -H "Content-Type: application/json" \
     -d '{
       "role": "agent",
       "parts": [{"type": "text", "content": "Hello from Agent B!"}]
     }'
```

Response:
```json
{
  "ok": true,
  "message_id": "msg_abc123",
  "server_seq": 1,
  "peer_id": "peer_001"
}
```

Agent A's SSE stream fires immediately:

```
event: acp.message
data: {"role":"agent","from_peer":"peer_001","parts":[{"type":"text","content":"Hello from Agent B!"}],"message_id":"msg_abc123","ts":"2026-03-28T..."}
```

## Step 7: Agent A Replies

```bash
curl -X POST http://localhost:7901/peer/peer_001/send \
     -H "Content-Type: application/json" \
     -d '{
       "role": "agent",
       "parts": [{"type": "text", "content": "Hello back from Agent A!"}]
     }'
```

🎉 **You have two agents communicating in real-time.**

---

## Using the Python SDK

Instead of curl, use the Python SDK:

```python
from acp_client import RelayClient

# Agent B
b = RelayClient("http://localhost:7902")
peer_id = b.connect("acp://1.2.3.4:7801/tok_xxxxxxxx")
b.send("Hello from SDK!", peer_id=peer_id)

# Receive messages (blocking iterator)
for msg in b.recv(timeout=5):
    print(f"Got: {msg.parts[0].content}")
```

Install:

```bash
pip install -e relay/  # from repo root
# or
pip install acp-client  # when published to PyPI
```

---

## Next Steps

- [Core Concepts](concepts.md) — understand links, peers, tasks, streams
- [Team Collaboration](../guides/team-collaboration.md) — orchestrator + workers
- [NAT Traversal](../nat-traversal.md) — how P2P works across networks
- [CLI Reference](../cli-reference.md) — all flags and options
