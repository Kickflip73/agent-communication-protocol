"""
ACP v2.40 — AgentCard `agent_limitations` field tests (AL1–AL6)

The `agent_limitations` object in AgentCard and /status exposes explicit
constraint declarations (inspired by A2A IS#1694):

  agent_limitations: {
    max_message_size_bytes:  int   — max bytes per single message
    max_recv_queue_size:     int   — recv queue hard cap
    max_wait_seconds:        int   — long-poll max wait (v2.39 clamp)
    max_peers:               int   — concurrent peer connections
    supported_message_roles: list  — valid role values
    supported_priorities:    list  — valid priority values
  }

Distinct from `limitations` (LimitationObject[]), which describes capability
boundaries in structured narrative form (v2.20).

Tests:
  AL1: GET /.well-known/acp.json returns `agent_limitations` field in AgentCard
  AL2: agent_limitations.max_message_size_bytes == 65536
  AL3: agent_limitations.supported_priorities contains all four values
  AL4: agent_limitations.supported_message_roles contains user/agent/system
  AL5: GET /status also contains `agent_limitations` field
  AL6: agent_limitations.max_wait_seconds == 30 (matches v2.39 long-poll clamp)
"""

import json
import os
import socket
import subprocess
import sys
import time
import threading
import urllib.error
import urllib.request

import pytest

# ── helpers ───────────────────────────────────────────────────────────────────

RELAY_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")


def _free_port():
    """Return a free port, ensuring both port and port+100 are available."""
    for _ in range(50):
        with socket.socket() as s:
            s.bind(("", 0))
            p = s.getsockname()[1]
        try:
            with socket.socket() as s2:
                s2.bind(("", p + 100))
            return p
        except OSError:
            continue
    raise RuntimeError("Could not find a port pair (p, p+100) that are both free")


def _http(port, path, method="GET", body=None, timeout=15):
    url = f"http://127.0.0.1:{port}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read()), e.code
        except Exception:
            return {}, e.code


def _start_relay(ws_port, name, local_only=True):
    env = os.environ.copy()
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        env.pop(k, None)
    cmd = [sys.executable, RELAY_SCRIPT, "--port", str(ws_port), "--name", name]
    if local_only:
        cmd += ["--local-only"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    for s in (proc.stdout, proc.stderr):
        threading.Thread(target=lambda x=s: x.read(), daemon=True).start()
    return proc


def _wait_for(fn, timeout=15, interval=0.4):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if fn():
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


# ── module-scoped fixture: single relay instance ──────────────────────────────

@pytest.fixture(scope="module")
def al_relay():
    ws_port = _free_port()
    http_port = ws_port + 100
    proc = _start_relay(ws_port, "AL-Agent")

    ready = _wait_for(lambda: _http(http_port, "/status")[1] == 200, timeout=15)
    if not ready:
        proc.kill()
        pytest.fail("Relay did not start in time")

    yield {"proc": proc, "http_port": http_port}

    proc.kill()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.terminate()


# ── AL1: /.well-known/acp.json returns agent_limitations ─────────────────────

def test_al1_agentcard_has_agent_limitations(al_relay):
    """AL1: GET /.well-known/acp.json returns agent_limitations field in AgentCard."""
    data, code = _http(al_relay["http_port"], "/.well-known/acp.json")
    assert code == 200, f"Expected 200, got {code}"
    card = data.get("self", {})
    assert "agent_limitations" in card, (
        f"agent_limitations missing from AgentCard: {list(card.keys())}"
    )
    assert isinstance(card["agent_limitations"], dict), (
        f"agent_limitations should be a dict, got {type(card['agent_limitations'])}"
    )


# ── AL2: max_message_size_bytes == 65536 ─────────────────────────────────────

def test_al2_max_message_size_bytes(al_relay):
    """AL2: agent_limitations.max_message_size_bytes == 65536."""
    data, code = _http(al_relay["http_port"], "/.well-known/acp.json")
    assert code == 200
    lim = data.get("self", {}).get("agent_limitations", {})
    assert "max_message_size_bytes" in lim, (
        f"max_message_size_bytes missing from agent_limitations: {lim}"
    )
    assert lim["max_message_size_bytes"] == 65536, (
        f"Expected 65536, got {lim['max_message_size_bytes']}"
    )


# ── AL3: supported_priorities contains all four values ───────────────────────

def test_al3_supported_priorities(al_relay):
    """AL3: agent_limitations.supported_priorities contains all four values."""
    data, code = _http(al_relay["http_port"], "/.well-known/acp.json")
    assert code == 200
    lim = data.get("self", {}).get("agent_limitations", {})
    assert "supported_priorities" in lim, (
        f"supported_priorities missing from agent_limitations: {lim}"
    )
    priorities = lim["supported_priorities"]
    expected = {"critical", "high", "normal", "low"}
    actual = set(priorities)
    assert actual == expected, (
        f"supported_priorities mismatch: expected {expected}, got {actual}"
    )


# ── AL4: supported_message_roles contains user/agent/system ──────────────────

def test_al4_supported_message_roles(al_relay):
    """AL4: agent_limitations.supported_message_roles contains user, agent, system."""
    data, code = _http(al_relay["http_port"], "/.well-known/acp.json")
    assert code == 200
    lim = data.get("self", {}).get("agent_limitations", {})
    assert "supported_message_roles" in lim, (
        f"supported_message_roles missing from agent_limitations: {lim}"
    )
    roles = set(lim["supported_message_roles"])
    for role in ("user", "agent", "system"):
        assert role in roles, (
            f"Role '{role}' missing from supported_message_roles: {roles}"
        )


# ── AL5: /status contains agent_limitations ──────────────────────────────────

def test_al5_status_has_agent_limitations(al_relay):
    """AL5: GET /status also contains agent_limitations field."""
    data, code = _http(al_relay["http_port"], "/status")
    assert code == 200, f"Expected 200, got {code}"
    assert "agent_limitations" in data, (
        f"agent_limitations missing from /status: {list(data.keys())}"
    )
    lim = data["agent_limitations"]
    assert isinstance(lim, dict), (
        f"agent_limitations in /status should be a dict, got {type(lim)}"
    )
    assert "max_message_size_bytes" in lim, (
        f"max_message_size_bytes missing from /status agent_limitations: {lim}"
    )


# ── AL6: max_wait_seconds == 30 (v2.39 long-poll clamp) ──────────────────────

def test_al6_max_wait_seconds(al_relay):
    """AL6: agent_limitations.max_wait_seconds == 30 (matches v2.39 long-poll clamp)."""
    data, code = _http(al_relay["http_port"], "/.well-known/acp.json")
    assert code == 200
    lim = data.get("self", {}).get("agent_limitations", {})
    assert "max_wait_seconds" in lim, (
        f"max_wait_seconds missing from agent_limitations: {lim}"
    )
    assert lim["max_wait_seconds"] == 30, (
        f"Expected 30 (v2.39 long-poll clamp), got {lim['max_wait_seconds']}"
    )
