"""
test_caller_signature.py — CS-1..12: ACP v2.61 caller_signature bilateral signing

Tests:
  CS-1:  POST /tasks record=true WITHOUT caller_signature → bilateral=false, caller_signature=null, caller_signature_valid=null
  CS-2:  POST /tasks record=true WITH invalid caller_signature (bad bytes) → bilateral=false, caller_signature_valid=false
  CS-3:  POST /tasks record=true WITH caller_signature but no caller_public_key → bilateral=false, caller_signature_valid=false
  CS-4:  POST /tasks record=true WITH caller_public_key but no caller_signature → bilateral=false, caller_signature_valid=false
  CS-5:  AgentCard capabilities.bilateral_interaction_records = true
  CS-6:  GET /interaction-records returns bilateral field on each record
  CS-7:  relay-only record (no caller_signature) → bilateral=false
  CS-8:  record stores caller_signature and caller_public_key even when verification fails
  CS-9:  invalid caller_signature is stored (not rejected) and appears in GET /interaction-records
  CS-10: canonical fields always present in IR regardless of bilateral flag
  CS-11: multiple records maintain proper previous_hash chain
  CS-12: caller_signature_valid is None (not False) when no caller_signature provided
"""
import base64
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

_RELAY = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")
_BASE_WS_PORT = 48900  # CS tests: 48900-48999


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _start_relay(ws_port: int, identity_file: str = None) -> tuple:
    """Start relay in test mode. HTTP port = ws_port + 100."""
    http_port = ws_port + 100
    cmd = [sys.executable, _RELAY, "--port", str(ws_port), "--name", "CSTestAgent",
           "--local-only", "--test-mode"]
    if identity_file:
        cmd += ["--identity", identity_file]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{http_port}/status", timeout=1) as r:
                if r.status == 200:
                    return proc, http_port
        except Exception:
            time.sleep(0.15)
    proc.terminate()
    raise RuntimeError(f"Relay failed to start on HTTP port {http_port}")


def _get(hp: int, path: str) -> tuple:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{hp}{path}", timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _post(hp: int, path: str, body: dict) -> tuple:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{hp}{path}",
        data=data, headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _post_task(hp: int, skill_id: str = "summarize", record: bool = True,
               caller_signature: str = None, caller_public_key: str = None,
               caller_did: str = None) -> dict:
    body: dict = {"skill_id": skill_id, "payload": {"text": "hello"}, "role": "agent", "record": record}
    if caller_did:
        body["caller_did"] = caller_did
    if caller_signature is not None:
        body["caller_signature"] = caller_signature
    if caller_public_key is not None:
        body["caller_public_key"] = caller_public_key
    status, data = _post(hp, "/tasks", body)
    assert status == 201, f"POST /tasks failed: {status} {data}"
    return data


# ── CS-1 ─────────────────────────────────────────────────────────────────────
def test_cs1_no_caller_sig_bilateral_false():
    """No caller_signature → bilateral=false, caller_signature=null, caller_signature_valid=null."""
    proc, hp = _start_relay(_BASE_WS_PORT + 0)
    try:
        data = _post_task(hp, record=True)
        ir = data["interaction_record"]
        assert ir["bilateral"] is False, f"expected bilateral=false, got {ir['bilateral']}"
        assert ir["caller_signature"] is None
        assert ir["caller_signature_valid"] is None
    finally:
        proc.terminate(); proc.wait(timeout=4)


