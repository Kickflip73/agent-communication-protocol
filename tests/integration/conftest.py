"""
Integration test fixtures — spins up a real acp_relay.py process for each test session.

Usage:
    pytest tests/integration/ -v

The relay is started in host mode on ephemeral ports (assigned by OS).
Tests receive a `relay_url` fixture pointing at the live HTTP API.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error

import pytest

RELAY_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "relay", "acp_relay.py")
STARTUP_TIMEOUT = 10.0   # seconds to wait for relay to become ready
POLL_INTERVAL   = 0.15   # seconds between readiness polls


def _find_free_port() -> int:
    """Bind to port 0 to let OS assign a free port, then release it."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_ready(url: str, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url + "/status", timeout=1) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(POLL_INTERVAL)
    return False


@pytest.fixture(scope="session")
def relay_process():
    """
    Session-scoped fixture: starts one acp_relay.py host process for all tests.
    Yields (process, http_url, ws_port).
    """
    # acp_relay.py uses --port N for WS; HTTP API is always port+100
    ws_port   = _find_free_port()
    http_port = ws_port + 100

    cmd = [
        sys.executable, RELAY_PATH,
        "--port", str(ws_port),
        "--name", "IntegrationTestAgent",
    ]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    http_url = f"http://127.0.0.1:{http_port}"

    if not _wait_ready(http_url, STARTUP_TIMEOUT):
        proc.terminate()
        proc.wait()
        stdout = proc.stdout.read().decode(errors="replace")
        stderr = proc.stderr.read().decode(errors="replace")
        pytest.fail(
            f"relay did not become ready within {STARTUP_TIMEOUT}s\n"
            f"stdout: {stdout[:500]}\nstderr: {stderr[:500]}"
        )

    yield proc, http_url, ws_port

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="session")
def relay_url(relay_process):
    """HTTP base URL for the running relay (e.g. http://127.0.0.1:49823)."""
    _, url, _ = relay_process
    return url


# ── HTTP helpers ──────────────────────────────────────────────────────────

def http_get(url: str, timeout: float = 5.0):
    """GET url → (status_code, dict)."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())
    except Exception as e:
        return 0, {"error": str(e)}


def http_post(url: str, body: dict, timeout: float = 5.0):
    """POST url with JSON body → (status_code, dict)."""
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())
    except Exception as e:
        return 0, {"error": str(e)}
