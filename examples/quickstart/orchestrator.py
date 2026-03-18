"""
ACP Quickstart — Orchestrator (stdio transport)

Demonstrates:
1. Spawning an agent as a subprocess (stdio transport)
2. Capability negotiation (agent.hello handshake)
3. Sending task.delegate and receiving task.result
4. Parallel dispatch to multiple agents (same agent, two tasks)
5. Graceful shutdown (agent.bye)

Run:
    python orchestrator.py
"""
import asyncio
import json
import datetime
import uuid
import sys
from pathlib import Path

# ── ACP message helpers (inline, no SDK dependency) ──────────────────────────

def now() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"

def make_id() -> str:
    return "msg_" + uuid.uuid4().hex[:12]

def make_msg(type_: str, from_: str, to: str, body: dict, **kwargs) -> dict:
    m = {"acp": "0.1", "id": make_id(), "type": type_,
         "from": from_, "to": to, "ts": now(), "body": body}
    m.update(kwargs)
    return m

# ── StdioClient ───────────────────────────────────────────────────────────────

class StdioClient:
    """Spawn an ACP agent as a subprocess and communicate via stdio."""

    def __init__(self, command: list[str], caller_aid: str):
        self.command    = command
        self.caller_aid = caller_aid
        self.peer_aid   = None        # filled after hello handshake
        self.capabilities: list[str] = []
        self._proc      = None

    async def __aenter__(self):
        self._proc = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await self._handshake()
        return self

    async def __aexit__(self, *_):
        await self._send(make_msg("agent.bye", self.caller_aid, self.peer_aid or "unknown", {}))
        self._proc.stdin.close()
        try:
            await asyncio.wait_for(self._proc.wait(), timeout=3)
        except asyncio.TimeoutError:
            self._proc.kill()

    async def _send(self, msg: dict):
        line = (json.dumps(msg, ensure_ascii=False) + "\n").encode()
        self._proc.stdin.write(line)
        await self._proc.stdin.drain()

    async def _recv(self) -> dict:
        line = await self._proc.stdout.readline()
        return json.loads(line.strip())

    async def _handshake(self):
        hello = make_msg("agent.hello", self.caller_aid, "unknown", {
            "name": "Orchestrator", "version": "1.0.0", "acp_version": "0.1",
            "capabilities": ["orchestrate"],
        })
        await self._send(hello)
        resp = await self._recv()
        assert resp["type"] == "agent.hello", f"Expected agent.hello, got {resp['type']}"
        self.peer_aid     = resp["from"]
        self.capabilities = resp["body"].get("capabilities", [])
        print(f"  ✓ Handshake OK — peer: {self.peer_aid}")
        print(f"  ✓ Peer capabilities: {self.capabilities}")

    async def delegate(self, task: str, input_: dict, correlation_id: str = None) -> dict:
        msg = make_msg("task.delegate", self.caller_aid, self.peer_aid, {
            "task": task, "input": input_, "constraints": {},
        }, correlation_id=correlation_id)
        await self._send(msg)
        return await self._recv()

# ── Demo ─────────────────────────────────────────────────────────────────────

AGENT_SCRIPT = Path(__file__).parent / "agent_summarizer.py"
ORCHESTRATOR_AID = "did:acp:local:orchestrator"

async def demo_single_task(client: StdioClient):
    print("\n[Demo 1] Single task — summarize one document")
    text = ("The Agent Communication Protocol (ACP) is a vendor-neutral open standard "
            "that defines how autonomous AI agents communicate with each other. "
            "It provides a standard message envelope, core message types, and transport bindings "
            "for stdio, HTTP/SSE, and TCP.")
    result = await client.delegate("Summarize this document", {"text": text})
    assert result["type"] == "task.result", f"Unexpected: {result['type']}"
    print(f"  Status : {result['body']['status']}")
    print(f"  Summary: {result['body']['output']['summary']}")
    print(f"  Words  : {result['body']['output']['word_count']}")
    print(f"  Usage  : {result['body']['usage']}")

async def demo_parallel_tasks(client: StdioClient):
    print("\n[Demo 2] Sequential tasks sharing a correlation_id (same workflow)")
    print("  Note: stdio is inherently sequential; HTTP/TCP transports support true parallelism.")
    workflow_id = "workflow_" + uuid.uuid4().hex[:8]

    texts = [
        "First document: short text for summarization.",
        "Second document: another piece of text to be summarized by the agent.",
    ]
    for i, text in enumerate(texts, 1):
        r = await client.delegate(f"Task {i}", {"text": text}, correlation_id=workflow_id)
        print(f"  Task {i} [{workflow_id}] → {r['body']['status']}: {r['body']['output']['summary']}")

async def demo_error_handling(client: StdioClient):
    print("\n[Demo 3] Error handling — send a task with missing input")
    result = await client.delegate("Summarize this", {})   # missing 'text'
    print(f"  Error code   : {result['body']['code']}")
    print(f"  Error message: {result['body']['message']}")

async def main():
    print("=" * 60)
    print("ACP Quickstart — stdio transport demo")
    print("=" * 60)
    print(f"\nSpawning agent: python {AGENT_SCRIPT.name}")

    async with StdioClient([sys.executable, str(AGENT_SCRIPT)], ORCHESTRATOR_AID) as client:
        await demo_single_task(client)
        await demo_parallel_tasks(client)
        await demo_error_handling(client)

    print("\n✓ All demos completed. Agent shut down gracefully.")


if __name__ == "__main__":
    asyncio.run(main())
