"""
ACP ↔ AutoGen integration.

Usage:
    from autogen import AssistantAgent, UserProxyAgent
    from acp_sdk.integrations.autogen import ACPAssistantAgent, expose_autogen_as_acp

    # Option A: Wrap an existing AutoGen agent to speak ACP
    assistant = AssistantAgent("assistant", llm_config={...})
    expose_autogen_as_acp(assistant, aid="did:acp:local:autogen-assistant",
                          gateway="http://localhost:8765")

    # Option B: Use ACPAssistantAgent directly (drop-in replacement)
    agent = ACPAssistantAgent(
        name="Summarizer",
        aid="did:acp:local:summarizer",
        gateway="http://localhost:8765",
        llm_config={...},
    )
"""
from __future__ import annotations
import asyncio
import json
import logging
from typing import Optional

log = logging.getLogger("acp_sdk.autogen")


def expose_autogen_as_acp(
    agent,  # AutoGen agent instance
    aid: str,
    gateway: str = "http://localhost:8765",
    capabilities: list[str] = None,
):
    """Wrap an AutoGen agent and register it with ACP Gateway."""

    async def _handler(msg_data: dict) -> str:
        """Convert ACP task.delegate → AutoGen message → response."""
        task = msg_data["body"].get("task", "")
        input_data = msg_data["body"].get("input", {})
        query = input_data.get("query") or input_data.get("text") or task

        # AutoGen: initiate a chat to get a response
        result = agent.generate_reply(
            messages=[{"role": "user", "content": query}]
        )
        return result if isinstance(result, str) else str(result)

    _register_http_handler(aid, gateway, capabilities or ["chat", "generate"], _handler)
    log.info(f"AutoGen agent '{agent.name}' exposed as ACP agent {aid}")


def _register_http_handler(aid: str, gateway: str, capabilities: list, handler):
    """Register agent with gateway using HTTP callback pattern."""
    try:
        from fastapi import FastAPI, Request
        import uvicorn, threading, aiohttp
    except ImportError:
        raise ImportError("pip install fastapi uvicorn aiohttp")

    import socket
    # Find a free port for the callback server
    s = socket.socket(); s.bind(("", 0)); port = s.getsockname()[1]; s.close()
    callback_url = f"http://host.docker.internal:{port}/acp/callback"

    callback_app = FastAPI()

    @callback_app.post("/acp/callback")
    async def receive(request: Request):
        data = await request.json()
        from acp_sdk.message import ACPMessage
        if data.get("type") == "task.delegate":
            try:
                output = await handler(data)
                reply = ACPMessage.task_result(
                    from_aid=aid, to_aid=data["from"],
                    status="success", output={"output": output},
                    reply_to=data["id"],
                )
            except Exception as e:
                reply = ACPMessage.error(aid, data["from"], "acp.handler_error", str(e))
            return reply.to_dict()
        return {"success": True}

    # Start callback server in background thread
    def run_server():
        uvicorn.run(callback_app, host="0.0.0.0", port=port, log_level="warning")

    t = threading.Thread(target=run_server, daemon=True)
    t.start()

    # Register with gateway
    async def _register():
        import aiohttp
        async with aiohttp.ClientSession() as session:
            await session.post(f"{gateway}/acp/v1/agents/register", json={
                "aid": aid,
                "info": {"capabilities": capabilities},
                "callback_url": callback_url,
            })
        log.info(f"Registered {aid} with callback {callback_url}")

    asyncio.get_event_loop().run_until_complete(_register())
