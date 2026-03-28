#!/usr/bin/env python3
"""
ACP Scenario D — Stress Test
100 messages, concurrent sends, reconnect after disconnect

BUG-043 fix (2026-03-28): Replaced wait_link=True / /peers/connect P2P mode with
host+guest --join mode (same as BUG-038 reconnect fix).
Root cause: /peers/connect triggers _connect_with_nat_traversal Level-1 test WS,
which races with guest_mode's actual WS and is rejected by BUG-041 dedup (BUG-042).
In sandbox there's no public IP so link=null and wait_link never returns.
Fix: Alpha starts in host mode (stdout=PIPE), captures tok_xxx via stdout/HTTP,
Beta starts with --join acp://127.0.0.1:<alpha_ws>/<token> (direct guest_mode call).
"""

import http.client as _http_client
import json
import os
import re
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

def _start_relay_host(ws_port, name):
    """Start relay in host mode (WS server). Returns (proc, stdout_pipe)."""
    http_port = ws_port + 100
    proc = subprocess.Popen(
        [sys.executable, "-u", RELAY_PATH,
         "--port", str(ws_port), "--name", name,
         "--http-host", "127.0.0.1",
         "--inbox", f"/tmp/acp_stress_{name}"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, bufsize=1,
        env=clean_subprocess_env(),
    )
    # Wait for HTTP to be ready (no need to wait for public IP)
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            conn = _http_client.HTTPConnection("127.0.0.1", http_port, timeout=1)
            conn.request("GET", "/status")
            resp = conn.getresponse()
            resp.read()
            if resp.status == 200:
                return proc
        except Exception:
            pass
        time.sleep(0.3)
    proc.kill()
    raise RuntimeError(f"Host relay {name}:{ws_port} did not start within 60s")


def _wait_host_link(proc, http_port, timeout=60):
    """
    Wait for host relay to emit acp:// link (stdout + HTTP fallback).
    Returns 'acp://127.0.0.1:<ws_port>/tok_xxx' or None.
    Handles both public-IP and local-IP link formats.
    """
    token_holder = {"link": None}
    lock = threading.Lock()

    def _stdout_reader():
        try:
            for line in proc.stdout:
                m = re.search(r"acp://[^\s/]+:(\d+)/(tok_[a-f0-9]+)", line)
                if m and not token_holder["link"]:
                    with lock:
                        token_holder["link"] = f"acp://127.0.0.1:{m.group(1)}/{m.group(2)}"
        except Exception:
            pass

    t = threading.Thread(target=_stdout_reader, daemon=True)
    t.start()

    deadline = time.time() + timeout
    while time.time() < deadline:
        with lock:
            if token_holder["link"]:
                return token_holder["link"]
        for endpoint in ("/link", "/status"):
            try:
                conn = _http_client.HTTPConnection("127.0.0.1", http_port, timeout=2)
                conn.request("GET", endpoint)
                resp = conn.getresponse()
                raw = resp.read()
                if resp.status == 200:
                    d = json.loads(raw)
                    raw_link = d.get("link") or ""
                    if raw_link:
                        local = re.sub(r"acp://[^:]+:", "acp://127.0.0.1:", raw_link)
                        with lock:
                            token_holder["link"] = local
                        return local
            except Exception:
                pass
        time.sleep(0.3)
    return None


def _start_relay_guest(ws_port, name, join_link):
    """Start relay in guest mode (--join <link>). Directly calls guest_mode()."""
    http_port = ws_port + 100
    proc = subprocess.Popen(
        [sys.executable, "-u", RELAY_PATH,
         "--port", str(ws_port), "--name", name,
         "--http-host", "127.0.0.1",
         "--inbox", f"/tmp/acp_stress_{name}",
         "--join", join_link],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, bufsize=1,
        env=clean_subprocess_env(),
    )
    # Wait for HTTP to be ready
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            conn = _http_client.HTTPConnection("127.0.0.1", http_port, timeout=1)
            conn.request("GET", "/status")
            resp = conn.getresponse()
            resp.read()
            if resp.status == 200:
                return proc
        except Exception:
            pass
        time.sleep(0.3)
    proc.kill()
    raise RuntimeError(f"Guest relay {name}:{ws_port} did not start within 30s")


def _wait_connected(http_port, timeout=20):
    """Poll /status until connected=True or peer_count >= 1."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            conn = _http_client.HTTPConnection("127.0.0.1", http_port, timeout=2)
            conn.request("GET", "/status")
            resp = conn.getresponse()
            raw = resp.read()
            if resp.status == 200:
                d = json.loads(raw)
                if d.get("connected") is True or d.get("peer_count", 0) >= 1:
                    return True
        except Exception:
            pass
        time.sleep(0.3)
    return False

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
    """
    Start Alpha (host) + Beta (guest --join Alpha), share peer_id via _PEER_ID.

    BUG-043 fix: Use host+guest --join mode instead of /peers/connect P2P mode.
    Alpha starts as host (emits acp:// token via stdout/HTTP).
    Beta starts with --join acp://127.0.0.1:<alpha_ws>/<token>, directly calling
    guest_mode() without NAT traversal (no Level-1 test WS, no BUG-042 race).
    """
    import glob
    for pattern in ["/tmp/acp_stress_StressAlpha*", "/tmp/acp_stress_StressBeta*"]:
        for f in glob.glob(pattern):
            try:
                os.remove(f)
            except OSError:
                pass

    proc_a = _start_relay_host(ALPHA_WS, "StressAlpha")
    _PROCS.append(proc_a)

    # Wait for Alpha to emit its acp:// link (token)
    alpha_link = _wait_host_link(proc_a, ALPHA_PORT, timeout=60)
    assert alpha_link, "StressAlpha did not produce acp:// link within 60s"

    # Start Beta in guest mode (--join Alpha's link)
    proc_b = _start_relay_guest(BETA_WS, "StressBeta", alpha_link)
    _PROCS.append(proc_b)

    # Wait for both sides to report connected
    alpha_conn = _wait_connected(ALPHA_PORT, timeout=20)
    beta_conn  = _wait_connected(BETA_PORT,  timeout=20)
    assert alpha_conn, "StressAlpha did not become connected within 20s"
    assert beta_conn,  "StressBeta did not become connected within 20s"

    # Discover peer_id from Alpha's /peers list
    s, r = get(ALPHA_PORT, "/peers")
    peers = r.get("peers", []) if isinstance(r, dict) else (r if isinstance(r, list) else [])
    connected_peers = [p for p in peers if p.get("connected")]
    assert connected_peers, f"No connected peer found on Alpha after connect: {peers}"
    _PEER_ID[0] = connected_peers[0].get("id") or connected_peers[0].get("peer_id")
    assert _PEER_ID[0], f"Could not determine peer_id from Alpha peers: {connected_peers}"

    # Probe-send to confirm WS channel is truly ready
    deadline = time.time() + 15
    peer_ready = False
    ps, pr = None, None
    while time.time() < deadline:
        ps, pr = post(ALPHA_PORT, f"/peer/{_PEER_ID[0]}/send", {
            "role": "agent",
            "parts": [{"kind": "text", "text": "__probe__"}],
        })
        if ps == 200 and isinstance(pr, dict) and pr.get("ok"):
            peer_ready = True
            break
        time.sleep(0.3)
    assert peer_ready, f"Peer {_PEER_ID[0]} not ready within 15s (last: {ps} {pr})"

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

    proc_a = _start_relay_host(ALPHA_WS, "StressAlpha")
    alpha_link = _wait_host_link(proc_a, ALPHA_PORT, timeout=60)
    assert alpha_link, "Alpha did not produce acp:// link"
    proc_b = _start_relay_guest(BETA_WS, "StressBeta", alpha_link)
    try:
        assert _wait_connected(ALPHA_PORT, 20), "Alpha not connected"
        assert _wait_connected(BETA_PORT,  20), "Beta not connected"
        s, r = get(ALPHA_PORT, "/peers")
        peers = r.get("peers", []) if isinstance(r, dict) else []
        connected_peers = [p for p in peers if p.get("connected")]
        _PEER_ID[0] = connected_peers[0].get("id") or connected_peers[0].get("peer_id")
        time.sleep(1)

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
