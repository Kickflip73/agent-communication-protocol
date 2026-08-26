"""
ACP v2.54 — POST /verify-card (v2) Tests
=========================================
VC2-1  … single mode — unsigned card (no card_sig) → valid=False
VC2-2  … single mode — second call → cached=True
VC2-3  … single mode — ttl=0 → cached=False (bypass cache)
VC2-4  … single mode — {card: <AgentCard>} wrapper accepted
VC2-5  … single mode — {self: <AgentCard>} wrapper accepted
VC2-6  … single mode — raw body (name/identity at root) accepted
VC2-7  … single mode — body with no recognisable card → 400
VC2-8  … batch mode  — 3 cards, counts match
VC2-9  … batch mode  — batch > 100 → 400
VC2-10 … batch mode  — non-list cards → 400
VC2-11 … batch mode  — non-dict card in list → valid=False, index recorded
VC2-12 … fetch mode  — bad URL → 422 ok=False
VC2-13 … fetch mode  — missing url → 400
VC2-14 … trust_integration — valid=False → trust_signal_written=False
VC2-15 … capabilities.verify_card_v2 = True
VC2-16 … endpoints.verify_card_v2 = /verify-card
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

# ── helpers ──────────────────────────────────────────────────────────────────

RELAY_PY = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")


def _start_relay(ws_port):
    http_port = ws_port + 100
    env = os.environ.copy()
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        env.pop(k, None)
    proc = subprocess.Popen(
        [sys.executable, RELAY_PY,
         "--port", str(ws_port), "--name", "VC2Relay",
         "--local-only", "--test-mode"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
    )
    for s in (proc.stdout, proc.stderr):
        threading.Thread(target=lambda x=s: x.read(), daemon=True).start()
    # wait ready
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
    req = urllib.request.Request(f"http://127.0.0.1:{hp}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


# ── cards used in tests ───────────────────────────────────────────────────────

CARD_UNSIGNED  = {"name": "Agent", "identity": {"scheme": "none"}}
CARD_NO_PUBKEY = {"name": "Agent", "identity": {"scheme": "ed25519"}}
CARD_BAD_SIG   = {"name": "Agent", "identity": {"scheme": "ed25519", "public_key": "AAAA", "card_sig": "BBBB"}}


# ── tests ─────────────────────────────────────────────────────────────────────

def test_vc2_1_to_16():
    """All VC2-1 through VC2-16 in a single relay fixture to minimise process overhead."""
    proc, hp = _start_relay(52500)
    try:
        # ── VC2-1: single — unsigned card ──────────────────────────────────
        s, b = _http("POST", hp, "/verify-card", {"card": CARD_UNSIGNED})
        assert s == 200, f"VC2-1: {s} {b}"
        assert b["ok"] is True,       f"VC2-1 ok: {b}"
        assert b["valid"] is False,   f"VC2-1 valid: {b}"
        assert b["cached"] is False,  f"VC2-1 cached: {b}"
        assert b["mode"] == "single", f"VC2-1 mode: {b}"

        # ── VC2-2: cached on second call ───────────────────────────────────
        s, b = _http("POST", hp, "/verify-card", {"card": CARD_UNSIGNED})
        assert s == 200, f"VC2-2: {s}"
        assert b["cached"] is True,                   f"VC2-2 cached: {b}"
        assert "cache_expires_in" in b,               f"VC2-2 no expires_in: {b}"
        assert b["cache_expires_in"] > 0,             f"VC2-2 expires_in<=0: {b}"

        # ── VC2-3: ttl=0 bypasses cache ────────────────────────────────────
        s, b = _http("POST", hp, "/verify-card", {"card": CARD_UNSIGNED, "ttl": 0})
        assert s == 200,              f"VC2-3: {s}"
        assert b["cached"] is False,  f"VC2-3 cached: {b}"

        # ── VC2-4: {card: ...} wrapper ─────────────────────────────────────
        s, b = _http("POST", hp, "/verify-card", {"card": CARD_NO_PUBKEY})
        assert s == 200,              f"VC2-4: {s}"
        assert b["ok"] is True,       f"VC2-4 ok: {b}"
        assert b["valid"] is False,   f"VC2-4 valid: {b}"

        # ── VC2-5: {self: ...} wrapper ─────────────────────────────────────
        s, b = _http("POST", hp, "/verify-card", {"self": CARD_NO_PUBKEY})
        assert s == 200,              f"VC2-5: {s}"
        assert b["ok"] is True,       f"VC2-5 ok: {b}"

        # ── VC2-6: raw body (identity at root) ─────────────────────────────
        s, b = _http("POST", hp, "/verify-card", CARD_BAD_SIG)
        assert s == 200,              f"VC2-6: {s}"
        assert b["ok"] is True,       f"VC2-6 ok: {b}"
        assert b["valid"] is False,   f"VC2-6 valid: {b}"

        # ── VC2-7: no recognisable card → 400 ──────────────────────────────
        s, b = _http("POST", hp, "/verify-card", {"mode": "single", "something": "else"})
        assert s == 400,              f"VC2-7: {s}"
        assert b.get("ok") is False,  f"VC2-7 ok: {b}"

        # ── VC2-8: batch — 3 cards, counts ────────────────────────────────
        s, b = _http("POST", hp, "/verify-card", {
            "mode": "batch",
            "cards": [CARD_UNSIGNED, CARD_NO_PUBKEY, CARD_BAD_SIG],
        })
        assert s == 200,                        f"VC2-8: {s}"
        assert b["ok"] is True,                 f"VC2-8 ok: {b}"
        assert b["mode"] == "batch",            f"VC2-8 mode: {b}"
        assert b["total"] == 3,                 f"VC2-8 total: {b}"
        assert b["valid_count"] == 0,           f"VC2-8 valid_count: {b}"
        assert b["invalid_count"] == 3,         f"VC2-8 invalid_count: {b}"
        assert len(b["results"]) == 3,          f"VC2-8 results len: {b}"
        assert b["results"][0]["index"] == 0,   f"VC2-8 index[0]: {b}"
        assert b["results"][2]["index"] == 2,   f"VC2-8 index[2]: {b}"

        # ── VC2-9: batch > 100 → 400 ──────────────────────────────────────
        s, b = _http("POST", hp, "/verify-card", {"mode": "batch", "cards": [{}] * 101})
        assert s == 400,              f"VC2-9: {s}"
        assert b.get("ok") is False,  f"VC2-9 ok: {b}"

        # ── VC2-10: batch cards not a list → 400 ──────────────────────────
        s, b = _http("POST", hp, "/verify-card", {"mode": "batch", "cards": "notalist"})
        assert s == 400,              f"VC2-10: {s}"

        # ── VC2-11: non-dict card in batch list ────────────────────────────
        s, b = _http("POST", hp, "/verify-card", {"mode": "batch", "cards": ["stringcard", {}]})
        assert s == 200,                        f"VC2-11: {s}"
        r0 = b["results"][0]
        assert r0["valid"] is False,            f"VC2-11 r0 valid: {r0}"
        assert r0["index"] == 0,                f"VC2-11 r0 index: {r0}"

        # ── VC2-12: fetch bad URL → 422 ────────────────────────────────────
        s, b = _http("POST", hp, "/verify-card", {"mode": "fetch", "url": "http://127.0.0.1:1/bad"})
        assert s == 422,              f"VC2-12: {s}"
        assert b.get("ok") is False,  f"VC2-12 ok: {b}"
        assert "error" in b,          f"VC2-12 error missing: {b}"

        # ── VC2-13: fetch missing url → 400 ───────────────────────────────
        s, b = _http("POST", hp, "/verify-card", {"mode": "fetch"})
        assert s == 400,              f"VC2-13: {s}"

        # ── VC2-14: trust_integration with invalid card → trust_signal_written=False ──
        s, b = _http("POST", hp, "/verify-card", {
            "card": CARD_UNSIGNED,
            "trust_integration": True,
            "peer_id": "peerXYZ",
        })
        assert s == 200,                              f"VC2-14: {s}"
        assert b.get("trust_signal_written") is False, f"VC2-14 trust_written: {b}"

        # ── VC2-15: capabilities.verify_card_v2 = True ────────────────────
        with urllib.request.urlopen(f"http://127.0.0.1:{hp}/.well-known/acp.json", timeout=3) as r:
            acp_json = json.loads(r.read())
        card_self = acp_json.get("self") or acp_json
        caps = card_self.get("capabilities", {})
        assert caps.get("verify_card_v2") is True, f"VC2-15 caps: {caps}"

        # ── VC2-16: endpoints.verify_card_v2 = /verify-card ───────────────
        endpoints = card_self.get("endpoints", {})
        assert endpoints.get("verify_card_v2") == "/verify-card", f"VC2-16 endpoints: {endpoints}"

    finally:
        proc.terminate()
        proc.wait(timeout=5)
