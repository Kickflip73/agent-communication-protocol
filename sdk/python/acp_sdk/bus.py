"""
InProcessBus — in-process message bus for testing and single-process MAS.
"""
from __future__ import annotations
import asyncio
import logging
from typing import Optional, TYPE_CHECKING
from .message import ACPMessage

if TYPE_CHECKING:
    from .agent import ACPAgent

logger = logging.getLogger("acp_sdk")


class InProcessBus:
    """
    Simple in-process message router.
    Suitable for unit tests and single-machine multi-agent setups.

    Example:
        bus = InProcessBus()
        orchestrator = OrchestratorAgent("did:acp:local:orchestrator", bus)
        worker = WorkerAgent("did:acp:local:worker", bus)

        result = await orchestrator.send(
            ACPMessage.task_delegate(
                from_aid="did:acp:local:orchestrator",
                to_aid="did:acp:local:worker",
                task="Process this data",
                input={"data": [1, 2, 3]},
            )
        )
    """

    def __init__(self):
        self._agents: dict[str, "ACPAgent"] = {}
        self._topic_subscribers: dict[str, list["ACPAgent"]] = {}
        self._message_log: list[ACPMessage] = []

    def register(self, agent: "ACPAgent"):
        self._agents[agent.aid] = agent
        logger.debug(f"Bus: registered agent {agent.aid}")

    def unregister(self, aid: str):
        self._agents.pop(aid, None)

    async def route(self, msg: ACPMessage) -> Optional[ACPMessage]:
        """Route a message to its recipient and return the response."""
        self._message_log.append(msg)

        to = msg.to

        # Pub/sub broadcast
        if to.startswith("topic:"):
            await self._broadcast(to, msg)
            return None

        # Unicast
        agent = self._agents.get(to)
        if not agent:
            from .message import MessageType
            return ACPMessage(
                type=MessageType.ERROR,
                from_aid="did:acp:local:bus",
                to=msg.from_aid,
                reply_to=msg.id,
                body={"code": "acp.unknown_agent", "message": f"Agent '{to}' not found"},
            )

        return await agent.receive(msg)

    async def _broadcast(self, topic: str, msg: ACPMessage):
        subscribers = self._topic_subscribers.get(topic, [])
        await asyncio.gather(*[agent.receive(msg) for agent in subscribers])

    def subscribe(self, topic: str, agent: "ACPAgent"):
        self._topic_subscribers.setdefault(topic, []).append(agent)

    @property
    def message_log(self) -> list[ACPMessage]:
        return list(self._message_log)

    def agents(self) -> list[str]:
        return list(self._agents.keys())
