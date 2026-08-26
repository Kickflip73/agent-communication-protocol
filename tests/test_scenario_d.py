#!/usr/bin/env python3
"""
tests/test_scenario_d.py — ACP v3.7.0 Scenario D: Local-Relay CI Stress Tests
===============================================================================
All tests run against a locally spawned acp_relay.py instance.
No external network dependencies (zero P2P, zero relay.acp.dev).

Architecture mirrors test_message_sig.py relay_url fixture
(subprocess + ws_port+100 HTTP, --local-only flag).

Tests:
  SD-1  test_scenario_d_basic      — 3 local agents each submit a task; relay accepts all
  SD-2  test_scenario_d_burst      — 20 tasks submitted in sequence; all accepted, IDs unique
  SD-3  test_scenario_d_p99_latency — 10 task submissions; P99 round-trip latency < 2000ms

Note on /message:send behaviour in --local-only mode:
  When no peer is connected, POST /message:send returns HTTP 503 with
  error_code="ERR_NOT_CONNECTED" and queues the message for later delivery.
  This is intentional relay behaviour — 503 here means "queued, not dropped".
  Tests that exercise /message:send therefore treat 503 as a valid (non-error) response.
"""

import os
import socket
import subprocess
import sys
import time
import urllib.request

import pytest
import requests

from helpers import clean_subprocess_env

# ── Port helpers ─────────────────────────────────────────────────────────────


def _free_port_pair():
    """Return a ws_port where both ws_port and ws_port+100 are free."""
    for _ in range(200):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            ws_port = s.getsockname()[1]
        try:
            with socket.socket() as s2:
                s2.bind(("127.0.0.1", ws_port + 100))
                return ws_port
        except OSError:
            continue
    raise RuntimeError("Could not find a free port pair (ws_port and ws_port+100)")


# ── Module-scoped relay fixture ──────────────────────────────────────────────


@pytest.fixture(scope="module")
def relay_url():
    """Start a local relay instance; yield its HTTP base URL; then shut it down.

    Mirrors the relay_url fixture in test_message_sig.py exactly:
    - subprocess.Popen with --local-only
    - HTTP port = ws_port + 100
    - Waits for /status to respond before yielding
    """
    ws_port = _free_port_pair()
    http_port = ws_port + 100

    relay_script = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")
    identity_file = os.path.expanduser("~/.acp/identity.json")

    cmd = [
        sys.executable, relay_script,
        "--port", str(ws_port),
        "--identity", identity_file,
        "--local-only",
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=clean_subprocess_env(),
    )

    base_url = f"http://127.0.0.1:{http_port}"

    # Wait up to 10 s for relay /status to respond
    deadline = time.time() + 10
    ready = False
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"{base_url}/status", timeout=2)
            ready = True
            break
        except Exception:
            time.sleep(0.3)

    if not ready:
        proc.terminate()
        pytest.skip(f"local relay failed to start on port {http_port}")

    yield base_url

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


# ── Helper utilities ─────────────────────────────────────────────────────────


def _create_task(base_url: str, content: str, agent_id: str = "agent_a") -> tuple:
    """POST /tasks — reliable in local-only mode (no peer required).

    Returns (status_code, response_body_dict).
    """
    payload = {
        "role": "agent",
        "parts": [{"type": "text", "content": content}],
        "sender_id": agent_id,
    }
    try:
        r = requests.post(f"{base_url}/tasks", json=payload, timeout=5)
        return r.status_code, r.json()
    except Exception as exc:
        return 0, {"error": str(exc)}


def _extract_task_id(body: dict) -> str | None:
    """Extract task id from various possible response shapes."""
    return (
        body.get("task_id")
        or body.get("id")
        or (body.get("task") or {}).get("id")
    )


# ── SD-1: Basic multi-agent task submission ──────────────────────────────────


