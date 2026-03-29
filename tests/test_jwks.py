#!/usr/bin/env python3
"""
test_jwks.py — v2.18: trust.signals JWKS compatibility layer

JW1: GET /.well-known/jwks.json returns 200 + valid JSON (always)
JW2: Without --identity, jwks.json returns {"keys": []}
JW3: With --identity, jwks.json contains exactly one JWK
JW4: JWK has required fields: kty="OKP", crv="Ed25519", x, use="sig", alg="EdDSA", kid
JW5: JWK 'x' field matches identity.public_key from AgentCard
JW6: JWK 'kid' is "<agent_name>:<pubkey_prefix_8chars>"
JW7: capabilities.trust_jwks=True in AgentCard
JW8: endpoints.jwks="/.well-known/jwks.json" in AgentCard
JW9: trust.signals contains 'jwks' signal type when --identity enabled
JW10: jwks signal has jwks_uri and alg fields
"""

import base64
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


def _clean_env() -> dict:
    env = os.environ.copy()
    for v in _PROXY_VARS:
        env.pop(v, None)
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _free_port() -> int:
    """Return a ws port where ws+100 (http) is also free."""
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


def _start_relay(ws_port: int, name: str = "JWKSAgent", extra: list = None) -> subprocess.Popen:
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


def _wait_ready(http_port: int, timeout: float = 15.0) -> bool:
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
    """Get the 'self' AgentCard from /.well-known/acp.json."""
    raw = _get_json(f"http://127.0.0.1:{http_port}/.well-known/acp.json")
    return raw.get("self", raw)


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def relay_no_identity():
    """Relay without --identity (no Ed25519 keypair)."""
    ws = _free_port()
    http = ws + 100
    proc = _start_relay(ws, "JWKSNoId")
    assert _wait_ready(http), f"relay (no identity) failed to start on http_port={http}"
    yield http
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


@pytest.fixture(scope="module")
def relay_with_identity(tmp_path_factory):
    """Relay with --identity (Ed25519 keypair auto-generated)."""
    ws = _free_port()
    http = ws + 100
    identity_dir = tmp_path_factory.mktemp("jwks_identity")
    identity_path = str(identity_dir / "identity.json")
    proc = _start_relay(ws, "JWKSAgent", extra=["--identity", identity_path])
    assert _wait_ready(http), f"relay (with identity) failed to start on http_port={http}"
    yield http
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


# ── helpers ───────────────────────────────────────────────────────────────────

def _b64url_decode(s: str) -> bytes:
    """Decode base64url string (no padding required)."""
    pad = (4 - len(s) % 4) % 4
    return base64.urlsafe_b64decode(s + "=" * pad)


# ── tests: without --identity ─────────────────────────────────────────────────

class TestJWKSNoIdentity:

    def test_jw1_endpoint_returns_200(self, relay_no_identity):
        """JW1: GET /.well-known/jwks.json returns 200 + valid JSON (always, even without --identity)."""
        url = f"http://127.0.0.1:{relay_no_identity}/.well-known/jwks.json"
        with urllib.request.urlopen(url, timeout=5) as r:
            assert r.status == 200, f"Expected 200, got {r.status}"
            data = json.loads(r.read())
        assert isinstance(data, dict), "Response should be a JSON object"
        assert "keys" in data, "Response should have 'keys' field"

    def test_jw2_no_identity_returns_empty_keys(self, relay_no_identity):
        """JW2: Without --identity, jwks.json returns {\"keys\": []}."""
        data = _get_json(f"http://127.0.0.1:{relay_no_identity}/.well-known/jwks.json")
        assert data == {"keys": []}, f"Expected empty keys, got: {data}"


# ── tests: with --identity ────────────────────────────────────────────────────

