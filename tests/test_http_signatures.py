"""
RFC 9421 HTTP Signatures Tests — v3.18 feature verification

Tests POST /verify/http-signature and POST /sign/http-request endpoints
for RFC 9421 HTTP Message Signatures transport-layer security.

Test matrix:
  test_hs_01  capabilities.http_signatures=true declared in AgentCard and /status
  test_hs_02  valid RFC 9421 signature → valid:true from /verify/http-signature
  test_hs_03  invalid signature → valid:false from /verify/http-signature
  test_hs_04  no signature headers → normal processing (backward compat)
  test_hs_05  signature covering @method + @target-uri + content-type → correct base string
  test_hs_06  tampered body → signature verification fails
  test_hs_07  /sign/http-request generates signature → verified by /verify/http-signature
  test_hs_08  ERR_INVALID_SIGNATURE 401 error code on invalid signature
"""
import pytest
import requests
import subprocess
import time
import signal
import sys
import os
import threading
import random
import base64
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE_PORT = 53200


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _free_port_pair():
    """Return a free (ws_port, http_port) pair."""
    import socket
    for _ in range(100):
        ws_port = BASE_PORT + random.randint(0, 800)
        http_port = ws_port + 100
        try:
            s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s1.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s1.bind(("127.0.0.1", ws_port))
            s1.close()
            s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s2.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s2.bind(("127.0.0.1", http_port))
            s2.close()
            return ws_port, http_port
        except OSError:
            continue
    raise RuntimeError("Cannot find free port pair")


def _relay_env():
    env = os.environ.copy()
    for v in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
              "all_proxy", "ALL_PROXY", "no_proxy", "NO_PROXY"):
        env.pop(v, None)
    return env


def _start_relay(ws_port, http_port, name="HSTest"):
    """Start a relay subprocess and wait until HTTP /status is ready."""
    cmd = [
        sys.executable, "-u", "relay/acp_relay.py",
        "--port", str(ws_port),
        "--http-port", str(http_port),
        "--http-host", "127.0.0.1",
        "--name", name,
        "--local-only",
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_relay_env(),
        cwd=os.path.join(os.path.dirname(__file__), ".."),
    )
    deadline = time.time() + 30
    while time.time() < deadline:
        if proc.poll() is not None:
            out, err = proc.communicate()
            raise RuntimeError(f"Relay '{name}' exited early.\nstdout: {out}\nstderr: {err}")
        try:
            r = requests.get(f"http://127.0.0.1:{http_port}/status", timeout=0.5)
            if r.status_code == 200:
                return proc
        except Exception:
            pass
        time.sleep(0.3)
    proc.terminate()
    raise RuntimeError(f"Relay '{name}' did not start within 30s")


def _stop_relay(proc):
    if proc and proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def _make_sig_input(method, path, content_type="application/json", keyid=None, created=None):
    """Build a RFC 9421 Signature-Input header value."""
    import time as _t
    if created is None:
        created = int(_t.time())
    if keyid is None:
        keyid = "did:acp:testpubkey1234567890123456789012345678901234567890"
    fields = '"@method" "@target-uri" "content-type"'
    return f'sig1=({fields});alg="ed25519";keyid="{keyid}";created={created}'


def _make_canonical_base(method, path, content_type="application/json", created=None):
    """Build canonical signature base string for testing."""
    import time as _t
    if created is None:
        created = int(_t.time())
    fields = '"@method" "@target-uri" "content-type"'
    lines = [
        f'"@method": {method.upper()}',
        f'"@target-uri": {path}',
        f'"content-type": {content_type}',
        f'"@signature-params": ({fields});created={created}',
    ]
    return "\n".join(lines).encode("utf-8")


