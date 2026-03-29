#!/usr/bin/env python3
"""
tests/run_scenario_ab_test.py
==============================
場景 A + 場景 B 完整測試腳本（subprocess 啟動 relay，HTTP 驗證）

端口規劃（HTTP = WS + 100）：
  場景 A：Alpha WS=7910 HTTP=8010, Beta WS=7920 HTTP=8020
  場景 B：Orchestrator WS=7930 HTTP=8030, Worker1 WS=7940 HTTP=8040, Worker2 WS=7950 HTTP=8050

注意：relay 使用公網 IP acp:// link（而非 127.0.0.1），因為 P2P WS 綁定在 0.0.0.0。
      link 通過 /status 接口獲取，需等待公網 IP 探測完成（~30s 在沙箱環境）。
"""
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

# ── 路径配置 ──────────────────────────────────────────────────────────────────
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
RELAY_PY  = os.path.abspath(os.path.join(TESTS_DIR, "..", "relay", "acp_relay.py"))

# ── 工具函数 ──────────────────────────────────────────────────────────────────
_procs = []

def clean_env():
    """移除代理变量，防止干扰 relay 子进程。"""
    env = os.environ.copy()
    for var in ("http_proxy","HTTP_PROXY","https_proxy","HTTPS_PROXY",
                "all_proxy","ALL_PROXY","ftp_proxy","FTP_PROXY","no_proxy","NO_PROXY"):
        env.pop(var, None)
    return env


def start_relay(name, ws_port):
    """启动 relay；HTTP 端口 = ws_port + 100"""
    p = subprocess.Popen(
        [sys.executable, RELAY_PY,
         "--name", name,
         "--port", str(ws_port),
         "--http-host", "127.0.0.1",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=clean_env(),
    )
    _procs.append(p)
    return p


def wait_http_ready(http_port, timeout=15):
    """等待 relay HTTP 端口就绪。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{http_port}/status", timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def wait_link(http_port, timeout=50):
    """等待 relay 获取到公网 link（IP探测完成）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{http_port}/status", timeout=3) as r:
                d = json.loads(r.read())
                lnk = d.get("link")
                if lnk:
                    return lnk
        except Exception:
            pass
        time.sleep(0.5)
    return None


def http_get(http_port, path, timeout=5):
    url = f"http://127.0.0.1:{http_port}{path}"
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read()), r.status


