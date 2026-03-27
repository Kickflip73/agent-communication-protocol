#!/usr/bin/env python3
"""
ACP Scenario D — Stress Test
100 messages, concurrent sends, reconnect after disconnect
"""

import http.client as _http_client
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid

import pytest
from helpers import clean_subprocess_env

RELAY_PATH = os.path.join(os.path.dirname(__file__), '..', 'relay', 'acp_relay.py')


def _free_port():
    """Return an OS-assigned free port where port AND port+100 are both free."""
    for _ in range(200):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            ws = s.getsockname()[1]
        try:
            with socket.socket() as s2:
                s2.bind(("127.0.0.1", ws + 100))
                return ws
        except OSError:
            continue
    raise RuntimeError("Could not find a free port pair (ws + ws+100)")


# Dynamic ports — assigned at module import to avoid cross-file collisions
ALPHA_WS   = _free_port()
ALPHA_PORT = ALPHA_WS + 100
BETA_WS    = _free_port()
BETA_PORT  = BETA_WS + 100

# ── HTTP helpers ──────────────────────────────────────────────────────────────

def http_req(method, port, path, body=None):
    conn = _http_client.HTTPConnection("127.0.0.1", port, timeout=10)
    if body is not None:
        data = json.dumps(body).encode()
        headers = {"Content-Type": "application/json", "Content-Length": str(len(data))}
        conn.request(method, path, data, headers)
    else:
        conn.request(method, path)
    resp = conn.getresponse()
    raw = resp.read()
    try:
        return resp.status, json.loads(raw)
    except Exception:
        return resp.status, raw

def get(port, path):             return http_req("GET",  port, path)
def post(port, path, b=None):    return http_req("POST", port, path, b)

# ── Relay management ──────────────────────────────────────────────────────────

def _start_relay(ws_port, name, wait_link=False):
    http_port = ws_port + 100
    proc = subprocess.Popen(
        [sys.executable, RELAY_PATH, "--port", str(ws_port), "--name", name,
         "--inbox", f"/tmp/acp_stress_{name}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env=clean_subprocess_env(),
    )
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            conn = _http_client.HTTPConnection("127.0.0.1", http_port, timeout=1)
            conn.request("GET", "/status")
            resp = conn.getresponse()
            raw  = resp.read()
            if resp.status == 200:
                if not wait_link:
                    return proc
                # Also wait for the P2P link (public IP detection) to be ready
                import json as _json
                try:
                    data = _json.loads(raw)
                    if data.get("link"):
                        return proc
                except Exception:
                    pass
        except Exception:
            pass
        time.sleep(0.3)
    proc.kill()
    raise RuntimeError(f"Relay {name}:{ws_port} did not start within 60s")

def _stop_relay(proc):
    try:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=3)
    except Exception:
        proc.kill()

# ── Module-scope fixtures ─────────────────────────────────────────────────────

_PROCS    = []          # module-level relay procs
_PEER_ID  = [None]      # shared peer_id set during setup


@pytest.fixture(scope="module", autouse=True)
def relay_pair():
    """Start Alpha + Beta, establish P2P connection, share peer_id via _PEER_ID."""
    # Clean stale inbox files
    import glob
    for pattern in ["/tmp/acp_stress_StressAlpha*", "/tmp/acp_stress_StressBeta*"]:
        for f in glob.glob(pattern):
            try:
                os.remove(f)
            except OSError:
                pass

    proc_a = _start_relay(ALPHA_WS, "StressAlpha")
    proc_b = _start_relay(BETA_WS,  "StressBeta", wait_link=True)
    _PROCS.extend([proc_a, proc_b])

    # Beta link is guaranteed ready by wait_link=True in _start_relay
    s, r = get(BETA_PORT, "/status")
    beta_link = r.get("link") if isinstance(r, dict) else None
    assert beta_link, f"Beta link not available after relay startup: status={s}"

    s2, r2 = post(ALPHA_PORT, "/peers/connect", {"link": beta_link, "role": "agent"})
    assert s2 == 200 and r2.get("ok"), f"P2P connect failed: {s2} {r2}"
    _PEER_ID[0] = r2.get("peer_id")

    # Wait for WS to fully establish — check connected=True AND ws is ready (BUG-030 fix)
    # connected=True is set immediately by _register_peer(), but ws handshake may still be
    # in progress. Probe-send a test message to confirm the channel is truly ready.
    deadline = time.time() + 10
    peer_ready = False
    while time.time() < deadline:
        ps, pr = post(ALPHA_PORT, f"/peer/{_PEER_ID[0]}/send", {
            "role": "agent",
            "parts": [{"kind": "text", "text": "__probe__"}],
        })
        if ps == 200 and isinstance(pr, dict) and pr.get("ok"):
            peer_ready = True
            break
        time.sleep(0.3)
    assert peer_ready, f"Peer {_PEER_ID[0]} not ready within 10s (last: {ps} {pr})"

    yield

    for proc in _PROCS:
        _stop_relay(proc)
    _PROCS.clear()
    _PEER_ID[0] = None


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_d1_alpha_beta_startup():
    """D1: 两个 relay 启动且 AgentCard 正确"""
    s_a, r_a = get(ALPHA_PORT, "/.well-known/acp.json")
    s_b, r_b = get(BETA_PORT,  "/.well-known/acp.json")
    name_a = (r_a.get("self") or {}).get("name") if isinstance(r_a, dict) else None
    name_b = (r_b.get("self") or {}).get("name") if isinstance(r_b, dict) else None
    assert s_a == 200 and name_a == "StressAlpha", f"Alpha card: {s_a} {name_a}"
    assert s_b == 200 and name_b == "StressBeta",  f"Beta card: {s_b} {name_b}"


