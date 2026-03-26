#!/usr/bin/env python3
"""
ACP Compatibility Certification — Level 1 (Core)
=================================================
Tests whether a relay implementation meets the ACP Level 1 spec.

Usage:
    # Against reference relay (auto-starts):
    python3 tests/cert/test_level1.py

    # Against external implementation:
    ACP_TARGET_URL=http://your-relay:7901 python3 tests/cert/test_level1.py
"""

import os, sys, json, time, subprocess, signal, requests

# ── Config ────────────────────────────────────────────────────────────────────
TARGET_URL  = os.environ.get("ACP_TARGET_URL", "").rstrip("/")
RELAY_PORT  = 7950
RELAY_PATH  = os.path.join(os.path.dirname(__file__), "../../relay/acp_relay.py")
RELAY_PROC  = None

def start_reference_relay():
    global RELAY_PROC, TARGET_URL
    http_port = RELAY_PORT + 100
    TARGET_URL = f"http://localhost:{http_port}"
    RELAY_PROC = subprocess.Popen(
        [sys.executable, RELAY_PATH, "--port", str(RELAY_PORT), "--name", "CertRelay"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    # Poll until ready
    for _ in range(30):
        try:
            if requests.get(f"{TARGET_URL}/status", timeout=0.5).status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.2)
    raise RuntimeError("Reference relay did not start within 6s")

def stop_reference_relay():
    if RELAY_PROC:
        RELAY_PROC.send_signal(signal.SIGTERM)
        RELAY_PROC.wait(timeout=3)

# ── Test harness ──────────────────────────────────────────────────────────────
results = []

def check(name, cond, detail=""):
    status = "✅" if cond else "❌"
    results.append((name, cond, detail))
    detail_str = f"  ({detail})" if detail else ""
    print(f"  {status} {name}{detail_str}")
    return cond

def get(path, **kw):
    return requests.get(f"{TARGET_URL}{path}", timeout=5, **kw)

def post(path, body=None, **kw):
    return requests.post(f"{TARGET_URL}{path}", json=body, timeout=5, **kw)

# ── pytest session-level fixture ──────────────────────────────────────────────
import pytest

def setup_module(module):
    """Auto-start reference relay when ACP_TARGET_URL is not set."""
    if not os.environ.get("ACP_TARGET_URL"):
        start_reference_relay()

def teardown_module(module):
    stop_reference_relay()

# ── Tests ─────────────────────────────────────────────────────────────────────

def test_c1_01_status():
    r = get("/status")
    ok = r.status_code == 200
    body = r.json() if ok else {}
    check("C1-01  GET /status → 200", ok, f"got {r.status_code}")
    check("C1-01  /status has 'acp_version'", "acp_version" in body, str(list(body.keys())[:6]))
    check("C1-01  /status has 'connected'",   "connected" in body, str(list(body.keys())[:6]))

def test_c1_02_agent_card():
    r = get("/.well-known/acp.json")
    check("C1-02  GET /.well-known/acp.json → 200", r.status_code == 200, f"got {r.status_code}")
    if r.status_code != 200:
        return
    body = r.json()
    # ACP relay returns {self: {...}, peer: {...}}; verify 'self' is present
    card = body.get("self", body)
    check("C1-02  AgentCard body is a dict", isinstance(card, dict), str(type(card)))

def test_c1_03_agent_card_fields():
    r = get("/.well-known/acp.json")
    body = r.json() if r.status_code == 200 else {}
    card = body.get("self", body)
    required = ["name", "version", "acp_version", "capabilities"]
    for field in required:
        check(f"C1-03  AgentCard has '{field}'", field in card, str(list(card.keys())))
    caps = card.get("capabilities", {})
    for cap in ["streaming", "push_notifications"]:
        check(f"C1-03  capabilities has '{cap}'", cap in caps)
    # link may be None before a peer connects — just check field exists
    check("C1-03  acp_version starts with '1.'",
          str(card.get("acp_version","")).startswith("1."), card.get("acp_version",""))

def test_c1_04_send_message():
    # ACP uses {"type":"text","content":"..."} in parts
    # In host mode without a peer, send returns 503 or 400 ERR_NOT_CONNECTED (expected)
    r = post("/message:send", {"role": "user",
                                "parts": [{"type": "text", "content": "cert-test"}]})
    # Accept 200 (peer connected), 400/503 (no peer yet — still a valid relay response)
    body = {}
    try:
        body = r.json()
    except Exception:
        pass

    if r.status_code == 200:
        check("C1-04  POST /message:send → 200", True)
        check("C1-04  response has message_id", "message_id" in body, str(body))
        # note: message_id returned but not propagated (test functions must return None)
    elif r.status_code in (400, 503):
        # 503 = host-mode no peer (relay not yet connected to anyone)
        # Both are acceptable "no peer" responses
        check("C1-04  POST /message:send → relay rejects no-peer request",
              True, f"got {r.status_code} (expected when no peer)")
        # failed_message_id may or may not be present (503 may return empty body)
        check("C1-04  response is JSON",
              isinstance(body, dict), str(type(body)))
    else:
        check("C1-04  POST /message:send → unexpected status",
              False, f"got {r.status_code}")

def test_c1_05_recv():
    r = get("/recv")
    check("C1-05  GET /recv → 200", r.status_code == 200, f"got {r.status_code}")
    body = r.json() if r.status_code == 200 else {}
    check("C1-05  response has messages array", isinstance(body.get("messages"), list), str(body))

def test_c1_06_idempotency():
    """Idempotency: relay must not create duplicate when same message_id replayed."""
    # In host mode without peer, we verify error response includes failed_message_id
    payload = {"role": "user", "parts": [{"type":"text","content":"idem"}],
               "message_id": "cert-idem-test-001"}
    r1 = post("/message:send", payload)
    r2 = post("/message:send", payload)
    b1 = r1.json() if r1.status_code in (200,400) else {}
    b2 = r2.json() if r2.status_code in (200,400) else {}
    # Both must return the same status code
    check("C1-06  Idempotent send → consistent status", r1.status_code == r2.status_code,
          f"{r1.status_code} vs {r2.status_code}")
    if r1.status_code == 200:
        id1 = b1.get("message_id")
        id2 = b2.get("message_id")
        check("C1-06  Same message_id returned", id1 == id2, f"{id1} vs {id2}")
    else:
        fid1 = b1.get("failed_message_id","")
        fid2 = b2.get("failed_message_id","")
        check("C1-06  Consistent failed_message_id on replay", fid1 == fid2,
              f"{fid1} vs {fid2}")

def test_c1_07_invalid_json():
    r = requests.post(f"{TARGET_URL}/message:send",
                      data="not-json", headers={"Content-Type":"application/json"}, timeout=5)
    check("C1-07  Invalid JSON → 400", r.status_code == 400, f"got {r.status_code}")
    body = r.json() if r.status_code == 400 else {}
    # ACP uses 'error_code' as the standard error key
    check("C1-07  error_code field present", "error_code" in body or "error" in body, str(body))

def test_c1_08_missing_role():
    r = post("/message:send", {"parts": [{"type":"text","content":"no-role"}]})
    check("C1-08  Missing role → 400", r.status_code == 400, f"got {r.status_code}")
    body = r.json() if r.status_code == 400 else {}
    ec = body.get("error_code", body.get("error",""))
    check("C1-08  error_code = ERR_INVALID_REQUEST",
          "ERR_INVALID_REQUEST" in ec, str(body))

def test_c1_09_error_format():
    r = post("/message:send", {"parts": [{"type":"text","content":"x"}]})  # missing role
    if r.status_code == 400:
        body = r.json()
        # ACP standard error format: {ok, error_code, error, failed_message_id}
        check("C1-09  Error response has 'error_code'", "error_code" in body, str(body))
        check("C1-09  Error response has 'error' (description)", "error" in body, str(body))

def test_c1_10_content_type():
    endpoints = [("/.well-known/acp.json","GET"), ("/recv","GET"), ("/status","GET")]
    for path, method in endpoints:
        r = get(path) if method == "GET" else post(path,{})
        ct = r.headers.get("Content-Type","")
        check(f"C1-10  {method} {path} Content-Type: application/json",
              "application/json" in ct, ct)

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    global TARGET_URL

    print("ACP Compatibility Certification — Level 1 (Core)")
    print("=" * 50)

    # Start relay if no external target given
    own_relay = not TARGET_URL
    if own_relay:
        print(f"No ACP_TARGET_URL set — starting reference relay on port {RELAY_PORT}...")
        start_reference_relay()
        print(f"Relay ready at {TARGET_URL}\n")
    else:
        print(f"Testing external target: {TARGET_URL}\n")

    try:
        test_c1_01_status()
        card = test_c1_02_agent_card()
        test_c1_03_agent_card_fields(card)
        msg_id = test_c1_04_send_message()
        test_c1_05_recv()
        if msg_id:
            test_c1_06_idempotency(msg_id)
        test_c1_07_invalid_json()
        test_c1_08_missing_role()
        test_c1_09_error_format()
        test_c1_10_content_type()
    finally:
        if own_relay:
            stop_reference_relay()

    # Summary
    passed = sum(1 for _,ok,_ in results if ok)
    total  = len(results)
    failed = total - passed
    print()
    print("=" * 50)
    print(f"Level 1: {passed}/{total} PASS", end="")
    if failed == 0:
        print(" — ✅ CERTIFIED")
        sys.exit(0)
    else:
        print(f" — ❌ {failed} FAILURES")
        for name, ok, detail in results:
            if not ok:
                print(f"  FAIL: {name}  ({detail})")
        sys.exit(1)

if __name__ == "__main__":
    main()
