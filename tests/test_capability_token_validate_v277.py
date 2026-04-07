"""
ACP v2.77 — POST /trust/signals/capability-token/fixtures/validate
Dynamic SINT capability token validation endpoint tests.
TV-01 .. TV-30 (30 test cases)
"""

import json
import time
import subprocess
import sys
import os
import pytest
import requests

PORT     = 18801
HTTP     = 18901
BASE_URL = f"http://localhost:{HTTP}"

RELAY_PY = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")
VALIDATE  = f"{BASE_URL}/trust/signals/capability-token/fixtures/validate"


@pytest.fixture(scope="module")
def relay():
    proc = subprocess.Popen(
        [sys.executable, RELAY_PY, "--port", str(PORT), "--name", "test-v277", "--test-mode"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(3.5)
    yield proc
    proc.terminate()
    proc.wait()


def _now():
    return int(time.time())


def _good_token(sub="did:key:zSub", skill="demo", extra=None):
    t = {
        "jti":      "urn:acp:test:good",
        "iss":      "did:key:zIss",
        "sub":      sub,
        "resource": f"acp://relay/skills/{skill}",
        "scheme":   "sint_ed25519",
        "exp":      _now() + 3600,
        "iat":      _now() - 10,
        "actions":  ["invoke"],
    }
    if extra:
        t.update(extra)
    return t


def _post(token, ctx=None, relay_fixture=None):
    body = {"token": token}
    if ctx is not None:
        body["invocation_context"] = ctx
    r = requests.post(VALIDATE, json=body, timeout=5)
    return r


# ══════════════════════════════════════════════════
# TV-01..TV-05: endpoint availability & envelope
# ══════════════════════════════════════════════════

def _agent_card(base_url):
    """Helper: fetch AgentCard from .well-known/acp.json → returns self section."""
    r = requests.get(f"{base_url}/.well-known/acp.json", timeout=5)
    assert r.status_code == 200
    d = r.json()
    return d.get("self", d)  # prefer 'self' key; fall back to root for older layouts


def test_tv01_version_gte_277(relay):
    """TV-01: VERSION >= 2.77"""
    card = _agent_card(BASE_URL)
    ver = card.get("version", "0.0.0")
    parts = [int(x) for x in ver.split(".")[:2]]
    assert parts >= [2, 77], f"version too low: {ver}"


def test_tv02_capability_declared(relay):
    """TV-02: capability_token_validate=True in AgentCard capabilities"""
    card = _agent_card(BASE_URL)
    caps = card.get("capabilities", {})
    assert caps.get("capability_token_validate") is True


def test_tv03_endpoint_declared(relay):
    """TV-03: capability_token_validate endpoint in AgentCard endpoints"""
    card = _agent_card(BASE_URL)
    eps = card.get("endpoints", {})
    assert "capability_token_validate" in eps
    assert "validate" in eps["capability_token_validate"]


def test_tv04_get_returns_405(relay):
    """TV-04: GET /validate → 405 METHOD_NOT_ALLOWED"""
    r = requests.get(VALIDATE, timeout=5)
    assert r.status_code == 405
    assert r.json()["code"] == "ERR_METHOD_NOT_ALLOWED"


def test_tv05_envelope_fields(relay):
    """TV-05: response envelope has ok/version/authorized/checks/a2a_ref"""
    r = _post(_good_token(), {"target_skill_id": "demo"})
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert "version" in d
    assert "authorized" in d
    assert "checks" in d
    assert "a2a_ref" in d


# ══════════════════════════════════════════════════
# TV-06..TV-10: ALLOW scenarios
# ══════════════════════════════════════════════════

def test_tv06_allow_full_context(relay):
    """TV-06: Valid token + full context → authorized=True"""
    r = _post(
        _good_token(sub="did:key:zSub"),
        {"target_skill_id": "demo", "invoking_agent_did": "did:key:zSub"}
    )
    assert r.status_code == 200
    d = r.json()
    assert d["authorized"] is True
    assert d.get("reason_code") == "token_valid"


def test_tv07_allow_no_context(relay):
    """TV-07: Valid token, no invocation_context → authorized=True (checks skipped)"""
    r = _post(_good_token())
    assert r.status_code == 200
    assert r.json()["authorized"] is True


def test_tv08_allow_5_checks_present(relay):
    """TV-08: Full allow → exactly 5 checks in response"""
    r = _post(
        _good_token(sub="did:key:zSub"),
        {"target_skill_id": "demo", "invoking_agent_did": "did:key:zSub"}
    )
    d = r.json()
    assert len(d["checks"]) == 5


def test_tv09_allow_all_checks_passed(relay):
    """TV-09: Full allow → all checks passed=True"""
    r = _post(
        _good_token(sub="did:key:zSub"),
        {"target_skill_id": "demo", "invoking_agent_did": "did:key:zSub"}
    )
    d = r.json()
    assert all(c["passed"] for c in d["checks"])


def test_tv10_allow_check_names(relay):
    """TV-10: All 5 expected check names present"""
    r = _post(
        _good_token(sub="did:key:zSub"),
        {"target_skill_id": "demo", "invoking_agent_did": "did:key:zSub"}
    )
    names = {c["check"] for c in r.json()["checks"]}
    assert names == {"expiry", "scope", "skill_id", "subject", "required_fields"}


# ══════════════════════════════════════════════════
# TV-11..TV-15: DENY — expiry
# ══════════════════════════════════════════════════

def test_tv11_deny_expired_token(relay):
    """TV-11: Expired token → deny_reason=token_expired"""
    t = _good_token()
    t["exp"] = _now() - 10
    t["iat"] = _now() - 3700
    r = _post(t, {"target_skill_id": "demo"})
    assert r.status_code == 403
    d = r.json()
    assert d["authorized"] is False
    assert d["deny_reason"] == "token_expired"
    assert d["http_status"] == 403


def test_tv12_deny_toctou_scenario(relay):
    """TV-12: Token expired between check_time and use_time (TOCTOU) → token_expired"""
    t = _good_token()
    check_time = _now() - 10
    exp        = _now() - 5  # expired 5s ago
    use_time   = _now()
    t["exp"] = exp
    t["iat"] = exp - 3600
    r = _post(t, {"target_skill_id": "demo", "check_time": check_time, "use_time": use_time})
    assert r.status_code == 403
    assert r.json()["deny_reason"] == "token_expired"


def test_tv13_deny_missing_exp(relay):
    """TV-13: Token without exp field → deny"""
    t = _good_token()
    del t["exp"]
    r = _post(t, {"target_skill_id": "demo"})
    assert r.status_code == 403
    assert r.json()["authorized"] is False


def test_tv14_expiry_check_in_checks_list(relay):
    """TV-14: Expired → expiry check in checks with passed=False"""
    t = _good_token()
    t["exp"] = _now() - 10
    t["iat"] = _now() - 3700
    d = _post(t).json()
    expiry_check = next(c for c in d["checks"] if c["check"] == "expiry")
    assert expiry_check["passed"] is False


def test_tv15_expiry_priority_over_scope(relay):
    """TV-15: Both expired + scope_mismatch → deny_reason is expiry (priority)"""
    t = _good_token()
    t["exp"] = _now() - 10
    t["iat"] = _now() - 3700
    r = _post(t, {"target_skill_id": "other-skill"})
    assert r.json()["deny_reason"] == "token_expired"


# ══════════════════════════════════════════════════
# TV-16..TV-20: DENY — scope/skill_id
# ══════════════════════════════════════════════════

def test_tv16_deny_scope_mismatch(relay):
    """TV-16: Token resource=demo, target=other-skill → scope_mismatch"""
    r = _post(_good_token(skill="demo"), {"target_skill_id": "other-skill"})
    assert r.status_code == 403
    d = r.json()
    assert d["authorized"] is False
    assert d["deny_reason"] == "scope_mismatch"


def test_tv17_deny_skill_id_mismatch_explicit(relay):
    """TV-17: explicit_skill_id mismatch → skill_id_mismatch"""
    r = _post(
        _good_token(skill="demo"),
        {"target_skill_id": "demo", "explicit_skill_id": "premium-skill"}
    )
    assert r.status_code == 403
    assert r.json()["deny_reason"] == "skill_id_mismatch"


def test_tv18_scope_match_no_conflict(relay):
    """TV-18: resource=premium, target=premium → scope passes"""
    r = _post(
        _good_token(skill="premium"),
        {"target_skill_id": "premium", "invoking_agent_did": "did:key:zSub"}
    )
    d = r.json()
    scope_check = next(c for c in d["checks"] if c["check"] == "scope")
    assert scope_check["passed"] is True


def test_tv19_scope_check_in_deny_details(relay):
    """TV-19: scope_mismatch → appears in deny_details list"""
    r = _post(_good_token(skill="demo"), {"target_skill_id": "wrong"})
    d = r.json()
    assert any(dd["check"] == "scope" for dd in d.get("deny_details", []))


def test_tv20_deny_missing_resource(relay):
    """TV-20: Token without resource field → deny"""
    t = _good_token()
    del t["resource"]
    r = _post(t, {"target_skill_id": "demo"})
    assert r.status_code == 403
    assert r.json()["authorized"] is False


# ══════════════════════════════════════════════════
# TV-21..TV-25: DENY — subject
# ══════════════════════════════════════════════════

def test_tv21_deny_subject_mismatch(relay):
    """TV-21: token.sub=SubA, invoking=SubB → subject_mismatch"""
    r = _post(
        _good_token(sub="did:key:zSubA"),
        {"target_skill_id": "demo", "invoking_agent_did": "did:key:zSubB"}
    )
    assert r.status_code == 403
    d = r.json()
    assert d["authorized"] is False
    assert d["deny_reason"] == "subject_mismatch"


def test_tv22_subject_skipped_no_did(relay):
    """TV-22: No invoking_agent_did → subject check skipped (passes)"""
    r = _post(
        _good_token(sub="did:key:zSub"),
        {"target_skill_id": "demo"}
    )
    d = r.json()
    subj_check = next(c for c in d["checks"] if c["check"] == "subject")
    assert subj_check["passed"] is True
    assert subj_check["reason"] == "skipped_no_invoking_did"


def test_tv23_deny_missing_sub(relay):
    """TV-23: Token without sub field → deny (missing_sub_field)"""
    t = _good_token()
    del t["sub"]
    r = _post(t, {"target_skill_id": "demo", "invoking_agent_did": "did:key:zSub"})
    assert r.status_code == 403
    assert r.json()["authorized"] is False


def test_tv24_subject_check_in_deny_details(relay):
    """TV-24: subject_mismatch → appears in deny_details"""
    r = _post(
        _good_token(sub="did:key:zSubA"),
        {"target_skill_id": "demo", "invoking_agent_did": "did:key:zSubB"}
    )
    d = r.json()
    assert any(dd["check"] == "subject" for dd in d.get("deny_details", []))


def test_tv25_subject_match_self_invocation(relay):
    """TV-25: sub == invoking_did → subject check passes"""
    r = _post(
        _good_token(sub="did:key:zAgent42"),
        {"target_skill_id": "demo", "invoking_agent_did": "did:key:zAgent42"}
    )
    d = r.json()
    subj_check = next(c for c in d["checks"] if c["check"] == "subject")
    assert subj_check["passed"] is True


# ══════════════════════════════════════════════════
# TV-26..TV-30: required_fields / error handling / integration
# ══════════════════════════════════════════════════

def test_tv26_deny_missing_required_fields(relay):
    """TV-26: Token missing jti+iss → deny"""
    t = {"sub": "did:key:zSub", "resource": "acp://r/skills/demo", "scheme": "sint_ed25519",
         "exp": _now() + 3600, "iat": _now() - 10}
    r = _post(t)
    assert r.status_code == 403
    assert r.json()["authorized"] is False


def test_tv27_deny_empty_token(relay):
    """TV-27: Empty token object → deny"""
    r = _post({})
    assert r.status_code == 403
    assert r.json()["authorized"] is False


def test_tv28_bad_request_no_token_field(relay):
    """TV-28: Body missing 'token' key → 400"""
    r = requests.post(VALIDATE, json={"invocation_context": {}}, timeout=5)
    assert r.status_code == 400
    assert r.json()["code"] == "ERR_BAD_REQUEST"


def test_tv29_deny_canonical_fixture_scope_mismatch(relay):
    """TV-29: Apply canonical fixture deny_scope_mismatch from GET /fixtures → confirms deny"""
    fixtures = requests.get(f"{BASE_URL}/trust/signals/capability-token/fixtures", timeout=5).json()
    scope_fixture = next(f for f in fixtures["deny"] if f["id"] == "deny_scope_mismatch")
    r = _post(scope_fixture["token"], scope_fixture.get("invocation_context", {}))
    assert r.json()["authorized"] is False
    assert r.json()["deny_reason"] in ("scope_mismatch", "skill_id_mismatch")


def test_tv30_deny_canonical_fixture_subject_mismatch(relay):
    """TV-30: Apply canonical fixture deny_subject_mismatch from GET /fixtures → confirms deny"""
    fixtures = requests.get(f"{BASE_URL}/trust/signals/capability-token/fixtures", timeout=5).json()
    subj_fixture = next(f for f in fixtures["deny"] if f["id"] == "deny_subject_mismatch")
    r = _post(subj_fixture["token"], subj_fixture.get("invocation_context", {}))
    assert r.json()["authorized"] is False
    assert r.json()["deny_reason"] == "subject_mismatch"
