"""
ACPClient — HTTP transport client for ACP.
"""
from __future__ import annotations
import json
import asyncio
import logging
from typing import Optional
from .message import ACPMessage

logger = logging.getLogger("acp_sdk")


class ACPClient:
    """
    HTTP-based ACP client. Sends messages to a remote ACP endpoint.

    Example:
        async with ACPClient("https://worker-agent.example.com") as client:
            result = await client.send(
                ACPMessage.task_delegate(
                    from_aid="did:acp:myorg:orchestrator",
                    to_aid="did:acp:myorg:worker",
                    task="Analyze sentiment",
                    input={"text": "I love this product!"},
                )
            )
            print(result.body["output"])
    """

    def __init__(self, base_url: str, token: str = None, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._session = None

    async def __aenter__(self):
        try:
            import aiohttp
            self._session = aiohttp.ClientSession(
                headers={"Authorization": f"Bearer {self.token}"} if self.token else {}
            )
        except ImportError:
            raise ImportError("Install aiohttp: pip install aiohttp")
        return self

    async def __aexit__(self, *args):
        if self._session:
            await self._session.close()

    async def send(self, msg: ACPMessage) -> Optional[ACPMessage]:
        """Send an ACP message via HTTP POST. Returns reply if synchronous."""
        if not self._session:
            raise RuntimeError("Use 'async with ACPClient(...) as client:'")

        url = f"{self.base_url}/acp/v1/messages"
        payload = msg.to_dict()

        async with self._session.post(url, json=payload, timeout=self.timeout) as resp:
            if resp.status == 202:
                return None  # Async accepted
            body = await resp.json()
            return ACPMessage.from_dict(body)

    async def query_agents(self, capability: str = None) -> list[dict]:
        """Query the agent registry."""
        if not self._session:
            raise RuntimeError("Use 'async with ACPClient(...) as client:'")

        url = f"{self.base_url}/acp/v1/agents"
        params = {}
        if capability:
            params["capability"] = capability

        async with self._session.get(url, params=params) as resp:
            data = await resp.json()
            return data.get("agents", [])
