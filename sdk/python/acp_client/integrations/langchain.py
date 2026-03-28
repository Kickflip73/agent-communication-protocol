"""
acp_client.integrations.langchain — LangChain Tool Adapter for ACP.

Wraps an ACP Relay endpoint as a LangChain ``BaseTool`` so that any
LangChain Agent can communicate with a remote ACP peer without any changes
to the core ``acp_client`` package (langchain is an optional dependency).

Usage
-----
    from acp_client.integrations.langchain import ACPTool, create_acp_tool

    tool = ACPTool(relay_url="http://localhost:8765", peer_id="agent_b")
    # or use the factory helper:
    tool = create_acp_tool("http://localhost:8765", "agent_b", timeout=60)

    # Use with LangChain agent (requires langchain installed):
    from langchain.agents import initialize_agent, AgentType
    from langchain_openai import ChatOpenAI

    llm  = ChatOpenAI(model="gpt-4o")
    agent = initialize_agent(
        [tool], llm,
        agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
        verbose=True,
    )
    result = agent.run("Ask agent_b to summarise the latest news")

Design notes
------------
- Zero mandatory dependency on langchain in core ``acp_client``.  LangChain
  is imported lazily inside ``ACPTool`` and ``ACPCallbackHandler``; if it is
  not installed an ``ImportError`` with a helpful install hint is raised at
  instantiation time, not at import time.
- ``_run`` is synchronous and delegates to ``RelayClient.send_and_recv``.
- ``_arun`` wraps the synchronous call via ``asyncio.get_event_loop().run_in_executor``
  so the tool is usable in async LangChain chains without blocking the event loop.
- ``ACPCallbackHandler`` records structured log entries for every ACP tool
  invocation; it can be passed as a ``callbacks`` argument to any LangChain
  chain or agent.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from ..client import RelayClient
from ..exceptions import ACPError

logger = logging.getLogger("acp_client.integrations.langchain")

# ── Lazy-import helpers ────────────────────────────────────────────────────────

_INSTALL_HINT = (
    "LangChain is not installed. "
    "Install it with: pip install langchain  "
    "or: pip install 'acp-client[langchain]'"
)


def _import_base_tool():
    """Lazily import langchain BaseTool; raise helpful ImportError if absent."""
    try:
        from langchain.tools import BaseTool  # type: ignore[import]
        return BaseTool
    except ImportError as exc:
        raise ImportError(_INSTALL_HINT) from exc


def _import_base_callback_handler():
    """Lazily import langchain BaseCallbackHandler."""
    try:
        from langchain.callbacks.base import BaseCallbackHandler  # type: ignore[import]
        return BaseCallbackHandler
    except ImportError as exc:
        raise ImportError(_INSTALL_HINT) from exc


# ── ACPTool ────────────────────────────────────────────────────────────────────

#: Canonical tool name visible to the LLM.
_ACP_TOOL_NAME = "acp_send"

#: Human-readable description surfaced to the LLM reasoning engine.
_ACP_TOOL_DESCRIPTION = (
    "Send a message to a remote ACP (Agent Communication Protocol) peer "
    "and receive its reply. Use this tool whenever you need to delegate a "
    "sub-task to another agent, retrieve information from a specialised "
    "agent, or coordinate work across agent boundaries. "
    "Input: a plain-text message string. "
    "Output: the reply text from the remote agent."
)


def _acp_tool_run(self: Any, message: str, *args: Any, **kwargs: Any) -> str:
    """
    Synchronously send *message* to the ACP peer and return the reply.

    Returns the reply text on success, or an error description string on
    failure (so the LLM can observe the error and retry / recover).
    """
    relay_url: str = self.__dict__["_relay_url"]
    peer_id: str = self.__dict__["_peer_id"]
    timeout: float = self.__dict__["_timeout"]

    logger.debug(
        "ACPTool._run: relay_url=%s peer_id=%r msg_len=%d",
        relay_url, peer_id, len(message),
    )
    try:
        client = RelayClient(base_url=relay_url, timeout=timeout)
        if peer_id:
            # Send to specific peer and poll for a reply
            client.send_to_peer(peer_id, text=message)
            before_count = len(client.recv(limit=200))
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                msgs = client.recv(limit=200)
                if len(msgs) > before_count:
                    reply_msg = msgs[-1]
                    text = reply_msg.get("text") or str(reply_msg.get("parts", ""))
                    logger.debug("ACPTool._run: received reply len=%d", len(text))
                    return text
                time.sleep(0.5)
            return "Error: timeout waiting for reply from ACP peer"
        else:
            result = client.send_and_recv(message, timeout=timeout)
            if result is None:
                return "Error: timeout waiting for reply from ACP peer"
            text = result.get("text") or str(result.get("parts", ""))
            logger.debug("ACPTool._run: received reply len=%d", len(text))
            return text
    except ACPError as exc:
        logger.warning("ACPTool._run: ACPError: %s", exc)
        return f"Error: ACP communication failed — {exc}"
    except Exception as exc:  # pragma: no cover
        logger.error("ACPTool._run: unexpected error: %s", exc, exc_info=True)
        return f"Error: unexpected failure — {exc}"


async def _acp_tool_arun(self: Any, message: str, *args: Any, **kwargs: Any) -> str:
    """
    Asynchronous version of ``_run``.

    Runs the synchronous ``_run`` in a thread-pool executor so the async
    event loop is not blocked during network I/O.
    """
    loop = asyncio.get_event_loop()
    result: str = await loop.run_in_executor(
        None, lambda: _acp_tool_run(self, message, *args, **kwargs)
    )
    return result


def _acp_tool_repr(self: Any) -> str:
    return (
        f"<ACPTool relay_url={self.__dict__['_relay_url']!r} "
        f"peer_id={self.__dict__['_peer_id']!r}>"
    )


class ACPTool:
    """
    LangChain Tool that sends a message to an ACP peer and returns the reply.

    This class inherits from ``langchain.tools.BaseTool`` at *instantiation*
    time via a lazy import, so LangChain does not need to be installed for the
    rest of ``acp_client`` to work.

    Parameters
    ----------
    relay_url:
        HTTP URL of the local ACP Relay endpoint (e.g. ``http://localhost:8765``).
    peer_id:
        Session-id of the remote peer this tool should address.  When the
        relay only has one connected peer you may pass an empty string and
        the relay will use its primary peer.
    timeout:
        Maximum seconds to wait for a reply before returning an error string.
    **kwargs:
        Additional keyword arguments forwarded to ``BaseTool.__init__``.

    Examples
    --------
    >>> tool = ACPTool(relay_url="http://localhost:8765", peer_id="agent_b")
    >>> tool.name
    'acp_send'
    >>> tool.run("Hello, agent_b!")
    '...'  # reply from the remote ACP peer
    """

    def __new__(
        cls,
        relay_url: str = "http://localhost:8765",
        peer_id: str = "",
        timeout: float = 30.0,
        **kwargs: Any,
    ) -> "ACPTool":
        """
        Build a *real* ``BaseTool`` subclass at instantiation time.

        We use ``__new__`` to dynamically subclass ``BaseTool`` only when the
        tool is actually created, keeping LangChain as a soft dependency.
        """
        BaseTool = _import_base_tool()

        def _init(self_inner: Any, **kw: Any) -> None:
            # Store ACP-specific state directly in __dict__ before BaseTool init
            self_inner.__dict__["_relay_url"] = kw.pop("relay_url", "http://localhost:8765")
            self_inner.__dict__["_peer_id"] = kw.pop("peer_id", "")
            self_inner.__dict__["_timeout"] = kw.pop("timeout", 30.0)
            BaseTool.__init__(self_inner, **kw)

        # Build a new class that properly inherits from BaseTool
        DynamicACPTool = type(
            "ACPTool",
            (BaseTool,),
            {
                "name": _ACP_TOOL_NAME,
                "description": _ACP_TOOL_DESCRIPTION,
                "__init__": _init,
                "_run": _acp_tool_run,
                "_arun": _acp_tool_arun,
                "__repr__": _acp_tool_repr,
            },
        )
        # Create instance and call our custom __init__
        instance = BaseTool.__new__(DynamicACPTool)
        _init(instance, relay_url=relay_url, peer_id=peer_id, timeout=timeout, **kwargs)
        return instance  # type: ignore[return-value]


# ── ACPCallbackHandler ─────────────────────────────────────────────────────────


def _handler_on_tool_start(
    self: Any,
    serialized: Dict[str, Any],
    input_str: str,
    **kwargs: Any,
) -> None:
    """Called when a LangChain tool starts executing."""
    tool_name = serialized.get("name", "unknown")
    log_level: int = self.__dict__["_log_level"]
    calls: List[Dict[str, Any]] = self.__dict__["_calls"]
    entry: Dict[str, Any] = {
        "event": "tool_start",
        "tool": tool_name,
        "input_len": len(input_str),
    }
    calls.append(entry)
    logger.log(
        log_level,
        "ACP tool_start: tool=%s input_len=%d",
        tool_name,
        len(input_str),
    )


def _handler_on_tool_end(self: Any, output: str, **kwargs: Any) -> None:
    """Called when a LangChain tool finishes executing."""
    log_level: int = self.__dict__["_log_level"]
    calls: List[Dict[str, Any]] = self.__dict__["_calls"]
    entry: Dict[str, Any] = {
        "event": "tool_end",
        "output_len": len(str(output)),
    }
    calls.append(entry)
    logger.log(
        log_level,
        "ACP tool_end: output_len=%d",
        len(str(output)),
    )


def _handler_on_tool_error(self: Any, error: Exception, **kwargs: Any) -> None:
    """Called when a LangChain tool raises an error."""
    calls: List[Dict[str, Any]] = self.__dict__["_calls"]
    entry: Dict[str, Any] = {
        "event": "tool_error",
        "error": str(error),
    }
    calls.append(entry)
    logger.error("ACP tool_error: %s", error)


def _handler_repr(self: Any) -> str:
    return "<ACPCallbackHandler>"


class ACPCallbackHandler:
    """
    LangChain CallbackHandler that logs ACP tool invocations.

    Records structured log entries via the standard ``logging`` module whenever
    an ACP tool starts or finishes, making it easy to audit inter-agent
    communication in production systems.

    Parameters
    ----------
    log_level:
        Python logging level for the log entries (default: ``logging.INFO``).

    Examples
    --------
    >>> handler = ACPCallbackHandler()
    >>> agent = initialize_agent([tool], llm, callbacks=[handler])
    """

    def __new__(
        cls,
        log_level: int = logging.INFO,
        **kwargs: Any,
    ) -> "ACPCallbackHandler":
        """Dynamically subclass BaseCallbackHandler at instantiation time."""
        BaseCallbackHandler = _import_base_callback_handler()

        def _init(self_inner: Any, **kw: Any) -> None:
            ll = kw.pop("log_level", logging.INFO)
            self_inner.__dict__["_log_level"] = ll
            self_inner.__dict__["_calls"] = []
            BaseCallbackHandler.__init__(self_inner, **kw)

        DynamicHandler = type(
            "ACPCallbackHandler",
            (BaseCallbackHandler,),
            {
                "__init__": _init,
                "on_tool_start": _handler_on_tool_start,
                "on_tool_end": _handler_on_tool_end,
                "on_tool_error": _handler_on_tool_error,
                "__repr__": _handler_repr,
            },
        )
        instance = BaseCallbackHandler.__new__(DynamicHandler)
        _init(instance, log_level=log_level, **kwargs)
        return instance  # type: ignore[return-value]


# ── Factory helper ─────────────────────────────────────────────────────────────


def create_acp_tool(
    relay_url: str,
    peer_id: str,
    timeout: float = 30.0,
    **kwargs: Any,
) -> ACPTool:
    """
    Factory function to create an :class:`ACPTool` instance.

    Convenience wrapper around ``ACPTool(...)`` that provides a clean,
    positional-argument API and documents the full parameter set in one place.

    Parameters
    ----------
    relay_url:
        HTTP URL of the local ACP Relay (e.g. ``"http://localhost:8765"``).
    peer_id:
        Session-id of the remote ACP peer to address.
    timeout:
        Seconds to wait for a reply (default 30).
    **kwargs:
        Additional keyword arguments forwarded to ``ACPTool.__init__``.

    Returns
    -------
    ACPTool
        A ready-to-use LangChain tool instance.

    Examples
    --------
    >>> tool = create_acp_tool("http://localhost:8765", "agent_b", timeout=60)
    >>> tool.name
    'acp_send'
    """
    return ACPTool(relay_url=relay_url, peer_id=peer_id, timeout=timeout, **kwargs)
