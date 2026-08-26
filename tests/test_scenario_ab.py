"""
test_scenario_ab.py — 场景 A + 场景 B 集成场景测试

场景 A：双 Agent 直接通信
  A1: Agent-Alice → Relay → GET /peers，确认双方可见
  A2: Alice POST /tasks (skill_id targeting Bob's skill) → audit_log 有 created + skill_invoked
  A3: Bob 端 POST /tasks → Alice 更新任务状态 working → completed
  A4: 双向会话：Alice → Bob, Bob → Alice 各发一条消息

场景 B：Orchestrator → Worker1 + Worker2 任务分发
  B1: Orchestrator 向 Worker1 分发任务 + 验证 audit_log
  B2: Orchestrator 向 Worker2 分发任务 + 验证 audit_log
  B3: Worker1 完成，Worker2 失败（error path），Orchestrator 端可查询两个 task 各自 audit-log
  B4: Orchestrator 批量发送（5 tasks to worker1），验证 task_id 唯一 + audit_log 全写入
"""

import json, time, threading, subprocess, urllib.request, urllib.error, os, sys

RELAY_PY = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")


def _wait_ready(http_port, timeout=12):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{http_port}/status", timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.25)
    return False


def _start(ws_port, name, skills=None, extra=None):
    http_port = ws_port + 100
    env = os.environ.copy()
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        env.pop(k, None)
    cmd = [sys.executable, RELAY_PY,
           "--port", str(ws_port), "--name", name,
           "--local-only", "--test-mode"]
    if skills:
        cmd += ["--skills", json.dumps(skills)]
    if extra:
        cmd.extend(extra)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    for s in (proc.stdout, proc.stderr):
        threading.Thread(target=lambda x=s: x.read(), daemon=True).start()
    assert _wait_ready(http_port), f"relay '{name}' on :{http_port} failed to start"
    return proc, http_port


def _http(method, hp, path, body=None):
    url = f"http://127.0.0.1:{hp}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _inject(hp, name, trust=None):
    body = {"from": name, "parts": [{"type": "text", "text": "hello"}]}
    if trust:
        body["trust_override"] = trust
    s, b = _http("POST", hp, "/debug/inject", body)
    assert s == 200, f"inject failed {s}: {b}"
    return b["peer_id"]


# ═══════════════════════════════════════════════════════════════
# 场景 A1: 双节点可见性
# ═══════════════════════════════════════════════════════════════
def test_a1_two_agents_peer_visibility():
    """A1: Alice + Bob 各自启动，互相 inject 后在 GET /peers 中可见。"""
    pa, ha = _start(50000, "Alice", [{"id": "sk_alice", "name": "Alice Skill"}])
    pb, hb = _start(50001, "Bob",   [{"id": "sk_bob",   "name": "Bob Skill"}])
    try:
        # Alice 节点注入 Bob，Bob 节点注入 Alice
        pid_bob_in_alice   = _inject(ha, "Bob")
        pid_alice_in_bob   = _inject(hb, "Alice")

        # Alice 节点可看到 Bob peer  (GET /peers returns "id" not "peer_id")
        s, b = _http("GET", ha, "/peers")
        assert s == 200
        peer_ids = [p["id"] for p in b.get("peers", [])]
        assert pid_bob_in_alice in peer_ids, f"Bob not visible in Alice's /peers: {peer_ids}"

        # Bob 节点可看到 Alice peer
        s, b = _http("GET", hb, "/peers")
        peer_ids = [p["id"] for p in b.get("peers", [])]
        assert pid_alice_in_bob in peer_ids, f"Alice not visible in Bob's /peers: {peer_ids}"
    finally:
        pa.terminate(); pa.wait(timeout=5)
        pb.terminate(); pb.wait(timeout=5)


# ═══════════════════════════════════════════════════════════════
# 场景 A2: Alice POST /tasks targeting Bob's skill → audit_log
# ═══════════════════════════════════════════════════════════════
def test_a2_task_creation_with_audit_log():
    """A2: Alice 创建 task 指向 bob_skill → audit_log 包含 created + skill_invoked。"""
    pa, ha = _start(50002, "Alice")
    try:
        # Alice 节点注册 bob_skill
        _inject(ha, "BobAgent")  # register a peer

        s, b = _http("POST", ha, "/tasks", {
            "role": "agent",
            "text": "process_data",
            "skill_id": "analysis",
        })
        assert s == 201, f"{s}: {b}"
        task = b["task"]
        assert "audit_log" in task
        events = [e["event"] for e in task["audit_log"]]
        assert "created" in events, f"'created' not in audit_log: {events}"

        # Retrieve via endpoint
        s2, b2 = _http("GET", ha, f"/tasks/{task['id']}/audit-log")
        assert s2 == 200
        assert b2["task_id"] == task["id"]
        assert b2["total"] >= 1
    finally:
        pa.terminate(); pa.wait(timeout=5)


