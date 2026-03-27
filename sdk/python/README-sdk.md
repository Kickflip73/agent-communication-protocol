# acp-client — Python SDK for the Agent Communication Protocol

[![PyPI version](https://img.shields.io/badge/pypi-acp--client-blue)](https://pypi.org/project/acp-client/)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://python.org)
[![ACP](https://img.shields.io/badge/ACP-v2.7-green)](https://github.com/Kickflip73/agent-communication-protocol)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

`acp-client` is the official Python SDK for [ACP (Agent Communication Protocol)](https://github.com/Kickflip73/agent-communication-protocol).
It provides synchronous and async clients for connecting to a running `acp_relay.py` node,
with **zero external dependencies** (stdlib only for the core).

---

## Installation

```bash
pip install acp-client
```

Optional extras:

```bash
pip install "acp-client[async]"   # httpx for native async HTTP
pip install "acp-client[http2]"   # h2 for HTTP/2 transport
pip install "acp-client[dev]"     # pytest + all extras for development
```

---

## 30-Second Quick-start

### Synchronous

```python
from acp_client import RelayClient

# Connect to a locally running relay (default port 7901)
client = RelayClient("http://localhost:7901")

# Check connection status
print(client.status())          # {'acp_version': '2.7', 'connected': True, ...}
print(client.is_connected())    # True

# Send a message to the connected peer
resp = client.send("Hello from acp-client!")
print(resp)                     # {'ok': True, 'message_id': 'msg_...'}

# Receive pending messages
for msg in client.recv():
    print(msg["role"], msg.get("text"))

# List connected peers
for peer in client.peers():
    print(peer["peer_id"], peer["name"])
```

### Asynchronous

```python
import asyncio
from acp_client import AsyncRelayClient

async def main():
    async with AsyncRelayClient("http://localhost:7901") as client:
        # Send a message
        await client.send("Hello async!")

        # Subscribe to real-time SSE events
        async for event in client.stream(timeout=30):
            if event.get("type") == "acp.message":
                print("Received:", event)

asyncio.run(main())
```

### CLI

```bash
# Status
acp-client status

# List peers
acp-client peers

# Send a message
acp-client send "Hello world"
acp-client send "Hi" --peer sess_abc123   # target specific peer

# Poll inbox
acp-client recv --limit 10

# Watch live event stream
acp-client stream --timeout 60

# All commands support --url for non-default relay address
acp-client --url http://localhost:8000 status
```

---

## API Reference

### `RelayClient`

```python
class RelayClient:
    def __init__(self, base_url: str = "http://localhost:7901", timeout: float = 10.0)
```

#### Status & Discovery

| Method | Returns | Description |
|--------|---------|-------------|
| `status()` | `dict` | Relay version, connection state, peer count |
| `card()` | `AgentCard` | This node's capability card |
| `card_raw()` | `dict` | Raw AgentCard dict |
| `link()` | `str` | Shareable `acp://` link for this node |
| `capabilities()` | `dict` | Capability flags (streaming, sse_seq, …) |
| `supported_interfaces()` | `list[str]` | Interface groups (core, task, stream, …) |
| `identity()` | `dict` | DID identity block (v1.3+) |
| `did_document()` | `dict` | W3C DID Document (v1.3+) |
| `is_connected()` | `bool` | True if ≥1 peer connected |

#### Peer Management

| Method | Returns | Description |
|--------|---------|-------------|
| `peers()` | `list[dict]` | All connected peers |
| `peer(peer_id)` | `dict` | Single peer info |
| `wait_for_peer(timeout, poll_interval)` | `bool` | Block until peer connects |

#### Messaging

| Method | Returns | Description |
|--------|---------|-------------|
| `send(text, *, parts, role, message_id)` | `dict` | Send to primary peer |
| `send_to_peer(peer_id, text, *, parts, role, message_id)` | `dict` | Send to specific peer |
| `recv(limit)` | `list[dict]` | Poll received messages (raw) |
| `recv_messages(limit)` | `list[Message]` | Poll as `Message` objects |
| `reply(correlation_id, text)` | `dict` | Send correlated reply |
| `send_and_recv(text, timeout, poll_interval)` | `dict \| None` | Send + wait for reply |

#### SSE Stream

| Method | Returns | Description |
|--------|---------|-------------|
| `stream(timeout)` | `Generator[dict]` | Subscribe to SSE event stream |

#### Tasks

| Method | Returns | Description |
|--------|---------|-------------|
| `tasks(status, peer_id, created_after, updated_after, sort, cursor, limit)` | `list[dict]` | List tasks with filters |
| `get_task(task_id)` | `Task` | Fetch single task |
| `create_task(payload, delegate)` | `dict` | Create or delegate task |
| `update_task(task_id, state, output)` | `dict` | Update task state |
| `cancel_task(task_id, raise_on_terminal)` | `dict` | Cancel task (idempotent) |
| `continue_task(task_id, text, parts)` | `dict` | Resume input_required task |
| `wait_for_task(task_id, timeout, poll_interval)` | `Task` | Poll until terminal state |

#### Skills

| Method | Returns | Description |
|--------|---------|-------------|
| `query_skills(skill_id, capability)` | `dict` | QuerySkill API |

---

### `AsyncRelayClient`

Mirrors `RelayClient` but all methods are `async`. Supports the async context manager protocol:

```python
async with AsyncRelayClient("http://localhost:7901") as client:
    ...
```

Additional async-only methods:

| Method | Description |
|--------|-------------|
| `connect_peer(link)` | Connect to a new peer via acp:// link |
| `is_connected_to(peer_id)` | Check if specific peer is connected |
| `discover()` | List mDNS LAN peers (v0.7, requires `--advertise-mdns`) |
| `query_skills(query, skill_id, capability, limit)` | Extended QuerySkill |
| `continue_task(task_id, text, parts)` | Resume input_required task |
| `sse_seq_enabled()` | True if SSE event sequencing is active (v2.5+) |

---

### Models

#### `AgentCard`

```python
from acp_client.models import AgentCard

card = AgentCard.from_dict(raw_dict)
card.name                        # str
card.version                     # str
card.capabilities                # dict
card.supports("streaming")       # bool
card.has_interface("task")       # bool — v2.5+ supported_interfaces
card.has_limitation("no_web")    # bool — v2.7+ limitations
card.can_use_p2p()               # bool — transport_modes
card.can_use_relay()             # bool
card.to_dict()                   # serialise back to dict
```

#### `Message`

```python
from acp_client.models import Message

msg = Message.from_dict(raw_dict)
msg.message_id                   # str
msg.role                         # "user" | "assistant"
msg.get_text()                   # combined text from text field or parts
msg.parts                        # list[Part]
msg.from_peer                    # sender peer_id
msg.context_id                   # multi-turn group id (v0.7)
```

#### `Task`

```python
from acp_client.models import Task, TaskStatus

task = Task.from_dict(raw_dict)
task.task_id                     # str
task.status                      # TaskStatus enum
task.is_terminal()               # bool
task.output                      # dict — set on completion
```

#### `TaskStatus`

```python
TaskStatus.SUBMITTED       # initial state
TaskStatus.WORKING         # in progress
TaskStatus.COMPLETED       # done ✓ (terminal)
TaskStatus.FAILED          # error ✓ (terminal)
TaskStatus.CANCELED        # cancelled ✓ (terminal)
TaskStatus.INPUT_REQUIRED  # waiting for user input
TaskStatus.CANCELLING      # two-phase cancel in progress (v2.6)

TaskStatus.COMPLETED.is_terminal()   # True
TaskStatus.terminal_states()         # frozenset of terminal states
```

#### `Part`

```python
from acp_client.models import Part

Part.text_part("Hello")               # text part
Part.data_part({"key": "value"})      # data part
Part.file_part("doc.pdf", "application/pdf", url="https://...")
```

---

### Exceptions

All exceptions are subclasses of `ACPError`:

```python
from acp_client.exceptions import (
    ACPError,             # Base — e.code, e.message, e.response
    ConnectionError,      # Cannot reach relay
    PeerNotFoundError,    # peer_id does not exist — e.peer_id
    TaskNotFoundError,    # task_id does not exist — e.task_id
    TaskNotCancelableError,  # Task in terminal state
    SendError,            # Relay rejected the send
    AuthError,            # 401 / 403
    TimeoutError,         # Blocking operation timed out
)

try:
    client.send_to_peer("bad_peer", "hi")
except PeerNotFoundError as e:
    print(f"Peer {e.peer_id!r} not found")
except ACPError as e:
    print(f"ACP error [{e.code}]: {e.message}")
```

---

## Integration with `acp_relay.py`

`acp-client` speaks directly to a running `acp_relay.py` node.

### Start the relay

```bash
python relay/acp_relay.py --port 7901 --name "MyAgent"
```

### Connect two agents (Python ↔ Python)

**Agent A** (server)
```python
from acp_client import RelayClient

a = RelayClient("http://localhost:7901")
print("Share this link:", a.link())  # acp://192.168.1.x:7901/tok_...
a.wait_for_peer(timeout=60)
a.send("Hello Agent B!")
```

**Agent B** (client — connect via CLI)
```bash
# In another terminal, start a second relay on port 7902
python relay/acp_relay.py --port 7902 --name "AgentB" --connect acp://192.168.1.x:7901/tok_...
```

Or via Python:
```python
from acp_client import AsyncRelayClient
import asyncio

async def main():
    async with AsyncRelayClient("http://localhost:7902") as b:
        await b.connect_peer("acp://192.168.1.x:7901/tok_...")
        await b.send("Hello Agent A!")

asyncio.run(main())
```

### Task delegation

```python
from acp_client import RelayClient

client = RelayClient("http://localhost:7901")

# Create and delegate a task to the connected peer
resp = client.create_task(
    payload={"description": "Summarise this text", "input": {"text": "..."}},
    delegate=True,
)
task_id = resp["task_id"]

# Wait for completion
task = client.wait_for_task(task_id, timeout=120)
print(task.status, task.output)
```

---

## Backward compatibility

The original `sdk/python/acp_sdk/` package remains unchanged.
`acp-client` is the new, pip-installable distribution of the same SDK,
restructured as a proper Python package with:

- Clean submodule layout (`client`, `async_client`, `models`, `exceptions`)
- Typed public API (`AgentCard`, `Message`, `Task`, `TaskStatus`, `Part`)
- Structured exception hierarchy (`ACPError` base class)
- `acp-client` CLI entry-point
- Zero mandatory runtime dependencies (stdlib only)

Existing code using `from acp_sdk import RelayClient` continues to work unchanged.

---

## Development

```bash
# Clone the repo
git clone https://github.com/Kickflip73/agent-communication-protocol.git
cd agent-communication-protocol/sdk/python

# Install in editable mode with dev extras
pip install -e ".[dev]"

# Run tests (60 cases, no relay required)
pytest tests/test_sdk_package.py -v
```

---

## License

Apache 2.0 — see [LICENSE](../../LICENSE).
