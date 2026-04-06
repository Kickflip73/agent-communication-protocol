"""
ACP v2.60 — Governance Metadata Tests

GM-1:  AgentCard includes governance_metadata block when --governance-metadata provided
GM-2:  governance_metadata NOT in AgentCard by default (no --governance-metadata)
GM-3:  GET /governance-metadata returns 200 with ok:true and block
GM-4:  GET /governance-metadata always includes auto-computed fields
GM-5:  capabilities.governance_metadata=true when configured
GM-6:  capabilities.governance_metadata=false by default
GM-7:  PATCH /governance-metadata — update trust_score
GM-8:  PATCH /governance-metadata — update policy_compliance
GM-9:  PATCH /governance-metadata — update audit_trail_reference
GM-10: PATCH /governance-metadata — update capability_manifest
GM-11: PATCH — read-only fields (generated_at, peer_count, task_count) silently ignored
GM-12: PATCH — invalid trust_score (> 1.0) returns 400
GM-13: PATCH — invalid policy_compliance (not array) returns 400
GM-14: AgentCard.endpoints.governance_metadata = '/governance-metadata'
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

_RELAY = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")
_BASE_PORT = 15100


def _start_relay(ws_port: int, extra_args=None):
    http_port = ws_port + 100
    cmd = [sys.executable, _RELAY, "--port", str(ws_port), "--name", "GMTestAgent",
           "--local-only", "--test-mode"]
    if extra_args:
        cmd += extra_args
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 12
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{http_port}/status", timeout=1) as r:
                if r.status == 200:
                    return proc, http_port
        except Exception:
            time.sleep(0.15)
    proc.terminate()
    raise RuntimeError(f"Relay failed to start on HTTP port {http_port}")


def _stop(proc):
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def _get(hp, path):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{hp}{path}", timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _post(hp, path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{hp}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _patch(hp, path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{hp}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


# ─── GM-1 ──────────────────────────────────────────────────────────────────────

def test_gm1_agentcard_includes_governance_metadata_when_configured():
    """GM-1: AgentCard.governance_metadata present when --governance-metadata is passed."""
    gm_json = json.dumps({
        "trust_score": 0.9,
        "policy_compliance": [{"policy": "acp-v1", "status": "compliant"}],
    })
    proc, hp = _start_relay(_BASE_PORT, extra_args=["--governance-metadata", gm_json])
    try:
        status, _raw = _get(hp, "/.well-known/acp.json")
        card = _raw.get("self") or _raw
        assert status == 200
        assert "governance_metadata" in card, "AgentCard should contain governance_metadata block"
        gm = card["governance_metadata"]
        assert gm.get("trust_score") == 0.9
        assert gm.get("policy_compliance") == [{"policy": "acp-v1", "status": "compliant"}]
    finally:
        _stop(proc)


# ─── GM-2 ──────────────────────────────────────────────────────────────────────

def test_gm2_no_governance_metadata_by_default():
    """GM-2: governance_metadata NOT in AgentCard when --governance-metadata not provided."""
    proc, hp = _start_relay(_BASE_PORT + 2)
    try:
        status, _raw = _get(hp, "/.well-known/acp.json")
        card = _raw.get("self") or _raw
        assert status == 200
        assert "governance_metadata" not in card, "governance_metadata should not appear by default"
    finally:
        _stop(proc)


# ─── GM-3 ──────────────────────────────────────────────────────────────────────

def test_gm3_get_governance_metadata_endpoint_returns_200():
    """GM-3: GET /governance-metadata returns 200 with ok:true and governance_metadata dict."""
    proc, hp = _start_relay(_BASE_PORT + 4)
    try:
        status, resp = _get(hp, "/governance-metadata")
        assert status == 200
        assert resp.get("ok") is True
        assert "governance_metadata" in resp
        gm = resp["governance_metadata"]
        assert isinstance(gm, dict)
    finally:
        _stop(proc)


# ─── GM-4 ──────────────────────────────────────────────────────────────────────

def test_gm4_auto_computed_fields_always_present():
    """GM-4: GET /governance-metadata always includes generated_at, peer_count, task_count, interaction_record_count."""
    proc, hp = _start_relay(_BASE_PORT + 6)
    try:
        status, resp = _get(hp, "/governance-metadata")
        assert status == 200
        gm = resp["governance_metadata"]
        for field in ("generated_at", "peer_count", "task_count", "interaction_record_count"):
            assert field in gm, f"Missing auto-computed field: {field}"
        assert isinstance(gm["peer_count"], int)
        assert isinstance(gm["task_count"], int)
        assert isinstance(gm["interaction_record_count"], int)
    finally:
        _stop(proc)


# ─── GM-5 ──────────────────────────────────────────────────────────────────────

def test_gm5_capability_flag_true_when_configured():
    """GM-5: AgentCard.capabilities.governance_metadata=true when --governance-metadata provided."""
    gm_json = json.dumps({"trust_score": 0.5})
    proc, hp = _start_relay(_BASE_PORT + 8, extra_args=["--governance-metadata", gm_json])
    try:
        status, _raw = _get(hp, "/.well-known/acp.json")
        card = _raw.get("self") or _raw
        assert status == 200
        caps = card.get("capabilities", {})
        assert caps.get("governance_metadata") is True
    finally:
        _stop(proc)


# ─── GM-6 ──────────────────────────────────────────────────────────────────────

def test_gm6_capability_flag_false_by_default():
    """GM-6: AgentCard.capabilities.governance_metadata=false when not configured."""
    proc, hp = _start_relay(_BASE_PORT + 10)
    try:
        status, _raw = _get(hp, "/.well-known/acp.json")
        card = _raw.get("self") or _raw
        assert status == 200
        caps = card.get("capabilities", {})
        assert caps.get("governance_metadata") is False
    finally:
        _stop(proc)


# ─── GM-7 ──────────────────────────────────────────────────────────────────────

def test_gm7_patch_trust_score():
    """GM-7: PATCH /governance-metadata can update trust_score."""
    proc, hp = _start_relay(_BASE_PORT + 12)
    try:
        status, resp = _patch(hp, "/governance-metadata", {"trust_score": 0.75})
        assert status == 200
        assert resp.get("ok") is True
        assert "trust_score" in resp.get("updated", [])
        gm = resp.get("governance_metadata", {})
        assert gm.get("trust_score") == 0.75
        # Confirm it's persisted via GET
        status2, resp2 = _get(hp, "/governance-metadata")
        assert status2 == 200
        assert resp2["governance_metadata"]["trust_score"] == 0.75
    finally:
        _stop(proc)


# ─── GM-8 ──────────────────────────────────────────────────────────────────────

def test_gm8_patch_policy_compliance():
    """GM-8: PATCH /governance-metadata can update policy_compliance list."""
    proc, hp = _start_relay(_BASE_PORT + 14)
    try:
        policies = [{"policy": "gdpr", "status": "compliant"}, {"policy": "soc2", "status": "unknown"}]
        status, resp = _patch(hp, "/governance-metadata", {"policy_compliance": policies})
        assert status == 200
        assert resp.get("ok") is True
        gm = resp.get("governance_metadata", {})
        assert gm.get("policy_compliance") == policies
    finally:
        _stop(proc)


# ─── GM-9 ──────────────────────────────────────────────────────────────────────

def test_gm9_patch_audit_trail_reference():
    """GM-9: PATCH /governance-metadata can update audit_trail_reference."""
    proc, hp = _start_relay(_BASE_PORT + 16)
    try:
        uri = "https://audit.example.com/trail/relay-1"
        status, resp = _patch(hp, "/governance-metadata", {"audit_trail_reference": uri})
        assert status == 200
        assert resp.get("ok") is True
        gm = resp.get("governance_metadata", {})
        assert gm.get("audit_trail_reference") == uri
    finally:
        _stop(proc)


# ─── GM-10 ─────────────────────────────────────────────────────────────────────

def test_gm10_patch_capability_manifest():
    """GM-10: PATCH /governance-metadata can update capability_manifest."""
    proc, hp = _start_relay(_BASE_PORT + 18, extra_args=["--skills", "transfer,summarize"])
    try:
        manifest = {
            "transfer":  {"tier": "T3", "status": "available", "deprecated": False},
            "summarize": {"tier": "T1", "status": "available", "deprecated": False},
        }
        status, resp = _patch(hp, "/governance-metadata", {"capability_manifest": manifest})
        assert status == 200
        assert resp.get("ok") is True
        gm = resp.get("governance_metadata", {})
        assert gm.get("capability_manifest") == manifest
    finally:
        _stop(proc)


# ─── GM-11 ─────────────────────────────────────────────────────────────────────

def test_gm11_readonly_fields_silently_ignored():
    """GM-11: Read-only fields (generated_at, peer_count, task_count) are silently ignored in PATCH."""
    proc, hp = _start_relay(_BASE_PORT + 20)
    try:
        status, resp = _patch(hp, "/governance-metadata", {
            "generated_at":             "2000-01-01T00:00:00Z",  # read-only
            "peer_count":               9999,                     # read-only
            "task_count":               9999,                     # read-only
            "interaction_record_count": 9999,                     # read-only
            "trust_score":              0.42,                     # writable
        })
        assert status == 200
        assert resp.get("ok") is True
        gm = resp.get("governance_metadata", {})
        # Writable field updated
        assert gm["trust_score"] == 0.42
        # Read-only fields not affected
        assert gm["peer_count"] != 9999
        assert gm["task_count"] != 9999
        assert gm["interaction_record_count"] != 9999
        assert gm.get("generated_at") != "2000-01-01T00:00:00Z"
    finally:
        _stop(proc)


# ─── GM-12 ─────────────────────────────────────────────────────────────────────

def test_gm12_invalid_trust_score_returns_400():
    """GM-12: PATCH /governance-metadata returns 400 when trust_score > 1.0."""
    proc, hp = _start_relay(_BASE_PORT + 22)
    try:
        status, resp = _patch(hp, "/governance-metadata", {"trust_score": 1.5})
        assert status == 400, f"Expected 400, got {status}"
        assert "error" in resp
    finally:
        _stop(proc)


# ─── GM-13 ─────────────────────────────────────────────────────────────────────

def test_gm13_invalid_policy_compliance_returns_400():
    """GM-13: PATCH /governance-metadata returns 400 when policy_compliance is not an array."""
    proc, hp = _start_relay(_BASE_PORT + 24)
    try:
        status, resp = _patch(hp, "/governance-metadata", {"policy_compliance": "not-a-list"})
        assert status == 400, f"Expected 400, got {status}"
        assert "error" in resp
    finally:
        _stop(proc)


# ─── GM-14 ─────────────────────────────────────────────────────────────────────

def test_gm14_endpoint_listed_in_agentcard():
    """GM-14: AgentCard.endpoints.governance_metadata = '/governance-metadata'."""
    proc, hp = _start_relay(_BASE_PORT + 26)
    try:
        status, _raw = _get(hp, "/.well-known/acp.json")
        card = _raw.get("self") or _raw
        assert status == 200
        endpoints = card.get("endpoints", {})
        assert "governance_metadata" in endpoints, "governance_metadata endpoint should be in AgentCard.endpoints"
        assert endpoints["governance_metadata"] == "/governance-metadata"
    finally:
        _stop(proc)
