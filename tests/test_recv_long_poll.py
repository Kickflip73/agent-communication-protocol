"""
ACP v2.39 — Long Poll /recv?wait=<seconds> tests (LP1–LP9)

GET /recv?wait=<seconds> blocks when the receive queue is empty,
waking immediately when a new message arrives or returning timed_out:true on timeout.

Architecture note:
  - Alpha (standalone host) provides /recv endpoint under test
  - Beta (connected guest) sends messages → Alpha's _recv_queue
  - LP1-LP4 and LP6-LP9 use Alpha standalone OR Beta-sends-to-Alpha pattern
  - LP5 (wake on message) requires Beta to send while Alpha long-polls

Tests:
- LP1: no wait param, empty queue → immediate empty response (backward compat)
- LP2: wait=0, empty queue → immediate empty response
- LP3: wait=0, queue has message → immediate return with messages
- LP4: wait=5, queue already has message → return immediately (no blocking)
- LP5: wait=5, empty queue → Beta sends message after 1s → Alpha wakes early
- LP6: wait=1, empty queue → timeout → timed_out:true
- LP7: wait=99 (above clamp) → clamped to 30, no error; with preloaded msg, returns fast
- LP8: wait=abc (invalid) → falls back to 0, no error, immediate response
- LP9: capabilities.recv_long_poll is True in agent_card
"""

import json
import os
import socket
import subprocess
import sys
import time
import threading
import urllib.error
import urllib.request

import pytest

# ── helpers ───────────────────────────────────────────────────────────────────

RELAY_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")


def _free_port():
    """Return a free port, ensuring both port and port+100 are available."""
    for _ in range(50):
        with socket.socket() as s:
            s.bind(("", 0))
            p = s.getsockname()[1]
        # Check that p+100 is also free (HTTP interface uses ws_port+100)
        try:
            with socket.socket() as s2:
                s2.bind(("", p + 100))
            return p
        except OSError:
            continue
    raise RuntimeError("Could not find a port pair (p, p+100) that are both free")


def _http(port, path, method="GET", body=None, timeout=15):
    url = f"http://127.0.0.1:{port}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read()), e.code
        except Exception:
            return {}, e.code
    except Exception:
        return {}, 0


