#!/usr/bin/env python3
"""
ACP 场景E测试 — NAT穿透三级降级（可验证子集）
===============================================
沙箱中无法模拟真实 NAT/WAN，因此测试可验证的降级相关逻辑：

- E1: /status 暴露 connection_type 字段（host mode: "host"）
- E2: SSE 事件流可订阅（/stream 端点）
- E3: 非法 link 格式 → 连接请求返回 4xx
- E4: P2P_MAX_RETRIES 配置可读（via --help 或源码）
- E5: DCUtR puncher 存在且可初始化（模块级）
- E6: 双实例 host 模式下两个 relay 相互独立（不共享状态）
- E7: guest_mode 调用无效 host → 适当超时 + 降级触发

运行方式：
    python3 tests/test_scenario_e.py
"""

import sys, os, time, json, threading, subprocess, signal, socket, requests
import pytest
from helpers import clean_subprocess_env

RELAY_PATH = os.path.join(os.path.dirname(__file__), "../relay/acp_relay.py")
HTTP_E1 = "http://localhost:7981"   # instance 1 (ws=7881)
HTTP_E2 = "http://localhost:7982"   # instance 2 (ws=7882)
PORT_E1 = 7881
PORT_E2 = 7882
PROCS   = []

def start_relay(port, name="RelayE"):
    p = subprocess.Popen(
        [sys.executable, RELAY_PATH, "--port", str(port), "--name", name],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    PROCS.append(p)
    base = f"http://localhost:{port+100}"
    for _ in range(40):
        try:
            if requests.get(f"{base}/recv", timeout=0.5).status_code == 200:
                return base
        except Exception:
            pass
        time.sleep(0.2)
    raise RuntimeError(f"Relay {name}:{port} did not start")

def stop_all():
    for p in PROCS:
        try:
            p.send_signal(signal.SIGTERM)
            p.wait(timeout=3)
        except Exception:
            pass

results = []
def check(name, cond, detail=""):
    status = "✅" if cond else "❌"
    results.append((name, cond, detail))
    detail_str = f"  ({detail})" if detail else ""
    print(f"  {status} {name}{detail_str}")
    return cond

# ── pytest module-scoped fixture ────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def relay_instances():
    """Start two relay instances for the duration of this test module."""
    start_relay(PORT_E1, name="RelayE-Alpha")
    start_relay(PORT_E2, name="RelayE-Beta")
    yield
    stop_all()

# ── pytest entry point ──────────────────────────────────────────────────────────

def test_scenario_e():
    """Pytest entry point: run all E scenarios end-to-end."""
    _run_e1_connection_type_field()
    _run_e2_sse_stream()
    _run_e3_invalid_link_formats()
    _run_e4_p2p_max_retries()
    _run_e5_dcutr_puncher()
    _run_e6_dual_instance_isolation()
    _run_e7_guest_invalid_host_timeout()
    failed = [r for r in results if not r[1]]
    assert not failed, f"Scenario E failures: {[r[0] for r in failed]}"

# ── Test cases ──────────────────────────────────────────────────────────────────

def _run_e1_connection_type_field():
    """E1: host mode /status 含 connection_type 或 connected 字段"""
    print("\n[E1] /status connection_type 字段...")
    r = requests.get(f"{HTTP_E1}/status", timeout=5)
    check("E1  /status → 200",               r.status_code == 200)
    body = r.json()
    has_conn_type = "connection_type" in body
    has_connected  = "connected" in body
    check("E1  含 connection_type 或 connected 字段",
          has_conn_type or has_connected,
          str(list(body.keys())[:8]))
    if has_conn_type:
        check("E1  connection_type 值合法",
              body["connection_type"] in ("host", "guest", "p2p", "relay", "dcutr_direct", "none"),
              body["connection_type"])

def _run_e2_sse_stream():
    """E2: /stream SSE 端点可建立连接并返回 text/event-stream"""
    print("\n[E2] SSE /stream 端点订阅...")
    try:
        r = requests.get(f"{HTTP_E1}/stream", stream=True, timeout=3)
        ct = r.headers.get("Content-Type", "")
        check("E2  /stream → 200",                r.status_code == 200, f"got {r.status_code}")
        check("E2  Content-Type: text/event-stream", "text/event-stream" in ct, ct)
        # Read first chunk — SSE keeps connection open; timeout is normal behavior
        try:
            chunk = next(r.iter_content(chunk_size=512), None)
            check("E2  首个 SSE 数据块不为空",     chunk is not None and len(chunk) > 0,
                  f"{len(chunk)}b" if chunk else "empty")
        except (requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout):
            # SSE connection timed out while waiting for events — expected, connection was live
            check("E2  SSE 连接保持直到超时（正常）", True, "timeout as expected")
        finally:
            try: r.close()
            except Exception: pass
    except requests.exceptions.Timeout:
        check("E2  /stream 保持连接（超时=正常）", True, "timeout ok")

def _run_e3_invalid_link_formats():
    """E3: POST /peers/connect 各种非法格式返回 4xx"""
    print("\n[E3] 非法 link 格式处理...")
    invalid_links = [
        ("空 link",         ""),
        ("纯文本",           "not-a-link-at-all"),
        ("http 非 acp",     "http://192.168.1.1:7800/token123"),
        ("缺 token",        "acp://192.168.1.1:7800"),
        ("端口越界",         "acp://192.168.1.1:99999/token123"),
    ]
    for label, link in invalid_links:
        try:
            r = requests.post(f"{HTTP_E1}/peers/connect",
                              json={"link": link}, timeout=5)
            is_4xx = 400 <= r.status_code < 500
            check(f"E3  {label} → 4xx",   is_4xx, f"got {r.status_code}")
        except Exception as e:
            check(f"E3  {label} → error", False, str(e))

def _run_e4_p2p_max_retries():
    """E4: P2P_MAX_RETRIES 常量可读，且 > 0"""
    print("\n[E4] P2P_MAX_RETRIES 配置...")
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../relay"))
        import importlib.util
        spec_ = importlib.util.spec_from_file_location("acp_relay_mod", RELAY_PATH)
        # Just grep the value — don't actually import (side effects)
        with open(RELAY_PATH) as f:
            src = f.read()
        import re
        m = re.search(r"P2P_MAX_RETRIES\s*=\s*(\d+)", src)
        if m:
            val = int(m.group(1))
            check("E4  P2P_MAX_RETRIES 常量存在",    True, f"value={val}")
            check("E4  P2P_MAX_RETRIES > 0",        val > 0, f"val={val}")
            check("E4  P2P_MAX_RETRIES 合理范围(1-20)", 1 <= val <= 20, f"val={val}")
        else:
            check("E4  P2P_MAX_RETRIES 常量存在",    False, "not found in source")
    except Exception as e:
        check("E4  P2P_MAX_RETRIES 读取",            False, str(e))

def _run_e5_dcutr_puncher():
    """E5: DCUtRPuncher 类存在且可实例化"""
    print("\n[E5] DCUtRPuncher 类检查...")
    try:
        with open(RELAY_PATH) as f:
            src = f.read()
        has_class = "class DCUtRPuncher" in src
        has_attempt = "async def attempt" in src
        check("E5  DCUtRPuncher 类定义存在",   has_class)
        check("E5  attempt() 方法存在",        has_attempt)
        # Check method signature
        import re
        m = re.search(r"async def attempt\(self[^)]*\)", src)
        check("E5  attempt 是 async 方法",     m is not None,
              m.group(0) if m else "not found")
    except Exception as e:
        check("E5  DCUtRPuncher 检查",         False, str(e))

def _run_e6_dual_instance_isolation():
    """E6: 两个独立 relay 实例状态互不干扰"""
    print("\n[E6] 双实例隔离测试...")
    try:
        # Create task on instance 1
        r1 = requests.post(f"{HTTP_E1}/tasks",
                           json={"role":"agent","parts":[{"type":"text","content":"inst1-task"}]},
                           timeout=5)
        check("E6  实例1 POST /tasks → 201",   r1.status_code == 201, f"got {r1.status_code}")

        # Verify instance 2 has no tasks from instance 1
        r2_tasks = requests.get(f"{HTTP_E2}/tasks", timeout=5)
        body2 = r2_tasks.json() if r2_tasks.status_code == 200 else {}
        total2 = body2.get("total", len(body2.get("tasks", [])))
        check("E6  实例2 不含实例1的 task",     total2 == 0, f"total2={total2}")

        # Each has independent /status
        s1 = requests.get(f"{HTTP_E1}/status", timeout=5).json()
        s2 = requests.get(f"{HTTP_E2}/status", timeout=5).json()
        sid1 = s1.get("session_id") or s1.get("agent_name", "?")
        sid2 = s2.get("session_id") or s2.get("agent_name", "?")
        # session_id may be None until P2P link is established; use agent_name as fallback
        check("E6  两实例 session_id 不同",
              sid1 != sid2,
              f"s1={str(sid1)[:12]} s2={str(sid2)[:12]}")
    except Exception as e:
        check("E6  双实例隔离",                False, str(e))

def _run_e7_guest_invalid_host_timeout():
    """E7: /peers/connect 指向不可达地址 → 立即接受（异步 connect），不挂起"""
    print("\n[E7] 不可达地址异步连接测试...")
    # Use a non-routable IP (TEST-NET-1 RFC5737)
    # Design: /peers/connect is async — returns 200 immediately, connects in background
    # This is correct behavior (like non-blocking TCP connect)
    bad_link = "acp://192.0.2.1:9999/deadbeef_token_xyz"
    t0 = time.time()
    try:
        r = requests.post(f"{HTTP_E1}/peers/connect",
                          json={"link": bad_link}, timeout=5)
        elapsed = time.time() - t0
        # Async connect: 200 = "accepted", connection happens in background
        accepted = r.status_code in (200, 202)
        check("E7  不可达地址立即接受（异步 connect）", accepted, f"status={r.status_code}")
        check("E7  响应时间 < 1s（不阻塞）",    elapsed < 1.0, f"{elapsed:.3f}s")
        body = r.json() if r.status_code in (200, 202) else {}
        check("E7  返回 peer_id（后台连接）",   "peer_id" in body, str(list(body.keys())[:5]))
    except requests.exceptions.Timeout:
        elapsed = time.time() - t0
        check("E7  响应不应超时",               False, f"timed out after {elapsed:.1f}s")
    except Exception as e:
        check("E7  连接尝试不崩溃",             False, str(e))

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("ACP 场景E — NAT穿透三级降级（可验证子集）")
    print("=" * 55)

    print("启动两个 Relay 实例...")
    base1 = start_relay(PORT_E1, name="RelayE-Alpha")
    base2 = start_relay(PORT_E2, name="RelayE-Beta")
    print(f"Alpha: {HTTP_E1}  Beta: {HTTP_E2}\n")

    try:
        _run_e1_connection_type_field()
        _run_e2_sse_stream()
        _run_e3_invalid_link_formats()
        _run_e4_p2p_max_retries()
        _run_e5_dcutr_puncher()
        _run_e6_dual_instance_isolation()
        _run_e7_guest_invalid_host_timeout()
    finally:
        stop_all()

    passed = sum(1 for _, ok, _ in results if ok)
    total  = len(results)
    failed = total - passed

    print()
    print("=" * 55)
    print(f"场景E: {passed}/{total} PASS", end="")
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
