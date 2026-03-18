"""
ACP ↔ LangChain / LangGraph integration.

Usage:
    from langchain_core.tools import tool
    from acp_sdk.integrations.langchain import acp_agent, expose_as_acp

    # Option A: Expose an existing LangChain agent via ACP
    from langgraph.prebuilt import create_react_agent
    agent = create_react_agent(llm, tools)
    expose_as_acp(agent, aid="did:acp:local:my-lc-agent", gateway="http://localhost:8765")

    # Option B: Call a remote ACP agent as a LangChain tool
    remote_tool = acp_agent_tool(
        aid="did:acp:local:remote-agent",
        gateway="http://localhost:8765",
        description="A remote agent that summarizes text",
    )
"""
from __future__ import annotations
import asyncio
import json
import uuid
import logging
from typing import Any, Callable

log = logging.getLogger("acp_sdk.langchain")


def expose_as_acp(
    agent_runnable,
    aid: str,
    gateway: str = "http://localhost:8765",
    capabilities: list[str] = None,
    name: str = None,
):
    """
    Expose a LangChain Runnable (agent, chain, etc.) as an ACP agent.
    Registers with the gateway and starts listening for task.delegate messages.
    """
    try:
        import aiohttp
    except ImportError:
        raise ImportError("pip install aiohttp")

    name = name or aid.split(":")[-1]
    caps = capabilities or ["invoke"]

    async def _run():
        # Register with gateway
        async with aiohttp.ClientSession() as session:
            await session.post(f"{gateway}/acp/v1/agents/register", json={
                "aid": aid,
                "info": {"name": name, "capabilities": caps},
                "callback_url": None,  # will use WebSocket
            })

        # Connect via WebSocket
        import aiohttp
        ws_url = gateway.replace("http://", "ws://").replace("https://", "wss://")
        ws_url += f"/acp/v1/ws/{aid.replace(':', '__COLON__')}"

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(ws_url) as ws:
                log.info(f"ACP: {aid} connected to gateway {gateway}")

                # Send hello
                from acp_sdk.message import ACPMessage
                hello = ACPMessage.agent_hello(aid, "did:acp:local:gateway", name, caps)
                await ws.send_str(hello.to_json())

                async for ws_msg in ws:
                    if ws_msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(ws_msg.data)
                        if data.get("type") == "task.delegate":
                            # Invoke the LangChain agent
                            task_input = data["body"].get("input", {})
                            query = task_input.get("query") or task_input.get("input") or str(task_input)
                            try:
                                result = await agent_runnable.ainvoke({"messages": [("human", query)]})
                                output = result.get("output") or str(result)
                                reply = ACPMessage.task_result(
                                    from_aid=aid, to_aid=data["from"],
                                    status="success", output={"output": output},
                                    reply_to=data["id"], correlation_id=data.get("correlation_id"),
                                )
                            except Exception as e:
                                reply = ACPMessage.error(aid, data["from"], "acp.handler_error", str(e), data["id"])
                            await ws.send_str(reply.to_json())

    # Run in background
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_run())
    except RuntimeError:
        asyncio.run(_run())

    log.info(f"ACP: {aid} registered (LangChain adapter)")


def acp_agent_tool(aid: str, gateway: str = "http://localhost:8765", description: str = ""):
    """
    Create a LangChain Tool that delegates to a remote ACP agent.

    Usage:
        tool = acp_agent_tool("did:acp:local:summarizer", gateway="http://localhost:8765")
        agent = create_react_agent(llm, [tool])
    """
    try:
        from langchain_core.tools import tool as lc_tool
    except ImportError:
        raise ImportError("pip install langchain-core")

    import aiohttp

    @lc_tool(description=description or f"Delegate to ACP agent: {aid}")
    async def call_acp_agent(input: str) -> str:
        """Call a remote ACP agent and return its result."""
        from acp_sdk.message import ACPMessage
        msg = ACPMessage.task_delegate(
            from_aid="did:acp:local:langchain-caller",
            to_aid=aid,
            task=input,
            input={"query": input},
            correlation_id="lc_" + str(uuid.uuid4())[:8],
        )
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{gateway}/acp/v1/messages", json=msg.to_dict()
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("body", {}).get("output", {}).get("output", str(data))
        return "No response from remote agent."

    call_acp_agent.__name__ = f"acp_{aid.split(':')[-1]}"
    return call_acp_agent
