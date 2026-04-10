"""
tests/test_task_queue_v298.py — v2.98: POST /tasks/queue async task enqueue
Tests: TQ1–TQ9

TQ1: GET /tasks/queue returns 200 with empty queue on startup
TQ2: POST /tasks/queue returns 202 with task_id, status=submitted, poll_url, sse_url
TQ3: POST /tasks/queue without role returns 400 ERR_INVALID_REQUEST
TQ4: GET /tasks/queue after enqueue shows queue_depth == 1
TQ5: POST /tasks/queue — task appears in GET /tasks/{id}
TQ6: POST /tasks/queue — multiple enqueues increment queue_depth
TQ7: capabilities.async_task_queue == True in AgentCard
TQ8: task_queue appears in API map (/.well-known/acp.json)
TQ9: POST /tasks/queue — queue_originated flag set on task
"""

import json
import os
import subprocess
import sys
import time
import urllib.request

RELAY = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")


def _get_free_port():
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_relay(ws_port):
    """HTTP port = ws_port + 100."""
    cmd = [
        sys.executable, RELAY,
        "--port", str(ws_port),
        "--http-host", "127.0.0.1",
        "--local-only",
        "--test-mode",
        "--no-identity",
    ]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _hp(ws_port):
    return ws_port + 100


def _wait_ready(ws_port, timeout=10.0):
    hp = _hp(ws_port)
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{hp}/status", timeout=1)
            return True
        except Exception:
            time.sleep(0.2)
    return False


def _get(ws_port, path):
    hp = _hp(ws_port)
    resp = urllib.request.urlopen(f"http://127.0.0.1:{hp}{path}", timeout=5)
    return resp.status, json.loads(resp.read())


def _post(ws_port, path, body):
    hp = _hp(ws_port)
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{hp}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=5)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


# ─── Shared fixture ────────────────────────────────────────────────────────────

class TestTaskQueue:

    def setup_method(self):
        self.ws_port = _get_free_port()
        self.proc = _start_relay(self.ws_port)
        assert _wait_ready(self.ws_port), "Relay did not start"

    def teardown_method(self):
        self.proc.terminate()
        self.proc.wait()

    # TQ1 ──────────────────────────────────────────────────────────────────────

    def test_tq1_get_empty_queue(self):
        """TQ1: GET /tasks/queue returns 200 with empty queue on startup."""
        status, body = _get(self.ws_port, "/tasks/queue")
        assert status == 200
        assert body["ok"] is True
        assert body["queue_depth"] == 0
        assert body["tasks"] == []

    # TQ2 ──────────────────────────────────────────────────────────────────────

    def test_tq2_post_returns_202(self):
        """TQ2: POST /tasks/queue returns 202 with required fields."""
        status, body = _post(self.ws_port, "/tasks/queue", {
            "role": "agent",
            "skill_id": "test-skill",
            "payload": {"action": "hello"},
        })
        assert status == 202, f"Expected 202, got {status}: {body}"
        assert body["ok"] is True
        assert "task_id" in body
        assert body["status"] == "submitted"
        assert "poll_url" in body
        assert "sse_url" in body
        assert "queued_at" in body
        assert body["task_id"] in body["poll_url"]

    # TQ3 ──────────────────────────────────────────────────────────────────────

    def test_tq3_missing_role_returns_400(self):
        """TQ3: POST /tasks/queue without role returns 400."""
        status, body = _post(self.ws_port, "/tasks/queue", {
            "skill_id": "test-skill",
            "payload": {"action": "oops"},
        })
        assert status == 400, f"Expected 400, got {status}: {body}"
        assert "error" in body or body.get("ok") is False

    # TQ4 ──────────────────────────────────────────────────────────────────────

    def test_tq4_queue_depth_after_enqueue(self):
        """TQ4: GET /tasks/queue after enqueue shows queue_depth == 1."""
        _post(self.ws_port, "/tasks/queue", {"role": "agent", "payload": {"x": 1}})
        _, body = _get(self.ws_port, "/tasks/queue")
        assert body["queue_depth"] == 1, f"Expected depth 1, got {body['queue_depth']}"
        assert len(body["tasks"]) == 1

    # TQ5 ──────────────────────────────────────────────────────────────────────

    def test_tq5_task_accessible_via_tasks_id(self):
        """TQ5: Enqueued task visible via GET /tasks/{id}."""
        _, enq = _post(self.ws_port, "/tasks/queue", {
            "role": "agent",
            "skill_id": "s1",
            "payload": {"action": "ping"},
        })
        task_id = enq["task_id"]
        status, body = _get(self.ws_port, f"/tasks/{task_id}")
        assert status == 200, f"Expected 200, got {status}"
        assert body.get("id") == task_id or body.get("task_id") == task_id
        t_status = body.get("status") or (body.get("task") or {}).get("status")
        assert t_status == "submitted", f"Expected submitted, got {t_status}"

    # TQ6 ──────────────────────────────────────────────────────────────────────

    def test_tq6_multiple_enqueues_increment_depth(self):
        """TQ6: Three enqueues → queue_depth == 3."""
        for i in range(3):
            _post(self.ws_port, "/tasks/queue", {
                "role": "agent", "payload": {"idx": i}
            })
        _, body = _get(self.ws_port, "/tasks/queue")
        assert body["queue_depth"] == 3, f"Expected 3, got {body['queue_depth']}"

    # TQ7 ──────────────────────────────────────────────────────────────────────

    def test_tq7_capability_flag(self):
        """TQ7: capabilities.async_task_queue == True."""
        _, card = _get(self.ws_port, "/.well-known/acp.json")
        caps = card.get("self", card).get("capabilities", {})
        assert caps.get("async_task_queue") is True, \
            f"Expected capabilities.async_task_queue=True, got {caps.get('async_task_queue')}"

    # TQ8 ──────────────────────────────────────────────────────────────────────

    def test_tq8_api_map_entry(self):
        """TQ8: task_queue appears in API map."""
        _, card = _get(self.ws_port, "/.well-known/acp.json")
        self_card = card.get("self", card)
        # API map may be at top-level or under 'endpoints'
        endpoints = self_card.get("endpoints", self_card)
        # Also check status endpoint
        _, status = _get(self.ws_port, "/status")
        api_map = status.get("api_map", {})
        found = "task_queue" in api_map or "task_queue" in endpoints
        assert found, f"task_queue not found in api_map={api_map} or endpoints={endpoints}"

    # TQ9 ──────────────────────────────────────────────────────────────────────

    def test_tq9_queue_originated_flag(self):
        """TQ9: queue_originated flag set in GET /tasks/queue listing."""
        _post(self.ws_port, "/tasks/queue", {
            "role": "agent", "payload": {"flag_test": True}
        })
        _, body = _get(self.ws_port, "/tasks/queue")
        tasks = body.get("tasks", [])
        assert len(tasks) == 1
        assert tasks[0].get("queue_originated") is True, \
            f"Expected queue_originated=True, got {tasks[0]}"
