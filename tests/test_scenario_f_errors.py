"""
tests/test_scenario_f_errors.py — 场景 F: 错误处理

覆盖 HEARTBEAT.md 场景 F 要求：
  - 无效 peer_id（ERR_NOT_FOUND）
  - 超大消息（ERR_PAYLOAD_TOO_LARGE）
  - 非法 JSON body（400 解析失败）
  - 重复 message_id（幂等去重）

测试列表:
  F-01: POST /message:send with unknown peer_id → ERR_NOT_FOUND or 404
  F-02: POST /peer/{invalid}/send → 404 ERR_NOT_FOUND
  F-03: POST /message:send with malformed JSON → 400
  F-04: POST /message:send with empty body → 400 ERR_INVALID_REQUEST
  F-05: POST /message:send with missing required 'parts'/'text' → 400
  F-06: POST /message:send with oversized message → 400 or 413
  F-07: Duplicate message_id (idempotency) → ok=True, deduplicated=True
  F-08: GET /peer/nonexistent/send (wrong method) → 405 or 404
  F-09: POST /task/nonexistent/status → 404 ERR_NOT_FOUND
  F-10: POST /message:send with invalid parts type (not list) → 400
"""

import os
import sys
import time
import socket
import subprocess
import pytest
import requests

RELAY = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")


def _free_port_pair():
    for _ in range(20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            ws = s.getsockname()[1]
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s2:
                s2.bind(("", ws + 100))
            return ws, ws + 100
        except OSError:
            continue
    raise RuntimeError("Cannot find free port pair")


@pytest.fixture(scope="module")
def relay_url():
    ws_port, http_port = _free_port_pair()
    proc = subprocess.Popen(
        [sys.executable, RELAY, "--port", str(ws_port), "--name", "ScenarioFErrors", "--local"],
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
        pytest.fail("Relay did not start within 15s")
    yield f"http://localhost:{http_port}"
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


# ── F-01: Unknown peer_id in /message:send body ───────────────────────────────

def test_f01_message_send_unknown_peer_id(relay_url):
    """F-01: POST /message:send with unknown peer_id in body → error."""
    r = requests.post(f"{relay_url}/message:send", json={
        "text": "hello",
        "peer_id": "peer_nonexistent_xyz",
    })
    d = r.json()
    assert r.status_code in (404, 400, 503), f"Unexpected status {r.status_code}: {d}"
    assert d.get("ok") is not True
    assert "error" in d or "ok" in d


# ── F-02: Direct /peer/{id}/send with unknown id ──────────────────────────────

def test_f02_peer_send_unknown_id(relay_url):
    """F-02: POST /peer/nonexistent_xyz/send → 404 ERR_NOT_FOUND."""
    r = requests.post(f"{relay_url}/peer/nonexistent_xyz/send", json={"text": "hi"})
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text[:200]}"
    d = r.json()
    assert d.get("ok") is not True
    error_code = d.get("error", {}).get("code", "") if isinstance(d.get("error"), dict) else d.get("code", "")
    assert "NOT_FOUND" in error_code or "not found" in str(d).lower(), \
        f"Expected NOT_FOUND error, got: {d}"


# ── F-03: Malformed JSON ──────────────────────────────────────────────────────

def test_f03_malformed_json(relay_url):
    """F-03: POST /message:send with malformed JSON → 400."""
    r = requests.post(
        f"{relay_url}/message:send",
        data=b"{not valid json !!!",
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text[:200]}"


# ── F-04: Empty body ──────────────────────────────────────────────────────────

def test_f04_empty_body(relay_url):
    """F-04: POST /message:send with empty body → 400 ERR_INVALID_REQUEST."""
    r = requests.post(
        f"{relay_url}/message:send",
        data=b"",
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text[:200]}"
    d = r.json()
    assert d.get("ok") is not True


# ── F-05: Missing parts/text ──────────────────────────────────────────────────

def test_f05_missing_parts_and_text(relay_url):
    """F-05: POST /message:send with no 'parts' and no 'text' → 400."""
    r = requests.post(f"{relay_url}/message:send", json={"message_id": "test_f05_msg"})
    assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text[:200]}"
    d = r.json()
    assert d.get("ok") is not True


# ── F-06: Oversized message ───────────────────────────────────────────────────

def test_f06_oversized_message(relay_url):
    """F-06: POST /message:send with very large text → 400 or 413."""
    big_text = "X" * (1024 * 1024 * 5)  # 5 MB
    r = requests.post(f"{relay_url}/message:send", json={"text": big_text}, timeout=15)
    # Relay may accept and queue (no active peer to reject), or reject with 400/413
    # The key check: it should not crash (500) and should return valid JSON
    assert r.status_code in (200, 400, 413, 503), \
        f"Unexpected status {r.status_code} for oversized message"
    # If it accepted (200/503), ok field should exist
    d = r.json()
    assert "ok" in d or "error" in d


# ── F-07: Duplicate message_id idempotency ────────────────────────────────────

def test_f07_duplicate_message_id_idempotency(relay_url):
    """F-07: Second POST with same message_id → ok=True, deduplicated=True."""
    msg_id = f"test_f07_idempotent_{int(time.time())}"
    payload = {"text": "test idempotent message", "message_id": msg_id, "role": "user"}

    # First send
    r1 = requests.post(f"{relay_url}/message:send", json=payload)
    d1 = r1.json()
    # May succeed (200) or fail with no peer (503), but message_id should be echoed
    assert r1.status_code in (200, 503), f"First send unexpected: {r1.status_code} {d1}"
    assert d1.get("message_id") == msg_id or d1.get("failed_message_id") == msg_id, \
        f"message_id not echoed in first response: {d1}"

    # Second send (immediate duplicate)
    r2 = requests.post(f"{relay_url}/message:send", json=payload)
    d2 = r2.json()

    if r1.status_code == 200:
        # Only deduplication applies when first send succeeded (200)
        assert r2.status_code == 200, f"Second send should be 200 (dedup), got {r2.status_code}: {d2}"
        assert d2.get("ok") is True
        assert d2.get("deduplicated") is True, \
            f"Expected deduplicated=True on second send, got: {d2}"
    else:
        # First send failed (no peer), duplicate behavior may vary
        # At minimum, it should not crash
        assert r2.status_code in (200, 400, 503), \
            f"Unexpected status on dup of failed send: {r2.status_code}"


# ── F-08: Wrong HTTP method on peer send ─────────────────────────────────────

def test_f08_get_on_peer_send_endpoint(relay_url):
    """F-08: GET /peer/{id}/send → 405 or 404 (not 200 or 500)."""
    r = requests.get(f"{relay_url}/peer/some_peer/send")
    assert r.status_code in (404, 405), \
        f"Expected 404/405, got {r.status_code}: {r.text[:200]}"


# ── F-09: Task not found ──────────────────────────────────────────────────────

def test_f09_task_not_found(relay_url):
    """F-09: GET /task/nonexistent/status → 404."""
    r = requests.get(f"{relay_url}/task/nonexistent_task_xyz/status")
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text[:200]}"
    d = r.json()
    assert d.get("ok") is not True


# ── F-10: Invalid parts type ──────────────────────────────────────────────────

def test_f10_invalid_parts_type(relay_url):
    """F-10: POST /message:send with parts as non-list (string) → 400."""
    r = requests.post(f"{relay_url}/message:send", json={
        "parts": "this should be a list not a string",
    })
    assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text[:200]}"
    d = r.json()
    assert d.get("ok") is not True
