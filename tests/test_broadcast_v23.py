"""
test_broadcast_v23.py — v2.23 broadcast enhancements

Tests:
  BH1: capabilities.peers_broadcast_subset = true
  BH2: capabilities.peers_broadcast_history = true
  BH3: endpoints.peers_broadcast_history = '/peers/broadcast/history'
  BH4: GET /peers/broadcast/history returns empty list on fresh start
  BH5: broadcast populates history (broadcast_id, ts, delivered, failed)
  BH6: broadcast_id returned in POST /peers/broadcast response
  BH7: GET /peers/broadcast/history?limit=1 returns only 1 entry
  BH8: POST /peers/broadcast with target_peers=[] (empty) → 503 ERR_NO_PEERS
  BH9: POST /peers/broadcast with unknown target_peers → 400 ERR_INVALID_REQUEST
  BH10: POST /peers/broadcast target_peers subset (B only) — only B receives, C doesn't
  BH11: version reports 2.23
"""

import sys, os, time, signal, subprocess, requests, pytest
import re as _re

RELAY = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")

WS_A, HTTP_A = 17110, 17210
WS_B, HTTP_B = 17111, 17211
WS_C, HTTP_C = 17112, 17212

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
        [sys.executable, RELAY, "--port", str(ws_port), "--name", name, "--local-only"],
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
    # Fallback: if HTTP responding accept
    try:
        if requests.get(f"http://127.0.0.1:{http}/status", timeout=2).status_code == 200:
            return proc
    except Exception:
        pass
    proc.kill()
    raise RuntimeError(f"{name} not ready within {wait}s")


def setup_module(_):
    _procs["A"] = _start(WS_A, "BroadcastV23A")
    _procs["B"] = _start(WS_B, "BroadcastV23B")
    _procs["C"] = _start(WS_C, "BroadcastV23C")


def teardown_module(_):
    for p in _procs.values():
        try:
            p.send_signal(signal.SIGTERM)
            p.wait(timeout=3)
        except Exception:
            pass


def _link(http):
    """Return localhost acp:// link by rebuilding with 127.0.0.1."""
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
    # Fallback: version present
    try:
        d = requests.get(f"http://127.0.0.1:{http}/status", timeout=2).json()
        if d.get("v") or d.get("acp_version"):
            return True
    except Exception:
        pass
    return False


def _msg_text(msg):
    parts = msg.get("parts") or []
    if parts and isinstance(parts[0], dict):
        return parts[0].get("content", "")
    return msg.get("text", "") or msg.get("content", "")


def _poll(http, keyword, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            data = requests.get(f"http://127.0.0.1:{http}/messages", timeout=5).json()
            msgs = data if isinstance(data, list) else data.get("messages", [])
            for m in msgs:
                if keyword in _msg_text(m):
                    return m
        except Exception:
            pass
        time.sleep(0.4)
    return None


# ── BH1–BH3: capability / endpoint flags ─────────────────────────────────────

def test_BH1_peers_broadcast_subset_capability():
    """BH1: AgentCard declares capabilities.peers_broadcast_subset=True (v2.23)."""
    _wait_link(HTTP_A)
    card = requests.get(f"http://127.0.0.1:{HTTP_A}/.well-known/acp.json", timeout=5).json()
    caps = (card.get("self") or card).get("capabilities", {})
    assert caps.get("peers_broadcast_subset") is True, f"peers_broadcast_subset missing: {caps}"


def test_BH2_peers_broadcast_history_capability():
    """BH2: AgentCard declares capabilities.peers_broadcast_history=True (v2.23)."""
    _wait_link(HTTP_A)
    card = requests.get(f"http://127.0.0.1:{HTTP_A}/.well-known/acp.json", timeout=5).json()
    caps = (card.get("self") or card).get("capabilities", {})
    assert caps.get("peers_broadcast_history") is True, f"peers_broadcast_history missing: {caps}"


def test_BH3_peers_broadcast_history_endpoint():
    """BH3: endpoints.peers_broadcast_history = '/peers/broadcast/history'."""
    _wait_link(HTTP_A)
    card = requests.get(f"http://127.0.0.1:{HTTP_A}/.well-known/acp.json", timeout=5).json()
    eps = (card.get("self") or card).get("endpoints", {})
    assert eps.get("peers_broadcast_history") == "/peers/broadcast/history", \
        f"endpoint missing: {eps}"


# ── BH4: history empty on fresh relay ────────────────────────────────────────

def test_BH4_history_empty_on_start():
    """BH4: GET /peers/broadcast/history returns empty list initially."""
    _wait_link(HTTP_A)
    r = requests.get(f"http://127.0.0.1:{HTTP_A}/peers/broadcast/history", timeout=5)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    body = r.json()
    assert body.get("ok") is True
    assert isinstance(body.get("history"), list)
    assert body["total"] == 0, f"Expected 0 history entries, got {body['total']}"


# ── BH5–BH7: history populated after broadcast ───────────────────────────────

def _wait_peer_connected(http, peer_id, timeout=15):
    """Poll /peers until peer_id appears as connected (BUG-057 fix)."""
    if not peer_id:
        return False
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"http://127.0.0.1:{http}/peers", timeout=3).json()
            for p in r.get("peers", []):
                if p.get("id") == peer_id and p.get("connected"):
                    return True
        except Exception:
            pass
        time.sleep(0.4)
    return False


