"""
ACP v2.78 — POST /trust/signals/capability-token/revoke
         + GET /trust/signals/capability-token/revocations
         + validate endpoint revocation check (Check 6)
SINT token active revocation — completes SINT lifecycle quad.
RV-01 .. RV-30
"""

import json
import time
import subprocess
import sys
import os
import pytest
import requests

PORT     = 18802
HTTP     = 18902
BASE_URL = f"http://localhost:{HTTP}"

RELAY_PY  = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")
REVOKE    = f"{BASE_URL}/trust/signals/capability-token/revoke"
REVOKE_LIST = f"{BASE_URL}/trust/signals/capability-token/revocations"
VALIDATE  = f"{BASE_URL}/trust/signals/capability-token/fixtures/validate"
CARD      = f"{BASE_URL}/.well-known/acp.json"


@pytest.fixture(scope="module")
def relay():
    proc = subprocess.Popen(
        [sys.executable, RELAY_PY, "--port", str(PORT), "--name", "test-v278", "--test-mode"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(3.5)
    yield proc
    proc.terminate()
    proc.wait()


def _now():
    return int(time.time())


def _revoke(jti, reason=None, revoked_by=None):
    body = {"jti": jti}
    if reason:     body["reason"]     = reason
    if revoked_by: body["revoked_by"] = revoked_by
    return requests.post(REVOKE, json=body, timeout=5)


def _validate(token, ctx=None):
    body = {"token": token}
    if ctx:
        body["invocation_context"] = ctx
    return requests.post(VALIDATE, json=body, timeout=5)


def _good_token(jti=None, sub="did:key:zSub", skill="demo"):
    return {
        "jti":      jti or f"urn:acp:rv:{_now()}",
        "iss":      "did:key:zIss",
        "sub":      sub,
        "resource": f"acp://relay/skills/{skill}",
        "scheme":   "sint_ed25519",
        "exp":      _now() + 3600,
    }


# ─── RV-01..RV-05: Basic revocation ───────────────────────────────────────────

def test_rv01_revoke_basic(relay):
    """RV-01: POST /revoke with valid jti returns ok=true revoked=true."""
    r = _revoke("jti-rv01")
    d = r.json()
    assert r.status_code == 200
    assert d.get("ok") is True
    assert d.get("revoked") is True
    assert d.get("jti") == "jti-rv01"
    assert "revocation_id" in d
    assert "revoked_at" in d


def test_rv02_revoke_reason_field(relay):
    """RV-02: Reason field is stored and returned."""
    r = _revoke("jti-rv02", reason="compromised")
    d = r.json()
    assert d.get("ok") is True
    assert d.get("reason") == "compromised"


def test_rv03_revoke_revoked_by_field(relay):
    """RV-03: revoked_by field is stored and returned."""
    r = _revoke("jti-rv03", revoked_by="did:acp:admin")
    d = r.json()
    assert d.get("ok") is True
    assert d.get("revoked_by") == "did:acp:admin"


def test_rv04_revoke_default_reason_manual(relay):
    """RV-04: Default reason is 'manual' when not specified."""
    r = _revoke("jti-rv04")
    d = r.json()
    assert d.get("ok") is True
    assert d.get("reason") == "manual"


def test_rv05_revoke_default_revoked_by_relay(relay):
    """RV-05: Default revoked_by is 'relay' when not specified."""
    r = _revoke("jti-rv05")
    d = r.json()
    assert d.get("ok") is True
    assert d.get("revoked_by") == "relay"


# ─── RV-06..RV-10: Error cases ────────────────────────────────────────────────

def test_rv06_revoke_missing_jti_400(relay):
    """RV-06: Missing 'jti' returns 400."""
    r = requests.post(REVOKE, json={}, timeout=5)
    d = r.json()
    assert r.status_code == 400
    assert d.get("ok") is False
    assert d.get("code") == "ERR_BAD_REQUEST"


def test_rv07_revoke_already_revoked_409(relay):
    """RV-07: Revoking an already-revoked token returns 409 ERR_ALREADY_REVOKED."""
    _revoke("jti-rv07")
    r = _revoke("jti-rv07")
    d = r.json()
    assert r.status_code == 409
    assert d.get("ok") is False
    assert d.get("code") == "ERR_ALREADY_REVOKED"


def test_rv08_revoke_idempotent_409_contains_revocation_id(relay):
    """RV-08: 409 response includes the original revocation_id."""
    first = _revoke("jti-rv08").json()
    second = _revoke("jti-rv08").json()
    assert second.get("revocation_id") == first.get("revocation_id")


def test_rv09_revoke_empty_jti_400(relay):
    """RV-09: Empty jti string returns 400."""
    r = requests.post(REVOKE, json={"jti": ""}, timeout=5)
    d = r.json()
    assert r.status_code == 400
    assert d.get("ok") is False
    assert d.get("code") == "ERR_BAD_REQUEST"


def test_rv10_revoke_invalid_json_400(relay):
    """RV-10: Invalid JSON body returns 400."""
    r = requests.post(REVOKE, data=b"not-json",
                      headers={"Content-Type": "application/json"}, timeout=5)
    d = r.json()
    assert r.status_code == 400
    assert d.get("ok") is False


# ─── RV-11..RV-15: Revocation list ────────────────────────────────────────────

def test_rv11_revocations_endpoint_ok(relay):
    """RV-11: GET /revocations returns ok=true with list."""
    r = requests.get(REVOKE_LIST, timeout=5)
    d = r.json()
    assert r.status_code == 200
    assert d.get("ok") is True
    assert "total_revoked" in d
    assert isinstance(d.get("revocations"), list)


def test_rv12_revocations_increases_after_revoke(relay):
    """RV-12: total_revoked increases after a revocation."""
    before = requests.get(REVOKE_LIST, timeout=5).json().get("total_revoked", 0)
    _revoke(f"jti-rv12-{_now()}")
    after = requests.get(REVOKE_LIST, timeout=5).json().get("total_revoked", 0)
    assert after > before


def test_rv13_revocations_contains_revoked_jti(relay):
    """RV-13: Revoked jti appears in /revocations list."""
    jti = f"jti-rv13-{_now()}"
    _revoke(jti)
    resp = requests.get(REVOKE_LIST, timeout=5).json()
    jtis = [x.get("jti") for x in resp.get("revocations", [])]
    assert jti in jtis


def test_rv14_revocations_record_fields(relay):
    """RV-14: Each revocation record has required fields."""
    jti = f"jti-rv14-{_now()}"
    _revoke(jti, reason="policy_violation")
    resp = requests.get(REVOKE_LIST, timeout=5).json()
    record = next((x for x in resp.get("revocations", []) if x.get("jti") == jti), None)
    assert record is not None
    for field in ("jti", "revocation_id", "revoked_at", "reason", "revoked_by"):
        assert field in record, f"Missing field: {field}"


def test_rv15_revocations_version_and_a2a_ref(relay):
    """RV-15: GET /revocations response includes version and a2a_ref."""
    resp = requests.get(REVOKE_LIST, timeout=5).json()
    assert "version" in resp
    assert "a2a_ref" in resp
    assert "1716" in resp.get("a2a_ref", "")


# ─── RV-16..RV-20: Validate endpoint revocation check ────────────────────────

def test_rv16_validate_revoked_token_denied(relay):
    """RV-16: validate returns authorized=false for a revoked token."""
    jti = f"jti-rv16-{_now()}"
    token = _good_token(jti=jti)
    _revoke(jti)
    resp = _validate(token).json()
    assert resp.get("authorized") is False


def test_rv17_validate_revoked_check_in_checks_list(relay):
    """RV-17: validate response includes 'revocation' check in checks list."""
    jti = f"jti-rv17-{_now()}"
    token = _good_token(jti=jti)
    _revoke(jti)
    resp = _validate(token).json()
    check_names = [c.get("check") for c in resp.get("checks", [])]
    assert "revocation" in check_names


def test_rv18_validate_revocation_check_failed(relay):
    """RV-18: revocation check has passed=false + reason='token_revoked'."""
    jti = f"jti-rv18-{_now()}"
    token = _good_token(jti=jti)
    _revoke(jti)
    resp = _validate(token).json()
    rev_check = next((c for c in resp.get("checks", []) if c.get("check") == "revocation"), None)
    assert rev_check is not None
    assert rev_check.get("passed") is False
    assert rev_check.get("reason") == "token_revoked"


def test_rv19_validate_clean_token_revocation_check_passes(relay):
    """RV-19: Non-revoked token has revocation check passed=true."""
    token = _good_token(jti=f"jti-rv19-clean-{_now()}")
    resp = _validate(token).json()
    rev_check = next((c for c in resp.get("checks", []) if c.get("check") == "revocation"), None)
    assert rev_check is not None
    assert rev_check.get("passed") is True
    assert rev_check.get("reason") == "token_not_revoked"


def test_rv20_validate_deny_reason_is_token_revoked(relay):
    """RV-20: deny_reason for revoked token is 'token_revoked'."""
    jti = f"jti-rv20-{_now()}"
    token = _good_token(jti=jti)
    _revoke(jti)
    resp = _validate(token).json()
    assert resp.get("authorized") is False
    assert resp.get("deny_reason") == "token_revoked"


# ─── RV-21..RV-25: Revocation reasons + lifecycle ─────────────────────────────

def test_rv21_revoke_expired_reason(relay):
    """RV-21: Reason 'expired' is stored correctly."""
    r = _revoke(f"jti-rv21-{_now()}", reason="expired")
    d = r.json()
    assert d.get("ok") is True
    assert d.get("reason") == "expired"


def test_rv22_revoke_compromised_reason(relay):
    """RV-22: Reason 'compromised' is stored correctly."""
    r = _revoke(f"jti-rv22-{_now()}", reason="compromised")
    d = r.json()
    assert d.get("ok") is True
    assert d.get("reason") == "compromised"


def test_rv23_revoke_policy_violation_reason(relay):
    """RV-23: Reason 'policy_violation' is stored correctly."""
    r = _revoke(f"jti-rv23-{_now()}", reason="policy_violation")
    d = r.json()
    assert d.get("ok") is True
    assert d.get("reason") == "policy_violation"


def test_rv24_revoke_forward_revocation(relay):
    """RV-24: Forward revocation (unknown jti) is accepted, token_known=False."""
    jti = f"jti-rv24-future-{_now()}"
    r = _revoke(jti)
    d = r.json()
    assert d.get("ok") is True
    assert d.get("revoked") is True
    assert d.get("token_known") is False


def test_rv25_revoke_version_and_a2a_ref(relay):
    """RV-25: Revoke response includes version >= 2.78 and a2a_ref."""
    r = _revoke(f"jti-rv25-{_now()}")
    d = r.json()
    assert "version" in d
    assert "a2a_ref" in d
    assert "1716" in d.get("a2a_ref", "")
    major, minor, *_ = d["version"].split(".")
    assert (int(major), int(minor)) >= (2, 78)


# ─── RV-26..RV-30: SINT lifecycle integration ─────────────────────────────────

def test_rv26_sint_lifecycle_full(relay):
    """RV-26: Full lifecycle: validate OK → revoke → validate DENIED."""
    jti = f"jti-rv26-lifecycle-{_now()}"
    token = _good_token(jti=jti)
    # Before revocation: authorized
    resp1 = _validate(token).json()
    assert resp1.get("authorized") is True
    # Revoke
    _revoke(jti, reason="compromised")
    # After revocation: denied
    resp3 = _validate(token).json()
    assert resp3.get("authorized") is False
    assert resp3.get("deny_reason") == "token_revoked"


def test_rv27_revoke_multiple_jtis(relay):
    """RV-27: Multiple different JTIs can each be revoked independently."""
    for i in range(5):
        jti = f"jti-rv27-multi-{i}-{_now()}"
        r = _revoke(jti)
        d = r.json()
        assert d.get("ok") is True
        assert d.get("revoked") is True


def test_rv28_capabilities_reflect_v278(relay):
    """RV-28: AgentCard capabilities include capability_token_revoke=True."""
    r = requests.get(CARD, timeout=5)
    d = r.json()
    caps = d.get("self", d).get("capabilities", {})
    assert caps.get("capability_token_revoke") is True


def test_rv29_endpoints_reflect_v278(relay):
    """RV-29: AgentCard endpoints include revoke and revocations paths."""
    r = requests.get(CARD, timeout=5)
    d = r.json()
    endpoints = d.get("self", d).get("endpoints", {})
    assert "capability_token_revoke" in endpoints
    assert "capability_token_revocations" in endpoints


def test_rv30_version_is_2_78(relay):
    """RV-30: Relay VERSION is >= 2.78.x."""
    r = requests.get(CARD, timeout=5)
    d = r.json()
    version = d.get("self", d).get("version", "")
    major, minor, *_ = version.split(".")
    assert (int(major), int(minor)) >= (2, 78), f"Expected >= 2.78, got {version}"
