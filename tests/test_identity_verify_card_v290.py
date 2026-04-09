"""
test_identity_verify_card_v290.py — ACP v2.90 POST /identity/verify-card tests

Tests:
  IVC1: Valid signed AgentCard → verified=True, did present
  IVC2: Card with tampered signature → verified=False
  IVC3: Card without card_sig (unsigned) → verified=False, error explains
  IVC4: Card without identity block at all → verified=False
  IVC5: Missing 'card' field in request body → 400 error
  IVC6: Empty body → 400 error
  IVC7: did_consistent=True when did:acp: matches public_key
  IVC8: capability flag 'offline_card_verify' present in /.well-known/acp.json
  IVC9: endpoint entry 'offline_card_verify' present in /.well-known/acp.json
"""

import base64
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


# ── Card-building helpers (using cryptography directly, no relay required) ─────

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _make_signed_card(name: str = "TestAgent") -> tuple:
    """Build a fully signed AgentCard using cryptography library directly.
    Returns (signed_card, public_key_b64url).
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    priv = Ed25519PrivateKey.generate()
    pub_raw = priv.public_key().public_bytes_raw()
    pub_b64 = _b64url(pub_raw)
    did = "did:acp:" + pub_b64

    card = {
        "name": name,
        "version": "1.0",
        "skills": [],
        "identity": {
            "scheme": "ed25519",
            "public_key": pub_b64,
            "did": did,
        },
    }
    # Same canonical payload as _sign_agent_card in acp_relay.py
    payload = json.dumps(card, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    sig_bytes = priv.sign(payload)
    card["identity"]["card_sig"] = _b64url(sig_bytes)
    return card, pub_b64


def _make_unsigned_card(name: str = "UnsignedAgent") -> dict:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    priv = Ed25519PrivateKey.generate()
    pub_raw = priv.public_key().public_bytes_raw()
    pub_b64 = _b64url(pub_raw)
    return {
        "name": name,
        "version": "1.0",
        "skills": [],
        "identity": {
            "scheme": "ed25519",
            "public_key": pub_b64,
            "did": "did:acp:" + pub_b64,
        },
    }


# ── Relay helpers ──────────────────────────────────────────────────────────────

def _free_port_pair() -> tuple:
    """Return (ws_port, http_port) where http_port = ws_port + 100, both free."""
    for _ in range(60):
        ws = random.randint(49200, 49299)
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


def _post(http_port, path, body: dict) -> tuple:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"http://localhost:{http_port}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


# ── Fixture ────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def relay_proc():
    """Start relay; HTTP port = ws_port + 100 (relay convention)."""
    ws_port, http_port = _free_port_pair()
    # Note: relay has no --http-port flag; HTTP listens on ws_port+100 automatically
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


# ══════════════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not IDENTITY_AVAILABLE, reason="cryptography not installed")
class TestIdentityVerifyCard:

    def test_ivc1_valid_signed_card(self, relay_proc):
        """IVC1: Valid signed AgentCard → verified=True, did present."""
        signed, pub_b64 = _make_signed_card("AgentAlpha")
        status, resp = _post(relay_proc, "/identity/verify-card", {"card": signed})
        assert status == 200, f"Unexpected status {status}: {resp}"
        assert resp["verified"] is True, f"Expected verified=True: {resp}"
        assert resp["did"] is not None
        assert resp["public_key"] == pub_b64
        assert resp.get("error") is None

    def test_ivc2_tampered_signature(self, relay_proc):
        """IVC2: Card with tampered card_sig → verified=False."""
        signed, _ = _make_signed_card("AgentBeta")
        orig_sig = signed["identity"]["card_sig"]
        sig_bytes = bytearray(base64.urlsafe_b64decode(orig_sig + "=="))
        sig_bytes[-1] ^= 0xFF
        signed["identity"]["card_sig"] = _b64url(bytes(sig_bytes))

        status, resp = _post(relay_proc, "/identity/verify-card", {"card": signed})
        assert status == 200
        assert resp["verified"] is False
        assert resp.get("error") is not None

    def test_ivc3_unsigned_card(self, relay_proc):
        """IVC3: Card without card_sig → verified=False, error explains."""
        card = _make_unsigned_card("AgentGamma")
        status, resp = _post(relay_proc, "/identity/verify-card", {"card": card})
        assert status == 200
        assert resp["verified"] is False
        assert resp.get("error") is not None
        assert "card_sig" in resp["error"] or "unsigned" in resp["error"]

    def test_ivc4_no_identity_block(self, relay_proc):
        """IVC4: Card without identity block → verified=False."""
        card = {"name": "AnonymousAgent", "version": "1.0", "skills": []}
        status, resp = _post(relay_proc, "/identity/verify-card", {"card": card})
        assert status == 200
        assert resp["verified"] is False

    def test_ivc5_missing_card_field(self, relay_proc):
        """IVC5: Body without 'card' field → 400."""
        status, resp = _post(relay_proc, "/identity/verify-card", {"not_card": {}})
        assert status == 400
        assert "error" in resp

    def test_ivc6_empty_body(self, relay_proc):
        """IVC6: Empty JSON body → 400."""
        status, resp = _post(relay_proc, "/identity/verify-card", {})
        assert status == 400
        assert "error" in resp

    def test_ivc7_did_consistent(self, relay_proc):
        """IVC7: did:acp: is consistent with public_key → did_consistent=True."""
        signed, _ = _make_signed_card("AgentDelta")
        status, resp = _post(relay_proc, "/identity/verify-card", {"card": signed})
        assert status == 200
        assert resp["verified"] is True
        assert resp.get("did_consistent") is True

    def test_ivc8_capability_flag(self, relay_proc):
        """IVC8: capabilities.offline_card_verify present in /.well-known/acp.json."""
        with urllib.request.urlopen(
            f"http://localhost:{relay_proc}/.well-known/acp.json", timeout=5
        ) as r:
            info = json.loads(r.read())
        # well-known response is wrapped: {"self": <card>, "peer": ...}
        card = info.get("self", info)
        caps = card.get("capabilities", {})
        assert caps.get("offline_card_verify") is True, \
            f"offline_card_verify capability missing; keys={list(caps.keys())}"

    def test_ivc9_endpoint_entry(self, relay_proc):
        """IVC9: endpoints.offline_card_verify in /.well-known/acp.json."""
        with urllib.request.urlopen(
            f"http://localhost:{relay_proc}/.well-known/acp.json", timeout=5
        ) as r:
            info = json.loads(r.read())
        # well-known response is wrapped: {"self": <card>, "peer": ...}
        card = info.get("self", info)
        endpoints = card.get("endpoints", {})
        assert "offline_card_verify" in endpoints, \
            f"offline_card_verify endpoint missing; keys={list(endpoints.keys())}"
        assert endpoints["offline_card_verify"] == "/identity/verify-card"
