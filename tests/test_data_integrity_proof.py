"""
tests/test_data_integrity_proof.py — ACP v3.2 W3C DataIntegrityProof compat layer

Validates that outbound messages carry a W3C-format `proof` object alongside
msg_sig, and that the new POST /verify/proof endpoint correctly verifies it.

Aligned with ANP 2026-04-10 DataIntegrityProof standard (Ed25519Signature2020).

Tests:
  DIP-01  Outbound message contains `proof` object with all required fields
          (type / verificationMethod / created / proofPurpose / proofValue)
  DIP-02  proof.type == "Ed25519Signature2020"
  DIP-03  proof.proofValue == msg_sig when to="" (same canonical payload → identical sig)
  DIP-04  POST /verify/proof — valid proof → {"valid": true}
  DIP-05  POST /verify/proof — tampered proofValue → {"valid": false}
  DIP-06  capabilities.data_integrity_proof is a boolean
"""

import base64
import json
import os
import sys

import pytest
import requests

# ── Relay module path ─────────────────────────────────────────────────────────

RELAY_DIR = os.path.join(os.path.dirname(__file__), "..", "relay")
sys.path.insert(0, RELAY_DIR)


def _load_relay_module():
    """Load acp_relay as a module (same pattern as test_message_sig.py)."""
    import importlib.util
    import pathlib
    import unittest.mock as mock

    spec = importlib.util.spec_from_file_location(
        "acp_relay_dip",
        pathlib.Path(RELAY_DIR) / "acp_relay.py",
    )
    mod = importlib.util.module_from_spec(spec)
    with mock.patch("sys.argv", ["acp_relay.py"]):
        try:
            spec.loader.exec_module(mod)
        except SystemExit:
            pass
    return mod


@pytest.fixture(scope="module")
def relay_mod():
    return _load_relay_module()


# ── Ed25519 key pair for unit tests ──────────────────────────────────────────

@pytest.fixture(scope="module")
def keypair():
    """Generate a fresh Ed25519 key pair for unit-level tests."""
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        import base64 as _b64

        priv = Ed25519PrivateKey.generate()
        pub = priv.public_key()
        pub_bytes = pub.public_bytes_raw()
        pub_b64 = _b64.urlsafe_b64encode(pub_bytes).rstrip(b"=").decode()
        return priv, pub_b64
    except ImportError:
        pytest.skip("cryptography library not available")


# ── Live relay fixture (same pattern as test_message_sig.py) ─────────────────

@pytest.fixture(scope="module")
def relay_url():
    import subprocess
    import socket
    import time
    import os as _os

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        ws_port = s.getsockname()[1]
    http_port = ws_port + 100
    relay_dir = _os.path.join(_os.path.dirname(__file__), "..", "relay")
    relay_script = _os.path.join(relay_dir, "acp_relay.py")
    identity_file = _os.path.expanduser("~/.acp/identity.json")
    cmd = ["python3", relay_script, "--port", str(ws_port), "--identity", identity_file, "--local-only"]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{http_port}"
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            import urllib.request
            urllib.request.urlopen(f"{url}/status", timeout=2)
            break
        except Exception:
            time.sleep(0.3)
    else:
        proc.terminate()
        pytest.skip(f"relay failed to start on port {http_port}")
    yield url
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()


# ── Helper: build a signed message with proof via the relay module ─────────────

def _make_signed_message_with_proof(keypair, relay_mod, to: str = ""):
    """
    Construct a message dict with msg_sig + proof fields, using the test keypair.
    Monkey-patches the relay module globals to use our test key pair.
    """
    priv, pub_b64 = keypair
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        import base64 as _b64
    except ImportError:
        pytest.skip("cryptography not available")

    # Patch relay module globals so _sign_message and _build_proof_object use our key
    original_priv = relay_mod._ed25519_private
    original_pub = relay_mod._ed25519_public_b64
    relay_mod._ed25519_private = priv
    relay_mod._ed25519_public_b64 = pub_b64
    try:
        msg = {
            "message_id": "msg_dip_unit_001",
            "from":       "test-agent-dip",
            "parts":      [{"type": "text", "text": "DIP unit test message"}],
            "ts":         "1744400000",
        }
        result = relay_mod._attach_sig(dict(msg), to=to)
    finally:
        relay_mod._ed25519_private = original_priv
        relay_mod._ed25519_public_b64 = original_pub

    return result, pub_b64


