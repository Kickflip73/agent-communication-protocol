"""
test_tasks_pagination.py — ACP v0.9 GET /tasks pagination parameters

Tests the A2A v1.0-aligned pagination parameters:
  - page_size  (integer, default 20, max 100): per-page count
  - after      (string, task_id): cursor — returns tasks after this ID (creation order)
  - status     (string, comma-separated multi-value): filter by task state

Response format:
  {
    "tasks":       [...],
    "total":       42,
    "has_more":    true,
    "next_cursor": "task_abc123"   # null when no more pages
  }

Tests:
  TP1: Default page_size=20 — returns correct count
  TP2: Custom page_size, valid range (1–100)
  TP3: page_size >100 — auto-clamped to 100
  TP4: `after` cursor pagination — returns tasks after given ID
  TP5: status filter — single status value
  TP6: status filter — multiple statuses (comma-separated)
  TP7: Empty result — has_more=false, next_cursor=null
  TP8: Full regression — no params → backward-compatible response shape
"""

import json
import pytest
import subprocess
import time
import sys
import os
import urllib.request
import urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RELAY_PATH = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _free_port():
    """Return an OS-assigned free WS port where port AND port+100 are both free."""
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


WS_PORT   = _free_port()
HTTP_PORT = WS_PORT + 100

_proc = None


def _make_env():
    env = os.environ.copy()
    for k in ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY"):
        env.pop(k, None)
    return env


def _wait_ready(timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://localhost:{HTTP_PORT}/.well-known/acp.json", timeout=1
            ) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.2)
    return False


def _get(path):
    """GET path, return (http_status, parsed_json)."""
    req = urllib.request.Request(f"http://localhost:{HTTP_PORT}{path}")
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _post(path, body):
    """POST JSON body to path, return (http_status, parsed_json)."""
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"http://localhost:{HTTP_PORT}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _create_task(description="pagination-test", status="submitted"):
    """Create a task and optionally advance its status. Returns task_id."""
    body = {
        "role":  "user",
        "parts": [{"type": "text", "content": description}],
    }
    status_code, resp = _post("/tasks/create", body)
    assert status_code in (200, 201), f"create_task failed: {status_code} {resp}"
    task_id = resp["task"]["id"]

    if status != "submitted":
        _post(f"/tasks/{task_id}/update", {"status": status})

    return task_id


def _create_tasks_batch(n, prefix="tp", status="submitted"):
    """Create n tasks, returning list of task_ids in creation order."""
    ids = []
    for i in range(n):
        ids.append(_create_task(f"{prefix}-{i}", status=status))
    return ids


