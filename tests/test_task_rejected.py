"""
test_task_rejected.py — ACP v2.66 Task `rejected` terminal state tests

RJ-1  : VERSION >= 2.66.0 (rejected_state feature present)
RJ-2  : POST /tasks/{id}:agent-reject transitions non-terminal task → rejected
RJ-3  : POST /tasks/{id}:agent-reject on already-terminal task returns ok + note
RJ-4  : POST /tasks/{id}:agent-reject on unknown task returns 404
RJ-5  : POST /tasks/{id}:agent-reject accepts custom reason + reject_code in response
RJ-6  : GET /tasks/{id} after agent-reject shows status=rejected
RJ-7  : GET /tasks?status=rejected filters correctly
RJ-8  : T3 :reject endpoint now transitions confirmation_pending → rejected (not failed)
RJ-9  : rejected task cannot be re-activated (terminal guard — second reject returns note)
RJ-10 : AgentCard capabilities.rejected_state = True
"""

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

# ── constants ─────────────────────────────────────────────────────────────────

RELAY_PY = str(Path(__file__).parent.parent / "relay" / "acp_relay.py")
WS_PORT   = 47350
HTTP_PORT = WS_PORT + 100


# ── helpers ───────────────────────────────────────────────────────────────────

def _wait_ready(port, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/status", timeout=2
            ) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def _kill_port(port):
    try:
        result = subprocess.run(
            ["ss", "-tlnp", f"sport = :{port}"],
            capture_output=True, text=True, timeout=3,
        )
        for line in result.stdout.splitlines():
            if f":{port}" in line and "pid=" in line:
                pid_str = line.split("pid=")[1].split(",")[0]
                try:
                    os.kill(int(pid_str), 9)
                except Exception:
                    pass
    except Exception:
        pass
    time.sleep(0.3)


def _get(url):
    with urllib.request.urlopen(url, timeout=8) as r:
        return json.loads(r.read())


def _post(http_port, path, body=None):
    url  = f"http://127.0.0.1:{http_port}{path}"
    data = json.dumps(body or {}).encode()
    req  = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _create_task(http_port, skill=None):
    """Create a task via /tasks/create; returns the task dict (with 'id' key)."""
    payload = {
        "role": "user",
        "parts": [{"type": "text", "content": "rj-test input"}],
    }
    if skill:
        payload["skill"] = skill
    code, body = _post(http_port, "/tasks/create", payload)
    assert code in (200, 201), f"create_task failed: {code} {body}"
    return body["task"]


# ── fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def relay():
    _kill_port(WS_PORT)
    _kill_port(HTTP_PORT)
    env = os.environ.copy()
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        env.pop(k, None)
    proc = subprocess.Popen(
        [sys.executable, RELAY_PY,
         "--port", str(WS_PORT), "--name", "RJRelay",
         "--local-only", "--test-mode"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
    )
    for s in (proc.stdout, proc.stderr):
        threading.Thread(target=lambda x=s: x.read(), daemon=True).start()
    assert _wait_ready(HTTP_PORT), f"relay on :{HTTP_PORT} did not start"
    yield HTTP_PORT
    proc.terminate()
    proc.wait(timeout=5)


# ── tests ─────────────────────────────────────────────────────────────────────

class TestTaskRejected:

    def test_rj1_version_gte_266(self, relay):
        """RJ-1: VERSION >= 2.66.0 (rejected_state feature present)."""
        data = _get(f"http://127.0.0.1:{relay}/status")
        version = data.get("acp_version", "")
        from packaging.version import Version
        assert Version(version) >= Version("2.66.0"), \
            f"Expected >= 2.66.0, got {version}"

    def test_rj2_agent_reject_transitions_to_rejected(self, relay):
        """RJ-2: POST /tasks/{id}:agent-reject on non-terminal task → rejected."""
        task = _create_task(relay)
        task_id = task["id"]

        # Check current status; skip if already terminal
        info = _get(f"http://127.0.0.1:{relay}/tasks/{task_id}")
        if info["status"] in ("completed", "failed", "canceled", "rejected"):
            pytest.skip("task completed too fast to reject")

        code, resp = _post(relay, f"/tasks/{task_id}:agent-reject",
                           {"reason": "rj2 test rejection"})
        assert code == 200, f"Expected 200, got {code}: {resp}"
        assert resp.get("ok") is True
        assert resp.get("status") == "rejected", \
            f"Expected 'rejected', got: {resp.get('status')}"

    def test_rj3_agent_reject_on_terminal_returns_ok_with_note(self, relay):
        """RJ-3: :agent-reject on already-terminal task (rejected) returns ok + note."""
        task = _create_task(relay)
        task_id = task["id"]
        time.sleep(0.1)

        # First rejection: bring task to rejected terminal state
        code1, resp1 = _post(relay, f"/tasks/{task_id}:agent-reject",
                             {"reason": "first rejection"})
        assert code1 == 200

        if resp1.get("note"):
            # Task was already terminal (e.g. completed); verify idempotent note
            code2, resp2 = _post(relay, f"/tasks/{task_id}:agent-reject",
                                 {"reason": "second rejection"})
            assert code2 == 200
            assert resp2.get("ok") is True
            assert "already in terminal state" in resp2.get("note", ""), \
                f"Expected terminal-state note, got: {resp2}"
            return

        assert resp1.get("status") == "rejected"

        # Second rejection on now-terminal rejected task → must return ok + note
        code2, resp2 = _post(relay, f"/tasks/{task_id}:agent-reject",
                             {"reason": "already rejected"})
        assert code2 == 200
        assert resp2.get("ok") is True
        assert resp2.get("status") == "rejected"
        assert "already in terminal state" in resp2.get("note", ""), \
            f"Expected 'already in terminal state' note, got: {resp2}"

    def test_rj4_agent_reject_unknown_task_returns_404(self, relay):
        """RJ-4: :agent-reject on unknown task_id → 404."""
        code, body = _post(relay, "/tasks/nonexistent-task-xyz-rj4:agent-reject",
                           {"reason": "test"})
        assert code == 404, f"Expected 404, got {code}: {body}"

    def test_rj5_agent_reject_custom_reason_and_code(self, relay):
        """RJ-5: :agent-reject returns custom reason + reject_code."""
        task = _create_task(relay)
        task_id = task["id"]
        time.sleep(0.1)

        info = _get(f"http://127.0.0.1:{relay}/tasks/{task_id}")
        if info["status"] in ("completed", "failed", "canceled", "rejected"):
            pytest.skip("task completed before test")

        code, resp = _post(relay, f"/tasks/{task_id}:agent-reject", {
            "reason": "skill not available",
            "reject_code": "skill_unavailable",
        })
        assert code == 200
        if resp.get("note"):  # already terminal
            pytest.skip("task became terminal before rejection")
        assert resp.get("ok") is True
        assert resp.get("reason") == "skill not available"
        assert resp.get("reject_code") == "skill_unavailable"
        assert resp.get("status") == "rejected"

    def test_rj6_get_task_after_reject_shows_rejected(self, relay):
        """RJ-6: GET /tasks/{id} after agent-reject shows status=rejected."""
        task = _create_task(relay)
        task_id = task["id"]
        time.sleep(0.1)

        info = _get(f"http://127.0.0.1:{relay}/tasks/{task_id}")
        if info["status"] in ("completed", "failed", "canceled", "rejected"):
            pytest.skip("task completed before test")

        _post(relay, f"/tasks/{task_id}:agent-reject", {"reason": "rj6"})
        info = _get(f"http://127.0.0.1:{relay}/tasks/{task_id}")
        assert info["status"] == "rejected", \
            f"GET /tasks/{task_id} should show 'rejected', got: {info['status']}"

    def test_rj7_list_tasks_filter_by_rejected(self, relay):
        """RJ-7: GET /tasks?status=rejected filters correctly (only rejected tasks returned)."""
        # Create + reject a fresh task
        task = _create_task(relay)
        task_id = task["id"]
        time.sleep(0.1)

        info = _get(f"http://127.0.0.1:{relay}/tasks/{task_id}")
        if info["status"] not in ("completed", "failed", "canceled", "rejected"):
            _post(relay, f"/tasks/{task_id}:agent-reject", {"reason": "rj7 filter test"})

        data = _get(f"http://127.0.0.1:{relay}/tasks?status=rejected")
        tasks = data.get("tasks", [])
        statuses = {t["status"] for t in tasks}
        assert all(s == "rejected" for s in statuses), \
            f"Non-rejected tasks in filter result: {statuses}"

    def test_rj8_t3_reject_endpoint_returns_rejected(self, relay):
        """RJ-8: T3 :reject endpoint transitions confirmation_pending → rejected."""
        # Check if a T3 skill exists that requires human confirmation
        skills_data = _get(f"http://127.0.0.1:{relay}/skills")
        skill_list = skills_data.get("skills", [])
        t3_skill = None
        for s in skill_list:
            sid = s.get("id") or s.get("name") if isinstance(s, dict) else str(s)
            if "human_confirm" in str(sid) or (isinstance(s, dict) and s.get("human_confirmation_required")):
                t3_skill = sid
                break

        if not t3_skill:
            pytest.skip("No T3 human_confirmation skill configured in test-mode relay")

        task = _create_task(relay, skill=t3_skill)
        task_id = task["id"]

        # Wait for confirmation_pending
        reached = False
        for _ in range(20):
            info = _get(f"http://127.0.0.1:{relay}/tasks/{task_id}")
            if info["status"] == "confirmation_pending":
                reached = True
                break
            if info["status"] in ("completed", "failed", "rejected", "canceled"):
                pytest.skip(f"Task reached terminal before confirmation_pending: {info['status']}")
            time.sleep(0.3)

        if not reached:
            pytest.skip("Task did not reach confirmation_pending")

        # T3 :reject → should now yield rejected (not failed)
        code, resp = _post(relay, f"/tasks/{task_id}:reject",
                           {"reason": "rj8 human says no"})
        assert code == 200
        assert resp.get("ok") is True
        assert resp.get("status") == "rejected", \
            f"T3 :reject should yield 'rejected', got: {resp.get('status')}"

        info = _get(f"http://127.0.0.1:{relay}/tasks/{task_id}")
        assert info["status"] == "rejected"

    def test_rj9_rejected_task_cannot_be_reactivated(self, relay):
        """RJ-9: rejected is terminal; second :agent-reject returns note (idempotent)."""
        task = _create_task(relay)
        task_id = task["id"]
        time.sleep(0.1)

        info = _get(f"http://127.0.0.1:{relay}/tasks/{task_id}")
        if info["status"] in ("completed", "failed", "canceled", "rejected"):
            pytest.skip("task already terminal before test")

        # First rejection
        _, r1 = _post(relay, f"/tasks/{task_id}:agent-reject", {"reason": "first"})
        if r1.get("note"):
            pytest.skip("task was already terminal when first rejection attempted")
        assert r1.get("status") == "rejected"

        # Second rejection — must return ok + note, not error
        code, r2 = _post(relay, f"/tasks/{task_id}:agent-reject", {"reason": "second"})
        assert code == 200
        assert r2.get("ok") is True
        assert r2.get("status") == "rejected"
        assert "already in terminal state" in r2.get("note", ""), \
            f"Expected terminal-state note, got: {r2}"

    def test_rj10_agentcard_capabilities_rejected_state(self, relay):
        """RJ-10: AgentCard capabilities.rejected_state == True."""
        data = _get(f"http://127.0.0.1:{relay}/.well-known/acp.json")
        # /.well-known/acp.json has structure {"self": {...}, "peer": {...}}
        card = data.get("self", data)
        caps = card.get("capabilities", {})
        assert caps.get("rejected_state") is True, \
            f"AgentCard should declare rejected_state=True, got: {caps.get('rejected_state')}"
