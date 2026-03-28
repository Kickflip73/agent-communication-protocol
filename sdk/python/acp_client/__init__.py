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
from .models import AgentCard, Message, Task, TaskStatus, Part, PartType, Extension
from .exceptions import (
    ACPError,
    PeerNotFoundError,
    TaskNotFoundError,
    TaskNotCancelableError,
    SendError,
    AuthError,
)

__version__ = "1.9.0"

# ── Optional integrations (lazy import; framework not required) ───────────────
# LangChain integration is available when langchain is installed:
#   from acp_client.integrations.langchain import ACPTool, create_acp_tool
#   from acp_client import create_acp_tool  # re-exported here for convenience
try:
    from .integrations.langchain import create_acp_tool  # noqa: F401
    _langchain_available = True
except ImportError:
    _langchain_available = False


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
    "Extension",
    # Exceptions
    "ACPError",
    "PeerNotFoundError",
    "TaskNotFoundError",
    "TaskNotCancelableError",
    "SendError",
    "AuthError",
    # Integrations (conditional)
    "create_acp_tool",
]
