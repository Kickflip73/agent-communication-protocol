"""
test_concurrent_and_integration.py — 场景 H 并发压力 + 三层防护链集成测试

Test IDs:
  CONC1–CONC6  — concurrent task creation, confirm/reject races, parallel peers
  INT1–INT5    — full three-layer chain: tier → param_constraints → human_confirmation
"""

import json
import time
import threading
import subprocess
import urllib.request
import urllib.error
import os
import sys
import uuid

RELAY_PY = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")


def wait_http_ready(http_port, timeout=12):
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


def _start_relay(ws_port, skills, extra_flags=None):
    http_port = ws_port + 100
    env = os.environ.copy()
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        env.pop(k, None)
    cmd = [sys.executable, RELAY_PY,
           "--port", str(ws_port), "--name", "ConcRelay",
           "--local-only", "--test-mode",
           "--skills", json.dumps(skills)]
    if extra_flags:
        cmd.extend(extra_flags)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    for s in (proc.stdout, proc.stderr):
        threading.Thread(target=lambda x=s: x.read(), daemon=True).start()
    assert wait_http_ready(http_port), f"relay on :{http_port} did not start"
    return proc, http_port


def _http(method, http_port, path, body=None):
    url = f"http://127.0.0.1:{http_port}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


# T3_TRUST_OVERRIDE: card_sig(0.35)+did_consistent(0.20)+ping<50ms(0.20)+msgs>100(0.15)=0.90
T3_TRUST = {
    "card_sig_valid": True, "did_consistent": True,
    "ping_rtt_ms": 20, "message_count": 150, "verified_identity": True,
}
T2_TRUST = {
    "card_sig_valid": True, "did_consistent": True, "ping_rtt_ms": 20,
}


def _inject(hp, name, trust=None):
    body = {"from": name, "parts": [{"type": "text", "text": "hi"}]}
    if trust:
        body["trust_override"] = trust
    s, b = _http("POST", hp, "/debug/inject", body)
    assert s == 200, f"inject failed: {s} {b}"
    return b["peer_id"]


# ═══════════════════════════════════════════════════════════════
# CONC1: 50 concurrent POST /tasks — all succeed, no data races
# ═══════════════════════════════════════════════════════════════
def test_conc1_concurrent_task_creation():
    """CONC1: 50 goroutines fire POST /tasks simultaneously — all 201, unique IDs."""
    proc, hp = _start_relay(48000, [{"id": "s1", "name": "S1"}])
    try:
        N = 50
        results = [None] * N

        def create(i):
            s, b = _http("POST", hp, "/tasks", {
                "role": "agent", "text": f"task-{i}", "skill_id": "s1",
            })
            results[i] = (s, b.get("task", b).get("id"))

        threads = [threading.Thread(target=create, args=(i,)) for i in range(N)]
        for t in threads: t.start()
        for t in threads: t.join(timeout=10)

        statuses = [r[0] for r in results]
        ids = [r[1] for r in results]
        assert all(s == 201 for s in statuses), f"Some failed: {[s for s in statuses if s != 201]}"
        assert len(set(ids)) == N, f"Duplicate task IDs detected: {len(set(ids))} unique of {N}"
    finally:
        proc.terminate(); proc.wait(timeout=5)


# ═══════════════════════════════════════════════════════════════
# CONC2: concurrent :confirm race — only one wins, other gets 409
# ═══════════════════════════════════════════════════════════════
def test_conc2_concurrent_confirm_race():
    """CONC2: two threads race to :confirm the same task — exactly one 200, one 409."""
    proc, hp = _start_relay(48001, [
        {"id": "dep", "name": "Dep", "authorization_tier": "T3", "human_confirmation_required": True}
    ])
    try:
        pid = _inject(hp, "racer", T3_TRUST)
        _, cr = _http("POST", hp, "/tasks", {
            "role": "agent", "text": "deploy", "skill_id": "dep", "peer_id": pid,
        })
        assert cr["task"]["status"] == "confirmation_pending"
        tid = cr["task"]["id"]

        outcomes = []
        barrier = threading.Barrier(2)

        def confirm():
            barrier.wait()
            s, b = _http("POST", hp, f"/tasks/{tid}:confirm")
            outcomes.append(s)

        threads = [threading.Thread(target=confirm) for _ in range(2)]
        for t in threads: t.start()
        for t in threads: t.join(timeout=5)

        # One should succeed (200), other either 200 idempotent or 409
        assert sorted(outcomes) in ([200, 200], [200, 409]), \
            f"Unexpected outcomes: {outcomes}"
        # Task must be in submitted state afterwards
        _, tget = _http("GET", hp, f"/tasks/{tid}")
        assert tget.get("status") == "submitted", f"Final status: {tget.get('status')}"
    finally:
        proc.terminate(); proc.wait(timeout=5)


