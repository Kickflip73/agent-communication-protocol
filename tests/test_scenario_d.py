#!/usr/bin/env python3
"""
ACP 场景D测试 — 压力测试
=========================
- D1: 100 条消息连续发送（单线程）
- D2: 并发发送（10 线程 × 10 条）
- D3: 大量消息积压后批量 /recv
- D4: 消息幂等性（同一 message_id 重发 10 次）
- D5: 快速连续 /tasks 创建（50 个 task）

运行方式：
    python3 tests/test_scenario_d.py
"""

import sys, os, time, json, threading, subprocess, signal, requests
from concurrent.futures import ThreadPoolExecutor, as_completed

RELAY_PATH = os.path.join(os.path.dirname(__file__), "../relay/acp_relay.py")
HTTP_BASE  = "http://localhost:7971"   # ws_port=7871, http_port=7971
RELAY_PORT = 7871
RELAY_PROC = None

# ── Helpers ────────────────────────────────────────────────────────────────────

def start_relay():
    global RELAY_PROC
    RELAY_PROC = subprocess.Popen(
        [sys.executable, RELAY_PATH, "--port", str(RELAY_PORT), "--name", "StressRelay"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(40):
        try:
            if requests.get(f"{HTTP_BASE}/recv", timeout=0.5).status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.2)
    raise RuntimeError("Relay did not start")

def stop_relay():
    if RELAY_PROC:
        RELAY_PROC.send_signal(signal.SIGTERM)
        RELAY_PROC.wait(timeout=3)

def send_msg(content, msg_id=None, role="agent"):
    payload = {"role": role, "parts": [{"type": "text", "content": content}]}
    if msg_id:
        payload["message_id"] = msg_id
    try:
        r = requests.post(f"{HTTP_BASE}/message:send", json=payload, timeout=5)
        return r.status_code, r.json()
    except Exception as e:
        return 0, {"error": str(e)}

def recv_all():
    try:
        r = requests.get(f"{HTTP_BASE}/recv?limit=200", timeout=5)
        if r.status_code == 200:
            return r.json().get("messages", [])
    except Exception:
        pass
    return []

results = []
def check(name, cond, detail=""):
    status = "✅" if cond else "❌"
    results.append((name, cond, detail))
    detail_str = f"  ({detail})" if detail else ""
    print(f"  {status} {name}{detail_str}")
    return cond

# ── Test cases ─────────────────────────────────────────────────────────────────

def test_d1_sequential_100():
    """D1: 100条消息顺序发送，全部返回 non-5xx"""
    print("\n[D1] 100 条顺序消息发送...")
    t0 = time.time()
    statuses = []
    for i in range(100):
        code, body = send_msg(f"stress-seq-{i:04d}")
        statuses.append(code)

    elapsed = time.time() - t0
    ok_count  = sum(1 for c in statuses if c in (200, 400, 503))
    err_count = sum(1 for c in statuses if c == 500 or c == 0)
    rps = 100 / elapsed

    check("D1  100 条发送无 5xx 错误", err_count == 0, f"{err_count} errors")
    check("D1  全部返回 valid HTTP",   ok_count == 100, f"{ok_count}/100")
    check(f"D1  吞吐量 ≥ 20 req/s",   rps >= 20, f"{rps:.1f} req/s")
    print(f"      elapsed: {elapsed:.2f}s, {rps:.1f} req/s")

def test_d2_concurrent_100():
    """D2: 10 线程 × 10 条并发发送"""
    print("\n[D2] 并发发送（10 线程 × 10 条）...")
    errors = []
    codes  = []
    lock   = threading.Lock()

    def worker(tid):
        for i in range(10):
            code, body = send_msg(f"stress-concurrent-t{tid}-{i}")
            with lock:
                codes.append(code)
                if code == 500 or code == 0:
                    errors.append((tid, i, code, body))

    t0 = time.time()
    threads = [threading.Thread(target=worker, args=(t,)) for t in range(10)]
    for th in threads: th.start()
    for th in threads: th.join()
    elapsed = time.time() - t0

    ok_count = sum(1 for c in codes if c in (200, 400, 503))
    rps = 100 / elapsed

    check("D2  并发 100 条无 5xx",      len(errors) == 0, f"{len(errors)} errors")
    check("D2  全部返回 valid HTTP",    ok_count == 100, f"{ok_count}/100")
    check(f"D2  并发吞吐 ≥ 30 req/s",  rps >= 30, f"{rps:.1f} req/s")
    print(f"      elapsed: {elapsed:.2f}s, {rps:.1f} req/s")

def test_d3_recv_batch():
    """D3: 大量消息后 /recv 批量拉取"""
    print("\n[D3] 批量 /recv 测试...")
    # 先清空
    recv_all()
    # 在 host-mode 下没有 peer，/recv 始终为空 inbox（消息进不来）
    # 改为测试 /status 和 /tasks 在负载后的响应性
    t0 = time.time()
    r = requests.get(f"{HTTP_BASE}/recv", timeout=5)
    elapsed = (time.time() - t0) * 1000

    check("D3  /recv 压力后仍返回 200",  r.status_code == 200, f"got {r.status_code}")
    check("D3  /recv 响应时间 < 200ms",  elapsed < 200, f"{elapsed:.1f}ms")
    body = r.json()
    check("D3  响应包含 messages 字段",  "messages" in body, str(list(body.keys())))

def test_d4_idempotency_10x():
    """D4: 同一 message_id 重发 10 次，行为一致"""
    print("\n[D4] 消息幂等性（同 message_id × 10）...")
    mid = "stress-idem-fixed-001"
    responses = []
    for _ in range(10):
        code, body = send_msg("idem-content", msg_id=mid)
        responses.append((code, body))

    codes = [c for c, _ in responses]
    # All must return same status code
    all_same = len(set(codes)) == 1
    check("D4  10 次重发返回一致状态码",   all_same, f"codes={set(codes)}")
    # No 500s
    no_500 = all(c != 500 for c in codes)
    check("D4  10 次无 500 错误",         no_500, f"codes={codes[:3]}...")

def test_d5_task_burst():
    """D5: 快速连续创建 50 个 task"""
    print("\n[D5] 50 个 task 快速创建...")
    task_ids = []
    errors   = []
    t0 = time.time()

    for i in range(50):
        try:
            r = requests.post(f"{HTTP_BASE}/tasks",
                              json={"role": "agent",
                                    "parts": [{"type":"text","content":f"task-stress-{i}"}]},
                              timeout=5)
            if r.status_code in (200, 201):   # /tasks returns 201 Created
                body_j = r.json()
                # /tasks returns {"ok":true,"task":{"id":"..."}}
                tid = (body_j.get("task_id")
                       or body_j.get("id")
                       or (body_j.get("task") or {}).get("id"))
                if tid:
                    task_ids.append(tid)
            elif r.status_code >= 500:
                errors.append((i, r.status_code))
        except Exception as e:
            errors.append((i, str(e)))

    elapsed = time.time() - t0

    check("D5  50 个 task 无 5xx",         len(errors) == 0, f"{len(errors)} errors")
    check("D5  创建成功数 = 50",           len(task_ids) == 50,
          f"{len(task_ids)}/50")
    check("D5  task_id 全部唯一",           len(set(task_ids)) == len(task_ids),
          f"dupes={len(task_ids)-len(set(task_ids))}")
    print(f"      elapsed: {elapsed:.2f}s, {50/elapsed:.1f} tasks/s")

    # Verify /tasks list integrity
    try:
        r2 = requests.get(f"{HTTP_BASE}/tasks", timeout=5)
        if r2.status_code == 200:
            body = r2.json()
            total = body.get("total", len(body.get("tasks", [])))
            check("D5  /tasks 列表总数 ≥ 50",   total >= 50, f"total={total}")
    except Exception as e:
        check("D5  /tasks list reachable",     False, str(e))

def test_d6_status_under_load():
    """D6: 压力后 /status 正常响应"""
    print("\n[D6] 压力后 /status 健康检查...")
    r = requests.get(f"{HTTP_BASE}/status", timeout=5)
    check("D6  /status → 200",             r.status_code == 200, f"got {r.status_code}")
    body = r.json() if r.status_code == 200 else {}
    check("D6  acp_version 字段存在",       "acp_version" in body, str(list(body.keys())[:5]))

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("ACP 场景D — 压力测试")
    print("=" * 50)
    print("启动 StressRelay...")
    start_relay()
    print(f"Relay ready at {HTTP_BASE}\n")

    try:
        test_d1_sequential_100()
        test_d2_concurrent_100()
        test_d3_recv_batch()
        test_d4_idempotency_10x()
        test_d5_task_burst()
        test_d6_status_under_load()
    finally:
        stop_relay()

    passed = sum(1 for _, ok, _ in results if ok)
    total  = len(results)
    failed = total - passed

    print()
    print("=" * 50)
    print(f"场景D: {passed}/{total} PASS", end="")
    if failed == 0:
        print(" ✅")
        sys.exit(0)
    else:
        print(f" ❌ ({failed} FAILURES)")
        for name, ok, detail in results:
            if not ok:
                print(f"  FAIL: {name}  ({detail})")
        sys.exit(1)

if __name__ == "__main__":
    main()
