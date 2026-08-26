"""
tests/test_origin_proof.py — ACP v3.1 origin_proof: recipient-bound msg_sig

Validates that the `to` field in the canonical signing payload binds the
signature to the intended recipient, preventing replay-to-wrong-recipient
attacks (aligned with ANP DataIntegrityProof / origin_proof pattern).

Tests:
  OP-01  _sign_message with `to` produces a different sig than without `to`
  OP-02  _verify_message_sig with matching `to` returns True
  OP-03  _verify_message_sig fails when `to` mismatch (wrong recipient)
  OP-04  Backward-compat: v3.0 sig (no `to`) still verifies without `to` arg
  OP-05  capabilities.origin_proof flag reflects identity availability (integration)
  OP-06  POST /verify/message with `to` field verifies origin_proof signature
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
    import importlib.util, pathlib
    import unittest.mock as mock

    spec = importlib.util.spec_from_file_location(
        "acp_relay_op",
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
    """Generate a fresh Ed25519 key pair for unit tests."""
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        import base64 as _b64
        priv = Ed25519PrivateKey.generate()
        pub  = priv.public_key()
        pub_bytes = pub.public_bytes_raw()
        pub_b64 = _b64.urlsafe_b64encode(pub_bytes).rstrip(b"=").decode()
        return priv, pub_b64
    except ImportError:
        pytest.skip("cryptography library not available")


def _make_sign_fn(priv, to: str = ""):
    """Return a signing function using `priv`, optionally with `to` binding."""
    import base64 as _b64

    def _sign(msg: dict) -> str:
        canonical = {
            "content":    json.dumps(msg.get("parts", []), sort_keys=True,
                                     ensure_ascii=False, separators=(",", ":")),
            "from":       str(msg.get("from", "")),
            "message_id": str(msg.get("message_id", "")),
            "ts":         str(msg.get("ts", "")),
        }
        if to:
            canonical["to"] = str(to)
        payload_bytes = json.dumps(canonical, sort_keys=True, ensure_ascii=False,
                                   separators=(",", ":")).encode()
        sig_bytes = priv.sign(payload_bytes)
        return _b64.urlsafe_b64encode(sig_bytes).rstrip(b"=").decode()

    return _sign


# ── Sample messages ───────────────────────────────────────────────────────────

SAMPLE_MSG = {
    "message_id": "msg_op_unit_001",
    "from":       "agent-alice",
    "parts":      [{"type": "text", "text": "Hello, origin_proof v3.1!"}],
    "ts":         "1744300000",
}

RECIPIENT_A = "peer_001"
RECIPIENT_B = "peer_002"


# ── Test cases ────────────────────────────────────────────────────────────────

# OP-01: sig with `to` differs from sig without `to`
def test_op01_sig_with_to_differs_from_without(keypair):
    """OP-01: Adding `to` to the canonical payload produces a different signature."""
    priv, _ = keypair
    sign_v30 = _make_sign_fn(priv, to="")
    sign_v31 = _make_sign_fn(priv, to=RECIPIENT_A)

    sig_v30 = sign_v30(SAMPLE_MSG)
    sig_v31 = sign_v31(SAMPLE_MSG)

    assert sig_v30 != sig_v31, (
        "Signature with `to` field must differ from signature without `to`. "
        "The canonical payload change must produce a distinct signature."
    )


# OP-02: _verify_message_sig with matching `to` returns True
def test_op02_verify_with_correct_to(relay_mod, keypair):
    """OP-02: _verify_message_sig returns True when `to` matches the signing recipient."""
    priv, pub_b64 = keypair
    sign_fn = _make_sign_fn(priv, to=RECIPIENT_A)

    msg = dict(SAMPLE_MSG)
    msg["msg_sig"] = sign_fn(msg)

    result = relay_mod._verify_message_sig(msg, pub_b64, to=RECIPIENT_A)
    assert result is True, (
        f"Verification with correct `to`='{RECIPIENT_A}' should return True. Got: {result}"
    )


# OP-03: _verify_message_sig fails when `to` doesn't match (wrong recipient)
def test_op03_verify_fails_wrong_recipient(relay_mod, keypair):
    """OP-03: origin_proof — signature bound to recipient_A must not verify for recipient_B."""
    priv, pub_b64 = keypair
    sign_fn = _make_sign_fn(priv, to=RECIPIENT_A)

    msg = dict(SAMPLE_MSG)
    msg["msg_sig"] = sign_fn(msg)

    # Attempt to verify as if the recipient is RECIPIENT_B — must fail
    result = relay_mod._verify_message_sig(msg, pub_b64, to=RECIPIENT_B)
    assert result is False, (
        f"Signature bound to '{RECIPIENT_A}' should NOT verify for '{RECIPIENT_B}'. "
        "This is the core origin_proof security guarantee."
    )


# OP-04: Backward-compat — v3.0 sig (no `to`) still verifies without `to` arg
def test_op04_backward_compat_v30_sig(relay_mod, keypair):
    """OP-04: v3.0 signature (no `to`) verifies correctly with _verify_message_sig(to='')."""
    priv, pub_b64 = keypair
    sign_fn_v30 = _make_sign_fn(priv, to="")  # v3.0 — no `to`

    msg = dict(SAMPLE_MSG)
    msg["msg_sig"] = sign_fn_v30(msg)

    # v3.0 verify — no `to` arg (default "")
    result_v30 = relay_mod._verify_message_sig(msg, pub_b64)
    assert result_v30 is True, "v3.0 sig (no `to`) should verify with default to='' argument"

    # Also assert it fails if someone tries to verify it as a v3.1 sig with a `to`
    result_wrong = relay_mod._verify_message_sig(msg, pub_b64, to=RECIPIENT_A)
    assert result_wrong is False, (
        "A v3.0 sig (no `to` in canonical) should NOT verify against a v3.1 canonical "
        "that includes `to` — the canonical payloads are different."
    )


# ── Integration fixture — live relay process ──────────────────────────────────

@pytest.fixture(scope="module")
def relay_url():
    """Start a dedicated relay instance; yield its HTTP URL, then stop."""
    import subprocess, socket, time

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        ws_port = s.getsockname()[1]
    http_port = ws_port + 100

    relay_dir = os.path.join(os.path.dirname(__file__), "..", "relay")
    relay_script = os.path.join(relay_dir, "acp_relay.py")
    identity_file = os.path.expanduser("~/.acp/identity.json")
    cmd = [
        "python3", relay_script,
        "--port", str(ws_port),
        "--identity", identity_file,
        "--local-only",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{http_port}"

    deadline = time.time() + 10
    ready = False
    while time.time() < deadline:
        try:
            import urllib.request
            urllib.request.urlopen(f"{url}/status", timeout=2)
            ready = True
            break
        except Exception:
            time.sleep(0.3)

    if not ready:
        proc.terminate()
        pytest.skip(f"relay failed to start on port {http_port}")

    yield url

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def _get_status(relay_url):
    r = requests.get(f"{relay_url}/status", timeout=10)
    r.raise_for_status()
    return r.json()


# OP-05: capabilities.origin_proof reflects identity availability
def test_op05_capability_origin_proof(relay_url):
    """OP-05: capabilities.origin_proof is present in /status and is a boolean."""
    status = _get_status(relay_url)
    agent_card_caps = status.get("agent_card", {}).get("capabilities", {})
    top_caps = status.get("capabilities", {})
    caps = {**top_caps, **agent_card_caps}

    assert "origin_proof" in caps, (
        f"capabilities.origin_proof should be present in /status. "
        f"agent_card.capabilities keys: {list(agent_card_caps.keys())}, "
        f"top-level capabilities keys: {list(top_caps.keys())}"
    )
    assert isinstance(caps["origin_proof"], bool), (
        "capabilities.origin_proof should be a boolean"
    )


# OP-06: POST /verify/message with `to` verifies origin_proof signature
def test_op06_verify_message_endpoint_with_to(relay_url):
    """OP-06: POST /verify/message accepts `to` param and correctly verifies origin_proof sig."""
    status = _get_status(relay_url)
    caps = status.get("capabilities", {})
    if not caps.get("msg_sig"):
        pytest.skip("relay started without --identity; msg_sig/origin_proof capability disabled")

    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        import base64 as _b64
    except ImportError:
        pytest.skip("cryptography not available")

    # Generate a fresh key pair for this test
    priv = Ed25519PrivateKey.generate()
    pub  = priv.public_key().public_bytes_raw()
    pub_b64 = _b64.urlsafe_b64encode(pub).rstrip(b"=").decode()

    recipient = "peer_op06_target"

    # Build an origin_proof-bound message (v3.1 canonical with `to`)
    test_msg = {
        "message_id": "msg_op06_origin_proof",
        "from":       "agent-alice",
        "parts":      [{"type": "text", "text": "OP-06 origin_proof integration test"}],
        "ts":         "1744300600",
    }
    sign_fn = _make_sign_fn(priv, to=recipient)
    test_msg["msg_sig"] = sign_fn(test_msg)

    # Should verify successfully with correct `to`
    r = requests.post(f"{relay_url}/verify/message", json={
        "message":    test_msg,
        "public_key": pub_b64,
        "to":         recipient,
    }, timeout=10)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert data.get("valid") is True, (
        f"Expected valid=true for correct origin_proof `to`, got: {data}"
    )
    assert data.get("ok") is True

    # Should fail verification with wrong `to` (replay-to-wrong-recipient defence)
    r_wrong = requests.post(f"{relay_url}/verify/message", json={
        "message":    test_msg,
        "public_key": pub_b64,
        "to":         "peer_wrong_recipient",
    }, timeout=10)
    assert r_wrong.status_code == 200
    data_wrong = r_wrong.json()
    assert data_wrong.get("valid") is False, (
        f"origin_proof sig must NOT verify for wrong recipient. Got: {data_wrong}"
    )
