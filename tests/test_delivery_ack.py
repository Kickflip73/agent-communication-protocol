"""
ACP v2.35 — Delivery ACK tests (DA1–DA10)

Tests verify that:
- DA1:  capabilities.delivery_ack is True in /status
- DA2:  /status includes messages_delivered counter (starts at 0)
- DA3:  /peers includes messages_delivered per connected peer
- DA4:  After Alpha sends a message to Beta, Alpha's messages_delivered increments
- DA5:  Per-peer messages_delivered counter increments after send+ack
- DA6:  acp.delivered does not trigger another acp.delivered (no ack loop)
- DA7:  Fresh relay starts with messages_delivered = 0
- DA8:  /.well-known/acp.json declares capabilities.delivery_ack = True
- DA9:  acp.ping (control frame) does NOT increment messages_delivered
- DA10: Sending N messages results in at least N delivery ACKs
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
    """Start a relay. local_only=True (default) skips public-IP + relay registration for fast CI."""
    env = os.environ.copy()
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        env.pop(k, None)
    cmd = [sys.executable, RELAY_SCRIPT, "--port", str(ws_port), "--name", name]
    if join:
        cmd += ["--join", join]
    if local_only and not join:   # local-only only applies to host mode (not guest/join)
        cmd += ["--local-only"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    for s in (proc.stdout, proc.stderr):
        threading.Thread(target=lambda x=s: x.read(), daemon=True).start()
    return proc


def _wait_for(fn, timeout=15, interval=0.5):
    """Poll fn() until it returns truthy or timeout expires; returns final bool."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if fn():
            return True
        time.sleep(interval)
    return False


# ── module-scoped fixture: Alpha + Beta connected pair ────────────────────────

@pytest.fixture(scope="module")
def ack_pair():
    a_ws = _free_port()
    a_http = a_ws + 100
    b_ws = _free_port()

    alpha = _start_relay(a_ws, "ACK-Alpha")
    time.sleep(2)

    # Wait for Alpha's link to be ready (relay generates link in <3s in practice)
    local_link = None
    for _ in range(30):
        data, code = _http(a_http, "/status")
        if code == 200 and data.get("link"):
            raw_link = data["link"]
            token = raw_link.split("/")[-1] if "/" in raw_link else None
            if token:
                local_link = f"acp://127.0.0.1:{a_ws}/{token}"
                break
        time.sleep(0.5)
    assert local_link, "Alpha never generated a link/token"

    beta = _start_relay(b_ws, "ACK-Beta", join=local_link)
    time.sleep(2)

    ok = _wait_for(
        lambda: any(
            p.get("connected")
            for p in _http(a_http, "/peers")[0].get("peers", [])
        ),
        timeout=15,
    )
    assert ok, "Alpha never saw Beta as a connected peer"

    yield {"a_http": a_http, "a_ws": a_ws, "b_ws": b_ws}

    alpha.terminate()
    beta.terminate()
    alpha.wait()
    beta.wait()


# ── DA1 ───────────────────────────────────────────────────────────────────────

def test_da1_capability_declared(ack_pair):
    """DA1: capabilities.delivery_ack must be True in agent_card."""
    data, code = _http(ack_pair["a_http"], "/status")
    assert code == 200
    caps = (data.get("agent_card") or {}).get("capabilities", {})
    assert caps.get("delivery_ack") is True, f"delivery_ack not in agent_card.capabilities: {caps}"


# ── DA2 ───────────────────────────────────────────────────────────────────────

def test_da2_status_has_messages_delivered(ack_pair):
    """DA2: /status must include messages_delivered (int)."""
    data, code = _http(ack_pair["a_http"], "/status")
    assert code == 200
    assert "messages_delivered" in data, f"missing messages_delivered in /status"
    assert isinstance(data["messages_delivered"], int)


# ── DA3 ───────────────────────────────────────────────────────────────────────

def test_da3_peers_has_messages_delivered(ack_pair):
    """DA3: /peers must include messages_delivered per connected peer."""
    data, code = _http(ack_pair["a_http"], "/peers")
    assert code == 200
    connected = [p for p in data.get("peers", []) if p.get("connected")]
    assert connected, "No connected peers"
    for p in connected:
        assert "messages_delivered" in p, f"messages_delivered missing from peer entry: {p}"


# ── DA4 ───────────────────────────────────────────────────────────────────────

def test_da4_counter_increments_after_send(ack_pair):
    """DA4: Alpha's messages_delivered must increment after sending a message to Beta."""
    a_http = ack_pair["a_http"]

    before, _ = _http(a_http, "/status")
    before_count = before.get("messages_delivered", 0)

    resp, code = _http(a_http, "/message:send", method="POST", body={
        "role": "agent",
        "text": "DA4 delivery ack test",
    })
    assert code == 200, f"Send failed: {resp}"
    assert resp.get("message_id"), "No message_id in send response"

    ok = _wait_for(
        lambda: _http(a_http, "/status")[0].get("messages_delivered", 0) > before_count,
        timeout=10,
    )
    after_count = _http(a_http, "/status")[0].get("messages_delivered", 0)
    assert ok, f"messages_delivered did not increment: before={before_count} after={after_count}"


