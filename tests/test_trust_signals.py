#!/usr/bin/env python3
"""
test_trust_signals.py — v2.14: trust.signals[] structured evidence

TS1: trust block present in AgentCard (/.well-known/acp.json)
TS2: trust.signals is a non-empty list
TS3: each signal has required fields (type, enabled, description, details)
TS4: known signal types are all present
TS5: without --identity, ed25519-related signals disabled
TS6: without --secret, hmac-related signals disabled
TS7: trust_signals capability declared in AgentCard
TS8: signals consistent with capabilities (trust.signals[n].enabled ↔ capabilities)
"""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RELAY_PY = os.path.join(BASE_DIR, "relay", "acp_relay.py")

_PROXY_VARS = (
    "http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY",
    "all_proxy", "ALL_PROXY", "ftp_proxy", "FTP_PROXY", "no_proxy", "NO_PROXY",
)

EXPECTED_SIGNAL_TYPES = {
    "hmac_message_signing",
    "ed25519_identity",
    "agent_card_signature",
    "peer_card_verification",
    "replay_window",
    "did_document",
}


def _clean_env() -> dict:
    env = os.environ.copy()
    for v in _PROXY_VARS:
        env.pop(v, None)
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _free_port() -> int:
    for _ in range(200):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            ws = s.getsockname()[1]
        try:
            with socket.socket() as s2:
                s2.bind(("127.0.0.1", ws + 100))
                return ws
        except OSError:
            continue
    raise RuntimeError("no free port pair")


def _start_relay(ws_port: int, name: str = "TrustAgent", extra: list = None) -> subprocess.Popen:
    cmd = [sys.executable, "-u", RELAY_PY,
           "--name", name,
           "--port", str(ws_port),
           "--http-host", "127.0.0.1"]
    if extra:
        cmd.extend(extra)
    return subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=_clean_env(),
    )


def _wait_ready(http_port: int, timeout: float = 12.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{http_port}/status", timeout=2
            ) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def _get_json(url: str, timeout: float = 5) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read())


def _get_agent_card(http_port: int) -> dict:
    """Get the 'self' AgentCard from /.well-known/acp.json (unwrap {self: card} wrapper)."""
    raw = _get_json(f"http://127.0.0.1:{http_port}/.well-known/acp.json")
    return raw.get("self", raw)  # support both wrapped and flat format


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def relay_no_identity():
    """Relay started without --identity (default)."""
    ws = _free_port()
    http = ws + 100
    proc = _start_relay(ws, "TSNoId")
    assert _wait_ready(http), f"relay failed to start (http_port={http})"
    yield http
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


# ── tests ─────────────────────────────────────────────────────────────────────

class TestTrustSignals:

    def test_ts1_trust_block_present(self, relay_no_identity):
        """TS1: trust block present in /.well-known/acp.json."""
        card = _get_agent_card(relay_no_identity)
        assert "trust" in card, "AgentCard missing 'trust' block"
        trust = card["trust"]
        assert "scheme" in trust
        assert "enabled" in trust
        assert "signals" in trust, "trust block missing 'signals' key"

    def test_ts2_signals_nonempty_list(self, relay_no_identity):
        """TS2: trust.signals is a non-empty list."""
        card = _get_agent_card(relay_no_identity)
        signals = card["trust"]["signals"]
        assert isinstance(signals, list), f"trust.signals should be list, got {type(signals)}"
        assert len(signals) > 0, "trust.signals should not be empty"

    def test_ts3_each_signal_has_required_fields(self, relay_no_identity):
        """TS3: each signal has type, enabled, description, details."""
        card = _get_agent_card(relay_no_identity)
        for sig in card["trust"]["signals"]:
            assert "type" in sig,        f"signal missing 'type': {sig}"
            assert "enabled" in sig,     f"signal missing 'enabled': {sig}"
            assert "description" in sig, f"signal missing 'description': {sig}"
            assert "details" in sig,     f"signal missing 'details': {sig}"
            assert isinstance(sig["enabled"], bool), f"signal.enabled should be bool: {sig}"
            assert isinstance(sig["details"], dict), f"signal.details should be dict: {sig}"

    def test_ts4_expected_signal_types_present(self, relay_no_identity):
        """TS4: all expected signal types are present."""
        card = _get_agent_card(relay_no_identity)
        found = {s["type"] for s in card["trust"]["signals"]}
        missing = EXPECTED_SIGNAL_TYPES - found
        assert not missing, f"Missing signal types: {missing}"

    def test_ts5_no_identity_ed25519_signals_disabled(self, relay_no_identity):
        """TS5: without --identity, ed25519/DID-related signals are disabled."""
        card = _get_agent_card(relay_no_identity)
        by_type = {s["type"]: s for s in card["trust"]["signals"]}

        assert not by_type["ed25519_identity"]["enabled"], \
            "ed25519_identity should be disabled without --identity"
        assert not by_type["agent_card_signature"]["enabled"], \
            "agent_card_signature should be disabled without --identity"
        assert not by_type["did_document"]["enabled"], \
            "did_document should be disabled without --identity"

    def test_ts6_no_hmac_signals_disabled(self, relay_no_identity):
        """TS6: without --secret, HMAC-related signals are disabled."""
        card = _get_agent_card(relay_no_identity)
        by_type = {s["type"]: s for s in card["trust"]["signals"]}

        assert not by_type["hmac_message_signing"]["enabled"], \
            "hmac_message_signing should be disabled without --secret"
        assert not by_type["replay_window"]["enabled"], \
            "replay_window should be disabled without --secret"

    def test_ts7_capability_declared(self, relay_no_identity):
        """TS7: trust_signals capability is declared in AgentCard."""
        card = _get_agent_card(relay_no_identity)
        caps = card.get("capabilities", {})
        assert caps.get("trust_signals") is True, \
            "capabilities.trust_signals should be True"

    def test_ts8_peer_card_verification_always_enabled(self, relay_no_identity):
        """TS8: peer_card_verification signal is always enabled (it's a built-in capability)."""
        card = _get_agent_card(relay_no_identity)
        by_type = {s["type"]: s for s in card["trust"]["signals"]}
        assert by_type["peer_card_verification"]["enabled"], \
            "peer_card_verification should always be enabled"
        assert by_type["peer_card_verification"]["details"].get("endpoint") == "/peer/verify"
