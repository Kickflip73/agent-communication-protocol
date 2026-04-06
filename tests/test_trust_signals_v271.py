"""
tests/test_trust_signals_v271.py — v2.71 security_posture as 13th trust signal

A2A #1628 @douglasborthwick suggested "security_posture" as a source-level
vulnerability scanning dimension. ACP v2.71 adds it as the 13th trust signal.

Security posture endpoint:
SP-1:  GET /trust/signals/security-posture returns ok=True, version
SP-2:  Response has posture_score, critical_cves, high_cves, total_cves
SP-3:  posture_score is one of {clean, advisory, vulnerable}
SP-4:  scanned_at is present (ISO 8601 datetime)
SP-5:  scan_tool is present
SP-6:  components is a non-empty list with name+version+cve_count per entry
SP-7:  disclaimer and note fields present

trust.signals[] 13th signal:
SG-8:  GET /trust/signals now returns 13 signals (was 12)
SG-9:  security_posture signal has enabled=True
SG-10: security_posture signal has severity="high", category="integrity"
SG-11: security_posture details include posture_score, endpoint, scan_tool
SG-12: security_posture details.endpoint = "/trust/signals/security-posture"

Schema (13 types):
SC-13: GET /trust/signals/schema returns count=13
SC-14: Schema includes security_posture with severity="high", category="integrity"
SC-15: /trust/signals/schema and /trust/signals are consistent for security_posture

Filters (v2.70 filters still work with 13 signals):
FL-16: ?category=integrity includes security_posture
FL-17: ?severity=high includes security_posture
FL-18: ?type=security_posture returns exactly 1 signal

AgentCard:
AC-19: capabilities.trust_signals_v271 = True
AC-20: endpoints.trust_signals_security_posture = '/trust/signals/security-posture'
"""

import os
import sys
import time
import socket
import subprocess
import pytest
import requests

RELAY = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")