def test_d2_p2p_connect():
    """D2: Alpha 已连接 Beta，peer_id 已建立"""
    peer_id = _PEER_ID[0]
    assert peer_id, "peer_id not set — P2P connect failed in fixture"
    s, r = get(ALPHA_PORT, "/peers")
    peers = r.get("peers", []) if isinstance(r, dict) else (r if isinstance(r, list) else [])
    p = next((p for p in peers
              if p.get("id") == peer_id or p.get("peer_id") == peer_id), None)
    assert p is not None, f"peer {peer_id} not in /peers: {peers}"
    assert p.get("connected"), f"peer {peer_id} not connected: {p}"


def test_d3_100_sequential_messages():
    """D3: 顺序发送 100 条消息"""
    peer_id = _PEER_ID[0]
    assert peer_id, "peer_id not set"
    N = 100
    success = 0
    t0 = time.time()
    for i in range(N):
        mid = f"stress-seq-{i:03d}-{uuid.uuid4().hex[:8]}"
        s, r = post(ALPHA_PORT, f"/peer/{peer_id}/send", {
            "role": "agent",
            "parts": [{"kind": "text", "text": f"stress message #{i}"}],
            "message_id": mid,
        })
        if s == 200 and r.get("ok"):
            success += 1
    elapsed = time.time() - t0
    print(f"\n  D3: {success}/{N} OK in {elapsed:.2f}s ({N/elapsed:.0f} msg/s)")
    assert success == N, f"D3: only {success}/{N} messages sent successfully"


def test_d4_beta_received_100():
    """D4: StressBeta 收到 ≥100 条消息"""
    time.sleep(1.5)  # allow async delivery
    s, r = http_req("GET", BETA_PORT, "/recv?limit=200")
    if isinstance(r, dict):
        count     = r.get("count", len(r.get("messages", [])))
        remaining = r.get("remaining", 0)
    elif isinstance(r, list):
        count, remaining = len(r), 0
    else:
        count, remaining = 0, 0
    total = count + remaining
    assert total >= 100, f"D4: Beta received only {total} messages (count={count} remaining={remaining})"


def test_d5_idempotency():
    """D5: 同一 message_id 发 5 次，全部 ok=true（幂等）"""
    peer_id = _PEER_ID[0]
    assert peer_id
    mid = f"idempotent-{uuid.uuid4().hex[:8]}"
    for attempt in range(5):
        s, r = post(ALPHA_PORT, f"/peer/{peer_id}/send", {
            "role": "agent",
            "parts": [{"kind": "text", "text": "idempotent test"}],
            "message_id": mid,
        })
        assert s == 200 and r.get("ok"), f"D5 attempt {attempt}: status={s} resp={r}"


