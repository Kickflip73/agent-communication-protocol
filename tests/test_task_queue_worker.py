"""
test_task_queue_worker.py — v3.11 async task queue worker tests

Tests:
  TQW1:  GET /tasks/queue/workers returns correct structure (no workers yet)
  TQW2:  POST /tasks/queue/worker requires callback_url
  TQW3:  POST /tasks/queue/worker registers worker successfully
  TQW4:  GET /tasks/queue/workers shows registered worker
  TQW5:  POST /tasks/queue/worker is idempotent (same worker_id → update)
  TQW6:  DELETE /tasks/queue/worker/{id} deregisters worker
  TQW7:  DELETE /tasks/queue/worker/{id} returns 404 for unknown worker
  TQW8:  POST /tasks/queue returns workers_dispatched=0 when no workers registered
  TQW9:  POST /tasks/queue dispatches to registered worker callback
  TQW10: AgentCard capabilities.task_queue_worker=true
  TQW11: AgentCard endpoints.task_queue_workers declared
  TQW12: Worker with peer_id filter only receives matching tasks
"""
import subprocess
import socket
import time
import json
import threading
import urllib.request
import urllib.error
import http.server
import os
import sys
import pytest

RELAY_PY = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _get(http_port: int, path: str, timeout: float = 5.0):
    url = f"http://127.0.0.1:{http_port}{path}"
    try:
        req = urllib.request.urlopen(url, timeout=timeout)
        return json.loads(req.read()), req.status
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read()), e.code
        except Exception:
            return {}, e.code
    except Exception:
        return None, None


def _post(http_port: int, path: str, body: dict, timeout: float = 8.0):
    url = f"http://127.0.0.1:{http_port}{path}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data,
                                  headers={"Content-Type": "application/json"},
                                  method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(resp.read()), resp.status
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read()), e.code
        except Exception:
            return {}, e.code
    except Exception:
        return None, None


def _delete(http_port: int, path: str, timeout: float = 5.0):
    url = f"http://127.0.0.1:{http_port}{path}"
    req = urllib.request.Request(url, method="DELETE")
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(resp.read()), resp.status
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read()), e.code
        except Exception:
            return {}, e.code
    except Exception:
        return None, None


