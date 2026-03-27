"""
Tests for RelayClient.

These tests do NOT require a running relay — they test the client logic
(serialization, URL construction, error handling) with a mock HTTP server.
"""
import json
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
import pytest
from acp_sdk import RelayClient


# ─────────────────────────────────────────────
# Minimal mock relay server
# ─────────────────────────────────────────────

MOCK_RESPONSES = {
    "/status": {
        "acp_version": "0.6-dev", "connected": True,
        "agent_card": {"capabilities": {"multi_session": True}},
    },
    "/peers": {
        "peers": [
            {"peer_id": "sess_abc123", "name": "Agent-B", "connected_at": 1710000000.0,
             "messages_sent": 3, "messages_received": 5}
        ],
        "count": 1,
    },
    "/peer/sess_abc123": {
        "peer_id": "sess_abc123", "name": "Agent-B",
        "connected_at": 1710000000.0, "messages_sent": 3,
    },
    "/recv": {"messages": [
        {"type": "acp.message", "message_id": "msg_001", "from": "Agent-B",
         "parts": [{"type": "text", "text": "Hello!"}]},
    ]},
    "/tasks": {"tasks": []},
    "/.well-known/acp.json": {"self": {"name": "Agent-A", "capabilities": {}}},
    "/link": {"link": "acp://127.0.0.1:7801/tok_test123"},
}

POST_RESPONSES = {
    "/message:send":      {"ok": True, "message_id": "msg_sent_001"},
    "/peer/sess_abc123/send": {"ok": True, "message_id": "msg_peer_001", "peer_id": "sess_abc123"},
    "/tasks/create":      {"ok": True, "task_id": "task_001", "state": "submitted"},
    "/tasks/task_001:update": {"ok": True},
    "/tasks/task_001:cancel": {"ok": True},
    "/skills/query":      {"ok": True, "skills": [{"id": "summarize"}]},
    "/reply":             {"ok": True},
}


class MockRelayHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # silence server logs

    def do_GET(self):
        path = self.path.split("?")[0]
        resp = MOCK_RESPONSES.get(path, {"error": "not found"})
        status = 200 if "error" not in resp else 404
        body = json.dumps(resp).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)  # consume body
        resp = POST_RESPONSES.get(self.path, {"error": "not found"})
        status = 200 if "error" not in resp else 404
        body = json.dumps(resp).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(scope="module")
def mock_server():
    server = HTTPServer(("127.0.0.1", 0), MockRelayHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.fixture
def client(mock_server):
    return RelayClient(mock_server, timeout=5.0)


# ─────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────

def test_status(client):
    st = client.status()
    assert st["acp_version"] == "0.6-dev"
    assert st["connected"] is True


def test_is_connected(client):
    assert client.is_connected() is True


def test_peers(client):
    peers = client.peers()
    assert len(peers) == 1
    assert peers[0]["peer_id"] == "sess_abc123"
    assert peers[0]["name"] == "Agent-B"


def test_peer_single(client):
    p = client.peer("sess_abc123")
    assert p["peer_id"] == "sess_abc123"


def test_link(client):
    link = client.link()
    assert link.startswith("acp://")


def test_card(client):
    card = client.card()
    assert "self" in card


def test_send_text(client):
    result = client.send("Hello world!")
    assert result["ok"] is True
    assert "message_id" in result


def test_send_parts(client):
    result = client.send(parts=[{"type": "text", "text": "Hello via parts"}])
    assert result["ok"] is True


def test_send_requires_text_or_parts(client):
    with pytest.raises(ValueError):
        client.send()


def test_send_to_peer(client):
    result = client.send_to_peer("sess_abc123", "Hi targeted!")
    assert result["ok"] is True
    assert result["peer_id"] == "sess_abc123"


def test_recv(client):
    msgs = client.recv()
    assert len(msgs) == 1
    assert msgs[0]["message_id"] == "msg_001"


def test_tasks(client):
    tasks = client.tasks()
    assert isinstance(tasks, list)


def test_create_task(client):
    result = client.create_task({"description": "Summarize docs"})
    assert result["ok"] is True
    assert result["state"] == "submitted"


def test_update_task(client):
    result = client.update_task("task_001", "completed", output={"summary": "done"})
    assert result["ok"] is True


def test_cancel_task(client):
    result = client.cancel_task("task_001")
    assert result["ok"] is True


def test_query_skills(client):
    result = client.query_skills(capability="summarize")
    assert result["ok"] is True
    assert len(result["skills"]) == 1


def test_reply(client):
    result = client.reply("msg_001", "Got it!")
    assert result["ok"] is True


def test_repr(client):
    r = repr(client)
    assert "RelayClient" in r
    assert "connected=True" in r


def test_import():
    """SDK imports cleanly."""
    from acp_sdk import RelayClient, AsyncRelayClient, ACPMessage, ACPAgent
    assert RelayClient.__version__ if hasattr(RelayClient, "__version__") else True
    from acp_sdk import __version__
    assert __version__ == "0.8.0"