def test_d6_concurrent_sends():
    """D6: 并发发送 20 条消息"""
    peer_id = _PEER_ID[0]
    assert peer_id
    N = 20
    success_count = [0]
    lock = threading.Lock()

    def send_one(i):
        mid = f"concurrent-{i:03d}-{uuid.uuid4().hex[:8]}"
        s, r = post(ALPHA_PORT, f"/peer/{peer_id}/send", {
            "role": "agent",
            "parts": [{"kind": "text", "text": f"concurrent #{i}"}],
            "message_id": mid,
        })
        if s == 200 and r.get("ok"):
            with lock:
                success_count[0] += 1

    threads = [threading.Thread(target=send_one, args=(i,)) for i in range(N)]
    t0 = time.time()
    for t in threads: t.start()
    for t in threads: t.join()
    elapsed = time.time() - t0
    print(f"\n  D6: {success_count[0]}/{N} OK in {elapsed:.2f}s")
    assert success_count[0] == N, f"D6: only {success_count[0]}/{N} concurrent sends succeeded"


def test_d7_disconnect_and_reconnect():
    """D7: 无效 link 连接失败后 relay 仍然存活"""
    s, r = post(ALPHA_PORT, "/peers/connect", {
        "link": "acp://invalid-link-for-test",
        "role": "agent",
    })
    # Invalid link should be rejected (400) or fail gracefully
    alive_s, _ = get(ALPHA_PORT, "/.well-known/acp.json")
    assert alive_s == 200, f"D7: Alpha relay died after invalid connect (alive_s={alive_s})"


def test_d8_large_message():
    """D8: 超大消息（>1MB）应被拒绝（400/413）"""
    peer_id = _PEER_ID[0]
    assert peer_id
    big_text = "X" * (1100 * 1024)  # 1.1 MB
    s, r = post(ALPHA_PORT, f"/peer/{peer_id}/send", {
        "role": "agent",
        "parts": [{"kind": "text", "text": big_text}],
        "message_id": f"large-{uuid.uuid4().hex[:8]}",
    })
    assert s in (400, 413), f"D8: expected 400/413 for large message, got {s}"


def test_d9_malformed_json():
    """D9: 非法 JSON body 返回 400（BUG-011 回归）"""
    conn = _http_client.HTTPConnection("127.0.0.1", ALPHA_PORT, timeout=5)
    conn.request("POST", "/message:send", b"not_json",
                 {"Content-Type": "application/json"})
    resp = conn.getresponse()
    resp.read()
    assert resp.status in (400, 422), f"D9: expected 400/422, got {resp.status}"


def test_d10_peer_stats():
    """D10: per-peer messages_sent ≥ 100 (D3 sent 100+)"""
    peer_id = _PEER_ID[0]
    assert peer_id
    s, r = get(ALPHA_PORT, "/peers")
    peers = r.get("peers", []) if isinstance(r, dict) else (r if isinstance(r, list) else [])
    target = next((p for p in peers
                   if p.get("id") == peer_id or p.get("peer_id") == peer_id), None)
    assert target is not None, f"D10: peer {peer_id} not in /peers"
    sent = target.get("messages_sent", 0)
    assert sent >= 100, f"D10: messages_sent={sent} < 100"


# ── Standalone entry ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import glob
    for pattern in ["/tmp/acp_stress_StressAlpha*", "/tmp/acp_stress_StressBeta*"]:
        for f in glob.glob(pattern):
            try: os.remove(f)
            except OSError: pass

    proc_a = _start_relay(ALPHA_WS, "StressAlpha")
    proc_b = _start_relay(BETA_WS,  "StressBeta", wait_link=True)
    try:
        s, r  = get(BETA_PORT, "/status")
        beta_link = r.get("link") if isinstance(r, dict) else None
        s2, r2 = post(ALPHA_PORT, "/peers/connect", {"link": beta_link, "role": "agent"})
        _PEER_ID[0] = r2.get("peer_id")
        time.sleep(2)

        tests = [
            test_d1_alpha_beta_startup,
            test_d2_p2p_connect,
            test_d3_100_sequential_messages,
            test_d4_beta_received_100,
            test_d5_idempotency,
            test_d6_concurrent_sends,
            test_d7_disconnect_and_reconnect,
            test_d8_large_message,
            test_d9_malformed_json,
            test_d10_peer_stats,
        ]
        passed = 0
        for fn in tests:
            try:
                fn()
                print(f"✅ {fn.__name__}")
                passed += 1
            except AssertionError as e:
                print(f"❌ {fn.__name__}: {e}")
        print(f"\n{'='*50}\nRESULT: {passed}/{len(tests)} PASS")
    finally:
        _stop_relay(proc_a)
        _stop_relay(proc_b)
