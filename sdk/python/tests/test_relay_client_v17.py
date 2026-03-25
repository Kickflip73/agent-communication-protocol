"""
Test suite for RelayClient v1.7 features:
  - tasks() time-window filters (v1.4 created_after/updated_after)
  - cancel_task() v1.5.2 idempotent semantics + 409 handling
  - capabilities() (v1.6 http2 + did_identity flags)
  - identity() / did_document() (v1.3 did:acp:)
"""
from __future__ import annotations

import json
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch, MagicMock

import pytest

sys_import = __import__("sys")
sys_import.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__file__)))

from acp_sdk.relay_client import RelayClient  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Minimal mock HTTP server
# ─────────────────────────────────────────────────────────────────────────────

class _MockHandler(BaseHTTPRequestHandler):
    """Mock relay server recording requests and serving preset responses."""
    log_message = lambda *_: None  # suppress access log

    def do_GET(self):
        resp = self.server.get_response.get(self.path)
        if resp is None:
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps(resp).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(length)
        self.server.last_post_body = json.loads(body_bytes) if body_bytes else {}
        self.server.last_post_path = self.path

        # Handle 409 for specific task id
        if self.path.endswith(":cancel") and "terminal_task" in self.path:
            error_body = json.dumps({
                "error": "ERR_TASK_NOT_CANCELABLE",
                "message": "Task is in terminal state"
            }).encode()
            self.send_response(409)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(error_body)))
            self.end_headers()
            self.wfile.write(error_body)
            return

        resp = self.server.post_response.get(self.path, {"ok": True})
        body = json.dumps(resp).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(scope="module")
def mock_server():
    server = HTTPServer(("127.0.0.1", 0), _MockHandler)
    server.get_response = {}
    server.post_response = {}
    server.last_post_body = {}
    server.last_post_path = ""
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    port = server.server_address[1]
    client = RelayClient(f"http://127.0.0.1:{port}", timeout=5.0)
    yield server, client
    server.shutdown()


# ─────────────────────────────────────────────────────────────────────────────
# T1: tasks() — created_after filter
# ─────────────────────────────────────────────────────────────────────────────

def test_t1_tasks_created_after(mock_server):
    """tasks(created_after=...) appends correct query param."""
    server, client = mock_server
    server.get_response["/tasks?created_after=2026-03-25T00:00:00Z"] = {
        "tasks": [{"id": "t1", "state": "completed"}]
    }
    result = client.tasks(created_after="2026-03-25T00:00:00Z")
    assert len(result) == 1
    assert result[0]["id"] == "t1"


# ─────────────────────────────────────────────────────────────────────────────
# T2: tasks() — updated_after filter
# ─────────────────────────────────────────────────────────────────────────────

def test_t2_tasks_updated_after(mock_server):
    """tasks(updated_after=...) appends correct query param."""
    server, client = mock_server
    server.get_response["/tasks?updated_after=2026-03-25T10:00:00Z"] = {
        "tasks": [{"id": "t2", "state": "working"}, {"id": "t3", "state": "failed"}]
    }
    result = client.tasks(updated_after="2026-03-25T10:00:00Z")
    assert len(result) == 2


# ─────────────────────────────────────────────────────────────────────────────
# T3: tasks() — combined filters
# ─────────────────────────────────────────────────────────────────────────────

def test_t3_tasks_combined_filters(mock_server):
    """tasks() builds correct multi-param query string."""
    server, client = mock_server
    server.get_response[
        "/tasks?status=completed&created_after=2026-03-24T00:00:00Z&sort=asc"
    ] = {"tasks": [{"id": "t4"}]}
    result = client.tasks(
        status="completed",
        created_after="2026-03-24T00:00:00Z",
        sort="asc",
    )
    assert result[0]["id"] == "t4"


# ─────────────────────────────────────────────────────────────────────────────
# T4: cancel_task() — success path
# ─────────────────────────────────────────────────────────────────────────────

