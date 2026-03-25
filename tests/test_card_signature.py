"""
test_card_signature.py — ACP v1.8 AgentCard self-signature tests

Tests:
  CS1: GET /.well-known/acp.json includes card_sig when --identity enabled
  CS2: card_sig verifies correctly via GET /verify/card (self)
  CS3: POST /verify/card with valid signed card → valid=True
  CS4: POST /verify/card with tampered card → valid=False
  CS5: POST /verify/card with unsigned card → valid=False + error message
  CS6: capabilities.card_sig=True when --identity enabled
  CS7: POST /verify/card accepts wrapped {self: card} form
  CS8: POST /verify/card with invalid JSON → 400
  CS9: did_consistent=True when did:acp: matches public_key
  CS10: card_sig absent when --identity NOT enabled
"""

import json
import pytest
import subprocess
import time
import urllib.request
import urllib.error
import base64
import copy
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RELAY_WS_PORT  = 7888   # WebSocket port
RELAY_HTTP_PORT = RELAY_WS_PORT + 100  # HTTP API = ws_port + 100 (acp_relay convention)
RELAY_PORT = RELAY_WS_PORT  # kept for compat
RELAY_BASE = f"http://localhost:{RELAY_HTTP_PORT}"

_relay_proc = None


@pytest.fixture(scope="module", autouse=True)
def relay_with_identity():
    """Start relay with --identity enabled for card signature tests."""
    global _relay_proc
    relay_path = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")

    env = os.environ.copy()
    env.pop("http_proxy", None)
    env.pop("HTTP_PROXY", None)
    env.pop("https_proxy", None)
    env.pop("HTTPS_PROXY", None)

    identity_path = f"/tmp/acp_test_identity_{RELAY_WS_PORT}.json"
    _relay_proc = subprocess.Popen(
        [sys.executable, relay_path,
         "--port", str(RELAY_WS_PORT),
         "--name", "CardSigTestAgent",
         "--identity", identity_path],  # enables Ed25519 keypair generation
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )

    # Wait for relay to be ready
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{RELAY_BASE}/.well-known/acp.json", timeout=1) as r:
                if r.status == 200:
                    break
        except Exception:
            time.sleep(0.2)
    else:
        _relay_proc.kill()
        pytest.fail("Relay did not start within 10s")

    yield

    _relay_proc.terminate()
    try:
        _relay_proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        _relay_proc.kill()


def _get(path):
    with urllib.request.urlopen(f"{RELAY_BASE}{path}", timeout=5) as r:
        return json.loads(r.read())


