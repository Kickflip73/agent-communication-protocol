"""
tests/test_trust_signals_v270.py — v2.70 trust.signals severity+category metadata

Schema endpoint:
SC-1:  GET /trust/signals/schema returns ok=True, 12 entries, version
SC-2:  Each schema entry has type, severity, category, description
SC-3:  severity values are in {critical, high, medium, low}
SC-4:  category values are in {identity, integrity, authorization, discovery, attestation}
SC-5:  Specific severity checks (ed25519_identity=critical, hmac_message_signing=high, did_document=medium)
SC-6:  Specific category checks (bilateral_ir=attestation, capability_token=authorization, jwks=discovery)

Signals endpoint with new filters (v2.70):
SF-7:  ?category=identity returns only identity-category signals
SF-8:  ?category=authorization returns authorization signals
SF-9:  ?severity=critical returns critical signals (ed25519_identity, agent_card_signature, capability_token)
SF-10: ?severity=medium returns medium signals (did_document, jwks, vouch_chain, wtrmrk)

Signal fields:
SV-11: Every signal in GET /trust/signals has severity field
SV-12: Every signal in GET /trust/signals has category field
SV-13: severity and category values match TRUST_SIGNAL_SCHEMA definitions

AgentCard:
AC-14: AgentCard capabilities.trust_signals_v270 = True
AC-15: AgentCard endpoints.trust_signals_schema = '/trust/signals/schema'
"""

import os
import sys
import time
import socket
import subprocess
import pytest
import requests

