"""
tests/test_peer_message_history.py
===================================
Tests for v2.48: GET /peers/<peer_id>/messages — per-peer message history query.

Strategy: single relay (--test-mode) + POST /debug/inject for peer+message injection.
No P2P connection required; avoids BUG-030 flakiness.

Scenarios:
  PMH1  - peer not found → 404 ERR_PEER_NOT_FOUND
  PMH2  - basic inbound message history returns messages
  PMH3  - direction=inbound filter — all returned messages have direction=inbound
  PMH4  - direction=outbound filter — valid structure (may be 0 messages in test env)
  PMH5  - direction=all (default) — includes inbound messages
  PMH6  - since_seq incremental polling — only returns server_seq > N
  PMH7  - limit + offset pagination + has_more / next_offset
  PMH8  - sort=asc / sort=desc ordering by received_at timestamp
  PMH9  - invalid params → 400 ERR_INVALID_REQUEST (direction/sort/limit/offset/since_seq)
  PMH10 - capabilities.peer_message_history=True + endpoints.peer_messages in AgentCard
"""

import json
import os
import socket
import subprocess
import sys
import time
import threading
import urllib.request
import urllib.error

import pytest

RELAY_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _free_port():
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _http(port, path, method="GET", body=None):
    url = f"http://127.0.0.1:{port}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read()), e.code
        except Exception:
            return {}, e.code


def _start_relay(ws_port, name, extra_args=None):
    env = os.environ.copy()
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        env.pop(k, None)
    cmd = [sys.executable, RELAY_SCRIPT,
           "--port", str(ws_port), "--name", name, "--local-only", "--test-mode"]
    if extra_args:
        cmd += extra_args
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    for s in (proc.stdout, proc.stderr):
        threading.Thread(target=lambda x=s: x.read(), daemon=True).start()
    return proc


def _wait_http(http_port, timeout=12):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            data, code = _http(http_port, "/status")
            if code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def _inject(http_port, from_name, content, message_id=None,
            context_id=None, priority="normal", direction="inbound"):
    """Inject a message via POST /debug/inject (--test-mode endpoint)."""
    body = {
        "from": from_name,
        "parts": [{"type": "text", "content": content}],
        "direction": direction,
    }
    if message_id:
        body["message_id"] = message_id
    if context_id:
        body["context_id"] = context_id
    if priority != "normal":
        body["priority"] = priority
    return _http(http_port, "/debug/inject", "POST", body)


