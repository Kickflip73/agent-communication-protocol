"""
tests/test_task_evidence.py
ACP v2.81 — task_evidence lifecycle evidence anchoring
TE1–TE12 (12 test cases)
"""
import socket
import subprocess
import time
import pytest
import requests


# ─── helpers ────────────────────────────────────────────────────────────────

def _free_port() -> int:
    """Return a free TCP port on localhost."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ─── module-scope fixture ────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def relay():
    """Start a single ACP relay for all TE tests; yield base URL; teardown.

    ACP relay uses --port for WS; HTTP port = WS port + 100.
    We pick a WS port such that WS+100 is also free.
    """
    # Find a ws_port where ws_port+100 is also available
    for _ in range(20):
        ws_port = _free_port()
        http_port = ws_port + 100
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", http_port))
                break  # both ports free
            except OSError:
                continue
    else:
        pytest.fail("Could not find two consecutive-100 free ports")

    proc = subprocess.Popen(
        [
            "python3", "relay/acp_relay.py",
            "--port", str(ws_port),
            "--name", "TETest",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    base = f"http://127.0.0.1:{http_port}"
    # wait for relay to be ready
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            r = requests.get(f"{base}/status", timeout=2)
            if r.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(0.2)
    else:
        proc.terminate()
        raise RuntimeError("Relay did not start in time")
    yield base
    proc.kill()
    try:
        proc.wait(timeout=10)
    except Exception:
        pass


# ─── tests ──────────────────────────────────────────────────────────────────

def test_TE1_post_evidence_requested(relay):
    """TE1: POST /tasks/t1/evidence — submit 'requested' event, seq=0"""
    r = requests.post(
        f"{relay}/tasks/t1/evidence",
        json={"event_type": "requested", "consumer_id": "c1", "artifact": {"key": "val"}},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "recorded"
    assert data["task_id"] == "t1"
    assert data["seq"] == 0
    assert "recorded_at" in data


def test_TE2_post_second_evidence_seq_increments(relay):
    """TE2: second POST to same task_id → seq=1"""
    r = requests.post(
        f"{relay}/tasks/t1/evidence",
        json={"event_type": "updated", "consumer_id": "c2"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["seq"] == 1
    assert data["task_id"] == "t1"


def test_TE3_get_evidence_list(relay):
    """TE3: GET /tasks/t1/evidence — count=2, list correct"""
    r = requests.get(f"{relay}/tasks/t1/evidence")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["task_id"] == "t1"
    assert data["count"] == 2
    assert len(data["evidence"]) == 2
    assert data["evidence"][0]["seq"] == 0
    assert data["evidence"][1]["seq"] == 1
    assert data["evidence"][0]["event_type"] == "requested"
    assert data["evidence"][1]["event_type"] == "updated"


def test_TE4_get_evidence_latest(relay):
    """TE4: GET /tasks/t1/evidence/latest — returns seq=1"""
    r = requests.get(f"{relay}/tasks/t1/evidence/latest")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["seq"] == 1
    assert data["task_id"] == "t1"
    assert data["event_type"] == "updated"


def test_TE5_different_task_ids_isolated(relay):
    """TE5: t2 evidence is isolated from t1"""
    r = requests.post(
        f"{relay}/tasks/t2/evidence",
        json={"event_type": "completed"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["seq"] == 0  # starts at 0 for t2, not 2
    assert data["task_id"] == "t2"

    # t1 still has 2 entries
    r2 = requests.get(f"{relay}/tasks/t1/evidence")
    assert r2.json()["count"] == 2

    # t2 has 1 entry
    r3 = requests.get(f"{relay}/tasks/t2/evidence")
    assert r3.json()["count"] == 1


def test_TE6_missing_event_type_returns_400(relay):
    """TE6: missing event_type → 400"""
    r = requests.post(
        f"{relay}/tasks/t3/evidence",
        json={"consumer_id": "c1", "artifact": {}},
    )
    assert r.status_code == 400, r.text
    assert "event_type" in r.json().get("error", "")


def test_TE7_invalid_event_type_returns_400(relay):
    """TE7: invalid event_type value → 400"""
    r = requests.post(
        f"{relay}/tasks/t3/evidence",
        json={"event_type": "unknown"},
    )
    assert r.status_code == 400, r.text
    assert "invalid" in r.json().get("error", "").lower() or "event_type" in r.json().get("error", "")


def test_TE8_artifact_optional(relay):
    """TE8: no artifact field — still records successfully"""
    r = requests.post(
        f"{relay}/tasks/t4/evidence",
        json={"event_type": "failed", "consumer_id": "c_noa"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "recorded"
    assert data["seq"] == 0


def test_TE9_get_evidence_nonexistent_task_returns_empty(relay):
    """TE9: GET evidence for nonexistent task → count=0, not 404"""
    r = requests.get(f"{relay}/tasks/nonexistent/evidence")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["task_id"] == "nonexistent"
    assert data["count"] == 0
    assert data["evidence"] == []


def test_TE10_get_latest_nonexistent_task_returns_404(relay):
    """TE10: GET /tasks/nonexistent/evidence/latest → 404"""
    r = requests.get(f"{relay}/tasks/nonexistent_xyz/evidence/latest")
    assert r.status_code == 404, r.text


def test_TE11_capabilities_task_evidence(relay):
    """TE11: /status agent_card.capabilities.task_evidence == True"""
    r = requests.get(f"{relay}/status")
    assert r.status_code == 200, r.text
    body = r.json()
    # capabilities live under agent_card in /status
    agent_card = body.get("agent_card") or {}
    caps = agent_card.get("capabilities", {})
    assert caps.get("task_evidence") is True, f"task_evidence not True in /status agent_card; caps={caps}"


def test_TE12_agentcard_capabilities_task_evidence(relay):
    """TE12: AgentCard /.well-known/acp.json has capabilities.task_evidence == True"""
    r = requests.get(f"{relay}/.well-known/acp.json")
    assert r.status_code == 200, r.text
    body = r.json()
    # /.well-known/acp.json returns {"self": <AgentCard>, "peer": ...}
    card = body.get("self") or body
    caps = card.get("capabilities", {})
    assert caps.get("task_evidence") is True, f"task_evidence not True in AgentCard; caps keys sample={list(caps)[-5:]}"
