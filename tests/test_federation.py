"""
test_federation.py — v3.10 multi-relay federation tests

Tests:
  FED1: GET /federation returns correct structure (no relays yet)
  FED2: POST /federation requires 'link' field
  FED3: POST /federation with invalid link format returns 400
  FED4: GET /federation after POST shows registered relay
  FED5: POST /federation is idempotent (same link → already_connected=True)
  FED6: AgentCard capabilities.federation=true
  FED7: AgentCard endpoints.federation and endpoints.federation_route declared
  FED8: POST /federation/route requires relay_id
  FED9: POST /federation/route requires target_peer_id
  FED10: POST /federation/route with unknown relay_id returns 404
  FED11: POST /federation/route with disconnected relay returns 503
  FED12: Two relay instances can federate (cross-relay message routing — local loopback)
"""
import subprocess
import socket
import time
import json
import urllib.request
import urllib.error
import os
import sys
import threading
import pytest

RELAY_PY = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _get(http_port: int, path: str, timeout: float = 5.0):
    url = f"http://127.0.0.1:{http_port}{path}"
    try:
        req = urllib.request.urlopen(url, timeout=timeout)
        return json.loads(req.read()), req.status
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read()), e.code
        except Exception:
            return {}, e.code
    except Exception:
        return None, None


def _post(http_port: int, path: str, body: dict, timeout: float = 8.0):
    url = f"http://127.0.0.1:{http_port}{path}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data,
                                  headers={"Content-Type": "application/json"},
                                  method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(resp.read()), resp.status
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read()), e.code
        except Exception:
            return {}, e.code
    except Exception as e:
        return None, None


