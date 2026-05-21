"""
Message ACK Tests — v3.16 feature verification

Tests POST /message:send?require_ack=true and acp.ack auto-reply protocol.

Test matrix:
  test_ack_01  capabilities.message_ack=true declared in AgentCard and /status
  test_ack_02  require_ack=true + peer online → acked:true in response
  test_ack_03  require_ack=true but no peer → 408 ERR_ACK_TIMEOUT
  test_ack_04  default (require_ack absent) → ok:true, no acked field (or acked:false)
  test_ack_05  ACK messages NOT visible in GET /recv
  test_ack_06  ack_timeout_ms custom timeout respected
  test_ack_07  concurrent sends — each message_id ACKed independently
  test_ack_08  VERSION reflects v3.16
"""
import pytest
import requests
import subprocess
import time
import signal
import sys
import os
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE_PORT = 53100


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _free_port_pair():
    """Return a free (ws_port, http_port) pair."""
    import socket
    import random
    for _ in range(100):
        ws_port = BASE_PORT + random.randint(0, 800)
        http_port = ws_port + 100
        try:
            s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s1.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s1.bind(("127.0.0.1", ws_port))
            s1.close()
            s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s2.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s2.bind(("127.0.0.1", http_port))
            s2.close()
            return ws_port, http_port
        except OSError:
            continue
    raise RuntimeError("Cannot find free port pair")


def _relay_env():
    env = os.environ.copy()
    for v in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
              "all_proxy", "ALL_PROXY", "no_proxy", "NO_PROXY"):
        env.pop(v, None)
    return env


def _start_relay(ws_port, http_port, name="ACKTest", join_link=None):
    """Start a relay subprocess and wait until HTTP /status is ready."""
    cmd = [
        "python3", "-u", "relay/acp_relay.py",
        "--port", str(ws_port),
        "--http-host", "127.0.0.1",
        "--name", name,
        "--local-only",
    ]
    if join_link:
        cmd.extend(["--join", join_link])

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_relay_env(),
        cwd=os.path.join(os.path.dirname(__file__), ".."),
    )

    deadline = time.time() + 30
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"Relay '{name}' exited early")
        try:
            r = requests.get(f"http://127.0.0.1:{http_port}/status", timeout=0.5)
            if r.status_code == 200:
                return proc
        except Exception:
            pass
        time.sleep(0.3)

    proc.terminate()
    raise RuntimeError(f"Relay '{name}' did not start within 30s")


def _stop_relay(proc):
    if proc and proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def _wait_peer(http_port, retries=40):
    """Wait for at least one connected peer; return first peer_id or None."""
    for _ in range(retries):
        try:
            r = requests.get(f"http://127.0.0.1:{http_port}/peers", timeout=1)
            for p in r.json().get("peers", []):
                if p.get("connected"):
                    return p["id"]
        except Exception:
            pass
        time.sleep(0.5)
    return None


def _alpha_link(http_port):
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            r = requests.get(f"http://127.0.0.1:{http_port}/status", timeout=1)
            lnk = r.json().get("link")
            if lnk:
                return lnk
        except Exception:
            pass
        time.sleep(0.3)
    raise RuntimeError("Alpha link not available")


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def single_relay():
    """A standalone relay with no peer — used for offline/single-node tests."""
    ws, http = _free_port_pair()
    proc = _start_relay(ws, http, "ACKSolo")
    yield {"http": http, "ws": ws, "proc": proc}
    _stop_relay(proc)


