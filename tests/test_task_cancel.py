"""
test_task_cancel.py — ACP v2.6 Task cancel 语义测试

Tests:
  TC1: :cancel 成功 → 返回 cancelling 中间状态
  TC2: cancelling 中间状态通过 SSE 可被观察到
  TC3: cancelling → canceled 最终转换（SSE 两步事件）
  TC4: 幂等取消 — 已是 cancelling 时重复调用返回 200
  TC5: 幂等取消 — 已是 canceled（terminal）时重复调用返回 200
  TC6: input_required → cancelling → canceled 路径
  TC7: terminal 状态（completed）不能被取消 → 200 + current status
  TC8: 不存在的 task_id → 404
  TC9: AgentCard 声明 task_cancelling=true
  TC10: cancelling 状态下 SSE seq 单调递增
"""

import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from typing import Dict, List, Optional, Any

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RELAY_PATH = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")

TERMINAL_STATES = {"completed", "failed", "canceled"}
CANCELLING_STATE = "cancelling"


# ──────────────────────────────────────────────────────────────────────────────
# Port helpers
# ──────────────────────────────────────────────────────────────────────────────

def _free_port() -> int:
    """Return a free WS port where port+100 is also free (HTTP port)."""
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


WS_PORT  = _free_port()
HTTP_PORT = WS_PORT + 100
BASE_URL  = f"http://127.0.0.1:{HTTP_PORT}"

_proc: Optional[subprocess.Popen] = None


def _clean_env() -> dict:
    env = os.environ.copy()
    for var in ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY",
                "all_proxy", "ALL_PROXY"):
        env.pop(var, None)
    return env


# ──────────────────────────────────────────────────────────────────────────────
# Relay lifecycle fixtures
# ──────────────────────────────────────────────────────────────────────────────

