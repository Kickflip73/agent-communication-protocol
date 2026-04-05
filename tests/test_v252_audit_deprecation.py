"""
test_v252_audit_deprecation.py — v2.52 feature tests

Test IDs:
  AUD1–AUD10  — task audit_log creation, state transitions, :confirm/:reject audit entries,
                 GET /tasks/{id}/audit-log endpoint, since_seq filtering
  DEP1–DEP6   — skill.deprecation_notice: POST /tasks deprecation_warning injection,
                 active skill no warning, missing fields tolerated, list endpoint
"""

import json
import time
import threading
import subprocess
import urllib.request
import urllib.error
import os
import sys

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
           "--port", str(ws_port), "--name", "AuditRelay",
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


T3_TRUST = {
    "card_sig_valid": True, "did_consistent": True,
    "ping_rtt_ms": 20, "message_count": 150, "verified_identity": True,
}


def _inject(hp, name, trust=None):
    body = {"from": name, "parts": [{"type": "text", "text": "hi"}]}
    if trust:
        body["trust_override"] = trust
    s, b = _http("POST", hp, "/debug/inject", body)
    assert s == 200, f"inject failed: {s} {b}"
    return b["peer_id"]


# ═══════════════════════════════════════════════════════════════
# AUD1: audit_log present on task creation
# ═══════════════════════════════════════════════════════════════
def test_aud1_audit_log_on_creation():
    """AUD1: task created via POST /tasks has audit_log with at least one 'created' entry."""
    proc, hp = _start_relay(49000, [{"id": "sk", "name": "SK"}])
    try:
        s, b = _http("POST", hp, "/tasks", {"role": "agent", "text": "hello", "skill_id": "sk"})
        assert s == 201
        task = b["task"]
        assert "audit_log" in task, "audit_log missing from task"
        assert len(task["audit_log"]) >= 1
        created = task["audit_log"][0]
        assert created["event"] == "created"
        assert "ts" in created
        assert created["seq"] == 0
    finally:
        proc.terminate(); proc.wait(timeout=5)


# ═══════════════════════════════════════════════════════════════
# AUD2: skill_invoked audit entry when skill_id provided
# ═══════════════════════════════════════════════════════════════
def test_aud2_skill_invoked_audit_entry():
    """AUD2: POST /tasks with skill_id records 'skill_invoked' entry in audit_log."""
    proc, hp = _start_relay(49001, [{"id": "writer", "name": "Writer"}])
    try:
        s, b = _http("POST", hp, "/tasks", {"role": "agent", "text": "write", "skill_id": "writer"})
        assert s == 201
        audit = b["task"]["audit_log"]
        events = [e["event"] for e in audit]
        assert "skill_invoked" in events, f"skill_invoked not in audit_log events: {events}"
        inv = next(e for e in audit if e["event"] == "skill_invoked")
        assert inv["detail"]["skill_id"] == "writer"
    finally:
        proc.terminate(); proc.wait(timeout=5)


# ═══════════════════════════════════════════════════════════════
# AUD3: GET /tasks/{id}/audit-log returns audit trail
# ═══════════════════════════════════════════════════════════════
def test_aud3_get_audit_log_endpoint():
    """AUD3: GET /tasks/{id}/audit-log returns {task_id, status, audit_log, total}."""
    proc, hp = _start_relay(49002, [{"id": "sk", "name": "SK"}])
    try:
        _, cr = _http("POST", hp, "/tasks", {"role": "agent", "text": "test", "skill_id": "sk"})
        tid = cr["task"]["id"]

        s, b = _http("GET", hp, f"/tasks/{tid}/audit-log")
        assert s == 200, f"Expected 200, got {s}: {b}"
        assert b["task_id"] == tid
        assert "status" in b
        assert "audit_log" in b
        assert isinstance(b["audit_log"], list)
        assert b["total"] >= 1
    finally:
        proc.terminate(); proc.wait(timeout=5)


# ═══════════════════════════════════════════════════════════════
# AUD4: audit-log 404 for non-existent task
# ═══════════════════════════════════════════════════════════════
def test_aud4_audit_log_404_unknown_task():
    """AUD4: GET /tasks/nonexistent/audit-log returns 404."""
    proc, hp = _start_relay(49003, [])
    try:
        s, b = _http("GET", hp, "/tasks/task_does_not_exist/audit-log")
        assert s == 404, f"Expected 404, got {s}"
    finally:
        proc.terminate(); proc.wait(timeout=5)


