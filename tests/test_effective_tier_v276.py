"""
test_effective_tier_v276.py — ACP v2.76: Factor 5 bilateral_ir_adj tests

Tests for the 5th factor in effective_tier computation:
  attestation_history_adjustment from local bilateral IR log (A2A #1716 @64R3N)

ET-01..ET-30
"""
import pytest
import time
import json
import requests
import subprocess
import socket
import os
import sys

RELAY_PATH = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")

_SKILLS_JSON = json.dumps([
    {
        "id": "tier-test-skill",
        "name": "Tier Test Skill",
        "description": "ET v2.76 test",
        "authorization_tier": "T2",
        "capability_token_required": False,
    }
])


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_relay(skills_json=_SKILLS_JSON, name="TestRelayV276"):
    ws_port = _free_port()
    http_port = ws_port + 100
    proc = subprocess.Popen(
        [sys.executable, RELAY_PATH, "--port", str(ws_port), "--name", name,
         "--skills", skills_json],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    base = f"http://127.0.0.1:{http_port}"
    for _ in range(50):
        try:
            requests.get(f"{base}/.well-known/acp.json", timeout=0.5)
            return proc, base
        except Exception:
            time.sleep(0.2)
    proc.kill()
    raise RuntimeError(f"Relay HTTP:{http_port} did not start")


# ── Module-scoped fixtures ──────────────────────────────────────────────────

@pytest.fixture(scope="module")
def relay_proc():
    proc, base = _start_relay()
    yield base
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except Exception:
        proc.kill()
        proc.wait(timeout=3)


@pytest.fixture(scope="module")
def relay(relay_proc):
    return relay_proc


@pytest.fixture(scope="module")
def skill_id():
    return "tier-test-skill"


# ── ET-01..ET-05: /well-known + capabilities ────────────────────────────────

def test_et01_version_276(relay):
    r = requests.get(f"{relay}/.well-known/acp.json", timeout=5)
    assert r.status_code == 200
    acp_ver = r.json().get("self", {}).get("acp_version", "")
    assert acp_ver >= "2.76"


def test_et02_capability_five_factors(relay):
    r = requests.get(f"{relay}/.well-known/acp.json", timeout=5)
    caps = r.json().get("self", {}).get("capabilities", {})
    assert caps.get("effective_tier_five_factors") is True


def test_et03_capability_effective_tier_computation(relay):
    r = requests.get(f"{relay}/.well-known/acp.json", timeout=5)
    caps = r.json().get("self", {}).get("capabilities", {})
    assert caps.get("effective_tier_computation") is True


def test_et04_effective_tier_endpoint_present(relay, skill_id):
    r = requests.get(f"{relay}/skills/{skill_id}/effective-tier", timeout=5)
    assert r.status_code == 200


def test_et05_factors_field_count(relay, skill_id):
    r = requests.get(f"{relay}/skills/{skill_id}/effective-tier", timeout=5)
    factors = r.json().get("factors", {})
    assert factors.get("factor_count") == 5


# ── ET-06..ET-10: bilateral_ir_adj field presence ──────────────────────────

def test_et06_bilateral_ir_adj_present(relay, skill_id):
    r = requests.get(f"{relay}/skills/{skill_id}/effective-tier", timeout=5)
    factors = r.json().get("factors", {})
    assert "bilateral_ir_adj" in factors


def test_et07_bilateral_ir_count_present(relay, skill_id):
    r = requests.get(f"{relay}/skills/{skill_id}/effective-tier", timeout=5)
    factors = r.json().get("factors", {})
    assert "bilateral_ir_count" in factors


def test_et08_bilateral_ir_merkle_root_field_present(relay, skill_id):
    r = requests.get(f"{relay}/skills/{skill_id}/effective-tier", timeout=5)
    factors = r.json().get("factors", {})
    assert "bilateral_ir_merkle_root" in factors


def test_et09_unknown_peer_bilateral_adj_is_positive(relay, skill_id):
    """Unknown peer (no bilateral records) should produce bilateral_ir_adj=+1."""
    r = requests.get(f"{relay}/skills/{skill_id}/effective-tier",
                     params={"peer_id": "did:key:z6MkBrandNewPeer00000"},
                     timeout=5)
    factors = r.json().get("factors", {})
    assert factors["bilateral_ir_adj"] == 1


def test_et10_unknown_peer_bilateral_count_is_zero(relay, skill_id):
    r = requests.get(f"{relay}/skills/{skill_id}/effective-tier",
                     params={"peer_id": "did:key:z6MkBrandNewPeer00000"},
                     timeout=5)
    factors = r.json().get("factors", {})
    assert factors["bilateral_ir_count"] == 0


# ── ET-11..ET-15: merkle root ────────────────────────────────────────────────

def test_et11_unknown_peer_merkle_root_is_null(relay, skill_id):
    """No bilateral records → no merkle root."""
    r = requests.get(f"{relay}/skills/{skill_id}/effective-tier",
                     params={"peer_id": "did:key:z6MkNullMerkle"},
                     timeout=5)
    factors = r.json().get("factors", {})
    assert factors["bilateral_ir_merkle_root"] is None


def test_et12_bilateral_ir_merkle_root_no_records():
    """Direct module test: _bilateral_ir_merkle_root returns None when no records."""
    import relay.acp_relay as r
    assert r._bilateral_ir_merkle_root("did:key:z6MkNoRecords") is None


def test_et13_bilateral_ir_adj_module_unknown_peer():
    import relay.acp_relay as r
    adj, count, merkle, _ = r._bilateral_ir_adj("did:key:z6MkUnknown")
    assert adj == 1
    assert count == 0
    assert merkle is None


def test_et14_bilateral_ir_adj_module_none_peer():
    """None peer_id → unknown → +1."""
    import relay.acp_relay as r
    adj, count, merkle, _ = r._bilateral_ir_adj(None)
    assert adj == 1
    assert count == 0


def test_et15_merkle_root_with_synthetic_records():
    """Inject synthetic bilateral records and verify merkle root is non-null 64-char hex."""
    import relay.acp_relay as r
    peer = "did:key:z6MkSyntheticMerkle01"
    r._interaction_records.append({
        "id": "ir-syn-01", "timestamp": "2026-04-07T09:00:00Z",
        "skill_id": "s1", "bilateral": True, "peer_id": peer, "caller_did": peer,
    })
    r._interaction_records.append({
        "id": "ir-syn-02", "timestamp": "2026-04-07T09:01:00Z",
        "skill_id": "s1", "bilateral": True, "peer_id": peer, "caller_did": peer,
    })
    root = r._bilateral_ir_merkle_root(peer)
    assert root is not None
    assert len(root) == 64  # SHA-256 hex
    # Cleanup
    r._interaction_records[:] = [
        rec for rec in r._interaction_records
        if rec.get("id") not in ("ir-syn-01", "ir-syn-02")
    ]


# ── ET-16..ET-20: adj thresholds ─────────────────────────────────────────────

def test_et16_one_record_neutral():
    """1 bilateral record → adj=0 (neutral)."""
    import relay.acp_relay as r
    peer = "did:key:z6MkOneRecord"
    r._interaction_records.append({
        "id": "ir-one-01", "timestamp": "2026-04-07T09:00:00Z",
        "skill_id": "s1", "bilateral": True, "peer_id": peer, "caller_did": peer,
    })
    adj, count, _, _div = r._bilateral_ir_adj(peer)
    assert adj == 0
    assert count == 1
    r._interaction_records[:] = [
        rec for rec in r._interaction_records if rec.get("id") != "ir-one-01"
    ]


def test_et17_four_records_neutral():
    """4 bilateral records → adj=0 (neutral, threshold not yet reached)."""
    import relay.acp_relay as r
    peer = "did:key:z6MkFourRecords"
    for i in range(4):
        r._interaction_records.append({
            "id": f"ir-four-{i:02d}", "timestamp": f"2026-04-07T09:0{i}:00Z",
            "skill_id": "s1", "bilateral": True, "peer_id": peer, "caller_did": peer,
        })
    adj, count, _, _div = r._bilateral_ir_adj(peer)
    assert adj == 0
    assert count == 4
    r._interaction_records[:] = [
        rec for rec in r._interaction_records
        if not rec.get("id", "").startswith("ir-four-")
    ]


def test_et18_five_records_minus_one():
    """5 bilateral records → adj=-1 (established peer, may lower floor)."""
    import relay.acp_relay as r
    peer = "did:key:z6MkFiveRecords"
    for i in range(5):
        r._interaction_records.append({
            "id": f"ir-five-{i:02d}", "timestamp": f"2026-04-07T09:0{i}:00Z",
            "skill_id": "s1", "bilateral": True, "peer_id": peer, "caller_did": peer,
        })
    adj, count, _, _div = r._bilateral_ir_adj(peer)
    assert adj == -1
    assert count == 5
    r._interaction_records[:] = [
        rec for rec in r._interaction_records
        if not rec.get("id", "").startswith("ir-five-")
    ]


def test_et19_ten_records_minus_one():
    """10 bilateral records → adj=-1 (max benefit)."""
    import relay.acp_relay as r
    peer = "did:key:z6MkTenRecords"
    for i in range(10):
        r._interaction_records.append({
            "id": f"ir-ten-{i:02d}", "timestamp": f"2026-04-07T09:{i:02d}:00Z",
            "skill_id": "s1", "bilateral": True, "peer_id": peer, "caller_did": peer,
        })
    adj, count, _, _div = r._bilateral_ir_adj(peer)
    assert adj == -1
    assert count == 10
    r._interaction_records[:] = [
        rec for rec in r._interaction_records
        if not rec.get("id", "").startswith("ir-ten-")
    ]


def test_et20_non_bilateral_records_not_counted():
    """bilateral=False records must NOT count toward the threshold."""
    import relay.acp_relay as r
    peer = "did:key:z6MkNonBilateral"
    for i in range(10):
        r._interaction_records.append({
            "id": f"ir-nb-{i:02d}", "timestamp": f"2026-04-07T09:{i:02d}:00Z",
            "skill_id": "s1", "bilateral": False, "peer_id": peer, "caller_did": peer,
        })
    adj, count, _, _div = r._bilateral_ir_adj(peer)
    assert adj == 1   # no bilateral records → unknown → +1
    assert count == 0
    r._interaction_records[:] = [
        rec for rec in r._interaction_records
        if not rec.get("id", "").startswith("ir-nb-")
    ]


# ── ET-21..ET-25: combined_adj five-factor logic ─────────────────────────────

def test_et21_any_plus_one_overrides():
    """bilateral_ir_adj=+1 → combined_adj >= 0 (conservative override)."""
    import relay.acp_relay as r
    peer = "did:key:z6MkPlusOneOverride"
    # No bilateral records → bilateral_ir_adj=+1
    r._interaction_records[:] = [
        rec for rec in r._interaction_records if rec.get("peer_id") != peer
    ]
    _et, factors = r._compute_effective_tier(
        {"authorization_tier": "T2", "capability_token_required": False}, peer
    )
    assert factors["combined_adj"] >= 0


def test_et22_two_neg_required_for_minus_one():
    """Only bilateral_ir_adj=-1, others neutral → combined=0 (need ≥2 of 3 negatives)."""
    import relay.acp_relay as r
    peer = "did:key:z6MkTwoNegReq"
    # 5 bilateral records → bilateral_ir_adj=-1; no peer card → reputation_adj=+1 (unknown in _peers)
    for i in range(5):
        r._interaction_records.append({
            "id": f"ir-2neg-{i:02d}", "timestamp": f"2026-04-07T11:{i:02d}:00Z",
            "skill_id": "s1", "bilateral": True, "peer_id": peer, "caller_did": peer,
        })
    _et, factors = r._compute_effective_tier(
        {"authorization_tier": "T2", "capability_token_required": False}, peer
    )
    # rep_adj=+1 (unknown in _peers) overrides → combined >= 0
    assert factors["combined_adj"] >= 0
    assert factors["bilateral_ir_adj"] == -1
    r._interaction_records[:] = [
        rec for rec in r._interaction_records
        if not rec.get("id", "").startswith("ir-2neg-")
    ]


def test_et23_factor_count_always_five():
    """_compute_effective_tier always returns factor_count=5."""
    import relay.acp_relay as r
    _et, factors = r._compute_effective_tier(
        {"authorization_tier": "T1", "capability_token_required": False}, None
    )
    assert factors["factor_count"] == 5


def test_et24_t3_immune_to_all_factors():
    """T3 skills always compute effective_tier=T3 regardless of adj factors."""
    import relay.acp_relay as r
    _et, factors = r._compute_effective_tier(
        {"authorization_tier": "T3", "capability_token_required": False}, None
    )
    assert factors["effective_tier"] == "T3"


def test_et25_bilateral_ir_all_three_keys():
    """factors dict always contains all three bilateral_ir fields."""
    import relay.acp_relay as r
    _et, factors = r._compute_effective_tier(
        {"authorization_tier": "T0", "capability_token_required": False},
        "did:key:z6MkAnyPeer"
    )
    assert "bilateral_ir_adj" in factors
    assert "bilateral_ir_count" in factors
    assert "bilateral_ir_merkle_root" in factors


# ── ET-26..ET-30: integration via HTTP ───────────────────────────────────────

def test_et26_http_bilateral_ir_adj_present(relay, skill_id):
    r = requests.get(f"{relay}/skills/{skill_id}/effective-tier", timeout=5)
    assert "bilateral_ir_adj" in r.json().get("factors", {})


def test_et27_http_bilateral_ir_count_non_negative(relay, skill_id):
    r = requests.get(f"{relay}/skills/{skill_id}/effective-tier", timeout=5)
    assert r.json()["factors"]["bilateral_ir_count"] >= 0


def test_et28_http_bilateral_ir_merkle_root_type(relay, skill_id):
    """bilateral_ir_merkle_root must be None or 64-char hex string."""
    r = requests.get(f"{relay}/skills/{skill_id}/effective-tier", timeout=5)
    merkle = r.json()["factors"]["bilateral_ir_merkle_root"]
    assert merkle is None or (isinstance(merkle, str) and len(merkle) == 64)


def test_et29_http_factor_count_five(relay, skill_id):
    r = requests.get(f"{relay}/skills/{skill_id}/effective-tier", timeout=5)
    assert r.json().get("factors", {}).get("factor_count") == 5


def test_et30_http_effective_tier_in_response(relay, skill_id):
    """effective_tier key must be present in the response."""
    r = requests.get(f"{relay}/skills/{skill_id}/effective-tier", timeout=5)
    data = r.json()
    assert "effective_tier" in data
    assert data.get("skill_id") == skill_id
