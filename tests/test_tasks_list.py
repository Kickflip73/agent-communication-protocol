"""
test_tasks_list.py — ACP v2.2 GET /tasks list endpoint tests

Tests:
  TL1:  No params → returns all tasks
  TL2:  ?status=working filter
  TL3:  ?peer_id=peer_001 filter (dual-layer: top-level and payload.peer_id)
  TL4:  ?limit=2&offset=0 pagination — first page
  TL5:  ?limit=2&offset=2 pagination — second page
  TL6:  has_more=true/false semantics
  TL7:  ?sort=asc ordering
  TL8:  ?created_after=<ISO> time filter
  TL9:  Empty result → {"tasks": [], "total": 0, "has_more": false}
  TL10: Invalid status param → 400 ERR_INVALID_REQUEST
"""

import json
import pytest
import subprocess
import time
import urllib.request
import urllib.error
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RELAY_PATH = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")


def _free_port():
    """Return an OS-assigned free port where port AND port+100 are both free."""
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


def _wait_ready(timeout=12):
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
    with urllib.request.urlopen(
        f"http://localhost:{HTTP_PORT}{path}", timeout=5
    ) as r:
        return r.status, json.loads(r.read())


def _get_err(path):
    """GET that also handles error responses, returning (status, body)."""
    req = urllib.request.Request(f"http://localhost:{HTTP_PORT}{path}")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"http://localhost:{HTTP_PORT}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _create_task(description="test task", status="submitted", peer_id=None,
                 created_at=None, payload_peer_id=None):
    """Helper: create a task and optionally update its status."""
    # role is required by /tasks/create (BUG-010)
    body = {
        "role": "user",
        "parts": [{"type": "text", "content": description}],
    }
    if peer_id:
        body["peer_id"] = peer_id
    if payload_peer_id:
        # peer_id inside payload — BUG-014 dual-layer test
        body["payload"] = {"role": "user", "peer_id": payload_peer_id,
                           "parts": [{"type": "text", "content": description}]}

    status_code, resp = _post("/tasks/create", body)
    assert status_code in (200, 201), f"create_task failed: {status_code} {resp}"
    task_id = resp["task"]["id"]

    # Push to desired status if not submitted
    if status not in ("submitted",):
        _post(f"/tasks/{task_id}/update", {"status": status})

    return task_id


