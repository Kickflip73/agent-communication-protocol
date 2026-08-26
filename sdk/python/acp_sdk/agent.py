"""
ACPAgent — base class for building ACP-compliant agents.
"""
from __future__ import annotations
import asyncio
import logging
from typing import Callable, Awaitable, Optional, TYPE_CHECKING
from .message import ACPMessage, MessageType

if TYPE_CHECKING:
    from .bus import InProcessBus

logger = logging.getLogger("acp_sdk")

HandlerFunc = Callable[[ACPMessage], Awaitable[Optional[ACPMessage]]]


class ACPAgent:
    """
    Base class for ACP agents.

    Subclass this and implement `handle_task_delegate` (or register handlers).

    Example:
        class SummarizerAgent(ACPAgent):
            async def handle_task_delegate(self, msg: ACPMessage) -> ACPMessage:
                text = msg.body["input"].get("text", "")
                summary = summarize(text)  # your logic
                return ACPMessage.task_result(
                    from_aid=self.aid,
                    to_aid=msg.from_aid,
                    status="success",
                    output={"summary": summary},
                    reply_to=msg.id,
                    correlation_id=msg.correlation_id,
                )
    """

    def __init__(self, aid: str, bus: "InProcessBus" = None):
        self.aid = aid
        self.bus = bus
        self._handlers: dict[MessageType, HandlerFunc] = {}
        self._setup_default_handlers()

        if bus:
            bus.register(self)

    def _setup_default_handlers(self):
        self.register_handler(MessageType.TASK_DELEGATE, self._default_task_delegate)
        self.register_handler(MessageType.TASK_CANCEL,   self._default_task_cancel)
        self.register_handler(MessageType.AGENT_HELLO,   self._default_agent_hello)

    def register_handler(self, msg_type: MessageType, handler: HandlerFunc):
        self._handlers[msg_type] = handler

    async def receive(self, msg: ACPMessage) -> Optional[ACPMessage]:
        """Called by the bus/transport when a message arrives for this agent."""
        logger.debug(f"[{self.aid}] received {msg.type} from {msg.from_aid}")
        handler = self._handlers.get(msg.type)
        if handler:
            try:
                return await handler(msg)
            except Exception as e:
                logger.error(f"[{self.aid}] handler error: {e}")
                return ACPMessage.error(
                    from_aid=self.aid,
                    to_aid=msg.from_aid,
                    code="acp.handler_error",
                    message=str(e),
                    reply_to=msg.id,
                )
        else:
            return ACPMessage.error(
                from_aid=self.aid,
                to_aid=msg.from_aid,
                code="acp.unsupported_type",
                message=f"Message type '{msg.type}' not supported",
                reply_to=msg.id,
            )

    async def send(self, msg: ACPMessage) -> Optional[ACPMessage]:
        """Send a message via the bus."""
        if self.bus:
            return await self.bus.route(msg)
        raise RuntimeError("No bus configured. Use ACPClient for HTTP transport.")

    # --- Override these in subclasses ---

    async def handle_task_delegate(self, msg: ACPMessage) -> Optional[ACPMessage]:
        """Override to handle incoming task.delegate messages."""
        return ACPMessage.error(
            from_aid=self.aid,
            to_aid=msg.from_aid,
            code="acp.capability_missing",
            message="This agent has not implemented task handling.",
            reply_to=msg.id,
        )

    # --- Default handlers ---

    async def _default_task_delegate(self, msg: ACPMessage) -> Optional[ACPMessage]:
        return await self.handle_task_delegate(msg)

    async def _default_task_cancel(self, msg: ACPMessage) -> Optional[ACPMessage]:
        logger.info(f"[{self.aid}] task cancelled: {msg.reply_to}")
        return None

    async def _default_agent_hello(self, msg: ACPMessage) -> Optional[ACPMessage]:
        # Echo back our own hello
        return ACPMessage.agent_hello(
            from_aid=self.aid,
            registry_aid=msg.from_aid,
            name=self.__class__.__name__,
            capabilities=list(self._handlers.keys()),
        )
