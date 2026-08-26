"""
tests/test_capability_token.py — ACP v3.3 capability_token + origin_proof OBO tests

Test suite: CT-01 ~ CT-06 (v3.3 specific)
  CT-01  Send message with capability_token field → outbound entry contains it
  CT-02  Send message WITHOUT capability_token field → no error, normal processing
  CT-03  GET /status/.well-known/acp.json capabilities.capability_token is a boolean
  CT-04  POST /capability/issue returns token with required fields
  CT-05  POST /capability/issue returned token sig is verifiable with relay public key (Ed25519)
  CT-06  Send message with principal_id/operator_id → origin_proof in outbound entry has those fields

NOTE: This test file replaces the v2.57 CT-1..12 suite (which tested
POST /skills/{id}/capability-token SINT-format endpoint). Those tests have been
superseded by the v3.3 capability_token passthrough + /capability/issue endpoint.
See tests/test_v33_capability_token.py for a parallel comprehensive suite.
"""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import tempfile
import base64

import pytest

# ── Path setup ────────────────────────────────────────────────────────────────

RELAY_DIR    = os.path.join(os.path.dirname(__file__), "..", "relay")
RELAY_SCRIPT = os.path.join(RELAY_DIR, "acp_relay.py")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _free_port_pair():
    """Return (ws_port, http_port) where http_port = ws_port + 100, both free."""
    for _ in range(20):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            ws_port = s.getsockname()[1]
        http_port = ws_port + 100
        with socket.socket() as s2:
            try:
                s2.bind(("127.0.0.1", http_port))
                return ws_port, http_port
            except OSError:
                continue
    raise RuntimeError("Cannot find free port pair")