# ─────────────────────────────────────────────────────────────────────────────
# Fixture: single relay (module-scoped, shared across all TP tests)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def single_relay():
    global _proc
    env = _make_env()
    _proc = subprocess.Popen(
        [sys.executable, RELAY_PATH, "--port", str(WS_PORT), "--name", "TPAgent"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
    )
    if not _wait_ready():
        _proc.kill()
        out, err = _proc.communicate()
        pytest.fail(
            f"Relay (HTTP:{HTTP_PORT}) did not start in time.\n"
            f"stdout: {out.decode()[:500]}\nstderr: {err.decode()[:500]}"
        )
    yield
    _proc.terminate()
    try:
        _proc.wait(timeout=6)
    except subprocess.TimeoutExpired:
        _proc.kill()


# ─────────────────────────────────────────────────────────────────────────────
# TP1: Default page_size=20 — returns correct count
# ─────────────────────────────────────────────────────────────────────────────

def test_tp1_default_page_size_20():
    """TP1: With page_size not specified, default is 20; response has required fields."""
    # Create 25 tasks so we definitely have more than 20
    _create_tasks_batch(25, prefix="tp1")

    status, data = _get("/tasks")
    assert status == 200, f"Expected 200, got {status}: {data}"

    # Response must include required v0.9 fields
    assert "tasks" in data, f"Missing 'tasks': {data}"
    assert "total" in data, f"Missing 'total': {data}"
    assert "has_more" in data, f"Missing 'has_more': {data}"
    assert "next_cursor" in data, f"Missing 'next_cursor': {data}"

    # Default page_size=20: page must have at most 20 items
    assert len(data["tasks"]) <= 20, (
        f"Default page should be ≤ 20 tasks, got {len(data['tasks'])}"
    )

    # Since we created 25 tasks, total >= 25 and has_more=True
    assert data["total"] >= 25, f"Expected total >= 25, got {data['total']}"
    assert data["has_more"] is True, (
        f"Expected has_more=True when total={data['total']} > 20: {data}"
    )
    assert data["next_cursor"] is not None, (
        f"next_cursor should be set when has_more=True: {data}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# TP2: Custom page_size — valid range (1–100)
# ─────────────────────────────────────────────────────────────────────────────

def test_tp2_custom_page_size_valid():
    """TP2: page_size=5 returns exactly 5 tasks when more are available."""
    # Ensure at least 10 tasks exist
    _create_tasks_batch(10, prefix="tp2")

    status, data = _get("/tasks?page_size=5")
    assert status == 200, f"Expected 200, got {status}: {data}"

    assert len(data["tasks"]) == 5, (
        f"Expected exactly 5 tasks with page_size=5, got {len(data['tasks'])}"
    )
    assert data["has_more"] is True, (
        f"Expected has_more=True with page_size=5 and {data['total']} total tasks"
    )
    assert data["next_cursor"] is not None, (
        f"next_cursor should be set when has_more=True: {data}"
    )

    # Test page_size=1
    status2, data2 = _get("/tasks?page_size=1")
    assert status2 == 200
    assert len(data2["tasks"]) == 1, f"Expected 1 task with page_size=1: {data2}"


# ─────────────────────────────────────────────────────────────────────────────
# TP3: page_size >100 — auto-clamped to 100
# ─────────────────────────────────────────────────────────────────────────────

def test_tp3_page_size_clamped_to_100():
    """TP3: page_size=999 is clamped to 100; returns at most 100 tasks."""
    # Create enough tasks to verify clamping behavior
    # (Relay is shared; existing tasks count too)
    status, data = _get("/tasks?page_size=999")
    assert status == 200, f"Expected 200, got {status}: {data}"

    assert len(data["tasks"]) <= 100, (
        f"page_size=999 should clamp to 100; got {len(data['tasks'])} tasks"
    )

    # Same check with page_size=200
    status2, data2 = _get("/tasks?page_size=200")
    assert status2 == 200
    assert len(data2["tasks"]) <= 100, (
        f"page_size=200 should clamp to 100; got {len(data2['tasks'])} tasks"
    )


# ─────────────────────────────────────────────────────────────────────────────
# TP4: `after` cursor pagination — next page
# ─────────────────────────────────────────────────────────────────────────────

def test_tp4_after_cursor_pagination():
    """TP4: `after=<task_id>` returns tasks created after that ID (exclusive cursor)."""
    # Create a fresh batch to have known ordering
    batch_ids = _create_tasks_batch(6, prefix="tp4")

    # Get first page with page_size=3
    status1, page1 = _get("/tasks?page_size=3&sort=asc")
    assert status1 == 200, f"Page1 request failed: {status1} {page1}"
    assert len(page1["tasks"]) == 3, f"Expected 3 tasks on page 1: {page1}"
    assert page1["has_more"] is True, f"Expected has_more=True on page 1: {page1}"
    assert page1["next_cursor"] is not None, (
        f"next_cursor must be set when has_more=True: {page1}"
    )

    cursor = page1["next_cursor"]
    page1_ids = [t["id"] for t in page1["tasks"]]

    # Get second page using `after` cursor
    status2, page2 = _get(f"/tasks?page_size=3&sort=asc&after={cursor}")
    assert status2 == 200, f"Page2 request failed: {status2} {page2}"

    page2_ids = [t["id"] for t in page2["tasks"]]

    # No overlap between pages
    overlap = set(page1_ids) & set(page2_ids)
    assert len(overlap) == 0, (
        f"Pages 1 and 2 must not overlap; found: {overlap}"
    )

    # The cursor task itself should NOT be in page 2 (exclusive)
    assert cursor not in page2_ids, (
        f"Cursor task {cursor} should be excluded from page 2: {page2_ids}"
    )

    # Page 2 tasks should come after the cursor task (in sort=asc order)
    # The cursor is the last task of page 1; page 2 starts after it
    assert len(page2["tasks"]) > 0, (
        f"Page 2 should have tasks after cursor {cursor}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# TP5: status filter — single status
# ─────────────────────────────────────────────────────────────────────────────

def test_tp5_status_filter_single():
    """TP5: status=working returns only working tasks."""
    # Create tasks in different states
    working_id   = _create_task("tp5-working",   status="working")
    completed_id = _create_task("tp5-completed", status="completed")
    failed_id    = _create_task("tp5-failed",    status="failed")

    status, data = _get("/tasks?status=working")
    assert status == 200, f"Expected 200: {status} {data}"

    task_ids = [t["id"] for t in data["tasks"]]

    assert working_id in task_ids, (
        f"working task {working_id} not in result: {task_ids}"
    )
    assert completed_id not in task_ids, (
        f"completed task should be filtered out: {task_ids}"
    )
    assert failed_id not in task_ids, (
        f"failed task should be filtered out: {task_ids}"
    )

    # All returned tasks must have status=working
    for t in data["tasks"]:
        assert t.get("status") == "working", (
            f"Non-working task in result: {t}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# TP6: status filter — multiple statuses (comma-separated)
# ─────────────────────────────────────────────────────────────────────────────

def test_tp6_status_filter_multi():
    """TP6: status=submitted,working returns tasks in either state (comma-separated)."""
    submitted_id = _create_task("tp6-submitted", status="submitted")
    working_id   = _create_task("tp6-working",   status="working")
    completed_id = _create_task("tp6-completed", status="completed")
    failed_id    = _create_task("tp6-failed",    status="failed")

    status, data = _get("/tasks?status=submitted,working")
    assert status == 200, f"Expected 200: {status} {data}"

    task_ids = [t["id"] for t in data["tasks"]]

    # Both submitted and working should be present
    assert submitted_id in task_ids, (
        f"submitted task {submitted_id} should be in result: {task_ids}"
    )
    assert working_id in task_ids, (
        f"working task {working_id} should be in result: {task_ids}"
    )

    # completed and failed should be excluded
    assert completed_id not in task_ids, (
        f"completed task should be filtered out: {task_ids}"
    )
    assert failed_id not in task_ids, (
        f"failed task should be filtered out: {task_ids}"
    )

    # All returned tasks must have status in {submitted, working}
    allowed = {"submitted", "working"}
    for t in data["tasks"]:
        assert t.get("status") in allowed, (
            f"Unexpected status in multi-filter result: {t}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# TP7: Empty result — has_more=false, next_cursor=null
# ─────────────────────────────────────────────────────────────────────────────

def test_tp7_empty_result():
    """TP7: Impossible filter → empty tasks, has_more=false, next_cursor=null."""
    # Use a far-future created_after that no task can ever satisfy
    status, data = _get("/tasks?created_after=2099-12-31T23:59:59Z")
    assert status == 200, f"Expected 200: {status} {data}"

    assert data["tasks"] == [], (
        f"Expected empty tasks list: {data['tasks']}"
    )
    assert data["total"] == 0, (
        f"Expected total=0: {data['total']}"
    )
    assert data["has_more"] is False, (
        f"Expected has_more=False: {data['has_more']}"
    )
    assert data["next_cursor"] is None, (
        f"Expected next_cursor=null: {data['next_cursor']}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# TP8: Full regression — no params → backward-compatible response shape
# ─────────────────────────────────────────────────────────────────────────────

def test_tp8_no_params_backward_compat():
    """TP8: GET /tasks with no params returns all existing tasks, shape unchanged."""
    # Ensure at least 1 task exists
    _create_task("tp8-baseline")

    status, data = _get("/tasks")
    assert status == 200, f"Expected 200, got {status}: {data}"

    # Must have all required fields (old + new)
    required_keys = {"tasks", "total", "has_more", "next_cursor"}
    missing = required_keys - set(data.keys())
    assert not missing, f"Missing required keys: {missing} in {list(data.keys())}"

    # tasks must be a list
    assert isinstance(data["tasks"], list), (
        f"'tasks' must be a list: {type(data['tasks'])}"
    )

    # total must be >= number of tasks on this page
    assert data["total"] >= len(data["tasks"]), (
        f"total {data['total']} must be >= page len {len(data['tasks'])}"
    )

    # has_more + next_cursor must be consistent
    if data["has_more"]:
        assert data["next_cursor"] is not None, (
            f"next_cursor must be set when has_more=True: {data}"
        )
    else:
        assert data["next_cursor"] is None, (
            f"next_cursor must be null when has_more=False: {data}"
        )

    # AgentCard must advertise tasks_pagination capability
    # Note: /.well-known/acp.json returns {"self": {...}, "peer": {...}}; capabilities live in "self"
    _, card = _get("/.well-known/acp.json")
    self_card = card.get("self", card)  # support both wrapped and flat AgentCard formats
    caps = self_card.get("capabilities", {})
    assert caps.get("tasks_pagination") is True, (
        f"AgentCard missing capabilities.tasks_pagination=true: {caps}"
    )


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