class TestJWKSWithIdentity:

    def test_jw1_endpoint_returns_200(self, relay_with_identity):
        """JW1 (with identity): GET /.well-known/jwks.json returns 200."""
        url = f"http://127.0.0.1:{relay_with_identity}/.well-known/jwks.json"
        with urllib.request.urlopen(url, timeout=5) as r:
            assert r.status == 200

    def test_jw3_with_identity_one_jwk(self, relay_with_identity):
        """JW3: With --identity, jwks.json contains exactly one JWK."""
        data = _get_json(f"http://127.0.0.1:{relay_with_identity}/.well-known/jwks.json")
        assert "keys" in data, "Missing 'keys' field"
        assert isinstance(data["keys"], list), "'keys' should be a list"
        assert len(data["keys"]) == 1, f"Expected 1 JWK, got {len(data['keys'])}"

    def test_jw4_jwk_required_fields(self, relay_with_identity):
        """JW4: JWK has required fields kty, crv, x, use, alg, kid with correct values."""
        data = _get_json(f"http://127.0.0.1:{relay_with_identity}/.well-known/jwks.json")
        jwk = data["keys"][0]

        assert jwk.get("kty") == "OKP",     f"kty should be 'OKP', got {jwk.get('kty')!r}"
        assert jwk.get("crv") == "Ed25519", f"crv should be 'Ed25519', got {jwk.get('crv')!r}"
        assert jwk.get("use") == "sig",     f"use should be 'sig', got {jwk.get('use')!r}"
        assert jwk.get("alg") == "EdDSA",   f"alg should be 'EdDSA', got {jwk.get('alg')!r}"
        assert "x" in jwk,                  "JWK missing 'x' field (public key)"
        assert "kid" in jwk,                "JWK missing 'kid' field"

        # 'x' must be a valid base64url-encoded 32-byte value
        x_bytes = _b64url_decode(jwk["x"])
        assert len(x_bytes) == 32, f"Ed25519 public key 'x' should be 32 bytes, got {len(x_bytes)}"

    def test_jw5_x_matches_identity_public_key(self, relay_with_identity):
        """JW5: JWK 'x' field matches identity.public_key from AgentCard."""
        card = _get_agent_card(relay_with_identity)
        identity = card.get("identity")
        assert identity is not None, "AgentCard should have identity block (--identity enabled)"

        pubkey_from_card = identity.get("public_key") or identity.get("pubkey_b64")
        assert pubkey_from_card, "identity.public_key missing from AgentCard"

        data = _get_json(f"http://127.0.0.1:{relay_with_identity}/.well-known/jwks.json")
        jwk_x = data["keys"][0]["x"]

        # Both should be the same base64url-encoded raw 32-byte Ed25519 public key
        assert jwk_x == pubkey_from_card, (
            f"JWK 'x' ({jwk_x!r}) does not match AgentCard identity.public_key ({pubkey_from_card!r})"
        )

    def test_jw6_kid_format(self, relay_with_identity):
        """JW6: JWK 'kid' is '<agent_name>:<pubkey_prefix_8chars>'."""
        card = _get_agent_card(relay_with_identity)
        agent_name = card.get("name", "")
        identity = card.get("identity", {})
        pubkey = identity.get("public_key") or identity.get("pubkey_b64", "")

        data = _get_json(f"http://127.0.0.1:{relay_with_identity}/.well-known/jwks.json")
        kid = data["keys"][0]["kid"]

        expected_kid = f"{agent_name}:{pubkey[:8]}"
        assert kid == expected_kid, (
            f"kid should be '{expected_kid}', got '{kid}'"
        )

    def test_jw7_capability_trust_jwks(self, relay_with_identity):
        """JW7: capabilities.trust_jwks=True in AgentCard."""
        card = _get_agent_card(relay_with_identity)
        caps = card.get("capabilities", {})
        assert caps.get("trust_jwks") is True, \
            f"capabilities.trust_jwks should be True, got {caps.get('trust_jwks')!r}"

    def test_jw8_endpoint_in_endpoints(self, relay_with_identity):
        """JW8: endpoints.jwks='/.well-known/jwks.json' in AgentCard."""
        card = _get_agent_card(relay_with_identity)
        endpoints = card.get("endpoints", {})
        assert endpoints.get("jwks") == "/.well-known/jwks.json", (
            f"endpoints.jwks should be '/.well-known/jwks.json', got {endpoints.get('jwks')!r}"
        )

    def test_jw9_trust_signals_contains_jwks(self, relay_with_identity):
        """JW9: trust.signals contains 'jwks' type when --identity enabled."""
        card = _get_agent_card(relay_with_identity)
        signals = card.get("trust", {}).get("signals", [])
        sig_types = {s["type"] for s in signals}
        assert "jwks" in sig_types, (
            f"trust.signals should contain 'jwks' type when --identity enabled. Found: {sig_types}"
        )

    def test_jw10_jwks_signal_fields(self, relay_with_identity):
        """JW10: jwks signal has jwks_uri and alg fields."""
        card = _get_agent_card(relay_with_identity)
        signals = card.get("trust", {}).get("signals", [])
        jwks_sig = next((s for s in signals if s["type"] == "jwks"), None)
        assert jwks_sig is not None, "No 'jwks' signal in trust.signals"
        assert jwks_sig.get("enabled") is True, "jwks signal should be enabled with --identity"
        assert jwks_sig.get("jwks_uri") == "/.well-known/jwks.json", (
            f"jwks_uri should be '/.well-known/jwks.json', got {jwks_sig.get('jwks_uri')!r}"
        )
        assert jwks_sig.get("alg") == "EdDSA", (
            f"alg should be 'EdDSA', got {jwks_sig.get('alg')!r}"
        )


# ── capability also available without identity (always declared) ──────────────

class TestJWKSCapabilityAlwaysDeclared:

    def test_jw7_capability_no_identity(self, relay_no_identity):
        """JW7 (no identity): capabilities.trust_jwks=True is always declared."""
        card = _get_agent_card(relay_no_identity)
        caps = card.get("capabilities", {})
        assert caps.get("trust_jwks") is True, \
            "capabilities.trust_jwks should always be True (endpoint always available)"

    def test_jw8_endpoint_no_identity(self, relay_no_identity):
        """JW8 (no identity): endpoints.jwks is present even without --identity."""
        card = _get_agent_card(relay_no_identity)
        endpoints = card.get("endpoints", {})
        assert endpoints.get("jwks") == "/.well-known/jwks.json", \
            "endpoints.jwks should always be declared"