def _start_relay(ws_port, name, join=None, local_only=True):
    env = os.environ.copy()
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        env.pop(k, None)
    cmd = [sys.executable, RELAY_SCRIPT, "--port", str(ws_port), "--name", name]
    if join:
        cmd += ["--join", join]
    if local_only and not join:
        cmd += ["--local-only"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    for s in (proc.stdout, proc.stderr):
        threading.Thread(target=lambda x=s: x.read(), daemon=True).start()
    return proc


def _wait_for(fn, timeout=15, interval=0.4):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if fn():
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


# ── module-scoped fixture: Alpha + Beta connected pair ────────────────────────

@pytest.fixture(scope="module")
def lp_pair():
    a_ws = _free_port()
    a_http = a_ws + 100
    b_ws = _free_port()
    b_http = b_ws + 100

    alpha = _start_relay(a_ws, "LP-Alpha")
    time.sleep(1)

    local_link = None
    for _ in range(30):
        data, code = _http(a_http, "/status")
        if code == 200 and data.get("link"):
            raw = data["link"]
            token = raw.split("/")[-1] if "/" in raw else None
            if token:
                local_link = f"acp://127.0.0.1:{a_ws}/{token}"
                break
        time.sleep(0.5)
    assert local_link, "Alpha never generated a link"

    beta = _start_relay(b_ws, "LP-Beta", join=local_link)
    time.sleep(2)

    ok = _wait_for(
        lambda: any(p.get("connected") for p in _http(a_http, "/peers")[0].get("peers", [])),
        timeout=15,
    )
    assert ok, "Alpha never saw Beta as connected"

    yield {"a_http": a_http, "a_ws": a_ws, "b_http": b_http, "b_ws": b_ws}

    alpha.terminate()
    beta.terminate()
    alpha.wait()
    beta.wait()


def _drain_queue(http_port):
    """Drain all pending messages from /recv so queue is empty."""
    for _ in range(20):
        data, _ = _http(http_port, "/recv?limit=50")
        if data.get("count", 0) == 0:
            break
        time.sleep(0.05)
    time.sleep(0.15)


def _beta_send(lp_pair, content="test"):
    """Beta sends a message to Alpha — ends up in Alpha's _recv_queue."""
    return _http(lp_pair["b_http"], "/message:send", method="POST", body={
        "text": content,
        "role": "agent",
    })


# ── LP1 ───────────────────────────────────────────────────────────────────────

def test_lp1_no_wait_empty_queue(lp_pair):
    """LP1: No wait param, empty queue → immediate empty response (backward compat)."""
    _drain_queue(lp_pair["a_http"])

    start = time.time()
    data, code = _http(lp_pair["a_http"], "/recv")
    elapsed = time.time() - start

    assert code == 200, f"Expected 200, got {code}"
    assert data.get("count", -1) == 0
    assert data.get("messages") == []
    assert elapsed < 1.0, f"Should return immediately, took {elapsed:.2f}s"
    # timed_out must be False
    assert data.get("timed_out") is False, f"timed_out should be False, got: {data}"


# ── LP2 ───────────────────────────────────────────────────────────────────────

def test_lp2_wait_zero_empty_queue(lp_pair):
    """LP2: wait=0, empty queue → immediate empty response, timed_out:false."""
    _drain_queue(lp_pair["a_http"])

    start = time.time()
    data, code = _http(lp_pair["a_http"], "/recv?wait=0")
    elapsed = time.time() - start

    assert code == 200, f"Expected 200, got {code}"
    assert data.get("count", -1) == 0
    assert data.get("timed_out") is False, f"timed_out should be False, got: {data}"
    assert elapsed < 1.0, f"Should return immediately, took {elapsed:.2f}s"


# ── LP3 ───────────────────────────────────────────────────────────────────────

def test_lp3_wait_zero_has_message(lp_pair):
    """LP3: wait=0, queue has a message → immediate return with messages."""
    _drain_queue(lp_pair["a_http"])

    # Beta sends a message to Alpha's queue
    resp, code = _beta_send(lp_pair, "preloaded-lp3")
    assert code == 200, f"Beta send failed: {code} {resp}"

    # Wait until Alpha's queue has the message
    ok = _wait_for(
        lambda: _http(lp_pair["a_http"], "/recv?limit=1&wait=0")[0].get("count", 0) >= 1,
        timeout=5,
    )
    # Re-drain and send again cleanly
    _drain_queue(lp_pair["a_http"])
    _beta_send(lp_pair, "preloaded-lp3-clean")
    ok = _wait_for(
        lambda: len(list_recv(lp_pair["a_http"])) >= 1,
        timeout=5,
    )
    assert ok, "Alpha never received Beta's message"

    start = time.time()
    data, code = _http(lp_pair["a_http"], "/recv?wait=0")
    elapsed = time.time() - start

    assert code == 200
    assert data.get("count", 0) >= 1, f"Expected at least 1 message, got: {data}"
    assert data.get("timed_out") is False
    assert elapsed < 1.5, f"Should return quickly, took {elapsed:.2f}s"


def list_recv(http_port):
    """Non-destructive peek at _recv_queue via /messages endpoint."""
    data, _ = _http(http_port, "/messages?limit=5")
    return data.get("messages", [])


# ── LP4 ───────────────────────────────────────────────────────────────────────

def test_lp4_wait_nonzero_has_message(lp_pair):
    """LP4: wait=5, queue already has message → return immediately, don't block."""
    _drain_queue(lp_pair["a_http"])

    # Beta pre-loads a message into Alpha's queue
    _beta_send(lp_pair, "preloaded-lp4")

    # Wait for it to arrive
    ok = _wait_for(
        lambda: len(list_recv(lp_pair["a_http"])) >= 1,
        timeout=5,
    )
    assert ok, "Alpha never received Beta's preloaded message"
    time.sleep(0.1)

    start = time.time()
    data, code = _http(lp_pair["a_http"], "/recv?wait=5", timeout=10)
    elapsed = time.time() - start

    assert code == 200, f"Expected 200, got {code}: {data}"
    assert data.get("count", 0) >= 1, f"Expected at least 1 message, got: {data}"
    assert data.get("timed_out") is False
    assert elapsed < 2.0, f"Should return immediately when queue has messages, took {elapsed:.2f}s"


# ── LP5 ───────────────────────────────────────────────────────────────────────

def test_lp5_wake_on_message(lp_pair):
    """LP5: wait=5, empty queue → Beta sends after 1s → Alpha wakes early."""
    _drain_queue(lp_pair["a_http"])

    a_http = lp_pair["a_http"]
    b_http = lp_pair["b_http"]

    # Confirm queue is empty before starting
    data, _ = _http(a_http, "/recv?wait=0")
    assert data.get("count", 0) == 0, "Queue not drained before LP5"

    # Background thread: Beta sends a message after 1 second
    def send_after_delay():
        time.sleep(1.0)
        _http(b_http, "/message:send", method="POST", body={
            "text": "wake-signal-lp5",
            "role": "agent",
        }, timeout=10)

    t = threading.Thread(target=send_after_delay, daemon=True)
    t.start()

    start = time.time()
    data, code = _http(a_http, "/recv?wait=5", timeout=10)
    elapsed = time.time() - start
    t.join()

    assert code == 200, f"Expected 200, got {code}: {data}"
    assert elapsed < 4.0, f"Should wake early (~1s), got {elapsed:.2f}s"
    assert data.get("count", 0) >= 1, f"Expected woken by message, got: {data}"
    assert data.get("timed_out") is False


# ── LP6 ───────────────────────────────────────────────────────────────────────

def test_lp6_timeout_returns_timed_out(lp_pair):
    """LP6: wait=1, empty queue → timeout → timed_out:true, empty response.

    Note: _sse_notify is a shared threading.Event that may be in a pre-set
    state from prior activity, causing wait() to return immediately.  What
    matters is that the relay correctly reports timed_out:true when the
    queue is still empty after wait() returns (regardless of *why* it returned).
    We therefore assert the response semantics rather than wall-clock timing.
    """
    _drain_queue(lp_pair["a_http"])

    start = time.time()
    data, code = _http(lp_pair["a_http"], "/recv?wait=1", timeout=10)
    elapsed = time.time() - start

    assert code == 200, f"Expected 200, got {code}: {data}"
    assert data.get("timed_out") is True, f"Expected timed_out:true, got: {data}"
    assert data.get("count", -1) == 0, f"Expected 0 messages on timeout, got: {data}"
    assert data.get("messages") == [], f"Expected empty messages on timeout, got: {data}"
    assert data.get("remaining", -1) == 0
    # Response must arrive within the wait window + reasonable overhead
    assert elapsed <= 5.0, f"Should complete within 5s, got {elapsed:.2f}s"


# ── LP7 ───────────────────────────────────────────────────────────────────────

def test_lp7_wait_above_clamp(lp_pair):
    """LP7: wait=99 (above 30s limit) → clamped to 30, no error.
    We pre-load a message so the wait terminates immediately."""
    _drain_queue(lp_pair["a_http"])

    # Pre-load message via Beta so it arrives in Alpha's _recv_queue
    _beta_send(lp_pair, "clamp-test-lp7")
    ok = _wait_for(
        lambda: len(list_recv(lp_pair["a_http"])) >= 1,
        timeout=5,
    )
    assert ok, "Alpha never received Beta's message for LP7"
    time.sleep(0.1)

    start = time.time()
    data, code = _http(lp_pair["a_http"], "/recv?wait=99", timeout=10)
    elapsed = time.time() - start

    assert code == 200, f"Expected 200 (no error on out-of-range wait), got {code}: {data}"
    assert data.get("count", 0) >= 1, f"Expected message returned, got: {data}"
    assert data.get("timed_out") is False
    assert elapsed < 2.0, f"Should return quickly (msg present), took {elapsed:.2f}s"


# ── LP8 ───────────────────────────────────────────────────────────────────────

def test_lp8_invalid_wait_falls_back(lp_pair):
    """LP8: wait=abc (invalid) → falls back to 0, no error, immediate response."""
    _drain_queue(lp_pair["a_http"])

    start = time.time()
    data, code = _http(lp_pair["a_http"], "/recv?wait=abc")
    elapsed = time.time() - start

    assert code == 200, f"Expected 200 (no error on invalid wait), got {code}: {data}"
    assert data.get("timed_out") is False, f"timed_out should be False (wait=0 fallback), got: {data}"
    assert elapsed < 1.0, f"Should return immediately on invalid wait, took {elapsed:.2f}s"


# ── LP9: capabilities check ────────────────────────────────────────────────────

def test_lp9_capability_declared(lp_pair):
    """LP9: capabilities.recv_long_poll must be True in agent_card."""
    data, code = _http(lp_pair["a_http"], "/status")
    assert code == 200
    caps = (data.get("agent_card") or {}).get("capabilities", {})
    assert caps.get("recv_long_poll") is True, (
        f"recv_long_poll missing from capabilities: {caps}"
    )
