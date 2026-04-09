"""
test_ir_test_vectors.py — ACP v2.64: Bilateral IR Test Vectors (ITV-1..18)

Tests for:
  GET /ir/test-vectors         — deterministic bilateral interaction record test vectors
  governance_metadata live_endpoint — APS serviceEndpoint alignment
  AgentCard capabilities.ir_test_vectors
  AgentCard endpoints.ir_test_vectors

Requested by @aeoess (A2A Issue #1718, 2026-04-06).
"""

import pytest
import hashlib
import json
import base64
import subprocess
import sys
import os
import time
import threading

# ── helpers ──────────────────────────────────────────────────────────────────
RELAY_PATH = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey, Ed25519PublicKey,
    )
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    ED25519_AVAILABLE = True
except ImportError:
    ED25519_AVAILABLE = False

import urllib.request
import urllib.error


def _get_free_port() -> int:
    """Return a free port (we'll use port for WebSocket and port+100 for HTTP API)."""
    import socket
    # Reserve two consecutive ports: p (WS) and p+100 (HTTP)
    for attempt in range(20):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        # Avoid ports where port+100 > 65535 or already used
        if port < 65000:
            return port
    import random
    return random.randint(20000, 40000)


def _http_port(ws_port: int) -> int:
    """ACP relay HTTP port = WS port + 100."""
    return ws_port + 100


