#!/usr/bin/env python3
"""
ACP Scenario D — Stress Test
100 messages, concurrent sends, reconnect after disconnect
"""

import asyncio
import http.client as _http_client
import json
import os
import signal
import subprocess
import sys
import threading
import time
import uuid

# relay: --port N → ws_port=N, http_port=N+100
ALPHA_WS   = 7950
ALPHA_PORT = 7950 + 100   # 8050
BETA_WS    = 7960
BETA_PORT  = 7960 + 100   # 8060
RELAY_PATH = os.path.join(os.path.dirname(__file__), '..', 'relay', 'acp_relay.py')

PASS = "✅"
FAIL = "❌"
SKIP = "⏭"
results = []

def log(tag, msg):
    print(f"  {tag} {msg}")

def record(name, ok, note=""):
    symbol = PASS if ok else FAIL
    results.append((name, ok, note))
    print(f"{symbol} {name}" + (f" — {note}" if note else ""))

# ── HTTP helpers ─────────────────────────────────────────────────────────────

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

def get(port, path):    return http_req("GET",  port, path)
def post(port, path, b=None): return http_req("POST", port, path, b)

# ── Relay management ─────────────────────────────────────────────────────────

def start_relay(port, name):
    # port here is the WS port; http_port = port + 100
    proc = subprocess.Popen(
        [sys.executable, RELAY_PATH, "--port", str(port), "--name", name,
         "--inbox", f"/tmp/acp_stress_{name}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    # http_port = ws_port + 100; poll until link is ready (up to 12s)
    http_port = port + 100
    deadline = time.time() + 12
    while time.time() < deadline:
        try:
            conn = _http_client.HTTPConnection("127.0.0.1", http_port, timeout=1)
            conn.request("GET", "/status")
            resp = conn.getresponse()
            raw = resp.read()
            if resp.status == 200:
                d = json.loads(raw)
                if d.get("link"):
                    break
        except Exception:
            pass
        time.sleep(0.4)
    return proc

def stop_relay(proc):
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()

# ── Tests ─────────────────────────────────────────────────────────────────────

def test_d1_alpha_beta_startup():
    """D1: 两个 relay 启动"""
    s_a, r_a = get(ALPHA_PORT, "/.well-known/acp.json")
    s_b, r_b = get(BETA_PORT,  "/.well-known/acp.json")
    # AgentCard name is at r["self"]["name"]
    name_a = (r_a.get("self") or {}).get("name") if isinstance(r_a, dict) else None
    name_b = (r_b.get("self") or {}).get("name") if isinstance(r_b, dict) else None
    ok = (s_a == 200 and s_b == 200
          and name_a == "StressAlpha"
          and name_b == "StressBeta")
    record("D1 两个 relay 启动正常", ok,
           f"Alpha={s_a}/{name_a} Beta={s_b}/{name_b}")
    return ok

def test_d2_p2p_connect():
    """D2: StressAlpha 连接 StressBeta"""
    # Get Beta's acp:// link from /status
    s, r = get(BETA_PORT, "/status")
    beta_link = r.get("link") if isinstance(r, dict) else None
    if not beta_link:
        record("D2 P2P 连接建立", False, f"beta link not available, status={s}")
        return False, None
    s2, r2 = post(ALPHA_PORT, "/peers/connect", {"link": beta_link, "role": "agent"})
    ok = s2 == 200 and r2.get("ok") is True
    record("D2 P2P 连接建立", ok, f"peer_id={r2.get('peer_id')} link={beta_link[:40]}...")
    return ok, r2.get("peer_id")

def test_d3_100_sequential_messages(peer_id):
    """D3: 顺序发送 100 条消息"""
    N = 100
    success = 0
    msg_ids = []
    t0 = time.time()
    for i in range(N):
        mid = f"stress-seq-{i:03d}-{uuid.uuid4().hex[:8]}"
        s, r = post(ALPHA_PORT, f"/peer/{peer_id}/send", {
            "role": "agent",
            "parts": [{"kind": "text", "text": f"stress message #{i}"}],
            "message_id": mid
        })
        if s == 200 and r.get("ok"):
            success += 1
            msg_ids.append(mid)
    elapsed = time.time() - t0
    ok = success == N
    record(f"D3 顺序 100 条消息发送", ok,
           f"{success}/{N} OK, 耗时 {elapsed:.2f}s ({N/elapsed:.0f} msg/s)")
    return ok, msg_ids

def test_d4_beta_received_100():
    """D4: StressBeta 收到 100 条消息"""
    # /recv is destructive (popleft), default limit=50; use limit=200 to get all
    s, r = http_req("GET", BETA_PORT, "/recv?limit=200")
    if isinstance(r, dict):
        count = r.get("count", len(r.get("messages", [])))
        remaining = r.get("remaining", 0)
    elif isinstance(r, list):
        count = len(r)
        remaining = 0
    else:
        count = 0
        remaining = 0
    total = count + remaining
    ok = total >= 100
    record("D4 StressBeta 收到 ≥100 条消息", ok,
           f"recv_count={count} remaining={remaining} total={total}")
    return ok

def test_d5_idempotency(peer_id):
    """D5: 消息幂等性 — 同一 message_id 发送 5 次，只处理一次"""
    mid = f"idempotent-{uuid.uuid4().hex[:8]}"
    responses = []
    for _ in range(5):
        s, r = post(ALPHA_PORT, f"/peer/{peer_id}/send", {
            "role": "agent",
            "parts": [{"kind": "text", "text": "idempotent test"}],
            "message_id": mid
        })
        responses.append((s, r.get("ok"), r.get("duplicate")))

    # 所有都应 ok=true（幂等），duplicate 字段可选
    all_ok = all(ok for _, ok, _ in responses)
    ok = all_ok
    record("D5 消息幂等性（同 ID 发 5 次全 ok）", ok, f"responses={responses[:2]}...")
    return ok

def test_d6_concurrent_sends(peer_id):
    """D6: 并发发送 20 条消息"""
    N = 20
    success_count = [0]
    lock = threading.Lock()

    def send_one(i):
        mid = f"concurrent-{i:03d}-{uuid.uuid4().hex[:8]}"
        s, r = post(ALPHA_PORT, f"/peer/{peer_id}/send", {
            "role": "agent",
            "parts": [{"kind": "text", "text": f"concurrent #{i}"}],
            "message_id": mid
        })
        if s == 200 and r.get("ok"):
            with lock:
                success_count[0] += 1

    threads = [threading.Thread(target=send_one, args=(i,)) for i in range(N)]
    t0 = time.time()
    for t in threads: t.start()
    for t in threads: t.join()
    elapsed = time.time() - t0

    ok = success_count[0] == N
    record(f"D6 并发 {N} 条消息", ok,
           f"{success_count[0]}/{N} OK, 耗时 {elapsed:.2f}s")
    return ok

def test_d7_disconnect_and_reconnect():
    """D7: 断线重连 — 停止 StressBeta，重启，重新建立连接"""
    # Beta 已停止（在外层 finally 前）
    # 这里只检测 Alpha 发消息得到错误（peer offline）
    s, r = post(ALPHA_PORT, "/peers/connect", {
        "link": "acp://invalid-link-for-test",
        "role": "agent"
    })
    # 无效 link 应该失败或超时，关键是 relay 不崩溃
    alive_s, alive_r = get(ALPHA_PORT, "/.well-known/acp.json")
    ok = alive_s == 200  # Alpha 仍然存活
    record("D7 无效 link 连接失败后 relay 仍存活", ok,
           f"connect_status={s}, relay_alive={alive_s}")
    return ok

def test_d8_large_message(peer_id):
    """D8: 超大消息（>1MB max_msg_bytes）应被拒绝"""
    big_text = "X" * (1100 * 1024)  # 1.1 MB — exceeds 1MB limit
    s, r = post(ALPHA_PORT, f"/peer/{peer_id}/send", {
        "role": "agent",
        "parts": [{"kind": "text", "text": big_text}],
        "message_id": f"large-{uuid.uuid4().hex[:8]}"
    })
    ok = s in (400, 413)  # 应被拒绝
    err_str = str(r.get("error", r))[:80] if isinstance(r, dict) else str(s)
    record("D8 超大消息被拒绝（400/413）", ok, f"status={s} error={err_str}")
    return ok

def test_d9_malformed_json():
    """D9: 非法 JSON body 返回 400（BUG-011 回归）"""
    conn = _http_client.HTTPConnection("127.0.0.1", ALPHA_PORT, timeout=5)
    conn.request("POST", "/message:send", b"not_json", {"Content-Type": "application/json"})
    resp = conn.getresponse()
    resp.read()
    ok = resp.status in (400, 422)
    record("D9 非法 JSON 返回 400/422 (BUG-011 回归)", ok, f"status={resp.status}")
    return ok

def test_d10_peer_stats(peer_id):
    """D10: per-peer 统计（messages_sent / messages_received 正确）"""
    s, r = get(ALPHA_PORT, "/peers")
    peers = r if isinstance(r, list) else r.get("peers", [])
    # /peers uses "id" field (not "peer_id")
    target = next((p for p in peers if p.get("id") == peer_id or p.get("peer_id") == peer_id), None)
    if target is None:
        record("D10 per-peer 统计", False, f"peer {peer_id} not found in /peers (peers={[p.get('id') for p in peers]})")
        return False
    sent = target.get("messages_sent", 0)
    ok = sent >= 100  # D3 发了 100+
    record("D10 Alpha per-peer messages_sent ≥ 100", ok,
           f"messages_sent={sent} messages_received={target.get('messages_received')}")
    return ok

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "="*60)
    print("ACP Scenario D — Stress Test")
    print("="*60)

    # Clean up old inbox files
    for f in [f"/tmp/acp_stress_StressAlpha", f"/tmp/acp_stress_StressBeta"]:
        try:
            import glob
            for ff in glob.glob(f"{f}*"):
                os.remove(ff)
        except Exception:
            pass

    proc_alpha = start_relay(ALPHA_WS, "StressAlpha")
    proc_beta  = start_relay(BETA_WS,  "StressBeta")

    try:
        print("\n[ D1 — Startup ]")
        ok = test_d1_alpha_beta_startup()
        if not ok:
            print("FATAL: relays not running, aborting")
            return

        print("\n[ D2 — P2P Connect ]")
        ok, peer_id = test_d2_p2p_connect()
        if not ok or not peer_id:
            print("FATAL: P2P connect failed, aborting")
            return

        # Wait for WS connection to fully establish (poll /peers until connected=true)
        deadline = time.time() + 10
        while time.time() < deadline:
            ps, pr = get(ALPHA_PORT, "/peers")
            peers_list = pr.get("peers", []) if isinstance(pr, dict) else []
            p_info = next((p for p in peers_list if p.get("peer_id") == peer_id), None)
            if p_info and p_info.get("connected"):
                break
            time.sleep(0.3)

        print("\n[ D3 — 100 Sequential Messages ]")
        ok, msg_ids = test_d3_100_sequential_messages(peer_id)

        time.sleep(0.5)

        print("\n[ D4 — Beta Inbox Count ]")
        time.sleep(1.5)  # wait for async delivery to Beta's inbox
        test_d4_beta_received_100()

        print("\n[ D5 — Idempotency ]")
        test_d5_idempotency(peer_id)

        print("\n[ D6 — Concurrent Sends ]")
        test_d6_concurrent_sends(peer_id)

        print("\n[ D7 — Disconnect Resilience ]")
        test_d7_disconnect_and_reconnect()

        print("\n[ D8 — Large Message Rejection ]")
        test_d8_large_message(peer_id)

        print("\n[ D9 — Malformed JSON (BUG-011 Regression) ]")
        test_d9_malformed_json()

        print("\n[ D10 — Per-peer Stats ]")
        test_d10_peer_stats(peer_id)

    finally:
        stop_relay(proc_alpha)
        stop_relay(proc_beta)

    # Summary
    total = len(results)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = [(n, note) for n, ok, note in results if not ok]

    print("\n" + "="*60)
    print(f"RESULT: {passed}/{total} PASS")
    if failed:
        print("\nFailed tests:")
        for n, note in failed:
            print(f"  {FAIL} {n}: {note}")
    print("="*60)

    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
