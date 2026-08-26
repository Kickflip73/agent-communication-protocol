"""
test_task_event_sequence.py — ACP v2.5 Task 事件序列规范测试

Tests:
  TES1: Task 完整生命周期 SSE 事件序列 (submitted→working→completed)
  TES2: 每个 Task SSE 事件必须包含必填字段 (type/ts/seq/task_id)
  TES3: SSE 事件的 seq 字段必须严格单调递增
  TES4: status 事件的状态转换顺序必须正确 (submitted 先于 working 先于 terminal)
  TES5: failed 状态事件必须包含 error 字段
  TES6: artifact 事件必须包含 task_id 和 artifact.parts
  TES7: message 事件必须包含 type/ts/seq/message_id/role/parts
  TES8: 相同 task_id 的事件序列中 seq 必须递增（不能回退）
  TES9: 终态事件（completed/failed/canceled）之后不应有同 task_id 的 status 事件
  TES10: 创建 Task 后 SSE 流中第一个 status 事件必须是 submitted
"""

import json
import pytest
import subprocess
import time
import socket
import threading
import urllib.request
import urllib.error
import sys
import os
from typing import List, Dict, Any, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RELAY_PATH = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")

TERMINAL_STATES = {"completed", "failed", "canceled"}


# ──────────────────────────────────────────────────────────────────────────────
# Port helpers
# ──────────────────────────────────────────────────────────────────────────────

def _free_port() -> int:
    """Return an OS-assigned free port where port AND port+100 are both free."""
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


WS_PORT = _free_port()
# ACP relay HTTP port is always WS_PORT + 100 (hard-coded in relay: port+100)
HTTP_PORT = WS_PORT + 100
BASE_URL = f"http://127.0.0.1:{HTTP_PORT}"

_proc: Optional[subprocess.Popen] = None


def _clean_env() -> dict:
    """Remove proxy env vars that would break localhost requests."""
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
        [
            sys.executable, RELAY_PATH,
            "--name", "TESTestAgent",
            "--port", str(WS_PORT),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=_clean_env(),
    )
    # Wait for relay to be ready
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
        f"{BASE_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


def _get(path: str) -> dict:
    req = urllib.request.Request(f"{BASE_URL}{path}", method="GET")
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


def _update_task(task_id: str, body: dict) -> dict:
    """Update a task via POST /tasks/{id}:update."""
    return _post(f"/tasks/{task_id}:update", body)


# ──────────────────────────────────────────────────────────────────────────────
# SSE collector: reads events from /stream for a limited time
# ──────────────────────────────────────────────────────────────────────────────

class SSECollector:
    """
    Non-blocking SSE collector using a raw socket to avoid urllib buffering.
    Call start() to begin streaming events in a background thread, then
    call stop() to get the collected events.
    """

    def __init__(self, duration: float = 2.0):
        self._duration = duration
        self._events: List[Dict[str, Any]] = []
        self._thread: Optional[threading.Thread] = None
        self._stop_flag = threading.Event()
        self._ready = threading.Event()

    def start(self):
        self._stop_flag.clear()
        self._ready.clear()
        self._events = []
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=1.0)  # wait until HTTP headers received

    def _run(self):
        """Use raw socket to get true streaming SSE (no urllib buffering)."""
        try:
            host = "127.0.0.1"
            port = HTTP_PORT
            sock = socket.create_connection((host, port), timeout=2)
            sock.sendall(
                f"GET /stream HTTP/1.1\r\nHost: {host}:{port}\r\n"
                f"Accept: text/event-stream\r\nConnection: close\r\n\r\n".encode()
            )
            # Read headers
            header_buf = b""
            while b"\r\n\r\n" not in header_buf:
                c = sock.recv(1)
                if not c:
                    break
                header_buf += c
            self._ready.set()  # signal that connection is established

            buf = b""
            deadline = time.time() + self._duration
            sock.settimeout(0.2)
            while time.time() < deadline and not self._stop_flag.is_set():
                try:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                    while b"\n\n" in buf:
                        block, buf = buf.split(b"\n\n", 1)
                        for line in block.split(b"\n"):
                            line = line.strip()
                            if line.startswith(b"data:"):
                                data_str = line[5:].strip().decode("utf-8", errors="replace")
                                try:
                                    evt = json.loads(data_str)
                                    self._events.append(evt)
                                except json.JSONDecodeError:
                                    pass
                except socket.timeout:
                    continue
                except Exception:
                    break
            sock.close()
        except Exception:
            self._ready.set()  # unblock start() even on error

    def stop(self) -> List[Dict[str, Any]]:
        self._stop_flag.set()
        if self._thread:
            self._thread.join(timeout=3)
        return list(self._events)


