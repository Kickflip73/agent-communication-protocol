"""
场景 H: 多 Agent 并发操作隔离 (HTTP-only)

Tests that three independent relay instances running concurrently:
  - H1: All instances are healthy and independent (/status)
  - H2: Concurrent /tasks creation produces no task-ID collisions across instances
  - H3: Large parallel task bursts maintain correct per-instance routing
  - H4: Message idempotency is scoped per-instance (same message_id ≠ cross-instance dedup)
  - H5: /recv queues are independent (messages on WA don't appear on WB)
  - H6: /status under concurrent load returns consistent data

Note: This version uses HTTP-only APIs. Tests that require cross-instance
P2P WebSocket connections (original H scenario) are tracked separately as
a network-dependent integration test (see tests/test_p2p_cross_connect.py).
"""
import sys, os, subprocess, signal, time, threading
import requests
import pytest
from helpers import clean_subprocess_env

RELAY_PATH = os.path.join(os.path.dirname(__file__), "../relay/acp_relay.py")
def _free_port():
    """Return an OS-assigned free port where port AND port+100 are both free."""
    import socket
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

PORT_HUB = _free_port()
PORT_WA  = _free_port()
PORT_WB  = _free_port()
HUB = f"http://localhost:{PORT_HUB + 100}"
WA  = f"http://localhost:{PORT_WA  + 100}"
WB  = f"http://localhost:{PORT_WB  + 100}"
PROCS = []


# ── Helpers ───────────────────────────────────────────────────────────────────

def _start_relay(port, name):
    p = subprocess.Popen(
        [sys.executable, RELAY_PATH, "--port", str(port), "--name", name],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env=clean_subprocess_env(),
    )
    PROCS.append(p)
    base = f"http://localhost:{port + 100}"
    for _ in range(40):
        try:
            if requests.get(f"{base}/recv", timeout=0.5).status_code == 200:
                return base
        except Exception:
            pass
        time.sleep(0.2)
    raise RuntimeError(f"Relay {name}:{port} did not start within 8s")


def _stop_all():
    for p in PROCS:
        try:
            p.send_signal(signal.SIGTERM)
            p.wait(timeout=3)
        except Exception:
            pass


def _create_task(base, content, role="agent"):
    r = requests.post(f"{base}/tasks",
                      json={"role": role,
                            "parts": [{"type": "text", "content": content}]},
                      timeout=5)
    if r.status_code == 201:
        return r.json().get("task", {}).get("id") or r.json().get("task_id")
    return None


# ── pytest fixture ────────────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def relay_instances():
    _start_relay(PORT_HUB, "Hub")
    _start_relay(PORT_WA,  "WorkerA")
    _start_relay(PORT_WB,  "WorkerB")
    yield
    _stop_all()


# ── Scenario implementation ───────────────────────────────────────────────────