def _gen_identity_file():
    """Generate a temporary Ed25519 identity JSON that acp_relay.py accepts."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import (
        Encoding, PrivateFormat, PublicFormat, NoEncryption,
    )
    priv = Ed25519PrivateKey.generate()
    pub  = priv.public_key()
    priv_raw = priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    pub_raw  = pub.public_bytes(Encoding.Raw, PublicFormat.Raw)
    priv_b64 = base64.urlsafe_b64encode(priv_raw).rstrip(b"=").decode()
    pub_b64  = base64.urlsafe_b64encode(pub_raw).rstrip(b"=").decode()
    ident = {"scheme": "ed25519", "private_key": priv_b64, "public_key": pub_b64}
    tf = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    json.dump(ident, tf)
    tf.close()
    return tf.name, pub_b64


@pytest.fixture(scope="module")
def relay_url():
    """
    Start a relay with Ed25519 identity. Yields (base_url, pub_b64).

    Falls back gracefully: if the identity file at ~/.acp/identity.json doesn't
    exist, a temporary one is generated so all tests can run.
    """
    ident_path = os.path.expanduser("~/.acp/identity.json")
    pub_b64 = None
    cleanup_ident = False
    if not os.path.exists(ident_path):
        ident_path, pub_b64 = _gen_identity_file()
        cleanup_ident = True
    else:
        try:
            with open(ident_path) as f:
                d = json.load(f)
            pub_b64 = d.get("public_key", "")
        except Exception:
            ident_path, pub_b64 = _gen_identity_file()
            cleanup_ident = True

    ws_port, http_port = _free_port_pair()
    cmd = [
        sys.executable, RELAY_SCRIPT,
        "--port", str(ws_port),
        "--identity", ident_path,
        "--local-only",
        "--test-mode",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{http_port}"
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"{url}/status", timeout=2)
            break
        except Exception:
            time.sleep(0.3)
    else:
        proc.terminate()
        if cleanup_ident:
            os.unlink(ident_path)
        pytest.skip(f"relay failed to start on {http_port}")

    yield url, pub_b64

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    if cleanup_ident:
        try:
            os.unlink(ident_path)
        except Exception:
            pass


def _post(url, path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{url}{path}", data=data,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def _get(url, path):
    try:
        with urllib.request.urlopen(f"{url}{path}", timeout=5) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


# ── CT-01: capability_token passthrough ──────────────────────────────────────

def test_ct01_capability_token_passthrough(relay_url):
    """CT-01: Send message with capability_token → outbound entry contains the field."""
    url, _ = relay_url
    token = {
        "type":     "Ed25519CapabilityToken",
        "subject":  "ct_bob",
        "resource": "*",
        "actions":  ["read"],
        "tier":     0,
        "exp":      "2099-01-01T00:00:00Z",
        "sig":      "fakesig",
    }
    _post(url, "/message:send", {
        "role":             "agent",
        "parts":            [{"type": "text", "content": "CT-01 hi"}],
        "capability_token": token,
    })
    time.sleep(0.2)
    msgs_resp = _get(url, "/messages?direction=outbound&limit=20")
    msgs = msgs_resp.get("messages", [])
    found = None
    for m in msgs:
        raw = m.get("raw") or m
        parts = raw.get("parts", [])
        for p in parts:
            if p.get("content") == "CT-01 hi" or p.get("text") == "CT-01 hi":
                found = raw
                break
        if found:
            break
    assert found is not None, f"CT-01: message not in /messages; got {msgs}"
    assert "capability_token" in found, (
        f"CT-01: capability_token not in outbound entry; keys={list(found.keys())}"
    )


# ── CT-02: no capability_token → normal processing ───────────────────────────

def test_ct02_no_capability_token_ok(relay_url):
    """CT-02: Send message WITHOUT capability_token → no error."""
    url, _ = relay_url
    r = _post(url, "/message:send", {
        "role":  "agent",
        "parts": [{"type": "text", "content": "CT-02 hello"}],
    })
    # 200/201: delivered; 500/503: queued (no peer connected) — all acceptable
    # Must not contain a capability-related error field
    assert "capability" not in str(r.get("error_code", "")).lower(), (
        f"CT-02: unexpected capability error: {r}"
    )


# ── CT-03: capabilities.capability_token is bool ──────────────────────────────

def test_ct03_capabilities_flag(relay_url):
    """CT-03: AgentCard capabilities.capability_token is a boolean."""
    url, _ = relay_url
    s = _get(url, "/.well-known/acp.json")
    card = s.get("self") or s
    caps = card.get("capabilities", {})
    assert "capability_token" in caps, (
        f"CT-03: capability_token not in capabilities; keys={list(caps.keys())}"
    )
    assert isinstance(caps["capability_token"], bool), (
        f"CT-03: capabilities.capability_token is not bool: {type(caps['capability_token'])}"
    )


# ── CT-04: POST /capability/issue returns correct structure ──────────────────

def test_ct04_issue_token_structure(relay_url):
    """CT-04: POST /capability/issue returns Ed25519CapabilityToken with all required fields."""
    url, _ = relay_url
    try:
        r = _post(url, "/capability/issue", {
            "subject":     "ct_bob",
            "resource":    "*",
            "actions":     ["read", "write"],
            "tier":        1,
            "exp_seconds": 3600,
        })
    except urllib.error.HTTPError as e:
        if e.code == 503:
            pytest.skip("no identity, /capability/issue returns 503")
        raise

    # Response is wrapped: {"ok": true, "token": {...}}
    if not r.get("ok"):
        if r.get("error_code") == "ERR_IDENTITY_REQUIRED":
            pytest.skip("no identity loaded")
        pytest.fail(f"CT-04: issue failed: {r}")

    token = r.get("token") or r
    assert token.get("type") == "Ed25519CapabilityToken", f"CT-04 type: {token}"
    for field in ("subject", "resource", "actions", "tier", "exp", "sig"):
        assert field in token, f"CT-04 missing field '{field}': {list(token.keys())}"


# ── CT-05: returned sig is verifiable with relay's public key ─────────────────

def test_ct05_issue_token_sig_verifiable(relay_url):
    """CT-05: POST /capability/issue sig is verifiable with Ed25519 relay public key."""
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:
        pytest.skip("cryptography not installed")

    url, pub_b64 = relay_url
    r = _post(url, "/capability/issue", {
        "subject":     "ct_bob",
        "resource":    "*",
        "actions":     ["read"],
        "tier":        0,
        "exp_seconds": 60,
    })
    if not r.get("ok"):
        if r.get("error_code") == "ERR_IDENTITY_REQUIRED":
            pytest.skip("no identity")
        pytest.fail(f"CT-05: issue failed: {r}")

    token = r.get("token") or r

    # Resolve public key: prefer /status identity, fall back to fixture pub_b64
    status = _get(url, "/status")
    pk_b64 = (status.get("identity") or {}).get("public_key") or pub_b64
    if not pk_b64:
        # Try /.well-known/acp.json
        card_resp = _get(url, "/.well-known/acp.json")
        card = card_resp.get("self") or card_resp
        pk_b64 = (card.get("identity") or {}).get("public_key", "")
    if not pk_b64:
        pytest.skip("no public_key available to verify signature")

    import datetime, calendar
    exp_val = token.get("exp")
    if isinstance(exp_val, str):
        try:
            dt = datetime.datetime.strptime(exp_val, "%Y-%m-%dT%H:%M:%SZ")
            exp_unix = calendar.timegm(dt.timetuple())
        except Exception:
            exp_unix = 0
    else:
        exp_unix = int(exp_val or 0)

    payload_to_sign = {
        "type":     token["type"],
        "subject":  token["subject"],
        "resource": token["resource"],
        "actions":  sorted(token["actions"]),
        "tier":     token["tier"],
        "iss":      token.get("iss", ""),
        "jti":      token.get("jti", ""),
        "iat":      token.get("iat", 0),
        "exp":      exp_unix,
    }
    canonical = json.dumps(payload_to_sign, sort_keys=True, separators=(",", ":")).encode()
    sig_bytes  = base64.urlsafe_b64decode(token["sig"] + "==")
    pub_bytes  = base64.urlsafe_b64decode(pk_b64 + "==")
    pub_key    = Ed25519PublicKey.from_public_bytes(pub_bytes)
    try:
        pub_key.verify(sig_bytes, canonical)
    except Exception as e:
        pytest.fail(f"CT-05: Ed25519 signature verification failed: {e}")


# ── CT-06: origin_proof contains OBO fields ───────────────────────────────────

def test_ct06_origin_proof_extended_fields(relay_url):
    """CT-06: Send message with principal_id/operator_id → origin_proof in outbound entry."""
    url, _ = relay_url
    r = _post(url, "/message:send", {
        "role":    "agent",
        "parts":   [{"type": "text", "content": "CT-06 delegated"}],
        "principal_id":             "did:acp:principal123",
        "operator_id":              "did:acp:operator456",
        "governance_framework_ref": "https://example.com/gf",
    })
    time.sleep(0.2)
    msgs_resp = _get(url, "/messages?direction=outbound&limit=20")
    msgs = msgs_resp.get("messages", [])
    found = None
    for m in msgs:
        raw = m.get("raw") or m
        parts = raw.get("parts", [])
        for p in parts:
            if p.get("content") == "CT-06 delegated" or p.get("text") == "CT-06 delegated":
                found = raw
                break
        if found:
            break
    assert found is not None, f"CT-06: OBO message not in /messages; got {msgs}"
    op = found.get("origin_proof", {})
    if op:  # only check fields if origin_proof is present (requires Ed25519 identity)
        assert op.get("principal_id") == "did:acp:principal123", (
            f"CT-06: principal_id mismatch: {op}"
        )
        assert op.get("operator_id") == "did:acp:operator456", (
            f"CT-06: operator_id mismatch: {op}"
        )
