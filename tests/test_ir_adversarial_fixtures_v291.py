"""
test_ir_adversarial_fixtures_v291.py — ACP v2.91 GET /ir/adversarial-fixtures tests

Tests:
  IAF1:  Endpoint returns 200 + ok=true
  IAF2:  fixture_count == 5 and fixtures list has 5 items
  IAF3:  Each fixture has required fields (id/scenario/agents/interactions/expected_flags/expected_trust_signal)
  IAF4:  AF-001 (legitimate) — expected_flags == [] and expected_trust_signal == "high"
  IAF5:  AF-002 (colluding pair) — expected_flags includes "mutual_inflation_risk"
  IAF6:  AF-003 (sybil ring) — expected_flags includes "sybil_ring_pattern"
  IAF7:  AF-004 (burst spike) — expected_flags includes "velocity_spike"
  IAF8:  AF-005 (tampered chain) — tampered_record_id present; expected_trust_signal == "invalid"
  IAF9:  All interactions in AF-001 have valid bilateral=True and relay_signature present
  IAF10: AF-005 record 3 has bilateral=False (tampered)
  IAF11: capability flag ir_adversarial_fixtures in /.well-known/acp.json
  IAF12: endpoint ir_adversarial_fixtures in /.well-known/acp.json
  IAF13: detection_algorithms dict present in response
"""

import json
import os
import random
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

# ── Path setup ─────────────────────────────────────────────────────────────────
_tests_dir = os.path.dirname(os.path.abspath(__file__))
_repo_root  = os.path.dirname(_tests_dir)
_relay_dir  = os.path.join(_repo_root, "relay")

if _relay_dir not in sys.path:
    sys.path.insert(0, _relay_dir)

import identity as _id_mod

IDENTITY_AVAILABLE = _id_mod.IDENTITY_AVAILABLE
RELAY_PATH = os.path.join(_relay_dir, "acp_relay.py")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _free_port_pair():
    for _ in range(60):
        ws = random.randint(49300, 49399)
        http = ws + 100
        ok = True
        for p in (ws, http):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    s.bind(("127.0.0.1", p))
            except OSError:
                ok = False
                break
        if ok:
            return ws, http
    raise RuntimeError("Cannot find free port pair")