# ──────────────────────────────────────────────────────────────────────────────
# Helper: collect SSE events around a task operation
# ──────────────────────────────────────────────────────────────────────────────

def _collect_task_events(task_id: str, duration: float = 1.5) -> List[Dict]:
    """Collect SSE events for a specific task_id over `duration` seconds."""
    collector = SSECollector(duration=duration)
    collector.start()
    time.sleep(duration)
    all_events = collector.stop()
    return [e for e in all_events if e.get("task_id") == task_id]


def _create_and_drive_task(
    initial_state: str = "working",
    final_state: str = "completed",
    artifact: Optional[dict] = None,
    error: Optional[str] = None,
) -> tuple:
    """
    Create a task and drive it through submitted→initial_state→final_state via
    PUT /tasks/{id}. Returns (task_id, all_sse_events_for_task).
    """
    collector = SSECollector(duration=3.5)
    collector.start()

    # Create task (triggers submitted SSE event)
    # Note: relay requires 'role' field in the payload
    resp = _post("/tasks", {
        "role":  "user",
        "parts": [{"type": "text", "content": "test task for event sequence"}],
    })
    assert resp.get("ok") is True or "task" in resp, f"Task creation failed: {resp}"
    task_id = resp.get("task", {}).get("id") or resp.get("id")
    assert task_id, f"No task_id in response: {resp}"

    time.sleep(0.2)

    # Drive to intermediate state
    if initial_state != "submitted":
        _update_task(task_id, {"status": initial_state})
        time.sleep(0.2)

    # Drive to final state with optional artifact/error
    update_body: dict = {"status": final_state}
    if artifact:
        update_body["artifact"] = artifact
    if error:
        update_body["error"] = error
    _update_task(task_id, update_body)

    time.sleep(0.8)  # allow SSE events to propagate before stopping collector
    all_events = collector.stop()
    task_events = [e for e in all_events if e.get("task_id") == task_id]
    return task_id, task_events


# ══════════════════════════════════════════════════════════════════════════════
# TES1: Complete lifecycle submitted→working→completed
# ══════════════════════════════════════════════════════════════════════════════

def test_tes1_complete_lifecycle_submitted_working_completed():
    """
    TES1: Task 完整生命周期 SSE 事件序列 (submitted→working→completed).
    Verifies that all three state transitions appear in SSE stream in order.
    """
    task_id, events = _create_and_drive_task(
        initial_state="working",
        final_state="completed",
        artifact={"parts": [{"type": "text", "content": "done"}]},
    )
    status_events = [e for e in events if e.get("type") == "status"]
    states = [e["state"] for e in status_events]

    assert "submitted" in states, f"'submitted' state missing. Got states: {states}"
    assert "working" in states, f"'working' state missing. Got states: {states}"
    assert "completed" in states, f"'completed' state missing. Got states: {states}"

    # Order check: submitted before working before completed
    idx_sub = states.index("submitted")
    idx_wk  = states.index("working")
    idx_cmp = states.index("completed")
    assert idx_sub < idx_wk,  f"submitted must come before working: {states}"
    assert idx_wk  < idx_cmp, f"working must come before completed: {states}"


