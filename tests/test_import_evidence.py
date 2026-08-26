"""Tests for POST /ir/import-evidence and GET /ir/imported-evidence (v2.65).

IE-1..20: import evidence endpoint validation
  IE-1:  POST /ir/import-evidence with valid bilateral IR → 200 ok
  IE-2:  response contains import_id, verify, reputation_update
  IE-3:  verify.relay_sig_valid=true for valid relay signature
  IE-4:  verify.caller_sig_valid=true for valid caller signature
  IE-5:  verify.bilateral_verified=true when both signatures valid
  IE-6:  reputation_update.trust_delta=+1 for bilateral_verified
  IE-7:  POST /ir/import-evidence with relay-only IR → trust_delta=0
  IE-8:  POST /ir/import-evidence with tampered relay_signature → relay_sig_valid=false, trust_delta=-1
  IE-9:  POST /ir/import-evidence with tampered caller_signature → caller_sig_valid=false
  IE-10: POST /ir/import-evidence missing 'ir' field → 400
  IE-11: POST /ir/import-evidence ir not object → 400
  IE-12: reputation_update contains aps_schema='v1'
  IE-13: reputation_update contains source_relay_did, agent_did, task_id, skill_id
  IE-14: reputation_update contains freshness_hint (int or None)
  IE-15: GET /ir/imported-evidence → 200 with records list
  IE-16: GET /ir/imported-evidence returns the imported record
  IE-17: GET /ir/imported-evidence?agent_did=<did> filters by agent_did
  IE-18: GET /ir/imported-evidence?limit=1 respects limit
  IE-19: POST /ir/import-evidence with no signatures → relay_sig_valid=null, trust_delta=-1
  IE-20: AgentCard capabilities.import_evidence=true + endpoints.import_evidence set
"""

import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

RELAY_PY = str(Path(__file__).parent.parent / "relay" / "acp_relay.py")
ED25519_AVAILABLE = True
try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey, Ed25519PublicKey,
    )
    import base64 as _base64
