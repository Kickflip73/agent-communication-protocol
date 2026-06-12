"""
Batch Message Send Tests — v3.15 feature verification
Tests POST /messages:batch endpoint for atomic multi-message enqueue.
"""
import pytest
import requests
import subprocess
import time
import signal
import sys
import os

# Add parent dirs to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE_PORT = 52800


def _free_port_pair():
    """Find a free port pair for WS and HTTP."""
    import socket
    while True:
        ws_port = BASE_PORT + (os.getpid() % 1000) + hash(time.time()) % 1000
        http_port = ws_port + 100
        try:
            s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s1.bind(("127.0.0.1", ws_port))
            s1.close()
            s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s2.bind(("127.0.0.1", http_port))
            s2.close()
            return ws_port, http_port
        except OSError:
            continue


def _start_relay(ws_port, http_port, name="BatchTest", join_link=None):
    """Start a relay instance."""
    cmd = [
        sys.executable, "-u", "relay/acp_relay.py",
        "--port", str(ws_port),
        "--http-port", str(http_port),
        "--http-host", "127.0.0.1",
        "--name", name,
        "--local-only",
    ]
    if join_link:
        cmd.extend(["--join", join_link])

    env = os.environ.copy()
    env.pop("http_proxy", None)
    env.pop("https_proxy", None)

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )

    # Wait for HTTP ready
    for _ in range(60):  # 30s timeout
        try:
            r = requests.get(f"http://127.0.0.1:{http_port}/status", timeout=0.5)
            if r.status_code == 200:
                return proc
        except Exception:
            pass
        if proc.poll() is not None:
            out, err = proc.communicate()
            raise RuntimeError(f"Relay {name} exited early.\nstdout: {out}\nstderr: {err}")
        time.sleep(0.5)

    proc.terminate()
    raise RuntimeError(f"Relay {name} did not start within 30s")


def _stop_relay(proc):
    """Stop a relay process."""
    if proc:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def _wait_peer_connected(http_port, retries=20):
    """Wait for at least one peer to be connected."""
    for _ in range(retries):
        try:
            r = requests.get(f"http://127.0.0.1:{http_port}/peers", timeout=1)
            data = r.json()
            if data.get("peers"):
                for p in data["peers"]:
                    if p.get("connected"):
                        return p["id"]
        except Exception:
            pass
        time.sleep(0.5)
    return None


@pytest.fixture(scope="module")
def relay_pair():
    """Create a pair of connected relays for testing."""
    alpha_ws, _ = _free_port_pair()
    beta_ws, _ = _free_port_pair()
    alpha_http = alpha_ws + 100  # HTTP port = WS port + 100
    beta_http = beta_ws + 100

    alpha_proc = _start_relay(alpha_ws, alpha_http, "AlphaBatch")

    # Get Alpha's link
    for _ in range(60):
        try:
            r = requests.get(f"http://127.0.0.1:{alpha_http}/status", timeout=1)
            data = r.json()
            if data.get("link"):
                alpha_link = data["link"]
                break
        except Exception:
            pass
        time.sleep(0.5)
    else:
        _stop_relay(alpha_proc)
        raise RuntimeError("Alpha link not available")

    beta_proc = _start_relay(beta_ws, beta_http, "BetaBatch", join_link=alpha_link)

    # Wait for connection
    peer_id = _wait_peer_connected(alpha_http, retries=30)
    if not peer_id:
        _stop_relay(beta_proc)
        _stop_relay(alpha_proc)
        raise RuntimeError("Peer connection not established")

    yield {
        "alpha": {"http": alpha_http, "ws": alpha_ws, "proc": alpha_proc, "peer_id": peer_id},
        "beta": {"http": beta_http, "ws": beta_ws, "proc": beta_proc},
    }

    _stop_relay(beta_proc)
    _stop_relay(alpha_proc)


class TestBatchMessageSend:
    """v3.15: POST /messages:batch tests"""

    def test_b1_batch_capability_declared(self, relay_pair):
        """B1: AgentCard declares batch_message capability"""
        r = requests.get(f"http://127.0.0.1:{relay_pair['alpha']['http']}/.well-known/acp.json")
        assert r.status_code == 200
        data = r.json()
        assert data["self"]["capabilities"]["batch_message"] is True

    def test_b2_batch_send_basic(self, relay_pair):
        """B2: Basic batch send with 3 messages"""
        payload = {
            "messages": [
                {"role": "user", "text": "Message 1"},
                {"role": "agent", "text": "Message 2"},
                {"role": "user", "text": "Message 3"},
            ]
        }
        r = requests.post(
            f"http://127.0.0.1:{relay_pair['alpha']['http']}/messages:batch",
            json=payload,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["sent"] == 3
        assert data["total"] == 3
        assert len(data["results"]) == 3
        for res in data["results"]:
            assert res["ok"] is True
            assert "message_id" in res
            assert "server_seq" in res

    def test_b3_batch_with_peer_id(self, relay_pair):
        """B3: Batch send with explicit peer_id"""
        peer_id = relay_pair["alpha"]["peer_id"]
        payload = {
            "messages": [
                {"role": "user", "text": "Direct to peer", "peer_id": peer_id},
            ]
        }
        r = requests.post(
            f"http://127.0.0.1:{relay_pair['alpha']['http']}/messages:batch",
            json=payload,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["sent"] == 1

    def test_b4_batch_empty_rejected(self, relay_pair):
        """B4: Empty batch is rejected"""
        payload = {"messages": []}
        r = requests.post(
            f"http://127.0.0.1:{relay_pair['alpha']['http']}/messages:batch",
            json=payload,
        )
        assert r.status_code == 400
        data = r.json()
        assert data["ok"] is False
        assert "error_code" in data

    def test_b5_batch_missing_role_rejected(self, relay_pair):
        """B5: Message missing role is rejected with per-item error"""
        payload = {
            "messages": [
                {"role": "user", "text": "Good message"},
                {"text": "Missing role"},  # No role
            ]
        }
        r = requests.post(
            f"http://127.0.0.1:{relay_pair['alpha']['http']}/messages:batch",
            json=payload,
        )
        assert r.status_code == 200  # Batch itself succeeds
        data = r.json()
        assert data["sent"] == 1
        assert data["total"] == 2
        assert data["results"][0]["ok"] is True
        assert data["results"][1]["ok"] is False
        assert "error" in data["results"][1]

    def test_b6_batch_too_large_rejected(self, relay_pair):
        """B6: Batch >100 messages is rejected"""
        payload = {
            "messages": [{"role": "user", "text": f"Msg {i}"} for i in range(101)]
        }
        r = requests.post(
            f"http://127.0.0.1:{relay_pair['alpha']['http']}/messages:batch",
            json=payload,
        )
        assert r.status_code == 413
        data = r.json()
        assert data["ok"] is False

    def test_b7_batch_atomic_mode(self, relay_pair):
        """B7: Atomic mode reports correctly"""
        payload = {
            "messages": [
                {"role": "user", "text": "Message 1"},
                {"role": "user", "text": "Message 2"},
            ],
            "atomic": True,
        }
        r = requests.post(
            f"http://127.0.0.1:{relay_pair['alpha']['http']}/messages:batch",
            json=payload,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["atomic"] is True
        assert data["ok"] is True  # All succeeded


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