# ═══════════════════════════════════════════════════════════════
# AUD5: state transitions recorded in audit_log
# ═══════════════════════════════════════════════════════════════
def test_aud5_state_transitions_in_audit_log():
    """AUD5: _update_task state changes are recorded as 'status_changed' in audit_log."""
    proc, hp = _start_relay(49004, [{"id": "sk", "name": "SK"}])
    try:
        _, cr = _http("POST", hp, "/tasks", {"role": "agent", "text": "work", "skill_id": "sk"})
        tid = cr["task"]["id"]

        # Manually advance task via /update endpoint
        _http("POST", hp, f"/tasks/{tid}:update", {"status": "working"})
        _http("POST", hp, f"/tasks/{tid}:update", {"status": "completed"})

        _, b = _http("GET", hp, f"/tasks/{tid}/audit-log")
        events = [e["event"] for e in b["audit_log"]]
        assert "status_changed" in events, f"status_changed not found: {events}"
        transitions = [e for e in b["audit_log"] if e["event"] == "status_changed"]
        assert len(transitions) >= 1
        # At least one transition should show "to" field
        assert any("to" in e.get("detail", {}) for e in transitions)
    finally:
        proc.terminate(); proc.wait(timeout=5)


# ═══════════════════════════════════════════════════════════════
# AUD6: :confirm records 'confirmed' audit entry
# ═══════════════════════════════════════════════════════════════
def test_aud6_confirm_records_audit_entry():
    """AUD6: POST /tasks/{id}:confirm records 'confirmed' audit entry."""
    proc, hp = _start_relay(49005, [
        {"id": "dep", "name": "Deploy", "authorization_tier": "T3", "human_confirmation_required": True}
    ])
    try:
        pid = _inject(hp, "auditor", T3_TRUST)
        _, cr = _http("POST", hp, "/tasks", {
            "role": "agent", "text": "deploy", "skill_id": "dep", "peer_id": pid,
        })
        tid = cr["task"]["id"]
        assert cr["task"]["status"] == "confirmation_pending"

        _http("POST", hp, f"/tasks/{tid}:confirm")

        _, b = _http("GET", hp, f"/tasks/{tid}/audit-log")
        events = [e["event"] for e in b["audit_log"]]
        assert "confirmed" in events, f"'confirmed' not in audit_log: {events}"
        confirmed_entry = next(e for e in b["audit_log"] if e["event"] == "confirmed")
        assert confirmed_entry["detail"]["by"] == "human"
    finally:
        proc.terminate(); proc.wait(timeout=5)


# ═══════════════════════════════════════════════════════════════
# AUD7: :reject records 'rejected' audit entry with reason
# ═══════════════════════════════════════════════════════════════
def test_aud7_reject_records_audit_entry():
    """AUD7: POST /tasks/{id}:reject records 'rejected' audit entry with reason."""
    proc, hp = _start_relay(49006, [
        {"id": "nuke", "name": "Nuke", "authorization_tier": "T3", "human_confirmation_required": True}
    ])
    try:
        pid = _inject(hp, "auditor2", T3_TRUST)
        _, cr = _http("POST", hp, "/tasks", {
            "role": "agent", "text": "launch", "skill_id": "nuke", "peer_id": pid,
        })
        tid = cr["task"]["id"]

        _http("POST", hp, f"/tasks/{tid}:reject", {"reason": "Classified mission abort"})

        _, b = _http("GET", hp, f"/tasks/{tid}/audit-log")
        events = [e["event"] for e in b["audit_log"]]
        assert "rejected" in events, f"'rejected' not in audit_log: {events}"
        rej_entry = next(e for e in b["audit_log"] if e["event"] == "rejected")
        assert "Classified mission abort" in rej_entry["detail"].get("reason", "")
    finally:
        proc.terminate(); proc.wait(timeout=5)


# ═══════════════════════════════════════════════════════════════
# AUD8: since_seq filtering on GET /tasks/{id}/audit-log
# ═══════════════════════════════════════════════════════════════
def test_aud8_audit_log_since_seq_filter():
    """AUD8: GET /tasks/{id}/audit-log?since_seq=N returns only entries with seq > N."""
    proc, hp = _start_relay(49007, [{"id": "sk", "name": "SK"}])
    try:
        _, cr = _http("POST", hp, "/tasks", {"role": "agent", "text": "test", "skill_id": "sk"})
        tid = cr["task"]["id"]

        # Get full log first
        _, full = _http("GET", hp, f"/tasks/{tid}/audit-log")
        total = full["total"]

        # Request with since_seq=0 — should return only entries with seq > 0
        _, filtered = _http("GET", hp, f"/tasks/{tid}/audit-log?since_seq=0")
        for entry in filtered["audit_log"]:
            assert entry["seq"] > 0, f"Entry with seq <= 0 returned after since_seq=0 filter: {entry}"

        # since_seq >= total — should return empty
        _, empty = _http("GET", hp, f"/tasks/{tid}/audit-log?since_seq={total + 100}")
        assert empty["audit_log"] == [], f"Expected empty, got: {empty['audit_log']}"
    finally:
        proc.terminate(); proc.wait(timeout=5)