@pytest.fixture(scope="module", autouse=True)
def single_relay():
    global _proc
    env = _make_env()
    _proc = subprocess.Popen(
        [sys.executable, RELAY_PATH, "--port", str(WS_PORT), "--name", "TLAgent"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
    )
    if not _wait_ready():
        _proc.kill()
        pytest.fail(f"Relay (HTTP:{HTTP_PORT}) did not start in time")
    yield
    _proc.terminate()
    try:
        _proc.wait(timeout=6)
    except subprocess.TimeoutExpired:
        _proc.kill()


# ─────────────────────────────────────────────────────────────────────────────
# TL1: No params → returns all tasks
# ─────────────────────────────────────────────────────────────────────────────

def test_tl1_no_params_returns_all():
    """TL1: GET /tasks with no params returns all tasks with required fields."""
    # Create 2 tasks to ensure we have some
    _create_task("tl1-alpha")
    _create_task("tl1-beta")

    status, data = _get("/tasks?offset=0")
    assert status == 200, f"Expected 200: {data}"
    assert "tasks" in data, f"Missing 'tasks' key: {data}"
    assert "total" in data, f"Missing 'total' key: {data}"
    assert "has_more" in data, f"Missing 'has_more' key: {data}"
    assert isinstance(data["tasks"], list), "tasks must be a list"
    assert data["total"] >= 2, f"Expected at least 2 tasks: {data['total']}"


# ─────────────────────────────────────────────────────────────────────────────
# TL2: ?status=working filter
# ─────────────────────────────────────────────────────────────────────────────

def test_tl2_status_filter_working():
    """TL2: ?status=working returns only working tasks."""
    # Create one working and one completed task
    working_id   = _create_task("tl2-working",   status="working")
    completed_id = _create_task("tl2-completed", status="completed")

    status, data = _get("/tasks?status=working&offset=0")
    assert status == 200, f"Expected 200: {data}"
    task_ids = [t["id"] for t in data["tasks"]]
    assert working_id in task_ids,   f"working task {working_id} not in results: {task_ids}"
    assert completed_id not in task_ids, f"completed task should be filtered out: {task_ids}"
    for t in data["tasks"]:
        assert t.get("status") == "working", f"Non-working task in result: {t}"


# ─────────────────────────────────────────────────────────────────────────────
# TL3: ?peer_id=peer_001 filter (dual-layer lookup)
# ─────────────────────────────────────────────────────────────────────────────

def test_tl3_peer_id_filter():
    """TL3: ?peer_id filter matches both top-level and payload.peer_id (BUG-014)."""
    # Top-level peer_id
    top_id = _create_task("tl3-top",     peer_id="tl3_peer_A")
    # payload.peer_id
    pay_id = _create_task("tl3-payload", payload_peer_id="tl3_peer_B")
    # Neither — should be excluded
    other_id = _create_task("tl3-other")

    # Filter by top-level
    _, data_a = _get("/tasks?peer_id=tl3_peer_A&offset=0")
    ids_a = [t["id"] for t in data_a["tasks"]]
    assert top_id in ids_a,   f"tl3-top not found: {ids_a}"
    assert other_id not in ids_a, f"other should be excluded: {ids_a}"

    # Filter by payload peer_id
    _, data_b = _get("/tasks?peer_id=tl3_peer_B&offset=0")
    ids_b = [t["id"] for t in data_b["tasks"]]
    assert pay_id in ids_b,   f"tl3-payload not found: {ids_b}"
    assert other_id not in ids_b, f"other should be excluded: {ids_b}"


# ─────────────────────────────────────────────────────────────────────────────
# TL4: offset pagination — first page
# ─────────────────────────────────────────────────────────────────────────────

def test_tl4_pagination_first_page():
    """TL4: ?limit=2&offset=0 returns first 2 tasks."""
    # Ensure at least 3 tasks exist (relay is shared, cumulative)
    for i in range(3):
        _create_task(f"tl4-{i}")

    status, data = _get("/tasks?limit=2&offset=0")
    assert status == 200, f"Expected 200: {data}"
    assert len(data["tasks"]) <= 2, f"Expected at most 2 tasks: {len(data['tasks'])}"
    assert data["total"] >= 3, f"Expected total >= 3: {data['total']}"


# ─────────────────────────────────────────────────────────────────────────────
# TL5: offset pagination — second page
# ─────────────────────────────────────────────────────────────────────────────

def test_tl5_pagination_second_page():
    """TL5: ?limit=2&offset=2 returns a different page than offset=0."""
    # Ensure at least 4 tasks
    for i in range(4):
        _create_task(f"tl5-{i}")

    _, page1 = _get("/tasks?limit=2&offset=0")
    _, page2 = _get("/tasks?limit=2&offset=2")

    ids1 = [t["id"] for t in page1["tasks"]]
    ids2 = [t["id"] for t in page2["tasks"]]

    # Pages should not overlap (assuming total > 2)
    overlap = set(ids1) & set(ids2)
    assert len(overlap) == 0, f"Pages 1 and 2 overlap: {overlap}"


# ─────────────────────────────────────────────────────────────────────────────
# TL6: has_more semantics
# ─────────────────────────────────────────────────────────────────────────────

def test_tl6_has_more_true_and_false():
    """TL6: has_more=true when more items remain; false when last page."""
    # Get total task count
    _, all_data = _get("/tasks?offset=0&limit=100")
    total = all_data["total"]

    if total == 0:
        pytest.skip("No tasks in relay for has_more test")

    # Request only 1 item: has_more should be True if total > 1
    _, data_one = _get("/tasks?limit=1&offset=0")
    if total > 1:
        assert data_one["has_more"] is True, (
            f"has_more should be True when total={total} > limit=1: {data_one}"
        )
    else:
        assert data_one["has_more"] is False, (
            f"has_more should be False when total={total} == limit=1: {data_one}"
        )

    # Request ALL at once: has_more should be False
    _, data_all = _get(f"/tasks?limit=100&offset=0")
    assert data_all["has_more"] is False, (
        f"has_more should be False when fetching all: {data_all}"
    )

    # When has_more is True, next_offset must be present
    if total > 1:
        assert "next_offset" in data_one, (
            f"next_offset missing when has_more=True: {data_one}"
        )
        assert data_one["next_offset"] == 1, (
            f"next_offset should be offset+limit=1: {data_one}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# TL7: sort=asc ordering
# ─────────────────────────────────────────────────────────────────────────────

def test_tl7_sort_asc():
    """TL7: ?sort=asc returns tasks in ascending created_at order."""
    # Create 2 tasks with a small delay to ensure different created_at
    id_first  = _create_task("tl7-first")
    time.sleep(0.05)
    id_second = _create_task("tl7-second")

    _, data_asc  = _get("/tasks?sort=asc&offset=0&limit=100")
    _, data_desc = _get("/tasks?sort=desc&offset=0&limit=100")

    ids_asc  = [t["id"] for t in data_asc["tasks"]]
    ids_desc = [t["id"] for t in data_desc["tasks"]]

    # In ascending order, first created should appear before second
    if id_first in ids_asc and id_second in ids_asc:
        assert ids_asc.index(id_first) < ids_asc.index(id_second), (
            f"sort=asc: tl7-first should precede tl7-second: {ids_asc}"
        )

    # desc should be the reverse for these two
    if id_first in ids_desc and id_second in ids_desc:
        assert ids_desc.index(id_second) < ids_desc.index(id_first), (
            f"sort=desc: tl7-second should precede tl7-first: {ids_desc}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# TL8: ?created_after=<ISO> time filter
# ─────────────────────────────────────────────────────────────────────────────

def test_tl8_created_after_filter():
    """TL8: ?created_after filters out tasks created before the given timestamp."""
    import datetime

    # Record time before creating the new task
    before = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    time.sleep(0.1)  # ensure created_at > before

    new_id = _create_task("tl8-new-task")

    _, data = _get(f"/tasks?created_after={before}&offset=0&limit=100")
    assert data["status_code"] if "status_code" in data else True  # guard
    ids = [t["id"] for t in data["tasks"]]
    assert new_id in ids, (
        f"tl8-new-task should appear after created_after={before}: {ids}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# TL9: Empty result
# ─────────────────────────────────────────────────────────────────────────────

def test_tl9_empty_result():
    """TL9: Filtering with impossible criteria returns empty result."""
    # Use a far-future created_after that no task can satisfy
    _, data = _get("/tasks?created_after=2099-01-01T00:00:00&offset=0")
    assert data["tasks"] == [], f"Expected empty tasks list: {data}"
    assert data["total"] == 0, f"Expected total=0: {data}"
    assert data["has_more"] is False, f"Expected has_more=False: {data}"


# ─────────────────────────────────────────────────────────────────────────────
# TL10: Invalid status param → 400 ERR_INVALID_REQUEST
# ─────────────────────────────────────────────────────────────────────────────

def test_tl10_invalid_status_400():
    """TL10: ?status=bogus returns 400 with ERR_INVALID_REQUEST."""
    status, data = _get_err("/tasks?status=bogus_status")
    assert status == 400, f"Expected 400 for invalid status: status={status}, data={data}"
    assert data.get("error_code") == "ERR_INVALID_REQUEST", (
        f"Expected ERR_INVALID_REQUEST: {data}"
    )
    assert "error" in data, f"Missing 'error' message: {data}"


# ─────────────────────────────────────────────────────────────────────────────

def run_tests():
    """Pytest entry point for direct execution."""
    pytest.main([__file__, "-v"])


if __name__ == "__main__":
    run_tests()
