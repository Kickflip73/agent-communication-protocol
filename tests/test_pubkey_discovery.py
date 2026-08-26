"""
tests/test_pubkey_discovery.py — PD1–PD8: DID pubkey discovery (v2.33)

Tests for GET|POST /identity/pubkey-discovery
Covers: capability declaration, did:acp: resolve, did:key: resolve,
        POST single, POST batch, invalid DID, missing param, endpoint declaration.
"""
import os
import sys
import time
import socket
import signal
import tempfile
import subprocess

import pytest
import requests

RELAY = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_ready(base, timeout=12.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{base}/.well-known/acp.json", timeout=2)
            if r.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.25)
    raise RuntimeError(f"relay at {base} did not become ready within {timeout}s")


@pytest.fixture(scope="module")
def relay_base():
    ws_port = _free_port()
    http_port = ws_port + 100
    identity_dir = tempfile.mkdtemp(prefix="acp_pd_test_")
    identity_path = os.path.join(identity_dir, "identity.json")
    proc = subprocess.Popen(
        [sys.executable, RELAY,
         "--port", str(ws_port),
         "--name", "PDTestAgent",
         "--identity", identity_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    base = f"http://127.0.0.1:{http_port}"
    try:
        _wait_ready(base)
        yield base
    finally:
        proc.kill()


@pytest.fixture(scope="module")
def card(relay_base):
    r = requests.get(f"{relay_base}/.well-known/acp.json", timeout=5)
    assert r.status_code == 200
    raw = r.json()
    # Support both {"self": {...}} and flat card formats
    return raw.get("self", raw)


class TestPubkeyDiscovery:

    def test_pd1_capability_declared(self, card):
        """PD1: capabilities.pubkey_discovery must be True."""
        caps = card.get("capabilities", {})
        assert caps.get("pubkey_discovery") is True, \
            f"pubkey_discovery not in capabilities: {list(caps.keys())}"

    def test_pd2_get_did_acp_resolves(self, relay_base, card):
        """PD2: GET /identity/pubkey-discovery?did=did:acp:... returns correct pubkey."""
        did = card.get("identity", {}).get("did_acp")
        expected_pubkey = card.get("identity", {}).get("public_key") \
                       or card.get("identity", {}).get("pubkey_b64")
        if not did or not did.startswith("did:acp:"):
            pytest.skip("relay did:acp: not available")
        r = requests.get(f"{relay_base}/identity/pubkey-discovery",
                         params={"did": did}, timeout=5)
        assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}"
        data = r.json()
        assert data["ok"] is True
        assert data["did"] == did
        assert data["scheme"] == "did:acp"
        assert data["algorithm"] == "ed25519"
        if expected_pubkey:
            assert data["public_key_b64"] == expected_pubkey, \
                f"pubkey mismatch: {data['public_key_b64']} != {expected_pubkey}"
        assert data["consistent"] is True
        assert "public_key_hex" in data
        assert len(data["public_key_hex"]) == 64  # 32 bytes = 64 hex chars

    def test_pd3_get_did_key_resolves(self, relay_base, card):
        """PD3: GET /identity/pubkey-discovery?did=did:key:z... returns correct pubkey."""
        did = card.get("identity", {}).get("did_key")
        expected_pubkey = card.get("identity", {}).get("public_key") \
                       or card.get("identity", {}).get("pubkey_b64")
        if not did or not did.startswith("did:key:z"):
            pytest.skip("relay did:key: not available")
        r = requests.get(f"{relay_base}/identity/pubkey-discovery",
                         params={"did": did}, timeout=5)
        assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}"
        data = r.json()
        assert data["ok"] is True
        assert data["scheme"] == "did:key"
        assert data["algorithm"] == "ed25519"
        if expected_pubkey:
            assert data["public_key_b64"] == expected_pubkey
        assert data["consistent"] is True

    def test_pd4_post_single_did(self, relay_base, card):
        """PD4: POST /identity/pubkey-discovery with {did} body resolves correctly."""
        did = card.get("identity", {}).get("did_acp")
        if not did:
            pytest.skip("relay DID not available")
        r = requests.post(f"{relay_base}/identity/pubkey-discovery",
                          json={"did": did}, timeout=5)
        assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}"
        data = r.json()
        assert data["ok"] is True
        assert data["did"] == did
        assert "public_key_b64" in data

    def test_pd5_post_batch_dids(self, relay_base, card):
        """PD5: POST /identity/pubkey-discovery with {dids: [...]} resolves batch."""
        did_acp = card.get("identity", {}).get("did_acp")
        did_key = card.get("identity", {}).get("did_key")
        dids = [d for d in [did_acp, did_key] if d]
        if len(dids) < 2:
            pytest.skip("need both did:acp: and did:key: for batch test")
        r = requests.post(f"{relay_base}/identity/pubkey-discovery",
                          json={"dids": dids}, timeout=5)
        assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}"
        data = r.json()
        assert data["ok"] is True
        assert data["count"] == 2
        results = data["results"]
        assert len(results) == 2
        assert all(res["ok"] for res in results), \
            f"some results failed: {[r for r in results if not r['ok']]}"
        # Both should resolve to the same pubkey (same agent)
        pubkeys = {res["public_key_b64"] for res in results}
        assert len(pubkeys) == 1, f"different pubkeys from same agent: {pubkeys}"

    def test_pd6_invalid_did_returns_error(self, relay_base):
        """PD6: Unsupported DID scheme returns ok:false with descriptive error."""
        r = requests.get(f"{relay_base}/identity/pubkey-discovery",
                         params={"did": "did:unknown:abc123"}, timeout=5)
        assert r.status_code == 400, f"Expected 400, got {r.status_code}"
        data = r.json()
        assert data["ok"] is False
        assert "error" in data
        assert "unsupported" in data["error"].lower(), \
            f"error message unexpected: {data['error']}"

    def test_pd7_missing_did_param_returns_400(self, relay_base):
        """PD7: GET without ?did= returns 400 with error."""
        r = requests.get(f"{relay_base}/identity/pubkey-discovery", timeout=5)
        assert r.status_code == 400, f"Expected 400, got {r.status_code}"
        data = r.json()
        assert data["ok"] is False
        assert "error" in data

    def test_pd8_endpoint_declared_in_card(self, card):
        """PD8: endpoints.pubkey_discovery must be declared in AgentCard."""
        endpoints = card.get("endpoints", {})
        assert "pubkey_discovery" in endpoints, \
            f"pubkey_discovery not in endpoints: {list(endpoints.keys())}"
        assert "/identity/pubkey-discovery" in endpoints["pubkey_discovery"], \
            f"unexpected endpoint value: {endpoints['pubkey_discovery']}"