def _wait_relay(http_port, timeout=12):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://localhost:{http_port}/.well-known/acp.json", timeout=1
            ) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def _get(http_port, path):
    try:
        with urllib.request.urlopen(
            f"http://localhost:{http_port}{path}", timeout=10
        ) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def relay_proc():
    ws_port, http_port = _free_port_pair()
    proc = subprocess.Popen(
        [sys.executable, RELAY_PATH,
         "--port", str(ws_port),
         "--local-only"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if not _wait_relay(http_port):
        proc.terminate()
        pytest.skip("Relay failed to start")
    yield http_port
    proc.terminate()
    proc.wait(timeout=5)


@pytest.fixture(scope="module")
def fixtures_resp(relay_proc):
    status, data = _get(relay_proc, "/ir/adversarial-fixtures")
    return status, data


# ══════════════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not IDENTITY_AVAILABLE, reason="cryptography not installed")
class TestIRAdversarialFixtures:

    def test_iaf1_200_ok(self, fixtures_resp):
        """IAF1: Endpoint returns 200 and ok=true."""
        status, data = fixtures_resp
        assert status == 200, f"Expected 200, got {status}: {data}"
        assert data.get("ok") is True, f"ok not True: {data}"

    def test_iaf2_fixture_count(self, fixtures_resp):
        """IAF2: fixture_count == 5 and fixtures list has 5 items."""
        _, data = fixtures_resp
        assert data.get("fixture_count") == 5
        assert len(data.get("fixtures", [])) == 5

    def test_iaf3_required_fields(self, fixtures_resp):
        """IAF3: Each fixture has required top-level fields."""
        _, data = fixtures_resp
        required = {"id", "scenario", "agents", "interactions",
                    "expected_flags", "expected_trust_signal"}
        for fx in data["fixtures"]:
            missing = required - set(fx.keys())
            assert not missing, f"Fixture {fx.get('id')} missing fields: {missing}"

    def test_iaf4_af001_legitimate(self, fixtures_resp):
        """IAF4: AF-001 expected_flags is empty, trust_signal is 'high'."""
        _, data = fixtures_resp
        af001 = next(f for f in data["fixtures"] if f["id"] == "AF-001")
        assert af001["expected_flags"] == [], f"AF-001 should have no flags: {af001['expected_flags']}"
        assert af001["expected_trust_signal"] == "high"
        assert af001["interaction_count"] == 50
        assert len(af001["interactions"]) == 50

    def test_iaf5_af002_colluding_pair(self, fixtures_resp):
        """IAF5: AF-002 includes mutual_inflation_risk flag."""
        _, data = fixtures_resp
        af002 = next(f for f in data["fixtures"] if f["id"] == "AF-002")
        assert "mutual_inflation_risk" in af002["expected_flags"], \
            f"AF-002 flags: {af002['expected_flags']}"
        assert af002["expected_trust_signal"] == "suspicious"
        assert af002["interaction_count"] == 20

    def test_iaf6_af003_sybil_ring(self, fixtures_resp):
        """IAF6: AF-003 includes sybil_ring_pattern flag."""
        _, data = fixtures_resp
        af003 = next(f for f in data["fixtures"] if f["id"] == "AF-003")
        assert "sybil_ring_pattern" in af003["expected_flags"], \
            f"AF-003 flags: {af003['expected_flags']}"
        assert af003["expected_trust_signal"] == "untrusted"
        assert af003["interaction_count"] == 21

    def test_iaf7_af004_burst_spike(self, fixtures_resp):
        """IAF7: AF-004 includes velocity_spike flag."""
        _, data = fixtures_resp
        af004 = next(f for f in data["fixtures"] if f["id"] == "AF-004")
        assert "velocity_spike" in af004["expected_flags"], \
            f"AF-004 flags: {af004['expected_flags']}"
        assert af004["expected_trust_signal"] == "suspicious"
        assert af004["interaction_count"] == 20

    def test_iaf8_af005_tampered_chain(self, fixtures_resp):
        """IAF8: AF-005 has tampered_record_id and expected_trust_signal == 'invalid'."""
        _, data = fixtures_resp
        af005 = next(f for f in data["fixtures"] if f["id"] == "AF-005")
        assert af005["expected_trust_signal"] == "invalid"
        assert "tampered_record_id" in af005, "tampered_record_id field missing"
        assert "signature_verification_failure" in af005["expected_flags"]

    def test_iaf9_af001_interactions_bilateral(self, fixtures_resp):
        """IAF9: All AF-001 interactions have bilateral=True and relay_signature."""
        _, data = fixtures_resp
        af001 = next(f for f in data["fixtures"] if f["id"] == "AF-001")
        for rec in af001["interactions"]:
            assert rec.get("bilateral") is True, \
                f"Record {rec.get('id')} has bilateral={rec.get('bilateral')}"
            assert rec.get("relay_signature"), \
                f"Record {rec.get('id')} missing relay_signature"

    def test_iaf10_af005_tampered_record_bilateral_false(self, fixtures_resp):
        """IAF10: AF-005 tampered record has bilateral=False."""
        _, data = fixtures_resp
        af005 = next(f for f in data["fixtures"] if f["id"] == "AF-005")
        tampered_id = af005["tampered_record_id"]
        tampered_rec = next(r for r in af005["interactions"] if r["id"] == tampered_id)
        assert tampered_rec.get("bilateral") is False, \
            f"Tampered record should have bilateral=False, got {tampered_rec.get('bilateral')}"

    def test_iaf11_capability_flag(self, relay_proc):
        """IAF11: capabilities.ir_adversarial_fixtures in /.well-known/acp.json."""
        with urllib.request.urlopen(
            f"http://localhost:{relay_proc}/.well-known/acp.json", timeout=5
        ) as r:
            info = json.loads(r.read())
        card = info.get("self", info)
        caps = card.get("capabilities", {})
        assert caps.get("ir_adversarial_fixtures") is True, \
            f"ir_adversarial_fixtures capability missing; keys={list(caps.keys())}"

    def test_iaf12_endpoint_entry(self, relay_proc):
        """IAF12: endpoints.ir_adversarial_fixtures in /.well-known/acp.json."""
        with urllib.request.urlopen(
            f"http://localhost:{relay_proc}/.well-known/acp.json", timeout=5
        ) as r:
            info = json.loads(r.read())
        card = info.get("self", info)
        endpoints = card.get("endpoints", {})
        assert "ir_adversarial_fixtures" in endpoints, \
            f"ir_adversarial_fixtures endpoint missing; keys={list(endpoints.keys())}"
        assert endpoints["ir_adversarial_fixtures"] == "/ir/adversarial-fixtures"

    def test_iaf13_detection_algorithms(self, fixtures_resp):
        """IAF13: detection_algorithms dict present with expected keys."""
        _, data = fixtures_resp
        algos = data.get("detection_algorithms", {})
        assert algos, "detection_algorithms dict is empty or missing"
        expected_keys = {"counterparty_diversity", "mutual_pair_ratio",
                         "velocity_ratio", "chain_integrity"}
        missing = expected_keys - set(algos.keys())
        assert not missing, f"detection_algorithms missing keys: {missing}"
