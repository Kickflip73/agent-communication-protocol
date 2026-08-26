"""
test_capability_token_detail_v274.py
=====================================
Tests for GET /trust/signals/capability-token (v2.74).

Aligned with A2A #1716 (SINT PR#111) — canonical capability token declaration
at the AgentSkill boundary.

Test IDs: CT-01..CT-20
"""

import pytest
import subprocess
import time
import requests
import socket
import os
import sys

RELAY = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def relay_proc():
    """Start a relay without identity (no Ed25519 key)."""
    ws_port = _free_port()
    http_port = ws_port + 100
    proc = subprocess.Popen(
        [sys.executable, RELAY, "--local", "--port", str(ws_port),
         "--name", "TestRelayV274", "--no-identity"],  # v2.85+: Ed25519 on by default; opt out explicitly
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    time.sleep(1.5)
    yield http_port, proc
    proc.terminate()
    proc.wait(timeout=5)


@pytest.fixture(scope="module")
def base_url(relay_proc):
    http_port, _ = relay_proc
    return f"http://localhost:{http_port}"


# ── CT-01: endpoint returns 200 ──────────────────────────────────────────────

def test_ct01_status_200(base_url):
    r = requests.get(f"{base_url}/trust/signals/capability-token", timeout=5)
    assert r.status_code == 200


# ── CT-02: ok=True ───────────────────────────────────────────────────────────

def test_ct02_ok_true(base_url):
    r = requests.get(f"{base_url}/trust/signals/capability-token", timeout=5)
    assert r.json()["ok"] is True


# ── CT-03: enabled=False (no identity loaded) ────────────────────────────────

def test_ct03_enabled_false_without_identity(base_url):
    data = requests.get(f"{base_url}/trust/signals/capability-token", timeout=5).json()
    assert data["enabled"] is False


# ── CT-04: issuer_did is None without identity ───────────────────────────────

def test_ct04_issuer_did_none_without_identity(base_url):
    data = requests.get(f"{base_url}/trust/signals/capability-token", timeout=5).json()
    assert data["issuer_did"] is None


# ── CT-05: scheme is sint_ed25519 ────────────────────────────────────────────

def test_ct05_scheme_sint_ed25519(base_url):
    data = requests.get(f"{base_url}/trust/signals/capability-token", timeout=5).json()
    assert data["scheme"] == "sint_ed25519"


# ── CT-06: algorithm is Ed25519 ──────────────────────────────────────────────

def test_ct06_algorithm_ed25519(base_url):
    data = requests.get(f"{base_url}/trust/signals/capability-token", timeout=5).json()
    assert data["algorithm"] == "Ed25519"


# ── CT-07: format is SINT ────────────────────────────────────────────────────

def test_ct07_format_sint(base_url):
    data = requests.get(f"{base_url}/trust/signals/capability-token", timeout=5).json()
    assert data["format"] == "SINT"


# ── CT-08: supported_tiers includes T0..T3 ───────────────────────────────────

def test_ct08_supported_tiers(base_url):
    data = requests.get(f"{base_url}/trust/signals/capability-token", timeout=5).json()
    tiers = data["supported_tiers"]
    assert set(tiers) == {"T0", "T1", "T2", "T3"}


# ── CT-09: sint_fields.required present ──────────────────────────────────────

def test_ct09_sint_fields_required(base_url):
    data = requests.get(f"{base_url}/trust/signals/capability-token", timeout=5).json()
    required = data["sint_fields"]["required"]
    for field in ("jti", "iss", "sub", "resource", "tier", "iat", "exp",
                  "signature", "public_key"):
        assert field in required, f"missing required SINT field: {field}"


# ── CT-10: sint_fields.optional present ──────────────────────────────────────

def test_ct10_sint_fields_optional(base_url):
    data = requests.get(f"{base_url}/trust/signals/capability-token", timeout=5).json()
    optional = data["sint_fields"]["optional"]
    assert "actions" in optional
    assert "constraints" in optional


# ── CT-11: default_ttl_seconds is 3600 ───────────────────────────────────────

def test_ct11_default_ttl_3600(base_url):
    data = requests.get(f"{base_url}/trust/signals/capability-token", timeout=5).json()
    assert data["default_ttl_seconds"] == 3600


# ── CT-12: endpoint_issue present ────────────────────────────────────────────

def test_ct12_endpoint_issue_present(base_url):
    data = requests.get(f"{base_url}/trust/signals/capability-token", timeout=5).json()
    assert "/skills/" in data["endpoint_issue"]
    assert "capability-token" in data["endpoint_issue"]


# ── CT-13: endpoint_verify present ───────────────────────────────────────────

def test_ct13_endpoint_verify_present(base_url):
    data = requests.get(f"{base_url}/trust/signals/capability-token", timeout=5).json()
    assert "/verify/external-token" in data["endpoint_verify"]


# ── CT-14: token_required_skills is a list ───────────────────────────────────

def test_ct14_token_required_skills_list(base_url):
    data = requests.get(f"{base_url}/trust/signals/capability-token", timeout=5).json()
    assert isinstance(data["token_required_skills"], list)


# ── CT-15: token_required_count matches list length ──────────────────────────

def test_ct15_token_required_count_matches(base_url):
    data = requests.get(f"{base_url}/trust/signals/capability-token", timeout=5).json()
    assert data["token_required_count"] == len(data["token_required_skills"])


# ── CT-16: active_tokens is int >= 0 ─────────────────────────────────────────

def test_ct16_active_tokens_int(base_url):
    data = requests.get(f"{base_url}/trust/signals/capability-token", timeout=5).json()
    assert isinstance(data["active_tokens"], int)
    assert data["active_tokens"] >= 0


# ── CT-17: total_issued is int >= 0 ──────────────────────────────────────────

def test_ct17_total_issued_int(base_url):
    data = requests.get(f"{base_url}/trust/signals/capability-token", timeout=5).json()
    assert isinstance(data["total_issued"], int)
    assert data["total_issued"] >= 0


# ── CT-18: note contains SINT reference ──────────────────────────────────────

def test_ct18_note_sint_reference(base_url):
    data = requests.get(f"{base_url}/trust/signals/capability-token", timeout=5).json()
    assert "SINT" in data["note"]


# ── CT-19: a2a_ref links to #1716 ────────────────────────────────────────────

def test_ct19_a2a_ref_1716(base_url):
    data = requests.get(f"{base_url}/trust/signals/capability-token", timeout=5).json()
    assert "1716" in data["a2a_ref"]


# ── CT-20: version matches relay VERSION ─────────────────────────────────────

def test_ct20_version_274(base_url):
    data = requests.get(f"{base_url}/trust/signals/capability-token", timeout=5).json()
    assert data["version"] >= "2.74"  # v2.75+ still satisfies this test


# ── CT-21: POST returns 4xx (non-200) — endpoint is GET-only ─────────────────

def test_ct21_post_returns_4xx(base_url):
    """POST to a GET-only endpoint should return a 4xx error."""
    r = requests.post(f"{base_url}/trust/signals/capability-token",
                      json={}, timeout=5)
    assert r.status_code in (404, 405), (
        f"Expected 404 or 405 for POST to GET-only endpoint, got {r.status_code}"
    )


# ── CT-22: AgentCard capabilities includes capability_token_detail=True ───────

def test_ct22_agent_card_capabilities(base_url):
    r = requests.get(f"{base_url}/.well-known/acp.json", timeout=5)
    assert r.status_code == 200
    card = r.json().get("self", {})
    caps = card.get("capabilities", {})
    assert caps.get("capability_token_detail") is True


# ── CT-23: AgentCard endpoints includes capability_token_detail ───────────────

def test_ct23_agent_card_endpoints(base_url):
    r = requests.get(f"{base_url}/.well-known/acp.json", timeout=5)
    card = r.json().get("self", {})
    endpoints = card.get("endpoints", {})
    assert "capability_token_detail" in endpoints
    assert "/trust/signals/capability-token" in endpoints["capability_token_detail"]


# ── CT-24: agent_name in response matches relay agent name ───────────────────

def test_ct24_agent_name_present(base_url):
    data = requests.get(f"{base_url}/trust/signals/capability-token", timeout=5).json()
    assert data["agent_name"] == "TestRelayV274"


# ── CT-25: active_tokens <= total_issued ─────────────────────────────────────

def test_ct25_active_lte_total(base_url):
    data = requests.get(f"{base_url}/trust/signals/capability-token", timeout=5).json()
    assert data["active_tokens"] <= data["total_issued"]
