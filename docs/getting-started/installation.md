# Installation

ACP has two components: the **Relay** (reference implementation) and the **Python SDK**.

## Relay

The relay (`relay/acp_relay.py`) uses **Python stdlib only** — no pip install needed.

```bash
git clone https://github.com/Kickflip73/agent-communication-protocol.git
cd agent-communication-protocol
python3 relay/acp_relay.py --version
# acp_relay.py v2.8.0
```

### Optional dependencies

| Feature | Dependency | Install |
|---------|-----------|---------|
| HTTP/2 (h2c) | `h2` | `pip install h2` |
| mDNS LAN discovery | stdlib `socket` | built-in |
| HMAC signing | stdlib `hmac` | built-in |

## Python SDK (`acp-client`)

```bash
# Install from repo
pip install -e ./relay/

# Verify
python3 -c "import acp_client; print(acp_client.__version__)"
# 1.9.0
```

### What's included

```
acp_client/
├── __init__.py          # RelayClient, AsyncRelayClient, top-level exports
├── client.py            # Synchronous RelayClient
├── async_client.py      # AsyncRelayClient (asyncio)
├── models.py            # AgentCard, Message, Task, Part, Extension, ...
├── exceptions.py        # ACPError hierarchy
└── integrations/
    └── langchain.py     # ACPTool, ACPCallbackHandler, create_acp_tool()
```

### Basic usage

```python
from acp_client import RelayClient, AgentCard, Message

c = RelayClient("http://localhost:7901")

# Get agent info
card: AgentCard = c.agent_card()
print(card.name, card.capabilities)

# Connect to a peer
peer_id = c.connect("acp://remote-host:7801/tok_xxx")

# Send a message
c.send("Hello!", peer_id=peer_id)

# Receive messages
for msg in c.recv(timeout=10):
    print(msg.parts[0].content)
```

### Async usage

```python
import asyncio
from acp_client import AsyncRelayClient

async def main():
    async with AsyncRelayClient("http://localhost:7901") as c:
        peer_id = await c.connect("acp://remote:7801/tok_xxx")
        await c.send("Hello async!", peer_id=peer_id)
        async for msg in c.stream():
            print(msg.parts[0].content)
            break

asyncio.run(main())
```

### LangChain integration

```python
from acp_client.integrations.langchain import create_acp_tool
from langchain.agents import initialize_agent

acp_tool = create_acp_tool(
    relay_url="http://localhost:7901",
    peer_link="acp://remote:7801/tok_xxx",
    description="Send tasks to the remote analysis agent"
)

agent = initialize_agent(
    tools=[acp_tool],
    llm=your_llm,
    agent="zero-shot-react-description"
)
```

## Docker

```bash
docker pull ghcr.io/kickflip73/agent-communication-protocol:latest

# Run
docker run -p 7901:7901 -p 7801:7801 \
  ghcr.io/kickflip73/agent-communication-protocol:latest \
  --name MyAgent
```

Or with docker-compose:

```bash
docker-compose up
```

## Verify Installation

```bash
# Start relay
python3 relay/acp_relay.py --name TestAgent &

# Check AgentCard
curl http://localhost:7901/.well-known/acp.json | python3 -m json.tool

# Check status
curl http://localhost:7901/status | python3 -m json.tool
```

Expected output:
```json
{
  "name": "TestAgent",
  "version": "2.8.0",
  "link": "acp://...",
  "peers": {},
  "capabilities": {
    "streaming": true,
    "tasks": true,
    "hmac_signing": false,
    "mdns_discovery": false
  },
  "extensions": []
}
```
