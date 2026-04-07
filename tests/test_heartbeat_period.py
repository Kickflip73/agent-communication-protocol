"""
test_heartbeat_period.py — ACP v2.80 heartbeat_period_ms tests

HP1  No --heartbeat-period-ms: AgentCard has no heartbeat_period_ms field (or null)
HP2  --heartbeat-period-ms 30000: AgentCard.heartbeat_period_ms == 30000
HP3  capabilities.heartbeat_period_declared == True when declared
HP4  capabilities.heartbeat_period_declared absent/False when not declared
HP5  GET /availability returns heartbeat_period_ms == 30000
HP6  POST /availability/heartbeat response includes heartbeat_period_ms == 30000
HP7  heartbeat_period_ms accepts positive integer boundary: 1ms
HP8  heartbeat_period_ms = 60000 (1 min), GET /.well-known/acp.json returns it correctly
HP9  heartbeat_period_ms present in GET /status agent_card field
HP10 No --heartbeat-period-ms: POST /availability/heartbeat response has no heartbeat_period_ms (or None)
"""

import sys
import os
import subprocess
import time
import socket
import json
import urllib.request
import urllib.error
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'relay'))

RELAY_BIN = os.path.join(os.path.dirname(__file__), '..', 'relay', 'acp_relay.py')


# ── Port helpers ─────────────────────────────────────────────────────────────

