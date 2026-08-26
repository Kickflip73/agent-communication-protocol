"""
tests/test_peer_trust.py — PT1–PT10
v2.34: GET /peers/<peer_id>/trust — structured per-peer trust score

Test matrix:
  PT1  — capability declared in AgentCard
  PT2  — endpoint declared in AgentCard
  PT3  — unknown peer → 404 ERR_PEER_NOT_FOUND
  PT4  — known peer, no ping/msgs → zero message_hist + ping_rtt scores
  PT5  — card_sig dimension: present, score in {0.0, 1.0}, has detail/weight
  PT6  — ping_rtt scoring: send a ping, verify score scaling
  PT7  — message_hist scoring: match score to messages_sent value
  PT8  — trust_level: high/medium/low classification matches trust_score
  PT9  — response schema: all required top-level + dimension fields present
  PT10 — trust_score == weighted sum of dimension scores (±0.001 tolerance)
"""

import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest

RELAY = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")


# ─── helpers ────────────────────────────────────────────────────────────────

def _free_port_pair():
    """Find a ws_port such that both ws_port and ws_port+100 (http_port) are free."""
    for _ in range(50):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            ws = s.getsockname()[1]
        # Check that ws+100 is also free
        try:
            with socket.socket() as s2:
                s2.bind(("127.0.0.1", ws + 100))
            return ws
        except OSError:
            continue
    raise RuntimeError("Could not find free port pair")


def _free_port():
    return _free_port_pair()


def _wait_ready(base, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"{base}/.well-known/acp.json", timeout=1)
            return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError(f"relay at {base} did not become ready within {timeout}s")


def _get(base, path):
    with urllib.request.urlopen(f"{base}{path}", timeout=8) as r:
        return json.loads(r.read())


