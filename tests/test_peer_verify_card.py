"""
ACP v2.55 — GET /peers/{peer_id}/verify-card Tests
====================================================
PVC-1  … unknown peer_id → 404 ERR_PEER_NOT_FOUND
PVC-2  … known peer with no AgentCard → 422 ERR_CARD_UNAVAILABLE
PVC-3  … known peer with unsigned card → 200 ok=True valid=False cached=False
PVC-4  … second call → cached=True
PVC-5  … force=1 bypasses cache
PVC-6  … ttl=0 behaves like force=1
PVC-7  … trust=1 + valid=False → trust_signal_written=False
PVC-8  … response includes peer_id / name / connected / card_available fields
PVC-9  … capabilities.peer_verify_card = True
PVC-10 … endpoints.peer_verify_card = /peers/{peer_id}/verify-card
"""

import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error

import pytest

RELAY_PY = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")


def _start_relay(ws_port):
    http_port = ws_port + 100
    env = os.environ.copy()
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        env.pop(k, None)
    proc = subprocess.Popen(
        [sys.executable, RELAY_PY,
         "--port", str(ws_port), "--name", "PVCRelay",
         "--local-only", "--test-mode"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
    )
    for s in (proc.stdout, proc.stderr):
        threading.Thread(target=lambda x=s: x.read(), daemon=True).start()
    deadline = time.time() + 12
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{http_port}/status", timeout=2) as r:
                if r.status == 200:
                    return proc, http_port
        except Exception:
            pass
        time.sleep(0.25)
    proc.terminate()
    raise RuntimeError(f"relay on :{http_port} did not start")


def _http(method, hp, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(
        f"http://127.0.0.1:{hp}{path}", data=data,
        headers=headers, method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _get(hp, path):
    return _http("GET", hp, path)


def _inject_peer_with_card(hp, peer_name, card):
    """Register a peer via /debug/inject (with agent_card field)."""
    s, b = _http("POST", hp, "/debug/inject", {
        "from": peer_name,
        "parts": [{"type": "text", "text": "hello"}],
        "agent_card": card,
    })
    assert s == 200, f"inject failed: {s} {b}"
    return b["peer_id"]


def _inject_peer_no_card(hp, peer_name):
    """Register a peer via /debug/inject (no agent_card)."""
    s, b = _http("POST", hp, "/debug/inject", {
        "from": peer_name,
        "parts": [{"type": "text", "text": "hello"}],
    })
    assert s == 200, f"inject failed: {s} {b}"
    return b["peer_id"]


CARD_UNSIGNED = {"name": "PeerAgent", "identity": {"scheme": "none"}}
CARD_NO_PUBKEY = {"name": "PeerAgent", "identity": {"scheme": "ed25519"}}


def test_pvc_1_to_10():
    proc, hp = _start_relay(52600)
    try:
        # ── Inject peers ─────────────────────────────────────────────────────
        peer_with_card = _inject_peer_with_card(hp, "AgentWithCard", CARD_UNSIGNED)
        peer_no_card   = _inject_peer_no_card(hp, "AgentNoCard")

        # ── PVC-1: unknown peer → 404 ────────────────────────────────────────
        s, b = _get(hp, "/peers/nonexistent_xyz/verify-card")
        assert s == 404, f"PVC-1: {s}"
        assert b.get("error_code") == "ERR_PEER_NOT_FOUND", f"PVC-1 code: {b}"

        # ── PVC-2: known peer, no card → 422 ────────────────────────────────
        s, b = _get(hp, f"/peers/{peer_no_card}/verify-card")
        assert s == 422, f"PVC-2: {s} {b}"
        assert b.get("error_code") == "ERR_CARD_UNAVAILABLE", f"PVC-2 code: {b}"
        assert b.get("card_available") is False, f"PVC-2 card_available: {b}"

        # ── PVC-3: known peer with unsigned card → 200 valid=False ───────────
        s, b = _get(hp, f"/peers/{peer_with_card}/verify-card")
        assert s == 200,             f"PVC-3: {s}"
        assert b.get("ok") is True,  f"PVC-3 ok: {b}"
        assert b.get("valid") is False, f"PVC-3 valid: {b}"
        assert b.get("cached") is False, f"PVC-3 cached: {b}"
        assert b.get("card_available") is True, f"PVC-3 card_available: {b}"

        # ── PVC-4: second call → cached=True ────────────────────────────────
        s, b = _get(hp, f"/peers/{peer_with_card}/verify-card")
        assert s == 200,                 f"PVC-4: {s}"
        assert b.get("cached") is True,  f"PVC-4 cached: {b}"
        assert "cache_expires_in" in b,  f"PVC-4 no expires_in: {b}"

        # ── PVC-5: force=1 bypasses cache ────────────────────────────────────
        s, b = _get(hp, f"/peers/{peer_with_card}/verify-card?force=1")
        assert s == 200,                  f"PVC-5: {s}"
        assert b.get("cached") is False,  f"PVC-5 cached: {b}"

        # ── PVC-6: ttl=0 behaves like force ──────────────────────────────────
        # First re-fill cache
        _get(hp, f"/peers/{peer_with_card}/verify-card")
        s, b = _get(hp, f"/peers/{peer_with_card}/verify-card?ttl=0")
        assert s == 200,                  f"PVC-6: {s}"
        assert b.get("cached") is False,  f"PVC-6 cached: {b}"

        # ── PVC-7: trust=1 + invalid card → trust_signal_written=False ───────
        s, b = _get(hp, f"/peers/{peer_with_card}/verify-card?trust=1")
        assert s == 200,                                f"PVC-7: {s}"
        assert b.get("trust_signal_written") is False,  f"PVC-7 trust_written: {b}"

        # ── PVC-8: response includes required fields ──────────────────────────
        s, b = _get(hp, f"/peers/{peer_with_card}/verify-card")
        assert s == 200, f"PVC-8: {s}"
        for field in ("ok", "peer_id", "name", "connected", "card_available"):
            assert field in b, f"PVC-8 missing {field}: {b}"
        assert b["peer_id"] == peer_with_card, f"PVC-8 peer_id: {b}"
        assert b["name"] == "AgentWithCard", f"PVC-8 name: {b}"
        assert b["card_available"] is True, f"PVC-8 card_available: {b}"

        # ── PVC-9: capabilities.peer_verify_card = True ───────────────────────
        with urllib.request.urlopen(f"http://127.0.0.1:{hp}/.well-known/acp.json", timeout=3) as r:
            acp_json = json.loads(r.read())
        card_self = acp_json.get("self") or acp_json
        caps = card_self.get("capabilities", {})
        assert caps.get("peer_verify_card") is True, f"PVC-9 caps: {caps}"

        # ── PVC-10: endpoints.peer_verify_card = /peers/{peer_id}/verify-card ─
        endpoints = card_self.get("endpoints", {})
        assert endpoints.get("peer_verify_card") == "/peers/{peer_id}/verify-card", \
            f"PVC-10 endpoints: {endpoints}"

    finally:
        proc.terminate()
        proc.wait(timeout=5)