# ══════════════════════════════════════════════════════════════════════════════
# TES2: Mandatory fields present in every Task SSE event
# ══════════════════════════════════════════════════════════════════════════════

def test_tes2_mandatory_fields_in_task_sse_events():
    """
    TES2: 每个 Task SSE 事件必须包含必填字段 (type/ts/seq/task_id).
    Spec §8.1 MUST: type, ts, seq present in all events;
                    task_id MUST be present in status + artifact events.
    """
    task_id, events = _create_and_drive_task(
        initial_state="working",
        final_state="completed",
        artifact={"parts": [{"type": "text", "content": "artifact content"}]},
    )
    assert events, f"No SSE events collected for task {task_id}"

    for evt in events:
        assert "type" in evt, f"Missing 'type' in event: {evt}"
        assert "ts" in evt,   f"Missing 'ts' in event: {evt}"
        assert "seq" in evt,  f"Missing 'seq' in event: {evt}"
        assert isinstance(evt["seq"], int), f"'seq' must be int, got: {type(evt['seq'])}"

    # For status and artifact events: task_id MUST be present
    for evt in events:
        if evt.get("type") in ("status", "artifact"):
            assert "task_id" in evt, \
                f"'task_id' MUST be present in {evt['type']} event: {evt}"
            assert evt["task_id"] == task_id, \
                f"task_id mismatch: expected {task_id}, got {evt['task_id']}"


# ══════════════════════════════════════════════════════════════════════════════
# TES3: SSE seq field is strictly monotonically increasing across all events
# ══════════════════════════════════════════════════════════════════════════════

def test_tes3_seq_monotonically_increasing():
    """
    TES3: SSE 事件的全局 seq 字段必须严格单调递增 (spec §8.1 §8.7 rule 7).
    The global SSE seq counter must never go backwards.
    """
    collector = SSECollector(duration=3.0)
    collector.start()

    # Create two tasks to generate multiple events
    resp1 = _post("/tasks", {"role": "user", "parts": [{"type": "text", "content": "task A"}]})
    task_id1 = resp1.get("task", {}).get("id") or resp1.get("id")
    time.sleep(0.15)
    _update_task(task_id1, {"status": "working"})
    time.sleep(0.15)
    _update_task(task_id1, {"status": "completed"})
    time.sleep(0.15)

    resp2 = _post("/tasks", {"role": "user", "parts": [{"type": "text", "content": "task B"}]})
    task_id2 = resp2.get("task", {}).get("id") or resp2.get("id")
    time.sleep(0.15)
    _update_task(task_id2, {"status": "working"})
    time.sleep(0.15)
    _update_task(task_id2, {"status": "completed"})
    time.sleep(0.5)

    all_events = collector.stop()
    seqs = [e["seq"] for e in all_events if "seq" in e]
    assert len(seqs) >= 4, f"Expected at least 4 events, got {len(seqs)}"

    for i in range(1, len(seqs)):
        assert seqs[i] > seqs[i - 1], \
            f"seq not monotonically increasing at index {i}: {seqs[i-1]} -> {seqs[i]}. Full seq: {seqs}"


# ══════════════════════════════════════════════════════════════════════════════
# TES4: State transition order must be correct
# ══════════════════════════════════════════════════════════════════════════════

def test_tes4_state_transition_order():
    """
    TES4: Status 事件状态转换顺序 — submitted 必须先于 working 先于 terminal state.
    Spec §8.2, §8.7 rules 3-4.
    """
    task_id, events = _create_and_drive_task(
        initial_state="working",
        final_state="failed",
        error="intentional test failure",
    )
    status_states = [e["state"] for e in events if e.get("type") == "status"]

    assert len(status_states) >= 2, \
        f"Expected at least 2 status events, got {len(status_states)}: {status_states}"

    # submitted must appear before any working/terminal states
    first_state = status_states[0]
    assert first_state == "submitted", \
        f"First status event must be 'submitted', got '{first_state}'. All states: {status_states}"

    # working must appear before failed
    if "working" in status_states and "failed" in status_states:
        assert status_states.index("working") < status_states.index("failed"), \
            f"'working' must precede 'failed'. States: {status_states}"


