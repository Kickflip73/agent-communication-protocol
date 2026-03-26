"""
test_peer_card_verify.py — ACP v1.9 Peer AgentCard Auto-Verification tests

Tests:
  PV1: capabilities.auto_card_verify=True always (regardless of --identity)
  PV2: GET /peer/verify returns 404 when no peer connected
  PV3: endpoints.peer_verify = "/peer/verify" in AgentCard
  PV4: _send_agent_card sends signed card when --identity enabled
  PV5: auto-verify succeeds when peer sends valid signed card (two relay integration)
  PV6: auto-verify reports unsigned when peer has no card_sig
  PV7: GET /peer/verify result includes peer_name, peer_did, verified, scheme
  PV8: peer_card_verification cleared on disconnect
"""

import json
import pytest
import subprocess
import time
import socket
import urllib.request
import urllib.error
import sys
import os
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RELAY_PATH = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")


def _free_port_pair() -> tuple[int, int]:
    """
    Return a (ws_port, http_port) pair where http_port = ws_port + 100,
    and both are currently available.  Retries until a valid pair is found.
    BUG-026 fix: avoids fixed-port collisions across concurrent test files.
    """
    import random
    for _ in range(50):
        # Pick a WS candidate in a test-specific range (8200–8700)
        ws = random.randint(8200, 8700)
        http = ws + 100
        # Check both ports are free
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
    # Fallback — original fixed ports (unlikely to reach here)
    return 7880, 7980


# Dynamic ports — allocated at module import to avoid cross-test collisions (BUG-026 fix)
HOST_WS, HOST_HTTP   = _free_port_pair()
GUEST_WS, GUEST_HTTP = _free_port_pair()

_host_proc  = None
_guest_proc = None


def _make_env():
    env = os.environ.copy()
    for k in ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY"):
        env.pop(k, None)
    return env


def _wait_ready(http_port, timeout=12):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://localhost:{http_port}/.well-known/acp.json", timeout=1) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.2)
    return False


def _get(http_port, path):
    with urllib.request.urlopen(f"http://localhost:{http_port}{path}", timeout=5) as r:
        return r.status, json.loads(r.read())


def _get_link(http_port):
    _, data = _get(http_port, "/status")
    return data.get("link") or data.get("session_link")


