"""
test_sdk_package.py — acp-client v1.7.0 package test suite.

Coverage:
  - Package import & public API surface
  - Models: AgentCard, Message, Task, Part, TaskStatus
  - Exceptions hierarchy
  - RelayClient against a local mock HTTP server
  - AsyncRelayClient (basic)
  - CLI entry-point existence

Requires: pytest, pytest-asyncio
Does NOT require a live relay (mock server is launched per-test-session).
"""
from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

# ─────────────────────────────────────────────────────────────
# 1. Package import tests
# ─────────────────────────────────────────────────────────────

def test_import_top_level():
    """Package top-level imports must work."""
    import acp_client
    assert hasattr(acp_client, "RelayClient")
    assert hasattr(acp_client, "AsyncRelayClient")


def test_import_relay_client():
    from acp_client import RelayClient
    assert RelayClient is not None


def test_import_async_relay_client():
    from acp_client import AsyncRelayClient
    assert AsyncRelayClient is not None


def test_import_models():
    from acp_client.models import AgentCard, Message, Task, TaskStatus
    assert AgentCard and Message and Task and TaskStatus


def test_import_exceptions():
    from acp_client.exceptions import ACPError, PeerNotFoundError, TaskNotFoundError
    assert ACPError and PeerNotFoundError and TaskNotFoundError


def test_version():
    import acp_client
    assert acp_client.__version__ == "1.7.0"


def test_all_exports():
    import acp_client
    for name in [
        "RelayClient", "AsyncRelayClient",
        "AgentCard", "Message", "Task", "TaskStatus", "Part", "PartType",
        "ACPError", "PeerNotFoundError", "TaskNotFoundError",
        "TaskNotCancelableError", "SendError", "AuthError",
    ]:
        assert hasattr(acp_client, name), f"Missing export: {name}"


# ─────────────────────────────────────────────────────────────
# 2. Model tests
# ─────────────────────────────────────────────────────────────

def test_agent_card_from_dict_basic():
    from acp_client.models import AgentCard
    raw = {"name": "test-agent", "version": "1.0.0", "capabilities": {"streaming": True}}
    card = AgentCard.from_dict(raw)
    assert card.name == "test-agent"
    assert card.version == "1.0.0"
    assert card.supports("streaming") is True
    assert card.supports("nonexistent") is False


def test_agent_card_limitations():
    from acp_client.models import AgentCard
    raw = {"name": "limited", "limitations": ["no_file_access", "no_internet"]}
    card = AgentCard.from_dict(raw)
    assert card.has_limitation("no_file_access") is True
    assert card.has_limitation("full_access") is False


def test_agent_card_transport_modes():
    from acp_client.models import AgentCard
    raw = {"name": "relay-only", "transport_modes": ["relay"]}
    card = AgentCard.from_dict(raw)
    assert card.can_use_relay() is True
    assert card.can_use_p2p() is False


def test_agent_card_supported_interfaces():
    from acp_client.models import AgentCard
    raw = {"name": "full", "supported_interfaces": ["core", "task", "stream"]}
    card = AgentCard.from_dict(raw)
    assert card.has_interface("task") is True
    assert card.has_interface("mdns") is False


def test_agent_card_repr():
    from acp_client.models import AgentCard
    card = AgentCard(name="myagent", version="2.0.0", acp_version="2.7")
    r = repr(card)
    assert "myagent" in r
    assert "2.0.0" in r


def test_agent_card_to_dict_roundtrip():
    from acp_client.models import AgentCard
    original = AgentCard(
        name="roundtrip",
        version="1.2.3",
        capabilities={"streaming": True},
        limitations=["no_web"],
    )
    d = original.to_dict()
    restored = AgentCard.from_dict(d)
    assert restored.name == original.name
    assert restored.limitations == original.limitations


def test_task_status_terminal():
    from acp_client.models import TaskStatus
    assert TaskStatus.COMPLETED.is_terminal() is True
    assert TaskStatus.FAILED.is_terminal() is True
    assert TaskStatus.CANCELED.is_terminal() is True
    assert TaskStatus.WORKING.is_terminal() is False
    assert TaskStatus.SUBMITTED.is_terminal() is False


def test_task_from_dict():
    from acp_client.models import Task, TaskStatus
    raw = {
        "task_id": "task_abc",
        "status": "completed",
        "output": {"result": "done"},
    }
    task = Task.from_dict(raw)
    assert task.task_id == "task_abc"
    assert task.status == TaskStatus.COMPLETED
    assert task.is_terminal() is True


def test_task_from_dict_state_alias():
    """Relay may use 'state' instead of 'status'."""
    from acp_client.models import Task, TaskStatus
    raw = {"task_id": "t1", "state": "working"}
    task = Task.from_dict(raw)
    assert task.status == TaskStatus.WORKING