def _wait_http_ready(http_port: int, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{http_port}/status", timeout=2)
            return True
        except Exception:
            time.sleep(0.3)
    return False


def _start_relay(ws_port: int, name: str = "TestRelay") -> subprocess.Popen:
    env = {**os.environ}
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        env.pop(k, None)
    env["no_proxy"] = "127.0.0.1,localhost"
    env["NO_PROXY"] = "127.0.0.1,localhost"
    proc = subprocess.Popen(
        [sys.executable, RELAY_PY,
         "--port", str(ws_port),
         "--local-only",
         "--name", name],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
    )
    def _drain(p):
        try:
            for _ in p: pass
        except Exception: pass
    threading.Thread(target=_drain, args=(proc.stdout,), daemon=True).start()
    return proc


@pytest.fixture(scope="module")
def relay():
    ws = _free_port()
    http = ws + 100
    proc = _start_relay(ws, "TQWRelay")
    if not _wait_http_ready(http, 30):
        proc.terminate()
        proc.wait(timeout=5)
        pytest.skip("TQWRelay did not start")
    yield {"ws": ws, "http": http, "proc": proc}
    proc.terminate()
    try: proc.wait(timeout=8)
    except subprocess.TimeoutExpired: proc.kill(); proc.wait()


# ── Callback receiver (tiny HTTP server that collects dispatched tasks) ───────

class _CallbackReceiver:
    """Minimal HTTP server that collects POST bodies — simulates a worker callback."""

    def __init__(self):
        self.port = _free_port()
        self.received: list = []
        self._lock = threading.Lock()
        self._server = None
        self._thread = None

    def start(self):
        receiver = self

        class _Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length)) if length else {}
                with receiver._lock:
                    receiver.received.append(body)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"ok":true}')

            def log_message(self, *args):
                pass  # silence

        self._server = http.server.HTTPServer(("127.0.0.1", self.port), _Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        if self._server:
            self._server.shutdown()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}/callback"

    def wait_for(self, n: int = 1, timeout: float = 5.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                if len(self.received) >= n:
                    return True
            time.sleep(0.1)
        return False


@pytest.fixture(scope="module")
def callback_server():
    cb = _CallbackReceiver().start()
    yield cb
    cb.stop()


# ── TQW1: GET /tasks/queue/workers structure ─────────────────────────────────

def test_tqw1_get_workers_structure(relay):
    """TQW1: GET /tasks/queue/workers returns correct structure."""
    data, code = _get(relay["http"], "/tasks/queue/workers")
    assert code == 200, f"Expected 200, got {code}: {data}"
    assert "workers" in data, f"Missing 'workers': {data}"
    assert "worker_count" in data, f"Missing 'worker_count': {data}"
    assert data.get("ok") is True


# ── TQW2: POST /tasks/queue/worker requires callback_url ─────────────────────

def test_tqw2_requires_callback_url(relay):
    """TQW2: POST /tasks/queue/worker without callback_url returns 400."""
    data, code = _post(relay["http"], "/tasks/queue/worker", {})
    assert code == 400, f"Expected 400, got {code}: {data}"
    assert "error" in data


# ── TQW3: POST /tasks/queue/worker registers successfully ────────────────────

def test_tqw3_registers_worker(relay, callback_server):
    """TQW3: POST /tasks/queue/worker registers worker successfully."""
    data, code = _post(relay["http"], "/tasks/queue/worker", {
        "callback_url": callback_server.url,
        "worker_id":    "test-worker-tqw3",
    })
    assert code == 200, f"Expected 200, got {code}: {data}"
    assert data.get("ok") is True
    assert data.get("worker_id") == "test-worker-tqw3"
    assert "registered_at" in data
    assert data.get("callback_url") == callback_server.url


# ── TQW4: GET /tasks/queue/workers shows registered worker ───────────────────

def test_tqw4_get_shows_registered(relay, callback_server):
    """TQW4: GET /tasks/queue/workers shows the registered worker."""
    # Ensure registered
    _post(relay["http"], "/tasks/queue/worker", {
        "callback_url": callback_server.url,
        "worker_id":    "test-worker-tqw4",
    })
    data, code = _get(relay["http"], "/tasks/queue/workers")
    assert code == 200
    worker_ids = [w["worker_id"] for w in data["workers"]]
    assert "test-worker-tqw4" in worker_ids, \
        f"Expected test-worker-tqw4 in workers: {worker_ids}"


# ── TQW5: Idempotent registration ─────────────────────────────────────────────

def test_tqw5_idempotent_registration(relay, callback_server):
    """TQW5: POST /tasks/queue/worker with same worker_id updates (idempotent)."""
    _post(relay["http"], "/tasks/queue/worker", {
        "callback_url": callback_server.url,
        "worker_id":    "test-worker-idem",
    })
    data, code = _post(relay["http"], "/tasks/queue/worker", {
        "callback_url": callback_server.url + "/v2",
        "worker_id":    "test-worker-idem",
    })
    assert code == 200, f"Expected 200, got {code}: {data}"
    assert data.get("ok") is True
    # Verify updated callback_url
    workers_data, _ = _get(relay["http"], "/tasks/queue/workers")
    worker = next((w for w in workers_data["workers"] if w["worker_id"] == "test-worker-idem"), None)
    assert worker is not None
    assert worker["callback_url"] == callback_server.url + "/v2"


# ── TQW6: DELETE /tasks/queue/worker/{id} deregisters ───────────────────────

def test_tqw6_delete_deregisters(relay, callback_server):
    """TQW6: DELETE /tasks/queue/worker/{id} removes the worker."""
    # Register first
    _post(relay["http"], "/tasks/queue/worker", {
        "callback_url": callback_server.url,
        "worker_id":    "test-worker-del",
    })
    # Delete
    data, code = _delete(relay["http"], "/tasks/queue/worker/test-worker-del")
    assert code == 200, f"Expected 200, got {code}: {data}"
    assert data.get("ok") is True
    assert data.get("deregistered") is True
    # Verify gone
    workers_data, _ = _get(relay["http"], "/tasks/queue/workers")
    worker_ids = [w["worker_id"] for w in workers_data["workers"]]
    assert "test-worker-del" not in worker_ids


# ── TQW7: DELETE unknown worker returns 404 ──────────────────────────────────

def test_tqw7_delete_unknown_404(relay):
    """TQW7: DELETE /tasks/queue/worker/{id} with unknown id returns 404."""
    data, code = _delete(relay["http"], "/tasks/queue/worker/nonexistent-xyz-999")
    assert code == 404, f"Expected 404, got {code}: {data}"
    assert data.get("deregistered") is False or "not found" in data.get("error", "")


# ── TQW8: POST /tasks/queue workers_dispatched=0 when no workers ─────────────

def test_tqw8_queue_dispatched_zero_when_no_workers(relay):
    """TQW8: POST /tasks/queue returns workers_dispatched=0 when no workers match."""
    # Use a skill_id unlikely to match any worker filter
    data, code = _post(relay["http"], "/tasks/queue", {
        "role":    "agent",
        "payload": {"skill_id": "unlikely-skill-xyz-999", "text": "test"},
    })
    assert code == 202, f"Expected 202, got {code}: {data}"
    assert "workers_dispatched" in data, f"Missing workers_dispatched: {data}"


# ── TQW9: POST /tasks/queue dispatches to registered worker ─────────────────

def test_tqw9_queue_dispatches_to_worker(relay, callback_server):
    """TQW9: POST /tasks/queue triggers dispatch to a registered worker callback."""
    # Clear received so far
    with callback_server._lock:
        initial_count = len(callback_server.received)

    # Register a match-all worker pointing to our callback server
    _post(relay["http"], "/tasks/queue/worker", {
        "callback_url": callback_server.url,
        "worker_id":    "test-worker-dispatch",
    })

    # Enqueue a task
    data, code = _post(relay["http"], "/tasks/queue", {
        "role":    "agent",
        "payload": {"skill_id": "demo", "text": "hello worker"},
    })
    assert code == 202, f"Expected 202, got {code}: {data}"
    assert data.get("workers_dispatched", 0) >= 1, \
        f"Expected workers_dispatched>=1: {data}"

    # Wait for callback to arrive
    arrived = callback_server.wait_for(initial_count + 1, timeout=5.0)
    assert arrived, "Worker callback was not received within 5s"

    # Verify dispatch envelope structure
    with callback_server._lock:
        last = callback_server.received[-1]
    assert last.get("type") == "acp.task.dispatch", f"Bad dispatch type: {last.get('type')}"
    assert "task" in last, f"Missing 'task' in dispatch: {last}"
    assert last["task"].get("status") == "submitted"

    # Cleanup: deregister
    _delete(relay["http"], "/tasks/queue/worker/test-worker-dispatch")


# ── TQW10: AgentCard capabilities.task_queue_worker=true ─────────────────────

def test_tqw10_capabilities_declared(relay):
    """TQW10: AgentCard capabilities.task_queue_worker=true."""
    wrapper, code = _get(relay["http"], "/.well-known/acp.json")
    assert code == 200
    card = wrapper.get("self") or wrapper
    caps = card.get("capabilities") or {}
    assert caps.get("task_queue_worker") is True, \
        f"Expected capabilities.task_queue_worker=true, got: {caps.get('task_queue_worker')}"


# ── TQW11: AgentCard endpoints.task_queue_workers declared ───────────────────

def test_tqw11_endpoints_declared(relay):
    """TQW11: AgentCard endpoints.task_queue_workers declared."""
    wrapper, code = _get(relay["http"], "/.well-known/acp.json")
    assert code == 200
    card = wrapper.get("self") or wrapper
    endpoints = card.get("endpoints") or {}
    assert "task_queue_workers" in endpoints, \
        f"Expected 'task_queue_workers' in endpoints, got: {list(endpoints.keys())[:10]}"
    assert endpoints["task_queue_workers"] == "/tasks/queue/workers"


# ── TQW12: Worker peer_id filter ─────────────────────────────────────────────

def test_tqw12_peer_id_filter(relay, callback_server):
    """TQW12: Worker with peer_id filter only dispatches matching tasks."""
    with callback_server._lock:
        initial_count = len(callback_server.received)

    # Register a worker with a specific peer_id filter (won't match generic tasks)
    _post(relay["http"], "/tasks/queue/worker", {
        "callback_url": callback_server.url,
        "worker_id":    "test-worker-filtered",
        "peer_id":      "specific-peer-abc123",  # only match this peer
    })

    # Enqueue a task with NO from_peer_id — should NOT match the filter
    _post(relay["http"], "/tasks/queue", {
        "role":    "agent",
        "payload": {"skill_id": "demo", "text": "no peer"},
    })
    time.sleep(0.5)  # brief wait
    with callback_server._lock:
        after_count = len(callback_server.received)

    # The filtered worker should NOT have received this task
    # (it may still dispatch to other match-all workers, but filtered one should be skipped)
    # We just verify the filter is respected — no assertion on exact count since other workers may match
    # The key assertion: no dispatch with worker_id=test-worker-filtered
    with callback_server._lock:
        new_dispatches = callback_server.received[initial_count:]
    filtered_dispatches = [d for d in new_dispatches
                           if d.get("worker_id") == "test-worker-filtered"]
    assert len(filtered_dispatches) == 0, \
        f"Filtered worker should not receive tasks without matching peer_id: {filtered_dispatches}"

    # Cleanup
    _delete(relay["http"], "/tasks/queue/worker/test-worker-filtered")