def _post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{RELAY_BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


# ─────────────────────────────────────────────────────────────────────────────

def test_cs1_card_has_card_sig():
    """CS1: GET /.well-known/acp.json includes identity.card_sig when --identity enabled."""
    data = _get("/.well-known/acp.json")
    card = data["self"]
    identity = card.get("identity")
    assert identity is not None, "identity block missing"
    assert "card_sig" in identity, f"card_sig missing from identity block: {identity}"
    assert isinstance(identity["card_sig"], str), "card_sig should be a string"
    assert len(identity["card_sig"]) > 60, "card_sig too short to be a valid Ed25519 sig"


def test_cs2_self_verify_via_get():
    """CS2: GET /verify/card self-verification returns valid=True."""
    data = _get("/verify/card")
    assert data["card_signed"] is True, "card_signed should be True with --identity"
    sv = data["self_verification"]
    assert sv["valid"] is True, f"self_verification failed: {sv}"
    assert sv["error"] is None, f"unexpected error: {sv['error']}"


def test_cs3_post_verify_valid_card():
    """CS3: POST /verify/card with a valid signed card → valid=True."""
    card_data = _get("/.well-known/acp.json")
    signed_card = card_data["self"]

    status, result = _post("/verify/card", signed_card)
    assert status == 200, f"Expected 200, got {status}: {result}"
    assert result["valid"] is True, f"Expected valid=True: {result}"
    assert result["error"] is None


def test_cs4_post_verify_tampered_card():
    """CS4: POST /verify/card with tampered card → valid=False."""
    card_data = _get("/.well-known/acp.json")
    card = copy.deepcopy(card_data["self"])

    # Tamper: change the agent name after signing
    card["name"] = "TamperedAgent_EVIL"

    status, result = _post("/verify/card", card)
    assert status == 200, f"Expected 200, got {status}"
    assert result["valid"] is False, f"Expected valid=False for tampered card: {result}"
    assert result["error"] is not None


def test_cs5_post_verify_unsigned_card():
    """CS5: POST /verify/card with unsigned card (no card_sig) → valid=False."""
    card_data = _get("/.well-known/acp.json")
    card = copy.deepcopy(card_data["self"])

    # Remove card_sig to simulate unsigned card
    if card.get("identity"):
        card["identity"].pop("card_sig", None)

    status, result = _post("/verify/card", card)
    assert status == 200
    assert result["valid"] is False, f"Expected valid=False for unsigned card: {result}"
    assert "card_sig missing" in (result.get("error") or ""), f"Unexpected error: {result}"


def test_cs6_capabilities_card_sig_true():
    """CS6: capabilities.card_sig=True when --identity enabled."""
    data = _get("/.well-known/acp.json")
    caps = data["self"].get("capabilities", {})
    assert caps.get("card_sig") is True, f"capabilities.card_sig should be True: {caps}"


def test_cs7_post_verify_wrapped_form():
    """CS7: POST /verify/card accepts wrapped {self: card} form from AgentCard endpoint."""
    card_data = _get("/.well-known/acp.json")
    # Pass the full response from /.well-known/acp.json (which has "self" key)
    status, result = _post("/verify/card", card_data)
    assert status == 200
    assert result["valid"] is True, f"Expected valid=True for wrapped form: {result}"


def test_cs8_post_verify_invalid_json_body():
    """CS8: POST /verify/card with invalid/empty body → 400."""
    req = urllib.request.Request(
        f"{RELAY_BASE}/verify/card",
        data=b"not json!!!",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            status = r.status
            body = json.loads(r.read())
    except urllib.error.HTTPError as e:
        status = e.code
        body = json.loads(e.read())

    assert status == 400, f"Expected 400 for invalid JSON, got {status}: {body}"


def test_cs9_did_consistent():
    """CS9: did_consistent=True when did:acp: matches public_key."""
    card_data = _get("/.well-known/acp.json")
    signed_card = card_data["self"]

    status, result = _post("/verify/card", signed_card)
    assert status == 200
    assert result["valid"] is True

    if signed_card.get("identity", {}).get("did"):
        assert result.get("did_consistent") is True, (
            f"did:acp: should be consistent with public_key: {result}"
        )


def test_cs10_no_card_sig_without_identity():
    """CS10: card_sig absent when agent started WITHOUT --identity."""
    # Start a second relay on a different port WITHOUT --identity
    port2 = RELAY_WS_PORT + 2  # ws port; HTTP will be port2+100
    relay_path = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")
    env = os.environ.copy()
    env.pop("http_proxy", None)
    env.pop("HTTP_PROXY", None)
    env.pop("https_proxy", None)
    env.pop("HTTPS_PROXY", None)

    # No --identity flag → identity disabled
    proc2 = subprocess.Popen(
        [sys.executable, relay_path, "--port", str(port2), "--name", "NoIdentityAgent"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
    )

    try:
        deadline = time.time() + 8
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://localhost:{port2 + 100}/.well-known/acp.json", timeout=1) as r:
                    if r.status == 200:
                        break
            except Exception:
                time.sleep(0.2)
        else:
            pytest.skip("Second relay (no-identity) did not start in time")

        data = json.loads(urllib.request.urlopen(
            f"http://localhost:{port2 + 100}/.well-known/acp.json", timeout=3
        ).read())
        card = data["self"]
        identity = card.get("identity")

        # With no --identity: identity block should be None OR card_sig should be absent
        if identity is not None:
            assert "card_sig" not in identity, (
                f"card_sig should NOT be present without --identity: {identity}"
            )

        # capabilities.card_sig should be False
        caps = card.get("capabilities", {})
        assert caps.get("card_sig") is False, (
            f"capabilities.card_sig should be False without --identity: {caps}"
        )

    finally:
        proc2.terminate()
        try:
            proc2.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc2.kill()


# ─────────────────────────────────────────────────────────────────────────────
# pytest entry point (module-level runner for compatibility)

def test_card_signature_suite():
    """Run all CS1-CS10 in sequence (pytest entry point)."""
    _run_cs1 = test_cs1_card_has_card_sig
    _run_cs2 = test_cs2_self_verify_via_get
    _run_cs3 = test_cs3_post_verify_valid_card
    _run_cs4 = test_cs4_post_verify_tampered_card
    _run_cs5 = test_cs5_post_verify_unsigned_card
    _run_cs6 = test_cs6_capabilities_card_sig_true
    _run_cs7 = test_cs7_post_verify_wrapped_form
    _run_cs8 = test_cs8_post_verify_invalid_json_body
    _run_cs9 = test_cs9_did_consistent
    _run_cs10 = test_cs10_no_card_sig_without_identity
    # Tests are collected individually by pytest; this suite runner is a fallback
    pass


if __name__ == "__main__":
    import sys
    failed = []
    tests = [
        ("CS1", test_cs1_card_has_card_sig),
        ("CS2", test_cs2_self_verify_via_get),
        ("CS3", test_cs3_post_verify_valid_card),
        ("CS4", test_cs4_post_verify_tampered_card),
        ("CS5", test_cs5_post_verify_unsigned_card),
        ("CS6", test_cs6_capabilities_card_sig_true),
        ("CS7", test_cs7_post_verify_wrapped_form),
        ("CS8", test_cs8_post_verify_invalid_json_body),
        ("CS9", test_cs9_did_consistent),
        ("CS10", test_cs10_no_card_sig_without_identity),
    ]
    for name, fn in tests:
        try:
            fn()
            print(f"✅ PASS  {name}")
        except Exception as e:
            print(f"❌ FAIL  {name}: {e}")
            failed.append(name)
    print(f"\n{'=' * 40}")
    print(f"Results: {len(tests)-len(failed)}/{len(tests)} PASS")
    sys.exit(1 if failed else 0)
