"""
test_direct_message.py — ACP v2.67: Direct Message mode tests (DM-1..12)

POST /message/send — Returns Message directly without creating a Task.
Aligns with A2A v1.0.0 SendMessageResponse { oneof { Task task; Message message; } }
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
        [sys.executable, RELAY, "--port", str(ws_port), "--name", "DMTestRelay"],
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


# ─────────────────────────────────────────────────────────────────────────────
# DM-1: Basic Direct Message — 200 + type="message" + message_id
# ─────────────────────────────────────────────────────────────────────────────
def test_dm1_basic_direct_message(relay_url):
    """DM-1: POST /message/send returns 200 with type='message' and message_id."""
    r = requests.post(f"{relay_url}/message/send", json={
        "role": "user",
        "text": "Hello, what is 2+2?",
    })
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    d = r.json()
    assert d["ok"] is True
    assert d["type"] == "message", f"Expected type='message', got: {d.get('type')}"
    assert "message_id" in d
    # _make_id uses underscore separator: "msg_<hex12>"
    assert d["message_id"].startswith("msg")
    assert d["role"] == "user"
    assert isinstance(d["parts"], list) and len(d["parts"]) > 0
    assert "timestamp" in d


# ─────────────────────────────────────────────────────────────────────────────
# DM-2: role=agent is accepted
# ─────────────────────────────────────────────────────────────────────────────
def test_dm2_role_agent_accepted(relay_url):
    """DM-2: role='agent' is accepted."""
    r = requests.post(f"{relay_url}/message/send", json={
        "role": "agent",
        "text": "Ping from agent.",
    })
    assert r.status_code == 200
    d = r.json()
    assert d["role"] == "agent"
    assert d["type"] == "message"


# ─────────────────────────────────────────────────────────────────────────────
# DM-3: No Task created — GET /tasks does not include the DM message_id
# ─────────────────────────────────────────────────────────────────────────────
def test_dm3_no_task_created(relay_url):
    """DM-3: Direct Message does NOT create a Task."""
    r = requests.post(f"{relay_url}/message/send", json={
        "role": "user",
        "text": "Quick question, no task needed.",
    })
    assert r.status_code == 200
    msg_id = r.json()["message_id"]

    # Check /tasks — message_id should not appear as a task id
    tasks_r = requests.get(f"{relay_url}/tasks")
    assert tasks_r.status_code == 200
    tasks = tasks_r.json().get("tasks", [])
    task_ids = [t["id"] for t in tasks]
    assert msg_id not in task_ids, f"message_id {msg_id} unexpectedly appeared as a Task id"


# ─────────────────────────────────────────────────────────────────────────────
# DM-4: context_id is preserved in response
# ─────────────────────────────────────────────────────────────────────────────
def test_dm4_context_id_preserved(relay_url):
    """DM-4: Supplied context_id is echoed back in response."""
    r = requests.post(f"{relay_url}/message/send", json={
        "role": "user",
        "text": "Context-scoped message.",
        "context_id": "ctx-test-001",
    })
    assert r.status_code == 200
    d = r.json()
    assert d.get("context_id") == "ctx-test-001"


# ─────────────────────────────────────────────────────────────────────────────
# DM-5: task_id association (optional — does not change Task state)
# ─────────────────────────────────────────────────────────────────────────────
def test_dm5_task_id_association(relay_url):
    """DM-5: task_id can be associated with the DM without changing any Task state."""
    r = requests.post(f"{relay_url}/message/send", json={
        "role": "user",
        "text": "Linked to a task reference.",
        "task_id": "task-ref-abc",
    })
    assert r.status_code == 200
    d = r.json()
    assert d.get("task_id") == "task-ref-abc"
    assert d["type"] == "message"


# ─────────────────────────────────────────────────────────────────────────────
# DM-6: parts[] format — text/file/data all accepted
# ─────────────────────────────────────────────────────────────────────────────
def test_dm6_parts_text_type(relay_url):
    """DM-6a: parts with type=text accepted."""
    r = requests.post(f"{relay_url}/message/send", json={
        "role": "user",
        "parts": [{"type": "text", "text": "Hello from parts"}],
    })
    assert r.status_code == 200
    d = r.json()
    assert d["parts"][0].get("type") == "text"


def test_dm6b_parts_data_type(relay_url):
    """DM-6b: parts with type=data accepted."""
    r = requests.post(f"{relay_url}/message/send", json={
        "role": "agent",
        "parts": [{"type": "data", "data": {"key": "value"}}],
    })
    assert r.status_code == 200
    d = r.json()
    assert d["type"] == "message"
    assert len(d["parts"]) == 1


def test_dm6c_parts_file_type(relay_url):
    """DM-6c: parts with type=file accepted."""
    r = requests.post(f"{relay_url}/message/send", json={
        "role": "agent",
        "parts": [{"type": "file", "url": "https://example.com/report.pdf", "mime_type": "application/pdf"}],
    })
    assert r.status_code == 200
    d = r.json()
    assert d["type"] == "message"


# ─────────────────────────────────────────────────────────────────────────────
# DM-7: Missing parts → 400
# ─────────────────────────────────────────────────────────────────────────────
def test_dm7_missing_parts_returns_400(relay_url):
    """DM-7: No parts and no text → 400."""
    r = requests.post(f"{relay_url}/message/send", json={
        "role": "user",
        # no text, no parts
    })
    assert r.status_code == 400, f"Expected 400, got {r.status_code}"
    d = r.json()
    assert d.get("ok") is False or "error" in d


# ─────────────────────────────────────────────────────────────────────────────
# DM-8: Missing role → 400
# ─────────────────────────────────────────────────────────────────────────────
def test_dm8_missing_role_returns_400(relay_url):
    """DM-8: Missing role → 400."""
    r = requests.post(f"{relay_url}/message/send", json={
        "text": "No role supplied",
    })
    assert r.status_code == 400, f"Expected 400, got {r.status_code}"
    d = r.json()
    assert d.get("ok") is False or "error" in d


# ─────────────────────────────────────────────────────────────────────────────
# DM-9: AgentCard capabilities.direct_message = True
# ─────────────────────────────────────────────────────────────────────────────
def test_dm9_agentcard_capability(relay_url):
    """DM-9: AgentCard capabilities.direct_message is True.

    /.well-known/acp.json response has structure: {"self": <card>, "peer": ...}
    """
    r = requests.get(f"{relay_url}/.well-known/acp.json")
    assert r.status_code == 200
    data = r.json()
    # Unwrap {"self": card, "peer": ...} envelope
    card = data.get("self", data)
    caps = card.get("capabilities", {})
    assert caps.get("direct_message") is True, \
        f"AgentCard missing capabilities.direct_message=True; got: {caps.get('direct_message')}"


# ─────────────────────────────────────────────────────────────────────────────
# DM-10: AgentCard endpoints.message_send = "/message/send"
# ─────────────────────────────────────────────────────────────────────────────
def test_dm10_agentcard_endpoint(relay_url):
    """DM-10: AgentCard endpoints.message_send points to /message/send.

    /.well-known/acp.json response has structure: {"self": <card>, "peer": ...}
    """
    r = requests.get(f"{relay_url}/.well-known/acp.json")
    assert r.status_code == 200
    data = r.json()
    # Unwrap {"self": card, "peer": ...} envelope
    card = data.get("self", data)
    endpoints = card.get("endpoints", {})
    assert endpoints.get("message_send") == "/message/send", \
        f"AgentCard endpoints.message_send incorrect; got: {endpoints.get('message_send')}"


# ─────────────────────────────────────────────────────────────────────────────
# DM-11: Concurrent 50 Direct Messages — all 200, no state pollution
# ─────────────────────────────────────────────────────────────────────────────
def test_dm11_concurrent_direct_messages(relay_url):
    """DM-11: 50 concurrent Direct Messages all return 200 with unique message_ids."""
    import concurrent.futures

    def send_dm(i):
        r = requests.post(f"{relay_url}/message/send", json={
            "role": "user",
            "text": f"concurrent message {i}",
        }, timeout=10)
        return r.status_code, r.json().get("message_id")

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(send_dm, range(50)))

    statuses = [s for s, _ in results]
    msg_ids  = [m for _, m in results]

    assert all(s == 200 for s in statuses), \
        f"Some DMs failed: {[s for s in statuses if s != 200]}"
    assert len(set(msg_ids)) == 50, "Duplicate message_ids returned in concurrent requests"

    # No tasks should have been created
    tasks_r = requests.get(f"{relay_url}/tasks")
    assert tasks_r.status_code == 200
    tasks = tasks_r.json().get("tasks", [])
    dm_msg_set = set(msg_ids)
    task_ids = {t["id"] for t in tasks}
    overlap = dm_msg_set & task_ids
    assert not overlap, f"DM message_ids leaked into Tasks: {overlap}"


# ─────────────────────────────────────────────────────────────────────────────
# DM-12: Wrong Content-Type → 415
# ─────────────────────────────────────────────────────────────────────────────
def test_dm12_wrong_content_type_returns_415(relay_url):
    """DM-12: Content-Type: text/plain → 415 Unsupported Media Type."""
    r = requests.post(
        f"{relay_url}/message/send",
        data="role=user&text=hello",
        headers={"Content-Type": "text/plain"},
    )
    assert r.status_code in (400, 415), \
        f"Expected 415 (or 400), got {r.status_code}: {r.text}"


# ─────────────────────────────────────────────────────────────────────────────
# DM-13 (bonus): client-supplied message_id is preserved
# ─────────────────────────────────────────────────────────────────────────────
def test_dm13_client_message_id_preserved(relay_url):
    """DM-13: Client-supplied message_id is echoed back unchanged."""
    custom_id = "msg-client-custom-xyz-001"
    r = requests.post(f"{relay_url}/message/send", json={
        "role": "user",
        "text": "Use my message_id please.",
        "message_id": custom_id,
    })
    assert r.status_code == 200
    d = r.json()
    assert d["message_id"] == custom_id, \
        f"Expected message_id={custom_id}, got {d.get('message_id')}"


# ─────────────────────────────────────────────────────────────────────────────
# DM-14: MAX_MSG_BYTES boundary — 1MB+ rejected, 70KB accepted
# (BUG-053 investigation: MAX_MSG_BYTES=1MB, not 64KB)
# ─────────────────────────────────────────────────────────────────────────────
def test_dm14_size_limit(relay_url):
    """DM-14: Body > MAX_MSG_BYTES (1MB) returns 413; 70KB accepted (< 1MB)."""
    import json as _json

    # 70KB — well under 1MB limit, must succeed
    r_small = requests.post(f"{relay_url}/message/send",
                            json={"role": "user", "text": "x" * 70000})
    assert r_small.status_code == 200, f"70KB should be accepted, got {r_small.status_code}"

    # 1.1MB — over 1MB limit, must be rejected
    big_payload = _json.dumps({"role": "user", "text": "x" * 1_100_000})
    r_big = requests.post(f"{relay_url}/message/send",
                          data=big_payload.encode(),
                          headers={"Content-Type": "application/json"})
    assert r_big.status_code == 413, \
        f"1.1MB should return 413, got {r_big.status_code}"
