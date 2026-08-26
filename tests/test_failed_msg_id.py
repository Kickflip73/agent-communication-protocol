"""
test_failed_msg_id.py — v2.30: failed_message_id in error response

Tests FM1–FM8 covering:
- FM1: POST /message:send with message_id to unknown peer → error has failed_message_id
- FM2: POST /message:send without message_id → no failed_message_id in error
- FM3: POST /message:send with invalid JSON body → no failed_message_id (malformed)
- FM4: POST /send (legacy) with message_id → failed_message_id echoed
- FM5: failed_message_id matches exactly what client sent (no mutation)
- FM6: capabilities.error_failed_msg_id declared
- FM7: missing required fields (no 'to') with message_id → failed_message_id echoed
- FM8: multiple error paths all echo failed_message_id when provided
"""

import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest


# ─── helpers ────────────────────────────────────────────────────────────────

def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_ready(base, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"{base}/.well-known/acp.json", timeout=1)
            return
        except Exception:
            time.sleep(0.15)
    raise RuntimeError(f"relay at {base} did not become ready")


def _post(base, path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{base}{path}",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _get(base, path):
    with urllib.request.urlopen(f"{base}{path}", timeout=5) as r:
        return r.status, json.loads(r.read())


# ─── fixture ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def relay_base():
    ws_port = _free_port()
    http_port = ws_port + 100
    base = f"http://127.0.0.1:{http_port}"
    proc = subprocess.Popen(
        [sys.executable, "relay/acp_relay.py", "--port", str(ws_port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        _wait_ready(base)
        yield base
    finally:
        proc.kill()
        proc.wait()


# ─── tests ──────────────────────────────────────────────────────────────────

class TestFailedMsgId:

    def test_fm1_unknown_peer_echoes_message_id(self, relay_base):
        """POST /message:send to unknown peer — error must include failed_message_id"""
        status, body = _post(relay_base, "/message:send", {
            "to": "nonexistent-peer-xyz",
            "message_id": "client-abc-001",
            "content": "hello",
        })
        assert status in (400, 404)
        assert body.get("failed_message_id") == "client-abc-001"

    def test_fm2_no_message_id_no_field(self, relay_base):
        """POST /message:send without message_id — failed_message_id must be absent"""
        status, body = _post(relay_base, "/message:send", {
            "to": "nonexistent-peer-xyz",
            "content": "hello",
        })
        assert status in (400, 404)
        assert "failed_message_id" not in body

    def test_fm3_missing_to_with_message_id(self, relay_base):
        """POST /message:send with message_id but missing 'to' → failed_message_id echoed"""
        status, body = _post(relay_base, "/message:send", {
            "message_id": "client-missing-to-001",
            "content": "hello",
        })
        assert status == 400
        assert body.get("failed_message_id") == "client-missing-to-001"

    def test_fm4_peer_send_unknown_peer_echoes_message_id(self, relay_base):
        """POST /peer/<id>/send to unknown peer → 404 + failed_message_id echoed"""
        status, body = _post(relay_base, "/peer/ghost-peer-999/send", {
            "message_id": "peer-msg-007",
            "content": "hello",
        })
        assert status == 404
        assert body.get("failed_message_id") == "peer-msg-007"

    def test_fm5_exact_match_no_mutation(self, relay_base):
        """failed_message_id must exactly match client's message_id (no truncation/mutation)"""
        long_id = "x" * 128  # 128-char id
        status, body = _post(relay_base, "/message:send", {
            "to": "ghost-peer",
            "message_id": long_id,
            "content": "test",
        })
        assert status in (400, 404)
        assert body.get("failed_message_id") == long_id

    def test_fm6_capability_declared(self, relay_base):
        """capabilities.error_failed_msg_id must be True in /.well-known/acp.json"""
        _, raw = _get(relay_base, "/.well-known/acp.json")
        card = raw.get("self", raw)
        assert card["capabilities"].get("error_failed_msg_id") is True

    def test_fm7_empty_body_no_crash(self, relay_base):
        """POST /message:send with empty object {} — should return 400, no failed_message_id"""
        status, body = _post(relay_base, "/message:send", {})
        assert status == 400
        assert "failed_message_id" not in body

    def test_fm8_unicode_message_id_preserved(self, relay_base):
        """failed_message_id with unicode characters preserved exactly"""
        uid = "消息-001-🔥"
        status, body = _post(relay_base, "/message:send", {
            "to": "ghost",
            "message_id": uid,
            "content": "test",
        })
        assert status in (400, 404)
        assert body.get("failed_message_id") == uid