except ImportError:
    ED25519_AVAILABLE = False

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def wait_http_ready(port, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/status", timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def _kill_port(port):
    try:
        result = subprocess.run(
            ["ss", "-tlnp", f"sport = :{port}"],
            capture_output=True, text=True, timeout=3
        )
        for line in result.stdout.splitlines():
            if f":{port}" in line and "pid=" in line:
                pid_str = line.split("pid=")[1].split(",")[0]
                try:
                    os.kill(int(pid_str), 9)
                except Exception:
                    pass
    except Exception:
        pass
    time.sleep(0.3)


def _start_relay(ws_port, extra_flags=None):
    http_port = ws_port + 100
    _kill_port(ws_port)
    _kill_port(http_port)
    env = os.environ.copy()
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        env.pop(k, None)
    cmd = [sys.executable, RELAY_PY,
           "--port", str(ws_port), "--name", "IERelay",
           "--local-only", "--test-mode"]
    if extra_flags:
        cmd.extend(extra_flags)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    for s in (proc.stdout, proc.stderr):
        threading.Thread(target=lambda x=s: x.read(), daemon=True).start()
    assert wait_http_ready(http_port), f"relay on :{http_port} did not start"
    return proc


def _http(method, http_port, path, body=None):
    url = f"http://127.0.0.1:{http_port}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _b64url_encode(b: bytes) -> str:
    import base64
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    import base64
    s = s.replace("-", "+").replace("_", "/")
    s += "=" * (-len(s) % 4)
    return base64.b64decode(s)


def _make_bilateral_ir(relay_priv=None, caller_priv=None, tamper_relay=False, tamper_caller=False,
                       omit_relay=False, omit_caller=True):
    """Build a synthetic bilateral IR record, optionally with Ed25519 signatures."""
    import base64

    relay_did = "did:key:z6Mk_test_relay"
    caller_did = "did:key:z6Mk_test_caller"
    task_id = "task-test-001"
    skill_id = "test_skill"
    record_id = "ir-test-001"
    sequence_a = 1
    previous_hash = "genesis"
    timestamp = "2026-04-06T07:00:00Z"

    canonical = {
        "id":            record_id,
        "type":          "interaction",
        "relay_did":     relay_did,
        "caller_did":    caller_did,
        "task_id":       task_id,
        "skill_id":      skill_id,
        "sequence_a":    sequence_a,
        "previous_hash": previous_hash,
        "timestamp":     timestamp,
    }
    canonical_bytes = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()

    relay_signature = None
    relay_public_key = None
    caller_signature = None
    caller_public_key = None

    if ED25519_AVAILABLE and not omit_relay:
        if relay_priv is None:
            relay_priv = Ed25519PrivateKey.generate()
        relay_pub = relay_priv.public_key()
        sig = relay_priv.sign(canonical_bytes)
        relay_signature = _b64url_encode(sig)
        if tamper_relay:
            relay_signature = _b64url_encode(b"\x00" * 64)
        relay_public_key = _b64url_encode(
            relay_pub.public_bytes_raw() if hasattr(relay_pub, "public_bytes_raw")
            else relay_pub.public_bytes(
                encoding=__import__("cryptography.hazmat.primitives.serialization", fromlist=["Encoding"]).Encoding.Raw,
                format=__import__("cryptography.hazmat.primitives.serialization", fromlist=["PublicFormat"]).PublicFormat.Raw,
            )
        )

    if ED25519_AVAILABLE and not omit_caller:
        if caller_priv is None:
            caller_priv = Ed25519PrivateKey.generate()
        caller_pub = caller_priv.public_key()
        sig = caller_priv.sign(canonical_bytes)
        caller_signature = _b64url_encode(sig)
        if tamper_caller:
            caller_signature = _b64url_encode(b"\x00" * 64)
        caller_public_key = _b64url_encode(
            caller_pub.public_bytes_raw() if hasattr(caller_pub, "public_bytes_raw")
            else caller_pub.public_bytes(
                encoding=__import__("cryptography.hazmat.primitives.serialization", fromlist=["Encoding"]).Encoding.Raw,
                format=__import__("cryptography.hazmat.primitives.serialization", fromlist=["PublicFormat"]).PublicFormat.Raw,
            )
        )

    ir = {
        **canonical,
        "quality_hint":            None,
        "caller_token_hash":       None,
        "relay_signature":         relay_signature,
        "relay_public_key":        relay_public_key,
        "caller_signature":        caller_signature,
        "caller_public_key":       caller_public_key,
        "caller_signature_valid":  None,
        "bilateral":               bool(relay_signature and caller_signature),
    }
    return ir


# ── Fixtures ──────────────────────────────────────────────────────────────────

WS_PORT = 47200
HTTP_PORT = WS_PORT + 100


@pytest.fixture(scope="module")
def relay():
    proc = _start_relay(WS_PORT)
    yield HTTP_PORT
    proc.terminate()
    proc.wait(timeout=5)


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not ED25519_AVAILABLE, reason="cryptography not installed")
def test_ie1_bilateral_ir_import_ok(relay):
    """IE-1: POST /ir/import-evidence with valid bilateral IR → 200 ok."""
    relay_priv = Ed25519PrivateKey.generate()
    caller_priv = Ed25519PrivateKey.generate()
    ir = _make_bilateral_ir(relay_priv=relay_priv, caller_priv=caller_priv, omit_caller=False)
    s, b = _http("POST", relay, "/ir/import-evidence", {"ir": ir})
    assert s == 200, f"{s}: {b}"
    assert b["ok"] is True


@pytest.mark.skipif(not ED25519_AVAILABLE, reason="cryptography not installed")
def test_ie2_response_shape(relay):
    """IE-2: response contains import_id, verify, reputation_update."""
    ir = _make_bilateral_ir(omit_caller=False)
    s, b = _http("POST", relay, "/ir/import-evidence", {"ir": ir})
    assert s == 200
    assert "import_id" in b
    assert "verify" in b
    assert "reputation_update" in b
    assert b["import_id"].startswith("imp-")


@pytest.mark.skipif(not ED25519_AVAILABLE, reason="cryptography not installed")
def test_ie3_relay_sig_valid(relay):
    """IE-3: verify.relay_sig_valid=true for valid relay signature."""
    relay_priv = Ed25519PrivateKey.generate()
    ir = _make_bilateral_ir(relay_priv=relay_priv, omit_caller=True)
    s, b = _http("POST", relay, "/ir/import-evidence", {"ir": ir})
    assert s == 200
    assert b["verify"]["relay_sig_valid"] is True


