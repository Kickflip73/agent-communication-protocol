"""
test_client_msg_id_v284.py — v2.84 client_msg_id idempotency key tests

Tests:
  CM1: client_msg_id echoed in response
  CM2: same client_msg_id within 30s → deduplicated=True
  CM3: message_id field also works as idempotency key
  CM4: auto-generated IDs (no key) never deduplicated

Ports: WS 17700, HTTP 17800
"""

import sys, os, time, signal, subprocess, requests, pytest

RELAY = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")

WS_A, HTTP_A = 17700, 17800
WS_B, HTTP_B = 17701, 17801

_procs: dict = {}


def _free_port(port):
    import re as _re
    try:
        out = subprocess.check_output(["ss", "-tlnp"], text=True, stderr=subprocess.DEVNULL, timeout=2)
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


def _start(ws_port, name, wait=25):
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
                return proc
        except Exception:
            pass
    proc.kill()
    raise RuntimeError(f"{name} not ready within {wait}s")


def _get_peer_id(http_port):
    r = requests.get(f"http://127.0.0.1:{http_port}/status", timeout=5)
    d = r.json()
    return d.get("peer_id") or d.get("session_id") or d.get("agent_id")


def setup_module(_):
    _procs["A"] = _start(WS_A, "CMAgentA")
    _procs["B"] = _start(WS_B, "CMAgentB")


def teardown_module(_):
    for p in _procs.values():
        try:
            p.kill()
        except Exception:
            pass


# ── helpers ──────────────────────────────────────────────────────────────────

def _connect_peers():
    """Get A's link and connect B to A."""
    st_a = requests.get(f"http://127.0.0.1:{HTTP_A}/status", timeout=5).json()
    link = st_a.get("link") or st_a.get("acp_link")
    if not link:
        pytest.skip("Relay A has no link (local-only, need join workaround)")
    # POST to B: join A
    requests.post(f"http://127.0.0.1:{HTTP_B}/join", json={"link": link}, timeout=5)
    time.sleep(2)
    # Get B's peer_id as seen by A
    peers_a = requests.get(f"http://127.0.0.1:{HTTP_A}/peers", timeout=5).json()
    peer_list = peers_a if isinstance(peers_a, list) else peers_a.get("peers", [])
    if not peer_list:
        pytest.skip("No peers connected to A")
    peer_id = peer_list[0] if isinstance(peer_list[0], str) else peer_list[0].get("peer_id", "")
    return peer_id


def _send(http_port, peer_id, content, extra=None):
    body = {"parts": [{"type": "text", "content": content}]}
    if extra:
        body.update(extra)
    r = requests.post(
        f"http://127.0.0.1:{http_port}/peer/{peer_id}/send",
        json=body, timeout=5
    )
    return r.json(), r.status_code


# ── tests ──────────────────────────────────────────────────────────────────────

def test_CM1_client_msg_id_echo():
    """CM1: client_msg_id is echoed in response."""
    peer_id = _connect_peers()
    resp, code = _send(HTTP_A, peer_id, "hello cm1", extra={"client_msg_id": "cm1-key-001"})
    assert code == 200, f"Unexpected status: {code} — {resp}"
    assert resp.get("ok") is True
    assert resp.get("client_msg_id") == "cm1-key-001", f"Expected echo of client_msg_id, got: {resp}"


def test_CM2_deduplication():
    """CM2: Same client_msg_id within 30s returns deduplicated=True."""
    peer_id = _connect_peers()
    resp1, code1 = _send(HTTP_A, peer_id, "first cm2", extra={"client_msg_id": "cm2-dedup-key"})
    assert code1 == 200
    assert resp1.get("ok") is True
    assert resp1.get("deduplicated") is not True, f"First send should NOT be deduped: {resp1}"

    resp2, code2 = _send(HTTP_A, peer_id, "second cm2 same key", extra={"client_msg_id": "cm2-dedup-key"})
    assert code2 == 200
    assert resp2.get("deduplicated") is True, f"Second send SHOULD be deduped: {resp2}"


def test_CM3_message_id_as_alias():
    """CM3: message_id field works as idempotency key alias."""
    peer_id = _connect_peers()
    resp1, _ = _send(HTTP_A, peer_id, "cm3 first", extra={"message_id": "cm3-mid-key"})
    assert resp1.get("ok") is True
    assert resp1.get("client_msg_id") == "cm3-mid-key", f"Expected message_id echoed as client_msg_id: {resp1}"

    resp2, _ = _send(HTTP_A, peer_id, "cm3 second", extra={"message_id": "cm3-mid-key"})
    assert resp2.get("deduplicated") is True, f"Should dedup on same message_id: {resp2}"


def test_CM4_auto_id_no_dedup():
    """CM4: Without client_msg_id, auto-generated IDs never deduplicated."""
    peer_id = _connect_peers()
    resp1, _ = _send(HTTP_A, peer_id, "cm4 auto first")
    resp2, _ = _send(HTTP_A, peer_id, "cm4 auto second")
    assert resp1.get("deduplicated") is not True
    assert resp2.get("deduplicated") is not True
    assert resp1.get("message_id") != resp2.get("message_id"), "Auto IDs should be unique"
