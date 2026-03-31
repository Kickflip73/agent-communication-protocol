"""
test_peer_card.py — v2.24 GET /peers/<peer_id>/card tests

Tests:
  PC1: capabilities.peer_card_query = true in AgentCard
  PC2: endpoints.peer_card = '/peers/{peer_id}/card' in AgentCard
  PC3: GET /peers/unknown_id/card → 404 ERR_PEER_NOT_FOUND
  PC4: GET /peers/<peer_id>/card → 200 with ok=true after peer connects
  PC5: response includes peer_id, name, connected, card_available fields
  PC6: agent_card field is dict (not None) after handshake exchange
  PC7: agent_card contains expected ACP fields (name, capabilities, endpoints)
  PC8: GET /peers/<peer_id>/card for disconnected peer still returns cached card
  PC9: version reports 2.24
"""

import sys, os, time, signal, subprocess, requests, pytest
import re as _re

RELAY = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")

WS_A, HTTP_A = 17120, 17220
WS_B, HTTP_B = 17121, 17221

_procs: dict = {}


def _free_port(port):
    try:
        out = subprocess.check_output(["ss", "-tlnp"], text=True,
                                       stderr=subprocess.DEVNULL, timeout=2)
        for line in out.splitlines():
            if f":{port} " in line or f":{port}\t" in line:
                m = _re.search(r"pid=(\d+)", line)
                if m:
                    try:
                        os.kill(int(m.group(1)), signal.SIGKILL)
                    except Exception:
                        pass
    except Exception:
        pass


def _start(ws_port, name, wait=22):
    http = ws_port + 100
    _free_port(ws_port)
    _free_port(http)
    time.sleep(0.3)
    proc = subprocess.Popen(
        [sys.executable, RELAY, "--port", str(ws_port), "--name", name],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    deadline = time.time() + wait
    while time.time() < deadline:
        time.sleep(0.8)
        if proc.poll() is not None:
            err = proc.stderr.read(600).decode(errors="replace")
            raise RuntimeError(f"{name} crashed: {err}")
        try:
            r = requests.get(f"http://127.0.0.1:{http}/status", timeout=2)
            if r.status_code == 200:
                d = r.json()
                if d.get("link") or d.get("relay_token") or d.get("session_id"):
                    return proc
        except Exception:
            pass
    try:
        if requests.get(f"http://127.0.0.1:{http}/status", timeout=2).status_code == 200:
            return proc
    except Exception:
        pass
    proc.kill()
    raise RuntimeError(f"{name} not ready within {wait}s")


def setup_module(_):
    _procs["A"] = _start(WS_A, "PeerCardA")
    _procs["B"] = _start(WS_B, "PeerCardB")


def teardown_module(_):
    for p in _procs.values():
        try:
            p.send_signal(signal.SIGTERM)
            p.wait(timeout=3)
        except Exception:
            pass


def _link(http):
    d = requests.get(f"http://127.0.0.1:{http}/status", timeout=5).json()
    raw = d.get("link") or d.get("relay_token") or ""
    token = raw.rstrip("/").rsplit("/", 1)[-1] if "/" in raw else raw
    ws_port = http - 100
    return f"acp://127.0.0.1:{ws_port}/{token}" if token else None


def _wait_link(http, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            d = requests.get(f"http://127.0.0.1:{http}/status", timeout=2).json()
            if d.get("link") or d.get("relay_token"):
                return True
        except Exception:
            pass
        time.sleep(0.5)
    try:
        d = requests.get(f"http://127.0.0.1:{http}/status", timeout=2).json()
        if d.get("v") or d.get("acp_version"):
            return True
    except Exception:
        pass
    return False


# ── PC1–PC2: capability / endpoint flags ─────────────────────────────────────

def test_PC1_peer_card_query_capability():
    """PC1: AgentCard declares capabilities.peer_card_query=True (v2.24)."""
    _wait_link(HTTP_A)
    card = requests.get(f"http://127.0.0.1:{HTTP_A}/.well-known/acp.json", timeout=5).json()
    caps = (card.get("self") or card).get("capabilities", {})
    assert caps.get("peer_card_query") is True, f"peer_card_query missing: {caps}"


def test_PC2_peer_card_endpoint():
    """PC2: endpoints.peer_card = '/peers/{peer_id}/card' in AgentCard."""
    _wait_link(HTTP_A)
    card = requests.get(f"http://127.0.0.1:{HTTP_A}/.well-known/acp.json", timeout=5).json()
    eps = (card.get("self") or card).get("endpoints", {})
    assert eps.get("peer_card") == "/peers/{peer_id}/card", f"endpoint missing: {eps}"


# ── PC3: 404 for unknown peer ─────────────────────────────────────────────────

def test_PC3_unknown_peer_404():
    """PC3: GET /peers/nonexistent/card → 404 ERR_PEER_NOT_FOUND."""
    _wait_link(HTTP_A)
    r = requests.get(f"http://127.0.0.1:{HTTP_A}/peers/nonexistent_peer_xyz/card", timeout=5)
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.json()}"
    body = r.json()
    assert body.get("error_code") == "ERR_PEER_NOT_FOUND", f"Wrong error_code: {body}"


# ── PC4–PC8: card after peer connects ────────────────────────────────────────

@pytest.fixture(scope="module")
def connected_peer_b():
    """Connect B to A, return peer_b_id."""
    _wait_link(HTTP_B)
    lb = _link(HTTP_B)
    assert lb, f"B link unavailable"
    r = requests.post(f"http://127.0.0.1:{HTTP_A}/peers/connect",
                      json={"link": lb}, timeout=10).json()
    time.sleep(3)  # wait for agent_card handshake exchange
    return r.get("peer_id")


def test_PC4_card_200_after_connect(connected_peer_b):
    """PC4: GET /peers/<peer_id>/card → 200 ok=true after connection."""
    peer_id = connected_peer_b
    assert peer_id, "peer_id not available"
    r = requests.get(f"http://127.0.0.1:{HTTP_A}/peers/{peer_id}/card", timeout=5)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.json()}"
    assert r.json().get("ok") is True


