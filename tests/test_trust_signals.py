"""
tests/test_trust_signals.py — v2.68 trust.signals[] extended inventory

TS-1:  GET /trust/signals returns ok=True, 12 signals, version field
TS-2:  All 12 expected signal types present
TS-3:  Each signal has required fields (type, enabled, description, details)
TS-4:  ?type=bilateral_ir filter returns exactly 1 signal
TS-5:  ?type=capability_token filter returns exactly 1 signal
TS-6:  ?type=wtrmrk filter returns exactly 1 signal
TS-7:  ?type=external_token filter returns exactly 1 signal
TS-8:  ?enabled=true filter returns only enabled signals (count >= 1)
TS-9:  ?enabled=false filter returns only disabled signals; enabled=False for all
TS-10: bilateral_ir signal has expected detail keys (endpoint_create, endpoint_list, count)
TS-11: AgentCard capabilities.trust_signals_v268 = True
TS-12: AgentCard endpoints.trust_signals = "/trust/signals"
TS-13: ?type=nonexistent returns count=0, ok=True
TS-14: No --identity: ed25519_identity signal enabled=False; bilateral_ir enabled=True
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
    """Start a relay, yield its HTTP base URL, tear down after module."""
    ws_port = _free_port()
    http_port = ws_port + 100
    proc = subprocess.Popen(
        [sys.executable, RELAY, "--port", str(ws_port), "--name", "TrustSignalsTest"],
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

EXPECTED_SIGNAL_TYPES = {
    "hmac_message_signing",
    "ed25519_identity",
    "agent_card_signature",
    "peer_card_verification",
    "replay_window",
    "did_document",
    "jwks",
    "vouch_chain",
    "bilateral_ir",
    "capability_token",
    "wtrmrk",
    "external_token",
}


# ── helpers ───────────────────────────────────────────────────────────────────

def get_signals(relay_url: str, **params) -> dict:
    r = requests.get(f"{relay_url}/trust/signals", params=params)
    assert r.status_code == 200, f"GET /trust/signals failed: {r.status_code} {r.text}"
    return r.json()


# ── tests ─────────────────────────────────────────────────────────────────────

def test_ts1_basic_response(relay_url):
    """TS-1: GET /trust/signals returns ok=True, signals list, version."""
    d = get_signals(relay_url)
    assert d["ok"] is True
    assert "signals" in d
    assert "count" in d
    assert "total" in d
    assert "version" in d
    assert d["version"].startswith("2.")
    assert isinstance(d["signals"], list)
    assert len(d["signals"]) == d["count"]


def test_ts2_all_12_types_present(relay_url):
    """TS-2: All 12 expected signal types are present in /trust/signals."""
    d = get_signals(relay_url)
    found_types = {s["type"] for s in d["signals"]}
    assert EXPECTED_SIGNAL_TYPES == found_types, \
        f"Missing: {EXPECTED_SIGNAL_TYPES - found_types}, Extra: {found_types - EXPECTED_SIGNAL_TYPES}"


def test_ts3_signal_schema(relay_url):
    """TS-3: Each signal has required fields: type, enabled, description, details."""
    d = get_signals(relay_url)
    for sig in d["signals"]:
        assert "type" in sig,        f"Signal missing 'type': {sig}"
        assert "enabled" in sig,     f"Signal missing 'enabled': {sig}"
        assert "description" in sig, f"Signal missing 'description': {sig}"
        assert "details" in sig,     f"Signal missing 'details': {sig}"
        assert isinstance(sig["enabled"], bool),      f"'enabled' must be bool: {sig}"
        assert isinstance(sig["description"], str),   f"'description' must be str: {sig}"
        assert isinstance(sig["details"], dict),      f"'details' must be dict: {sig}"


def test_ts4_filter_bilateral_ir(relay_url):
    """TS-4: ?type=bilateral_ir returns exactly 1 signal."""
    d = get_signals(relay_url, type="bilateral_ir")
    assert d["ok"] is True
    assert d["count"] == 1
    assert d["signals"][0]["type"] == "bilateral_ir"


def test_ts5_filter_capability_token(relay_url):
    """TS-5: ?type=capability_token returns exactly 1 signal."""
    d = get_signals(relay_url, type="capability_token")
    assert d["ok"] is True
    assert d["count"] == 1
    assert d["signals"][0]["type"] == "capability_token"


def test_ts6_filter_wtrmrk(relay_url):
    """TS-6: ?type=wtrmrk returns exactly 1 signal."""
    d = get_signals(relay_url, type="wtrmrk")
    assert d["ok"] is True
    assert d["count"] == 1
    assert d["signals"][0]["type"] == "wtrmrk"


def test_ts7_filter_external_token(relay_url):
    """TS-7: ?type=external_token returns exactly 1 signal."""
    d = get_signals(relay_url, type="external_token")
    assert d["ok"] is True
    assert d["count"] == 1
    assert d["signals"][0]["type"] == "external_token"


def test_ts8_filter_enabled_true(relay_url):
    """TS-8: ?enabled=true returns only signals with enabled=True."""
    d = get_signals(relay_url, enabled="true")
    assert d["ok"] is True
    assert d["count"] >= 1, "Expected at least 1 enabled signal (peer_card_verification is always True)"
    for sig in d["signals"]:
        assert sig["enabled"] is True, f"Non-enabled signal returned: {sig['type']}"


def test_ts9_filter_enabled_false(relay_url):
    """TS-9: ?enabled=false returns only signals with enabled=False."""
    d = get_signals(relay_url, enabled="false")
    assert d["ok"] is True
    for sig in d["signals"]:
        assert sig["enabled"] is False, f"Enabled signal returned in ?enabled=false: {sig['type']}"


def test_ts10_bilateral_ir_detail_keys(relay_url):
    """TS-10: bilateral_ir signal has expected detail keys."""
    d = get_signals(relay_url, type="bilateral_ir")
    sig = d["signals"][0]
    details = sig["details"]
    assert "endpoint_create" in details
    assert "endpoint_list" in details
    assert "endpoint_import" in details
    assert "endpoint_vectors" in details
    assert "count" in details
    assert details["endpoint_create"] == "/tasks?record=true"
    assert details["endpoint_list"] == "/interaction-records"
    assert isinstance(details["count"], int)
    assert details["bilateral"] is True


def test_ts11_agentcard_capability(relay_url):
    """TS-11: AgentCard capabilities.trust_signals_v268 = True."""
    r = requests.get(f"{relay_url}/.well-known/acp.json")
    assert r.status_code == 200
    card = r.json()
    cap = card.get("self", card).get("capabilities", {})
    assert cap.get("trust_signals_v268") is True, \
        f"capabilities.trust_signals_v268 not True; got {cap.get('trust_signals_v268')}"


def test_ts12_agentcard_endpoint(relay_url):
    """TS-12: AgentCard endpoints.trust_signals = '/trust/signals'."""
    r = requests.get(f"{relay_url}/.well-known/acp.json")
    assert r.status_code == 200
    card = r.json()
    ep = card.get("self", card).get("endpoints", {})
    assert ep.get("trust_signals") == "/trust/signals", \
        f"endpoints.trust_signals unexpected: {ep.get('trust_signals')}"


def test_ts13_unknown_type_filter(relay_url):
    """TS-13: ?type=nonexistent returns count=0, ok=True, empty list."""
    d = get_signals(relay_url, type="nonexistent_signal_type_xyz")
    assert d["ok"] is True
    assert d["count"] == 0
    assert d["signals"] == []
    assert d["total"] == 12  # total is always all 12


def test_ts14_no_identity_bilateral_ir_enabled(relay_url):
    """TS-14: Without --identity, bilateral_ir is enabled=True (always available)."""
    # bilateral_ir doesn't require Ed25519 identity to be enabled
    d = get_signals(relay_url, type="bilateral_ir")
    sig = d["signals"][0]
    assert sig["enabled"] is True, "bilateral_ir should always be enabled (no identity required)"
    # ed25519_identity should be disabled (no --identity in test fixture)
    d2 = get_signals(relay_url, type="ed25519_identity")
    sig2 = d2["signals"][0]
    assert sig2["enabled"] is False, "ed25519_identity should be disabled without --identity"