# ══════════════════════════════════════════════════════════════════════════════
# TES5: failed status event must include error field
# ══════════════════════════════════════════════════════════════════════════════

def test_tes5_failed_event_has_error_field():
    """
    TES5: failed 状态事件必须包含 error 字段 (spec §8.3 SHOULD).
    When a task transitions to failed with an error string, the SSE event must carry it.
    """
    error_msg = "upstream service timeout — TES5"
    task_id, events = _create_and_drive_task(
        initial_state="working",
        final_state="failed",
        error=error_msg,
    )
    failed_events = [
        e for e in events
        if e.get("type") == "status" and e.get("state") == "failed"
    ]
    assert failed_events, f"No failed status events found. Events: {events}"

    failed_evt = failed_events[0]
    assert "error" in failed_evt, \
        f"'error' field missing from failed event: {failed_evt}"
    assert failed_evt["error"] == error_msg, \
        f"error field mismatch: expected '{error_msg}', got '{failed_evt['error']}'"


# ══════════════════════════════════════════════════════════════════════════════
# TES6: artifact event must include task_id and artifact.parts
# ══════════════════════════════════════════════════════════════════════════════

def test_tes6_artifact_event_required_fields():
    """
    TES6: Artifact 事件必须包含 task_id 和 artifact.parts (spec §8.4).
    """
    artifact_content = "Summarized content for TES6 test."
    task_id, events = _create_and_drive_task(
        initial_state="working",
        final_state="completed",
        artifact={
            "parts": [{"type": "text", "content": artifact_content}]
        },
    )
    artifact_events = [e for e in events if e.get("type") == "artifact"]
    assert artifact_events, \
        f"No artifact events found for task {task_id}. Events: {[e.get('type') for e in events]}"

    for art_evt in artifact_events:
        assert "task_id" in art_evt, f"'task_id' missing in artifact event: {art_evt}"
        assert art_evt["task_id"] == task_id, \
            f"task_id mismatch in artifact event: {art_evt}"
        assert "artifact" in art_evt, f"'artifact' missing in artifact event: {art_evt}"
        assert "parts" in art_evt["artifact"], \
            f"'artifact.parts' missing in artifact event: {art_evt}"
        assert isinstance(art_evt["artifact"]["parts"], list), \
            f"'artifact.parts' must be a list: {art_evt}"
        assert len(art_evt["artifact"]["parts"]) > 0, \
            f"'artifact.parts' must be non-empty: {art_evt}"


# ══════════════════════════════════════════════════════════════════════════════
# TES7: message events must include required fields
# ══════════════════════════════════════════════════════════════════════════════

def test_tes7_message_event_required_fields():
    """
    TES7: Message 事件必须包含 type/ts/seq/message_id/role/parts (spec §8.5).
    Send a message and verify the resulting SSE message event has all required fields.
    """
    collector = SSECollector(duration=2.5)
    collector.start()

    # Send a message (triggers message SSE event — even for outbound via BUG-001 fix)
    try:
        _post("/message:send", {
            "role": "user",
            "parts": [{"type": "text", "content": "TES7 probe message"}],
        })
    except Exception:
        # Sending may fail if no peer connected; we still check what was emitted
        pass

    time.sleep(0.7)
    all_events = collector.stop()
    msg_events = [e for e in all_events if e.get("type") == "message"]

    if not msg_events:
        pytest.skip("No message SSE events collected (no peer connected; outbound SSE may not fire)")

    for evt in msg_events:
        assert "type" in evt,       f"Missing 'type' in message event: {evt}"
        assert "ts" in evt,         f"Missing 'ts' in message event: {evt}"
        assert "seq" in evt,        f"Missing 'seq' in message event: {evt}"
        assert "message_id" in evt, f"Missing 'message_id' in message event: {evt}"
        assert "role" in evt,       f"Missing 'role' in message event: {evt}"
        assert "parts" in evt,      f"Missing 'parts' in message event: {evt}"
        assert isinstance(evt["parts"], list), f"'parts' must be list: {evt}"