def _post(base, path, body=None):
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(
        f"{base}{path}",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _start_relay(ws_port, name, extra_args=None):
    """Start a relay subprocess. Drains stdout/stderr in background threads."""
    env = os.environ.copy()
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        env.pop(k, None)
    cmd = [sys.executable, RELAY, "--port", str(ws_port), "--name", name]
    if extra_args:
        cmd.extend(extra_args)
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    for stream in (proc.stdout, proc.stderr):
        threading.Thread(target=lambda s=stream: s.read(), daemon=True).start()
    http_port = ws_port + 100
    base = f"http://127.0.0.1:{http_port}"
    _wait_ready(base)
    return proc, base


def _stop_relay(proc, timeout=8):
    if proc and proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


# ─── fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def relay_a():
    ws_port = _free_port()
    proc, base = _start_relay(ws_port, "pt-main")
    yield base
    proc.terminate()
    proc.wait()


@pytest.fixture(scope="module")
def relay_pair():
    """
    Two relays: Alpha (host) + Beta (--join Alpha).
    Yields (base_a, base_b, peer_id_of_beta_in_alpha).
    """
    ws_a = _free_port_pair()
    ws_b = _free_port_pair()
    a_http = ws_a + 100

    # Start Alpha
    proc_a, base_a = _start_relay(ws_a, "pt-alpha")

    # Get Alpha's link from /status
    alpha_link = None
    for _ in range(120):
        try:
            data = _get(base_a, "/status")
            if data.get("link"):
                alpha_link = data["link"]
                break
        except Exception:
            pass
        time.sleep(0.5)

    if not alpha_link:
        # Fallback: build local link from session_id
        try:
            data = _get(base_a, "/status")
            token = data.get("session_id") or "test_tok"
        except Exception:
            token = "test_tok"
        alpha_link = f"acp://127.0.0.1:{ws_a}/{token}"

    # Start Beta, joining Alpha
    proc_b, base_b = _start_relay(ws_b, "pt-beta", extra_args=["--join", alpha_link])

    # Wait for Alpha to see Beta as a connected peer
    peer_id = None
    for _ in range(80):
        try:
            data = _get(base_a, "/peers")
            peers = [p for p in data.get("peers", []) if p.get("connected")]
            if peers:
                peer_id = peers[0]["id"]
                break
        except Exception:
            pass
        time.sleep(0.5)

    assert peer_id, "Alpha never saw Beta as a connected peer"

    # Give time for AgentCard exchange
    time.sleep(0.5)

    yield base_a, base_b, peer_id

    _stop_relay(proc_b)
    _stop_relay(proc_a)


# ─── PT1: capability declared ────────────────────────────────────────────────

def test_pt1_capability_declared(relay_a):
    card = _get(relay_a, "/.well-known/acp.json")
    # AgentCard structure: {self: {capabilities: {...}}}
    caps = card.get("self", card).get("capabilities", {})
    assert caps.get("peer_trust") is True, f"peer_trust not in capabilities: {caps}"


# ─── PT2: endpoint declared ──────────────────────────────────────────────────

def test_pt2_endpoint_declared(relay_a):
    card = _get(relay_a, "/.well-known/acp.json")
    endpoints = card.get("self", card).get("endpoints", {})
    assert "peer_trust" in endpoints, f"peer_trust not in endpoints: {endpoints}"
    assert "/trust" in endpoints["peer_trust"], f"trust endpoint wrong: {endpoints['peer_trust']}"


# ─── PT3: unknown peer → 404 ─────────────────────────────────────────────────

def test_pt3_unknown_peer_404(relay_a):
    try:
        _get(relay_a, "/peers/nonexistent-peer-xyz/trust")
        pytest.fail("Expected 404")
    except urllib.error.HTTPError as e:
        assert e.code == 404
        body = json.loads(e.read())
        assert body.get("ok") is False
        assert "ERR_PEER_NOT_FOUND" in body.get("error_code", "")


# ─── PT4: known peer with no ping/msgs → zeros ───────────────────────────────

def test_pt4_known_peer_zero_scores(relay_pair):
    base_a, _base_b, peer_id = relay_pair
    resp = _get(base_a, f"/peers/{peer_id}/trust")
    assert resp["ok"] is True
    dims = resp["dimensions"]
    # No messages sent yet, no ping yet
    assert dims["message_hist"]["score"] == 0.0, f"Expected 0.0, got {dims['message_hist']['score']}"
    assert dims["ping_rtt"]["score"] == 0.0, f"Expected 0.0, got {dims['ping_rtt']['score']}"
    assert dims["ping_rtt"]["last_ping_rtt_ms"] is None
    assert dims["ping_rtt"]["ping_count"] == 0


# ─── PT5: card_sig dimension has proper structure ────────────────────────────

def test_pt5_card_sig_dimension(relay_pair):
    base_a, _base_b, peer_id = relay_pair
    resp = _get(base_a, f"/peers/{peer_id}/trust")
    assert resp["ok"] is True
    dims = resp["dimensions"]
    d = dims["card_sig"]
    assert d["score"] in (0.0, 1.0), f"card_sig score should be 0.0 or 1.0, got {d['score']}"
    assert "detail" in d, "card_sig missing 'detail'"
    assert "weight" in d, "card_sig missing 'weight'"
    assert abs(d["weight"] - 0.35) < 0.001, f"Expected weight 0.35, got {d['weight']}"


# ─── PT6: ping_rtt scoring after a real ping ─────────────────────────────────

def test_pt6_ping_rtt_scoring(relay_pair):
    base_a, _base_b, peer_id = relay_pair
    # Attempt a ping to populate RTT data
    status, ping_resp = _post(base_a, f"/peers/{peer_id}/ping", {"timeout": 3.0})
    rtt = ping_resp.get("rtt_ms") if status == 200 else None

    resp = _get(base_a, f"/peers/{peer_id}/trust")
    dims = resp["dimensions"]
    rtt_dim = dims["ping_rtt"]

    if rtt is not None:
        # Verify the score matches the RTT buckets
        if rtt < 50:
            expected_score = 1.0
        elif rtt < 200:
            expected_score = 0.7
        elif rtt < 500:
            expected_score = 0.4
        else:
            expected_score = 0.1
        assert abs(rtt_dim["score"] - expected_score) < 0.001, \
            f"RTT={rtt}ms → expected score {expected_score}, got {rtt_dim['score']}"
        assert rtt_dim["last_ping_rtt_ms"] is not None
        assert rtt_dim["ping_count"] >= 1
    else:
        # Ping failed (WS not stable), score should be 0.0
        assert rtt_dim["score"] == 0.0


# ─── PT7: message_hist scoring ───────────────────────────────────────────────

def test_pt7_message_hist_scoring(relay_pair):
    base_a, _base_b, peer_id = relay_pair
    resp = _get(base_a, f"/peers/{peer_id}/trust")
    dims = resp["dimensions"]
    msgs = dims["message_hist"]["messages_sent"]
    score = dims["message_hist"]["score"]

    if msgs >= 100:
        assert score == 1.0
    elif msgs >= 20:
        assert score == 0.7
    elif msgs >= 5:
        assert score == 0.4
    elif msgs > 0:
        assert score == 0.2
    else:
        assert score == 0.0

    assert f"{msgs}" in dims["message_hist"]["detail"], \
        f"detail should mention message count: {dims['message_hist']['detail']}"


# ─── PT8: trust_level classification ─────────────────────────────────────────

def test_pt8_trust_level_classification(relay_pair):
    base_a, _base_b, peer_id = relay_pair
    resp = _get(base_a, f"/peers/{peer_id}/trust")
    score = resp["trust_score"]
    level = resp["trust_level"]

    if score >= 0.75:
        assert level == "high", f"score {score} should be 'high', got '{level}'"
    elif score >= 0.45:
        assert level == "medium", f"score {score} should be 'medium', got '{level}'"
    else:
        assert level == "low", f"score {score} should be 'low', got '{level}'"


# ─── PT9: response schema completeness ───────────────────────────────────────

def test_pt9_response_schema(relay_pair):
    base_a, _base_b, peer_id = relay_pair
    resp = _get(base_a, f"/peers/{peer_id}/trust")

    required_top = {"ok", "peer_id", "name", "connected", "trust_score", "trust_level",
                    "dimensions", "evaluated_at"}
    missing_top = required_top - resp.keys()
    assert not missing_top, f"Missing top-level fields: {missing_top}"

    required_dims = {"card_sig", "did_consistent", "ping_rtt", "message_hist", "vouch"}
    missing_dims = required_dims - resp["dimensions"].keys()
    assert not missing_dims, f"Missing dimension keys: {missing_dims}"

    for dim_name, dim in resp["dimensions"].items():
        assert "score" in dim,  f"Dimension '{dim_name}' missing 'score'"
        assert "weight" in dim, f"Dimension '{dim_name}' missing 'weight'"
        assert "detail" in dim, f"Dimension '{dim_name}' missing 'detail'"
        assert 0.0 <= dim["score"] <= 1.0, \
            f"Dimension '{dim_name}' score={dim['score']} out of [0, 1]"

    assert resp["peer_id"] == peer_id
    assert isinstance(resp["trust_score"], float)
    assert resp["trust_level"] in ("high", "medium", "low")


# ─── PT10: trust_score == weighted sum of dimension scores ───────────────────

def test_pt10_trust_score_is_weighted_sum(relay_pair):
    base_a, _base_b, peer_id = relay_pair
    resp = _get(base_a, f"/peers/{peer_id}/trust")
    dims = resp["dimensions"]

    weights = {"card_sig": 0.35, "did_consistent": 0.20,
               "ping_rtt": 0.20, "message_hist": 0.15, "vouch": 0.10}
    expected = sum(dims[k]["score"] * weights[k] for k in weights)
    actual = resp["trust_score"]

    assert abs(actual - round(expected, 4)) < 0.001, \
        f"trust_score {actual} != weighted sum {expected:.4f}; dims={dims}"
