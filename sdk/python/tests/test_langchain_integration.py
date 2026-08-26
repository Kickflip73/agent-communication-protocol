"""
tests/test_langchain_integration.py — LangChain Integration Test Suite

Tests for acp_client.integrations.langchain:
  - ACPTool (name, description, _run, _arun, timeout, error handling)
  - ACPCallbackHandler (on_tool_start, on_tool_end, on_tool_error)
  - create_acp_tool factory function
  - Behaviour when langchain is not installed (ImportError path)

All tests use mock objects — no live relay or real LangChain installation
is required.
"""
from __future__ import annotations

import asyncio
import logging
import sys
import types
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures & helpers — build a minimal fake langchain module
# ─────────────────────────────────────────────────────────────────────────────

def _make_fake_langchain() -> None:
    """
    Inject a minimal stub of langchain into sys.modules so that lazy imports
    inside the integration module succeed without the real package installed.
    """
    class _BaseTool:
        name: str = ""
        description: str = ""

        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)

        def run(self, input_str: str, **kwargs: Any) -> str:
            return self._run(input_str)

        async def arun(self, input_str: str, **kwargs: Any) -> str:
            return await self._arun(input_str)

        def _run(self, message: str, *args: Any, **kwargs: Any) -> str:
            raise NotImplementedError

        async def _arun(self, message: str, *args: Any, **kwargs: Any) -> str:
            raise NotImplementedError

    class _BaseCallbackHandler:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def on_tool_start(self, serialized: Dict, input_str: str, **kwargs: Any) -> None:
            pass

        def on_tool_end(self, output: str, **kwargs: Any) -> None:
            pass

        def on_tool_error(self, error: Exception, **kwargs: Any) -> None:
            pass

    # Build fake module tree
    lc_pkg = types.ModuleType("langchain")
    lc_tools = types.ModuleType("langchain.tools")
    lc_tools.BaseTool = _BaseTool  # type: ignore[attr-defined]

    lc_cb_pkg = types.ModuleType("langchain.callbacks")
    lc_cb_base = types.ModuleType("langchain.callbacks.base")
    lc_cb_base.BaseCallbackHandler = _BaseCallbackHandler  # type: ignore[attr-defined]

    sys.modules.setdefault("langchain", lc_pkg)
    sys.modules["langchain.tools"] = lc_tools
    sys.modules.setdefault("langchain.callbacks", lc_cb_pkg)
    sys.modules["langchain.callbacks.base"] = lc_cb_base


# Inject stubs before importing the integration module
_make_fake_langchain()

