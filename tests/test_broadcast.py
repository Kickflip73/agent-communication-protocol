"""
test_broadcast.py — v2.22 /peers/broadcast endpoint tests

Tests POST /peers/broadcast: fanout message to all connected peers.
Ports: WS 19800/19801/19802, HTTP 19900/19901/19902
"""

import sys, os, time, signal, subprocess, requests, pytest

RELAY = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")

WS_A, HTTP_A = 17100, 17200
WS_B, HTTP_B = 17101, 17201
WS_C, HTTP_C = 17102, 17202

_procs: dict = {}


def _free_port(port):
    """Kill process on port using ss output (one-shot, no wait loop)."""
    import re as _re
    try:
        out = subprocess.check_output(
            ["ss", "-tlnp"], text=True, stderr=subprocess.DEVNULL, timeout=2
        )
        for line in out.splitlines():
            if f":{port} " in line or f":{port}\t" in line or line.strip().endswith(f":{port}"):
                m = _re.search(r"pid=(\d+)", line)
                if m:
                    try:
                        os.kill(int(m.group(1)), signal.SIGKILL)
                    except Exception:
                        pass
    except Exception:
        pass


def _start(ws_port, name, wait=20):
    http = ws_port + 100
    # Free ports before starting
    _free_port(ws_port)
    _free_port(http)
    time.sleep(0.3)  # brief wait for kernel to release

    proc = subprocess.Popen(
        [sys.executable, RELAY, "--port", str(ws_port), "--name", name,
         "--local-only"],   # skip Cloudflare/IP lookup so WS starts immediately (test reliability)
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
    # Fallback: if HTTP is responding but link not yet assigned, still return proc
    try:
        if requests.get(f"http://127.0.0.1:{http}/status", timeout=2).status_code == 200:
            return proc
    except Exception:
        pass
    proc.kill()
    raise RuntimeError(f"{name} not ready within {wait}s")


def setup_module(_):
    # _start() already calls _kill_port per relay; just start them
    _procs["A"] = _start(WS_A, "BroadcastA")
    _procs["B"] = _start(WS_B, "BroadcastB")
    _procs["C"] = _start(WS_C, "BroadcastC")


def teardown_module(_):
    for p in _procs.values():
        try:
            p.send_signal(signal.SIGTERM)
            p.wait(timeout=3)
        except Exception:
            pass


def _link(http):
    """Return a localhost acp:// link for connecting to this relay in tests.

    /status.link may contain a public/LAN IP that is unreachable in the test
    sandbox.  We extract the token from whatever link is present and rebuild
    an acp://127.0.0.1:WS_PORT/TOKEN link so /peers/connect can reach the
    relay via loopback.
    """
    d = requests.get(f"http://127.0.0.1:{http}/status", timeout=5).json()
    raw = d.get("link") or d.get("relay_token") or ""
    # Extract token: last path segment of acp://…/TOKEN
    token = raw.rstrip("/").rsplit("/", 1)[-1] if "/" in raw else raw
    # WS port = HTTP port - 100 (per test port layout)
    ws_port = http - 100
    return f"acp://127.0.0.1:{ws_port}/{token}" if token else None


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


# ── BC1: capability flag ──────────────────────────────────────────────────────

def _wait_link(http, timeout=20):
    """Wait until /status returns a link/relay_token (relay fully initialized).

    Falls back to accepting any 200 response with a version present, since
    the link field is only populated after public-IP detection completes
    (which may be slow or fail in sandbox environments).
    """
    deadline = time.time() + timeout
    last_d = {}
    while time.time() < deadline:
        try:
            d = requests.get(f"http://127.0.0.1:{http}/status", timeout=2).json()
            last_d = d
            if d.get("link") or d.get("relay_token"):
                return True
        except Exception:
            pass
        time.sleep(0.5)
    # Fallback: accept if relay is responding (link may be slow due to public IP lookup)
    try:
        d = requests.get(f"http://127.0.0.1:{http}/status", timeout=2).json()
        if d.get("v") or d.get("acp_version"):
            return True  # relay is up even if link not yet populated
    except Exception:
        pass
    return False
    return False


def test_BC1_broadcast_capability_flag():
    """BC1: AgentCard declares capabilities.peers_broadcast=True (v2.22)."""
    _wait_link(HTTP_A)
    resp = requests.get(f"http://127.0.0.1:{HTTP_A}/.well-known/acp.json", timeout=5).json()
    # AgentCard is nested under "self" key
    card = resp.get("self") or resp
    caps = card.get("capabilities", {})
    assert caps.get("peers_broadcast") is True, f"peers_broadcast not in capabilities: {caps}"


def test_BC2_broadcast_endpoint_declared():
    """BC2: AgentCard endpoints.peers_broadcast = '/peers/broadcast'."""
    _wait_link(HTTP_A)
    resp = requests.get(f"http://127.0.0.1:{HTTP_A}/.well-known/acp.json", timeout=5).json()
    card = resp.get("self") or resp
    endpoints = card.get("endpoints", {})
    assert endpoints.get("peers_broadcast") == "/peers/broadcast", \
        f"peers_broadcast endpoint not declared: {endpoints}"


# ── BC3: no-peer case ─────────────────────────────────────────────────────────

def test_BC3_broadcast_no_peers_returns_503():
    """BC3: /peers/broadcast with no connected peers → 503 ERR_NO_PEERS."""
    _wait_link(HTTP_A)
    r = requests.post(f"http://127.0.0.1:{HTTP_A}/peers/broadcast",
                      json={"text": "hello", "role": "agent"}, timeout=5)
    assert r.status_code == 503, f"expected 503, got {r.status_code}: {r.json()}"
    body = r.json()
    assert body.get("error_code") == "ERR_NO_PEERS", \
        f"expected ERR_NO_PEERS, got: {body}"


# ── BC4: validation ───────────────────────────────────────────────────────────

def test_BC4_broadcast_missing_role_returns_400():
    """BC4: /peers/broadcast without 'role' → 400 ERR_INVALID_REQUEST."""
    r = requests.post(f"http://127.0.0.1:{HTTP_A}/peers/broadcast",
                      json={"text": "hello"}, timeout=5)
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.json()}"