def test_message_from_dict():
    from acp_client.models import Message
    raw = {
        "message_id": "msg_001",
        "role": "user",
        "text": "Hello world",
        "from": "agent-b",
    }
    msg = Message.from_dict(raw)
    assert msg.message_id == "msg_001"
    assert msg.role == "user"
    assert msg.get_text() == "Hello world"
    assert msg.from_peer == "agent-b"


def test_message_get_text_from_parts():
    from acp_client.models import Message, Part
    msg = Message(parts=[Part.text_part("hello"), Part.text_part(" world")])
    assert msg.get_text() == "hello\n world"


def test_part_roundtrip():
    from acp_client.models import Part
    p = Part.text_part("hello ACP")
    d = p.to_dict()
    p2 = Part.from_dict(d)
    assert p2.type == "text"
    assert p2.text == "hello ACP"


# ─────────────────────────────────────────────────────────────
# 3. Exception tests
# ─────────────────────────────────────────────────────────────

def test_exception_hierarchy():
    from acp_client.exceptions import (
        ACPError, PeerNotFoundError, TaskNotFoundError,
        TaskNotCancelableError, SendError, AuthError,
    )
    assert issubclass(PeerNotFoundError, ACPError)
    assert issubclass(TaskNotFoundError, ACPError)
    assert issubclass(TaskNotCancelableError, ACPError)
    assert issubclass(SendError, ACPError)
    assert issubclass(AuthError, ACPError)


def test_peer_not_found_error():
    from acp_client.exceptions import PeerNotFoundError
    e = PeerNotFoundError("sess_xyz")
    assert e.code == "ERR_PEER_NOT_FOUND"
    assert "sess_xyz" in str(e)


def test_task_not_found_error():
    from acp_client.exceptions import TaskNotFoundError
    e = TaskNotFoundError("task_999")
    assert e.code == "ERR_TASK_NOT_FOUND"
    assert "task_999" in str(e)


def test_raise_from_response_ok():
    """_raise_from_response should be a no-op on success."""
    from acp_client.exceptions import _raise_from_response
    _raise_from_response({"ok": True})  # must not raise


def test_raise_from_response_peer_not_found():
    from acp_client.exceptions import _raise_from_response, PeerNotFoundError
    with pytest.raises(PeerNotFoundError):
        _raise_from_response({"error_code": "ERR_PEER_NOT_FOUND"}, peer_id="x")


def test_raise_from_response_task_not_cancelable():
    from acp_client.exceptions import _raise_from_response, TaskNotCancelableError
    with pytest.raises(TaskNotCancelableError):
        _raise_from_response({"error_code": "ERR_TASK_NOT_CANCELABLE"}, task_id="t1")


# ─────────────────────────────────────────────────────────────
# 4. Mock HTTP server fixture
# ─────────────────────────────────────────────────────────────

MOCK_GET: dict[str, Any] = {
    "/status": {
        "acp_version": "2.7.0",
        "connected": True,
        "peer_count": 1,
    },
    "/peers": {
        "peers": [
            {
                "peer_id": "sess_mock001",
                "name": "MockPeer",
                "connected_at": 1711600000.0,
                "messages_sent": 2,
                "messages_received": 3,
            }
        ],
        "count": 1,
    },
    "/peer/sess_mock001": {
        "peer_id": "sess_mock001",
        "name": "MockPeer",
    },
    "/.well-known/acp.json": {
        "name": "test-relay",
        "version": "2.7.0",
        "acp_version": "2.7",
        "capabilities": {
            "streaming": True,
            "multi_session": True,
            "sse_seq": True,
        },
        "supported_interfaces": ["core", "task", "stream"],
        "transport_modes": ["p2p", "relay"],
        "limitations": [],
    },
    "/link": {"link": "acp://127.0.0.1:7901/tok_mock"},
    "/recv": {
        "messages": [
            {
                "message_id": "msg_r001",
                "role": "assistant",
                "text": "Hi from mock relay!",
                "from": "MockPeer",
            }
        ]
    },
    "/tasks": {"tasks": [
        {"task_id": "task_001", "status": "completed", "description": "test task"}
    ]},
    "/tasks/task_001": {
        "task_id": "task_001", "status": "completed",
        "output": {"result": "42"},
    },
    "/tasks/task_999": {"error_code": "ERR_TASK_NOT_FOUND", "ok": False},
}

