"""
acp-client — Python SDK for the Agent Communication Protocol (ACP).

Public API
----------
    from acp_client import RelayClient, AsyncRelayClient
    from acp_client.models import AgentCard, Message, Task, TaskStatus
    from acp_client.exceptions import ACPError, PeerNotFoundError, TaskNotFoundError

Quick-start (sync)
------------------
    from acp_client import RelayClient

    client = RelayClient("http://localhost:7901")
    client.send("Hello from acp-client!")
    for msg in client.recv():
        print(msg)

Quick-start (async)
-------------------
    import asyncio
    from acp_client import AsyncRelayClient

    async def main():
        async with AsyncRelayClient("http://localhost:7901") as client:
            await client.send("Hello async!")
            async for event in client.stream(timeout=30):
                print(event)

    asyncio.run(main())
"""

from .client import RelayClient
from .async_client import AsyncRelayClient
from .models import AgentCard, Message, Task, TaskStatus, Part, PartType
from .exceptions import (
    ACPError,
    PeerNotFoundError,
    TaskNotFoundError,
    TaskNotCancelableError,
    SendError,
    AuthError,
)

__version__ = "1.7.0"
__all__ = [
    # Clients
    "RelayClient",
    "AsyncRelayClient",
    # Models
    "AgentCard",
    "Message",
    "Task",
    "TaskStatus",
    "Part",
    "PartType",
    # Exceptions
    "ACPError",
    "PeerNotFoundError",
    "TaskNotFoundError",
    "TaskNotCancelableError",
    "SendError",
    "AuthError",
]