@pytest.fixture(scope="module")
def two_peers_bc():
    """Connect B and C to A for BH5-BH10. (BUG-057: poll for actual connection)"""
    _wait_link(HTTP_B)
    _wait_link(HTTP_C)
    lb = _link(HTTP_B)
    lc = _link(HTTP_C)
    assert lb, "B link unavailable"
    assert lc, "C link unavailable"
    rb = requests.post(f"http://127.0.0.1:{HTTP_A}/peers/connect",
                       json={"link": lb}, timeout=10).json()
    b_id = rb.get("peer_id")
    # If already_connected, peer is already registered as connected
    if not rb.get("already_connected"):
        _wait_peer_connected(HTTP_A, b_id, timeout=20)

    rc = requests.post(f"http://127.0.0.1:{HTTP_A}/peers/connect",
                       json={"link": lc}, timeout=10).json()
    c_id = rc.get("peer_id")
    if not rc.get("already_connected"):
        _wait_peer_connected(HTTP_A, c_id, timeout=20)

    # Final check: verify at least one peer is connected before proceeding
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            r = requests.get(f"http://127.0.0.1:{HTTP_A}/peers", timeout=3).json()
            active = [p for p in r.get("peers", []) if p.get("connected")]
            if active:
                break
        except Exception:
            pass
        time.sleep(0.5)

    return b_id, c_id


def test_BH5_broadcast_populates_history(two_peers_bc):
    """BH5: POST /peers/broadcast records entry in /peers/broadcast/history."""
    requests.post(f"http://127.0.0.1:{HTTP_A}/peers/broadcast",
                  json={"text": "BH5_history_test", "role": "agent"}, timeout=5)
    r = requests.get(f"http://127.0.0.1:{HTTP_A}/peers/broadcast/history", timeout=5)
    body = r.json()
    assert body["total"] >= 1, f"history not populated: {body}"
    entry = body["history"][0]
    assert "broadcast_id" in entry, f"broadcast_id missing from entry: {entry}"
    assert "ts" in entry, f"ts missing from entry: {entry}"
    assert "delivered" in entry, f"delivered missing from entry: {entry}"
    assert "failed" in entry, f"failed missing from entry: {entry}"


def test_BH6_broadcast_id_in_response(two_peers_bc):
    """BH6: POST /peers/broadcast response includes broadcast_id."""
    r = requests.post(f"http://127.0.0.1:{HTTP_A}/peers/broadcast",
                      json={"text": "BH6_id_check", "role": "agent"}, timeout=5)
    body = r.json()
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {body}"
    assert "broadcast_id" in body, f"broadcast_id missing from response: {body}"
    assert isinstance(body["broadcast_id"], str) and len(body["broadcast_id"]) > 0


def test_BH7_history_limit_param(two_peers_bc):
    """BH7: GET /peers/broadcast/history?limit=1 returns at most 1 entry."""
    # Ensure at least 2 entries exist
    for i in range(2):
        requests.post(f"http://127.0.0.1:{HTTP_A}/peers/broadcast",
                      json={"text": f"BH7_padding_{i}", "role": "agent"}, timeout=5)
    r = requests.get(f"http://127.0.0.1:{HTTP_A}/peers/broadcast/history?limit=1", timeout=5)
    body = r.json()
    assert len(body["history"]) == 1, f"Expected 1 entry with limit=1, got: {len(body['history'])}"


# ── BH8–BH10: target_peers subset broadcast ──────────────────────────────────

def test_BH8_target_peers_empty_503(two_peers_bc):
    """BH8: target_peers=[] (no valid peers selected) → 503 ERR_NO_PEERS."""
    r = requests.post(f"http://127.0.0.1:{HTTP_A}/peers/broadcast",
                      json={"text": "BH8_empty_target", "role": "agent",
                            "target_peers": []}, timeout=5)
    assert r.status_code == 503, f"Expected 503, got {r.status_code}: {r.json()}"
    assert r.json().get("error_code") == "ERR_NO_PEERS"


def test_BH9_target_peers_unknown_400(two_peers_bc):
    """BH9: target_peers with unknown peer_id → 400 ERR_INVALID_REQUEST."""
    r = requests.post(f"http://127.0.0.1:{HTTP_A}/peers/broadcast",
                      json={"text": "BH9_unknown", "role": "agent",
                            "target_peers": ["nonexistent_peer_xyz"]}, timeout=5)
    assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.json()}"
    assert r.json().get("error_code") == "ERR_INVALID_REQUEST"


def test_BH10_target_peers_subset_delivery(two_peers_bc):
    """BH10: target_peers=[B] — only B receives, verify via B messages."""
    peer_b_id, peer_c_id = two_peers_bc
    assert peer_b_id, "B peer_id not available"

    r = requests.post(f"http://127.0.0.1:{HTTP_A}/peers/broadcast",
                      json={"text": "BH10_b_only", "role": "agent",
                            "target_peers": [peer_b_id]}, timeout=5)
    body = r.json()
    assert r.status_code == 200, f"Expected 200: {body}"
    assert body.get("total_peers") == 1, f"Expected total_peers=1: {body}"

    # B should receive it
    msg_b = _poll(HTTP_B, "BH10_b_only", timeout=10)
    assert msg_b is not None, "B did not receive subset broadcast"

    # C should NOT receive it (wait 3s and check)
    msg_c = _poll(HTTP_C, "BH10_b_only", timeout=3)
    assert msg_c is None, f"C received message it should not have: {msg_c}"


# ── BH11: version ─────────────────────────────────────────────────────────────

def test_BH11_version_2_23():
    """BH11: Server reports VERSION 2.23+ (forward compatible)."""
    _wait_link(HTTP_A)
    r = requests.get(f"http://127.0.0.1:{HTTP_A}/status", timeout=5).json()
    ver = r.get("acp_version") or r.get("v") or ""
    major, minor = ver.split(".")[:2]
    assert (int(major), int(minor)) >= (2, 23), f"Expected 2.23+, got: {ver}"