def _find_peer_id(http_port, agent_name, timeout=5):
    """Find peer id (list[].id) by agent name (list[].name). Returns None if not found."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        data, code = _http(http_port, "/peers")
        if code == 200:
            peers = data.get("peers", [])
            if isinstance(peers, list):
                for p in peers:
                    if p.get("name") == agent_name or p.get("agent_name") == agent_name:
                        return p.get("id") or p.get("peer_id")
        time.sleep(0.3)
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Module-scoped fixture
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def relay():
    """Single relay with --test-mode. HTTP port = ws_port + 100."""
    ws_port = _free_port()
    http_port = ws_port + 100

    proc = _start_relay(ws_port, "PMH-Relay")
    ok = _wait_http(http_port, timeout=12)
    assert ok, f"Relay HTTP interface did not start on :{http_port}"

    yield {"http": http_port, "ws": ws_port}

    proc.terminate()
    proc.wait()


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────

def test_pmh1_peer_not_found(relay):
    """PMH1: Nonexistent peer → 404 ERR_PEER_NOT_FOUND."""
    data, code = _http(relay["http"], "/peers/nonexistent-xyz-999/messages")
    assert code == 404, f"Expected 404, got {code}: {data}"
    assert data.get("ok") is False
    assert data.get("error_code") == "ERR_PEER_NOT_FOUND"


def test_pmh2_basic_history(relay):
    """PMH2: Injected messages appear in /peers/<id>/messages."""
    http = relay["http"]

    for i in range(3):
        result, code = _inject(http, "PMH-Alpha", f"alpha-msg-{i}",
                               message_id=f"pmh2-alpha-{i}")
        assert code == 200, f"inject failed: {result}"

    peer_id = _find_peer_id(http, "PMH-Alpha")
    assert peer_id, "PMH-Alpha not auto-registered as peer"

    data, code = _http(http, f"/peers/{peer_id}/messages")
    assert code == 200, f"Expected 200, got {code}: {data}"
    assert data["ok"] is True
    assert data["peer_id"] == peer_id
    assert isinstance(data["messages"], list)
    assert data["count"] >= 1, f"Expected ≥1 message, got {data['count']}"
    assert "total" in data
    assert "has_more" in data
    assert data["count"] <= data["total"]

    # Verify message structure
    msg = data["messages"][0]
    assert "message_id" in msg
    assert "direction" in msg
    assert "parts" in msg
    assert "received_at" in msg


def test_pmh3_direction_inbound(relay):
    """PMH3: direction=inbound — all returned messages have direction='inbound'."""
    http = relay["http"]
    r, code = _inject(http, "PMH-Beta", "pmh3-inbound-test")
    assert code == 200, f"inject failed: {r}"

    peer_id = _find_peer_id(http, "PMH-Beta")
    assert peer_id, "PMH-Beta not registered"

    data, code = _http(http, f"/peers/{peer_id}/messages?direction=inbound")
    assert code == 200
    assert data["direction_filter"] == "inbound"
    for msg in data["messages"]:
        assert msg["direction"] == "inbound", \
            f"direction=inbound leaked outbound: {msg['message_id']}"


def test_pmh4_direction_outbound(relay):
    """PMH4: direction=outbound — valid structure, each message has direction=outbound."""
    http = relay["http"]
    r, code = _inject(http, "PMH-Gamma", "pmh4-test")
    assert code == 200, f"inject failed: {r}"

    peer_id = _find_peer_id(http, "PMH-Gamma")
    assert peer_id

    data, code = _http(http, f"/peers/{peer_id}/messages?direction=outbound")
    assert code == 200
    assert data["direction_filter"] == "outbound"
    assert isinstance(data["messages"], list)
    for msg in data["messages"]:
        assert msg["direction"] == "outbound", \
            f"direction=outbound leaked inbound: {msg['message_id']}"


def test_pmh5_direction_all(relay):
    """PMH5: direction=all (default) — returns inbound messages."""
    http = relay["http"]
    r, code = _inject(http, "PMH-Delta", "pmh5-all-test")
    assert code == 200, f"inject failed: {r}"

    peer_id = _find_peer_id(http, "PMH-Delta")
    assert peer_id

    # explicit direction=all
    data, code = _http(http, f"/peers/{peer_id}/messages?direction=all")
    assert code == 200
    assert data["direction_filter"] == "all"
    assert data["count"] >= 1, "direction=all should include injected inbound messages"

    # default (no direction param)
    data2, code2 = _http(http, f"/peers/{peer_id}/messages")
    assert code2 == 200
    assert data2["count"] >= 1


def test_pmh6_since_seq_incremental(relay):
    """PMH6: since_seq=N returns only messages with server_seq > N."""
    http = relay["http"]

    r1, c1 = _inject(http, "PMH-Echo", "pmh6-before", message_id="pmh6-before-1")
    assert c1 == 200
    time.sleep(0.1)

    peer_id = _find_peer_id(http, "PMH-Echo")
    assert peer_id

    # Record the server_seq from the inject response
    seq_before = r1.get("server_seq", 0)

    # Inject another message after recording seq_before
    r2, c2 = _inject(http, "PMH-Echo", "pmh6-after", message_id="pmh6-after-1")
    assert c2 == 200
    time.sleep(0.1)

    # since_seq=seq_before should exclude the first message
    data, code = _http(http, f"/peers/{peer_id}/messages?since_seq={seq_before}&sort=asc")
    assert code == 200
    for msg in data.get("messages", []):
        if msg.get("server_seq"):
            assert msg["server_seq"] > seq_before, \
                f"since_seq={seq_before}: got msg with server_seq={msg['server_seq']}"


def test_pmh7_pagination(relay):
    """PMH7: limit + offset pagination with has_more and next_offset."""
    http = relay["http"]

    for i in range(6):
        r, c = _inject(http, "PMH-Foxtrot", f"pmh7-item-{i}", message_id=f"pmh7-f{i}")
        assert c == 200

    peer_id = _find_peer_id(http, "PMH-Foxtrot")
    assert peer_id

    all_data, _ = _http(http, f"/peers/{peer_id}/messages")
    total = all_data["total"]

    if total < 3:
        pytest.skip(f"Only {total} messages injected; need ≥ 3")

    # Page 1: limit=2
    p1, code = _http(http, f"/peers/{peer_id}/messages?limit=2&offset=0")
    assert code == 200
    assert len(p1["messages"]) <= 2

    if total > 2:
        assert p1["has_more"] is True, f"has_more should be True when total={total} > 2"
        assert p1["next_offset"] == 2

        # Page 2
        p2, _ = _http(http, f"/peers/{peer_id}/messages?limit=2&offset=2")
        assert p2["ok"] is True
        assert p2["count"] <= 2

        # Verify no overlap (message_ids should differ between pages)
        ids_p1 = {m["message_id"] for m in p1["messages"] if m.get("message_id")}
        ids_p2 = {m["message_id"] for m in p2["messages"] if m.get("message_id")}
        assert not (ids_p1 & ids_p2), "Pages overlap: same message_id in both pages"
    else:
        assert p1["has_more"] is False
        assert p1["next_offset"] is None


def test_pmh8_sort_order(relay):
    """PMH8: sort=asc → oldest first; sort=desc → newest first."""
    http = relay["http"]

    for i in range(4):
        r, c = _inject(http, "PMH-Golf", f"pmh8-order-{i}", message_id=f"pmh8-g{i}")
        assert c == 200
        time.sleep(0.06)  # distinct timestamps

    peer_id = _find_peer_id(http, "PMH-Golf")
    assert peer_id

    asc_data, _ = _http(http, f"/peers/{peer_id}/messages?sort=asc")
    desc_data, _ = _http(http, f"/peers/{peer_id}/messages?sort=desc")

    assert asc_data["sort"] == "asc"
    assert desc_data["sort"] == "desc"

    asc_ts = [m["received_at"] for m in asc_data["messages"] if m.get("received_at")]
    if len(asc_ts) >= 2:
        for i in range(len(asc_ts) - 1):
            assert asc_ts[i] <= asc_ts[i + 1], \
                f"ASC order violated: [{i}]={asc_ts[i]} > [{i+1}]={asc_ts[i+1]}"

    desc_ts = [m["received_at"] for m in desc_data["messages"] if m.get("received_at")]
    if len(desc_ts) >= 2:
        for i in range(len(desc_ts) - 1):
            assert desc_ts[i] >= desc_ts[i + 1], \
                f"DESC order violated: [{i}]={desc_ts[i]} < [{i+1}]={desc_ts[i+1]}"

    # ASC first == DESC last (same first-injected message appears at start/end respectively)
    if asc_ts and desc_ts and len(asc_ts) >= 2:
        assert asc_ts[0] <= desc_ts[0], \
            "ASC[0] should be ≤ DESC[0] (oldest appears first in ASC)"


def test_pmh9_invalid_params(relay):
    """PMH9: Invalid query params → 400 ERR_INVALID_REQUEST."""
    http = relay["http"]

    r, c = _inject(http, "PMH-Hotel", "pmh9-setup")
    assert c == 200
    peer_id = _find_peer_id(http, "PMH-Hotel")
    assert peer_id

    cases = [
        ("?direction=sideways", "invalid direction"),
        ("?sort=random",        "invalid sort"),
        ("?limit=abc",          "non-integer limit"),
        ("?offset=xyz",         "non-integer offset"),
        ("?since_seq=not-int",  "non-integer since_seq"),
    ]
    for qs, desc in cases:
        data, code = _http(http, f"/peers/{peer_id}/messages{qs}")
        assert code == 400, f"[{desc}] expected 400, got {code}: {data}"
        assert data.get("error_code") == "ERR_INVALID_REQUEST", \
            f"[{desc}] expected ERR_INVALID_REQUEST, got: {data.get('error_code')}"


def test_pmh10_capability_declared(relay):
    """PMH10: AgentCard (/.well-known/acp.json self field) declares capabilities + endpoint."""
    http = relay["http"]

    data, code = _http(http, "/.well-known/acp.json")
    assert code == 200

    # /.well-known/acp.json returns {"self": <AgentCard>, "peer": ...}
    self_card = data.get("self", {})
    caps = self_card.get("capabilities", {})

    assert caps.get("peer_message_history") is True, \
        f"capabilities.peer_message_history should be True; got {caps.get('peer_message_history')}"

    endpoints = self_card.get("endpoints", {})
    assert "peer_messages" in endpoints, \
        f"endpoints.peer_messages not declared. Keys: {list(endpoints.keys())[:15]}"
    assert "{peer_id}" in endpoints["peer_messages"], \
        f"endpoints.peer_messages should contain {{peer_id}}, got: {endpoints['peer_messages']}"