# ── Test cases ────────────────────────────────────────────────────────────────

# DIP-01: Outbound message contains `proof` object with all required W3C fields
def test_dip01_proof_object_present_with_all_fields(keypair, relay_mod):
    """DIP-01: _attach_sig produces a `proof` object containing all required W3C DI fields."""
    msg, _ = _make_signed_message_with_proof(keypair, relay_mod, to="")
    assert "proof" in msg, (
        "_attach_sig should attach a `proof` field when identity key is available. "
        f"Message keys: {list(msg.keys())}"
    )
    proof = msg["proof"]
    required_fields = {"type", "verificationMethod", "created", "proofPurpose", "proofValue"}
    missing = required_fields - set(proof.keys())
    assert not missing, (
        f"proof object is missing required W3C DataIntegrityProof fields: {missing}. "
        f"Got fields: {set(proof.keys())}"
    )


# DIP-02: proof.type == "Ed25519Signature2020"
def test_dip02_proof_type_is_ed25519signature2020(keypair, relay_mod):
    """DIP-02: proof.type must be exactly 'Ed25519Signature2020'."""
    msg, _ = _make_signed_message_with_proof(keypair, relay_mod, to="")
    assert "proof" in msg, "proof field must be present (DIP-01 prerequisite)"
    proof_type = msg["proof"].get("type")
    assert proof_type == "Ed25519Signature2020", (
        f"proof.type must be 'Ed25519Signature2020', got: {proof_type!r}"
    )


# DIP-03: proof.proofValue == msg_sig when to="" (same canonical payload)
def test_dip03_proof_value_equals_msg_sig_when_no_to(keypair, relay_mod):
    """DIP-03: proof.proofValue and msg_sig use the same canonical payload when to=''.
    Since Ed25519 is deterministic, both values must be identical.
    """
    msg, _ = _make_signed_message_with_proof(keypair, relay_mod, to="")
    assert "msg_sig" in msg, "msg_sig must be present"
    assert "proof" in msg, "proof must be present"
    proof_value = msg["proof"].get("proofValue")
    msg_sig_value = msg["msg_sig"]
    assert proof_value == msg_sig_value, (
        f"proof.proofValue must equal msg_sig when to='' (same canonical payload, deterministic Ed25519). "
        f"proof.proofValue={proof_value!r}, msg_sig={msg_sig_value!r}"
    )