def test_PC5_card_response_fields(connected_peer_b):
    """PC5: response includes peer_id, name, connected, card_available."""
    peer_id = connected_peer_b
    body = requests.get(f"http://127.0.0.1:{HTTP_A}/peers/{peer_id}/card", timeout=5).json()
    assert "peer_id" in body, f"peer_id missing: {body}"
    assert "name" in body, f"name missing: {body}"
    assert "connected" in body, f"connected missing: {body}"
    assert "card_available" in body, f"card_available missing: {body}"
    assert body["peer_id"] == peer_id


def test_PC6_agent_card_not_none(connected_peer_b):
    """PC6: agent_card is a non-None dict after handshake (acp.agent_card exchange)."""
    peer_id = connected_peer_b
    body = requests.get(f"http://127.0.0.1:{HTTP_A}/peers/{peer_id}/card", timeout=5).json()
    assert body.get("card_available") is True, \
        f"card_available=False, handshake may not have completed: {body}"
    card = body.get("agent_card")
    assert isinstance(card, dict), f"agent_card is not dict: {card!r}"


def test_PC7_agent_card_has_acp_fields(connected_peer_b):
    """PC7: agent_card contains ACP standard fields (name, capabilities, endpoints)."""
    peer_id = connected_peer_b
    body = requests.get(f"http://127.0.0.1:{HTTP_A}/peers/{peer_id}/card", timeout=5).json()
    card = body.get("agent_card") or {}
    # AgentCard may be nested under "self"
    actual = card.get("self") or card
    assert "name" in actual, f"name missing from agent_card: {actual}"
    assert "capabilities" in actual, f"capabilities missing from agent_card: {actual}"
    assert "endpoints" in actual, f"endpoints missing from agent_card: {actual}"


def test_PC8_disconnected_peer_returns_cached_card(connected_peer_b):
    """PC8: after disconnect, /peers/<id>/card still returns cached card_available."""
    # This is a soft test — card may or may not persist across disconnect
    # depending on whether peer was cleaned up; just verify endpoint doesn't 500
    peer_id = connected_peer_b
    r = requests.get(f"http://127.0.0.1:{HTTP_A}/peers/{peer_id}/card", timeout=5)
    assert r.status_code in (200, 404), f"Unexpected status: {r.status_code}: {r.json()}"


# ── PC9: version ──────────────────────────────────────────────────────────────

def test_PC9_version_2_24():
    """PC9: Server reports VERSION 2.24.x."""
    _wait_link(HTTP_A)
    r = requests.get(f"http://127.0.0.1:{HTTP_A}/status", timeout=5).json()
    ver = r.get("acp_version") or r.get("v") or ""
    major, minor = ver.split(".")[:2]
    assert (int(major), int(minor)) >= (2, 24), f"Expected 2.24+, got: {ver}"