# ── DA5 ───────────────────────────────────────────────────────────────────────

def test_da5_per_peer_counter_increments(ack_pair):
    """DA5: Per-peer messages_delivered counter increments after send+ack."""
    a_http = ack_pair["a_http"]

    peers_before, _ = _http(a_http, "/peers")
    connected = [p for p in peers_before.get("peers", []) if p.get("connected")]
    assert connected
    before_peer_count = connected[0].get("messages_delivered", 0)

    resp, code = _http(a_http, "/message:send", method="POST", body={
        "role": "agent",
        "text": "DA5 per-peer counter test",
    })
    assert code == 200, f"Send failed: {resp}"

    ok = _wait_for(
        lambda: any(
            p.get("messages_delivered", 0) > before_peer_count
            for p in _http(a_http, "/peers")[0].get("peers", [])
            if p.get("connected")
        ),
        timeout=10,
    )
    peers_after, _ = _http(a_http, "/peers")
    after_peer_count = max(
        (p.get("messages_delivered", 0) for p in peers_after.get("peers", []) if p.get("connected")),
        default=0,
    )
    assert ok, f"Per-peer messages_delivered did not increment: before={before_peer_count} after={after_peer_count}"


# ── DA6 ───────────────────────────────────────────────────────────────────────

def test_da6_no_ack_loop(ack_pair):
    """DA6: acp.delivered must NOT trigger another acp.delivered (no infinite loop)."""
    a_http = ack_pair["a_http"]

    resp, code = _http(a_http, "/message:send", method="POST", body={
        "role": "agent",
        "text": "DA6 ack-loop detection",
    })
    assert code == 200

    time.sleep(2)
    count1 = _http(a_http, "/status")[0].get("messages_delivered", 0)
    time.sleep(2)
    count2 = _http(a_http, "/status")[0].get("messages_delivered", 0)

    assert count2 == count1, (
        f"messages_delivered grew after stabilisation ({count1} → {count2}): possible ACK loop"
    )


# ── DA7 ───────────────────────────────────────────────────────────────────────

def test_da7_fresh_relay_starts_at_zero():
    """DA7: A newly started relay must have messages_delivered = 0."""
    ws = _free_port()
    http = ws + 100
    relay = _start_relay(ws, "DA7-Fresh", local_only=True)
    time.sleep(1)
    try:
        data, code = _http(http, "/status")
        assert code == 200
        assert data.get("messages_delivered", -1) == 0, (
            f"Expected 0, got {data.get('messages_delivered')}"
        )
    finally:
        relay.terminate()
        relay.wait()


# ── DA8 ───────────────────────────────────────────────────────────────────────

def test_da8_agentcard_declares_capability(ack_pair):
    """DA8: /.well-known/acp.json 'self.capabilities' must include delivery_ack = True."""
    data, code = _http(ack_pair["a_http"], "/.well-known/acp.json")
    assert code == 200
    # /.well-known/acp.json returns {"self": <AgentCard>, "peer": ...}
    self_card = data.get("self") or data  # fallback: some versions return the card directly
    caps = self_card.get("capabilities", {})
    assert caps.get("delivery_ack") is True, (
        f"delivery_ack missing from /.well-known/acp.json self.capabilities: {caps}"
    )


# ── DA9 ───────────────────────────────────────────────────────────────────────

def test_da9_ping_does_not_trigger_ack(ack_pair):
    """DA9: acp.ping (control frame) must NOT increment messages_delivered."""
    a_http = ack_pair["a_http"]

    peers_data, _ = _http(a_http, "/peers")
    connected = [p for p in peers_data.get("peers", []) if p.get("connected")]
    assert connected, "No connected peers for ping test"
    peer_id = connected[0]["id"]

    before_count = _http(a_http, "/status")[0].get("messages_delivered", 0)

    # Trigger a ping (control frame — should NOT cause acp.delivered)
    _http(a_http, f"/peers/{peer_id}/ping", method="POST", body={})
    time.sleep(2)

    after_count = _http(a_http, "/status")[0].get("messages_delivered", 0)
    assert after_count == before_count, (
        f"messages_delivered changed after ping: before={before_count} after={after_count}"
    )


# ── DA10 ──────────────────────────────────────────────────────────────────────

def test_da10_multiple_messages_multiple_acks(ack_pair):
    """DA10: Sending N messages must yield at least N delivery ACKs."""
    a_http = ack_pair["a_http"]
    N = 3

    before_count = _http(a_http, "/status")[0].get("messages_delivered", 0)

    for i in range(N):
        resp, code = _http(a_http, "/message:send", method="POST", body={
            "role": "agent",
            "text": f"DA10 bulk message #{i + 1}",
        })
        assert code == 200, f"Send #{i + 1} failed: {resp}"
        time.sleep(0.1)

    ok = _wait_for(
        lambda: _http(a_http, "/status")[0].get("messages_delivered", 0) >= before_count + N,
        timeout=15,
    )
    final_count = _http(a_http, "/status")[0].get("messages_delivered", 0)
    assert ok, f"Expected >= {before_count + N} deliveries, got {final_count}"
