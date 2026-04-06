"""
test_runtime_limitations.py — ACP v2.69: GET /limitations/runtime tests (RL-1..10)

Dynamic runtime limitations endpoint.
Aligns with A2A #1694 @citriac Agent Exchange Hub v0.4.0 stable/runtime split.
"""

import pytest
import subprocess
import sys
import os
import time
import socket
import requests

RELAY = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")


def _free_port():
    """Find a free port."""
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def relay_url():
    """Start a relay, yield its HTTP base URL, tear down after module.

    acp_relay.py uses --port for WS; HTTP API listens on port+100.
    """
    ws_port = _free_port()
    http_port = ws_port + 100
    proc = subprocess.Popen(
        [sys.executable, RELAY, "--port", str(ws_port), "--name", "RLTestRelay"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            r = requests.get(f"http://localhost:{http_port}/status", timeout=1)
            if r.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(0.2)
    else:
        proc.terminate()
        pytest.fail("Relay did not start in time")

    yield f"http://localhost:{http_port}"

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


# ── RL-1: GET /limitations/runtime returns ok=True, runtime{} dict, version, timestamp ──

def test_rl1_basic_shape(relay_url):
    """RL-1: GET /limitations/runtime returns ok=True, runtime{} dict, version, timestamp."""
    r = requests.get(f"{relay_url}/limitations/runtime", timeout=5)
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert isinstance(data.get("runtime"), dict)
    assert "version" in data
    assert "timestamp" in data


# ── RL-2: runtime dict has all required keys ─────────────────────────────────

def test_rl2_required_keys(relay_url):
    """RL-2: runtime dict has all required keys: current_load, queue_depth, active_tasks, total_tasks, memory_usage_mb."""
    r = requests.get(f"{relay_url}/limitations/runtime", timeout=5)
    assert r.status_code == 200
    runtime = r.json()["runtime"]
    for key in ("current_load", "queue_depth", "active_tasks", "total_tasks", "memory_usage_mb"):
        assert key in runtime, f"Missing key: {key}"


# ── RL-3: memory_usage_mb is a positive float ────────────────────────────────

def test_rl3_memory_positive(relay_url):
    """RL-3: memory_usage_mb is a positive float (> 0)."""
    r = requests.get(f"{relay_url}/limitations/runtime", timeout=5)
    assert r.status_code == 200
    mb = r.json()["runtime"]["memory_usage_mb"]
    assert isinstance(mb, (int, float))
    assert mb > 0, f"memory_usage_mb should be > 0, got {mb}"


# ── RL-4: active_tasks == 0 when no tasks exist ──────────────────────────────

def test_rl4_active_tasks_zero_initially(relay_url):
    """RL-4: active_tasks == 0 when no tasks exist."""
    r = requests.get(f"{relay_url}/limitations/runtime", timeout=5)
    assert r.status_code == 200
    active = r.json()["runtime"]["active_tasks"]
    assert active == 0, f"Expected 0 active_tasks initially, got {active}"


# ── RL-5: queue_depth >= 0 initially ─────────────────────────────────────────

def test_rl5_queue_depth_nonneg(relay_url):
    """RL-5: queue_depth >= 0 initially."""
    r = requests.get(f"{relay_url}/limitations/runtime", timeout=5)
    assert r.status_code == 200
    qd = r.json()["runtime"]["queue_depth"]
    assert isinstance(qd, int)
    assert qd >= 0, f"queue_depth should be >= 0, got {qd}"


# ── RL-6: After 1 task completes, active_tasks still >= 0 ────────────────────

def test_rl6_active_tasks_after_task(relay_url):
    """RL-6: After 1 task completes, active_tasks still >= 0."""
    # Create a task via /tasks/create (correct ACP format)
    create_r = requests.post(
        f"{relay_url}/tasks/create",
        json={"role": "user", "parts": [{"type": "text", "content": "rl-6 test"}]},
        timeout=5,
    )
    assert create_r.status_code in (200, 201, 202)

    # Wait briefly for task to settle
    time.sleep(0.5)

    r = requests.get(f"{relay_url}/limitations/runtime", timeout=5)
    assert r.status_code == 200
    active = r.json()["runtime"]["active_tasks"]
    assert active >= 0, f"active_tasks should be >= 0 after task, got {active}"


# ── RL-7: AgentCard capabilities.runtime_limitations == True ─────────────────

def test_rl7_agentcard_capability(relay_url):
    """RL-7: AgentCard capabilities.runtime_limitations == True."""
    r = requests.get(f"{relay_url}/.well-known/acp.json", timeout=5)
    assert r.status_code == 200
    card = r.json()
    # AgentCard is wrapped: {"self": {...}, "peer": {...}}
    agent_card = card.get("self", card)
    caps = agent_card.get("capabilities", {})
    assert caps.get("runtime_limitations") is True, (
        f"capabilities.runtime_limitations should be True, got {caps.get('runtime_limitations')}"
    )


# ── RL-8: AgentCard endpoints.runtime_limitations == "/limitations/runtime" ──

def test_rl8_agentcard_endpoint(relay_url):
    """RL-8: AgentCard endpoints.runtime_limitations == "/limitations/runtime"."""
    r = requests.get(f"{relay_url}/.well-known/acp.json", timeout=5)
    assert r.status_code == 200
    card = r.json()
    # AgentCard is wrapped: {"self": {...}, "peer": {...}}
    agent_card = card.get("self", card)
    endpoints = agent_card.get("endpoints", {})
    assert endpoints.get("runtime_limitations") == "/limitations/runtime", (
        f"endpoints.runtime_limitations should be '/limitations/runtime', "
        f"got {endpoints.get('runtime_limitations')}"
    )


# ── RL-9: peer_count == 0 when no WS peers connected ─────────────────────────

def test_rl9_peer_count_zero(relay_url):
    """RL-9: peer_count == 0 when no WS peers connected (HTTP-only relay)."""
    r = requests.get(f"{relay_url}/limitations/runtime", timeout=5)
    assert r.status_code == 200
    runtime = r.json()["runtime"]
    assert "peer_count" in runtime
    peer_count = runtime["peer_count"]
    assert isinstance(peer_count, int)
    assert peer_count == 0, f"peer_count should be 0 with no WS peers, got {peer_count}"


# ── RL-10: total_tasks >= 0; memory_source in ("psutil", "resource") ─────────

def test_rl10_total_tasks_and_memory_source(relay_url):
    """RL-10: total_tasks >= 0; memory_source in ("psutil", "resource")."""
    r = requests.get(f"{relay_url}/limitations/runtime", timeout=5)
    assert r.status_code == 200
    runtime = r.json()["runtime"]

    total = runtime.get("total_tasks")
    assert isinstance(total, int)
    assert total >= 0, f"total_tasks should be >= 0, got {total}"

    source = runtime.get("memory_source")
    assert source in ("psutil", "resource"), (
        f"memory_source should be 'psutil' or 'resource', got {source!r}"
    )
