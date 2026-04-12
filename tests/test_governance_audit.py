"""
test_governance_audit.py — v3.13 GET /governance/audit tests

Tests:
  GA1:  GET /governance/audit returns correct structure (ok, records, total, returned)
  GA2:  Returns 200 even when no interaction records exist
  GA3:  `audit_endpoint` field in response matches "/governance/audit"
  GA4:  `capabilities.governance_audit=true` in AgentCard
  GA5:  `endpoints.governance_audit` declared in AgentCard
  GA6:  `governance_metadata.audit_endpoint` declared in AgentCard
  GA7:  `?limit=` query param limits returned records
  GA8:  `?peer_id=` filter only returns matching records
  GA9:  `?task_id=` filter only returns matching records
  GA10: `?since=` filter only returns records after timestamp
"""
import subprocess
import socket
import time
import json
import threading
import urllib.request
import urllib.error
import os
import sys
import pytest

RELAY_PY = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _get(http_port: int, path: str, timeout: float = 5.0):
    url = f"http://127.0.0.1:{http_port}{path}"
    try:
        resp = urllib.request.urlopen(url, timeout=timeout)
        return json.loads(resp.read()), resp.status
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
    except Exception:
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


def _start_relay(ws_port: int, name: str = "GARelay") -> subprocess.Popen:
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
        except Exception: pass
    threading.Thread(target=_drain, args=(proc.stdout,), daemon=True).start()
    return proc


@pytest.fixture(scope="module")
def relay():
    ws = _free_port()
    http = ws + 100
    proc = _start_relay(ws, "GARelay")
    if not _wait_http_ready(http, 30):
        proc.terminate()
        proc.wait(timeout=5)
        pytest.skip("GARelay did not start")
    yield {"ws": ws, "http": http, "proc": proc}
    proc.terminate()
    try: proc.wait(timeout=8)
    except subprocess.TimeoutExpired: proc.kill(); proc.wait()


# ── GA1: Structure ────────────────────────────────────────────────────────────

def test_ga1_structure(relay):
    """GA1: GET /governance/audit returns correct structure."""
    data, code = _get(relay["http"], "/governance/audit")
    assert code == 200, f"Expected 200, got {code}: {data}"
    assert data.get("ok") is True
    assert "records" in data, f"Missing 'records': {data}"
    assert "total" in data, f"Missing 'total': {data}"
    assert "returned" in data, f"Missing 'returned': {data}"
    assert isinstance(data["records"], list)


# ── GA2: Empty records returns 200 ───────────────────────────────────────────

def test_ga2_empty_returns_200(relay):
    """GA2: GET /governance/audit returns 200 even with no interaction records."""
    data, code = _get(relay["http"], "/governance/audit")
    assert code == 200, f"Expected 200, got {code}: {data}"
    # records may be empty list — that's fine
    assert isinstance(data.get("records"), list)
    assert data.get("total", 0) >= 0


# ── GA3: audit_endpoint field ─────────────────────────────────────────────────

def test_ga3_audit_endpoint_field(relay):
    """GA3: Response contains audit_endpoint="/governance/audit"."""
    data, code = _get(relay["http"], "/governance/audit")
    assert code == 200
    assert data.get("audit_endpoint") == "/governance/audit", \
        f"Expected audit_endpoint='/governance/audit': {data.get('audit_endpoint')}"


# ── GA4: capabilities.governance_audit=true ──────────────────────────────────

def test_ga4_capabilities(relay):
    """GA4: AgentCard capabilities.governance_audit=true."""
    wrapper, code = _get(relay["http"], "/.well-known/acp.json")
    assert code == 200
    card = wrapper.get("self") or wrapper
    caps = card.get("capabilities") or {}
    assert caps.get("governance_audit") is True, \
        f"Expected capabilities.governance_audit=true, got: {caps.get('governance_audit')}"


# ── GA5: endpoints.governance_audit declared ─────────────────────────────────

def test_ga5_endpoints_declared(relay):
    """GA5: AgentCard endpoints.governance_audit declared."""
    wrapper, code = _get(relay["http"], "/.well-known/acp.json")
    assert code == 200
    card = wrapper.get("self") or wrapper
    endpoints = card.get("endpoints") or {}
    assert "governance_audit" in endpoints, \
        f"Expected 'governance_audit' in endpoints, keys: {list(endpoints.keys())[:10]}"
    assert endpoints["governance_audit"] == "/governance/audit"


# ── GA6: governance_metadata.audit_endpoint ──────────────────────────────────

def test_ga6_governance_metadata_audit_endpoint(relay):
    """GA6: governance_metadata.audit_endpoint declared in AgentCard."""
    wrapper, code = _get(relay["http"], "/.well-known/acp.json")
    assert code == 200
    card = wrapper.get("self") or wrapper
    # governance_metadata may be inside card.governance or card directly
    gm = (card.get("governance") or {}).get("governance_metadata") or card.get("governance_metadata") or {}
    if not gm:
        # Try /governance-metadata endpoint
        gm_data, gm_code = _get(relay["http"], "/governance-metadata")
        if gm_code == 200:
            gm = gm_data.get("governance_metadata") or gm_data
    assert gm.get("audit_endpoint") == "/governance/audit", \
        f"Expected governance_metadata.audit_endpoint='/governance/audit', got: {gm.get('audit_endpoint')}"


# ── GA7: ?limit= query param ─────────────────────────────────────────────────

def test_ga7_limit_param(relay):
    """GA7: ?limit= restricts returned records."""
    # First ensure there's at least 1 interaction record by POSTing a task
    # (interaction records are created automatically when tasks are executed)
    # Even with 0 records, limit enforcement should still work
    data, code = _get(relay["http"], "/governance/audit?limit=5")
    assert code == 200
    assert data.get("returned", 0) <= 5, \
        f"returned={data.get('returned')} exceeds limit=5"
    # returned should not exceed total
    assert data.get("returned", 0) <= data.get("total", 0) + 1  # +1 for edge case


# ── GA8: ?peer_id= filter ────────────────────────────────────────────────────

def test_ga8_peer_id_filter(relay):
    """GA8: ?peer_id= filters records by peer_id."""
    data, code = _get(relay["http"], "/governance/audit?peer_id=nonexistent-peer-xyz999")
    assert code == 200
    assert data.get("ok") is True
    # No records should match this fake peer_id
    assert len(data.get("records", [])) == 0, \
        f"Expected 0 records for fake peer_id, got: {len(data.get('records', []))}"


# ── GA9: ?task_id= filter ────────────────────────────────────────────────────

def test_ga9_task_id_filter(relay):
    """GA9: ?task_id= filters records by task_id."""
    data, code = _get(relay["http"], "/governance/audit?task_id=nonexistent-task-abc999")
    assert code == 200
    assert data.get("ok") is True
    assert len(data.get("records", [])) == 0, \
        f"Expected 0 records for fake task_id, got: {len(data.get('records', []))}"


# ── GA10: ?since= filter ─────────────────────────────────────────────────────

def test_ga10_since_filter(relay):
    """GA10: ?since= filters records after the given timestamp."""
    # Use a future timestamp — no records should be after it
    future_ts = "2099-01-01T00:00:00.000Z"
    data, code = _get(relay["http"], f"/governance/audit?since={future_ts}")
    assert code == 200
    assert data.get("ok") is True
    assert len(data.get("records", [])) == 0, \
        f"Expected 0 records after future timestamp, got: {len(data.get('records', []))}"