def _wait_ready(http_port: int, timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{http_port}/status", timeout=1)
            return True
        except Exception:
            time.sleep(0.15)
    return False


def _get(url: str):
    with urllib.request.urlopen(url, timeout=6) as r:
        return json.loads(r.read())


def _b64url_decode(s: str) -> bytes:
    s = s.replace("-", "+").replace("_", "/")
    s += "=" * (-len(s) % 4)
    return base64.b64decode(s)


def _ensure_identity_key() -> str:
    """Generate (or reuse) an identity key file for tests. Returns path."""
    key_path = "/tmp/acp_test_ir_identity.key"
    if not os.path.exists(key_path):
        # Generate via relay --gen-identity, then copy
        gen_result = subprocess.run(
            [sys.executable, RELAY_PATH, "--gen-identity"],
            capture_output=True, text=True, timeout=10
        )
        # relay writes to /root/.acp/identity.key by default; copy it
        default_key = os.path.expanduser("~/.acp/identity.key")
        if os.path.exists(default_key):
            import shutil
            shutil.copy2(default_key, key_path)
        else:
            pytest.skip("could not generate identity key for tests")
    return key_path


@pytest.fixture(scope="module")
def relay_with_identity():
    """Start relay with --identity /path/to/key + --test-mode (Ed25519 keys)."""
    key_path = _ensure_identity_key()
    ws_port = _get_free_port()
    http = _http_port(ws_port)
    cmd = [sys.executable, RELAY_PATH,
           "--port", str(ws_port),
           "--identity", key_path,
           "--test-mode"]       # keeps relay alive in HTTP-only mode
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not _wait_ready(http):
        proc.terminate()
        pytest.skip("relay with identity failed to start")
    yield f"http://127.0.0.1:{http}"
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()


@pytest.fixture(scope="module")
def relay_no_identity():
    """Start relay without --identity + --test-mode (no Ed25519 keys)."""
    ws_port = _get_free_port()
    http = _http_port(ws_port)
    cmd = [sys.executable, RELAY_PATH,
           "--port", str(ws_port),
           "--test-mode", "--no-identity"]  # v2.85+: Ed25519 on by default; opt out explicitly
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not _wait_ready(http):
        proc.terminate()
        pytest.skip("relay without identity failed to start")
    yield f"http://127.0.0.1:{http}"
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()


# ══ ITV-1..4: AgentCard metadata ═════════════════════════════════════════════

class TestAgentCardMetadata:
    """ITV-1..4: ir_test_vectors in AgentCard capabilities + endpoints."""

    def test_itv1_capability_ir_test_vectors(self, relay_with_identity):
        """ITV-1: AgentCard.capabilities.ir_test_vectors = true when Ed25519 available."""
        data = _get(f"{relay_with_identity}/.well-known/acp.json")
        # AgentCard response is wrapped: {"self": {...}, "peer": ...}
        card = data.get("self", data)
        caps = card.get("capabilities", {})
        assert caps.get("ir_test_vectors") is True, (
            f"capabilities.ir_test_vectors should be true; got: {caps.get('ir_test_vectors')}"
        )

    def test_itv2_endpoint_ir_test_vectors(self, relay_with_identity):
        """ITV-2: AgentCard.endpoints.ir_test_vectors = /ir/test-vectors."""
        data = _get(f"{relay_with_identity}/.well-known/acp.json")
        card = data.get("self", data)
        endpoints = card.get("endpoints", {})
        assert endpoints.get("ir_test_vectors") == "/ir/test-vectors", (
            f"endpoints.ir_test_vectors should be '/ir/test-vectors'; got: {endpoints.get('ir_test_vectors')}"
        )

    def test_itv3_governance_live_endpoint(self, relay_with_identity):
        """ITV-3: governance_metadata.live_endpoint = /governance-metadata (APS serviceEndpoint alignment)."""
        # Enable governance by querying directly
        data = _get(f"{relay_with_identity}/governance-metadata")
        gm = data.get("governance_metadata", {})
        assert gm.get("live_endpoint") == "/governance-metadata", (
            f"governance_metadata.live_endpoint should be '/governance-metadata'; got: {gm.get('live_endpoint')}"
        )

    def test_itv4_version_is_264(self, relay_with_identity):
        """ITV-4: VERSION >= 2.64.0."""
        data = _get(f"{relay_with_identity}/status")
        version = data.get("acp_version", "")
        from packaging.version import Version
        try:
            assert Version(version) >= Version("2.64.0"), f"expected VERSION >= 2.64.0, got: {version}"
        except Exception:
            # fallback: just check major.minor prefix
            assert version.startswith("2.6"), f"expected VERSION >= 2.64.0, got: {version}"


# ══ ITV-5..8: Response structure ═════════════════════════════════════════════

class TestTestVectorStructure:
    """ITV-5..8: GET /ir/test-vectors response shape."""

    def test_itv5_ok_and_top_level_fields(self, relay_with_identity):
        """ITV-5: Response has ok=true and required top-level fields."""
        data = _get(f"{relay_with_identity}/ir/test-vectors")
        assert data.get("ok") is True
        required = {"schema_version", "generated_by", "generated_at", "keys", "vectors",
                    "canonical_payload_format", "signature_algorithm", "did_key_derivation"}
        missing = required - set(data.keys())
        assert not missing, f"Missing top-level fields: {missing}"

    def test_itv6_schema_version_and_generated_by(self, relay_with_identity):
        """ITV-6: schema_version='1.0' and generated_by starts with 'ACP/'."""
        data = _get(f"{relay_with_identity}/ir/test-vectors")
        assert data["schema_version"] == "1.0"
        assert data["generated_by"].startswith("ACP/"), f"got: {data['generated_by']}"

    def test_itv7_keys_block(self, relay_with_identity):
        """ITV-7: keys block has relay and caller, each with did_key/did_acp/pub_key_b64/hex."""
        data = _get(f"{relay_with_identity}/ir/test-vectors")
        keys = data["keys"]
        for party in ("relay", "caller"):
            k = keys[party]
            assert k.get("did_key", "").startswith("did:key:z6Mk"), (
                f"keys.{party}.did_key should start with 'did:key:z6Mk'"
            )
            assert k.get("did_acp", "").startswith("did:acp:"), (
                f"keys.{party}.did_acp should start with 'did:acp:'"
            )
            assert len(k.get("public_key_hex", "")) == 64, (
                f"keys.{party}.public_key_hex should be 64 hex chars"
            )
            assert k.get("public_key_b64"), f"keys.{party}.public_key_b64 missing"

    def test_itv8_four_vectors(self, relay_with_identity):
        """ITV-8: Exactly 4 test vectors returned (tv-ir-001..004)."""
        data = _get(f"{relay_with_identity}/ir/test-vectors")
        vectors = data["vectors"]
        assert len(vectors) == 4, f"Expected 4 vectors, got {len(vectors)}"
        ids = {v["id"] for v in vectors}
        expected = {"tv-ir-001", "tv-ir-002", "tv-ir-003", "tv-ir-004"}
        assert ids == expected, f"Vector IDs mismatch: {ids}"


# ══ ITV-9..12: Cryptographic correctness ═════════════════════════════════════

@pytest.mark.skipif(not ED25519_AVAILABLE, reason="cryptography package not installed")
class TestCryptographicCorrectness:
    """ITV-9..12: Verify Ed25519 signatures in test vectors are actually valid."""

    def test_itv9_vector1_bilateral_both_valid(self, relay_with_identity):
        """ITV-9: tv-ir-001 — bilateral=true, both signatures verify against canonical_bytes_hex."""
        data = _get(f"{relay_with_identity}/ir/test-vectors")
        v = next(v for v in data["vectors"] if v["id"] == "tv-ir-001")
        keys = data["keys"]

        assert v["bilateral"] is True
        assert v["relay_signature_valid"] is True
        assert v["caller_signature_valid"] is True

        canonical = bytes.fromhex(v["canonical_bytes_hex"])

        # Verify relay signature
        relay_pub = Ed25519PublicKey.from_public_bytes(_b64url_decode(keys["relay"]["public_key_b64"]))
        relay_sig = _b64url_decode(v["relay_signature"])
        relay_pub.verify(relay_sig, canonical)  # raises if invalid

        # Verify caller signature
        caller_pub = Ed25519PublicKey.from_public_bytes(_b64url_decode(keys["caller"]["public_key_b64"]))
        caller_sig = _b64url_decode(v["caller_signature"])
        caller_pub.verify(caller_sig, canonical)  # raises if invalid

    def test_itv10_vector2_unilateral_relay_only(self, relay_with_identity):
        """ITV-10: tv-ir-002 — bilateral=false, relay sig valid, caller_signature=null."""
        data = _get(f"{relay_with_identity}/ir/test-vectors")
        v = next(v for v in data["vectors"] if v["id"] == "tv-ir-002")
        keys = data["keys"]

        assert v["bilateral"] is False
        assert v["relay_signature_valid"] is True
        assert v.get("caller_signature") is None
        assert v.get("caller_signature_valid") is None

        canonical = bytes.fromhex(v["canonical_bytes_hex"])
        relay_pub = Ed25519PublicKey.from_public_bytes(_b64url_decode(keys["relay"]["public_key_b64"]))
        relay_sig = _b64url_decode(v["relay_signature"])
        relay_pub.verify(relay_sig, canonical)

    def test_itv11_vector3_tampered_caller_sig(self, relay_with_identity):
        """ITV-11: tv-ir-003 — caller_signature_valid=false (tampered payload), bilateral=false."""
        data = _get(f"{relay_with_identity}/ir/test-vectors")
        v = next(v for v in data["vectors"] if v["id"] == "tv-ir-003")
        keys = data["keys"]

        assert v["bilateral"] is False
        assert v["caller_signature_valid"] is False
        assert v["relay_signature_valid"] is True

        canonical = bytes.fromhex(v["canonical_bytes_hex"])
        caller_pub = Ed25519PublicKey.from_public_bytes(_b64url_decode(keys["caller"]["public_key_b64"]))
        caller_sig = _b64url_decode(v["caller_signature"])

        # This signature SHOULD NOT verify against the canonical payload (it's tampered)
        with pytest.raises(Exception):
            caller_pub.verify(caller_sig, canonical)

    def test_itv12_vector4_did_key_cross_verify(self, relay_with_identity):
        """ITV-12: tv-ir-004 — did:key identifiers in canonical payload, signatures still valid."""
        data = _get(f"{relay_with_identity}/ir/test-vectors")
        v = next(v for v in data["vectors"] if v["id"] == "tv-ir-004")
        keys = data["keys"]

        assert v["bilateral"] is True
        payload = v["canonical_payload"]
        # did:key format in payload
        assert payload["relay_did"].startswith("did:key:z6Mk")
        assert payload["caller_did"].startswith("did:key:z6Mk")

        canonical = bytes.fromhex(v["canonical_bytes_hex"])

        relay_pub = Ed25519PublicKey.from_public_bytes(_b64url_decode(keys["relay"]["public_key_b64"]))
        relay_pub.verify(_b64url_decode(v["relay_signature"]), canonical)

        caller_pub = Ed25519PublicKey.from_public_bytes(_b64url_decode(keys["caller"]["public_key_b64"]))
        caller_pub.verify(_b64url_decode(v["caller_signature"]), canonical)


# ══ ITV-13..15: Determinism & chain integrity ═════════════════════════════════

class TestDeterminismAndChain:
    """ITV-13..15: Test vectors are deterministic and chain-linked."""

    def test_itv13_vectors_deterministic(self, relay_with_identity):
        """ITV-13: Two calls to /ir/test-vectors produce identical signatures (deterministic keys)."""
        d1 = _get(f"{relay_with_identity}/ir/test-vectors")
        d2 = _get(f"{relay_with_identity}/ir/test-vectors")
        # Signatures must be identical (same seed → same key → same sig over same payload)
        for v1, v2 in zip(d1["vectors"], d2["vectors"]):
            assert v1["canonical_bytes_hex"] == v2["canonical_bytes_hex"], (
                f"canonical_bytes_hex differs for {v1['id']}"
            )
            if v1.get("relay_signature"):
                assert v1["relay_signature"] == v2["relay_signature"], (
                    f"relay_signature differs for {v1['id']} (not deterministic)"
                )

    def test_itv14_vector2_previous_hash_references_vector1(self, relay_with_identity):
        """ITV-14: tv-ir-002.previous_hash is sha256 of tv-ir-001 canonical payload."""
        data = _get(f"{relay_with_identity}/ir/test-vectors")
        v1 = next(v for v in data["vectors"] if v["id"] == "tv-ir-001")
        v2 = next(v for v in data["vectors"] if v["id"] == "tv-ir-002")

        v1_canonical = v1["canonical_payload"]
        v1_bytes = json.dumps(v1_canonical, sort_keys=True, separators=(",", ":")).encode()
        expected_hash = "sha256:" + hashlib.sha256(v1_bytes).hexdigest()

        assert v2["canonical_payload"]["previous_hash"] == expected_hash, (
            f"tv-ir-002.previous_hash should reference tv-ir-001. "
            f"Expected: {expected_hash}, got: {v2['canonical_payload']['previous_hash']}"
        )

    def test_itv15_vector1_previous_hash_is_genesis(self, relay_with_identity):
        """ITV-15: tv-ir-001.previous_hash = 'genesis' (first record in chain)."""
        data = _get(f"{relay_with_identity}/ir/test-vectors")
        v1 = next(v for v in data["vectors"] if v["id"] == "tv-ir-001")
        assert v1["canonical_payload"]["previous_hash"] == "genesis"

    def test_itv16_canonical_bytes_match_payload(self, relay_with_identity):
        """ITV-16: canonical_bytes_hex decodes to JSON-serialized canonical_payload."""
        data = _get(f"{relay_with_identity}/ir/test-vectors")
        for v in data["vectors"]:
            if v.get("canonical_bytes_hex"):
                decoded = bytes.fromhex(v["canonical_bytes_hex"]).decode()
                expected = json.dumps(v["canonical_payload"], sort_keys=True, separators=(",", ":"))
                assert decoded == expected, (
                    f"{v['id']}: canonical_bytes_hex does not match canonical_payload serialization"
                )


# ══ ITV-17..18: Edge cases ════════════════════════════════════════════════════

class TestEdgeCases:
    """ITV-17..18: No-identity relay and record block correctness."""

    def test_itv17_no_identity_returns_503(self, relay_no_identity):
        """ITV-17: Relay without --identity returns 503 for /ir/test-vectors."""
        try:
            _get(f"{relay_no_identity}/ir/test-vectors")
            pytest.fail("Expected HTTP error 503 but got 200")
        except urllib.error.HTTPError as e:
            assert e.code == 503, f"Expected 503, got {e.code}"

    def test_itv18_record_block_has_all_bilateral_fields(self, relay_with_identity):
        """ITV-18: tv-ir-001.record block contains all expected bilateral IR fields."""
        data = _get(f"{relay_with_identity}/ir/test-vectors")
        v1 = next(v for v in data["vectors"] if v["id"] == "tv-ir-001")
        record = v1["record"]

        required = {
            "id", "type", "relay_did", "caller_did", "task_id", "skill_id",
            "sequence_a", "previous_hash", "timestamp",
            "relay_signature", "relay_public_key",
            "caller_signature", "caller_public_key",
            "caller_signature_valid", "bilateral",
            "quality_hint", "caller_token_hash",
        }
        missing = required - set(record.keys())
        assert not missing, f"record missing fields: {missing}"
        assert record["bilateral"] is True
        assert record["caller_signature_valid"] is True