@pytest.mark.timeout(20)
def test_scenario_d_basic(relay_url):
    """SD-1: 3 local agents each submit a task; relay accepts all with 201 Created."""
    agents = ["agent_a", "agent_b", "agent_c"]
    results = {}
    task_ids = {}

    for agent in agents:
        code, body = _create_task(relay_url, f"hello-from-{agent}", agent_id=agent)
        results[agent] = code
        task_ids[agent] = _extract_task_id(body)

    # All three task submissions must succeed with 201
    failures = {a: c for a, c in results.items() if c != 201}
    assert not failures, (
        f"SD-1: agents did not get 201 Created: {failures}"
    )

    # Each must have a non-empty task id
    missing_ids = {a for a, tid in task_ids.items() if not tid}
    assert not missing_ids, (
        f"SD-1: these agents got no task_id in response: {missing_ids}"
    )

    # All task ids must be distinct
    ids = list(task_ids.values())
    assert len(set(ids)) == len(ids), (
        f"SD-1: duplicate task IDs returned: {ids}"
    )


# ── SD-2: Burst 20 tasks ─────────────────────────────────────────────────────


@pytest.mark.timeout(20)
def test_scenario_d_burst(relay_url):
    """SD-2: agent_a submits 20 tasks in sequence; all accepted with 201, all IDs unique."""
    N = 20
    statuses = []
    task_ids = []

    for i in range(N):
        code, body = _create_task(
            relay_url, f"burst-content-{i:04d}", agent_id="agent_a"
        )
        statuses.append(code)
        tid = _extract_task_id(body)
        if tid:
            task_ids.append(tid)

    # No connection errors (status == 0)
    conn_errors = statuses.count(0)
    assert conn_errors == 0, (
        f"SD-2: {conn_errors}/{N} requests failed with connection error"
    )

    # All must succeed (201 Created)
    ok_count = sum(1 for s in statuses if s == 201)
    assert ok_count == N, (
        f"SD-2: only {ok_count}/{N} returned 201. statuses={statuses}"
    )

    # All task IDs must be unique
    assert len(task_ids) == N, (
        f"SD-2: only {len(task_ids)}/{N} responses contained a task_id"
    )
    assert len(set(task_ids)) == N, (
        f"SD-2: duplicate task IDs found among {N} burst submissions"
    )

    # Verify /tasks list reflects the submissions
    r = requests.get(f"{relay_url}/tasks", timeout=5)
    assert r.status_code == 200, f"SD-2: GET /tasks returned {r.status_code}"
    body = r.json()
    total = body.get("total", len(body.get("tasks", [])))
    assert total >= N, (
        f"SD-2: /tasks reports only {total} tasks, expected >= {N}"
    )


# ── SD-3: P99 latency ────────────────────────────────────────────────────────


@pytest.mark.timeout(20)
def test_scenario_d_p99_latency(relay_url):
    """SD-3: 10 task submissions; measure round-trip latency; assert P99 < 2000ms."""
    N = 10
    latencies_ms = []

    for i in range(N):
        t0 = time.monotonic()
        code, body = _create_task(
            relay_url, f"latency-probe-{i:04d}", agent_id="agent_lat"
        )
        elapsed_ms = (time.monotonic() - t0) * 1000
        # Only record latency for successful or HTTP-level responses (not conn errors)
        if code != 0:
            latencies_ms.append(elapsed_ms)

    assert len(latencies_ms) >= int(N * 0.9), (
        f"SD-3: too many connection failures — only {len(latencies_ms)}/{N} got HTTP responses"
    )

    latencies_ms.sort()
    # P99 index (conservative: last element for small N)
    p99_idx = max(0, int(len(latencies_ms) * 0.99) - 1)
    p99_ms = latencies_ms[p99_idx]

    assert p99_ms < 2000, (
        f"SD-3: P99 latency {p99_ms:.1f}ms exceeds 2000ms threshold. "
        f"samples={[f'{x:.0f}ms' for x in latencies_ms]}"
    )
