"""
ACP v2.36 — Read Receipt tests (RR1–RR8)

Two-phase receipt semantics:
  acp.delivered  (v2.35) — physical delivery: message arrived at peer WS
  acp.read       (v2.36) — logical consumption: peer replied (consumed message)

Tests:
- RR1: capabilities.read_receipt is True in agent_card
- RR2: /status includes messages_read counter (starts at 0)
- RR3: /peers includes messages_read per connected peer
- RR4: Alpha sends msg → Beta replies → Alpha's messages_read increments
- RR5: Per-peer messages_read counter increments after read receipt received
- RR6: acp.read does NOT trigger another acp.read (no loop)
- RR7: Fresh relay starts with messages_read = 0
- RR8: messages_delivered and messages_read are independent counters
        (delivery always ≥ read; read only increments when peer replies)
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


def _wait_for(fn, timeout=15, interval=0.5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if fn():
            return True
        time.sleep(interval)
    return False


# ── module-scoped fixture: Alpha + Beta connected pair ────────────────────────

@pytest.fixture(scope="module")
def rr_pair():
    a_ws = _free_port()
    a_http = a_ws + 100
    b_ws = _free_port()
    b_http = b_ws + 100

    alpha = _start_relay(a_ws, "RR-Alpha")
    time.sleep(1)

    # Wait for Alpha link
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

    beta = _start_relay(b_ws, "RR-Beta", join=local_link)
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


# ── RR1 ───────────────────────────────────────────────────────────────────────

def test_rr1_capability_declared(rr_pair):
    """RR1: capabilities.read_receipt must be True in agent_card."""
    data, code = _http(rr_pair["a_http"], "/status")
    assert code == 200
    caps = (data.get("agent_card") or {}).get("capabilities", {})
    assert caps.get("read_receipt") is True, f"read_receipt missing from agent_card.capabilities: {caps}"


# ── RR2 ───────────────────────────────────────────────────────────────────────

def test_rr2_status_has_messages_read(rr_pair):
    """RR2: /status must include messages_read counter (int)."""
    data, code = _http(rr_pair["a_http"], "/status")
    assert code == 200
    assert "messages_read" in data, "missing messages_read in /status"
    assert isinstance(data["messages_read"], int)


# ── RR3 ───────────────────────────────────────────────────────────────────────

def test_rr3_peers_has_messages_read(rr_pair):
    """RR3: /peers must include messages_read per connected peer."""
    data, code = _http(rr_pair["a_http"], "/peers")
    assert code == 200
    connected = [p for p in data.get("peers", []) if p.get("connected")]
    assert connected, "No connected peers"
    for p in connected:
        assert "messages_read" in p, f"messages_read missing from peer entry: {p}"


# ── RR4 ───────────────────────────────────────────────────────────────────────

def test_rr4_read_counter_increments_after_reply(rr_pair):
    """RR4: Alpha's messages_read must increment after Beta replies to Alpha's message.

    Flow:
      1. Alpha sends → Beta (triggers acp.delivered on Alpha side, v2.35)
      2. Beta sends reply → Alpha (triggers acp.read on Alpha side, v2.36)
      3. Alpha messages_read should be > before
    """
    a_http = rr_pair["a_http"]
    b_http = rr_pair["b_http"]

    before_read = _http(a_http, "/status")[0].get("messages_read", 0)

    # Step 1: Alpha sends to Beta
    resp, code = _http(a_http, "/message:send", method="POST", body={
        "role": "agent",
        "text": "RR4 — please reply",
    })
    assert code == 200, f"Alpha send failed: {resp}"
    time.sleep(0.5)

    # Step 2: Beta replies (this should trigger acp.read on Alpha)
    resp2, code2 = _http(b_http, "/message:send", method="POST", body={
        "role": "agent",
        "text": "RR4 — reply from Beta",
    })
    assert code2 == 200, f"Beta reply failed: {resp2}"

    ok = _wait_for(
        lambda: _http(a_http, "/status")[0].get("messages_read", 0) > before_read,
        timeout=10,
    )
    after_read = _http(a_http, "/status")[0].get("messages_read", 0)
    assert ok, f"messages_read did not increment: before={before_read} after={after_read}"


# ── RR5 ───────────────────────────────────────────────────────────────────────

def test_rr5_per_peer_read_counter_increments(rr_pair):
    """RR5: Per-peer messages_read counter must increment after read receipt."""
    a_http = rr_pair["a_http"]
    b_http = rr_pair["b_http"]

    peers_before, _ = _http(a_http, "/peers")
    connected = [p for p in peers_before.get("peers", []) if p.get("connected")]
    assert connected
    before_peer_read = connected[0].get("messages_read", 0)

    # Alpha sends, then Beta replies
    _http(a_http, "/message:send", method="POST", body={"role": "agent", "text": "RR5 probe"})
    time.sleep(0.3)
    _http(b_http, "/message:send", method="POST", body={"role": "agent", "text": "RR5 reply"})

    ok = _wait_for(
        lambda: any(
            p.get("messages_read", 0) > before_peer_read
            for p in _http(a_http, "/peers")[0].get("peers", [])
            if p.get("connected")
        ),
        timeout=10,
    )
    after_peer_read = max(
        (p.get("messages_read", 0) for p in _http(a_http, "/peers")[0].get("peers", []) if p.get("connected")),
        default=0,
    )
    assert ok, f"Per-peer messages_read did not increment: before={before_peer_read} after={after_peer_read}"


# ── RR6 ───────────────────────────────────────────────────────────────────────

def test_rr6_no_read_receipt_loop(rr_pair):
    """RR6: acp.read must NOT trigger another acp.read (no infinite loop)."""
    a_http = rr_pair["a_http"]
    b_http = rr_pair["b_http"]

    _http(a_http, "/message:send", method="POST", body={"role": "agent", "text": "RR6 loop test"})
    time.sleep(0.3)
    _http(b_http, "/message:send", method="POST", body={"role": "agent", "text": "RR6 reply"})
    time.sleep(2)

    count1 = _http(a_http, "/status")[0].get("messages_read", 0)
    time.sleep(2)
    count2 = _http(a_http, "/status")[0].get("messages_read", 0)

    assert count2 == count1, (
        f"messages_read grew after stabilisation ({count1}→{count2}): possible read-receipt loop"
    )


# ── RR7 ───────────────────────────────────────────────────────────────────────

def test_rr7_fresh_relay_starts_at_zero():
    """RR7: A freshly started relay must have messages_read = 0."""
    ws = _free_port()
    http = ws + 100
    relay = _start_relay(ws, "RR7-Fresh", local_only=True)
    time.sleep(1)
    try:
        data, code = _http(http, "/status")
        assert code == 200
        assert data.get("messages_read", -1) == 0, (
            f"Expected 0, got {data.get('messages_read')}"
        )
    finally:
        relay.terminate()
        relay.wait()


# ── RR8 ───────────────────────────────────────────────────────────────────────

def test_rr8_delivered_and_read_are_independent(rr_pair):
    """RR8: messages_delivered and messages_read are independent counters.

    After Alpha sends N messages:
      - Alpha.messages_delivered >= N   (Beta ACK'd every delivery)
      - Alpha.messages_read == 0 extra  (Beta hasn't replied yet in this isolated test)

    After Beta replies once:
      - Alpha.messages_read increments by at least 1
    """
    a_http = rr_pair["a_http"]
    b_http = rr_pair["b_http"]

    before_del  = _http(a_http, "/status")[0].get("messages_delivered", 0)
    before_read = _http(a_http, "/status")[0].get("messages_read", 0)

    # Alpha sends 3 messages without Beta replying
    for i in range(3):
        _http(a_http, "/message:send", method="POST", body={
            "role": "agent", "text": f"RR8 msg #{i+1} (no reply expected)"
        })
        time.sleep(0.1)

    # Wait for deliveries
    _wait_for(
        lambda: _http(a_http, "/status")[0].get("messages_delivered", 0) >= before_del + 3,
        timeout=10,
    )
    mid_del  = _http(a_http, "/status")[0].get("messages_delivered", 0)
    mid_read = _http(a_http, "/status")[0].get("messages_read", 0)

    assert mid_del >= before_del + 3, f"delivery counter too low: {mid_del}"
    assert mid_read == before_read, (
        f"messages_read should not have changed yet: before={before_read} mid={mid_read}"
    )

    # Now Beta replies — messages_read should increment
    _http(b_http, "/message:send", method="POST", body={"role": "agent", "text": "RR8 final reply"})
    _wait_for(
        lambda: _http(a_http, "/status")[0].get("messages_read", 0) > before_read,
        timeout=10,
    )
    final_read = _http(a_http, "/status")[0].get("messages_read", 0)
    assert final_read > before_read, (
        f"messages_read should have incremented after Beta replied: {before_read}→{final_read}"
    )
