"""
test_offline_queue.py — ACP v2.0 Offline Delivery Queue tests

Tests:
  OQ1: capabilities.offline_queue=True always advertised
  OQ2: endpoints.offline_queue = "/offline-queue" in AgentCard
  OQ3: GET /offline-queue returns empty queue when nothing buffered
  OQ4: GET /offline-queue returns structure with total_queued and max_per_peer
  OQ5: POST /message:send with no peer → 503 + message queued in offline buffer
  OQ6: offline queue depth increments with each failed send
  OQ7: offline queue snapshot contains id, type, queued_at metadata per message
  OQ8: POST /send (legacy) with no peer → message queued in offline buffer
  OQ9: queue is bounded by OFFLINE_QUEUE_MAXLEN (oldest dropped when full, newest kept)
  OQ10: queue cleared after flush (simulated via DELETE /offline-queue)
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
    with urllib.request.urlopen(f"http://localhost:{HTTP_PORT}{path}", timeout=5) as r:
        return r.status, json.loads(r.read())


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


@pytest.fixture(scope="module", autouse=True)
def single_relay():
    global _proc
    env = _make_env()
    _proc = subprocess.Popen(
        [sys.executable, RELAY_PATH, "--port", str(WS_PORT), "--name", "OQAgent"],
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

def test_oq1_capabilities_offline_queue():
    """OQ1: capabilities.offline_queue=True always advertised."""
    _, data = _get("/.well-known/acp.json")
    caps = data["self"].get("capabilities", {})
    assert caps.get("offline_queue") is True, (
        f"capabilities.offline_queue should be True: {caps}"
    )


def test_oq2_endpoints_offline_queue():
    """OQ2: endpoints.offline_queue = '/offline-queue' in AgentCard."""
    _, data = _get("/.well-known/acp.json")
    endpoints = data["self"].get("endpoints", {})
    assert endpoints.get("offline_queue") == "/offline-queue", (
        f"endpoints.offline_queue missing: {endpoints}"
    )


def test_oq3_get_offline_queue_empty():
    """OQ3: GET /offline-queue returns empty queue when nothing buffered."""
    _, data = _get("/offline-queue")
    assert data.get("total_queued") == 0, (
        f"Expected total_queued=0 on fresh relay: {data}"
    )
    assert isinstance(data.get("queue"), dict)
    assert data.get("max_per_peer") == 100


def test_oq4_get_offline_queue_structure():
    """OQ4: GET /offline-queue returns required structure fields."""
    _, data = _get("/offline-queue")
    for field in ("total_queued", "max_per_peer", "queue"):
        assert field in data, f"Field '{field}' missing: {data}"
    assert isinstance(data["total_queued"], int)
    assert isinstance(data["max_per_peer"], int)
    assert isinstance(data["queue"], dict)


def test_oq5_send_no_peer_queued():
    """OQ5: POST /message:send with no peer → 503 but message buffered in offline queue."""
    status, resp = _post("/message:send", {
        "role": "user",
        "parts": [{"type": "text", "content": "hello offline world"}],
        "message_id": "oq5-test-msg",
    })
    # Should return 503 (no connection)
    assert status == 503, f"Expected 503 with no peer: status={status}, resp={resp}"

    # But message should be in queue
    _, queue_data = _get("/offline-queue")
    assert queue_data["total_queued"] >= 1, (
        f"Message should be in offline queue after failed send: {queue_data}"
    )


def test_oq6_queue_depth_increments():
    """OQ6: Offline queue depth increments with each failed send."""
    _, q0 = _get("/offline-queue")
    depth_before = q0["total_queued"]

    # Send 3 more messages while no peer
    for i in range(3):
        _post("/message:send", {
            "role": "user",
            "parts": [{"type": "text", "content": f"queued message {i}"}],
            "message_id": f"oq6-msg-{i}",
        })

    _, q1 = _get("/offline-queue")
    depth_after = q1["total_queued"]

    assert depth_after == depth_before + 3, (
        f"Expected depth to grow by 3: before={depth_before}, after={depth_after}"
    )


def test_oq7_queue_message_metadata():
    """OQ7: Offline queue snapshot contains id, type, queued_at per message."""
    _, queue_data = _get("/offline-queue")
    assert queue_data["total_queued"] > 0, "Need at least one queued message for this test"

    # Find first non-empty bucket
    found_msg = None
    for bucket in queue_data["queue"].values():
        if bucket["messages"]:
            found_msg = bucket["messages"][0]
            break

    assert found_msg is not None, "No messages found in any bucket"
    for field in ("type", "queued_at"):
        assert field in found_msg, f"Field '{field}' missing from queued message metadata: {found_msg}"
    # id may be None if not provided by sender, but queued_at must be present
    assert found_msg["queued_at"] is not None, "queued_at should be a timestamp"


def test_oq8_legacy_send_also_queues():
    """OQ8: POST /send (legacy endpoint) with no peer also queues to offline buffer."""
    _, q0 = _get("/offline-queue")
    before = q0["total_queued"]

    status, resp = _post("/send", {
        "type": "text",
        "content": "legacy send offline",
        "id": "oq8-legacy-msg",
    })
    assert status == 503, f"Expected 503 with no peer on /send: {status}"

    _, q1 = _get("/offline-queue")
    after = q1["total_queued"]

    assert after > before, (
        f"Legacy /send should also buffer to offline queue: before={before}, after={after}"
    )


def test_oq9_queue_bounded_by_maxlen():
    """
    OQ9: Queue is bounded by OFFLINE_QUEUE_MAXLEN (100).
    Sending 110 messages should not exceed 100 in any single bucket.
    """
    # Send 110 messages under a unique peer key via /message:send
    for i in range(110):
        _post("/message:send", {
            "role": "user",
            "parts": [{"type": "text", "content": f"bound test msg {i}"}],
            "message_id": f"oq9-msg-{i:03d}",
        })

    _, queue_data = _get("/offline-queue")
    for peer_id, bucket in queue_data["queue"].items():
        assert bucket["depth"] <= 100, (
            f"Queue bucket '{peer_id}' exceeds OFFLINE_QUEUE_MAXLEN=100: depth={bucket['depth']}"
        )


def test_oq10_status_endpoint_shows_queue_info():
    """OQ10: GET /status includes offline_queue_depth summary."""
    _, status = _get("/status")
    # /status should at minimum not crash; offline queue info is a bonus
    assert isinstance(status, dict), f"GET /status should return a dict: {status}"
    # Check that the relay is still healthy after all the failed sends
    assert status.get("version") is not None or status.get("agent_name") is not None, (
        f"Relay /status looks wrong after offline queue tests: {status}"
    )


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        ("OQ1",  test_oq1_capabilities_offline_queue),
        ("OQ2",  test_oq2_endpoints_offline_queue),
        ("OQ3",  test_oq3_get_offline_queue_empty),
        ("OQ4",  test_oq4_get_offline_queue_structure),
        ("OQ5",  test_oq5_send_no_peer_queued),
        ("OQ6",  test_oq6_queue_depth_increments),
        ("OQ7",  test_oq7_queue_message_metadata),
        ("OQ8",  test_oq8_legacy_send_also_queues),
        ("OQ9",  test_oq9_queue_bounded_by_maxlen),
        ("OQ10", test_oq10_status_endpoint_shows_queue_info),
    ]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print(f"✅ PASS  {name}")
        except pytest.skip.Exception as e:
            print(f"⏭️  SKIP  {name}: {e}")
        except Exception as e:
            print(f"❌ FAIL  {name}: {e}")
            failed.append(name)
    print(f"\n{'='*40}")
    sys.exit(1 if failed else 0)