def test_t4_cancel_task_success(mock_server):
    """cancel_task() on an active task returns server response."""
    server, client = mock_server
    server.post_response["/tasks/active_task_001:cancel"] = {"state": "canceled"}
    result = client.cancel_task("active_task_001")
    assert result.get("state") == "canceled"


# ─────────────────────────────────────────────────────────────────────────────
# T5: cancel_task() — idempotent 409 (raise_on_terminal=False)
# ─────────────────────────────────────────────────────────────────────────────

def test_t5_cancel_task_409_no_raise(mock_server):
    """cancel_task() on terminal task returns error dict (default, no raise)."""
    server, client = mock_server
    # "terminal_task" triggers 409 in mock handler
    result = client.cancel_task("terminal_task")
    assert "error" in result
    assert result["error"] == "ERR_TASK_NOT_CANCELABLE"


# ─────────────────────────────────────────────────────────────────────────────
# T6: cancel_task() — idempotent 409 (raise_on_terminal=True)
# ─────────────────────────────────────────────────────────────────────────────

def test_t6_cancel_task_409_raise(mock_server):
    """cancel_task(raise_on_terminal=True) raises ValueError on 409."""
    server, client = mock_server
    with pytest.raises(ValueError, match="terminal state"):
        client.cancel_task("terminal_task", raise_on_terminal=True)


# ─────────────────────────────────────────────────────────────────────────────
# T7: capabilities() — http2 + did_identity flags
# ─────────────────────────────────────────────────────────────────────────────

def test_t7_capabilities_http2(mock_server):
    """capabilities() extracts capabilities block from AgentCard."""
    server, client = mock_server
    server.get_response["/.well-known/acp.json"] = {
        "name": "TestRelay",
        "capabilities": {
            "http2": True,
            "did_identity": True,
            "hmac_signing": True,
            "mdns": False,
        },
        "identity": {
            "did": "did:acp:abc123",
            "scheme": "ed25519",
        },
    }
    caps = client.capabilities()
    assert caps.get("http2") is True
    assert caps.get("did_identity") is True
    assert caps.get("mdns") is False


# ─────────────────────────────────────────────────────────────────────────────
# T8: identity() — did:acp: field
# ─────────────────────────────────────────────────────────────────────────────

def test_t8_identity_did(mock_server):
    """identity() returns identity block with did field."""
    server, client = mock_server
    # Reuse AgentCard response from T7
    ident = client.identity()
    assert ident.get("did", "").startswith("did:acp:")
    assert ident.get("scheme") == "ed25519"


# ─────────────────────────────────────────────────────────────────────────────
# T9: did_document() — W3C DID Document structure
# ─────────────────────────────────────────────────────────────────────────────

def test_t9_did_document(mock_server):
    """did_document() fetches /.well-known/did.json and returns DID Document."""
    server, client = mock_server
    server.get_response["/.well-known/did.json"] = {
        "@context": ["https://www.w3.org/ns/did/v1"],
        "id": "did:acp:abc123",
        "verificationMethod": [{
            "id": "did:acp:abc123#keys-1",
            "type": "Ed25519VerificationKey2020",
            "controller": "did:acp:abc123",
            "publicKeyMultibase": "zABC...",
        }],
        "service": [{
            "id": "did:acp:abc123#acp-relay",
            "type": "ACPRelay",
            "serviceEndpoint": "http://127.0.0.1:7901",
        }],
    }
    doc = client.did_document()
    assert doc.get("id", "").startswith("did:acp:")
    assert "@context" in doc
    assert any(s["type"] == "ACPRelay" for s in doc.get("service", []))


# ─────────────────────────────────────────────────────────────────────────────
# T10: capabilities() fallback on server error
# ─────────────────────────────────────────────────────────────────────────────

def test_t10_capabilities_fallback_on_error():
    """capabilities() returns {} when relay is unreachable (no crash)."""
    client = RelayClient("http://127.0.0.1:1", timeout=0.5)
    result = client.capabilities()
    assert result == {}


if __name__ == "__main__":
    import subprocess, sys
    sys.exit(subprocess.call(["python", "-m", "pytest", __file__, "-v"]))