def setup_module(module):
    global _proc
    _proc = subprocess.Popen(
        [sys.executable, RELAY_PATH,
         "--name", "CancelTestAgent",
         "--port", str(WS_PORT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=_clean_env(),
    )
    # Wait for relay to start (HTTP port = WS_PORT + 100)
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"{BASE_URL}/status", timeout=1)
            return
        except Exception:
            time.sleep(0.15)
    raise RuntimeError(f"Relay did not start in time at {BASE_URL}")


def teardown_module(module):
    if _proc:
        _proc.terminate()
        try:
            _proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _proc.kill()
            _proc.wait(timeout=3)


# ──────────────────────────────────────────────────────────────────────────────
# HTTP helpers
# ──────────────────────────────────────────────────────────────────────────────

def _post(path: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{BASE_URL}{path}", data=data,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


def _get(path: str) -> dict:
    with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=5) as r:
        return json.loads(r.read())


def _update_task(task_id: str, body: dict) -> dict:
    """Update a task via POST /tasks/{id}:update."""
    return _post(f"/tasks/{task_id}:update", body)


def _post_status(path: str, body: dict) -> tuple:
    """Returns (status_code, response_dict)."""
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{BASE_URL}{path}", data=data,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _create_task(role="user") -> str:
    """Create a task and return its task_id."""
    resp = _post("/tasks", {
        "role": role,
        "parts": [{"type": "text", "content": "test payload"}],
    })
    assert resp.get("ok"), f"Task creation failed: {resp}"
    return resp["task"]["id"]


def _collect_sse_events(duration: float = 1.5) -> List[Dict[str, Any]]:
    """Connect to /stream, collect SSE events for `duration` seconds.
    
    Uses raw socket recv to avoid urllib's buffering which can delay events.
    """
    events: List[Dict[str, Any]] = []
    stop = threading.Event()

    def _reader():
        try:
            import socket as _socket
            host = "127.0.0.1"
            s = _socket.create_connection((host, HTTP_PORT), timeout=duration + 3)
            s.sendall(b"GET /stream HTTP/1.1\r\nHost: " + host.encode() +
                      b"\r\nConnection: keep-alive\r\n\r\n")
            s.settimeout(0.5)  # short recv timeout so we can check deadline
            buf = b""
            deadline = time.time() + duration
            while time.time() < deadline and not stop.is_set():
                try:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                    # Process all complete SSE lines
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        line = line.rstrip(b"\r")
                        if line.startswith(b"data:"):
                            payload = line[5:].strip()
                            if payload:
                                try:
                                    events.append(json.loads(payload))
                                except json.JSONDecodeError:
                                    pass
                except _socket.timeout:
                    continue
            s.close()
        except Exception:
            pass

    t = threading.Thread(target=_reader, daemon=True)
    t.start()
    return events, stop, t


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestTaskCancel:

    # TC1: :cancel 成功 → 返回 cancelling 状态
    def test_cancel_returns_cancelling(self):
        """POST :cancel on an active task returns status=cancelling."""
        task_id = _create_task()
        # Transition to working
        _update_task(task_id, {"status": "working"})

        status_code, resp = _post_status(f"/tasks/{task_id}:cancel", {})
        assert status_code == 200, f"Expected 200 got {status_code}: {resp}"
        assert resp.get("ok") is True
        assert resp.get("status") == "cancelling", (
            f"Expected 'cancelling', got {resp.get('status')!r}"
        )

    # TC2: cancelling 状态可通过 SSE 被观察到
    def test_cancelling_state_observable_via_sse(self):
        """SSE stream emits a status=cancelling event before status=canceled."""
        task_id = _create_task()
        _update_task(task_id, {"status": "working"})

        events, stop, t = _collect_sse_events(duration=2.0)
        time.sleep(0.2)  # let SSE connection establish

        _post(f"/tasks/{task_id}:cancel", {})

        time.sleep(1.0)  # allow both cancelling+canceled to propagate
        stop.set()
        t.join(timeout=3)

        task_events = [e for e in events if e.get("task_id") == task_id and e.get("type") == "status"]
        states = [e["state"] for e in task_events]
        assert "cancelling" in states, (
            f"Expected 'cancelling' SSE event for task {task_id}, got states: {states}"
        )

    # TC3: cancelling → canceled 两步转换（SSE 可观察，使用 task-scoped subscribe）
    def test_cancelling_then_canceled_sse_sequence(self):
        """SSE emits cancelling then canceled events in order.
        
        Uses /tasks/{id}:subscribe which sends terminal-filtered events for this task
        and auto-closes the stream after the terminal state.
        """
        task_id = _create_task()
        _update_task(task_id, {"status": "working"})

        states: List[str] = []
        done = threading.Event()

        def _subscribe():
            """Use raw socket to avoid urllib buffering delays."""
            import socket as _socket
            try:
                host = "127.0.0.1"
                path = f"/tasks/{task_id}:subscribe"
                s = _socket.create_connection((host, HTTP_PORT), timeout=10)
                s.sendall(
                    f"GET {path} HTTP/1.1\r\nHost: {host}\r\nConnection: keep-alive\r\n\r\n"
                    .encode()
                )
                s.settimeout(0.5)
                buf = b""
                deadline = time.time() + 8
                while time.time() < deadline:
                    try:
                        chunk = s.recv(4096)
                        if not chunk:
                            break
                        buf += chunk
                        while b"\n" in buf:
                            line, buf = buf.split(b"\n", 1)
                            line = line.rstrip(b"\r")
                            if line.startswith(b"data:"):
                                payload = line[5:].strip()
                                if payload:
                                    try:
                                        evt = json.loads(payload)
                                        if evt.get("type") == "status" and "state" in evt:
                                            states.append(evt["state"])
                                            if evt["state"] in TERMINAL_STATES:
                                                done.set()
                                                s.close()
                                                return
                                    except json.JSONDecodeError:
                                        pass
                    except _socket.timeout:
                        continue
                s.close()
            except Exception:
                pass
            finally:
                done.set()

        t = threading.Thread(target=_subscribe, daemon=True)
        t.start()
        time.sleep(0.3)  # let SSE subscription establish

        _post(f"/tasks/{task_id}:cancel", {})

        # Wait for terminal (canceled) event on the stream
        done.wait(timeout=6)
        t.join(timeout=3)

        # Both states must appear
        assert "cancelling" in states, f"Missing 'cancelling' in SSE states: {states}"
        assert "canceled" in states, f"Missing 'canceled' in SSE states: {states}"

        # cancelling must precede canceled
        idx_cancelling = states.index("cancelling")
        idx_canceled   = states.index("canceled")
        assert idx_cancelling < idx_canceled, (
            f"'cancelling' should appear before 'canceled', got order: {states}"
        )

    # TC4: 幂等 — 已是 cancelling 时重复取消
    def test_idempotent_cancel_when_already_cancelling(self):
        """Calling :cancel when task is already cancelling returns 200 idempotently."""
        task_id = _create_task()
        _update_task(task_id, {"status": "working"})

        # First cancel → cancelling
        resp1 = _post(f"/tasks/{task_id}:cancel", {})
        assert resp1.get("status") in ("cancelling", "canceled"), f"Unexpected: {resp1}"

        # Manually set back to cancelling for idempotency test (race-safe: check either)
        # Second cancel → should still return 200
        status_code, resp2 = _post_status(f"/tasks/{task_id}:cancel", {})
        assert status_code == 200, f"Expected 200, got {status_code}: {resp2}"
        assert resp2.get("ok") is True
        assert resp2.get("status") in ("cancelling", "canceled"), (
            f"Expected cancelling or canceled, got: {resp2.get('status')!r}"
        )

    # TC5: 幂等 — 已是 canceled（terminal）时重复取消
    def test_idempotent_cancel_when_already_canceled(self):
        """Calling :cancel on a canceled task is idempotent (200, no error)."""
        task_id = _create_task()
        _update_task(task_id, {"status": "working"})

        # Cancel → wait for terminal
        _post(f"/tasks/{task_id}:cancel", {})
        deadline = time.time() + 3
        while time.time() < deadline:
            task = _get(f"/tasks/{task_id}")  # GET /tasks/{id} returns task dict directly
            if task["status"] == "canceled":
                break
            time.sleep(0.1)

        # Second cancel on already-canceled task
        status_code, resp = _post_status(f"/tasks/{task_id}:cancel", {})
        assert status_code == 200, f"Expected 200, got {status_code}: {resp}"
        assert resp.get("ok") is True
        assert resp.get("status") == "canceled", (
            f"Expected 'canceled' idempotent response, got: {resp.get('status')!r}"
        )

    # TC6: input_required → cancelling → canceled 路径
    def test_cancel_from_input_required(self):
        """input_required task can be canceled via the cancelling intermediate state."""
        task_id = _create_task()
        _update_task(task_id, {"status": "working"})
        _update_task(task_id, {"status": "input_required"})

        # Verify task is input_required (GET /tasks/{id} returns task dict directly)
        task = _get(f"/tasks/{task_id}")
        assert task["status"] == "input_required", f"Expected input_required, got: {task['status']}"

        # Cancel it
        status_code, resp = _post_status(f"/tasks/{task_id}:cancel", {})
        assert status_code == 200
        assert resp.get("ok") is True
        assert resp.get("status") in ("cancelling", "canceled"), (
            f"Expected cancelling or canceled, got: {resp.get('status')!r}"
        )

        # Wait for terminal
        deadline = time.time() + 3
        while time.time() < deadline:
            task = _get(f"/tasks/{task_id}")  # returns task dict directly
            if task["status"] in TERMINAL_STATES:
                break
            time.sleep(0.1)

        assert task["status"] == "canceled", (
            f"Expected task to reach 'canceled', got: {task['status']}"
        )

    # TC7: completed task → cancel returns 200 with current status (no 409)
    def test_cancel_completed_task_returns_ok_with_current_status(self):
        """Cancelling a completed task is idempotent (200) with the current status."""
        task_id = _create_task()
        _update_task(task_id, {"status": "working"})
        _update_task(task_id, {"status": "completed"})

        status_code, resp = _post_status(f"/tasks/{task_id}:cancel", {})
        assert status_code == 200, f"Expected 200, got {status_code}: {resp}"
        assert resp.get("ok") is True
        assert resp.get("status") == "completed", (
            f"Expected current status 'completed' to be returned, got: {resp.get('status')!r}"
        )

    # TC8: 不存在的 task_id → 404
    def test_cancel_nonexistent_task_returns_404(self):
        """Cancelling a non-existent task returns 404."""
        status_code, resp = _post_status("/tasks/nonexistent_task_xyz:cancel", {})
        assert status_code == 404, f"Expected 404, got {status_code}: {resp}"

    # TC9: AgentCard 声明 task_cancelling=true
    def test_agentcard_declares_task_cancelling(self):
        """AgentCard capabilities.task_cancelling must be true.
        
        The /.well-known/acp.json endpoint returns {"self": <card>, "peer": ...}.
        """
        resp = _get("/.well-known/acp.json")
        # The card is nested under "self"
        card = resp.get("self", resp)
        caps = card.get("capabilities", {})
        assert caps.get("task_cancelling") is True, (
            f"Expected capabilities.task_cancelling=true in AgentCard, got: {caps.get('task_cancelling')!r}\n"
            f"Full capabilities: {caps}"
        )

    # TC10: cancelling 状态下 SSE seq 单调递增
    def test_cancelling_seq_monotonically_increasing(self):
        """SSE seq values are strictly monotonically increasing through the cancel path."""
        task_id = _create_task()
        _update_task(task_id, {"status": "working"})

        events, stop, t = _collect_sse_events(duration=2.5)
        time.sleep(0.2)

        _post(f"/tasks/{task_id}:cancel", {})

        time.sleep(1.5)
        stop.set()
        t.join(timeout=3)

        task_events = [e for e in events if e.get("task_id") == task_id and e.get("type") == "status"]
        seqs = [e["seq"] for e in task_events if "seq" in e]

        assert len(seqs) >= 1, f"Expected at least 1 status event for task {task_id}"
        for i in range(1, len(seqs)):
            assert seqs[i] > seqs[i - 1], (
                f"SSE seq not monotonically increasing: {seqs}"
            )