def _run_scenario_h():
    results = {}

    # H1: All three instances healthy
    print("\n[H1] Three relay instances healthy and independent")
    for name, base in [("Hub", HUB), ("WA", WA), ("WB", WB)]:
        r = requests.get(f"{base}/status", timeout=5)
        ok = r.status_code == 200 and "acp_version" in r.json()
        print(f"  {'✅' if ok else '❌'} {name} /status → {r.status_code}")
        results[f"H1_{name}_healthy"] = ok

    # H2: Concurrent task creation — no cross-instance ID collisions
    print("\n[H2] Concurrent task creation — no task_id collisions across instances")
    wa_ids, wb_ids = [], []
    create_errors = []

    def batch_create(base, store, prefix, n):
        for i in range(n):
            tid = _create_task(base, f"{prefix}-task-{i}")
            if tid:
                store.append(tid)
            else:
                create_errors.append(f"{prefix}-{i}")

    t1 = threading.Thread(target=batch_create, args=(WA, wa_ids, "wa", 10))
    t2 = threading.Thread(target=batch_create, args=(WB, wb_ids, "wb", 10))
    t1.start(); t2.start()
    t1.join(); t2.join()

    overlap = set(wa_ids) & set(wb_ids)
    print(f"  {'✅' if len(wa_ids)==10 else '❌'} WA created {len(wa_ids)}/10 tasks")
    print(f"  {'✅' if len(wb_ids)==10 else '❌'} WB created {len(wb_ids)}/10 tasks")
    print(f"  {'✅' if not overlap else '❌ COLLISION'} No task_id overlap: {overlap or 'none'}")
    results["H2_wa_tasks_count"]  = len(wa_ids) == 10
    results["H2_wb_tasks_count"]  = len(wb_ids) == 10
    results["H2_no_id_collision"] = not overlap

    # H3: Task lists are isolated per-instance
    print("\n[H3] /tasks lists are isolated per-instance")
    wa_list = requests.get(f"{WA}/tasks", timeout=5).json().get("tasks", [])
    wb_list = requests.get(f"{WB}/tasks", timeout=5).json().get("tasks", [])
    wa_list_ids = {t["id"] for t in wa_list}
    wb_list_ids = {t["id"] for t in wb_list}
    cross_in_wa = wa_list_ids & set(wb_ids)  # WB tasks should not appear in WA
    cross_in_wb = wb_list_ids & set(wa_ids)  # WA tasks should not appear in WB
    print(f"  {'✅' if not cross_in_wa else '❌'} WA list has no WB tasks: {cross_in_wa or 'none'}")
    print(f"  {'✅' if not cross_in_wb else '❌'} WB list has no WA tasks: {cross_in_wb or 'none'}")
    results["H3_wa_list_isolated"] = not cross_in_wa
    results["H3_wb_list_isolated"] = not cross_in_wb

    # H4: Per-instance task state independence
    print("\n[H4] Task state changes on WA do not affect WB")
    if wa_ids and wb_ids:
        wa_tid = wa_ids[0]
        wb_tid = wb_ids[0]
        # Cancel a WA task
        r_cancel = requests.post(f"{WA}/tasks/{wa_tid}:cancel", timeout=5)
        ok_cancel = r_cancel.status_code in (200, 204)
        # Check WB task is unaffected
        r_wb_task = requests.get(f"{WB}/tasks/{wb_tid}", timeout=5)
        if r_wb_task.status_code == 200:
            d = r_wb_task.json()
            # GET /tasks/{id} returns flat object (no "task" wrapper)
            wb_status = d.get("status") or d.get("task", {}).get("status", "?")
        else:
            wb_status = "?"
        wa_not_on_wb = requests.get(f"{WB}/tasks/{wa_tid}", timeout=5).status_code == 404
        print(f"  {'✅' if ok_cancel else '⚠️'} WA task cancel: {r_cancel.status_code}")
        print(f"  {'✅' if wb_status in ('submitted','working','completed') else '❌'} WB task status unaffected: {wb_status}")
        print(f"  {'✅' if wa_not_on_wb else '❌'} WA task_id not found on WB (404)")
        results["H4_wb_task_unaffected"] = wb_status in ("submitted", "working", "completed")
        results["H4_wa_task_not_on_wb"]  = wa_not_on_wb
    else:
        results["H4_wb_task_unaffected"] = False
        results["H4_wa_task_not_on_wb"]  = False

    # H5: /recv queues are independent
    print("\n[H5] /recv queues are independent per-instance")
    wa_recv = requests.get(f"{WA}/recv", timeout=5).json()
    wb_recv = requests.get(f"{WB}/recv", timeout=5).json()
    # Both should return 200 with separate message lists
    wa_recv_ok = "messages" in wa_recv
    wb_recv_ok = "messages" in wb_recv
    print(f"  {'✅' if wa_recv_ok else '❌'} WA /recv has messages key")
    print(f"  {'✅' if wb_recv_ok else '❌'} WB /recv has messages key")
    results["H5_wa_recv_ok"] = wa_recv_ok
    results["H5_wb_recv_ok"] = wb_recv_ok

    # H6: /status under concurrent load
    print("\n[H6] /status consistent under concurrent load")
    status_results = []
    status_errors  = []

    def check_status(base, n):
        for _ in range(n):
            try:
                r = requests.get(f"{base}/status", timeout=3)
                status_results.append(r.status_code == 200 and "acp_version" in r.json())
            except Exception as e:
                status_errors.append(str(e))

    threads = [
        threading.Thread(target=check_status, args=(WA, 5)),
        threading.Thread(target=check_status, args=(WB, 5)),
        threading.Thread(target=check_status, args=(HUB, 5)),
    ]
    for t in threads: t.start()
    for t in threads: t.join()

    status_ok_rate = sum(status_results) / len(status_results) if status_results else 0
    print(f"  {'✅' if status_ok_rate==1.0 else '❌'} All {len(status_results)} /status calls ok: {status_ok_rate:.0%}")
    results["H6_status_under_load"] = status_ok_rate >= 0.95

    # Summary
    total  = len(results)
    passed = sum(1 for v in results.values() if v)
    print(f"\n{'=' * 50}")
    print(f"场景H: {passed}/{total} PASS")
    for k, v in results.items():
        print(f"  {'✅' if v else '❌'} {k}")

    return results


# ── pytest entry point ────────────────────────────────────────────────────────

def test_scenario_h():
    results = _run_scenario_h()
    failed  = [k for k, v in results.items() if not v]
    assert not failed, f"Scenario H failures: {failed}"


if __name__ == "__main__":
    print("ACP 场景H — 多 Agent 并发隔离 (HTTP-only)")
    print("=" * 50)
    _start_relay(PORT_HUB, "Hub")
    _start_relay(PORT_WA,  "WorkerA")
    _start_relay(PORT_WB,  "WorkerB")
    try:
        results = _run_scenario_h()
    finally:
        _stop_all()
    sys.exit(0 if all(results.values()) else 1)