# ═══════════════════════════════════════════════════════════════
# AUD9: audit_log entries have monotonically increasing seq
# ═══════════════════════════════════════════════════════════════
def test_aud9_audit_log_monotonic_seq():
    """AUD9: All audit_log entries have strictly increasing seq numbers."""
    proc, hp = _start_relay(49008, [{"id": "sk", "name": "SK"}])
    try:
        _, cr = _http("POST", hp, "/tasks", {"role": "agent", "text": "seq-test", "skill_id": "sk"})
        tid = cr["task"]["id"]
        _http("POST", hp, f"/tasks/{tid}:update", {"status": "working"})
        _http("POST", hp, f"/tasks/{tid}:update", {"status": "completed"})

        _, b = _http("GET", hp, f"/tasks/{tid}/audit-log")
        seqs = [e["seq"] for e in b["audit_log"]]
        assert seqs == sorted(seqs), f"seq not monotonically increasing: {seqs}"
        assert len(set(seqs)) == len(seqs), f"Duplicate seq values: {seqs}"
    finally:
        proc.terminate(); proc.wait(timeout=5)


# ═══════════════════════════════════════════════════════════════
# AUD10: audit_log is included in GET /tasks/{id} task object
# ═══════════════════════════════════════════════════════════════
def test_aud10_audit_log_in_task_object():
    """AUD10: GET /tasks/{id} response includes audit_log field."""
    proc, hp = _start_relay(49009, [{"id": "sk", "name": "SK"}])
    try:
        _, cr = _http("POST", hp, "/tasks", {"role": "agent", "text": "check", "skill_id": "sk"})
        tid = cr["task"]["id"]

        s, b = _http("GET", hp, f"/tasks/{tid}")
        assert s == 200
        assert "audit_log" in b, f"audit_log missing from GET /tasks/{tid}: {list(b.keys())}"
        assert isinstance(b["audit_log"], list)
    finally:
        proc.terminate(); proc.wait(timeout=5)


# ═══════════════════════════════════════════════════════════════
# DEP1: POST /tasks on deprecated skill returns deprecation_warning
# ═══════════════════════════════════════════════════════════════
def test_dep1_deprecated_skill_returns_warning():
    """DEP1: POST /tasks targeting a deprecated skill returns 201 with deprecation_warning."""
    skills = [{
        "id": "old_transfer",
        "name": "Old Transfer",
        "deprecation_notice": {
            "deprecated": True,
            "deprecated_since": "2026-03-01",
            "sunset_at": "2026-06-01",
            "replacement_skill": "transfer_v2",
            "message": "Use transfer_v2 instead.",
        }
    }]
    proc, hp = _start_relay(49010, skills)
    try:
        s, b = _http("POST", hp, "/tasks", {
            "role": "agent", "text": "transfer", "skill_id": "old_transfer"
        })
        assert s == 201, f"Expected 201, got {s}: {b}"
        assert "task" in b, "task missing from response"
        assert "deprecation_warning" in b, f"deprecation_warning missing from response: {list(b.keys())}"
        dw = b["deprecation_warning"]
        assert dw["deprecated"] is True
        assert dw["replacement_skill"] == "transfer_v2"
        assert dw["sunset_at"] == "2026-06-01"
        assert "transfer_v2" in dw["message"]
    finally:
        proc.terminate(); proc.wait(timeout=5)


# ═══════════════════════════════════════════════════════════════
# DEP2: POST /tasks on active skill has NO deprecation_warning
# ═══════════════════════════════════════════════════════════════
def test_dep2_active_skill_no_deprecation_warning():
    """DEP2: POST /tasks on non-deprecated skill does NOT include deprecation_warning."""
    proc, hp = _start_relay(49011, [{"id": "active", "name": "Active Skill"}])
    try:
        s, b = _http("POST", hp, "/tasks", {
            "role": "agent", "text": "run", "skill_id": "active"
        })
        assert s == 201
        assert "deprecation_warning" not in b, \
            f"Unexpected deprecation_warning for active skill: {b.get('deprecation_warning')}"
    finally:
        proc.terminate(); proc.wait(timeout=5)