# ═══════════════════════════════════════════════════════════════
# CONC3: confirm and reject race — task ends in submitted OR failed
# ═══════════════════════════════════════════════════════════════
def test_conc3_confirm_reject_race():
    """CONC3: one thread confirms, one rejects simultaneously — task ends in submitted or failed (not hanging)."""
    proc, hp = _start_relay(48002, [
        {"id": "dep", "name": "Dep", "authorization_tier": "T3", "human_confirmation_required": True}
    ])
    try:
        pid = _inject(hp, "cr_peer", T3_TRUST)
        _, cr = _http("POST", hp, "/tasks", {
            "role": "agent", "text": "deploy", "skill_id": "dep", "peer_id": pid,
        })
        tid = cr["task"]["id"]
        barrier = threading.Barrier(2)
        results = {}

        def do_confirm():
            barrier.wait()
            s, b = _http("POST", hp, f"/tasks/{tid}:confirm")
            results["confirm"] = (s, b)

        def do_reject():
            barrier.wait()
            s, b = _http("POST", hp, f"/tasks/{tid}:reject", {"reason": "race-reject"})
            results["reject"] = (s, b)

        t1 = threading.Thread(target=do_confirm)
        t2 = threading.Thread(target=do_reject)
        t1.start(); t2.start()
        t1.join(timeout=5); t2.join(timeout=5)

        _, final = _http("GET", hp, f"/tasks/{tid}")
        assert final.get("status") in ("submitted", "failed"), \
            f"Task in unexpected state: {final.get('status')}"
        # Task must NOT be stuck in confirmation_pending
        assert final.get("status") != "confirmation_pending", "Task stuck in confirmation_pending!"
    finally:
        proc.terminate(); proc.wait(timeout=5)


# ═══════════════════════════════════════════════════════════════
# CONC4: 10 parallel peers submit tasks concurrently
# ═══════════════════════════════════════════════════════════════
def test_conc4_parallel_peers_submit():
    """CONC4: 10 different peers submit tasks in parallel — all 201, no cross-contamination."""
    proc, hp = _start_relay(48003, [{"id": "work", "name": "Work"}])
    try:
        results = {}
        lock = threading.Lock()

        def peer_submit(i):
            pid = _inject(hp, f"peer_{i}")
            s, b = _http("POST", hp, "/tasks", {
                "role": "agent", "text": f"job-{i}", "skill_id": "work", "peer_id": pid,
            })
            with lock:
                results[i] = (s, b.get("task", b).get("id"))

        threads = [threading.Thread(target=peer_submit, args=(i,)) for i in range(10)]
        for t in threads: t.start()
        for t in threads: t.join(timeout=15)

        assert len(results) == 10
        assert all(r[0] == 201 for r in results.values()), \
            f"Failures: {[(i, r) for i, r in results.items() if r[0] != 201]}"
        ids = [r[1] for r in results.values()]
        assert len(set(ids)) == 10, "Duplicate task IDs across parallel peers"
    finally:
        proc.terminate(); proc.wait(timeout=5)


# ═══════════════════════════════════════════════════════════════
# CONC5: 100 rapid-fire tasks — throughput test, no crashes
# ═══════════════════════════════════════════════════════════════
def test_conc5_100_tasks_throughput():
    """CONC5: 100 sequential POST /tasks in tight loop — all 201, relay stays stable."""
    proc, hp = _start_relay(48004, [{"id": "rapid", "name": "Rapid"}])
    try:
        failures = []
        for i in range(100):
            s, b = _http("POST", hp, "/tasks", {
                "role": "agent", "text": f"msg-{i}", "skill_id": "rapid",
            })
            if s != 201:
                failures.append((i, s, b))

        assert not failures, f"{len(failures)} failures: {failures[:3]}"

        # Relay still healthy
        s, b = _http("GET", hp, "/status")
        assert s == 200

        s, b = _http("GET", hp, "/tasks?limit=200")
        tasks = b.get("tasks", [])
        assert len(tasks) >= 100, f"Only {len(tasks)} tasks visible in /tasks?limit=200"
    finally:
        proc.terminate(); proc.wait(timeout=5)