RELAY = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def relay_url():
    ws_port = _free_port()
    http_port = ws_port + 100
    proc = subprocess.Popen(
        [sys.executable, RELAY, "--port", str(ws_port), "--name", "TrustSignalsV270Test"],
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


VALID_SEVERITIES = {"critical", "high", "medium", "low"}
VALID_CATEGORIES = {"identity", "integrity", "authorization", "discovery", "attestation"}


# ── helpers ───────────────────────────────────────────────────────────────────

def get_schema(relay_url: str) -> dict:
    r = requests.get(f"{relay_url}/trust/signals/schema")
    assert r.status_code == 200, f"GET /trust/signals/schema: {r.status_code} {r.text}"
    return r.json()


def get_signals(relay_url: str, **params) -> dict:
    r = requests.get(f"{relay_url}/trust/signals", params=params)
    assert r.status_code == 200, f"GET /trust/signals: {r.status_code} {r.text}"
    return r.json()


# ── schema endpoint tests ─────────────────────────────────────────────────────

def test_sc1_schema_basic(relay_url):
    """SC-1: GET /trust/signals/schema returns ok=True, 12 entries, version."""
    d = get_schema(relay_url)
    assert d["ok"] is True
    assert "schema" in d
    assert "count" in d
    assert "version" in d
    assert d["count"] == 12
    assert len(d["schema"]) == 12
    assert d["version"].startswith("2.")
    assert "note" in d


def test_sc2_schema_entry_fields(relay_url):
    """SC-2: Each schema entry has type, severity, category, description."""
    d = get_schema(relay_url)
    for entry in d["schema"]:
        assert "type" in entry,        f"Missing 'type': {entry}"
        assert "severity" in entry,    f"Missing 'severity': {entry}"
        assert "category" in entry,    f"Missing 'category': {entry}"
        assert "description" in entry, f"Missing 'description': {entry}"
        assert isinstance(entry["type"], str)
        assert isinstance(entry["severity"], str)
        assert isinstance(entry["category"], str)
        assert isinstance(entry["description"], str)
        assert len(entry["description"]) > 0, f"Empty description for {entry['type']}"


def test_sc3_severity_values(relay_url):
    """SC-3: All severity values are in {critical, high, medium, low}."""
    d = get_schema(relay_url)
    for entry in d["schema"]:
        assert entry["severity"] in VALID_SEVERITIES, \
            f"Invalid severity '{entry['severity']}' for type '{entry['type']}'"


def test_sc4_category_values(relay_url):
    """SC-4: All category values are in the valid set."""
    d = get_schema(relay_url)
    for entry in d["schema"]:
        assert entry["category"] in VALID_CATEGORIES, \
            f"Invalid category '{entry['category']}' for type '{entry['type']}'"


def test_sc5_specific_severities(relay_url):
    """SC-5: Spot-check expected severity levels for key signal types."""
    d = get_schema(relay_url)
    by_type = {e["type"]: e for e in d["schema"]}
    # Cryptographic proof → critical
    assert by_type["ed25519_identity"]["severity"] == "critical", "ed25519_identity should be critical"
    assert by_type["agent_card_signature"]["severity"] == "critical", "agent_card_signature should be critical"
    assert by_type["capability_token"]["severity"] == "critical", "capability_token should be critical"
    # Runtime verification → high
    assert by_type["hmac_message_signing"]["severity"] == "high", "hmac_message_signing should be high"
    assert by_type["replay_window"]["severity"] == "high", "replay_window should be high"
    assert by_type["peer_card_verification"]["severity"] == "high", "peer_card_verification should be high"
    # Structural/discovery → medium
    assert by_type["did_document"]["severity"] == "medium", "did_document should be medium"
    assert by_type["jwks"]["severity"] == "medium", "jwks should be medium"
    assert by_type["wtrmrk"]["severity"] == "medium", "wtrmrk should be medium"


def test_sc6_specific_categories(relay_url):
    """SC-6: Spot-check expected category assignments."""
    d = get_schema(relay_url)
    by_type = {e["type"]: e for e in d["schema"]}
    assert by_type["bilateral_ir"]["category"] == "attestation"
    assert by_type["capability_token"]["category"] == "authorization"
    assert by_type["external_token"]["category"] == "authorization"
    assert by_type["jwks"]["category"] == "discovery"
    assert by_type["did_document"]["category"] == "discovery"
    assert by_type["ed25519_identity"]["category"] == "identity"
    assert by_type["agent_card_signature"]["category"] == "identity"
    assert by_type["hmac_message_signing"]["category"] == "integrity"
    assert by_type["replay_window"]["category"] == "integrity"
    assert by_type["peer_card_verification"]["category"] == "integrity"
    assert by_type["vouch_chain"]["category"] == "attestation"
    assert by_type["wtrmrk"]["category"] == "attestation"


# ── /trust/signals with new v2.70 filters ────────────────────────────────────

def test_sf7_filter_category_identity(relay_url):
    """SF-7: ?category=identity returns only identity-category signals."""
    d = get_signals(relay_url, category="identity")
    assert d["ok"] is True
    assert d["count"] >= 1
    for sig in d["signals"]:
        assert sig.get("category") == "identity", f"Non-identity signal: {sig['type']}"
    # Should contain ed25519_identity and agent_card_signature
    types = {s["type"] for s in d["signals"]}
    assert "ed25519_identity" in types
    assert "agent_card_signature" in types


def test_sf8_filter_category_authorization(relay_url):
    """SF-8: ?category=authorization returns authorization signals."""
    d = get_signals(relay_url, category="authorization")
    assert d["ok"] is True
    assert d["count"] >= 1
    for sig in d["signals"]:
        assert sig.get("category") == "authorization"
    types = {s["type"] for s in d["signals"]}
    assert "capability_token" in types
    assert "external_token" in types


def test_sf9_filter_severity_critical(relay_url):
    """SF-9: ?severity=critical returns critical signals."""
    d = get_signals(relay_url, severity="critical")
    assert d["ok"] is True
    assert d["count"] >= 1
    for sig in d["signals"]:
        assert sig.get("severity") == "critical"
    types = {s["type"] for s in d["signals"]}
    assert "ed25519_identity" in types
    assert "agent_card_signature" in types
    assert "capability_token" in types


def test_sf10_filter_severity_medium(relay_url):
    """SF-10: ?severity=medium returns medium signals (did_document, jwks, vouch_chain, wtrmrk)."""
    d = get_signals(relay_url, severity="medium")
    assert d["ok"] is True
    assert d["count"] >= 1
    for sig in d["signals"]:
        assert sig.get("severity") == "medium"
    types = {s["type"] for s in d["signals"]}
    assert "did_document" in types
    assert "jwks" in types
    assert "wtrmrk" in types


# ── signal fields in /trust/signals ──────────────────────────────────────────

def test_sv11_signals_have_severity(relay_url):
    """SV-11: Every signal in GET /trust/signals has a severity field."""
    d = get_signals(relay_url)
    assert d["count"] == 12
    for sig in d["signals"]:
        assert "severity" in sig, f"Signal missing severity: {sig['type']}"
        assert sig["severity"] in VALID_SEVERITIES, \
            f"Invalid severity '{sig['severity']}' for {sig['type']}"


def test_sv12_signals_have_category(relay_url):
    """SV-12: Every signal in GET /trust/signals has a category field."""
    d = get_signals(relay_url)
    for sig in d["signals"]:
        assert "category" in sig, f"Signal missing category: {sig['type']}"
        assert sig["category"] in VALID_CATEGORIES, \
            f"Invalid category '{sig['category']}' for {sig['type']}"


def test_sv13_signals_schema_consistency(relay_url):
    """SV-13: severity/category in /trust/signals match /trust/signals/schema."""
    schema_d = get_schema(relay_url)
    signals_d = get_signals(relay_url)
    schema_by_type = {e["type"]: e for e in schema_d["schema"]}
    for sig in signals_d["signals"]:
        t = sig["type"]
        assert t in schema_by_type, f"Signal type '{t}' not in schema"
        assert sig["severity"] == schema_by_type[t]["severity"], \
            f"{t}: severity mismatch (signals={sig['severity']}, schema={schema_by_type[t]['severity']})"
        assert sig["category"] == schema_by_type[t]["category"], \
            f"{t}: category mismatch (signals={sig['category']}, schema={schema_by_type[t]['category']})"


# ── AgentCard ─────────────────────────────────────────────────────────────────

def test_ac14_agentcard_trust_signals_v270(relay_url):
    """AC-14: AgentCard capabilities.trust_signals_v270 = True."""
    r = requests.get(f"{relay_url}/.well-known/acp.json")
    assert r.status_code == 200
    card = r.json()
    cap = card.get("self", card).get("capabilities", {})
    assert cap.get("trust_signals_v270") is True, \
        f"capabilities.trust_signals_v270 not True; got {cap.get('trust_signals_v270')}"


def test_ac15_agentcard_schema_endpoint(relay_url):
    """AC-15: AgentCard endpoints.trust_signals_schema = '/trust/signals/schema'."""
    r = requests.get(f"{relay_url}/.well-known/acp.json")
    assert r.status_code == 200
    card = r.json()
    ep = card.get("self", card).get("endpoints", {})
    assert ep.get("trust_signals_schema") == "/trust/signals/schema", \
        f"endpoints.trust_signals_schema unexpected: {ep.get('trust_signals_schema')}"