# ═══════════════════════════════════════════════════════════════
# DEP3: task is still created (201) even when skill is deprecated
# ═══════════════════════════════════════════════════════════════
def test_dep3_deprecated_skill_task_still_created():
    """DEP3: Deprecated skill does not block task creation — task must be returned."""
    skills = [{
        "id": "legacy_api",
        "name": "Legacy API",
        "deprecation_notice": {"deprecated": True, "message": "Migrate to v2."}
    }]
    proc, hp = _start_relay(49012, skills)
    try:
        s, b = _http("POST", hp, "/tasks", {
            "role": "agent", "text": "call legacy", "skill_id": "legacy_api"
        })
        assert s == 201
        assert "task" in b
        assert b["task"]["id"].startswith("task_")
        assert b["task"]["status"] in ("submitted", "confirmation_pending")
    finally:
        proc.terminate(); proc.wait(timeout=5)


# ═══════════════════════════════════════════════════════════════
# DEP4: deprecation_notice with deprecated=false → no warning
# ═══════════════════════════════════════════════════════════════
def test_dep4_deprecation_false_no_warning():
    """DEP4: skill with deprecation_notice.deprecated=false does NOT emit deprecation_warning."""
    skills = [{
        "id": "soon_deprecated",
        "name": "Soon Deprecated",
        "deprecation_notice": {"deprecated": False, "message": "Will be deprecated in Q3."}
    }]
    proc, hp = _start_relay(49013, skills)
    try:
        s, b = _http("POST", hp, "/tasks", {
            "role": "agent", "text": "use skill", "skill_id": "soon_deprecated"
        })
        assert s == 201
        assert "deprecation_warning" not in b, \
            f"Unexpected deprecation_warning when deprecated=false: {b.get('deprecation_warning')}"
    finally:
        proc.terminate(); proc.wait(timeout=5)


# ═══════════════════════════════════════════════════════════════
# DEP5: deprecated skill in GET /skills includes deprecation_notice
# ═══════════════════════════════════════════════════════════════
def test_dep5_deprecated_skill_visible_in_skills_list():
    """DEP5: GET /skills includes deprecation_notice field for deprecated skills."""
    skills = [{
        "id": "old_sk",
        "name": "Old Skill",
        "deprecation_notice": {
            "deprecated": True,
            "replacement_skill": "new_sk",
            "message": "Use new_sk.",
        }
    }]
    proc, hp = _start_relay(49014, skills)
    try:
        s, b = _http("GET", hp, "/skills")
        assert s == 200
        skill_list = b.get("skills", [])
        old_sk = next((sk for sk in skill_list if sk.get("id") == "old_sk"), None)
        assert old_sk is not None, f"old_sk not found in /skills: {skill_list}"
        assert "deprecation_notice" in old_sk, \
            f"deprecation_notice missing from skill object: {list(old_sk.keys())}"
        assert old_sk["deprecation_notice"]["deprecated"] is True
    finally:
        proc.terminate(); proc.wait(timeout=5)


# ═══════════════════════════════════════════════════════════════
# DEP6: deprecated T3 skill — deprecation_warning + confirmation_pending together
# ═══════════════════════════════════════════════════════════════
def test_dep6_deprecated_t3_skill_warning_and_confirmation():
    """DEP6: Deprecated T3 skill with human_confirmation_required → both deprecation_warning AND confirmation_pending."""
    skills = [{
        "id": "legacy_deploy",
        "name": "Legacy Deploy",
        "authorization_tier": "T3",
        "human_confirmation_required": True,
        "deprecation_notice": {
            "deprecated": True,
            "replacement_skill": "deploy_v2",
            "message": "Migrate to deploy_v2.",
        }
    }]
    proc, hp = _start_relay(49015, skills)
    try:
        pid = _inject(hp, "legacy_caller", T3_TRUST)
        s, b = _http("POST", hp, "/tasks", {
            "role": "agent", "text": "deploy legacy", "skill_id": "legacy_deploy", "peer_id": pid,
        })
        assert s == 201, f"{s}: {b}"
        assert b["task"]["status"] == "confirmation_pending", \
            f"Expected confirmation_pending, got: {b['task']['status']}"
        assert "deprecation_warning" in b, \
            f"deprecation_warning missing alongside confirmation_pending: {list(b.keys())}"
        assert b["deprecation_warning"]["replacement_skill"] == "deploy_v2"
    finally:
        proc.terminate(); proc.wait(timeout=5)