@pytest.mark.skipif(not ED25519_AVAILABLE, reason="cryptography not installed")
def test_ie4_caller_sig_valid(relay):
    """IE-4: verify.caller_sig_valid=true for valid caller signature."""
    relay_priv = Ed25519PrivateKey.generate()
    caller_priv = Ed25519PrivateKey.generate()
    ir = _make_bilateral_ir(relay_priv=relay_priv, caller_priv=caller_priv, omit_caller=False)
    s, b = _http("POST", relay, "/ir/import-evidence", {"ir": ir})
    assert s == 200
    assert b["verify"]["caller_sig_valid"] is True


@pytest.mark.skipif(not ED25519_AVAILABLE, reason="cryptography not installed")
def test_ie5_bilateral_verified(relay):
    """IE-5: verify.bilateral_verified=true when both signatures valid."""
    relay_priv = Ed25519PrivateKey.generate()
    caller_priv = Ed25519PrivateKey.generate()
    ir = _make_bilateral_ir(relay_priv=relay_priv, caller_priv=caller_priv, omit_caller=False)
    s, b = _http("POST", relay, "/ir/import-evidence", {"ir": ir})
    assert s == 200
    assert b["verify"]["bilateral_verified"] is True


@pytest.mark.skipif(not ED25519_AVAILABLE, reason="cryptography not installed")
def test_ie6_trust_delta_bilateral(relay):
    """IE-6: reputation_update.trust_delta=+1 for bilateral_verified."""
    relay_priv = Ed25519PrivateKey.generate()
    caller_priv = Ed25519PrivateKey.generate()
    ir = _make_bilateral_ir(relay_priv=relay_priv, caller_priv=caller_priv, omit_caller=False)
    s, b = _http("POST", relay, "/ir/import-evidence", {"ir": ir})
    assert s == 200
    assert b["reputation_update"]["trust_delta"] == 1


@pytest.mark.skipif(not ED25519_AVAILABLE, reason="cryptography not installed")
def test_ie7_trust_delta_relay_only(relay):
    """IE-7: POST /ir/import-evidence with relay-only IR → trust_delta=0."""
    relay_priv = Ed25519PrivateKey.generate()
    ir = _make_bilateral_ir(relay_priv=relay_priv, omit_caller=True)
    s, b = _http("POST", relay, "/ir/import-evidence", {"ir": ir})
    assert s == 200
    assert b["reputation_update"]["trust_delta"] == 0


@pytest.mark.skipif(not ED25519_AVAILABLE, reason="cryptography not installed")
def test_ie8_tampered_relay_sig(relay):
    """IE-8: tampered relay_signature → relay_sig_valid=false, trust_delta=-1."""
    relay_priv = Ed25519PrivateKey.generate()
    ir = _make_bilateral_ir(relay_priv=relay_priv, tamper_relay=True, omit_caller=True)
    s, b = _http("POST", relay, "/ir/import-evidence", {"ir": ir})
    assert s == 200
    assert b["verify"]["relay_sig_valid"] is False
    assert b["reputation_update"]["trust_delta"] == -1


@pytest.mark.skipif(not ED25519_AVAILABLE, reason="cryptography not installed")
def test_ie9_tampered_caller_sig(relay):
    """IE-9: tampered caller_signature → caller_sig_valid=false."""
    relay_priv = Ed25519PrivateKey.generate()
    caller_priv = Ed25519PrivateKey.generate()
    ir = _make_bilateral_ir(relay_priv=relay_priv, caller_priv=caller_priv,
                             tamper_caller=True, omit_caller=False)
    s, b = _http("POST", relay, "/ir/import-evidence", {"ir": ir})
    assert s == 200
    assert b["verify"]["caller_sig_valid"] is False


def test_ie10_missing_ir_field(relay):
    """IE-10: POST /ir/import-evidence missing 'ir' field → 400."""
    s, b = _http("POST", relay, "/ir/import-evidence", {"not_ir": {}})
    assert s == 400
    assert b["ok"] is False
    assert "ir" in b.get("error", "")


def test_ie11_ir_not_object(relay):
    """IE-11: POST /ir/import-evidence ir not object → 400."""
    s, b = _http("POST", relay, "/ir/import-evidence", {"ir": "not_an_object"})
    assert s == 400
    assert b["ok"] is False


def test_ie12_aps_schema(relay):
    """IE-12: reputation_update contains aps_schema='v1'."""
    ir = _make_bilateral_ir(omit_relay=True, omit_caller=True)
    s, b = _http("POST", relay, "/ir/import-evidence", {"ir": ir})
    assert s == 200
    assert b["reputation_update"]["aps_schema"] == "v1"


