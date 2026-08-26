"""
ACP-P2P Demo: 两个 Agent 直接通信，零第三方依赖

运行方式：
    # 方式一：两个进程
    python demo_p2p.py receiver   # 终端1，打印 ACP URI
    python demo_p2p.py sender <acp://...>  # 终端2，粘贴 URI

    # 方式二：单进程测试（同一个脚本内两个 Agent）
    python demo_p2p.py local
"""
import asyncio
import sys

sys.path.insert(0, "..")
from sdk.acp_p2p import P2PAgent, ACPURI


# ════════════════════════════════════════════════════════════════
#  接收方 Agent（10行）
# ════════════════════════════════════════════════════════════════

def run_receiver():
    agent = P2PAgent("echo-agent", port=7700, capabilities=["echo", "reverse"])

    @agent.on_task
    async def handle(task: str, input_data: dict) -> dict:
        text = input_data.get("text", "")
        if "reverse" in task.lower():
            return {"result": text[::-1]}
        return {"echo": text, "task_received": task}

    print("Receiver started. Share the URI above with the sender.")
    agent.start(block=True)


# ════════════════════════════════════════════════════════════════
#  发送方 Agent
# ════════════════════════════════════════════════════════════════

async def run_sender(target_uri: str):
    sender = P2PAgent("caller-agent", port=7701)

    print(f"\n→ Sending task to: {target_uri}\n")

    # Task 1: echo
    result = await sender.send(
        to=target_uri,
        task="Echo this message",
        input={"text": "Hello from ACP-P2P!"},
    )
    print(f"Echo result:   {result['body']['output']}")

    # Task 2: reverse
    result2 = await sender.send(
        to=target_uri,
        task="Reverse this string",
        input={"text": "ACP Protocol"},
    )
    print(f"Reverse result: {result2['body']['output']}")

    # Discover peer identity
    identity = await sender.discover(target_uri)
    print(f"\nPeer identity: {identity}")


# ════════════════════════════════════════════════════════════════
#  单进程本地测试（最简单的演示方式）
# ════════════════════════════════════════════════════════════════

async def run_local():
    print("=== ACP-P2P Local Demo (Two Agents, One Process) ===\n")

    # Agent A: worker
    worker = P2PAgent("worker", port=7800, capabilities=["summarize"])

    @worker.on_task
    async def worker_handle(task: str, input_data: dict) -> dict:
        text = input_data.get("text", "")
        return {"summary": text[:60] + "..." if len(text) > 60 else text}

    # Agent B: orchestrator
    orchestrator = P2PAgent("orchestrator", port=7801, capabilities=["coordinate"])

    @orchestrator.on_task
    async def orch_handle(task: str, input_data: dict) -> dict:
        return {"status": "delegated"}

    # Start both servers in background
    async with worker, orchestrator:
        print(f"Worker URI:       {worker.uri}")
        print(f"Orchestrator URI: {orchestrator.uri}\n")

        # Orchestrator asks Worker to summarize
        result = await orchestrator.send(
            to=str(worker.uri),
            task="Summarize this article",
            input={"text": "Artificial intelligence is rapidly transforming every industry, from healthcare to finance..."},
        )
        print(f"✅ Result from worker: {result['body']['output']}\n")

        # Worker asks Orchestrator something back (bidirectional)
        result2 = await worker.send(
            to=str(orchestrator.uri),
            task="Are you available?",
            input={},
        )
        print(f"✅ Result from orchestrator: {result2['body']['output']}")

    print("\n✅ ACP-P2P demo complete — zero third-party servers used!")


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "local"

    if mode == "receiver":
        run_receiver()
    elif mode == "sender":
        if len(sys.argv) < 3:
            print("Usage: python demo_p2p.py sender <acp://host:port/name>")
            sys.exit(1)
        asyncio.run(run_sender(sys.argv[2]))
    elif mode == "local":
        asyncio.run(run_local())
    else:
        print("Usage: demo_p2p.py [receiver|sender <uri>|local]")