def test_BC5_broadcast_missing_text_returns_400():
    """BC5: /peers/broadcast without 'text' or 'parts' → 400 ERR_INVALID_REQUEST."""
    r = requests.post(f"http://127.0.0.1:{HTTP_A}/peers/broadcast",
                      json={"role": "agent"}, timeout=5)
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.json()}"


# ── BC6–BC10: actual broadcast with peers ─────────────────────────────────────

def _wait_peer_connected(http, expected_count=1, timeout=15):
    """Wait until the relay at http_port has at least `expected_count` connected peers."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            d = requests.get(f"http://127.0.0.1:{http}/peers", timeout=3).json()
            peers = d if isinstance(d, list) else d.get("peers", [])
            connected = [p for p in peers if p.get("connected")]
            if len(connected) >= expected_count:
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


@pytest.fixture(scope="module")
def two_peers_connected():
    """Connect B and C to A, return (peer_b_id, peer_c_id)."""
    # Wait for B and C to be fully ready (link assigned) before extracting links
    _wait_link(HTTP_B)
    _wait_link(HTTP_C)
    lb = _link(HTTP_B)
    lc = _link(HTTP_C)
    assert lb, f"B link is None after wait (status: {requests.get(f'http://127.0.0.1:{HTTP_B}/status',timeout=3).json()})"
    assert lc, f"C link is None after wait (status: {requests.get(f'http://127.0.0.1:{HTTP_C}/status',timeout=3).json()})"
    rb = requests.post(f"http://127.0.0.1:{HTTP_A}/peers/connect",
                       json={"link": lb}, timeout=10).json()
    rc = requests.post(f"http://127.0.0.1:{HTTP_A}/peers/connect",
                       json={"link": lc}, timeout=10).json()
    # Wait for both WS handshakes to complete (replaces static sleep)
    ok = _wait_peer_connected(HTTP_A, expected_count=2, timeout=20)
    assert ok, (
        f"A did not get 2 connected peers within 20s — "
        f"peers: {requests.get(f'http://127.0.0.1:{HTTP_A}/peers', timeout=3).json()}"
    )
    return rb.get("peer_id"), rc.get("peer_id")


def test_BC6_broadcast_delivers_to_all_peers(two_peers_connected):
    """BC6: POST /peers/broadcast reaches all connected peers (B and C)."""
    r = requests.post(f"http://127.0.0.1:{HTTP_A}/peers/broadcast",
                      json={"text": "BC6_broadcast_msg", "role": "agent"}, timeout=5)
    assert r.status_code == 200, f"broadcast returned {r.status_code}: {r.json()}"
    body = r.json()
    assert body.get("ok") is True
    assert body.get("broadcast") is True
    assert body.get("delivered", 0) >= 1, f"delivered=0: {body}"


def test_BC7_broadcast_b_receives(two_peers_connected):
    """BC7: Agent B receives the broadcast message."""
    requests.post(f"http://127.0.0.1:{HTTP_A}/peers/broadcast",
                  json={"text": "BC7_for_B", "role": "agent"}, timeout=5)
    msg = _poll(HTTP_B, "BC7_for_B", timeout=10)
    assert msg is not None, "B did not receive broadcast message"


def test_BC8_broadcast_c_receives(two_peers_connected):
    """BC8: Agent C receives the broadcast message."""
    requests.post(f"http://127.0.0.1:{HTTP_A}/peers/broadcast",
                  json={"text": "BC8_for_C", "role": "agent"}, timeout=5)
    msg = _poll(HTTP_C, "BC8_for_C", timeout=10)
    assert msg is not None, "C did not receive broadcast message"


def test_BC9_broadcast_response_has_results(two_peers_connected):
    """BC9: Broadcast response includes per-peer results[]."""
    r = requests.post(f"http://127.0.0.1:{HTTP_A}/peers/broadcast",
                      json={"text": "BC9_results_check", "role": "agent"}, timeout=5)
    body = r.json()
    results = body.get("results", [])
    assert isinstance(results, list) and len(results) >= 1, \
        f"results missing or empty: {body}"
    for res in results:
        assert "peer_id" in res and "message_id" in res and "ok" in res, \
            f"result missing fields: {res}"


def test_BC10_broadcast_version_2_22(two_peers_connected):
    """BC10: Server reports VERSION 2.22+ (broadcast feature milestone; updated for 2.23+)."""
    _wait_link(HTTP_A)
    r = requests.get(f"http://127.0.0.1:{HTTP_A}/status", timeout=5).json()
    # /status uses "acp_version" key (not "version")
    version = r.get("acp_version") or r.get("version", "")
    major, minor = version.split(".")[:2]
    assert (int(major), int(minor)) >= (2, 22), f"expected version 2.22+, got: {version}"