def _free_port_pair():
    for _ in range(20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            ws = s.getsockname()[1]
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s2:
                s2.bind(("", ws + 100))
            return ws, ws + 100
        except OSError:
            continue
    raise RuntimeError("Cannot find free port pair")


@pytest.fixture(scope="module")
def relay_url():
    ws_port, http_port = _free_port_pair()
    proc = subprocess.Popen(
        [sys.executable, RELAY, "--port", str(ws_port), "--name", "TrustSignalsV271Test", "--local"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            r = requests.get(f"http://localhost:{http_port}/status", timeout=1)
            if r.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(0.2)
    else:
        proc.terminate()
        pytest.fail("Relay did not start in time")
    yield f"http://localhost:{http_port}"
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


VALID_POSTURE_SCORES = {"clean", "advisory", "vulnerable"}


# ── /trust/signals/security-posture ──────────────────────────────────────────

def test_sp1_security_posture_basic(relay_url):
    """SP-1: GET /trust/signals/security-posture returns ok=True, version."""
    r = requests.get(f"{relay_url}/trust/signals/security-posture")
    assert r.status_code == 200, f"status={r.status_code} body={r.text[:200]}"
    d = r.json()
    assert d.get("ok") is True
    assert "version" in d
    assert d["version"].startswith("2.")


def test_sp2_required_fields(relay_url):
    """SP-2: Response has posture_score, cve counts."""
    d = requests.get(f"{relay_url}/trust/signals/security-posture").json()
    for field in ("posture_score", "critical_cves", "high_cves", "total_cves"):
        assert field in d, f"Missing field: {field}"
    assert isinstance(d["critical_cves"], int)
    assert isinstance(d["high_cves"], int)
    assert isinstance(d["total_cves"], int)
    assert d["critical_cves"] >= 0
    assert d["high_cves"] >= 0
    assert d["total_cves"] >= 0


def test_sp3_posture_score_values(relay_url):
    """SP-3: posture_score is in {clean, advisory, vulnerable}."""
    d = requests.get(f"{relay_url}/trust/signals/security-posture").json()
    assert d["posture_score"] in VALID_POSTURE_SCORES, \
        f"Invalid posture_score: '{d['posture_score']}'"


def test_sp4_scanned_at(relay_url):
    """SP-4: scanned_at is present (ISO 8601)."""
    d = requests.get(f"{relay_url}/trust/signals/security-posture").json()
    assert "scanned_at" in d
    assert d["scanned_at"] is not None
    sa = d["scanned_at"]
    assert isinstance(sa, str) and len(sa) > 10, f"Invalid scanned_at: {sa}"
    assert "T" in sa, f"Not ISO 8601: {sa}"


def test_sp5_scan_tool(relay_url):
    """SP-5: scan_tool is present."""
    d = requests.get(f"{relay_url}/trust/signals/security-posture").json()
    assert "scan_tool" in d
    assert isinstance(d["scan_tool"], str)
    assert len(d["scan_tool"]) > 0


def test_sp6_components(relay_url):
    """SP-6: components is a non-empty list with required fields."""
    d = requests.get(f"{relay_url}/trust/signals/security-posture").json()
    assert "components" in d
    comps = d["components"]
    assert isinstance(comps, list)
    assert len(comps) >= 1, "Expected at least 1 component"
    for comp in comps:
        assert "name" in comp, f"Component missing name: {comp}"
        assert "version" in comp, f"Component missing version: {comp}"
        assert "cve_count" in comp, f"Component missing cve_count: {comp}"
        assert isinstance(comp["cve_count"], int)


def test_sp7_note_disclaimer(relay_url):
    """SP-7: disclaimer and note fields present."""
    d = requests.get(f"{relay_url}/trust/signals/security-posture").json()
    assert "disclaimer" in d
    assert "note" in d
    assert isinstance(d["disclaimer"], str) and len(d["disclaimer"]) > 10
    assert isinstance(d["note"], str) and len(d["note"]) > 10


# ── trust.signals[] 13th signal ───────────────────────────────────────────────

def test_sg8_thirteen_signals(relay_url):
    """SG-8: GET /trust/signals returns 13 signals."""
    r = requests.get(f"{relay_url}/trust/signals")
    assert r.status_code == 200
    d = r.json()
    assert d.get("count") == 13, f"Expected 13, got {d.get('count')}"
    assert len(d["signals"]) == 13


def test_sg9_security_posture_enabled(relay_url):
    """SG-9: security_posture signal has enabled=True."""
    d = requests.get(f"{relay_url}/trust/signals").json()
    sp = next((s for s in d["signals"] if s["type"] == "security_posture"), None)
    assert sp is not None, "security_posture signal not found"
    assert sp["enabled"] is True


def test_sg10_security_posture_severity_category(relay_url):
    """SG-10: security_posture has severity=high, category=integrity."""
    d = requests.get(f"{relay_url}/trust/signals").json()
    sp = next((s for s in d["signals"] if s["type"] == "security_posture"), None)
    assert sp is not None
    assert sp["severity"] == "high", f"Expected high, got {sp['severity']}"
    assert sp["category"] == "integrity", f"Expected integrity, got {sp['category']}"


def test_sg11_security_posture_details(relay_url):
    """SG-11: security_posture details include posture_score, endpoint, scan_tool."""
    d = requests.get(f"{relay_url}/trust/signals").json()
    sp = next((s for s in d["signals"] if s["type"] == "security_posture"), None)
    assert sp is not None
    det = sp.get("details", {})
    assert "posture_score" in det, f"Missing posture_score in details: {det}"
    assert "scan_tool" in det, f"Missing scan_tool in details: {det}"
    assert "endpoint" in det, f"Missing endpoint in details: {det}"
    assert "total_cves" in det, f"Missing total_cves in details: {det}"


def test_sg12_security_posture_endpoint_detail(relay_url):
    """SG-12: security_posture details.endpoint = '/trust/signals/security-posture'."""
    d = requests.get(f"{relay_url}/trust/signals").json()
    sp = next((s for s in d["signals"] if s["type"] == "security_posture"), None)
    assert sp is not None
    assert sp["details"]["endpoint"] == "/trust/signals/security-posture", \
        f"Unexpected endpoint: {sp['details']['endpoint']}"


# ── Schema (13 types) ─────────────────────────────────────────────────────────

def test_sc13_schema_count(relay_url):
    """SC-13: GET /trust/signals/schema returns count=13."""
    r = requests.get(f"{relay_url}/trust/signals/schema")
    assert r.status_code == 200
    d = r.json()
    assert d.get("count") == 13, f"Expected 13, got {d.get('count')}"
    assert len(d["schema"]) == 13


def test_sc14_schema_security_posture(relay_url):
    """SC-14: Schema includes security_posture with severity=high, category=integrity."""
    d = requests.get(f"{relay_url}/trust/signals/schema").json()
    sp = next((e for e in d["schema"] if e["type"] == "security_posture"), None)
    assert sp is not None, "security_posture not found in schema"
    assert sp["severity"] == "high"
    assert sp["category"] == "integrity"
    assert len(sp.get("description", "")) > 10


def test_sc15_schema_signals_consistency(relay_url):
    """SC-15: /trust/signals/schema and /trust/signals consistent for security_posture."""
    schema_d = requests.get(f"{relay_url}/trust/signals/schema").json()
    signals_d = requests.get(f"{relay_url}/trust/signals").json()
    sp_schema = next((e for e in schema_d["schema"] if e["type"] == "security_posture"), None)
    sp_signal = next((s for s in signals_d["signals"] if s["type"] == "security_posture"), None)
    assert sp_schema is not None and sp_signal is not None
    assert sp_signal["severity"] == sp_schema["severity"], "severity mismatch"
    assert sp_signal["category"] == sp_schema["category"], "category mismatch"


# ── Filters ───────────────────────────────────────────────────────────────────

def test_fl16_filter_category_integrity_includes_security_posture(relay_url):
    """FL-16: ?category=integrity includes security_posture."""
    d = requests.get(f"{relay_url}/trust/signals", params={"category": "integrity"}).json()
    types = {s["type"] for s in d["signals"]}
    assert "security_posture" in types, f"security_posture not in integrity filter: {types}"
    # integrity should also still have hmac/replay/peer_card
    assert "hmac_message_signing" in types
    assert "replay_window" in types


def test_fl17_filter_severity_high_includes_security_posture(relay_url):
    """FL-17: ?severity=high includes security_posture."""
    d = requests.get(f"{relay_url}/trust/signals", params={"severity": "high"}).json()
    types = {s["type"] for s in d["signals"]}
    assert "security_posture" in types, f"security_posture not in high severity filter: {types}"


def test_fl18_filter_type_security_posture(relay_url):
    """FL-18: ?type=security_posture returns exactly 1 signal."""
    d = requests.get(f"{relay_url}/trust/signals", params={"type": "security_posture"}).json()
    assert d["count"] == 1
    assert d["signals"][0]["type"] == "security_posture"


# ── AgentCard ─────────────────────────────────────────────────────────────────

def test_ac19_agentcard_trust_signals_v271(relay_url):
    """AC-19: capabilities.trust_signals_v271 = True."""
    r = requests.get(f"{relay_url}/.well-known/acp.json")
    assert r.status_code == 200
    card = r.json()
    cap = card.get("self", card).get("capabilities", {})
    assert cap.get("trust_signals_v271") is True, \
        f"capabilities.trust_signals_v271 not True; got {cap.get('trust_signals_v271')}"


def test_ac20_agentcard_security_posture_endpoint(relay_url):
    """AC-20: endpoints.trust_signals_security_posture = '/trust/signals/security-posture'."""
    r = requests.get(f"{relay_url}/.well-known/acp.json")
    assert r.status_code == 200
    card = r.json()
    ep = card.get("self", card).get("endpoints", {})
    assert ep.get("trust_signals_security_posture") == "/trust/signals/security-posture", \
        f"Unexpected: {ep.get('trust_signals_security_posture')}"