# ═══════════════════════════════════════════════════════════════
# 场景 A3: 任务状态流转 submitted → working → completed
# ═══════════════════════════════════════════════════════════════
def test_a3_task_lifecycle_audit_trail():
    """A3: task 经历 submitted→working→completed，audit_log 记录全部 status_changed。"""
    pa, ha = _start(50003, "Alice")
    try:
        s, b = _http("POST", ha, "/tasks", {"role": "agent", "text": "run job"})
        assert s == 201
        tid = b["task"]["id"]

        _http("POST", ha, f"/tasks/{tid}:update", {"status": "working"})
        _http("POST", ha, f"/tasks/{tid}:update", {"status": "completed"})

        s, b = _http("GET", ha, f"/tasks/{tid}/audit-log")
        assert s == 200
        events = [e["event"] for e in b["audit_log"]]
        transitions = [e for e in b["audit_log"] if e["event"] == "status_changed"]

        # Should have: submitted→working, working→completed
        assert len(transitions) >= 2, f"Expected ≥2 status_changed, got: {transitions}"

        # Verify 'to' fields
        to_states = [e["detail"]["to"] for e in transitions]
        assert "working"   in to_states, f"'working' not in transitions: {to_states}"
        assert "completed" in to_states, f"'completed' not in transitions: {to_states}"

        # Seq monotonically increasing
        seqs = [e["seq"] for e in b["audit_log"]]
        assert seqs == sorted(seqs), f"seq not monotonic: {seqs}"
    finally:
        pa.terminate(); pa.wait(timeout=5)


# ═══════════════════════════════════════════════════════════════
# 场景 A4: 双向消息（Alice↔Bob 各自 inject + 确认消息入库）
# ═══════════════════════════════════════════════════════════════
def test_a4_bidirectional_message_exchange():
    """A4: Alice 节点 inject Bob 消息，Bob 节点 inject Alice 消息，双方 /messages 均可查。"""
    pa, ha = _start(50004, "Alice")
    pb, hb = _start(50005, "Bob")
    try:
        # Alice relay: inject message from Bob
        s, b = _http("POST", ha, "/debug/inject", {
            "from": "Bob",
            "parts": [{"type": "text", "text": "Hello Alice from Bob"}]
        })
        assert s == 200
        pid_bob = b["peer_id"]

        # Bob relay: inject message from Alice
        s, b = _http("POST", hb, "/debug/inject", {
            "from": "Alice",
            "parts": [{"type": "text", "text": "Hello Bob from Alice"}]
        })
        assert s == 200
        pid_alice = b["peer_id"]

        # Verify Alice relay has Bob's message
        s, b = _http("GET", ha, f"/peers/{pid_bob}/messages")
        assert s == 200, f"{s}: {b}"
        msgs = b.get("messages", [])
        assert len(msgs) >= 1
        texts = [p["text"] for m in msgs for p in m.get("parts", []) if "text" in p]
        assert any("Hello Alice from Bob" in t for t in texts), \
            f"Bob's message not found: {texts}"

        # Verify Bob relay has Alice's message
        s, b = _http("GET", hb, f"/peers/{pid_alice}/messages")
        assert s == 200
        msgs = b.get("messages", [])
        texts = [p["text"] for m in msgs for p in m.get("parts", []) if "text" in p]
        assert any("Hello Bob from Alice" in t for t in texts), \
            f"Alice's message not found: {texts}"
    finally:
        pa.terminate(); pa.wait(timeout=5)
        pb.terminate(); pb.wait(timeout=5)


# ═══════════════════════════════════════════════════════════════
# 场景 B1+B2: Orchestrator 向 Worker1 + Worker2 分发任务
# ═══════════════════════════════════════════════════════════════
def test_b1_b2_orchestrator_dispatches_to_workers():
    """B1+B2: Orchestrator 创建 2 个 task（分别指向 worker1_skill / worker2_skill），
    各自 audit_log 独立，skill_invoked.skill_id 正确。"""
    po, ho = _start(50006, "Orchestrator", [
        {"id": "worker1_skill", "name": "Worker1 Analysis"},
        {"id": "worker2_skill", "name": "Worker2 Render"},
    ])
    try:
        # Dispatch to Worker1
        s1, b1 = _http("POST", ho, "/tasks", {
            "role": "agent", "text": "analyze dataset", "skill_id": "worker1_skill"
        })
        assert s1 == 201, f"Worker1 dispatch failed: {s1} {b1}"
        tid1 = b1["task"]["id"]

        # Dispatch to Worker2
        s2, b2 = _http("POST", ho, "/tasks", {
            "role": "agent", "text": "render output", "skill_id": "worker2_skill"
        })
        assert s2 == 201, f"Worker2 dispatch failed: {s2} {b2}"
        tid2 = b2["task"]["id"]

        # Verify task IDs are distinct
        assert tid1 != tid2, "task IDs should be unique"

        # Worker1 audit_log
        _, al1 = _http("GET", ho, f"/tasks/{tid1}/audit-log")
        inv1 = next((e for e in al1["audit_log"] if e["event"] == "skill_invoked"), None)
        assert inv1 is not None, f"skill_invoked missing in Worker1 audit_log"
        assert inv1["detail"]["skill_id"] == "worker1_skill", \
            f"Wrong skill_id: {inv1['detail']['skill_id']}"

        # Worker2 audit_log
        _, al2 = _http("GET", ho, f"/tasks/{tid2}/audit-log")
        inv2 = next((e for e in al2["audit_log"] if e["event"] == "skill_invoked"), None)
        assert inv2 is not None, f"skill_invoked missing in Worker2 audit_log"
        assert inv2["detail"]["skill_id"] == "worker2_skill", \
            f"Wrong skill_id: {inv2['detail']['skill_id']}"
    finally:
        po.terminate(); po.wait(timeout=5)