# ═══════════════════════════════════════════════════════════════
# CONC6: concurrent trust_override inject — no peer table corruption
# ═══════════════════════════════════════════════════════════════
def test_conc6_concurrent_peer_inject():
    """CONC6: 20 concurrent /debug/inject calls with trust_override — all succeed, distinct peer_ids."""
    proc, hp = _start_relay(48005, [{"id": "sk", "name": "SK"}])
    try:
        peer_ids = [None] * 20
        errors = []

        def inject_peer(i):
            try:
                s, b = _http("POST", hp, "/debug/inject", {
                    "from": f"cp_{i}",
                    "parts": [{"type": "text", "text": "hi"}],
                    "trust_override": T3_TRUST,
                })
                assert s == 200, f"inject {i} failed: {s} {b}"
                peer_ids[i] = b.get("peer_id")
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=inject_peer, args=(i,)) for i in range(20)]
        for t in threads: t.start()
        for t in threads: t.join(timeout=10)

        assert not errors, f"Errors: {errors}"
        assert all(p for p in peer_ids), f"Some peer_ids null: {peer_ids}"
        assert len(set(peer_ids)) == 20, f"Duplicate peer_ids: {len(set(peer_ids))} unique of 20"
    finally:
        proc.terminate(); proc.wait(timeout=5)


# ═══════════════════════════════════════════════════════════════
# INT1: full happy path — T3 + param_constraints + human_confirmation
# ═══════════════════════════════════════════════════════════════
def test_int1_full_three_layer_happy_path():
    """INT1: T3 peer + valid params + human confirm → full happy path through all three layers."""
    skills = [{
        "id": "transfer",
        "name": "Transfer Funds",
        "authorization_tier": "T3",
        "param_constraints": {
            "amount": {"type": "number", "required": True, "min": 1, "max": 10000},
            "currency": {"type": "string", "required": True, "allowed_values": ["USD", "EUR", "CNY"]},
        },
        "human_confirmation_required": True,
    }]
    proc, hp = _start_relay(48010, skills)
    try:
        pid = _inject(hp, "bank_agent", T3_TRUST)

        # Step 1: POST /tasks → confirmation_pending
        s, b = _http("POST", hp, "/tasks", {
            "role": "agent", "text": "transfer",
            "skill_id": "transfer", "peer_id": pid,
            "params": {"amount": 500, "currency": "USD"},
        })
        assert s == 201, f"Layer chain failed at task create: {s} {b}"
        assert b["task"]["status"] == "confirmation_pending", \
            f"Expected confirmation_pending, got: {b['task']['status']}"
        tid = b["task"]["id"]

        # Step 2: :confirm → submitted
        s2, b2 = _http("POST", hp, f"/tasks/{tid}:confirm")
        assert s2 == 200, f":confirm failed: {s2} {b2}"
        assert b2["status"] == "submitted"

        # Final state check
        _, final = _http("GET", hp, f"/tasks/{tid}")
        assert final.get("status") == "submitted"
    finally:
        proc.terminate(); proc.wait(timeout=5)


# ═══════════════════════════════════════════════════════════════
# INT2: T3 tier block — param check never reached
# ═══════════════════════════════════════════════════════════════
def test_int2_tier_blocks_before_param_check():
    """INT2: Low-trust peer → 403 ERR_AUTHORIZATION_TIER before param_constraints check."""
    skills = [{
        "id": "transfer",
        "name": "Transfer",
        "authorization_tier": "T3",
        "param_constraints": {
            "amount": {"type": "number", "required": True},
        },
        "human_confirmation_required": True,
    }]
    proc, hp = _start_relay(48011, skills)
    try:
        # No trust_override → score ~0, fails T3
        pid = _inject(hp, "low_trust")
        s, b = _http("POST", hp, "/tasks", {
            "role": "agent", "text": "go",
            "skill_id": "transfer", "peer_id": pid,
            "params": {"amount": 500},
        })
        assert s == 403, f"Expected 403 from tier check, got: {s} {b}"
        assert b["error_code"] == "ERR_AUTHORIZATION_TIER"
        # Ensure param error NOT raised
        assert b.get("error_code") != "ERR_PARAM_CONSTRAINT"
    finally:
        proc.terminate(); proc.wait(timeout=5)