MOCK_POST: dict[str, Any] = {
    "/message:send": {"ok": True, "message_id": "msg_sent_001"},
    "/peer/sess_mock001/send": {"ok": True, "message_id": "msg_peer_001"},
    "/peer/sess_bad/send": {"error_code": "ERR_PEER_NOT_FOUND", "ok": False},
    "/tasks/create": {"ok": True, "task_id": "task_new", "state": "submitted"},
    "/tasks/task_001:update": {"ok": True},
    "/tasks/task_001:cancel": {"ok": True, "state": "canceled"},
    "/tasks/task_term:cancel": {"error": "ERR_TASK_NOT_CANCELABLE", "ok": False},
    "/skills/query": {"ok": True, "skills": [{"id": "echo", "name": "Echo"}]},
}


class MockHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # silence

    def do_GET(self):
        path = self.path.split("?")[0]
        resp = MOCK_GET.get(path, {"error": "not_found"})
        status = 200 if "error" not in resp or resp.get("ok") is False else 404
        if resp.get("ok") is False:
            status = 200  # relay returns 200 with error body
        self._respond(status, resp)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        resp = MOCK_POST.get(self.path, {"error": "not_found"})
        self._respond(200, resp)

    def _respond(self, status: int, body: dict):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture(scope="module")