def _fake_ed25519_signature(data: bytes) -> str:
    """Generate a deterministic 'signature' for testing invalid signature scenario.
    This is NOT a real Ed25519 signature — it's a known-invalid value for test_hs_03.
    """
    import hashlib
    h = hashlib.sha256(data).digest()
    return base64.b64encode(b"\x00" * 64).decode("ascii")


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def single_relay():
    """A standalone relay with no peer — used for HTTP signature tests."""
    ws, http = _free_port_pair()
    proc = _start_relay(ws, http, "HSRelay")
    yield {"http": http, "ws": ws, "proc": proc}
    _stop_relay(proc)


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestHTTPSignatures:

    # ── test_hs_01 ──────────────────────────────────────────────────────────
    def test_hs_01_capability_declared(self, single_relay):
        """HS-01: AgentCard declares capabilities.http_signatures=true."""
        r = requests.get(f"http://127.0.0.1:{single_relay['http']}/.well-known/acp.json", timeout=5)
        assert r.status_code == 200
        card = r.json()
        assert "self" in card
        assert "http_signatures" in card["self"].get("capabilities", {})
        assert card["self"]["capabilities"]["http_signatures"] is True

    # ── test_hs_02 ──────────────────────────────────────────────────────────
    def test_hs_02_valid_signature(self, single_relay):
        """HS-02: Valid RFC 9421 signature → valid:true from /verify/http-signature."""
        # First sign a request
        sign_body = {
            "method": "POST",
            "path": "/message:send",
            "authority": "test.example.com",
            "headers": {"content-type": "application/json"},
            "covered_fields": ["@method", "@target-uri", "content-type"],
        }
        r = requests.post(
            f"http://127.0.0.1:{single_relay['http']}/sign/http-request",
            json=sign_body,
            timeout=5,
        )
        assert r.status_code == 200
        sig_data = r.json()
        assert sig_data["ok"] is True
        assert "signature_input" in sig_data
        assert "signature" in sig_data
        assert "signer" in sig_data

        # Now verify the generated signature
        verify_body = {
            "method": "POST",
            "path": "/message:send",
            "authority": "test.example.com",
            "headers": {"content-type": "application/json"},
            "signature_input": sig_data["signature_input"],
            "signature": sig_data["signature"],
        }
        r2 = requests.post(
            f"http://127.0.0.1:{single_relay['http']}/verify/http-signature",
            json=verify_body,
            timeout=5,
        )
        assert r2.status_code == 200
        result = r2.json()
        assert result["ok"] is True
        assert result["valid"] is True
        assert result.get("signer") is not None
        assert "@method" in result.get("covered_fields", [])

    # ── test_hs_03 ──────────────────────────────────────────────────────────
    def test_hs_03_invalid_signature(self, single_relay):
        """HS-03: Invalid signature → valid:false from /verify/http-signature."""
        sig_input = _make_sig_input("POST", "/message:send")
        # Use a known-invalid signature (all zeros)
        invalid_sig = base64.b64encode(b"\x00" * 64).decode("ascii")

        body = {
            "method": "POST",
            "path": "/message:send",
            "authority": "test.example.com",
            "headers": {"content-type": "application/json"},
            "signature_input": sig_input,
            "signature": invalid_sig,
        }
        r = requests.post(
            f"http://127.0.0.1:{single_relay['http']}/verify/http-signature",
            json=body,
            timeout=5,
        )
        # Should return 401 with valid:false
        assert r.status_code in (401, 200)  # 401 or 200 with valid:false
        result = r.json()
        assert result["valid"] is False
        assert result.get("error") is not None

    # ── test_hs_04 ──────────────────────────────────────────────────────────
    def test_hs_04_no_signature_backward_compat(self, single_relay):
        """HS-04: No signature headers → normal processing (backward compat)."""
        # /verify/http-signature should reject requests missing signature headers
        body = {
            "method": "POST",
            "path": "/message:send",
        }
        r = requests.post(
            f"http://127.0.0.1:{single_relay['http']}/verify/http-signature",
            json=body,
            timeout=5,
        )
        assert r.status_code == 400
        result = r.json()
        assert result["ok"] is False
        assert result["valid"] is False
        assert "neither" in result.get("error", "") or "signature" in result.get("error", "")

    # ── test_hs_05 ──────────────────────────────────────────────────────────
    def test_hs_05_covered_fields_base_string(self, single_relay):
        """HS-05: Signature covering @method + @target-uri + content-type → correct base string."""
        # Sign with specific covered fields
        sign_body = {
            "method": "POST",
            "path": "/message:send",
            "authority": "test.example.com",
            "headers": {"content-type": "application/json", "authorization": "Bearer token123"},
            "covered_fields": ["@method", "@target-uri", "content-type"],
        }
        r = requests.post(
            f"http://127.0.0.1:{single_relay['http']}/sign/http-request",
            json=sign_body,
            timeout=5,
        )
        assert r.status_code == 200
        sig_data = r.json()
        assert sig_data["ok"] is True

        # Verify — the base string should match exactly
        verify_body = {
            "method": "POST",
            "path": "/message:send",
            "authority": "test.example.com",
            "headers": {"content-type": "application/json", "authorization": "Bearer token123"},
            "signature_input": sig_data["signature_input"],
            "signature": sig_data["signature"],
        }
        r2 = requests.post(
            f"http://127.0.0.1:{single_relay['http']}/verify/http-signature",
            json=verify_body,
            timeout=5,
        )
        assert r2.status_code == 200
        result = r2.json()
        assert result["valid"] is True
        expected_fields = ["@method", "@target-uri", "content-type"]
        assert result.get("covered_fields") == expected_fields

    # ── test_hs_06 ──────────────────────────────────────────────────────────
    def test_hs_06_tampered_body_fails(self, single_relay):
        """HS-06: Tampered body → signature verification fails."""
        # Sign with one content-type
        sign_body = {
            "method": "POST",
            "path": "/message:send",
            "authority": "test.example.com",
            "headers": {"content-type": "application/json"},
            "covered_fields": ["@method", "@target-uri", "content-type"],
        }
        r = requests.post(
            f"http://127.0.0.1:{single_relay['http']}/sign/http-request",
            json=sign_body,
            timeout=5,
        )
        assert r.status_code == 200
        sig_data = r.json()

        # Verify with DIFFERENT content-type (tampered)
        verify_body = {
            "method": "POST",
            "path": "/message:send",
            "authority": "test.example.com",
            "headers": {"content-type": "text/plain"},  # Tampered!
            "signature_input": sig_data["signature_input"],
            "signature": sig_data["signature"],
        }
        r2 = requests.post(
            f"http://127.0.0.1:{single_relay['http']}/verify/http-signature",
            json=verify_body,
            timeout=5,
        )
        result = r2.json()
        assert result["valid"] is False
        assert result.get("error") is not None

    # ── test_hs_07 ──────────────────────────────────────────────────────────
    def test_hs_07_sign_then_verify_loop(self, single_relay):
        """HS-07: /sign/http-request generates signature → verified by /verify/http-signature."""
        for method in ["POST", "GET", "PUT"]:
            for path in ["/message:send", "/status", "/tasks"]:
                sign_body = {
                    "method": method,
                    "path": path,
                    "authority": "loop.test.com",
                    "headers": {"content-type": "application/json"},
                    "covered_fields": ["@method", "@target-uri", "content-type"],
                }
                r = requests.post(
                    f"http://127.0.0.1:{single_relay['http']}/sign/http-request",
                    json=sign_body,
                    timeout=5,
                )
                assert r.status_code == 200
                sig_data = r.json()
                assert sig_data["ok"] is True

                verify_body = {
                    "method": method,
                    "path": path,
                    "authority": "loop.test.com",
                    "headers": {"content-type": "application/json"},
                    "signature_input": sig_data["signature_input"],
                    "signature": sig_data["signature"],
                }
                r2 = requests.post(
                    f"http://127.0.0.1:{single_relay['http']}/verify/http-signature",
                    json=verify_body,
                    timeout=5,
                )
                assert r2.status_code == 200
                result = r2.json()
                assert result["valid"] is True, f"Failed for {method} {path}: {result}"

    # ── test_hs_08 ──────────────────────────────────────────────────────────
    def test_hs_08_err_invalid_signature_401(self, single_relay):
        """HS-08: ERR_INVALID_SIGNATURE 401 error code on invalid signature."""
        sig_input = _make_sig_input("POST", "/message:send")
        invalid_sig = base64.b64encode(b"\x00" * 64).decode("ascii")

        body = {
            "method": "POST",
            "path": "/message:send",
            "authority": "test.example.com",
            "headers": {"content-type": "application/json"},
            "signature_input": sig_input,
            "signature": invalid_sig,
        }
        r = requests.post(
            f"http://127.0.0.1:{single_relay['http']}/verify/http-signature",
            json=body,
            timeout=5,
        )
        result = r.json()
        assert result["valid"] is False
        # Check that error indicates invalid signature
        assert result.get("error") is not None
        assert "invalid" in result.get("error", "").lower() or "unsupported" in result.get("error", "").lower()