def _free_port() -> int:
    """Return a free TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _wait_http(port: int, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/status", timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def _get(port: int, path: str):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as r:
        return json.loads(r.read())


def _post(port: int, path: str, body=None):
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data,
        {"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read())


def _get_agent_card(port: int) -> dict:
    """Fetch AgentCard from /.well-known/acp.json (unwrap 'self' wrapper)."""
    data = _get(port, "/.well-known/acp.json")
    if isinstance(data, dict) and "self" in data:
        return data["self"]
    return data


def _clean_env() -> dict:
    proxy_vars = (
        "http_proxy", "HTTP_PROXY",
        "https_proxy", "HTTPS_PROXY",
        "all_proxy", "ALL_PROXY",
        "no_proxy", "NO_PROXY",
    )
    env = os.environ.copy()
    for v in proxy_vars:
        env.pop(v, None)
    return env


def _start_relay(extra_args=None):
    # HTTP port = ws_port + 100 (hardcoded in relay)
    # Find a ws_port such that both ws_port and ws_port+100 are free
    while True:
        ws_port = _free_port()
        http_port = ws_port + 100
        # Quick check: try binding ws_port+100 as well
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', http_port))
            break  # both ports available
        except OSError:
            pass  # collision, try again
    cmd = [
        sys.executable, RELAY_BIN,
        "--port", str(ws_port),
        "--name", "HPTest",
        "--test-mode",
    ]
    if extra_args:
        cmd.extend(extra_args)
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=_clean_env(),
    )
    return proc, ws_port, http_port


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def relay_no_hbp():
    """Relay started WITHOUT --heartbeat-period-ms."""
    proc, ws_port, http_port = _start_relay()
    assert _wait_http(http_port), f"Relay (no hbp) did not start on HTTP {http_port}"
    yield http_port
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
        proc.wait(timeout=3)


@pytest.fixture(scope="module")
def relay_hbp_30000():
    """Relay started WITH --heartbeat-period-ms 30000."""
    proc, ws_port, http_port = _start_relay(["--heartbeat-period-ms", "30000"])
    assert _wait_http(http_port), f"Relay (hbp=30000) did not start on HTTP {http_port}"
    yield http_port
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
        proc.wait(timeout=3)


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestHeartbeatPeriodMS:

    # HP1: No --heartbeat-period-ms: AgentCard has no heartbeat_period_ms (or null)
    def test_HP1_no_heartbeat_period_in_card(self, relay_no_hbp):
        card = _get_agent_card(relay_no_hbp)
        hbp = card.get("heartbeat_period_ms")
        assert hbp is None, (
            f"Expected heartbeat_period_ms to be absent/null in AgentCard, got {hbp!r}"
        )

    # HP2: --heartbeat-period-ms 30000: AgentCard.heartbeat_period_ms == 30000
    def test_HP2_heartbeat_period_in_card(self, relay_hbp_30000):
        card = _get_agent_card(relay_hbp_30000)
        assert card.get("heartbeat_period_ms") == 30000, (
            f"Expected heartbeat_period_ms=30000, got {card.get('heartbeat_period_ms')!r}"
        )

    # HP3: capabilities.heartbeat_period_declared == True when declared
    def test_HP3_capability_declared_true(self, relay_hbp_30000):
        card = _get_agent_card(relay_hbp_30000)
        caps = card.get("capabilities", {})
        assert caps.get("heartbeat_period_declared") is True, (
            f"Expected capabilities.heartbeat_period_declared=True, got {caps.get('heartbeat_period_declared')!r}"
        )

    # HP4: capabilities.heartbeat_period_declared absent or False when not declared
    def test_HP4_capability_declared_absent_or_false(self, relay_no_hbp):
        card = _get_agent_card(relay_no_hbp)
        caps = card.get("capabilities", {})
        val = caps.get("heartbeat_period_declared")
        assert val is None or val is False, (
            f"Expected heartbeat_period_declared to be absent/False, got {val!r}"
        )

    # HP5: GET /availability returns heartbeat_period_ms == 30000
    def test_HP5_availability_includes_heartbeat_period(self, relay_hbp_30000):
        data = _get(relay_hbp_30000, "/availability")
        assert data.get("heartbeat_period_ms") == 30000, (
            f"Expected GET /availability to include heartbeat_period_ms=30000, "
            f"got {data.get('heartbeat_period_ms')!r}"
        )

    # HP6: POST /availability/heartbeat response includes heartbeat_period_ms == 30000
    def test_HP6_heartbeat_response_includes_period(self, relay_hbp_30000):
        data = _post(relay_hbp_30000, "/availability/heartbeat")
        assert data.get("heartbeat_period_ms") == 30000, (
            f"Expected POST /availability/heartbeat to include heartbeat_period_ms=30000, "
            f"got {data.get('heartbeat_period_ms')!r}"
        )

    # HP7: heartbeat_period_ms boundary: 1ms is valid positive integer
    def test_HP7_boundary_1ms(self):
        proc, ws_port, http_port = _start_relay(["--heartbeat-period-ms", "1"])
        try:
            assert _wait_http(http_port), f"Relay (hbp=1) did not start on HTTP {http_port}"
            card = _get_agent_card(http_port)
            assert card.get("heartbeat_period_ms") == 1, (
                f"Expected heartbeat_period_ms=1, got {card.get('heartbeat_period_ms')!r}"
            )
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
                proc.wait(timeout=3)

    # HP8: heartbeat_period_ms = 60000, GET /.well-known/acp.json returns it correctly
    def test_HP8_60000_well_known(self):
        proc, ws_port, http_port = _start_relay(["--heartbeat-period-ms", "60000"])
        try:
            assert _wait_http(http_port), f"Relay (hbp=60000) did not start on HTTP {http_port}"
            data = _get(http_port, "/.well-known/acp.json")
            # unwrap self wrapper if present
            if isinstance(data, dict) and "self" in data:
                card = data["self"]
            else:
                card = data
            assert card.get("heartbeat_period_ms") == 60000, (
                f"Expected heartbeat_period_ms=60000 in /.well-known/acp.json, "
                f"got {card.get('heartbeat_period_ms')!r}"
            )
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
                proc.wait(timeout=3)

    # HP9: heartbeat_period_ms present in GET /status agent_card field
    def test_HP9_in_status_agent_card(self, relay_hbp_30000):
        data = _get(relay_hbp_30000, "/status")
        # /status may embed agent_card directly or as a sub-key
        agent_card = data.get("agent_card") or data
        hbp = agent_card.get("heartbeat_period_ms")
        assert hbp == 30000, (
            f"Expected heartbeat_period_ms=30000 in GET /status agent_card, got {hbp!r}"
        )

    # HP10: No --heartbeat-period-ms: POST /availability/heartbeat has no heartbeat_period_ms
    def test_HP10_no_hbp_heartbeat_response(self, relay_no_hbp):
        data = _post(relay_no_hbp, "/availability/heartbeat")
        hbp = data.get("heartbeat_period_ms")
        assert hbp is None, (
            f"Expected heartbeat_period_ms to be absent/None in heartbeat response, got {hbp!r}"
        )