# ═══════════════════════════════════════════════════════════════
# 场景 B3: Worker1 完成，Worker2 失败，各自 audit_log 独立记录
# ═══════════════════════════════════════════════════════════════
def test_b3_worker1_complete_worker2_fail():
    """B3: Worker1 completed, Worker2 failed。两个 task audit_log 中 status_changed.to 各异。"""
    po, ho = _start(50007, "Orchestrator2", [
        {"id": "w1", "name": "Worker1"},
        {"id": "w2", "name": "Worker2"},
    ])
    try:
        _, r1 = _http("POST", ho, "/tasks", {"role": "agent", "text": "job1", "skill_id": "w1"})
        _, r2 = _http("POST", ho, "/tasks", {"role": "agent", "text": "job2", "skill_id": "w2"})
        tid1 = r1["task"]["id"]
        tid2 = r2["task"]["id"]

        # Worker1 succeeds
        _http("POST", ho, f"/tasks/{tid1}:update", {"status": "working"})
        _http("POST", ho, f"/tasks/{tid1}:update", {"status": "completed"})

        # Worker2 fails
        _http("POST", ho, f"/tasks/{tid2}:update", {"status": "working"})
        _http("POST", ho, f"/tasks/{tid2}:update", {"status": "failed", "error": "OOM"})

        # Worker1 audit: last transition = completed
        _, al1 = _http("GET", ho, f"/tasks/{tid1}/audit-log")
        transitions1 = [e["detail"]["to"] for e in al1["audit_log"] if e["event"] == "status_changed"]
        assert "completed" in transitions1, f"Worker1 should be completed: {transitions1}"
        assert "failed" not in transitions1, f"Worker1 should not be failed: {transitions1}"

        # Worker2 audit: last transition = failed
        _, al2 = _http("GET", ho, f"/tasks/{tid2}/audit-log")
        transitions2 = [e["detail"]["to"] for e in al2["audit_log"] if e["event"] == "status_changed"]
        assert "failed" in transitions2, f"Worker2 should be failed: {transitions2}"

        # Worker2 failed entry has error detail
        fail_entry = next(
            (e for e in al2["audit_log"]
             if e["event"] == "status_changed" and e.get("detail", {}).get("to") == "failed"),
            None
        )
        assert fail_entry is not None
        assert fail_entry["detail"].get("error") == "OOM", \
            f"error field missing/wrong: {fail_entry['detail']}"
    finally:
        po.terminate(); po.wait(timeout=5)


# ═══════════════════════════════════════════════════════════════
# 场景 B4: Orchestrator 批量分发 5 tasks → task_id 唯一 + audit_log 全写入
# ═══════════════════════════════════════════════════════════════
def test_b4_bulk_dispatch_unique_ids_and_audit():
    """B4: Orchestrator 批量创建 5 个 task，task_id 全部唯一，每个都有 audit_log。"""
    po, ho = _start(50008, "OrchestratorBulk", [{"id": "bulk_sk", "name": "Bulk Worker"}])
    try:
        task_ids = []
        for i in range(5):
            s, b = _http("POST", ho, "/tasks", {
                "role": "agent",
                "text": f"batch_job_{i}",
                "skill_id": "bulk_sk",
            })
            assert s == 201, f"Task {i} failed: {s} {b}"
            tid = b["task"]["id"]
            task_ids.append(tid)
            # Each task must have audit_log
            assert "audit_log" in b["task"], f"Task {i} missing audit_log"
            assert len(b["task"]["audit_log"]) >= 1, f"Task {i} audit_log empty"

        # All task IDs must be unique
        assert len(task_ids) == len(set(task_ids)), \
            f"Duplicate task IDs found: {task_ids}"

        # Verify via audit-log endpoint for each
        for tid in task_ids:
            s, b = _http("GET", ho, f"/tasks/{tid}/audit-log")
            assert s == 200, f"audit-log endpoint failed for {tid}: {s}"
            assert b["total"] >= 1, f"empty audit_log for {tid}"
    finally:
        po.terminate(); po.wait(timeout=5)