# DIP-04: POST /verify/proof — valid proof → {"valid": true}
def test_dip04_verify_proof_endpoint_valid(relay_url):
    """DIP-04: POST /verify/proof returns valid=true for a properly constructed proof."""
    # Check relay has identity
    status = requests.get(f"{relay_url}/status", timeout=10).json()
    caps = {
        **status.get("capabilities", {}),
        **status.get("agent_card", {}).get("capabilities", {}),
    }
    if not caps.get("data_integrity_proof"):
        pytest.skip("relay started without --identity; data_integrity_proof capability disabled")

    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        import base64 as _b64
    except ImportError:
        pytest.skip("cryptography not available")

    # Generate a fresh key pair and build a proof manually
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key().public_bytes_raw()
    pub_b64 = _b64.urlsafe_b64encode(pub).rstrip(b"=").decode()

    test_msg = {
        "message_id": "msg_dip04_valid",
        "from":       "agent-dip04",
        "parts":      [{"type": "text", "text": "DIP-04 valid proof test"}],
        "ts":         "1744400400",
    }

    # Sign with the same canonical form as msg_sig (v3.0, no `to`)
    canonical = {
        "content":    json.dumps(test_msg.get("parts", []), sort_keys=True,
                                 ensure_ascii=False, separators=(",", ":")),
        "from":       str(test_msg["from"]),
        "message_id": str(test_msg["message_id"]),
        "ts":         str(test_msg["ts"]),
    }
    payload_bytes = json.dumps(canonical, sort_keys=True, ensure_ascii=False,
                               separators=(",", ":")).encode()
    sig_bytes = priv.sign(payload_bytes)
    proof_value = _b64.urlsafe_b64encode(sig_bytes).rstrip(b"=").decode()

    test_msg["proof"] = {
        "type":               "Ed25519Signature2020",
        "verificationMethod": f"did:acp:{pub_b64}#key-0",
        "created":            "2026-04-11T09:22:00Z",
        "proofPurpose":       "assertionMethod",
        "proofValue":         proof_value,
    }

    r = requests.post(f"{relay_url}/verify/proof", json={"message": test_msg}, timeout=10)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert data.get("valid") is True, (
        f"Expected valid=true for a correctly constructed proof, got: {data}"
    )
    assert data.get("type") == "Ed25519Signature2020"
    assert data.get("verificationMethod") == f"did:acp:{pub_b64}#key-0"


# DIP-05: POST /verify/proof — tampered proofValue → {"valid": false}
def test_dip05_verify_proof_endpoint_tampered(relay_url):
    """DIP-05: POST /verify/proof returns valid=false when proofValue is tampered."""
    status = requests.get(f"{relay_url}/status", timeout=10).json()
    caps = {
        **status.get("capabilities", {}),
        **status.get("agent_card", {}).get("capabilities", {}),
    }
    if not caps.get("data_integrity_proof"):
        pytest.skip("relay started without --identity; data_integrity_proof capability disabled")

    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        import base64 as _b64
    except ImportError:
        pytest.skip("cryptography not available")

    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key().public_bytes_raw()
    pub_b64 = _b64.urlsafe_b64encode(pub).rstrip(b"=").decode()

    test_msg = {
        "message_id": "msg_dip05_tampered",
        "from":       "agent-dip05",
        "parts":      [{"type": "text", "text": "DIP-05 tampered proof test"}],
        "ts":         "1744400500",
        "proof": {
            "type":               "Ed25519Signature2020",
            "verificationMethod": f"did:acp:{pub_b64}#key-0",
            "created":            "2026-04-11T09:22:00Z",
            "proofPurpose":       "assertionMethod",
            # Deliberately invalid proofValue (64 zero bytes, base64url-encoded)
            "proofValue":         _b64.urlsafe_b64encode(bytes(64)).rstrip(b"=").decode(),
        },
    }

    r = requests.post(f"{relay_url}/verify/proof", json={"message": test_msg}, timeout=10)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert data.get("valid") is False, (
        f"Expected valid=false for tampered proofValue, got: {data}"
    )


# DIP-06: capabilities.data_integrity_proof is a boolean
def test_dip06_capability_data_integrity_proof(relay_url):
    """DIP-06: capabilities.data_integrity_proof is present in /status and is a boolean."""
    status = requests.get(f"{relay_url}/status", timeout=10).json()
    agent_card_caps = status.get("agent_card", {}).get("capabilities", {})
    top_caps = status.get("capabilities", {})
    caps = {**top_caps, **agent_card_caps}

    assert "data_integrity_proof" in caps, (
        f"capabilities.data_integrity_proof should be present in /status. "
        f"agent_card.capabilities keys: {list(agent_card_caps.keys())}, "
        f"top-level capabilities keys: {list(top_caps.keys())}"
    )
    assert isinstance(caps["data_integrity_proof"], bool), (
        "capabilities.data_integrity_proof should be a boolean, "
        f"got: {type(caps['data_integrity_proof'])}"
    )
