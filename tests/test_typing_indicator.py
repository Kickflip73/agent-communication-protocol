"""
ACP v2.37 — Typing Indicator tests (TI1–TI8)

POST /message:typing → sends 'acp.typing' control frame to peer.
Peer receives frame → updates peer.typing state + broadcasts SSE 'typing' event.

Agent real-time status trio:
  acp.delivered (v2.35) — physical delivery ✓
  acp.read      (v2.36) — logical consumption ✓✓
  acp.typing    (v2.37) — typing status 🖊

Tests:
- TI1: capabilities.typing_indicator is True in agent_card
- TI2: /status includes peer_typing (bool) and peer_typing_since fields
- TI3: /peers includes typing and typing_since per connected peer
- TI4: POST /message:typing {typing:true} returns ok:True
- TI5: After Alpha POSTs typing:true, Beta's peer_typing becomes True
- TI6: After Alpha POSTs typing:false, Beta's peer_typing resets to False
- TI7: POST /message:typing without 'typing' field defaults to true
- TI8: POST /message:typing to disconnected relay returns 503 ERR_NOT_CONNECTED
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


def _wait_for(fn, timeout=15, interval=0.4):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if fn():
            return True
        time.sleep(interval)
    return False


# ── module-scoped fixture: Alpha + Beta connected pair ────────────────────────

@pytest.fixture(scope="module")
def ti_pair():
    a_ws = _free_port()
    a_http = a_ws + 100
    b_ws = _free_port()
    b_http = b_ws + 100

    alpha = _start_relay(a_ws, "TI-Alpha")
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

    beta = _start_relay(b_ws, "TI-Beta", join=local_link)
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


# ── TI1 ───────────────────────────────────────────────────────────────────────

def test_ti1_capability_declared(ti_pair):
    """TI1: capabilities.typing_indicator must be True in agent_card."""
    data, code = _http(ti_pair["a_http"], "/status")
    assert code == 200
    caps = (data.get("agent_card") or {}).get("capabilities", {})
    assert caps.get("typing_indicator") is True, (
        f"typing_indicator missing from agent_card.capabilities: {caps}"
    )


# ── TI2 ───────────────────────────────────────────────────────────────────────

def test_ti2_status_has_peer_typing(ti_pair):
    """TI2: /status must include peer_typing (bool) and peer_typing_since fields."""
    data, code = _http(ti_pair["a_http"], "/status")
    assert code == 200
    assert "peer_typing" in data, "peer_typing missing from /status"
    assert isinstance(data["peer_typing"], bool), "peer_typing must be bool"
    assert "peer_typing_since" in data, "peer_typing_since missing from /status"


# ── TI3 ───────────────────────────────────────────────────────────────────────

def test_ti3_peers_has_typing_field(ti_pair):
    """TI3: /peers must include typing and typing_since per connected peer."""
    data, code = _http(ti_pair["a_http"], "/peers")
    assert code == 200
    connected = [p for p in data.get("peers", []) if p.get("connected")]
    assert connected, "No connected peers"
    for p in connected:
        assert "typing" in p, f"typing missing from peer: {p}"
        assert "typing_since" in p, f"typing_since missing from peer: {p}"


# ── TI4 ───────────────────────────────────────────────────────────────────────

def test_ti4_post_typing_returns_ok(ti_pair):
    """TI4: POST /message:typing {typing:true} must return ok:True."""
    resp, code = _http(ti_pair["a_http"], "/message:typing", method="POST",
                       body={"typing": True})
    assert code == 200, f"Unexpected status {code}: {resp}"
    assert resp.get("ok") is True, f"Expected ok:true, got: {resp}"
    assert resp.get("typing") is True


# ── TI5 ───────────────────────────────────────────────────────────────────────

def test_ti5_peer_typing_true_propagates(ti_pair):
    """TI5: After Alpha POSTs typing:true, Beta's peer_typing becomes True."""
    a_http = ti_pair["a_http"]
    b_http = ti_pair["b_http"]

    # Reset state
    _http(a_http, "/message:typing", method="POST", body={"typing": False})
    time.sleep(0.3)

    # Alpha starts typing → Beta should see peer_typing=True
    resp, code = _http(a_http, "/message:typing", method="POST", body={"typing": True})
    assert code == 200

    ok = _wait_for(
        lambda: _http(b_http, "/status")[0].get("peer_typing") is True,
        timeout=10,
    )
    beta_status = _http(b_http, "/status")[0]
    assert ok, (
        f"Beta peer_typing never became True: {beta_status.get('peer_typing')}"
    )
    assert beta_status.get("peer_typing_since") is not None, "peer_typing_since should be set"


# ── TI6 ───────────────────────────────────────────────────────────────────────

def test_ti6_peer_typing_false_resets(ti_pair):
    """TI6: After Alpha POSTs typing:false, Beta's peer_typing resets to False."""
    a_http = ti_pair["a_http"]
    b_http = ti_pair["b_http"]

    # Ensure Alpha is typing first
    _http(a_http, "/message:typing", method="POST", body={"typing": True})
    _wait_for(lambda: _http(b_http, "/status")[0].get("peer_typing") is True, timeout=8)

    # Stop typing
    _http(a_http, "/message:typing", method="POST", body={"typing": False})

    ok = _wait_for(
        lambda: _http(b_http, "/status")[0].get("peer_typing") is False,
        timeout=10,
    )
    beta_status = _http(b_http, "/status")[0]
    assert ok, f"Beta peer_typing never reset to False: {beta_status.get('peer_typing')}"
    assert beta_status.get("peer_typing_since") is None, (
        f"peer_typing_since should be None after stop: {beta_status.get('peer_typing_since')}"
    )


# ── TI7 ───────────────────────────────────────────────────────────────────────

def test_ti7_default_typing_is_true(ti_pair):
    """TI7: POST /message:typing without 'typing' field defaults to true."""
    resp, code = _http(ti_pair["a_http"], "/message:typing", method="POST", body={})
    assert code == 200, f"Unexpected status {code}: {resp}"
    assert resp.get("typing") is True, f"Expected typing:true by default, got: {resp}"


# ── TI8 ───────────────────────────────────────────────────────────────────────

def test_ti8_typing_on_disconnected_relay_returns_503():
    """TI8: POST /message:typing on a standalone relay (no peer) returns 503."""
    ws = _free_port()
    http = ws + 100
    relay = _start_relay(ws, "TI8-Alone", local_only=True)
    time.sleep(1.5)
    try:
        resp, code = _http(http, "/message:typing", method="POST", body={"typing": True})
        assert code == 503, f"Expected 503, got {code}: {resp}"
        # error structure: {ok:false, error_code:"ERR_NOT_CONNECTED", error:"..."}
        err_code = resp.get("error_code") or (resp.get("error", {}) or {}).get("code")
        assert err_code == "ERR_NOT_CONNECTED", f"Expected ERR_NOT_CONNECTED: {resp}"
    finally:
        relay.terminate()
        relay.wait()