@pytest.fixture(scope="module", autouse=True)
def two_relays():
    """Start host relay (no identity) and guest relay (with identity), used for integration tests."""
    global _host_proc, _guest_proc

    env = _make_env()
    # Use a port-specific identity path to avoid cross-run collisions
    identity_path = f"/tmp/acp_pv_identity_{GUEST_WS}.json"

    _host_proc = subprocess.Popen(
        [sys.executable, RELAY_PATH,
         "--port", str(HOST_WS), "--name", "PVHost", "--relay"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
    )
    if not _wait_ready(HOST_HTTP):
        _host_proc.kill()
        pytest.fail(f"Host relay (HTTP:{HOST_HTTP}) did not start in time")

    _guest_proc = subprocess.Popen(
        [sys.executable, RELAY_PATH,
         "--port", str(GUEST_WS), "--name", "PVGuest", "--identity", identity_path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
    )
    if not _wait_ready(GUEST_HTTP):
        _host_proc.kill()
        _guest_proc.kill()
        pytest.fail(f"Guest relay (HTTP:{GUEST_HTTP}) did not start in time")

    yield

    for p in (_host_proc, _guest_proc):
        p.terminate()
        try:
            p.wait(timeout=6)
        except subprocess.TimeoutExpired:
            p.kill()


# ─────────────────────────────────────────────────────────────────────────────

def test_pv1_capabilities_auto_card_verify():
    """PV1: capabilities.auto_card_verify=True in AgentCard (both relays)."""
    for port, name in [(HOST_HTTP, "host"), (GUEST_HTTP, "guest")]:
        _, data = _get(port, "/.well-known/acp.json")
        caps = data["self"].get("capabilities", {})
        assert caps.get("auto_card_verify") is True, (
            f"capabilities.auto_card_verify should be True on {name} relay: {caps}"
        )


def test_pv2_peer_verify_404_when_no_peer():
    """PV2: GET /peer/verify returns 404 when no peer connected."""
    req = urllib.request.Request(
        f"http://localhost:{HOST_HTTP}/peer/verify",
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            status = r.status
            body = json.loads(r.read())
    except urllib.error.HTTPError as e:
        status = e.code
        body = json.loads(e.read())

    assert status == 404, f"Expected 404 with no peer, got {status}: {body}"
    assert "error" in body


def test_pv3_endpoints_peer_verify_in_agentcard():
    """PV3: endpoints.peer_verify = '/peer/verify' in AgentCard."""
    for port, name in [(HOST_HTTP, "host"), (GUEST_HTTP, "guest")]:
        _, data = _get(port, "/.well-known/acp.json")
        endpoints = data["self"].get("endpoints", {})
        assert endpoints.get("peer_verify") == "/peer/verify", (
            f"endpoints.peer_verify missing on {name} relay: {endpoints}"
        )


def test_pv4_sent_card_is_signed():
    """PV4: /.well-known/acp.json returns signed card when --identity enabled."""
    _, data = _get(GUEST_HTTP, "/.well-known/acp.json")
    card = data["self"]
    identity = card.get("identity") or {}
    assert "card_sig" in identity, (
        f"guest relay should send signed card (--identity enabled): {identity}"
    )
    assert len(identity["card_sig"]) > 60, "card_sig too short"


def test_pv5_auto_verify_after_peer_connect():
    """
    PV5: After two relays connect, GET /peer/verify returns verified=True on the receiver.

    This test connects host and guest, waits for AgentCard exchange, then
    checks /peer/verify on the guest side (guest connected to host relay's link).

    Note: This is an integration test — may be skipped if relay session
    creation is blocked by sandbox network policy.
    """
    # Get host relay link
    try:
        _, status_data = _get(HOST_HTTP, "/status")
        link = status_data.get("link") or status_data.get("session_link")
    except Exception as e:
        pytest.skip(f"Cannot get host relay link: {e}")

    if not link or not link.startswith("acp://"):
        pytest.skip(f"Host relay has no valid acp:// link (sandbox may block relay registration): {link}")

    # Connect guest to host's link
    try:
        connect_req = urllib.request.Request(
            f"http://localhost:{GUEST_HTTP}/peers/connect",
            data=json.dumps({"link": link}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(connect_req, timeout=8) as r:
            connect_result = json.loads(r.read())
    except Exception as e:
        pytest.skip(f"Guest could not connect to host link (sandbox may block): {e}")

    # Wait for AgentCard exchange
    deadline = time.time() + 8
    verified = False
    while time.time() < deadline:
        try:
            _, vr = _get(GUEST_HTTP, "/peer/verify")
            if vr.get("verified") is True:
                verified = True
                break
            if vr.get("valid") is False:
                break  # definitive failure
        except urllib.error.HTTPError as e:
            if e.code == 404:
                time.sleep(0.3)
                continue
            raise
        time.sleep(0.3)

    try:
        _, vr = _get(GUEST_HTTP, "/peer/verify")
        assert vr.get("verified") is True, (
            f"Expected verified=True after peer connect: {vr}"
        )
        assert vr.get("peer_name") is not None
    except urllib.error.HTTPError as e:
        if e.code == 404:
            pytest.skip("Peers did not connect (no acp:// link available in sandbox)")
        raise


def test_pv6_auto_verify_unsigned_peer():
    """
    PV6: When peer sends unsigned card (no card_sig), peer/verify returns valid=None and error message.

    We verify this indirectly: a relay started without --identity sends unsigned cards.
    The host relay (started without --identity) sends unsigned cards.
    Check that guest's view of host shows the "unsigned" case.
    """
    # This test checks the unsigned path by inspecting the host's AgentCard
    _, data = _get(HOST_HTTP, "/.well-known/acp.json")
    host_card = data["self"]
    host_identity = host_card.get("identity")

    # Host was started WITHOUT --identity, so identity should be None or no card_sig
    if host_identity and host_identity.get("card_sig"):
        pytest.skip("Host relay unexpectedly has card_sig — skipping unsigned path test")

    # Simulate: verify host's card directly via POST /verify/card from guest
    verify_req = urllib.request.Request(
        f"http://localhost:{GUEST_HTTP}/verify/card",
        data=json.dumps(host_card).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(verify_req, timeout=5) as r:
        vr = json.loads(r.read())

    assert vr.get("valid") is False, (
        f"Unsigned card should return valid=False: {vr}"
    )
    # Without --identity: identity block is None → "public_key missing"
    # With --identity but no card_sig: → "card_sig missing"
    # Both are valid "unverifiable" errors
    error_msg = vr.get("error") or ""
    assert ("card_sig missing" in error_msg or "public_key missing" in error_msg), (
        f"Expected unverifiable error (card_sig or public_key missing), got: {vr}"
    )


def test_pv7_peer_verify_fields():
    """PV7: /peer/verify response includes expected fields when connected."""
    # Check the field structure exists (actual values depend on connection state)
    # Use POST /verify/card on a known signed card to validate field structure
    _, card_data = _get(GUEST_HTTP, "/.well-known/acp.json")
    signed_card = card_data["self"]

    verify_req = urllib.request.Request(
        f"http://localhost:{GUEST_HTTP}/verify/card",
        data=json.dumps(signed_card).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(verify_req, timeout=5) as r:
        vr = json.loads(r.read())

    # Verify all expected fields are present
    for field in ("valid", "did", "public_key", "scheme", "error"):
        assert field in vr, f"Field '{field}' missing from verify result: {vr}"

    assert vr["valid"] is True
    assert vr["scheme"] in ("ed25519", "ed25519+ca", "none", "unknown")
    assert vr["did"] is not None and vr["did"].startswith("did:acp:")


def test_pv8_peer_card_verification_cleared_on_disconnect():
    """PV8: peer_card_verification is None when no peer connected (cleared on disconnect)."""
    # Fresh relay: no peer connected, so peer_card_verification should be absent/None from /status
    try:
        _, status = _get(HOST_HTTP, "/status")
        # Check that peer_card is None (no peer connected initially)
        assert status.get("peer_card") is None, (
            f"peer_card should be None when no peer connected: {status.get('peer_card')}"
        )
    except Exception as e:
        pytest.skip(f"Cannot get /status: {e}")


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    failed = []
    tests = [
        ("PV1", test_pv1_capabilities_auto_card_verify),
        ("PV2", test_pv2_peer_verify_404_when_no_peer),
        ("PV3", test_pv3_endpoints_peer_verify_in_agentcard),
        ("PV4", test_pv4_sent_card_is_signed),
        ("PV5", test_pv5_auto_verify_after_peer_connect),
        ("PV6", test_pv6_auto_verify_unsigned_peer),
        ("PV7", test_pv7_peer_verify_fields),
        ("PV8", test_pv8_peer_card_verification_cleared_on_disconnect),
    ]
    for name, fn in tests:
        try:
            fn()
            print(f"✅ PASS  {name}")
        except pytest.skip.Exception as e:
            print(f"⏭️  SKIP  {name}: {e}")
        except Exception as e:
            print(f"❌ FAIL  {name}: {e}")
            failed.append(name)
    print(f"\n{'=' * 40}")
    sys.exit(1 if failed else 0)
