"""
test_messages_list.py — ACP v2.9 GET /messages history list endpoint tests

Tests:
  ML1: Basic query (no params) returns empty list when relay is fresh
  ML2: After receiving a message, verify total/messages/has_more fields
  ML3: limit/offset pagination correctness
  ML4: sort=asc/desc ordering
  ML5: role filter (agent/user)
  ML6: received_after time filter
  ML7: limit exceeding max (100) gets clamped
  ML8: Invalid params (non-numeric offset/limit) return 400
"""

import json
import pytest
import subprocess
import time
import urllib.request
import urllib.error
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RELAY_PATH = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")


def _free_port():
    """Return an OS-assigned free port where port AND port+100 are both free."""
    import socket
    for _ in range(200):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            ws = s.getsockname()[1]
        try:
            with socket.socket() as s2:
                s2.bind(("127.0.0.1", ws + 100))
                return ws
        except OSError:
            continue
    raise RuntimeError("Could not find a free port pair (ws + ws+100)")


WS_PORT   = _free_port()
HTTP_PORT = WS_PORT + 100

_proc = None


def _make_env():
    env = os.environ.copy()
    for k in ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY"):
        env.pop(k, None)
    return env


def _wait_ready(timeout=15):
    """Wait until relay is up AND has a P2P link available."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://localhost:{HTTP_PORT}/.well-known/acp.json", timeout=1
            ) as r:
                if r.status == 200:
                    # Also wait for link to be set (requires IP detection ~4s)
                    link_deadline = time.time() + 10
                    while time.time() < link_deadline:
                        try:
                            with urllib.request.urlopen(
                                f"http://localhost:{HTTP_PORT}/link", timeout=1
                            ) as rl:
                                ld = json.loads(rl.read())
                                if ld.get("link"):
                                    return True
                        except Exception:
                            pass
                        time.sleep(0.3)
                    # Even if link isn't available, relay is up
                    return True
        except Exception:
            time.sleep(0.2)
    return False


def _get(path):
    with urllib.request.urlopen(
        f"http://localhost:{HTTP_PORT}{path}", timeout=5
    ) as r:
        return r.status, json.loads(r.read())


def _get_err(path):
    """GET that handles error responses, returning (status, body)."""
    req = urllib.request.Request(f"http://localhost:{HTTP_PORT}{path}")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"http://localhost:{HTTP_PORT}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _inject_message(role="agent", text="hello", from_peer="peer_test", context_id=None):
    """
    Inject a message into the relay's recv_queue via the /recv-inject debug endpoint,
    or alternatively via /message:send with a mock payload.
    Since there's no dedicated inject endpoint, we use the internal test approach:
    POST to /message:send which stores into _recv_queue when received from self.
    
    Actually we inject by calling the relay's internal HTTP endpoint that processes
    incoming messages. We use the existing /message:send endpoint, which on the
    relay side stores to _recv_queue only when received via WebSocket.
    
    For testing, we directly inject via the relay's debug introspection at /recv
    ... Actually the cleanest approach is to use the relay's own send endpoint
    to send to itself via HTTP, which triggers message processing.
    
    The relay stores messages in _recv_queue when it RECEIVES them (from a peer WS).
    For unit testing without a real peer, we use the /tasks/create endpoint which
    triggers _on_message logic indirectly, or we patch via a special test route.
    
    Simplest approach: spin up two relays and connect them, but that's complex.
    Instead, we exploit the relay's /message:send which in relay mode (no peer)
    may not store to recv_queue.
    
    BEST APPROACH: Use the relay's own HTTP POST /message:send to self, but since
    _recv_queue is only populated on WebSocket receive, we need to either:
    1. Use a second relay instance that connects and sends
    2. POST to a special test-only endpoint
    
    Looking at the code: _recv_queue is populated in _on_message() which is called
    from the WebSocket handler. For integration tests, the easiest path is to
    connect a second relay that sends a message.
    
    For test simplicity, we use the conftest.py helper pattern from existing tests.
    """
    pass


def _send_via_second_relay(text="hello", role="agent", from_name="sender",
                           target_port=None):
    """
    Start a second relay instance, connect it to the test relay, send a message,
    then stop it. Returns True if sent successfully.
    """
    import socket as _socket
    # Find free ports for second relay
    for _ in range(200):
        with _socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            ws2 = s.getsockname()[1]
        try:
            with _socket.socket() as s2:
                s2.bind(("127.0.0.1", ws2 + 100))
                break
        except OSError:
            continue
    else:
        return False

    http2 = ws2 + 100
    env = _make_env()

    # Get the join link — try /link first (set after IP detection), then /status
    link = None
    ws_port_card = WS_PORT
    import re as _re

    for attempt in range(3):
        try:
            with urllib.request.urlopen(
                f"http://localhost:{HTTP_PORT}/link", timeout=3
            ) as r:
                ld = json.loads(r.read())
                link = ld.get("link", "")
                if link:
                    break
        except Exception:
            pass
        try:
            with urllib.request.urlopen(
                f"http://localhost:{HTTP_PORT}/status", timeout=3
            ) as r:
                sd = json.loads(r.read())
                link = sd.get("link", "")
                ws_port_card = sd.get("ws_port", WS_PORT) or WS_PORT
                if link:
                    break
        except Exception:
            pass
        time.sleep(1)

    if not link:
        # Fallback: reconstruct from ws_port + token from /.well-known
        try:
            with urllib.request.urlopen(
                f"http://localhost:{HTTP_PORT}/.well-known/acp.json", timeout=3
            ) as r:
                card_data = json.loads(r.read())
            self_card = card_data.get("self", card_data)
            token = self_card.get("token", "")
            ws_port_card = self_card.get("ws_port", WS_PORT) or WS_PORT
            if token:
                link = f"acp://127.0.0.1:{ws_port_card}/{token}"
        except Exception:
            pass

    if not link:
        return False

    # Replace any public IP with 127.0.0.1 for local testing
    link = _re.sub(r"acp://[^:/]+:", f"acp://127.0.0.1:", link)

    proc2 = subprocess.Popen(
        [sys.executable, RELAY_PATH, "--port", str(ws2),
         "--name", from_name, "--join", link],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
    )
    try:
        # Wait for second relay to be ready
        deadline2 = time.time() + 10
        while time.time() < deadline2:
            try:
                with urllib.request.urlopen(
                    f"http://localhost:{http2}/.well-known/acp.json", timeout=1
                ) as r2:
                    if r2.status == 200:
                        break
            except Exception:
                time.sleep(0.2)
        else:
            return False

        # Wait for peer connection to establish
        time.sleep(0.5)

        # Send message via second relay
        body = {
            "role":  role,
            "parts": [{"type": "text", "content": text}],
        }
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            f"http://localhost:{http2}/message:send",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as r3:
                return r3.status in (200, 201)
        except Exception:
            return False
    finally:
        proc2.terminate()
        try:
            proc2.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc2.kill()


@pytest.fixture(scope="module", autouse=True)
def single_relay():
    global _proc
    env = _make_env()
    _proc = subprocess.Popen(
        [sys.executable, RELAY_PATH, "--port", str(WS_PORT), "--name", "MLAgent"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
    )
    if not _wait_ready():
        _proc.kill()
        pytest.fail(f"Relay (HTTP:{HTTP_PORT}) did not start in time")
    yield
    _proc.terminate()
    try:
        _proc.wait(timeout=6)
    except subprocess.TimeoutExpired:
        _proc.kill()


# ─────────────────────────────────────────────────────────────────────────────
# ML1: Basic query (no params) returns empty list on fresh relay
# ─────────────────────────────────────────────────────────────────────────────

def test_ml1_basic_empty_list():
    """ML1: GET /messages with no params on fresh relay returns empty list."""
    status, data = _get("/messages")
    assert status == 200, f"Expected 200: {data}"
    assert "messages" in data,  f"Missing 'messages' key: {data}"
    assert "total"    in data,  f"Missing 'total' key: {data}"
    assert "has_more" in data,  f"Missing 'has_more' key: {data}"
    assert isinstance(data["messages"], list), "messages must be a list"
    # Fresh relay (no peers connected, no messages received)
    assert data["total"]    == 0,   f"Expected total=0 on fresh relay: {data}"
    assert data["has_more"] is False, f"Expected has_more=False on fresh relay: {data}"


# ─────────────────────────────────────────────────────────────────────────────
# ML2: After messages are received, verify total/messages/has_more
# ─────────────────────────────────────────────────────────────────────────────

def test_ml2_messages_after_receive():
    """ML2: After messages arrive, total/messages/has_more reflect correctly."""
    # Send 2 messages via second relay
    sent1 = _send_via_second_relay(text="ml2-msg-1", from_name="ML2Sender")
    time.sleep(0.3)
    sent2 = _send_via_second_relay(text="ml2-msg-2", from_name="ML2Sender2")
    time.sleep(0.3)

    if not (sent1 or sent2):
        pytest.skip("Could not establish peer connection for ML2 test")

    status, data = _get("/messages")
    assert status == 200, f"Expected 200: {data}"
    assert "messages"    in data, f"Missing 'messages': {data}"
    assert "total"       in data, f"Missing 'total': {data}"
    assert "has_more"    in data, f"Missing 'has_more': {data}"
    assert "next_offset" in data, f"Missing 'next_offset': {data}"

    count = int(sent1) + int(sent2)
    assert data["total"] >= count, (
        f"Expected total >= {count} after {count} sends: {data['total']}"
    )
    assert len(data["messages"]) >= count, (
        f"Expected at least {count} messages in list: {len(data['messages'])}"
    )

    # Verify message fields
    for msg in data["messages"]:
        assert "id"          in msg or "message_id" in msg, f"Missing id/message_id: {msg}"
        assert "received_at" in msg, f"Missing received_at: {msg}"
        assert "role"        in msg, f"Missing role: {msg}"
        assert "parts"       in msg, f"Missing parts: {msg}"


# ─────────────────────────────────────────────────────────────────────────────
# ML3: limit/offset pagination correctness
# ─────────────────────────────────────────────────────────────────────────────

def test_ml3_pagination():
    """ML3: limit/offset pagination works correctly."""
    # Send enough messages to test pagination
    for i in range(4):
        _send_via_second_relay(text=f"ml3-msg-{i}", from_name=f"ML3Sender{i}")
        time.sleep(0.15)

    # Get all messages to know the total
    _, all_data = _get("/messages?limit=100&offset=0")
    total = all_data["total"]

    if total < 2:
        pytest.skip("Not enough messages for pagination test")

    # Page 1: limit=2, offset=0
    status, page1 = _get("/messages?limit=2&offset=0")
    assert status == 200
    assert len(page1["messages"]) <= 2

    # Page 2: limit=2, offset=2
    status, page2 = _get("/messages?limit=2&offset=2")
    assert status == 200

    # No overlap between pages
    ids1 = {m.get("id") or m.get("message_id") for m in page1["messages"]}
    ids2 = {m.get("id") or m.get("message_id") for m in page2["messages"]}
    overlap = ids1 & ids2
    assert len(overlap) == 0, f"Page overlap detected: {overlap}"

    # has_more is True on page 1 when total > 2
    if total > 2:
        assert page1["has_more"] is True, (
            f"has_more should be True (total={total} > limit=2): {page1}"
        )
        assert page1["next_offset"] == 2, (
            f"next_offset should be 2: {page1}"
        )

    # Last page: has_more should be False
    _, last_page = _get(f"/messages?limit=100&offset=0")
    assert last_page["has_more"] is False, (
        f"has_more should be False when fetching all: {last_page}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# ML4: sort=asc/desc ordering
# ─────────────────────────────────────────────────────────────────────────────

def test_ml4_sort_asc_desc():
    """ML4: sort=asc returns oldest first; sort=desc returns newest first."""
    # Send messages with time gaps to ensure ordering is detectable
    sent_a = _send_via_second_relay(text="ml4-first",  from_name="ML4Sender")
    time.sleep(0.3)
    sent_b = _send_via_second_relay(text="ml4-second", from_name="ML4Sender")
    time.sleep(0.3)

    if not (sent_a and sent_b):
        pytest.skip("Could not send messages for ML4 sort test")

    _, asc_data  = _get("/messages?sort=asc&limit=100&offset=0")
    _, desc_data = _get("/messages?sort=desc&limit=100&offset=0")

    asc_times  = [m.get("received_at", 0) for m in asc_data["messages"]]
    desc_times = [m.get("received_at", 0) for m in desc_data["messages"]]

    # Verify asc is non-decreasing
    for i in range(len(asc_times) - 1):
        assert asc_times[i] <= asc_times[i + 1], (
            f"sort=asc: times not non-decreasing at index {i}: {asc_times[i]} > {asc_times[i+1]}"
        )

    # Verify desc is non-increasing
    for i in range(len(desc_times) - 1):
        assert desc_times[i] >= desc_times[i + 1], (
            f"sort=desc: times not non-increasing at index {i}: {desc_times[i]} < {desc_times[i+1]}"
        )

    # asc and desc should be reverses of each other
    if len(asc_data["messages"]) > 1:
        asc_ids  = [m.get("id") or m.get("message_id") for m in asc_data["messages"]]
        desc_ids = [m.get("id") or m.get("message_id") for m in desc_data["messages"]]
        assert asc_ids == list(reversed(desc_ids)), (
            f"asc and desc results should be reverses:\nasc={asc_ids}\ndesc={desc_ids}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# ML5: role filter
# ─────────────────────────────────────────────────────────────────────────────

def test_ml5_role_filter():
    """ML5: role=agent/user filter returns only matching messages."""
    # Send one message with role=agent (default) and one with role=user
    sent_agent = _send_via_second_relay(text="ml5-agent-msg", role="agent",
                                        from_name="ML5SenderA")
    time.sleep(0.2)
    sent_user = _send_via_second_relay(text="ml5-user-msg",  role="user",
                                       from_name="ML5SenderB")
    time.sleep(0.2)

    if not (sent_agent or sent_user):
        pytest.skip("Could not send messages for ML5 role filter test")

    # Filter by agent
    _, agent_data = _get("/messages?role=agent&limit=100&offset=0")
    for msg in agent_data["messages"]:
        assert msg.get("role") == "agent", (
            f"role=agent filter returned non-agent message: {msg}"
        )

    # Filter by user
    _, user_data = _get("/messages?role=user&limit=100&offset=0")
    for msg in user_data["messages"]:
        assert msg.get("role") == "user", (
            f"role=user filter returned non-user message: {msg}"
        )

    # totals should sum to overall total (or less, since some may have neither)
    _, all_data = _get("/messages?limit=100&offset=0")
    assert agent_data["total"] + user_data["total"] <= all_data["total"] + 1, (
        "agent + user totals exceed overall total by more than 1"
    )


# ─────────────────────────────────────────────────────────────────────────────
# ML6: received_after time filter
# ─────────────────────────────────────────────────────────────────────────────

def test_ml6_received_after_filter():
    """ML6: received_after=<unix_ts> filters out older messages."""
    # Record timestamp before sending
    before_ts = time.time()
    time.sleep(0.1)

    sent = _send_via_second_relay(text="ml6-after-msg", from_name="ML6Sender")
    time.sleep(0.3)

    if not sent:
        pytest.skip("Could not send message for ML6 received_after test")

    # Query messages received after 'before_ts'
    _, data = _get(f"/messages?received_after={before_ts}&limit=100&offset=0")
    assert data["total"] >= 1, (
        f"Expected at least 1 message after ts={before_ts}: {data}"
    )
    for msg in data["messages"]:
        assert msg.get("received_at", 0) > before_ts, (
            f"Message received_at={msg.get('received_at')} should be > {before_ts}"
        )

    # Query messages received AFTER current time: should be 0
    future_ts = time.time() + 9999
    _, future_data = _get(f"/messages?received_after={future_ts}&limit=100&offset=0")
    assert future_data["total"] == 0, (
        f"Expected 0 messages after future ts: {future_data}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# ML7: limit exceeding max (100) gets clamped
# ─────────────────────────────────────────────────────────────────────────────

def test_ml7_limit_clamped_to_100():
    """ML7: limit=200 (exceeds max 100) is silently clamped to 100."""
    status, data = _get("/messages?limit=200&offset=0")
    assert status == 200, f"Expected 200: {data}"
    assert "messages" in data, f"Missing 'messages': {data}"
    # The response should succeed and return at most 100 items
    assert len(data["messages"]) <= 100, (
        f"Clamped limit=100 still returned {len(data['messages'])} messages"
    )
    # Verify total field is present (not affected by clamping)
    assert "total" in data, f"Missing 'total': {data}"


# ─────────────────────────────────────────────────────────────────────────────
# ML8: Invalid params (non-numeric offset/limit) return 400
# ─────────────────────────────────────────────────────────────────────────────

def test_ml8_invalid_params_return_400():
    """ML8: Non-numeric offset or limit returns 400 ERR_INVALID_REQUEST."""
    # Non-numeric limit
    status_l, data_l = _get_err("/messages?limit=abc&offset=0")
    assert status_l == 400, (
        f"Expected 400 for limit=abc: status={status_l}, data={data_l}"
    )
    assert data_l.get("error_code") == "ERR_INVALID_REQUEST", (
        f"Expected ERR_INVALID_REQUEST for limit=abc: {data_l}"
    )

    # Non-numeric offset
    status_o, data_o = _get_err("/messages?limit=10&offset=xyz")
    assert status_o == 400, (
        f"Expected 400 for offset=xyz: status={status_o}, data={data_o}"
    )
    assert data_o.get("error_code") == "ERR_INVALID_REQUEST", (
        f"Expected ERR_INVALID_REQUEST for offset=xyz: {data_o}"
    )

    # Both invalid
    status_b, data_b = _get_err("/messages?limit=foo&offset=bar")
    assert status_b == 400, (
        f"Expected 400 for limit=foo&offset=bar: status={status_b}, data={data_b}"
    )


# ─────────────────────────────────────────────────────────────────────────────

def run_tests():
    """Pytest entry point for direct execution."""
    pytest.main([__file__, "-v"])


if __name__ == "__main__":
    run_tests()
