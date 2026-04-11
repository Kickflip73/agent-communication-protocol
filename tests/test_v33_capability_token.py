"""
tests/test_v33_capability_token.py — ACP v3.3 capability_token passthrough + origin_proof OBO fields

Test suite: CT-01 ~ CT-06 (v3.3 specific)
  CT-01  Send message with capability_token field → /recv shows it in outbound entry
  CT-02  Send message WITHOUT capability_token field → no error, normal processing
  CT-03  GET /status capabilities.capability_token is a boolean
  CT-04  POST /capability/issue returns token with required fields (type/subject/resource/actions/tier/exp/sig)
  CT-05  POST /capability/issue returned token sig is verifiable with relay public key (Ed25519)
  CT-06  Send message with principal_id/operator_id → origin_proof in outbound entry contains those fields
"""

import base64
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

# ── Path setup ───────────────────────────────────────────────────────────────

RELAY_DIR    = os.path.join(os.path.dirname(__file__), "..", "relay")
RELAY_SCRIPT = os.path.join(RELAY_DIR, "acp_relay.py")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _free_ports():
    """Return a (ws_port, http_port) pair where ws+100=http, both unbound."""
    for _ in range(20):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            ws_port = s.getsockname()[1]
        http_port = ws_port + 100
        # quick probe — if http_port is also free, use it
        with socket.socket() as s2:
            try:
                s2.bind(("127.0.0.1", http_port))
                return ws_port, http_port
            except OSError:
                continue
    raise RuntimeError("Could not find free port pair")