def _wait_http_ready(http_port: int, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{http_port}/status", timeout=2)
            return True
        except Exception:
            time.sleep(0.3)
    return False


def _start_relay(ws_port: int, name: str = "TestRelay") -> subprocess.Popen:
    env = {**os.environ}
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        env.pop(k, None)
    env["no_proxy"] = "127.0.0.1,localhost"
    env["NO_PROXY"] = "127.0.0.1,localhost"
    proc = subprocess.Popen(
        [sys.executable, RELAY_PY,
         "--port", str(ws_port),
         "--local-only",
         "--name", name],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
    )
    def _drain(p):
        try:
            for _ in p: pass
        except Exception:
            pass
    threading.Thread(target=_drain, args=(proc.stdout,), daemon=True).start()
    return proc


@pytest.fixture(scope="module")
def relay_a():
    """Relay A — the 'source' relay for federation tests."""
    ws = _free_port()
    http = ws + 100
    proc = _start_relay(ws, "RelayA")
    if not _wait_http_ready(http, 30):
        proc.terminate()
        proc.wait(timeout=5)
        pytest.skip("RelayA did not start")
    yield {"ws": ws, "http": http, "proc": proc}
    proc.terminate()
    try: proc.wait(timeout=8)
    except subprocess.TimeoutExpired: proc.kill(); proc.wait()


@pytest.fixture(scope="module")
def relay_b():
    """Relay B — the 'target' relay for cross-relay routing tests."""
    ws = _free_port()
    http = ws + 100
    proc = _start_relay(ws, "RelayB")
    if not _wait_http_ready(http, 30):
        proc.terminate()
        proc.wait(timeout=5)
        pytest.skip("RelayB did not start")
    yield {"ws": ws, "http": http, "proc": proc}
    proc.terminate()
    try: proc.wait(timeout=8)
    except subprocess.TimeoutExpired: proc.kill(); proc.wait()


# ── FED1: GET /federation structure ──────────────────────────────────────────

def test_fed1_get_federation_structure(relay_a):
    """FED1: GET /federation returns correct structure."""
    data, code = _get(relay_a["http"], "/federation")
    assert code == 200, f"Expected 200, got {code}: {data}"
    assert "relays" in data, f"Missing 'relays': {data}"
    assert "relay_count" in data, f"Missing 'relay_count': {data}"
    assert "capabilities" in data, f"Missing 'capabilities': {data}"
    assert data["capabilities"].get("federation") is True


# ── FED2: GET /federation initially empty ────────────────────────────────────

def test_fed2_initially_empty(relay_a):
    """FED2: Initially no federation relays."""
    data, code = _get(relay_a["http"], "/federation")
    assert code == 200
    assert data["relays"] == [], f"Expected empty relays, got: {data['relays']}"
    assert data["relay_count"] == 0


# ── FED3: POST /federation requires link ─────────────────────────────────────

def test_fed3_requires_link(relay_a):
    """FED3: POST /federation without link returns 400."""
    data, code = _post(relay_a["http"], "/federation", {})
    assert code == 400, f"Expected 400, got {code}: {data}"
    assert "error" in data


# ── FED4: POST /federation with invalid link format ───────────────────────────

def test_fed4_invalid_link_format(relay_a):
    """FED4: POST /federation with invalid link format returns 400."""
    data, code = _post(relay_a["http"], "/federation", {
        "link": "not-a-valid-acp-link",
        "name": "bad-relay",
    })
    assert code == 400, f"Expected 400, got {code}: {data}"


# ── FED5: POST /federation registers relay ────────────────────────────────────

@pytest.fixture(scope="module")
def federation_link(relay_a, relay_b):
    """Get relay_b's acp:// link and register it on relay_a."""
    # Get relay_b's link from /status
    status, code = _get(relay_b["http"], "/status")
    assert code == 200, f"Failed to get relay_b status: {code}"
    link = status.get("link")
    if not link:
        pytest.skip("relay_b has no link (local-only may not have generated one yet)")
    return link


def test_fed5_post_federation_registers(relay_a, relay_b, federation_link):
    """FED5: POST /federation registers remote relay."""
    data, code = _post(relay_a["http"], "/federation", {
        "link": federation_link,
        "name": "test-relay-b",
    })
    assert code == 200, f"Expected 200, got {code}: {data}"
    assert data.get("ok") is True, f"Expected ok=true: {data}"
    assert "relay_id" in data, f"Missing relay_id: {data}"
    assert "peer_id" in data, f"Missing peer_id: {data}"
    assert data.get("already_connected") is False


# ── FED6: GET /federation shows registered relay ─────────────────────────────

def test_fed6_get_shows_registered_relay(relay_a, relay_b, federation_link):
    """FED6: GET /federation shows the registered relay after POST."""
    # Ensure federation is registered (may already be from FED5)
    status_b, _ = _get(relay_b["http"], "/status")
    link = status_b.get("link") or federation_link

    # Register if not already
    _post(relay_a["http"], "/federation", {"link": link, "name": "relay-b"})

    data, code = _get(relay_a["http"], "/federation")
    assert code == 200
    assert data["relay_count"] >= 1, f"Expected ≥1 relays, got: {data['relay_count']}"
    relay_links = [r["link"] for r in data["relays"]]
    assert link in relay_links, f"Expected {link} in relays: {relay_links}"


# ── FED7: Idempotent federation ───────────────────────────────────────────────

def test_fed7_idempotent_federation(relay_a, relay_b, federation_link):
    """FED7: Posting same link twice returns already_connected=True."""
    # First registration
    _post(relay_a["http"], "/federation", {"link": federation_link})
    # Second registration (idempotent)
    data, code = _post(relay_a["http"], "/federation", {"link": federation_link})
    assert code == 200, f"Expected 200, got {code}: {data}"
    assert data.get("already_connected") is True, f"Expected already_connected=True: {data}"


# ── FED8: AgentCard capabilities.federation ───────────────────────────────────

def test_fed8_capabilities_federation(relay_a):
    """FED8: AgentCard capabilities.federation=true."""
    wrapper, code = _get(relay_a["http"], "/.well-known/acp.json")
    assert code == 200
    card = wrapper.get("self") or wrapper
    caps = card.get("capabilities") or {}
    assert caps.get("federation") is True, \
        f"Expected capabilities.federation=true, got: {caps.get('federation')}"


# ── FED9: AgentCard endpoints declaration ────────────────────────────────────

def test_fed9_endpoints_declared(relay_a):
    """FED9: AgentCard endpoints.federation and endpoints.federation_route declared."""
    wrapper, code = _get(relay_a["http"], "/.well-known/acp.json")
    assert code == 200
    card = wrapper.get("self") or wrapper
    endpoints = card.get("endpoints") or {}
    assert "federation" in endpoints, \
        f"Expected 'federation' in endpoints, got: {list(endpoints.keys())[:10]}"
    assert "federation_route" in endpoints, \
        f"Expected 'federation_route' in endpoints, got: {list(endpoints.keys())[:10]}"
    assert endpoints["federation"] == "/federation"
    assert endpoints["federation_route"] == "/federation/route"


# ── FED10: POST /federation/route requires relay_id ──────────────────────────

def test_fed10_route_requires_relay_id(relay_a):
    """FED10: POST /federation/route without relay_id returns 400."""
    data, code = _post(relay_a["http"], "/federation/route", {
        "target_peer_id": "some-peer",
        "text": "hello",
    })
    assert code == 400, f"Expected 400, got {code}: {data}"
    assert "error" in data


# ── FED11: POST /federation/route requires target_peer_id ───────────────────

def test_fed11_route_requires_target_peer_id(relay_a):
    """FED11: POST /federation/route without target_peer_id returns 400."""
    data, code = _post(relay_a["http"], "/federation/route", {
        "relay_id": "relay_fake",
        "text": "hello",
    })
    assert code == 400, f"Expected 400, got {code}: {data}"
    assert "error" in data


# ── FED12: POST /federation/route with unknown relay returns 404 ─────────────

def test_fed12_route_unknown_relay(relay_a):
    """FED12: POST /federation/route with unknown relay_id returns 404."""
    data, code = _post(relay_a["http"], "/federation/route", {
        "relay_id": "relay_nonexistent_abc123",
        "target_peer_id": "some-peer",
        "text": "hello",
    })
    assert code == 404, f"Expected 404, got {code}: {data}"
    assert data.get("error_code") == "ERR_FEDERATION_RELAY_NOT_FOUND" or \
           "not registered" in data.get("error", ""), \
           f"Unexpected error: {data}"