from acp_client.integrations.langchain import (  # noqa: E402
    ACPCallbackHandler,
    ACPTool,
    create_acp_tool,
    _acp_tool_run,
    _acp_tool_arun,
    _handler_on_tool_start,
    _handler_on_tool_end,
    _handler_on_tool_error,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helper: build a mock RelayClient
# ─────────────────────────────────────────────────────────────────────────────

def _mock_relay_client(reply_text: str = "pong") -> MagicMock:
    mock = MagicMock()
    mock.send_and_recv.return_value = {"text": reply_text, "role": "assistant"}
    mock.recv.return_value = []
    mock.send_to_peer.return_value = {"ok": True, "message_id": "msg_test"}
    return mock


# ─────────────────────────────────────────────────────────────────────────────
# TC-01  ACPTool init — name and description
# ─────────────────────────────────────────────────────────────────────────────

class TestACPToolInit:
    """TC-01: Verify ACPTool has correct name and description after init."""

    def test_acp_tool_name(self) -> None:
        tool = ACPTool(relay_url="http://localhost:8765", peer_id="agent_b")
        assert tool.name == "acp_send"

    def test_acp_tool_description_not_empty(self) -> None:
        tool = ACPTool(relay_url="http://localhost:8765", peer_id="agent_b")
        assert isinstance(tool.description, str)
        assert len(tool.description) > 20

    def test_acp_tool_description_mentions_acp(self) -> None:
        tool = ACPTool(relay_url="http://localhost:8765", peer_id="agent_b")
        assert "ACP" in tool.description or "agent" in tool.description.lower()

    def test_acp_tool_stores_relay_url(self) -> None:
        tool = ACPTool(relay_url="http://my-relay:9000", peer_id="x")
        assert tool.__dict__["_relay_url"] == "http://my-relay:9000"

    def test_acp_tool_stores_peer_id(self) -> None:
        tool = ACPTool(relay_url="http://localhost:8765", peer_id="peer_xyz")
        assert tool.__dict__["_peer_id"] == "peer_xyz"

    def test_acp_tool_default_timeout(self) -> None:
        tool = ACPTool(relay_url="http://localhost:8765", peer_id="")
        assert tool.__dict__["_timeout"] == 30.0

    def test_acp_tool_custom_timeout(self) -> None:
        tool = ACPTool(relay_url="http://localhost:8765", peer_id="", timeout=60.0)
        assert tool.__dict__["_timeout"] == 60.0


# ─────────────────────────────────────────────────────────────────────────────
# TC-02  ACPTool._run — success path
# ─────────────────────────────────────────────────────────────────────────────

class TestACPToolRunSuccess:
    """TC-02: _run sends message via RelayClient and returns reply text."""

    def test_run_returns_reply_text(self) -> None:
        tool = ACPTool(relay_url="http://localhost:8765", peer_id="")
        mock_client = _mock_relay_client(reply_text="Hello back!")

        with patch("acp_client.integrations.langchain.RelayClient", return_value=mock_client):
            result = _acp_tool_run(tool, "Hello!")

        assert result == "Hello back!"

    def test_run_calls_send_and_recv(self) -> None:
        tool = ACPTool(relay_url="http://localhost:8765", peer_id="")
        mock_client = _mock_relay_client()

        with patch("acp_client.integrations.langchain.RelayClient", return_value=mock_client):
            _acp_tool_run(tool, "ping")

        mock_client.send_and_recv.assert_called_once_with("ping", timeout=30.0)

    def test_run_with_specific_peer_id(self) -> None:
        """When peer_id is set, uses send_to_peer + polls recv."""
        tool = ACPTool(relay_url="http://localhost:8765", peer_id="agent_b")
        mock_client = MagicMock()
        mock_client.send_to_peer.return_value = {"ok": True}
        # First call returns empty list (before_count=0), second returns a message
        mock_client.recv.side_effect = [
            [],
            [{"text": "reply from b", "role": "assistant"}],
        ]

        with patch("acp_client.integrations.langchain.RelayClient", return_value=mock_client):
            result = _acp_tool_run(tool, "hi agent_b")

        assert result == "reply from b"
        mock_client.send_to_peer.assert_called_once_with("agent_b", text="hi agent_b")

    def test_run_via_instance_method(self) -> None:
        """Verify the dynamically bound _run method on the instance works."""
        tool = ACPTool(relay_url="http://localhost:8765", peer_id="")
        mock_client = _mock_relay_client(reply_text="via instance")

        with patch("acp_client.integrations.langchain.RelayClient", return_value=mock_client):
            # Call via the instance (bound method on dynamic class)
            result = tool._run("Hello!")

        assert result == "via instance"


# ─────────────────────────────────────────────────────────────────────────────
# TC-03  ACPTool._run — timeout path
# ─────────────────────────────────────────────────────────────────────────────

class TestACPToolRunTimeout:
    """TC-03: _run returns error string when relay times out."""

    def test_run_returns_error_on_none_reply(self) -> None:
        tool = ACPTool(relay_url="http://localhost:8765", peer_id="")
        mock_client = MagicMock()
        mock_client.send_and_recv.return_value = None  # simulate timeout

        with patch("acp_client.integrations.langchain.RelayClient", return_value=mock_client):
            result = _acp_tool_run(tool, "slow message")

        assert "timeout" in result.lower() or "Error" in result

    def test_run_timeout_does_not_raise(self) -> None:
        """_run must return a string, never raise, so LLM can observe the error."""
        tool = ACPTool(relay_url="http://localhost:8765", peer_id="")
        mock_client = MagicMock()
        mock_client.send_and_recv.return_value = None

        with patch("acp_client.integrations.langchain.RelayClient", return_value=mock_client):
            result = _acp_tool_run(tool, "test")

        assert isinstance(result, str)


# ─────────────────────────────────────────────────────────────────────────────
# TC-04  ACPTool._run — ACPError handling
# ─────────────────────────────────────────────────────────────────────────────

class TestACPToolErrorHandling:
    """TC-04: _run catches ACPError and returns descriptive error string."""

    def test_run_catches_acp_error(self) -> None:
        from acp_client.exceptions import ACPError

        tool = ACPTool(relay_url="http://localhost:8765", peer_id="")
        mock_client = MagicMock()
        mock_client.send_and_recv.side_effect = ACPError("peer gone")

        with patch("acp_client.integrations.langchain.RelayClient", return_value=mock_client):
            result = _acp_tool_run(tool, "hello")

        assert "Error" in result or "error" in result
        assert isinstance(result, str)


# ─────────────────────────────────────────────────────────────────────────────
# TC-05  ACPTool._arun — async wrapper
# ─────────────────────────────────────────────────────────────────────────────

class TestACPToolArun:
    """TC-05: _arun delegates to _run and returns same result asynchronously."""

    def test_arun_returns_reply_text(self) -> None:
        tool = ACPTool(relay_url="http://localhost:8765", peer_id="")
        mock_client = _mock_relay_client(reply_text="async pong")

        with patch("acp_client.integrations.langchain.RelayClient", return_value=mock_client):
            result = asyncio.run(_acp_tool_arun(tool, "async ping"))

        assert result == "async pong"

    def test_arun_returns_string(self) -> None:
        tool = ACPTool(relay_url="http://localhost:8765", peer_id="")
        mock_client = MagicMock()
        mock_client.send_and_recv.return_value = None

        with patch("acp_client.integrations.langchain.RelayClient", return_value=mock_client):
            result = asyncio.run(_acp_tool_arun(tool, "test"))

        assert isinstance(result, str)


# ─────────────────────────────────────────────────────────────────────────────
# TC-06  Missing langchain — ImportError path
# ─────────────────────────────────────────────────────────────────────────────

class TestACPToolMissingLangchain:
    """TC-06: Proper ImportError is raised when langchain is not installed."""

    def test_import_error_has_install_hint(self) -> None:
        """
        Simulate missing langchain by patching _import_base_tool to raise ImportError.
        """
        import acp_client.integrations.langchain as lc_mod

        original_fn = lc_mod._import_base_tool

        def _raise():
            raise ImportError("No module named 'langchain'")

        lc_mod._import_base_tool = _raise
        try:
            with pytest.raises(ImportError) as exc_info:
                ACPTool.__new__(ACPTool)
            err_msg = str(exc_info.value).lower()
            assert "langchain" in err_msg or "pip" in err_msg
        finally:
            lc_mod._import_base_tool = original_fn

    def test_callback_handler_import_error(self) -> None:
        import acp_client.integrations.langchain as lc_mod

        original_fn = lc_mod._import_base_callback_handler

        def _raise():
            raise ImportError("No module named 'langchain'")

        lc_mod._import_base_callback_handler = _raise
        try:
            with pytest.raises(ImportError):
                ACPCallbackHandler.__new__(ACPCallbackHandler)
        finally:
            lc_mod._import_base_callback_handler = original_fn


# ─────────────────────────────────────────────────────────────────────────────
# TC-07  create_acp_tool factory
# ─────────────────────────────────────────────────────────────────────────────

class TestCreateACPToolFactory:
    """TC-07: Factory function returns a properly configured ACPTool."""

    def test_factory_returns_acp_tool(self) -> None:
        tool = create_acp_tool("http://localhost:8765", "agent_b")
        assert tool.name == "acp_send"

    def test_factory_sets_relay_url(self) -> None:
        tool = create_acp_tool("http://relay:9999", "peer1")
        assert tool.__dict__["_relay_url"] == "http://relay:9999"

    def test_factory_sets_peer_id(self) -> None:
        tool = create_acp_tool("http://localhost:8765", "peer_42")
        assert tool.__dict__["_peer_id"] == "peer_42"

    def test_factory_sets_custom_timeout(self) -> None:
        tool = create_acp_tool("http://localhost:8765", "peer", timeout=90)
        assert tool.__dict__["_timeout"] == 90

    def test_factory_default_timeout(self) -> None:
        tool = create_acp_tool("http://localhost:8765", "peer")
        assert tool.__dict__["_timeout"] == 30.0


# ─────────────────────────────────────────────────────────────────────────────
# TC-08  ACPCallbackHandler
# ─────────────────────────────────────────────────────────────────────────────

class TestACPCallbackHandler:
    """TC-08: CallbackHandler records tool_start, tool_end, tool_error events."""

    def _make_handler(self) -> Any:
        return ACPCallbackHandler(log_level=logging.DEBUG)

    def test_handler_instantiates(self) -> None:
        handler = self._make_handler()
        assert handler is not None

    def test_on_tool_start_records_event(self) -> None:
        handler = self._make_handler()
        _handler_on_tool_start(
            handler,
            {"name": "acp_send"},
            "hello world",
        )
        calls: List = handler.__dict__["_calls"]
        assert len(calls) == 1
        assert calls[0]["event"] == "tool_start"
        assert calls[0]["tool"] == "acp_send"

    def test_on_tool_start_records_input_length(self) -> None:
        handler = self._make_handler()
        msg = "x" * 42
        _handler_on_tool_start(handler, {"name": "acp_send"}, msg)
        calls: List = handler.__dict__["_calls"]
        assert calls[0]["input_len"] == 42

    def test_on_tool_end_records_event(self) -> None:
        handler = self._make_handler()
        _handler_on_tool_end(handler, "output text")
        calls: List = handler.__dict__["_calls"]
        assert calls[0]["event"] == "tool_end"
        assert calls[0]["output_len"] == len("output text")

    def test_on_tool_error_records_event(self) -> None:
        handler = self._make_handler()
        _handler_on_tool_error(handler, ValueError("boom"))
        calls: List = handler.__dict__["_calls"]
        assert calls[0]["event"] == "tool_error"
        assert "boom" in calls[0]["error"]

    def test_multiple_events_accumulate(self) -> None:
        handler = self._make_handler()
        _handler_on_tool_start(handler, {"name": "acp_send"}, "msg")
        _handler_on_tool_end(handler, "reply")
        calls: List = handler.__dict__["_calls"]
        assert len(calls) == 2
        assert calls[0]["event"] == "tool_start"
        assert calls[1]["event"] == "tool_end"

    def test_handler_via_instance_method(self) -> None:
        """Verify the dynamically bound on_tool_start method works directly."""
        handler = self._make_handler()
        handler.on_tool_start({"name": "acp_send"}, "hello")
        calls: List = handler.__dict__["_calls"]
        assert len(calls) == 1
        assert calls[0]["event"] == "tool_start"


# ─────────────────────────────────────────────────────────────────────────────
# TC-09  Repr
# ─────────────────────────────────────────────────────────────────────────────

class TestRepr:
    """TC-09: __repr__ returns a useful string."""

    def test_tool_repr_contains_relay_url(self) -> None:
        tool = ACPTool(relay_url="http://localhost:8765", peer_id="b")
        r = repr(tool)
        assert "localhost:8765" in r

    def test_handler_repr(self) -> None:
        handler = ACPCallbackHandler()
        r = repr(handler)
        assert "ACPCallbackHandler" in r or "Callback" in r or "Handler" in r


# ─────────────────────────────────────────────────────────────────────────────
# TC-10  Integration smoke-test via create_acp_tool + _run
# ─────────────────────────────────────────────────────────────────────────────

class TestIntegrationSmoke:
    """TC-10: End-to-end smoke test using factory + mocked relay."""

    def test_smoke_create_and_run(self) -> None:
        tool = create_acp_tool("http://localhost:8765", "", timeout=5)
        mock_client = _mock_relay_client(reply_text="smoke reply")

        with patch("acp_client.integrations.langchain.RelayClient", return_value=mock_client):
            result = _acp_tool_run(tool, "smoke test message")

        assert result == "smoke reply"

    def test_smoke_empty_peer_id_uses_primary(self) -> None:
        """Empty peer_id → send_and_recv path (primary peer)."""
        tool = create_acp_tool("http://localhost:8765", "")
        mock_client = MagicMock()
        mock_client.send_and_recv.return_value = {"text": "ok from primary", "role": "assistant"}

        with patch("acp_client.integrations.langchain.RelayClient", return_value=mock_client):
            result = _acp_tool_run(tool, "test")

        assert result == "ok from primary"

    def test_smoke_arun_integration(self) -> None:
        tool = create_acp_tool("http://localhost:8765", "", timeout=5)
        mock_client = _mock_relay_client(reply_text="async smoke")

        with patch("acp_client.integrations.langchain.RelayClient", return_value=mock_client):
            result = asyncio.run(_acp_tool_arun(tool, "async smoke test"))

        assert result == "async smoke"


# ─────────────────────────────────────────────────────────────────────────────
# TC-11  Public API surface — create_acp_tool re-exported from top-level __init__
# ─────────────────────────────────────────────────────────────────────────────

class TestPublicAPI:
    """TC-11: create_acp_tool is accessible from acp_client top-level."""

    def test_create_acp_tool_importable_from_top_level(self) -> None:
        import acp_client
        assert hasattr(acp_client, "create_acp_tool")

    def test_create_acp_tool_callable(self) -> None:
        import acp_client
        tool = acp_client.create_acp_tool("http://localhost:8765", "peer")
        assert tool.name == "acp_send"


# ─────────────────────────────────────────────────────────────────────────────
# TC-12  langchain optional extra in pyproject.toml
# ─────────────────────────────────────────────────────────────────────────────

class TestPyprojectToml:
    """TC-12: pyproject.toml declares the langchain optional dependency."""

    def test_langchain_optional_dep_declared(self) -> None:
        import pathlib
        import tomllib  # Python 3.11+

        toml_path = pathlib.Path(__file__).parent.parent / "pyproject.toml"
        with open(toml_path, "rb") as fh:
            config = tomllib.load(fh)

        extras = config["project"]["optional-dependencies"]
        assert "langchain" in extras, "Expected 'langchain' key in optional-dependencies"
        langchain_deps = extras["langchain"]
        assert any("langchain" in dep for dep in langchain_deps)