def http_post(http_port, path, body, timeout=5):
    url = f"http://127.0.0.1:{http_port}{path}"
    req = urllib.request.Request(
        url, json.dumps(body).encode(),
        {"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read()), e.code


def stop_all():
    for p in list(_procs):
        try:
            p.send_signal(signal.SIGTERM)
            p.wait(timeout=8)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
        except Exception:
            pass
    _procs.clear()


def wait_peer_connected(http_port, peer_id, retries=80, interval=0.5):
    """等待 peer WS 握手完成（fast path: GET /peers connected flag; fallback: probe send）."""
    for _ in range(retries):
        try:
            with __import__("urllib").request.urlopen(
                    f"http://127.0.0.1:{http_port}/peers", timeout=3) as resp:
                peers = __import__("json").loads(resp.read())
                peer_list = peers if isinstance(peers, list) else peers.get("peers", [])
                for p in peer_list:
                    if p.get("id") == peer_id and p.get("connected"):
                        return True
        except Exception:
            pass
        try:
            r, _ = http_post(http_port, f"/peer/{peer_id}/send",
                             {"parts": [{"type": "text", "content": "__probe__"}], "role": "agent"})
            if r.get("ok"):
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


def read_inbox(agent_name):
    path = f"/tmp/acp_inbox_{agent_name}.jsonl"
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def inbox_count(agent_name):
    return len(read_inbox(agent_name))


def inbox_has(agent_name, text):
    return any(
        any(p.get("content","") == text for p in msg.get("parts",[]))
        for msg in read_inbox(agent_name)
    )


# ── 結果收集 ──────────────────────────────────────────────────────────────────
results = []

def check(name, passed, note=""):
    sym = "✅" if passed else "❌"
    results.append((name, passed, note))
    print(f"  {sym}  {name}" + (f"  [{note}]" if note else ""))
    return passed


# ═════════════════════════════════════════════════════════════════════════════
# 場景 A：雙 Agent 基礎通信（Alpha + Beta）
# Alpha WS=7910 HTTP=8010, Beta WS=7920 HTTP=8020
# ═════════════════════════════════════════════════════════════════════════════
def run_scenario_a():
    print("\n" + "="*60)
    print("場景 A：雙 Agent 基礎通信（Alpha ↔ Beta）")
    print("  Alpha WS=7910/HTTP=8010, Beta WS=7920/HTTP=8020")
    print("="*60)

    # 清理旧 inbox
    for name in ("Alpha", "Beta"):
        p = f"/tmp/acp_inbox_{name}.jsonl"
        if os.path.exists(p): os.remove(p)

    # 啟動 relay
    print("  啟動 Alpha（WS=7910）...")
    start_relay("Alpha", 7910)
    print("  啟動 Beta（WS=7920）...")
    start_relay("Beta",  7920)

    ok_a = wait_http_ready(8010)
    ok_b = wait_http_ready(8020)
    check("A0-a Alpha HTTP 就緒", ok_a)
    check("A0-b Beta HTTP 就緒", ok_b)
    if not (ok_a and ok_b):
        print("  [ABORT] relay 啟動失敗")
        return 0

    # A1: AgentCard 驗證
    try:
        card_a, sc1 = http_get(8010, "/.well-known/acp.json")
        check("A1-a Alpha AgentCard（有 self 字段）", sc1 == 200 and "self" in card_a,
              f"name={card_a.get('self',{}).get('name','?')}, version={card_a.get('self',{}).get('acp_version','?')}")
    except Exception as e:
        check("A1-a Alpha AgentCard", False, str(e))

    try:
        card_b, sc2 = http_get(8020, "/.well-known/acp.json")
        check("A1-b Beta AgentCard（有 self 字段）", sc2 == 200 and "self" in card_b,
              f"name={card_b.get('self',{}).get('name','?')}")
    except Exception as e:
        check("A1-b Beta AgentCard", False, str(e))

    # A2: /peers 初始空
    try:
        peers_a, _ = http_get(8010, "/peers")
        check("A2 /peers 初始為空", len(peers_a.get("peers", [])) == 0)
    except Exception as e:
        check("A2 /peers 初始", False, str(e))

    # 等待公網 link（IP 探測）
    print("  等待公網 link 就緒（最多 50s）...")
    t0 = time.time()
    beta_link = wait_link(8020)
    alpha_link = wait_link(8010)
    print(f"  Beta link:  {beta_link[:50] if beta_link else 'None'}... ({time.time()-t0:.0f}s)")
    print(f"  Alpha link: {alpha_link[:50] if alpha_link else 'None'}...")

    if not beta_link:
        check("A3 Beta link 可用", False, "timeout waiting for public IP")
        return 0

    # A3: 建立 P2P 連接（Alpha → Beta）
    try:
        r, sc = http_post(8010, "/peers/connect", {"link": beta_link, "name": "Beta"})
        connected = r.get("ok") and sc == 200
        check("A3 Alpha→Beta P2P 連接建立", connected,
              f"status={sc}, peer_id={r.get('peer_id')}")
        alpha_to_beta_peer = r.get("peer_id", "peer_001")
    except Exception as e:
        check("A3 Alpha→Beta 連接", False, str(e))
        alpha_to_beta_peer = "peer_001"
        connected = False

    if connected:
        ready = wait_peer_connected(8010, alpha_to_beta_peer)
        check("A3-b WS 握手完成", ready)
    else:
        ready = False

    # A4: A→B 單向消息
    msg_a_to_b = 0
    if ready:
        try:
            r, sc = http_post(8010, f"/peer/{alpha_to_beta_peer}/send", {
                "role": "agent",
                "parts": [{"type": "text", "content": "Hello Beta from Alpha!"}],
            })
            sent = r.get("ok")
            check("A4-a A→B 單向消息發送",  sent,
                  f"status={sc}, server_seq={r.get('server_seq')}")
            if sent:
                msg_a_to_b += 1
        except Exception as e:
            check("A4-a A→B 發送", False, str(e))

        time.sleep(0.8)
        check("A4-b Beta inbox 收到消息",
              inbox_has("Beta", "Hello Beta from Alpha!"),
              f"inbox={inbox_count('Beta')}")

    # A5: B→A 反向（Beta → Alpha）
    msg_b_to_a = 0
    if alpha_link:
        try:
            r2, sc2 = http_post(8020, "/peers/connect", {"link": alpha_link, "name": "Alpha"})
            check("A5-a Beta→Alpha 連接建立", r2.get("ok") and sc2 == 200, f"status={sc2}")
            beta_to_alpha_peer = r2.get("peer_id", "peer_001")

            if r2.get("ok"):
                check("A5-b WS 握手完成", wait_peer_connected(8020, beta_to_alpha_peer))
                r3, sc3 = http_post(8020, f"/peer/{beta_to_alpha_peer}/send", {
                    "role": "agent",
                    "parts": [{"type": "text", "content": "Reply from Beta!"}],
                })
                check("A5-c B→A 發送成功", r3.get("ok"), f"status={sc3}")
                if r3.get("ok"):
                    msg_b_to_a += 1
        except Exception as e:
            check("A5 Beta→Alpha", False, str(e))
    else:
        check("A5 Beta→Alpha", False, "no alpha link")

    time.sleep(0.8)
    check("A5-d Alpha inbox 收到 Beta 回覆",
          inbox_has("Alpha", "Reply from Beta!"),
          f"inbox={inbox_count('Alpha')}")

    # A6: 雙向會話多條消息
    if ready:
        extra_sent = 0
        for i in range(3):
            try:
                r4, _ = http_post(8010, f"/peer/{alpha_to_beta_peer}/send", {
                    "role": "agent",
                    "parts": [{"type": "text", "content": f"Multi#{i}"}],
                })
                if r4.get("ok"):
                    extra_sent += 1
            except Exception:
                pass
        msg_a_to_b += extra_sent
        check("A6 雙向會話 3 條連發", extra_sent == 3, f"sent={extra_sent}/3")

    # A7: /peers 統計
    try:
        peers2, _ = http_get(8010, "/peers")
        peer_list = peers2.get("peers", [])
        check("A7 /peers 有記錄", len(peer_list) >= 1,
              f"count={len(peer_list)}")
    except Exception as e:
        check("A7 /peers", False, str(e))

    # A8: SSE stream 驗證
    import socket
    try:
        s = socket.socket()
        s.settimeout(3)
        s.connect(("127.0.0.1", 8010))
        s.send(b"GET /stream HTTP/1.1\r\nHost: 127.0.0.1:8010\r\n\r\n")
        resp = s.recv(512).decode("utf-8", errors="replace")
        s.close()
        check("A8 SSE /stream 響應 200 OK", "200 OK" in resp, f"resp={resp[:60]!r}")
    except Exception as e:
        check("A8 SSE /stream", False, str(e))

    total_msgs = msg_a_to_b + msg_b_to_a
    print(f"\n  場景 A 消息統計: A→B={msg_a_to_b}, B→A={msg_b_to_a}, 合計={total_msgs}")
    return total_msgs


# ═════════════════════════════════════════════════════════════════════════════
# 場景 B：團隊協作（Orchestrator → Worker1 + Worker2）
# Orch WS=7930 HTTP=8030, W1 WS=7940 HTTP=8040, W2 WS=7950 HTTP=8050
# ═════════════════════════════════════════════════════════════════════════════
def run_scenario_b():
    print("\n" + "="*60)
    print("場景 B：團隊協作（Orchestrator → Worker1 + Worker2）")
    print("  Orch WS=7930/HTTP=8030, W1 WS=7940/HTTP=8040, W2 WS=7950/HTTP=8050")
    print("="*60)

    # 清理旧 inbox
    for name in ("Orchestrator", "Worker1", "Worker2"):
        p = f"/tmp/acp_inbox_{name}.jsonl"
        if os.path.exists(p): os.remove(p)

    # 啟動 3 個 relay
    print("  啟動 Orchestrator（WS=7930）...")
    start_relay("Orchestrator", 7930)
    print("  啟動 Worker1（WS=7940）...")
    start_relay("Worker1", 7940)
    print("  啟動 Worker2（WS=7950）...")
    start_relay("Worker2", 7950)

    ok_orch = wait_http_ready(8030)
    ok_w1   = wait_http_ready(8040)
    ok_w2   = wait_http_ready(8050)
    check("B0-a Orchestrator HTTP 就緒", ok_orch)
    check("B0-b Worker1 HTTP 就緒", ok_w1)
    check("B0-c Worker2 HTTP 就緒", ok_w2)
    if not (ok_orch and ok_w1 and ok_w2):
        print("  [ABORT] relay 啟動失敗")
        return

    # 並行等待所有 link 就緒（BUG-035 fix 策略）
    import concurrent.futures
    print("  並行等待 link 就緒（最多 50s）...")
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        orch_fut = ex.submit(wait_link, 8030)
        w1_fut   = ex.submit(wait_link, 8040)
        w2_fut   = ex.submit(wait_link, 8050)
        orch_link = orch_fut.result()
        w1_link   = w1_fut.result()
        w2_link   = w2_fut.result()
    print(f"  links ready in {time.time()-t0:.0f}s")
    print(f"  Orch: {orch_link[:40] if orch_link else 'None'}...")
    print(f"  W1:   {w1_link[:40] if w1_link else 'None'}...")
    print(f"  W2:   {w2_link[:40] if w2_link else 'None'}...")

    if not (w1_link and w2_link):
        check("B-links Worker1/2 link 可用", False, "timeout")
        return

    # B1: Orchestrator 連接 Worker1
    r, sc = http_post(8030, "/peers/connect", {"link": w1_link, "name": "Worker1"})
    check("B1 Orch→Worker1 連接建立", r.get("ok") and sc == 200,
          f"status={sc}, peer_id={r.get('peer_id')}")
    w1_peer_id = r.get("peer_id", "peer_001")

    # B2: Orchestrator 連接 Worker2
    r2, sc2 = http_post(8030, "/peers/connect", {"link": w2_link, "name": "Worker2"})
    check("B2 Orch→Worker2 連接建立", r2.get("ok") and sc2 == 200,
          f"status={sc2}, peer_id={r2.get('peer_id')}")
    w2_peer_id = r2.get("peer_id", "peer_002")

    # 等 WS 握手完成
    print("  等待 Worker1/Worker2 WS 就緒...")
    check("B2-d Worker1 WS 握手完成", wait_peer_connected(8030, w1_peer_id))
    check("B2-e Worker2 WS 握手完成", wait_peer_connected(8030, w2_peer_id))

    # B3: /peers 驗證（2 個 connected peer）
    peers_orch, _ = http_get(8030, "/peers")
    connected_count = sum(1 for p in peers_orch.get("peers", []) if p.get("connected"))
    check("B3 Orchestrator 有 2 個 connected peer", connected_count == 2,
          f"count={connected_count}")

    # B4: Orchestrator → Worker1 發送任務（/peer/{id}/send）
    r, sc = http_post(8030, f"/peer/{w1_peer_id}/send", {
        "role": "agent",
        "parts": [{"type": "text", "content": "TASK:W1:analyze_dataset"}],
    })
    check("B4 Orch→Worker1 定向發送任務", r.get("ok"), f"status={sc}")

    # B5: Orchestrator → Worker2 發送任務（/peer/{id}/send）
    r2, sc2 = http_post(8030, f"/peer/{w2_peer_id}/send", {
        "role": "agent",
        "parts": [{"type": "text", "content": "TASK:W2:generate_report"}],
    })
    check("B5 Orch→Worker2 定向發送任務", r2.get("ok"), f"status={sc2}")

    time.sleep(1.0)

    # B6/B7: 驗證兩個 Worker 均收到消息 ★核心驗證點★
    check("B6 Worker1 收到任務消息 ✓",
          inbox_has("Worker1", "TASK:W1:analyze_dataset"),
          f"inbox={inbox_count('Worker1')}")
    check("B7 Worker2 收到任務消息 ✓",
          inbox_has("Worker2", "TASK:W2:generate_report"),
          f"inbox={inbox_count('Worker2')}")

    # B8: Worker1 回覆 Orchestrator
    if orch_link:
        r3, sc3 = http_post(8040, "/peers/connect", {"link": orch_link, "name": "Orchestrator"})
        check("B8-a Worker1→Orch 連接", r3.get("ok"), f"status={sc3}")
        w1_to_orch_peer = r3.get("peer_id")

        if r3.get("ok") and w1_to_orch_peer:
            check("B8-b Worker1→Orch WS 就緒", wait_peer_connected(8040, w1_to_orch_peer))
            r4, _ = http_post(8040, f"/peer/{w1_to_orch_peer}/send", {
                "role": "agent",
                "parts": [{"type": "text", "content": "RESULT:W1:done"}],
            })
            check("B8-c Worker1 回覆 Orchestrator", r4.get("ok"))

    # B9: Worker2 回覆 Orchestrator
    if orch_link:
        r5, sc5 = http_post(8050, "/peers/connect", {"link": orch_link, "name": "Orchestrator"})
        check("B9-a Worker2→Orch 連接", r5.get("ok"), f"status={sc5}")
        w2_to_orch_peer = r5.get("peer_id")

        if r5.get("ok") and w2_to_orch_peer:
            check("B9-b Worker2→Orch WS 就緒", wait_peer_connected(8050, w2_to_orch_peer))
            r6, _ = http_post(8050, f"/peer/{w2_to_orch_peer}/send", {
                "role": "agent",
                "parts": [{"type": "text", "content": "RESULT:W2:done"}],
            })
            check("B9-c Worker2 回覆 Orchestrator", r6.get("ok"))

    time.sleep(1.0)

    # B10/B11: Orchestrator 收到兩個 Worker 的結果
    check("B10 Orch 收到 Worker1 結果",
          inbox_has("Orchestrator", "RESULT:W1:done"),
          f"inbox={inbox_count('Orchestrator')}")
    check("B11 Orch 收到 Worker2 結果",
          inbox_has("Orchestrator", "RESULT:W2:done"),
          f"inbox={inbox_count('Orchestrator')}")

    # B12: Orchestrator AgentCard 驗證
    try:
        card, sc = http_get(8030, "/.well-known/acp.json")
        check("B12 Orchestrator AgentCard OK", sc == 200 and "self" in card)
    except Exception as e:
        check("B12 AgentCard", False, str(e))

    # B13: Orch /peers 查詢（SSE 路徑驗證）
    try:
        status_orch, _ = http_get(8030, "/status")
        check("B13 Orchestrator messages_sent >= 2",
              status_orch.get("messages_sent", 0) >= 2,
              f"sent={status_orch.get('messages_sent', 0)}")
    except Exception as e:
        check("B13 messages_sent", False, str(e))


# ═════════════════════════════════════════════════════════════════════════════
# 主入口
# ═════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("ACP 測試輪 — 場景 A/B")
    print(f"relay: {RELAY_PY}")
    print()

    try:
        # 場景 A
        msg_count = run_scenario_a()
        stop_all()
        print(f"\n  [場景 A 完成] 消息總數={msg_count}")

        time.sleep(1)

        # 場景 B
        run_scenario_b()
        stop_all()
        print(f"\n  [場景 B 完成]")

    except KeyboardInterrupt:
        print("\n[INTERRUPTED]")
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback; traceback.print_exc()
    finally:
        stop_all()

    # ── 彙報 ──────────────────────────────────────────────────────────────────
    total  = len(results)
    passed = sum(1 for _, p, _ in results if p)
    failed = [(n, note) for n, p, note in results if not p]

    print(f"\n{'='*60}")
    print(f"最終結果：{passed}/{total} PASS")
    if failed:
        print("\n失敗項：")
        for n, note in failed:
            print(f"  ❌  {n}" + (f"  [{note}]" if note else ""))
    else:
        print("✅ 全部通過！")
    print("="*60)

    sys.exit(0 if not failed else 1)
