"""
test_capability_token_fixtures_v275.py
=======================================
Tests for GET /trust/signals/capability-token/fixtures (v2.75).

Canonical authorization fixture endpoint — minimal vector set proposed by
@pshkv in A2A #1716: 4 deny scenarios + 1 allow scenario.

Test IDs: CF-01..CF-20
"""

import pytest
import subprocess
import time
import requests
import socket
import os
import sys

RELAY = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")
ENDPOINT = "/trust/signals/capability-token/fixtures"


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
         "--name", "TestRelayV275"],
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


@pytest.fixture(scope="module")
def fixture_data(base_url):
    """Cache the fixture response for all tests."""
    r = requests.get(f"{base_url}{ENDPOINT}", timeout=5)
    assert r.status_code == 200
    return r.json()


# ── CF-01: endpoint returns 200 ──────────────────────────────────────────────

def test_cf01_status_200(base_url):
    """GET /trust/signals/capability-token/fixtures returns HTTP 200."""
    r = requests.get(f"{base_url}{ENDPOINT}", timeout=5)
    assert r.status_code == 200


# ── CF-02: ok=True ───────────────────────────────────────────────────────────

def test_cf02_ok_true(fixture_data):
    """Response envelope has ok=True."""
    assert fixture_data.get("ok") is True


# ── CF-03: top-level structure has allow and deny arrays ──────────────────────

def test_cf03_has_allow_and_deny_arrays(fixture_data):
    """Response contains 'allow' and 'deny' top-level arrays."""
    assert "allow" in fixture_data
    assert "deny" in fixture_data
    assert isinstance(fixture_data["allow"], list)
    assert isinstance(fixture_data["deny"], list)


# ── CF-04: exactly 1 allow scenario ─────────────────────────────────────────

def test_cf04_one_allow_scenario(fixture_data):
    """Canonical fixture has exactly 1 allow scenario (minimal vector set)."""
    assert len(fixture_data["allow"]) == 1


# ── CF-05: exactly 4 deny scenarios ─────────────────────────────────────────

def test_cf05_four_deny_scenarios(fixture_data):
    """Canonical fixture has exactly 4 deny scenarios (minimal vector set)."""
    assert len(fixture_data["deny"]) == 4


# ── CF-06: fixture_count metadata is correct ─────────────────────────────────

def test_cf06_fixture_count(fixture_data):
    """fixture_count.allow/deny/total reflect actual array lengths."""
    fc = fixture_data.get("fixture_count", {})
    assert fc.get("allow") == 1
    assert fc.get("deny") == 4
    assert fc.get("total") == 5


# ── CF-07: allow scenario has verdict=allow ──────────────────────────────────

def test_cf07_allow_verdict(fixture_data):
    """The allow scenario has verdict='allow'."""
    allow = fixture_data["allow"][0]
    assert allow.get("verdict") == "allow"


# ── CF-08: allow scenario expected_result.authorized=True ────────────────────

def test_cf08_allow_authorized_true(fixture_data):
    """Allow scenario expected_result.authorized is True."""
    allow = fixture_data["allow"][0]
    assert allow.get("expected_result", {}).get("authorized") is True


# ── CF-09: all deny scenarios have verdict=deny ──────────────────────────────

def test_cf09_deny_verdicts(fixture_data):
    """All deny scenarios have verdict='deny'."""
    for d in fixture_data["deny"]:
        assert d.get("verdict") == "deny", f"Expected deny, got: {d.get('verdict')} in {d.get('id')}"


# ── CF-10: deny_reasons_covered includes all 4 required reasons ──────────────

def test_cf10_deny_reasons_covered(fixture_data):
    """deny_reasons_covered lists all 4 required denial reasons."""
    covered = set(fixture_data.get("deny_reasons_covered", []))
    required = {"scope_mismatch", "expired_toctou", "skill_id_mismatch", "subject_mismatch"}
    assert required.issubset(covered), f"Missing deny reasons: {required - covered}"


# ── CF-11: scope_mismatch deny scenario present ──────────────────────────────

def test_cf11_scope_mismatch_present(fixture_data):
    """A deny scenario with deny_reason='scope_mismatch' exists."""
    reasons = [d.get("deny_reason") for d in fixture_data["deny"]]
    assert "scope_mismatch" in reasons


# ── CF-12: expired_toctou deny scenario present ──────────────────────────────

def test_cf12_expired_toctou_present(fixture_data):
    """A deny scenario with deny_reason='expired_toctou' exists."""
    reasons = [d.get("deny_reason") for d in fixture_data["deny"]]
    assert "expired_toctou" in reasons


# ── CF-13: skill_id_mismatch deny scenario present ───────────────────────────

def test_cf13_skill_id_mismatch_present(fixture_data):
    """A deny scenario with deny_reason='skill_id_mismatch' exists."""
    reasons = [d.get("deny_reason") for d in fixture_data["deny"]]
    assert "skill_id_mismatch" in reasons


# ── CF-14: subject_mismatch deny scenario present ────────────────────────────

def test_cf14_subject_mismatch_present(fixture_data):
    """A deny scenario with deny_reason='subject_mismatch' exists."""
    reasons = [d.get("deny_reason") for d in fixture_data["deny"]]
    assert "subject_mismatch" in reasons


# ── CF-15: all deny scenarios have expected_result.authorized=False ───────────

def test_cf15_deny_authorized_false(fixture_data):
    """All deny scenarios have expected_result.authorized=False."""
    for d in fixture_data["deny"]:
        assert d.get("expected_result", {}).get("authorized") is False, \
            f"Expected authorized=False in deny scenario: {d.get('id')}"


# ── CF-16: all deny scenarios have expected_result.http_status=403 ───────────

def test_cf16_deny_http_status_403(fixture_data):
    """All deny scenarios have expected_result.http_status=403."""
    for d in fixture_data["deny"]:
        assert d.get("expected_result", {}).get("http_status") == 403, \
            f"Expected http_status=403 in deny scenario: {d.get('id')}"


# ── CF-17: all fixtures have unique IDs ──────────────────────────────────────

def test_cf17_unique_fixture_ids(fixture_data):
    """All fixture IDs (allow + deny) are unique."""
    all_ids = [f.get("id") for f in fixture_data["allow"] + fixture_data["deny"]]
    assert len(all_ids) == len(set(all_ids)), f"Duplicate fixture IDs found: {all_ids}"


# ── CF-18: all fixtures have token objects ────────────────────────────────────

def test_cf18_all_fixtures_have_token(fixture_data):
    """Every fixture (allow and deny) has a 'token' object."""
    for f in fixture_data["allow"] + fixture_data["deny"]:
        assert "token" in f, f"Missing token in fixture: {f.get('id')}"
        assert isinstance(f["token"], dict)


# ── CF-19: version is reported as 2.75.0 ─────────────────────────────────────

def test_cf19_version_275(fixture_data):
    """Response version is >= 2.75.0."""
    assert fixture_data.get("version") >= "2.75"


# ── CF-20: non-GET methods are rejected ──────────────────────────────────────

def test_cf20_method_not_allowed(base_url):
    """POST to fixture endpoint returns a non-200 error status (GET-only endpoint).

    The relay routes GET and POST through separate handlers; a POST to a
    GET-only path may return 404 (no POST handler) or 405 (explicit method
    check).  Either is acceptable — what matters is that the caller is not
    given a 2xx success response.
    """
    r = requests.post(f"{base_url}{ENDPOINT}", json={}, timeout=5)
    assert r.status_code in (404, 405), \
        f"Expected 404 or 405 for POST to GET-only endpoint, got {r.status_code}"