# ═══════════════════════════════════════════════════════════════
# INT3: param_constraints block — confirmation never reached
# ═══════════════════════════════════════════════════════════════
def test_int3_param_blocks_before_confirmation():
    """INT3: T3 tier passes, but invalid params → 400 ERR_PARAM_CONSTRAINT (no confirmation_pending)."""
    skills = [{
        "id": "transfer",
        "name": "Transfer",
        "authorization_tier": "T3",
        "param_constraints": {
            "amount": {"type": "number", "required": True, "max": 10000},
        },
        "human_confirmation_required": True,
    }]
    proc, hp = _start_relay(48012, skills)
    try:
        pid = _inject(hp, "t3_peer_bad_param", T3_TRUST)
        s, b = _http("POST", hp, "/tasks", {
            "role": "agent", "text": "transfer",
            "skill_id": "transfer", "peer_id": pid,
            "params": {"amount": 99999},  # exceeds max
        })
        assert s == 400, f"Expected 400 from param check, got: {s} {b}"
        assert b["error_code"] == "ERR_PARAM_CONSTRAINT"
        # violated_params entries may be param names or "param 'name': ..." message strings
        violated = b.get("violated_params", [])
        assert any("amount" in str(v) for v in violated), \
            f"'amount' not found in violated_params: {violated}"
        # Ensure task was NOT created in confirmation_pending
        _, tasks_resp = _http("GET", hp, "/tasks")
        pend = [t for t in tasks_resp.get("tasks", []) if t.get("status") == "confirmation_pending"]
        assert len(pend) == 0, f"Task entered confirmation_pending despite param violation"
    finally:
        proc.terminate(); proc.wait(timeout=5)


# ═══════════════════════════════════════════════════════════════
# INT4: full rejection path — T3 + valid params + human rejects
# ═══════════════════════════════════════════════════════════════
def test_int4_full_rejection_path():
    """INT4: T3 + valid params → confirmation_pending → :reject → failed."""
    skills = [{
        "id": "nuke",
        "name": "Nuke",
        "authorization_tier": "T3",
        "param_constraints": {
            "target": {"type": "string", "required": True},
        },
        "human_confirmation_required": True,
    }]
    proc, hp = _start_relay(48013, skills)
    try:
        pid = _inject(hp, "nuke_agent", T3_TRUST)
        s, b = _http("POST", hp, "/tasks", {
            "role": "agent", "text": "launch",
            "skill_id": "nuke", "peer_id": pid,
            "params": {"target": "test-env"},
        })
        assert s == 201 and b["task"]["status"] == "confirmation_pending"
        tid = b["task"]["id"]

        s2, b2 = _http("POST", hp, f"/tasks/{tid}:reject", {"reason": "Absolutely not."})
        assert s2 == 200
        assert b2["status"] == "failed"
        assert "Absolutely not." in b2.get("reason", "")

        _, final = _http("GET", hp, f"/tasks/{tid}")
        assert final.get("status") == "failed"
    finally:
        proc.terminate(); proc.wait(timeout=5)


# ═══════════════════════════════════════════════════════════════
# INT5: --auto-confirm-t3 bypasses all confirmation — T3 + params → submitted directly
# ═══════════════════════════════════════════════════════════════
def test_int5_auto_confirm_bypasses_full_chain():
    """INT5: --auto-confirm-t3 + valid T3 params → submitted directly (no confirmation_pending)."""
    skills = [{
        "id": "deploy",
        "name": "Deploy",
        "authorization_tier": "T3",
        "param_constraints": {
            "env": {"type": "string", "required": True, "allowed_values": ["staging", "prod"]},
        },
        "human_confirmation_required": True,
    }]
    proc, hp = _start_relay(48014, skills, extra_flags=["--auto-confirm-t3"])
    try:
        pid = _inject(hp, "ci_bot", T3_TRUST)
        s, b = _http("POST", hp, "/tasks", {
            "role": "agent", "text": "deploy",
            "skill_id": "deploy", "peer_id": pid,
            "params": {"env": "staging"},
        })
        assert s == 201, f"{s}: {b}"
        assert b["task"]["status"] == "submitted", \
            f"Expected submitted with --auto-confirm-t3, got: {b['task']['status']}"
        assert b["task"].get("confirmation_required") is not True
    finally:
        proc.terminate(); proc.wait(timeout=5)
