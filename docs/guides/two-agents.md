# Two Agents in 60 Seconds

The fastest path from zero to two communicating agents.

## What You'll Build

```
Agent A ──────────────── Agent B
  [7901]    acp://link    [7902]
     ↑                      ↑
  SSE stream           sends messages
```

## Run It

=== "Two Terminals"

    **Terminal 1 — Agent A:**
    ```bash
    python3 relay/acp_relay.py --name AgentA
    # copy the acp://... link
    ```

    **Terminal 2 — Agent B:**
    ```bash
    python3 relay/acp_relay.py --name AgentB --http-port 7902 --ws-port 7802

    # Connect B → A (replace with your actual link)
    curl -X POST http://localhost:7902/peers/connect \
         -d '{"link":"acp://1.2.3.4:7801/tok_xxx"}'

    # Send
    curl -X POST http://localhost:7902/message:send \
         -d '{"role":"agent","parts":[{"type":"text","content":"Hello A!"}]}'
    ```

=== "Python SDK"

    ```python
    import subprocess, time
    from acp_client import RelayClient

    # In practice, AgentA is a separate process/machine.
    # Here we simulate locally for the demo.

    # Start AgentA relay (would normally be remote)
    proc_a = subprocess.Popen(["python3","relay/acp_relay.py",
                                "--name","AgentA","--http-port","7901"])
    time.sleep(2)  # wait for startup

    a = RelayClient("http://localhost:7901")
    link_a = a.status()["link"]  # get AgentA's link

    # AgentB connects to AgentA
    proc_b = subprocess.Popen(["python3","relay/acp_relay.py",
                                "--name","AgentB","--http-port","7902","--ws-port","7802"])
    time.sleep(2)
    b = RelayClient("http://localhost:7902")
    peer_id = b.connect(link_a)

    # Send and receive
    b.send("Hello from Agent B!", peer_id=peer_id)

    # Agent A receives
    msgs = a.recv(timeout=3)
    for msg in msgs:
        print(f"AgentA got: {msg.parts[0].content}")
        # Reply
        a.send("Hello back from Agent A!", peer_id=msg.from_peer)
    ```

=== "Async SDK"

    ```python
    import asyncio
    from acp_client import AsyncRelayClient

    async def agent_b_task(link_a: str):
        async with AsyncRelayClient("http://localhost:7902") as b:
            peer_id = await b.connect(link_a)
            await b.send("Hello async!", peer_id=peer_id)
            async for msg in b.stream(timeout=5):
                print(f"B got reply: {msg.parts[0].content}")
                break

    asyncio.run(agent_b_task("acp://1.2.3.4:7801/tok_xxx"))
    ```

## Verify the Connection

```bash
# Check Agent A's peer list
curl http://localhost:7901/peers | python3 -m json.tool
```

```json
{
  "peer_001": {
    "name": "AgentB",
    "connected": true,
    "messages_sent": 0,
    "messages_received": 1
  }
}
```

## Next Steps

- Scale up: [Team Collaboration](team-collaboration.md) — orchestrator + multiple workers
- Production: [Security](../security.md) — enable HMAC signing
- Cross-network: [NAT Traversal](../nat-traversal.md) — agents on different machines
