"""v2.63: POST /verify/external-token + GET /identity/did-key test suite

Tests ETV-1..16 covering:
  ETV-1..4:   GET /identity/did-key — W3C did:key derivation + roundtrip
  ETV-5..8:   POST /verify/external-token — valid SINT token
  ETV-9..10:  Expiry handling (expired/future)
  ETV-11..12: Invalid/tampered signature rejection
  ETV-13..16: Malformed input error handling

Cross-protocol compatibility:
  ACP did:key derivation: multicodec [0xed, 0x01] + base58btc — identical to
  APS v1.32.0 toDIDKey() and SINT keyToDid() (A2A #1713 cross-verify, 9/9 PASS, 2026-04-06).
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time

import pytest
import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_RELAY_PY = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")
_IDENTITY_FILE = os.path.expanduser("~/.acp/identity_etv_test.key")


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(port: int, timeout: float = 12.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return True
        except OSError:
            time.sleep(0.15)
    return False


def _clean_env():
    env = os.environ.copy()
    for k in list(env.keys()):
        if "PROXY" in k.upper():
            del env[k]
    return env


def _gen_identity_file(path: str) -> str:
    """Generate Ed25519 identity key file via --gen-identity, return path."""
    subprocess.run(
        [sys.executable, _RELAY_PY, "--gen-identity", "--identity", path],
        capture_output=True, env=_clean_env(),
    )
    return path


@pytest.fixture(scope="module")
def relay_with_identity():
    """Relay with Ed25519 identity loaded (required for ETV tests)."""
    # Generate identity if not exists
    os.makedirs(os.path.dirname(_IDENTITY_FILE), exist_ok=True)
    if not os.path.exists(_IDENTITY_FILE):
        _gen_identity_file(_IDENTITY_FILE)

    ws_port   = _find_free_port()
    http_port = ws_port + 100
    proc = subprocess.Popen(
        [sys.executable, _RELAY_PY,
         "--port", str(ws_port),
         "--name", "etv-test-relay",
         "--identity", _IDENTITY_FILE,
         "--test-mode"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env=_clean_env(),
    )
    assert _wait_for_port(http_port, 14), (
        f"etv relay did not start on HTTP port {http_port} (ws={ws_port})"
    )
    yield http_port
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except Exception:
        proc.kill()


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _get(port: int, path: str) -> dict:
    url = f"http://127.0.0.1:{port}{path}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read().decode())


def _post(port: int, path: str, body: dict) -> tuple[dict, int]:
    url = f"http://127.0.0.1:{port}{path}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data,
                                  headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read().decode()), r.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode()), e.code


# ---------------------------------------------------------------------------
# Ed25519 helpers
# ---------------------------------------------------------------------------

def _gen_keypair():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    private = Ed25519PrivateKey.generate()
    pub_raw = private.public_key().public_bytes_raw()
    return private, pub_raw


def _sign_canonical(private_key, subject_hex, resource, actions, tier, exp):
    actions_csv = ",".join(sorted(actions))
    exp_str     = str(int(exp)) if exp is not None else "0"
    canonical   = f"{subject_hex}|{resource}|{actions_csv}|{tier}|{exp_str}"
    sig         = private_key.sign(canonical.encode("utf-8"))
    return canonical, sig.hex()


def _make_token(private_key, pub_raw,
                resource="acp://test/skills/read",
                actions=None, tier="T1_read", exp=None):
    subject_hex = pub_raw.hex()
    if actions is None:
        actions = ["invoke"]
    _, sig_hex = _sign_canonical(private_key, subject_hex, resource, actions, tier, exp)
    token: dict = {
        "subject":   subject_hex,
        "resource":  resource,
        "actions":   actions,
        "tier":      tier,
        "signature": sig_hex,
    }
    if exp is not None:
        token["exp"] = exp
    return token


# ---------------------------------------------------------------------------
# Local did:key derivation (mirrors ACP/APS/SINT implementation)
# ---------------------------------------------------------------------------

_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

def _base58_encode(data: bytes) -> str:
    num = int.from_bytes(data, "big")
    result = ""
    while num > 0:
        num, rem = divmod(num, 58)
        result = _B58_ALPHABET[rem] + result
    for byte in data:
        if byte == 0:
            result = "1" + result
        else:
            break
    return result


def _expect_did_key(pub_raw: bytes) -> str:
    """Compute expected did:key — same algorithm as ACP, APS v1.32.0, and SINT."""
    prefixed = bytes([0xed, 0x01]) + pub_raw
    return f"did:key:z{_base58_encode(prefixed)}"


# ===========================================================================
# ETV-1..4: GET /identity/did-key
# ===========================================================================

def test_etv1_did_key_returns_ok(relay_with_identity):
    """ETV-1: GET /identity/did-key returns ok=true and did_key."""
    data = _get(relay_with_identity, "/identity/did-key")
    assert data.get("ok") is True,     f"ETV-1: ok not true: {data}"
    assert data.get("did_key"),        f"ETV-1: did_key missing: {data}"


def test_etv2_did_key_format(relay_with_identity):
    """ETV-2: did:key starts with did:key:z6Mk (Ed25519 multicodec 0xed01 + base58btc)."""
    data = _get(relay_with_identity, "/identity/did-key")
    did  = data.get("did_key", "")
    assert did.startswith("did:key:z6Mk"), (
        f"ETV-2: expected did:key:z6Mk... (APS/SINT compatible), got: {did}"
    )


def test_etv3_did_key_hex_roundtrip(relay_with_identity):
    """ETV-3: public_key_hex → local _expect_did_key() matches endpoint did_key."""
    data    = _get(relay_with_identity, "/identity/did-key")
    hex_key = data.get("public_key_hex")
    if not hex_key:
        pytest.skip("public_key_hex not in response (identity not loaded)")
    pub_raw  = bytes.fromhex(hex_key)
    expected = _expect_did_key(pub_raw)
    actual   = data.get("did_key")
    assert actual == expected, (
        f"ETV-3: did_key mismatch\n  expected: {expected}\n  actual:   {actual}"
    )


def test_etv4_did_key_algorithm(relay_with_identity):
    """ETV-4: algorithm=Ed25519, multicodec=0xed01."""
    data = _get(relay_with_identity, "/identity/did-key")
    assert data.get("algorithm") == "Ed25519", \
        f"ETV-4: algorithm={data.get('algorithm')!r}, want Ed25519"
    assert data.get("multicodec") == "0xed01", \
        f"ETV-4: multicodec={data.get('multicodec')!r}, want 0xed01"


# ===========================================================================
# ETV-5..8: POST /verify/external-token — valid token
# ===========================================================================

def test_etv5_valid_token(relay_with_identity):
    """ETV-5: Valid SINT token — ok=true, valid=true, subject_did present."""
    priv, pub = _gen_keypair()
    token     = _make_token(priv, pub)
    resp, status = _post(relay_with_identity, "/verify/external-token", {"token": token})
    assert status == 200,               f"ETV-5: expected 200, got {status}: {resp}"
    assert resp.get("ok") is True,      f"ETV-5: ok not true: {resp}"
    assert resp.get("valid") is True,   f"ETV-5: valid not true: {resp}"
    assert resp.get("subject_did", "").startswith("did:key:"), \
        f"ETV-5: subject_did missing/wrong: {resp}"


def test_etv6_valid_token_did_key_matches(relay_with_identity):
    """ETV-6: subject_did from verify endpoint matches local _expect_did_key(pub)."""
    priv, pub = _gen_keypair()
    token     = _make_token(priv, pub, tier="T2_act")
    resp, _   = _post(relay_with_identity, "/verify/external-token", {"token": token})
    expected  = _expect_did_key(pub)
    actual    = resp.get("subject_did", "")
    assert actual == expected, (
        f"ETV-6: subject_did mismatch\n  expected: {expected}\n  actual:   {actual}"
    )


def test_etv7_fields_verified_steps(relay_with_identity):
    """ETV-7: fields_verified contains required verification steps."""
    priv, pub = _gen_keypair()
    token     = _make_token(priv, pub)
    resp, _   = _post(relay_with_identity, "/verify/external-token", {"token": token})
    fv        = resp.get("fields_verified", [])
    for step in ["required_fields", "subject_pubkey_decoded", "did_key_derived", "signature_valid"]:
        assert step in fv, f"ETV-7: '{step}' missing from fields_verified={fv}"


def test_etv8_relay_did_key_annotated(relay_with_identity):
    """ETV-8: relay_did_key present in response (this relay's DID for cross-reference)."""
    priv, pub = _gen_keypair()
    token     = _make_token(priv, pub)
    resp, _   = _post(relay_with_identity, "/verify/external-token", {"token": token})
    assert "relay_did_key" in resp, f"ETV-8: relay_did_key not in response: {resp}"


# ===========================================================================
# ETV-9..10: Expiry handling
# ===========================================================================

def test_etv9_expired_token_rejected(relay_with_identity):
    """ETV-9: Token with exp in the past → ok=false, expired=true."""
    priv, pub  = _gen_keypair()
    past_exp   = int(time.time()) - 3600
    token      = _make_token(priv, pub, exp=past_exp)
    resp, _    = _post(relay_with_identity, "/verify/external-token", {"token": token})
    assert resp.get("ok") is False,     f"ETV-9: expected ok=false for expired token: {resp}"
    assert resp.get("expired") is True, f"ETV-9: expected expired=true: {resp}"


def test_etv10_future_exp_accepted(relay_with_identity):
    """ETV-10: Token with exp in the future → ok=true, valid=true, expired=false."""
    priv, pub   = _gen_keypair()
    future_exp  = int(time.time()) + 3600
    token       = _make_token(priv, pub, exp=future_exp)
    resp, _     = _post(relay_with_identity, "/verify/external-token", {"token": token})
    assert resp.get("ok") is True,      f"ETV-10: expected ok=true: {resp}"
    assert resp.get("valid") is True,   f"ETV-10: expected valid=true: {resp}"
    assert resp.get("expired") is False, f"ETV-10: expected expired=false: {resp}"


# ===========================================================================
# ETV-11..12: Invalid/tampered signatures
# ===========================================================================

def test_etv11_wrong_key_signature(relay_with_identity):
    """ETV-11: Token signed by different key → ok=false, valid=false."""
    priv1, pub1 = _gen_keypair()
    priv2, _    = _gen_keypair()
    subject_hex = pub1.hex()
    # Sign canonical payload with priv2 (wrong key for pub1)
    canonical   = f"{subject_hex}|acp://test/skills/read|invoke|T1_read|0"
    sig_hex     = priv2.sign(canonical.encode()).hex()
    token = {
        "subject":   subject_hex,
        "resource":  "acp://test/skills/read",
        "actions":   ["invoke"],
        "tier":      "T1_read",
        "signature": sig_hex,
    }
    resp, _ = _post(relay_with_identity, "/verify/external-token", {"token": token})
    assert resp.get("ok") is False,    f"ETV-11: expected ok=false for wrong sig: {resp}"
    assert resp.get("valid") is False, f"ETV-11: expected valid=false: {resp}"


def test_etv12_tampered_resource(relay_with_identity):
    """ETV-12: Token with tampered resource after signing → ok=false, valid=false."""
    priv, pub = _gen_keypair()
    token     = _make_token(priv, pub, resource="acp://test/skills/read")
    token["resource"] = "acp://test/skills/admin"   # tamper after signing
    resp, _   = _post(relay_with_identity, "/verify/external-token", {"token": token})
    assert resp.get("ok") is False,    f"ETV-12: expected ok=false for tampered payload: {resp}"
    assert resp.get("valid") is False, f"ETV-12: expected valid=false: {resp}"


# ===========================================================================
# ETV-13..16: Malformed inputs
# ===========================================================================

def test_etv13_missing_token_field(relay_with_identity):
    """ETV-13: Request without 'token' field → error."""
    resp, status = _post(relay_with_identity, "/verify/external-token", {"not_token": {}})
    assert status == 400 or resp.get("ok") is False, \
        f"ETV-13: expected error for missing token field: {resp}"


def test_etv14_missing_required_token_fields(relay_with_identity):
    """ETV-14: Token missing required fields (actions/tier/signature) → ok=false with error msg."""
    incomplete = {"subject": "a" * 64, "resource": "acp://x"}
    resp, _    = _post(relay_with_identity, "/verify/external-token", {"token": incomplete})
    assert resp.get("ok") is False, f"ETV-14: expected ok=false for incomplete token: {resp}"
    assert "missing required fields" in (resp.get("error") or ""), \
        f"ETV-14: error msg wrong: {resp}"


def test_etv15_bad_subject_length(relay_with_identity):
    """ETV-15: Subject not 64 hex chars → ok=false with length error."""
    priv, pub = _gen_keypair()
    token     = _make_token(priv, pub)
    token["subject"] = "deadbeef"   # only 8 chars
    resp, _   = _post(relay_with_identity, "/verify/external-token", {"token": token})
    assert resp.get("ok") is False, f"ETV-15: expected ok=false for short subject: {resp}"


def test_etv16_empty_body(relay_with_identity):
    """ETV-16: Empty request body → 400 or ok=false."""
    resp, status = _post(relay_with_identity, "/verify/external-token", {})
    assert status == 400 or resp.get("ok") is False, \
        f"ETV-16: expected error for empty body: {resp}"
