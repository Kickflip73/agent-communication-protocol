"""
ACP v2.41 — GET /skills OpenAPI spec tests (SO1–SO5)

Verifies that:
  SO1: GET /health (/.well-known/acp.json) contains `skills_schema_url` field
  SO2: skills_schema_url value is "/docs/openapi-skills.yaml"
  SO3: GET /docs/openapi-skills.yaml returns HTTP 200
  SO4: The returned content contains 'openapi: "3.1.0"' or "openapi: '3.1.0'"
  SO5: capabilities.skills_openapi_spec == True

Introduced in ACP v2.41 to support technical evangelism at A2A IS#1655
with a standardized, externally referenceable schema.
"""

import json
import os
import socket
import subprocess
import sys
import time
import threading
import urllib.error
import urllib.request

import pytest

# ── helpers ───────────────────────────────────────────────────────────────────

RELAY_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")


def _free_port():
    """Return a free port, ensuring both port and port+100 are available."""
    for _ in range(50):
        with socket.socket() as s:
            s.bind(("", 0))
            p = s.getsockname()[1]
        try:
            with socket.socket() as s2:
                s2.bind(("", p + 100))
            return p
        except OSError:
            continue
    raise RuntimeError("Could not find a port pair (p, p+100) that are both free")


def _http(port, path, method="GET", body=None, timeout=15):
    """HTTP helper that returns (parsed_body, status_code)."""
    url = f"http://127.0.0.1:{port}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read()), e.code
        except Exception:
            return {}, e.code


def _http_raw(port, path, timeout=15):
    """HTTP helper that returns (raw_bytes, status_code) — for non-JSON responses."""
    url = f"http://127.0.0.1:{port}{path}"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read(), r.status
    except urllib.error.HTTPError as e:
        return e.read(), e.code


def _start_relay(ws_port, name, local_only=True):
    env = os.environ.copy()
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        env.pop(k, None)
    cmd = [sys.executable, RELAY_SCRIPT, "--port", str(ws_port), "--name", name]
    if local_only:
        cmd += ["--local-only"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    for s in (proc.stdout, proc.stderr):
        threading.Thread(target=lambda x=s: x.read(), daemon=True).start()
    return proc


def _wait_for(fn, timeout=15, interval=0.4):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if fn():
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


# ── module-scoped fixture: single relay instance ──────────────────────────────

@pytest.fixture(scope="module")
def so_relay():
    ws_port = _free_port()
    http_port = ws_port + 100
    proc = _start_relay(ws_port, "SO-Agent")

    ready = _wait_for(lambda: _http(http_port, "/status")[1] == 200, timeout=15)
    if not ready:
        proc.kill()
        pytest.fail("Relay did not start in time")

    yield {"proc": proc, "http_port": http_port}

    proc.kill()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.terminate()


# ── tests ─────────────────────────────────────────────────────────────────────

def test_SO1_agent_card_has_skills_schema_url(so_relay):
    """SO1: GET /.well-known/acp.json (AgentCard) must contain skills_schema_url field."""
    port = so_relay["http_port"]
    data, status = _http(port, "/.well-known/acp.json")
    assert status == 200, f"Expected 200, got {status}"
    card = data.get("self", data)
    assert "skills_schema_url" in card, (
        f"AgentCard missing 'skills_schema_url' field. Keys: {list(card.keys())}"
    )


def test_SO2_skills_schema_url_value(so_relay):
    """SO2: skills_schema_url must be '/docs/openapi-skills.yaml'."""
    port = so_relay["http_port"]
    data, status = _http(port, "/.well-known/acp.json")
    assert status == 200
    card = data.get("self", data)
    url = card.get("skills_schema_url")
    assert url == "/docs/openapi-skills.yaml", (
        f"Expected '/docs/openapi-skills.yaml', got {url!r}"
    )


def test_SO3_get_openapi_spec_returns_200(so_relay):
    """SO3: GET /docs/openapi-skills.yaml must return HTTP 200."""
    port = so_relay["http_port"]
    raw, status = _http_raw(port, "/docs/openapi-skills.yaml")
    assert status == 200, (
        f"Expected 200 from GET /docs/openapi-skills.yaml, got {status}. "
        f"Body: {raw[:200]!r}"
    )


def test_SO4_openapi_spec_contains_version(so_relay):
    """SO4: The spec content must declare openapi: '3.1.0'."""
    port = so_relay["http_port"]
    raw, status = _http_raw(port, "/docs/openapi-skills.yaml")
    assert status == 200
    content = raw.decode("utf-8")
    assert ('openapi: "3.1.0"' in content or "openapi: '3.1.0'" in content), (
        f"Spec does not contain openapi: '3.1.0'. First 300 chars: {content[:300]!r}"
    )


def test_SO5_capabilities_skills_openapi_spec(so_relay):
    """SO5: capabilities.skills_openapi_spec must be True in AgentCard."""
    port = so_relay["http_port"]
    data, status = _http(port, "/.well-known/acp.json")
    assert status == 200
    card = data.get("self", data)
    caps = card.get("capabilities", {})
    assert caps.get("skills_openapi_spec") is True, (
        f"Expected capabilities.skills_openapi_spec == True, got: {caps.get('skills_openapi_spec')!r}"
    )