# ══════════════════════════════════════════════════════════════════════════════
# TES8: seq values for same task_id must be increasing (no rewind)
# ══════════════════════════════════════════════════════════════════════════════

def test_tes8_task_seq_values_increasing():
    """
    TES8: 相同 task_id 的 SSE 事件中 seq 必须递增 (spec §8.7 rule 7).
    Each event within a task's event stream must have a higher seq than the previous.
    """
    task_id, events = _create_and_drive_task(
        initial_state="working",
        final_state="completed",
        artifact={"parts": [{"type": "text", "content": "TES8 artifact"}]},
    )
    assert events, f"No events for task {task_id}"

    seqs = [e["seq"] for e in events if "seq" in e]
    assert len(seqs) >= 2, \
        f"Need at least 2 events to check ordering. Got seqs: {seqs}"

    for i in range(1, len(seqs)):
        assert seqs[i] > seqs[i - 1], \
            f"seq must strictly increase within task events at index {i}: " \
            f"{seqs[i-1]} -> {seqs[i]}. All seqs for task: {seqs}"


# ══════════════════════════════════════════════════════════════════════════════
# TES9: No status events after terminal state for same task
# ══════════════════════════════════════════════════════════════════════════════

def test_tes9_no_status_events_after_terminal_state():
    """
    TES9: 终态事件（completed/failed/canceled）之后不应有同 task_id 的 status 事件 (spec §8.7 rule 5).
    After reaching a terminal state, the relay must not emit further status events for that task.
    """
    task_id, events = _create_and_drive_task(
        initial_state="working",
        final_state="completed",
    )
    status_events = [e for e in events if e.get("type") == "status"]
    if not status_events:
        pytest.skip("No status events collected")

    # Find the index of first terminal event
    terminal_idx = None
    for i, evt in enumerate(status_events):
        if evt.get("state") in TERMINAL_STATES:
            terminal_idx = i
            break

    if terminal_idx is None:
        pytest.skip("No terminal state event found in collected events")

    # No status events should come after terminal
    post_terminal = status_events[terminal_idx + 1:]
    assert not post_terminal, \
        f"Found status events after terminal state at index {terminal_idx}: {post_terminal}"


# ══════════════════════════════════════════════════════════════════════════════
# TES10: First SSE event for a new task MUST be state=submitted
# ══════════════════════════════════════════════════════════════════════════════

def test_tes10_first_event_is_submitted():
    """
    TES10: 创建 Task 后 SSE 流中第一个 status 事件必须是 submitted (spec §8.2, §8.7 rule 6).
    The very first status event emitted for a newly-created task must be state=submitted.
    """
    collector = SSECollector(duration=2.0)
    collector.start()

    resp = _post("/tasks", {
        "role":  "user",
        "parts": [{"type": "text", "content": "TES10 first-event test"}],
    })
    task_id = resp.get("task", {}).get("id") or resp.get("id")
    assert task_id, f"No task_id in creation response: {resp}"

    time.sleep(0.6)
    all_events = collector.stop()

    task_status_events = [
        e for e in all_events
        if e.get("type") == "status" and e.get("task_id") == task_id
    ]
    assert task_status_events, \
        f"No status events found for task {task_id}"

    first_status = task_status_events[0]
    assert first_status["state"] == "submitted", \
        f"First status event for new task must be 'submitted', got '{first_status['state']}'"