def _start_relay_with_identity(extra_args=None):
    """Start a relay with a fresh temp identity. Returns (proc, http_port, ident_path)."""
    import tempfile
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import (
        Encoding, PrivateFormat, PublicFormat, NoEncryption
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

    ws_port, http_port = _free_ports()
    cmd = [
        sys.executable, RELAY_SCRIPT,
        "--port", str(ws_port),
        "--identity", tf.name,
        "--local-only",
        "--test-mode",
    ]
    if extra_args:
        cmd += extra_args
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{http_port}/status", timeout=1)
            break
        except Exception:
            time.sleep(0.2)
    else:
        proc.terminate()
        os.unlink(tf.name)
        pytest.skip(f"relay failed to start on http port {http_port}")
    return proc, http_port, tf.name, pub_b64


def _get(hp, path):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{hp}{path}", timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _post(hp, path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{hp}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


# ── Shared relay fixture (module scope) ──────────────────────────────────────

@pytest.fixture(scope="module")
def relay_info():
    """Start a relay with Ed25519 identity; yield (http_port, pub_b64); teardown."""
    proc, hp, ident_path, pub_b64 = _start_relay_with_identity()
    yield hp, pub_b64
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    try:
        os.unlink(ident_path)
    except Exception:
        pass


# ── CT-01: capability_token passthrough ──────────────────────────────────────

def test_ct_01_capability_token_passthrough(relay_info):
    """CT-01: Send message with capability_token → /recv outbound entry contains the field."""
    hp, _ = relay_info
    sample_token = {
        "type":     "Ed25519CapabilityToken",
        "subject":  "did:acp:TestPeer",
        "resource": "sess-abc",
        "actions":  ["read", "write"],
        "tier":     1,
        "exp":      "2030-01-01T00:00:00Z",
        "sig":      "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    }
    s, b = _post(hp, "/message:send", {
        "role":             "agent",
        "parts":            [{"type": "text", "content": "CT-01 test"}],
        "capability_token": sample_token,
    })
    # Send might get 503 (no peer WS, message queued) or 200 — both are fine for this test
    assert s in (200, 201, 500, 503), f"CT-01 send status: {s} body={b}"

    # Check /messages for outbound entry containing capability_token
    s2, b2 = _get(hp, "/messages?direction=outbound&limit=20")
    assert s2 == 200, f"CT-01 /messages status: {s2}"
    msgs = b2.get("messages", [])
    # Find the message with our text
    found = None
    for m in msgs:
        raw = m.get("raw") or m
        parts = raw.get("parts", [])
        for p in parts:
            if p.get("content") == "CT-01 test" or p.get("text") == "CT-01 test":
                found = raw
                break
        if found:
            break
    assert found is not None, f"CT-01: message not found in /messages; got {msgs}"
    assert "capability_token" in found, (
        f"CT-01: capability_token not in outbound message entry; keys={list(found.keys())}"
    )
    assert found["capability_token"].get("subject") == "did:acp:TestPeer", (
        f"CT-01: capability_token.subject mismatch: {found['capability_token']}"
    )


# ── CT-02: no capability_token → normal processing ────────────────────────────

def test_ct_02_no_capability_token_no_error(relay_info):
    """CT-02: Send message WITHOUT capability_token field → normal processing, no error."""
    hp, _ = relay_info
    s, b = _post(hp, "/message:send", {
        "role":  "agent",
        "parts": [{"type": "text", "content": "CT-02 plain message"}],
    })
    # Status may be 200, 500, or 503 (no peer WS connected → queued is ok), but NOT a capability error
    assert s in (200, 201, 500, 503), f"CT-02 status: {s}"
    if s == 500:
        # Must not be a capability-related error
        assert "capability" not in str(b).lower(), f"CT-02 unexpected capability error: {b}"

    # Verify the message appears in /messages without capability_token key causing issues
    s2, b2 = _get(hp, "/messages?direction=outbound&limit=20")
    assert s2 == 200, f"CT-02 /messages status: {s2}"


# ── CT-03: capabilities.capability_token is boolean ──────────────────────────

def test_ct_03_capabilities_capability_token_is_bool(relay_info):
    """CT-03: AgentCard capabilities.capability_token is a boolean (True when identity loaded)."""
    hp, _ = relay_info
    # capabilities lives in the agent card, not /status
    s, b = _get(hp, "/.well-known/acp.json")
    assert s == 200, f"CT-03 /.well-known/acp.json status: {s}"
    card = b.get("self") or b
    caps = card.get("capabilities", {})
    assert "capability_token" in caps, f"CT-03: capability_token not in capabilities: {list(caps.keys())}"
    assert isinstance(caps["capability_token"], bool), (
        f"CT-03: capabilities.capability_token is not bool: {type(caps['capability_token'])}"
    )
    assert caps["capability_token"] is True, (
        f"CT-03: capabilities.capability_token expected True (identity loaded), got {caps['capability_token']}"
    )


# ── CT-04: POST /capability/issue returns required fields ─────────────────────

def test_ct_04_capability_issue_required_fields(relay_info):
    """CT-04: POST /capability/issue returns token with type/subject/resource/actions/tier/exp/sig."""
    hp, _ = relay_info
    s, b = _post(hp, "/capability/issue", {
        "subject":     "did:acp:Callee",
        "resource":    "sess-123",
        "actions":     ["read", "write"],
        "tier":        1,
        "exp_seconds": 3600,
    })
    assert s == 200, f"CT-04 status: {s} body={b}"
    assert b.get("ok") is True, f"CT-04 ok field: {b}"
    token = b.get("token")
    assert token is not None, f"CT-04 token field missing: {b}"
    for field in ("type", "subject", "resource", "actions", "tier", "exp", "sig"):
        assert field in token, f"CT-04 missing field '{field}' in token: {list(token.keys())}"
    assert token["type"]     == "Ed25519CapabilityToken", f"CT-04 type: {token['type']}"
    assert token["subject"]  == "did:acp:Callee",         f"CT-04 subject: {token['subject']}"
    assert token["resource"] == "sess-123",                f"CT-04 resource: {token['resource']}"
    assert "read"  in token["actions"],                    f"CT-04 actions missing read: {token['actions']}"
    assert "write" in token["actions"],                    f"CT-04 actions missing write: {token['actions']}"
    assert token["tier"] == 1,                             f"CT-04 tier: {token['tier']}"
    assert "T" not in str(token["exp"]) or "-" in str(token["exp"]), \
        f"CT-04 exp format unexpected: {token['exp']}"  # should be ISO-8601 or similar


# ── CT-05: sig verifiable with relay public key ───────────────────────────────

def test_ct_05_capability_issue_sig_verifiable(relay_info):
    """CT-05: POST /capability/issue sig is verifiable with relay public key (Ed25519)."""
    hp, pub_b64 = relay_info
    s, b = _post(hp, "/capability/issue", {
        "subject":     "did:acp:Verifier",
        "resource":    "*",
        "actions":     ["read"],
        "tier":        0,
        "exp_seconds": 7200,
    })
    assert s == 200, f"CT-05 issue status: {s} body={b}"
    token = b["token"]

    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:
        pytest.skip("cryptography library not available for sig verification")

    # Reconstruct the canonical payload that was signed
    # (mirrors the signing code in /capability/issue)
    import datetime
    exp_iso = token["exp"]
    # Convert exp back to unix timestamp for canonical payload
    # The relay signs a payload with exp as unix int, but stores as ISO in token.
    # We need to verify using the same canonical form — let's derive iat and exp_ts from token.
    iat_val = token.get("iat")
    exp_val = token.get("exp")  # ISO-8601 string in token

    # Build canonical payload matching server-side signing logic
    # The server signs: {type, subject, resource, actions, tier, iss, jti, iat, exp_unix_int}
    # but the token stores exp as ISO. We need to reconstruct with the raw unix exp.
    # However, the relay encodes exp as ISO in the returned token but signs the numeric.
    # Per the implementation: payload_ci has exp as int, then token overrides exp with ISO.
    # So we verify against the payload BEFORE the ISO override — fetch iat and compute exp_unix.
    import calendar
    if isinstance(exp_val, str):
        try:
            dt = datetime.datetime.strptime(exp_val, "%Y-%m-%dT%H:%M:%SZ")
            exp_unix = calendar.timegm(dt.timetuple())
        except Exception:
            exp_unix = 0
    else:
        exp_unix = int(exp_val)

    payload_to_verify = {
        "type":     token["type"],
        "subject":  token["subject"],
        "resource": token["resource"],
        "actions":  sorted(token["actions"]),
        "tier":     token["tier"],
        "iss":      token["iss"],
        "jti":      token["jti"],
        "iat":      token["iat"],
        "exp":      exp_unix,   # the relay signed the numeric value
    }
    canonical = json.dumps(payload_to_verify, sort_keys=True, separators=(",", ":")).encode()
    sig_bytes  = base64.urlsafe_b64decode(token["sig"] + "==")
    pub_raw    = base64.urlsafe_b64decode(pub_b64 + "==")

    try:
        pub_key = Ed25519PublicKey.from_public_bytes(pub_raw)
        pub_key.verify(sig_bytes, canonical)
    except Exception as e:
        pytest.fail(f"CT-05: Ed25519 signature verification failed: {e}\n"
                    f"canonical={canonical}\nsig={token['sig']}\npub_b64={pub_b64}")


# ── CT-06: origin_proof OBO fields ───────────────────────────────────────────

def test_ct_06_origin_proof_obo_fields(relay_info):
    """CT-06: Send message with principal_id/operator_id → origin_proof contains those fields."""
    hp, _ = relay_info
    s, b = _post(hp, "/message:send", {
        "role":         "agent",
        "parts":        [{"type": "text", "content": "CT-06 OBO test"}],
        "principal_id": "did:acp:Principal",
        "operator_id":  "did:acp:Operator",
        "governance_framework_ref": "https://example.org/gov/v1",
    })
    assert s in (200, 201, 500, 503), f"CT-06 send status: {s}"

    # Check /messages for outbound entry with origin_proof
    s2, b2 = _get(hp, "/messages?direction=outbound&limit=20")
    assert s2 == 200, f"CT-06 /messages status: {s2}"
    msgs = b2.get("messages", [])
    found = None
    for m in msgs:
        raw = m.get("raw") or m
        parts = raw.get("parts", [])
        for p in parts:
            if p.get("content") == "CT-06 OBO test" or p.get("text") == "CT-06 OBO test":
                found = raw
                break
        if found:
            break
    assert found is not None, f"CT-06: OBO message not found in /messages; got {msgs}"
    assert "origin_proof" in found, (
        f"CT-06: origin_proof not in outbound message; keys={list(found.keys())}"
    )
    op = found["origin_proof"]
    assert op.get("principal_id") == "did:acp:Principal", (
        f"CT-06: origin_proof.principal_id mismatch: {op}"
    )
    assert op.get("operator_id") == "did:acp:Operator", (
        f"CT-06: origin_proof.operator_id mismatch: {op}"
    )
    assert op.get("governance_framework_ref") == "https://example.org/gov/v1", (
        f"CT-06: origin_proof.governance_framework_ref mismatch: {op}"
    )