def mock_relay():
    """Start a mock HTTP relay server for the test session."""
    server = HTTPServer(("127.0.0.1", 0), MockHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    url = f"http://127.0.0.1:{port}"
    yield url
    server.shutdown()


# ─────────────────────────────────────────────────────────────
# 5. RelayClient integration tests (mock server)
# ─────────────────────────────────────────────────────────────

def test_client_status(mock_relay):
    from acp_client import RelayClient
    c = RelayClient(mock_relay)
    st = c.status()
    assert st["acp_version"] == "2.7.0"
    assert st["connected"] is True


def test_client_card(mock_relay):
    from acp_client import RelayClient, AgentCard
    c = RelayClient(mock_relay)
    card = c.card()
    assert isinstance(card, AgentCard)
    assert card.name == "test-relay"
    assert card.supports("streaming") is True


def test_client_link(mock_relay):
    from acp_client import RelayClient
    c = RelayClient(mock_relay)
    link = c.link()
    assert link.startswith("acp://")


def test_client_peers(mock_relay):
    from acp_client import RelayClient
    c = RelayClient(mock_relay)
    peers = c.peers()
    assert len(peers) == 1
    assert peers[0]["peer_id"] == "sess_mock001"


def test_client_is_connected(mock_relay):
    from acp_client import RelayClient
    c = RelayClient(mock_relay)
    assert c.is_connected() is True


def test_client_send(mock_relay):
    from acp_client import RelayClient
    c = RelayClient(mock_relay)
    resp = c.send("Hello relay!")
    assert resp["ok"] is True
    assert "message_id" in resp


def test_client_send_with_parts(mock_relay):
    from acp_client import RelayClient
    c = RelayClient(mock_relay)
    resp = c.send(parts=[{"type": "text", "text": "structured"}])
    assert resp["ok"] is True


def test_client_send_to_peer(mock_relay):
    from acp_client import RelayClient
    c = RelayClient(mock_relay)
    resp = c.send_to_peer("sess_mock001", "targeted message")
    assert resp["ok"] is True


def test_client_send_to_peer_not_found(mock_relay):
    from acp_client import RelayClient
    from acp_client.exceptions import PeerNotFoundError
    c = RelayClient(mock_relay)
    with pytest.raises(PeerNotFoundError):
        c.send_to_peer("sess_bad", "hi")


def test_client_recv(mock_relay):
    from acp_client import RelayClient
    c = RelayClient(mock_relay)
    msgs = c.recv()
    assert len(msgs) >= 1
    assert msgs[0]["message_id"] == "msg_r001"


def test_client_recv_messages(mock_relay):
    from acp_client import RelayClient
    from acp_client.models import Message
    c = RelayClient(mock_relay)
    msgs = c.recv_messages()
    assert all(isinstance(m, Message) for m in msgs)
    assert msgs[0].get_text() == "Hi from mock relay!"


def test_client_tasks(mock_relay):
    from acp_client import RelayClient
    c = RelayClient(mock_relay)
    tasks = c.tasks()
    assert len(tasks) == 1
    assert tasks[0]["task_id"] == "task_001"


def test_client_get_task(mock_relay):
    from acp_client import RelayClient
    from acp_client.models import Task, TaskStatus
    c = RelayClient(mock_relay)
    task = c.get_task("task_001")
    assert isinstance(task, Task)
    assert task.status == TaskStatus.COMPLETED
    assert task.is_terminal() is True


def test_client_create_task(mock_relay):
    from acp_client import RelayClient
    c = RelayClient(mock_relay)
    resp = c.create_task({"description": "new task"})
    assert resp["ok"] is True
    assert resp["task_id"] == "task_new"


def test_client_cancel_task(mock_relay):
    from acp_client import RelayClient
    c = RelayClient(mock_relay)
    resp = c.cancel_task("task_001")
    assert resp.get("ok") or resp.get("state") == "canceled"


def test_client_cancel_task_terminal_raises(mock_relay):
    from acp_client import RelayClient
    from acp_client.exceptions import TaskNotCancelableError
    c = RelayClient(mock_relay)
    with pytest.raises(TaskNotCancelableError):
        c.cancel_task("task_term", raise_on_terminal=True)


def test_client_query_skills(mock_relay):
    from acp_client import RelayClient
    c = RelayClient(mock_relay)
    resp = c.query_skills(capability="echo")
    assert resp["ok"] is True
    assert len(resp["skills"]) >= 1


def test_client_send_requires_text_or_parts():
    from acp_client import RelayClient
    c = RelayClient("http://localhost:9999")
    with pytest.raises(ValueError):
        c.send()  # neither text nor parts


def test_client_capabilities(mock_relay):
    from acp_client import RelayClient
    c = RelayClient(mock_relay)
    caps = c.capabilities()
    assert caps["streaming"] is True
    assert caps["sse_seq"] is True


def test_client_supported_interfaces(mock_relay):
    from acp_client import RelayClient
    c = RelayClient(mock_relay)
    ifaces = c.supported_interfaces()
    assert "core" in ifaces
    assert "task" in ifaces


def test_client_repr():
    from acp_client import RelayClient
    c = RelayClient("http://localhost:7901")
    r = repr(c)
    assert "RelayClient" in r
    assert "7901" in r


# ─────────────────────────────────────────────────────────────
# 6. AsyncRelayClient tests
# ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_async_client_status(mock_relay):
    from acp_client import AsyncRelayClient
    async with AsyncRelayClient(mock_relay) as c:
        st = await c.status()
        assert st["acp_version"] == "2.7.0"


@pytest.mark.asyncio
async def test_async_client_card(mock_relay):
    from acp_client import AsyncRelayClient, AgentCard
    async with AsyncRelayClient(mock_relay) as c:
        card = await c.card()
        assert isinstance(card, AgentCard)
        assert card.supports("streaming") is True


@pytest.mark.asyncio
async def test_async_client_send(mock_relay):
    from acp_client import AsyncRelayClient
    async with AsyncRelayClient(mock_relay) as c:
        resp = await c.send("Hello from async!")
        assert resp["ok"] is True


@pytest.mark.asyncio
async def test_async_client_recv(mock_relay):
    from acp_client import AsyncRelayClient
    async with AsyncRelayClient(mock_relay) as c:
        msgs = await c.recv()
        assert len(msgs) >= 1


@pytest.mark.asyncio
async def test_async_client_peers(mock_relay):
    from acp_client import AsyncRelayClient
    async with AsyncRelayClient(mock_relay) as c:
        peers = await c.peers()
        assert len(peers) == 1


@pytest.mark.asyncio
async def test_async_client_tasks(mock_relay):
    from acp_client import AsyncRelayClient
    async with AsyncRelayClient(mock_relay) as c:
        tasks = await c.tasks()
        assert len(tasks) == 1


@pytest.mark.asyncio
async def test_async_client_cancel_task_terminal_raises(mock_relay):
    from acp_client import AsyncRelayClient
    from acp_client.exceptions import TaskNotCancelableError
    async with AsyncRelayClient(mock_relay) as c:
        with pytest.raises(TaskNotCancelableError):
            await c.cancel_task("task_term", raise_on_terminal=True)


@pytest.mark.asyncio
async def test_async_client_context_manager():
    from acp_client import AsyncRelayClient
    async with AsyncRelayClient("http://localhost:9999") as c:
        assert isinstance(c, AsyncRelayClient)


# ─────────────────────────────────────────────────────────────
# 7. CLI entry-point test
# ─────────────────────────────────────────────────────────────

def test_cli_importable():
    from acp_client._cli import main
    assert callable(main)


def test_cli_help(capsys):
    from acp_client._cli import main
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "acp-client" in captured.out


def test_cli_status(mock_relay):
    from acp_client._cli import main
    main(["--url", mock_relay, "status"])  # should not raise


def test_cli_peers(mock_relay, capsys):
    from acp_client._cli import main
    main(["--url", mock_relay, "peers"])
    captured = capsys.readouterr()
    assert "sess_mock001" in captured.out or "MockPeer" in captured.out


def test_cli_send(mock_relay, capsys):
    from acp_client._cli import main
    main(["--url", mock_relay, "send", "hello from CLI"])
    captured = capsys.readouterr()
    assert "msg_sent_001" in captured.out


def test_cli_recv(mock_relay, capsys):
    from acp_client._cli import main
    main(["--url", mock_relay, "recv", "--limit", "5"])
    captured = capsys.readouterr()
    assert "msg_r001" in captured.out or "Hi from mock relay" in captured.out