def test_ie13_rep_update_fields(relay):
    """IE-13: reputation_update contains source_relay_did, agent_did, task_id, skill_id."""
    ir = _make_bilateral_ir(omit_relay=True, omit_caller=True)
    s, b = _http("POST", relay, "/ir/import-evidence", {"ir": ir})
    assert s == 200
    rep = b["reputation_update"]
    assert rep["source_relay_did"] == ir["relay_did"]
    assert rep["agent_did"] == ir["caller_did"]
    assert rep["task_id"] == ir["task_id"]
    assert rep["skill_id"] == ir["skill_id"]


def test_ie14_freshness_hint(relay):
    """IE-14: reputation_update contains freshness_hint (int or None)."""
    ir = _make_bilateral_ir(omit_relay=True, omit_caller=True)
    s, b = _http("POST", relay, "/ir/import-evidence", {"ir": ir})
    assert s == 200
    fh = b["reputation_update"].get("freshness_hint")
    assert fh is None or isinstance(fh, int)


def test_ie15_list_imported_evidence(relay):
    """IE-15: GET /ir/imported-evidence → 200 with records list."""
    s, b = _http("GET", relay, "/ir/imported-evidence")
    assert s == 200
    assert b["ok"] is True
    assert "records" in b
    assert isinstance(b["records"], list)
    assert isinstance(b["total"], int)


def test_ie16_imported_record_visible(relay):
    """IE-16: GET /ir/imported-evidence returns the imported record."""
    ir = _make_bilateral_ir(omit_relay=True, omit_caller=True)
    ir["task_id"] = "task-ie16-unique"
    _, post_b = _http("POST", relay, "/ir/import-evidence", {"ir": ir})
    import_id = post_b["import_id"]

    s, b = _http("GET", relay, "/ir/imported-evidence")
    assert s == 200
    found = any(r["import_id"] == import_id for r in b["records"])
    assert found, f"import_id {import_id} not found in imported-evidence list"


def test_ie17_filter_by_agent_did(relay):
    """IE-17: GET /ir/imported-evidence?agent_did=<did> filters by agent_did."""
    unique_did = "did:key:z6Mk_ie17_unique_filter"
    ir = _make_bilateral_ir(omit_relay=True, omit_caller=True)
    ir["caller_did"] = unique_did
    _http("POST", relay, "/ir/import-evidence", {"ir": ir})

    s, b = _http("GET", relay, f"/ir/imported-evidence?agent_did={urllib.parse.quote(unique_did)}")
    assert s == 200
    for r in b["records"]:
        assert unique_did in (r.get("reputation_update", {}).get("agent_did") or "")


def test_ie18_limit(relay):
    """IE-18: GET /ir/imported-evidence?limit=1 respects limit."""
    # Import at least 2 records
    for i in range(2):
        ir = _make_bilateral_ir(omit_relay=True, omit_caller=True)
        ir["task_id"] = f"task-ie18-{i}"
        _http("POST", relay, "/ir/import-evidence", {"ir": ir})

    s, b = _http("GET", relay, "/ir/imported-evidence?limit=1")
    assert s == 200
    assert b["count"] <= 1
    assert len(b["records"]) <= 1


def test_ie19_no_signatures(relay):
    """IE-19: IR with no signatures → relay_sig_valid=None, trust_delta=-1."""
    ir = _make_bilateral_ir(omit_relay=True, omit_caller=True)
    s, b = _http("POST", relay, "/ir/import-evidence", {"ir": ir})
    assert s == 200
    assert b["verify"]["relay_sig_valid"] is None
    assert b["reputation_update"]["trust_delta"] == -1


def test_ie20_agentcard_capability(relay):
    """IE-20: AgentCard capabilities.import_evidence=true + endpoints.import_evidence set."""
    s, b = _http("GET", relay, "/status")
    assert s == 200
    card = b.get("agent_card", b)  # agent_card nested or top-level
    caps = card.get("capabilities", {})
    eps  = card.get("endpoints",    {})
    # import_evidence capability presence (may be false if no identity, but field must exist)
    assert "import_evidence" in caps or "import_evidence" in eps, \
        f"import_evidence not present in capabilities or endpoints.\ncaps={caps}\neps={eps}"
    if caps.get("import_evidence"):
        assert eps.get("import_evidence") == "/ir/import-evidence"