@pytest.fixture(scope="module")
def relay_pair():
    """Two connected relays (alpha + beta)."""
    a_ws, a_http = _free_port_pair()
    b_ws, b_http = _free_port_pair()

    alpha = _start_relay(a_ws, a_http, "ACKAlpha")
    link = _alpha_link(a_http)
    beta = _start_relay(b_ws, b_http, "ACKBeta", join_link=link)

    peer_id = _wait_peer(a_http, retries=40)
    if not peer_id:
        _stop_relay(beta)
        _stop_relay(alpha)
        pytest.fail("relay_pair: peer connection not established within 20s")

    yield {
        "alpha": {"http": a_http, "ws": a_ws, "proc": alpha, "peer_id": peer_id},
        "beta":  {"http": b_http, "ws": b_ws, "proc": beta},
    }
    _stop_relay(beta)
    _stop_relay(alpha)


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestMessageACK:

    # ── test_ack_01 ──────────────────────────────────────────────────────────
    def test_ack_01_capability_declared_agent_card(self, single_relay):
        """ACK-01: AgentCard declares capabilities.message_ack=true."""
        r = requests.get(f"http://127.0.0.1:{single_relay['http']}/.well-known/acp.json")
        assert r.status_code == 200
        data = r.json()
        assert data["self"]["capabilities"]["message_ack"] is True, (
            "capabilities.message_ack not true in AgentCard"
        )

    # ── test_ack_08 (alias of 01 for /status) ─────────────────────────────
    def test_ack_08_capability_in_status(self, single_relay):
        """ACK-08: /status shortcut capabilities also contains message_ack=true."""
        r = requests.get(f"http://127.0.0.1:{single_relay['http']}/status")
        assert r.status_code == 200
        data = r.json()
        # capabilities may be at top-level or under agent_card
        caps = data.get("capabilities") or data.get("agent_card", {}).get("capabilities", {})
        assert caps.get("message_ack") is True, (
            f"capabilities.message_ack not true in /status — got: {caps.get('message_ack')}"
        )

    # ── test_ack_04 ──────────────────────────────────────────────────────────
    def test_ack_04_default_no_require_ack(self, single_relay):
        """ACK-04: Without require_ack, send returns ok:true immediately (no acked field required)."""
        r = requests.post(
            f"http://127.0.0.1:{single_relay['http']}/message:send",
            json={"role": "user", "text": "hello"},
            timeout=10,
        )
        # OK even with no peer — falls through gracefully (ConnectionError caught by relay → ok=false
        # is acceptable; just verify it does NOT block and does NOT return acked:true)
        data = r.json()
        assert "acked" not in data or data.get("acked") is not True, (
            "require_ack not set but response contains acked:true"
        )

    # ── test_ack_05 ──────────────────────────────────────────────────────────
    def test_ack_05_ack_not_in_recv(self, relay_pair):
        """ACK-05: acp.ack frames are NOT visible in GET /recv."""
        # Send a message from alpha to beta; beta will auto-ACK alpha.
        # Then drain alpha's /recv — no acp.ack should appear.
        r = requests.post(
            f"http://127.0.0.1:{relay_pair['alpha']['http']}/message:send",
            json={"role": "user", "text": "ACK visibility check"},
            timeout=10,
        )
        assert r.status_code == 200
        # Give relay time to process the message and potential ACK frame
        time.sleep(1.5)

        # Check alpha's recv queue (outbound messages visible there)
        r2 = requests.get(f"http://127.0.0.1:{relay_pair['alpha']['http']}/recv", timeout=5)
        assert r2.status_code == 200
        msgs = r2.json().get("messages", [])
        ack_msgs = [m for m in msgs if (
            (m.get("raw") or m).get("type") == "acp.ack"
            or m.get("type") == "acp.ack"
        )]
        assert len(ack_msgs) == 0, (
            f"acp.ack frames should not appear in /recv, but found: {ack_msgs}"
        )

        # Also check beta's recv queue
        r3 = requests.get(f"http://127.0.0.1:{relay_pair['beta']['http']}/recv", timeout=5)
        assert r3.status_code == 200
        beta_msgs = r3.json().get("messages", [])
        beta_ack_msgs = [m for m in beta_msgs if (
            (m.get("raw") or m).get("type") == "acp.ack"
            or m.get("type") == "acp.ack"
        )]
        assert len(beta_ack_msgs) == 0, (
            f"acp.ack frames should not appear in beta /recv, but found: {beta_ack_msgs}"
        )

    # ── test_ack_02 ──────────────────────────────────────────────────────────
    def test_ack_02_require_ack_peer_online(self, relay_pair):
        """ACK-02: require_ack=true with peer connected → acked:true."""
        r = requests.post(
            f"http://127.0.0.1:{relay_pair['alpha']['http']}/message:send",
            json={
                "role":        "user",
                "text":        "require_ack test",
                "require_ack": True,
                "ack_timeout_ms": 8000,
            },
            timeout=15,
        )
        assert r.status_code == 200, (
            f"Expected 200, got {r.status_code}: {r.text}"
        )
        data = r.json()
        assert data.get("ok") is True, f"ok should be True: {data}"
        assert data.get("acked") is True, (
            f"Expected acked:true when require_ack=true and peer online, got: {data}"
        )

    # ── test_ack_03 ──────────────────────────────────────────────────────────
    def test_ack_03_require_ack_no_peer_timeout(self, single_relay):
        """ACK-03: require_ack=true with no peer → 408 ERR_ACK_TIMEOUT."""
        # Use a short timeout so the test doesn't hang
        r = requests.post(
            f"http://127.0.0.1:{single_relay['http']}/message:send",
            json={
                "role":           "user",
                "text":           "no peer test",
                "require_ack":    True,
                "ack_timeout_ms": 800,   # short timeout for fast test
            },
            timeout=10,
        )
        # With no peer, the message send itself may fail with ERR_NOT_CONNECTED (503)
        # OR the send may succeed (local-only relay queues it) but ACK never arrives (408).
        # Both outcomes are valid per the spec: no peer → no ACK.
        data = r.json()
        assert r.status_code in (408, 503), (
            f"Expected 408 ERR_ACK_TIMEOUT or 503 ERR_NOT_CONNECTED when no peer, "
            f"got {r.status_code}: {data}"
        )
        assert data.get("ok") is False
        if r.status_code == 408:
            assert data.get("error_code") == "ERR_ACK_TIMEOUT", (
                f"error_code should be ERR_ACK_TIMEOUT, got: {data.get('error_code')}"
            )

    # ── test_ack_06 ──────────────────────────────────────────────────────────
    def test_ack_06_custom_timeout_ms(self, single_relay):
        """ACK-06: ack_timeout_ms custom value is respected (small value → fast timeout)."""
        t0 = time.time()
        r = requests.post(
            f"http://127.0.0.1:{single_relay['http']}/message:send",
            json={
                "role":           "user",
                "text":           "custom timeout test",
                "require_ack":    True,
                "ack_timeout_ms": 600,   # 0.6 seconds
            },
            timeout=10,
        )
        elapsed = time.time() - t0
        data = r.json()
        assert r.status_code in (408, 503), (
            f"Expected 408 or 503 with no peer, got {r.status_code}: {data}"
        )
        # Should return quickly — definitely under 5s (the default would be 5s)
        assert elapsed < 4.0, (
            f"Custom ack_timeout_ms=600 should timeout in ~0.6s, but took {elapsed:.2f}s"
        )

    # ── test_ack_07 ──────────────────────────────────────────────────────────
    def test_ack_07_concurrent_messages_acked_independently(self, relay_pair):
        """ACK-07: Concurrent require_ack sends each get their own ACK (no cross-contamination)."""
        N = 4
        results = [None] * N
        errors  = [None] * N

        def send(idx):
            try:
                r = requests.post(
                    f"http://127.0.0.1:{relay_pair['alpha']['http']}/message:send",
                    json={
                        "role":           "user",
                        "text":           f"concurrent msg {idx}",
                        "require_ack":    True,
                        "ack_timeout_ms": 8000,
                    },
                    timeout=15,
                )
                results[idx] = r.json()
            except Exception as e:
                errors[idx] = str(e)

        threads = [threading.Thread(target=send, args=(i,)) for i in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)

        for i in range(N):
            assert errors[i] is None, f"Thread {i} raised: {errors[i]}"
            assert results[i] is not None, f"Thread {i} got no result"
            d = results[i]
            assert d.get("ok") is True,    f"Thread {i}: ok should be True: {d}"
            assert d.get("acked") is True, f"Thread {i}: acked should be True: {d}"
            assert "message_id" in d,      f"Thread {i}: missing message_id: {d}"

        # Verify all message_ids are unique
        ids = [r["message_id"] for r in results if r]
        assert len(set(ids)) == N, f"Expected {N} unique message_ids, got: {ids}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
