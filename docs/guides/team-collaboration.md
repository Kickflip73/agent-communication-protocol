# Team Collaboration

Connect an Orchestrator to multiple Worker agents for parallel task distribution.

## Architecture

```
Orchestrator (7901)
    ├── Worker-1 (peer_001) — data processing
    └── Worker-2 (peer_002) — report generation
```

## Setup

Start all three relays:

```bash
# Orchestrator
python3 relay/acp_relay.py --name Orchestrator --http-port 7901 --ws-port 7801

# Worker 1
python3 relay/acp_relay.py --name Worker1 --http-port 7902 --ws-port 7802

# Worker 2  
python3 relay/acp_relay.py --name Worker2 --http-port 7903 --ws-port 7803
```

Get Worker links:

```bash
curl http://localhost:7902/status | jq .link  # Worker1 link
curl http://localhost:7903/status | jq .link  # Worker2 link
```

## Connect Workers to Orchestrator

```bash
# Worker1 connects to Orchestrator
curl -X POST http://localhost:7902/peers/connect \
     -d '{"link": "acp://...orchestrator_link..."}'
# → {"ok":true,"peer_id":"peer_001"}

# Worker2 connects to Orchestrator
curl -X POST http://localhost:7903/peers/connect \
     -d '{"link": "acp://...orchestrator_link..."}'
# → {"ok":true,"peer_id":"peer_001"}
```

Now Orchestrator has two peers:

```bash
curl http://localhost:7901/peers
```
```json
{
  "peer_001": {"name": "Worker1", "connected": true},
  "peer_002": {"name": "Worker2", "connected": true}
}
```

## Targeted Messaging

With multiple peers, always use `/peer/{id}/send` to target a specific worker:

```bash
# Dispatch task to Worker1
curl -X POST http://localhost:7901/peer/peer_001/send \
     -d '{
       "role": "agent",
       "parts": [{"type": "data", "data": {"task": "process_dataset_A"}}]
     }'

# Dispatch task to Worker2
curl -X POST http://localhost:7901/peer/peer_002/send \
     -d '{
       "role": "agent",
       "parts": [{"type": "data", "data": {"task": "generate_report_B"}}]
     }'
```

!!! warning "Use `/peer/{id}/send` with multiple peers"
    When connected to 2+ peers, `/message:send` will return `ERR_AMBIGUOUS_PEER`.
    Always use `/peer/{id}/send` to target a specific peer.

## Python SDK: Orchestrator Pattern

```python
from acp_client import RelayClient
import concurrent.futures

orch = RelayClient("http://localhost:7901")

# Get peer IDs (workers already connected)
peers = orch.peers()
worker_ids = list(peers.keys())  # ["peer_001", "peer_002"]

# Distribute work in parallel
tasks = [
    {"worker": "peer_001", "job": "analyze_dataset_A"},
    {"worker": "peer_002", "job": "generate_report_B"},
]

def dispatch(task):
    orch.send(
        parts=[{"type": "data", "data": {"job": task["job"]}}],
        peer_id=task["worker"]
    )
    return task["worker"]

with concurrent.futures.ThreadPoolExecutor() as ex:
    results = list(ex.map(dispatch, tasks))

print(f"Dispatched to {len(results)} workers")

# Collect results via SSE stream
completed = {}
for msg in orch.stream(timeout=30):
    peer = msg.from_peer
    result = msg.parts[0].data if msg.parts[0].type == "data" else msg.parts[0].content
    completed[peer] = result
    if len(completed) == len(worker_ids):
        break

print("All workers responded:", completed)
```

## Task-Based Collaboration

For longer-running work, use Tasks:

```python
# Create a task on Worker1
worker1 = RelayClient("http://localhost:7902")
# (Worker1 creates its own task to track work)
task = worker1.create_task(
    task_id="analysis_001",
    title="Analyze Dataset A",
    role="agent"
)

# Orchestrator subscribes to task updates via SSE
for event in worker1.task_stream("analysis_001"):
    print(f"Worker1 status: {event.state}")
    if event.state in ("completed", "failed"):
        break
```

## Ring Pipeline

For sequential processing (A → B → C → A):

```
AgentA → AgentB (enriches) → AgentC (formats) → AgentA (final result)
```

Each agent connects to the next:

```bash
# A connects to B, B connects to C, C connects to A
# Each agent's relay forwards messages downstream
```

See the [test_scenario_c test](https://github.com/Kickflip73/agent-communication-protocol/blob/main/tests/test_scenario_bc.py) for a complete example.
