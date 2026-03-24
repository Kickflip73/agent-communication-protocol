#!/usr/bin/env python3
"""
tests/test_scenario_bc.py

Scenario B: Team Collaboration (Orchestrator → Worker1 + Worker2)
Scenario C: Multi-Agent Pipeline (A → B → C → A chain)

Run: python3 tests/test_scenario_bc.py
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

RELAY_PY = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py"))
_procs = []

def start_agent(name, port):
    p = subprocess.Popen(
        [sys.executable, RELAY_PY, "--name", name, "--port", str(port), "--http-host", "127.0.0.1"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    _procs.append(p)
    return p

def stop_all():
    for p in _procs:
        try: p.terminate(); p.wait(timeout=3)
        except Exception: pass

def get(http_port, path, timeout=5):
    with urllib.request.urlopen(f"http://127.0.0.1:{http_port}{path}", timeout=timeout) as r:
        return json.loads(r.read()), r.status

def post(http_port, path, body, timeout=5):
    req = urllib.request.Request(
        f"http://127.0.0.1:{http_port}{path}",
        json.dumps(body).encode(), {"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read()), e.code

results = []

def wait_peer_ready(http_port, peer_id, retries=16, interval=0.5):
    """Wait until peer WS handshake completes (probe send succeeds)."""
    for _ in range(retries):
        r, _ = post(http_port, f"/peer/{peer_id}/send",
                    {"parts": [{"type": "text", "content": "__probe__"}], "role": "agent"})
        if r.get("ok"):
            return True
        time.sleep(interval)
    return False

def ok(name, passed, note=""):
    sym = "✅" if passed else "❌"
    results.append((name, passed, note))
    print(f"  {sym}  {name}" + (f" — {note}" if note else ""))

def read_inbox(name):
    path = f"/tmp/acp_inbox_{name}.jsonl"
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]

def inbox_has(name, text):
    return any(
        any(p.get("content", "") == text for p in msg.get("parts", []))
        for msg in read_inbox(name)
    )

# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO B: Orchestrator → Worker1 + Worker2 task distribution
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*55)
print("Scenario B: Team Collaboration (Orchestrator + 2 Workers)")
print("="*55)

# Ports: Orch=7850→7950, W1=7851→7951, W2=7852→7952
start_agent("Orchestrator", 7850)
start_agent("Worker1",      7851)
start_agent("Worker2",      7852)
time.sleep(5)

try:
    # Get links
    orch_link, _ = get(7950, "/status")
    orch_link = orch_link["link"]
    w1_link, _   = get(7951, "/status")
    w1_link = w1_link["link"]
    w2_link, _   = get(7952, "/status")
    w2_link = w2_link["link"]
    print(f"  Orchestrator: {orch_link}")
    print(f"  Worker1:      {w1_link}")
    print(f"  Worker2:      {w2_link}")

    # B1: Orchestrator connects to Worker1
    r, c = post(7950, "/peers/connect", {"link": w1_link, "name": "Worker1"})
    ok("B1.1 Orch→W1 connect ok", r.get("ok") and c == 200)
    w1_peer_id = r.get("peer_id", "peer_001")
    wait_peer_ready(7950, w1_peer_id)

    # B2: Orchestrator connects to Worker2
    r, c = post(7950, "/peers/connect", {"link": w2_link, "name": "Worker2"})
    ok("B2.1 Orch→W2 connect ok", r.get("ok") and c == 200)
    w2_peer_id = r.get("peer_id", "peer_002")
    wait_peer_ready(7950, w2_peer_id)

    time.sleep(1)

    # B3: Verify both connections
    peers_orch, _ = get(7950, "/peers")
    connected_count = sum(1 for p in peers_orch["peers"] if p["connected"])
    ok("B3.1 Orch has 2 connected peers", connected_count == 2, f"count={connected_count}")

    # B4: Create tasks for each worker
    task1, c1 = post(7950, "/tasks", {
        "role": "agent",
        "input": {"parts": [{"type": "text", "content": "Task for Worker1: analyze data"}]}
    })
    ok("B4.1 Create task1", c1 in (200, 201) and task1.get("ok") and "id" in task1.get("task", {}))

    task2, c2 = post(7950, "/tasks", {
        "role": "agent",
        "input": {"parts": [{"type": "text", "content": "Task for Worker2: generate report"}]}
    })
    ok("B4.2 Create task2", c2 in (200, 201) and task2.get("ok") and "id" in task2.get("task", {}))

    # B5: Dispatch messages to workers
    r1, _ = post(7950, f"/peer/{w1_peer_id}/send", {
        "text": "TASK:B-W1:analyze dataset X",
        "task_id": task1.get("task", {}).get("id")
    })
    ok("B5.1 Dispatch to Worker1", r1.get("ok"))

    r2, _ = post(7950, f"/peer/{w2_peer_id}/send", {
        "text": "TASK:B-W2:generate final report",
        "task_id": task2.get("task", {}).get("id")
    })
    ok("B5.2 Dispatch to Worker2", r2.get("ok"))

    time.sleep(2)

    # B6: Workers received their tasks
    ok("B6.1 Worker1 received task", inbox_has("Worker1", "TASK:B-W1:analyze dataset X"))
    ok("B6.2 Worker2 received task", inbox_has("Worker2", "TASK:B-W2:generate final report"))

    # B7: Workers reply back to Orchestrator
    w1_peers, _ = get(7951, "/peers")
    w1_orch_peer = next((p["id"] for p in w1_peers["peers"] if p["connected"]), None)
    if w1_orch_peer:
        r, _ = post(7951, f"/peer/{w1_orch_peer}/send", {"text": "RESULT:B-W1:analysis complete"})
        ok("B7.1 Worker1 replies to Orch", r.get("ok"))
    else:
        ok("B7.1 Worker1 replies to Orch", False, "no connected peer found")

    w2_peers, _ = get(7952, "/peers")
    w2_orch_peer = next((p["id"] for p in w2_peers["peers"] if p["connected"]), None)
    if w2_orch_peer:
        r, _ = post(7952, f"/peer/{w2_orch_peer}/send", {"text": "RESULT:B-W2:report ready"})
        ok("B7.2 Worker2 replies to Orch", r.get("ok"))
    else:
        ok("B7.2 Worker2 replies to Orch", False, "no connected peer found")

    time.sleep(2)

    # B8: Orchestrator received both results
    ok("B8.1 Orch got Worker1 result", inbox_has("Orchestrator", "RESULT:B-W1:analysis complete"))
    ok("B8.2 Orch got Worker2 result", inbox_has("Orchestrator", "RESULT:B-W2:report ready"))

    # B9: Task status check
    tasks_list, _ = get(7950, "/tasks?limit=10")
    ok("B9.1 Tasks list returns results", tasks_list.get("count", 0) >= 2)

except Exception as e:
    ok("Scenario B", False, str(e))

stop_all()
_procs.clear()

# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO C: Multi-Agent Pipeline (A → B → C → A)
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*55)
print("Scenario C: Multi-Agent Pipeline (A → B → C → A chain)")
print("="*55)

start_agent("PipeA", 7853)
start_agent("PipeB", 7854)
start_agent("PipeC", 7855)
time.sleep(5)

try:
    link_a, _ = get(7953, "/status"); link_a = link_a["link"]
    link_b, _ = get(7954, "/status"); link_b = link_b["link"]
    link_c, _ = get(7955, "/status"); link_c = link_c["link"]
    print(f"  PipeA: {link_a}")
    print(f"  PipeB: {link_b}")
    print(f"  PipeC: {link_c}")

    # C1: Establish pipeline A→B→C
    r, _ = post(7953, "/peers/connect", {"link": link_b, "name": "PipeB"})
    ok("C1.1 A connects to B", r.get("ok"))
    b_at_a = r.get("peer_id")

    r, _ = post(7954, "/peers/connect", {"link": link_c, "name": "PipeC"})
    ok("C1.2 B connects to C", r.get("ok"))
    c_at_b = r.get("peer_id")

    r, _ = post(7955, "/peers/connect", {"link": link_a, "name": "PipeA"})
    ok("C1.3 C connects to A (close loop)", r.get("ok"))
    a_at_c = r.get("peer_id")

    time.sleep(3)

    # Verify all connections
    peers_a, _ = get(7953, "/peers")
    peers_b, _ = get(7954, "/peers")
    peers_c, _ = get(7955, "/peers")
    ok("C2.1 A has peer connected", any(p["connected"] for p in peers_a["peers"]))
    ok("C2.2 B has peer connected", any(p["connected"] for p in peers_b["peers"]))
    ok("C2.3 C has peer connected", any(p["connected"] for p in peers_c["peers"]))

    # C3: Send through pipeline A → B
    r, _ = post(7953, f"/peer/{b_at_a}/send", {"text": "PIPE:stage1:raw_data"})
    ok("C3.1 A→B pipeline step 1", r.get("ok"))

    time.sleep(1)
    ok("C3.2 B received stage1", inbox_has("PipeB", "PIPE:stage1:raw_data"))

    # C4: B forwards to C (simulating stage 2 processing)
    r, _ = post(7954, f"/peer/{c_at_b}/send", {"text": "PIPE:stage2:processed_data"})
    ok("C4.1 B→C pipeline step 2", r.get("ok"))

    time.sleep(1)
    ok("C4.2 C received stage2", inbox_has("PipeC", "PIPE:stage2:processed_data"))

    # C5: C returns result to A (close the loop)
    r, _ = post(7955, f"/peer/{a_at_c}/send", {"text": "PIPE:stage3:final_result"})
    ok("C5.1 C→A pipeline complete", r.get("ok"))

    time.sleep(1)
    ok("C5.2 A received final result", inbox_has("PipeA", "PIPE:stage3:final_result"))

    # C6: Message ordering check
    inbox_b = read_inbox("PipeB")
    inbox_c = read_inbox("PipeC")
    inbox_a_final = read_inbox("PipeA")
    ok("C6.1 B inbox non-empty", len(inbox_b) >= 1)
    ok("C6.2 C inbox non-empty", len(inbox_c) >= 1)
    ok("C6.3 A received final result in inbox", len(inbox_a_final) >= 1)

    # C7: Status checks after pipeline
    status_a, _ = get(7953, "/status")
    ok("C7.1 A messages_received >= 1", status_a["messages_received"] >= 1)
    ok("C7.2 A messages_sent >= 1",     status_a["messages_sent"] >= 1)

    # C8: Concurrent sends (simulate parallel pipeline stages)
    import threading
    concurrent_results = []
    def send_concurrent(http_port, peer_id, text, idx):
        try:
            r, c = post(http_port, f"/peer/{peer_id}/send", {"text": text}, timeout=5)
            concurrent_results.append((idx, r.get("ok"), c))
        except Exception as e:
            concurrent_results.append((idx, False, str(e)))

    threads = [
        threading.Thread(target=send_concurrent, args=(7953, b_at_a, f"CONCURRENT:{i}", i))
        for i in range(5)
    ]
    for t in threads: t.start()
    for t in threads: t.join(timeout=10)

    all_ok = all(r[1] for r in concurrent_results)
    ok("C8.1 5 concurrent sends all succeeded", all_ok,
       f"{sum(r[1] for r in concurrent_results)}/5 ok")

    time.sleep(2)
    status_b_final, _ = get(7954, "/status")
    ok("C8.2 B received all concurrent messages",
       status_b_final["messages_received"] >= 5,
       f"received={status_b_final['messages_received']}")

except Exception as e:
    ok("Scenario C", False, str(e))

stop_all()

# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────
total  = len(results)
passed = sum(1 for _, p, _ in results if p)
failed = total - passed

print(f"\n{'='*55}")
print(f"Scenario B+C Tests: {passed}/{total} PASS")
if failed:
    print(f"\nFailed:")
    for name, p, note in results:
        if not p:
            print(f"  ❌ {name}" + (f" — {note}" if note else ""))
print("="*55)

sys.exit(0 if failed == 0 else 1)