# ── CS-2 ─────────────────────────────────────────────────────────────────────
def test_cs2_invalid_caller_sig_bad_bytes():
    """Invalid caller_signature (64 zero-bytes) → caller_signature_valid=false, bilateral=false."""
    if not HAS_CRYPTO:
        import pytest; pytest.skip("cryptography not installed")
    proc, hp = _start_relay(_BASE_WS_PORT + 2)
    try:
        priv = Ed25519PrivateKey.generate()
        pub_b64 = _b64url_encode(priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
        bad_sig = _b64url_encode(b"\x00" * 64)
        data = _post_task(hp, record=True, caller_signature=bad_sig, caller_public_key=pub_b64)
        ir = data["interaction_record"]
        assert ir["caller_signature_valid"] is False
        assert ir["bilateral"] is False
        assert ir["caller_signature"] == bad_sig
    finally:
        proc.terminate(); proc.wait(timeout=4)


# ── CS-3 ─────────────────────────────────────────────────────────────────────
def test_cs3_sig_without_pubkey():
    """caller_signature without caller_public_key → caller_signature_valid=false."""
    proc, hp = _start_relay(_BASE_WS_PORT + 4)
    try:
        sig = _b64url_encode(b"\xab" * 64)
        data = _post_task(hp, record=True, caller_signature=sig)
        ir = data["interaction_record"]
        assert ir["caller_signature_valid"] is False
        assert ir["bilateral"] is False
    finally:
        proc.terminate(); proc.wait(timeout=4)


# ── CS-4 ─────────────────────────────────────────────────────────────────────
def test_cs4_pubkey_without_sig():
    """caller_public_key without caller_signature → caller_signature_valid=false."""
    if not HAS_CRYPTO:
        import pytest; pytest.skip("cryptography not installed")
    proc, hp = _start_relay(_BASE_WS_PORT + 6)
    try:
        priv = Ed25519PrivateKey.generate()
        pub_b64 = _b64url_encode(priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
        data = _post_task(hp, record=True, caller_public_key=pub_b64)
        ir = data["interaction_record"]
        assert ir["caller_signature_valid"] is False
        assert ir["bilateral"] is False
    finally:
        proc.terminate(); proc.wait(timeout=4)


# ── CS-5 ─────────────────────────────────────────────────────────────────────
def test_cs5_agentcard_bilateral_capability():
    """AgentCard.capabilities.bilateral_interaction_records = true."""
    proc, hp = _start_relay(_BASE_WS_PORT + 8)
    try:
        status, body = _get(hp, "/.well-known/acp.json")
        assert status == 200
        card = body.get("self") or body
        caps = card.get("capabilities", {})
        assert caps.get("bilateral_interaction_records") is True, (
            f"bilateral_interaction_records not true in capabilities: {caps}"
        )
    finally:
        proc.terminate(); proc.wait(timeout=4)


# ── CS-6 ─────────────────────────────────────────────────────────────────────
def test_cs6_get_interaction_records_has_bilateral_field():
    """GET /interaction-records returns bilateral field on each record."""
    proc, hp = _start_relay(_BASE_WS_PORT + 10)
    try:
        _post_task(hp, record=True)
        status, data = _get(hp, "/interaction-records")
        assert status == 200
        assert data["ok"] is True
        assert len(data["records"]) >= 1
        for rec in data["records"]:
            assert "bilateral" in rec, f"Record missing 'bilateral': {list(rec.keys())}"
    finally:
        proc.terminate(); proc.wait(timeout=4)


# ── CS-7 ─────────────────────────────────────────────────────────────────────
def test_cs7_relay_only_record_bilateral_false():
    """Record without caller_signature has bilateral=false."""
    proc, hp = _start_relay(_BASE_WS_PORT + 12)
    try:
        data = _post_task(hp, record=True)
        ir = data["interaction_record"]
        assert ir["bilateral"] is False
    finally:
        proc.terminate(); proc.wait(timeout=4)


# ── CS-8 ─────────────────────────────────────────────────────────────────────
def test_cs8_record_stores_caller_sig_and_pubkey():
    """Both caller_signature and caller_public_key are stored in the record."""
    if not HAS_CRYPTO:
        import pytest; pytest.skip("cryptography not installed")
    proc, hp = _start_relay(_BASE_WS_PORT + 14)
    try:
        priv = Ed25519PrivateKey.generate()
        pub_b64 = _b64url_encode(priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
        bad_sig = _b64url_encode(b"\xff" * 64)
        data = _post_task(hp, record=True, caller_signature=bad_sig, caller_public_key=pub_b64)
        ir = data["interaction_record"]
        assert ir["caller_signature"] == bad_sig
        assert ir["caller_public_key"] == pub_b64
        assert "relay_signature" in ir
    finally:
        proc.terminate(); proc.wait(timeout=4)


# ── CS-9 ─────────────────────────────────────────────────────────────────────
def test_cs9_invalid_sig_stored_and_in_list():
    """Invalid caller_signature is stored (not rejected) and appears in GET /interaction-records."""
    if not HAS_CRYPTO:
        import pytest; pytest.skip("cryptography not installed")
    proc, hp = _start_relay(_BASE_WS_PORT + 16)
    try:
        priv = Ed25519PrivateKey.generate()
        pub_b64 = _b64url_encode(priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
        bad_sig = _b64url_encode(b"\xcc" * 64)
        data = _post_task(hp, record=True, caller_signature=bad_sig, caller_public_key=pub_b64)
        ir = data["interaction_record"]
        assert "id" in ir
        assert ir["caller_signature_valid"] is False
        _, list_data = _get(hp, "/interaction-records")
        ids = [rec["id"] for rec in list_data["records"]]
        assert ir["id"] in ids
    finally:
        proc.terminate(); proc.wait(timeout=4)


# ── CS-10 ────────────────────────────────────────────────────────────────────
def test_cs10_canonical_fields_always_present():
    """Canonical payload fields always present in IR regardless of bilateral flag."""
    proc, hp = _start_relay(_BASE_WS_PORT + 18)
    try:
        data = _post_task(hp, record=True)
        ir = data["interaction_record"]
        required = ["id", "type", "relay_did", "caller_did", "task_id", "skill_id",
                    "sequence_a", "previous_hash", "timestamp"]
        for field in required:
            assert field in ir, f"Missing canonical field: {field}"
        # v2.61 fields also always present
        for field in ["bilateral", "caller_signature_valid", "caller_signature", "caller_public_key"]:
            assert field in ir, f"Missing v2.61 field: {field}"
    finally:
        proc.terminate(); proc.wait(timeout=4)


# ── CS-11 ────────────────────────────────────────────────────────────────────
def test_cs11_chain_linkage_maintained():
    """Multiple records maintain proper previous_hash chain linkage."""
    proc, hp = _start_relay(_BASE_WS_PORT + 20)
    try:
        for _ in range(3):
            _post_task(hp, record=True)
        _, data = _get(hp, "/interaction-records?limit=10")
        recs = data["records"]
        assert len(recs) >= 3
        assert recs[0]["previous_hash"] == "genesis"
        for i in range(1, len(recs)):
            prev_bytes = json.dumps(recs[i-1], sort_keys=True, separators=(",", ":")).encode()
            expected = "sha256:" + hashlib.sha256(prev_bytes).hexdigest()
            assert recs[i]["previous_hash"] == expected, (
                f"Record {i} previous_hash mismatch"
            )
    finally:
        proc.terminate(); proc.wait(timeout=4)


# ── CS-12 ────────────────────────────────────────────────────────────────────
def test_cs12_caller_signature_valid_none_when_absent():
    """caller_signature_valid is None (not False) when no caller_signature provided."""
    proc, hp = _start_relay(_BASE_WS_PORT + 22)
    try:
        data = _post_task(hp, record=True)
        ir = data["interaction_record"]
        assert ir["caller_signature_valid"] is None, (
            f"expected None, got {ir['caller_signature_valid']!r}"
        )
        assert ir["caller_signature"] is None
        assert ir["caller_public_key"] is None
    finally:
        proc.terminate(); proc.wait(timeout=4)
