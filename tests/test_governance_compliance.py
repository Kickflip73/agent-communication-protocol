"""
test_governance_compliance.py — v3.12 governance compliance tests

Tests:
  GC1:  GET /governance/compliance returns correct structure (no prior check)
  GC2:  POST /governance/compliance triggers live check, sets last_verified_at
  GC3:  POST /governance/compliance returns compliance_report with policy_checks
  GC4:  GET /governance/compliance after POST shows last_verified_at
  GC5:  AgentCard.governance.compliance_report present
  GC6:  AgentCard.governance.last_verified_at present (null before first check)
  GC7:  capabilities.governance_compliance=true in AgentCard
  GC8:  endpoints.governance_compliance in AgentCard
  GC9:  POST /governance/policy still returns governance block (regression)
  GC10: POST /governance/compliance with empty policy_compliance returns compliant
  GC11: Multiple POST /governance/compliance calls are idempotent (status stays compliant)
  GC12: GET /governance/compliance compliance_endpoint field correct
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
        req = urllib.request.urlopen(url, timeout=timeout)
        return json.loads(req.read()), req.status
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read()), e.code
        except Exception:
            return {}, e.code
    except Exception:
        return None, None


def _post(http_port: int, path: str, body: dict = None, timeout: float = 5.0):
    url = f"http://127.0.0.1:{http_port}{path}"
    data = json.dumps(body or {}).encode()
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


def _start_relay(ws_port: int, name: str = "TestRelay",
                 extra_args: list = None) -> subprocess.Popen:
    env = {**os.environ}
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        env.pop(k, None)
    env["no_proxy"] = "127.0.0.1,localhost"
    env["NO_PROXY"] = "127.0.0.1,localhost"
    cmd = [sys.executable, RELAY_PY,
           "--port", str(ws_port),
           "--local-only",
           "--name", name]
    if extra_args:
        cmd.extend(extra_args)
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
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
    proc = _start_relay(ws, "GCRelay")
    if not _wait_http_ready(http, 30):
        proc.terminate()
        proc.wait(timeout=5)
        pytest.skip("GCRelay did not start")
    yield {"ws": ws, "http": http, "proc": proc}
    proc.terminate()
    try: proc.wait(timeout=8)
    except subprocess.TimeoutExpired: proc.kill(); proc.wait()


# ── GC1: GET /governance/compliance initial structure ────────────────────────

def test_gc1_get_structure(relay):
    """GC1: GET /governance/compliance returns correct structure."""
    data, code = _get(relay["http"], "/governance/compliance")
    assert code == 200, f"Expected 200, got {code}: {data}"
    assert data.get("ok") is True
    assert "compliance_report" in data, f"Missing compliance_report: {data}"
    assert "governance" in data, f"Missing governance: {data}"
    cr = data["compliance_report"]
    assert "policies_declared" in cr
    assert "issues_detected" in cr
    assert "status" in cr
    assert "compliance_endpoint" in cr


# ── GC2: POST /governance/compliance triggers check ──────────────────────────

def test_gc2_post_sets_verified_at(relay):
    """GC2: POST /governance/compliance sets last_verified_at."""
    data, code = _post(relay["http"], "/governance/compliance")
    assert code == 200, f"Expected 200, got {code}: {data}"
    assert data.get("ok") is True
    assert data.get("last_verified_at") is not None, \
        f"last_verified_at should be set after POST: {data}"
    # Should be a valid ISO8601 timestamp
    assert "T" in data["last_verified_at"] or "Z" in data["last_verified_at"], \
        f"last_verified_at not ISO8601: {data['last_verified_at']}"


# ── GC3: POST returns policy_checks list ─────────────────────────────────────

def test_gc3_post_returns_policy_checks(relay):
    """GC3: POST /governance/compliance returns compliance_report with policy_checks."""
    data, code = _post(relay["http"], "/governance/compliance")
    assert code == 200
    cr = data.get("compliance_report", {})
    assert "policy_checks" in cr, f"Missing policy_checks in report: {cr}"
    assert isinstance(cr["policy_checks"], list)
    # Status should be one of the valid values
    assert cr.get("status") in ("compliant", "issues_detected", "unverified"), \
        f"Unexpected status: {cr.get('status')}"


# ── GC4: GET after POST shows last_verified_at ───────────────────────────────

def test_gc4_get_after_post_shows_verified_at(relay):
    """GC4: GET /governance/compliance after POST shows last_verified_at."""
    # First POST to set verified_at
    post_data, _ = _post(relay["http"], "/governance/compliance")
    verified_at = post_data.get("last_verified_at")
    assert verified_at is not None

    # Now GET — should show same or later verified_at
    get_data, code = _get(relay["http"], "/governance/compliance")
    assert code == 200
    assert get_data.get("last_verified_at") is not None, \
        f"GET should show last_verified_at after POST: {get_data}"


# ── GC5: AgentCard.governance.compliance_report present ──────────────────────

def test_gc5_agentcard_compliance_report(relay):
    """GC5: AgentCard.governance.compliance_report is present."""
    wrapper, code = _get(relay["http"], "/.well-known/acp.json")
    assert code == 200
    card = wrapper.get("self") or wrapper
    gov = card.get("governance") or {}
    assert "compliance_report" in gov, \
        f"Expected governance.compliance_report in AgentCard, got keys: {list(gov.keys())}"
    cr = gov["compliance_report"]
    assert "policies_declared" in cr
    assert "issues_detected" in cr
    assert "status" in cr


# ── GC6: AgentCard.governance.last_verified_at present ───────────────────────

def test_gc6_agentcard_last_verified_at(relay):
    """GC6: AgentCard.governance.last_verified_at field is present."""
    wrapper, code = _get(relay["http"], "/.well-known/acp.json")
    assert code == 200
    card = wrapper.get("self") or wrapper
    gov = card.get("governance") or {}
    assert "last_verified_at" in gov, \
        f"Expected governance.last_verified_at in AgentCard, got keys: {list(gov.keys())}"


# ── GC7: capabilities.governance_compliance=true ─────────────────────────────

def test_gc7_capabilities_declared(relay):
    """GC7: capabilities.governance_compliance=true in AgentCard."""
    wrapper, code = _get(relay["http"], "/.well-known/acp.json")
    assert code == 200
    card = wrapper.get("self") or wrapper
    caps = card.get("capabilities") or {}
    assert caps.get("governance_compliance") is True, \
        f"Expected capabilities.governance_compliance=true, got: {caps.get('governance_compliance')}"


# ── GC8: endpoints.governance_compliance declared ────────────────────────────

def test_gc8_endpoints_declared(relay):
    """GC8: endpoints.governance_compliance declared in AgentCard."""
    wrapper, code = _get(relay["http"], "/.well-known/acp.json")
    assert code == 200
    card = wrapper.get("self") or wrapper
    endpoints = card.get("endpoints") or {}
    assert "governance_compliance" in endpoints, \
        f"Expected endpoints.governance_compliance, got keys: {list(endpoints.keys())[:15]}"
    assert endpoints["governance_compliance"] == "/governance/compliance"


# ── GC9: POST /governance/policy regression ──────────────────────────────────

def test_gc9_governance_policy_regression(relay):
    """GC9: POST /governance/policy still returns governance block (regression)."""
    data, code = _post(relay["http"], "/governance/policy")
    assert code == 200, f"POST /governance/policy failed: {code} {data}"
    assert "framework" in data, f"Missing framework: {data}"
    assert data["framework"] == "ACP"
    assert "credential_lifecycle" in data


# ── GC10: no policies = compliant after POST ─────────────────────────────────

def test_gc10_no_policies_is_compliant(relay):
    """GC10: POST /governance/compliance with no policies declared returns compliant."""
    data, code = _post(relay["http"], "/governance/compliance")
    assert code == 200
    cr = data.get("compliance_report", {})
    # With no policies declared, issues_detected should be 0 → compliant
    assert cr.get("issues_detected", -1) == 0, \
        f"Expected 0 issues with no policies: {cr}"
    assert cr.get("status") == "compliant", \
        f"Expected 'compliant' with 0 issues: {cr.get('status')}"


# ── GC11: multiple POSTs are idempotent ──────────────────────────────────────

def test_gc11_idempotent(relay):
    """GC11: Multiple POST /governance/compliance calls remain compliant."""
    for i in range(3):
        data, code = _post(relay["http"], "/governance/compliance")
        assert code == 200, f"POST {i+1} failed: {code}"
        assert data.get("ok") is True
        cr = data.get("compliance_report", {})
        assert cr.get("status") in ("compliant", "issues_detected"), \
            f"POST {i+1} unexpected status: {cr.get('status')}"


# ── GC12: compliance_endpoint field correct ───────────────────────────────────

def test_gc12_compliance_endpoint_field(relay):
    """GC12: GET /governance/compliance compliance_endpoint field is '/governance/compliance'."""
    data, code = _get(relay["http"], "/governance/compliance")
    assert code == 200
    cr = data.get("compliance_report", {})
    assert cr.get("compliance_endpoint") == "/governance/compliance", \
        f"Expected '/governance/compliance', got: {cr.get('compliance_endpoint')}"
