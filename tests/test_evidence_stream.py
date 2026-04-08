"""
tests/test_evidence_stream.py — ACP v2.82 evidence_stream SSE tests
ES1–ES12 (12 test cases)
"""

import json
import queue
import socket
import subprocess
import threading
import time

import pytest
import requests


# ──────────────────────────────────────────────────────────────────────────────
# Fixture: start relay server on a free port pair (module scope)
# ──────────────────────────────────────────────────────────────────────────────

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def relay():
    """Start an ACP relay subprocess; yield base URL; teardown.

    ACP relay: --port <ws_port>, HTTP API = ws_port + 100.
    Find a ws_port where ws_port + 100 is also free.
    """
    for _ in range(20):
        ws_port = _free_port()
        http_port = ws_port + 100
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", http_port))
                break
            except OSError:
                continue
    else:
        pytest.fail("Could not find two consecutive-100 free ports")

    proc = subprocess.Popen(
        [
            "python3", "relay/acp_relay.py",
            "--port", str(ws_port),
            "--name", "ESTest",
            "--test-mode",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    base = f"http://127.0.0.1:{http_port}"

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


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def post_evidence(base_url: str, task_id: str, event_type: str = "updated", **extra) -> dict:
    payload = {"event_type": event_type, **extra}
    r = requests.post(
        f"{base_url}/tasks/{task_id}/evidence",
        json=payload,
        timeout=5,
    )
    assert r.status_code == 200, f"POST evidence failed ({r.status_code}): {r.text}"
    return r.json()


def collect_sse_events(base_url: str, task_id: str,
                       n: int, timeout: float = 8.0) -> list:
    """
    Open SSE connection, collect n data-bearing events, return parsed dicts.
    Runs the reader in a daemon thread so caller isn't blocked.
    Uses chunk_size=1 to ensure per-byte streaming (required for BaseHTTP SSE).
    """
    result_q: queue.Queue = queue.Queue()
    stop_event = threading.Event()

    def _reader():
        try:
            with requests.get(
                f"{base_url}/tasks/{task_id}/evidence-stream",
                stream=True,
                timeout=timeout + 2,
            ) as resp:
                for raw in resp.iter_lines(chunk_size=1, decode_unicode=True):
                    if stop_event.is_set():
                        break
                    if raw and raw.startswith("data:"):
                        data_str = raw[len("data:"):].strip()
                        try:
                            result_q.put(json.loads(data_str))
                        except Exception:
                            pass
                    if result_q.qsize() >= n:
                        break
        except Exception:
            pass

    t = threading.Thread(target=_reader, daemon=True)
    t.start()

    items = []
    deadline = time.time() + timeout
    while len(items) < n and time.time() < deadline:
        try:
            items.append(result_q.get(timeout=0.1))
        except queue.Empty:
            pass

    stop_event.set()
    return items


# ──────────────────────────────────────────────────────────────────────────────
# Tests  ES1–ES12
# ──────────────────────────────────────────────────────────────────────────────

def test_es1_content_type(relay):
    """ES1: GET /tasks/t1/evidence-stream responds with text/event-stream."""
    task_id = f"es1-{time.time_ns()}"
    r = requests.get(
        f"{relay}/tasks/{task_id}/evidence-stream",
        stream=True,
        timeout=5,
    )
    assert r.status_code == 200
    assert "text/event-stream" in r.headers.get("Content-Type", "")
    r.close()


def test_es2_keepalive_on_empty_task(relay):
    """ES2: Empty task SSE returns ': keepalive' comment within timeout."""
    task_id = f"es2-empty-{time.time_ns()}"
    keepalive_seen = threading.Event()

    def _reader():
        try:
            with requests.get(
                f"{relay}/tasks/{task_id}/evidence-stream",
                stream=True,
                timeout=12,
            ) as resp:
                for raw in resp.iter_lines(chunk_size=1, decode_unicode=True):
                    if raw == ": keepalive":
                        keepalive_seen.set()
                        break
        except Exception:
            pass

    t = threading.Thread(target=_reader, daemon=True)
    t.start()
    # keepalive interval is 5s — allow up to 10s
    assert keepalive_seen.wait(timeout=10), "Expected ': keepalive' within 10s"


def test_es3_replay_existing_evidence(relay):
    """ES3: Task with existing evidence — connect SSE → replay immediately."""
    task_id = f"es3-replay-{time.time_ns()}"
    post_evidence(relay, task_id, "requested")
    post_evidence(relay, task_id, "updated")
    post_evidence(relay, task_id, "completed")

    evts = collect_sse_events(relay, task_id, n=2, timeout=6)
    assert len(evts) >= 2, f"Expected ≥2 replayed events, got {len(evts)}"


def test_es4_live_push(relay):
    """ES4: POST evidence while SSE connected → subscriber receives it live."""
    task_id = f"es4-live-{time.time_ns()}"
    result_q: queue.Queue = queue.Queue()
    stop_event = threading.Event()

    def _reader():
        try:
            with requests.get(
                f"{relay}/tasks/{task_id}/evidence-stream",
                stream=True,
                timeout=12,
            ) as resp:
                for raw in resp.iter_lines(chunk_size=1, decode_unicode=True):
                    if stop_event.is_set():
                        break
                    if raw and raw.startswith("data:"):
                        try:
                            result_q.put(json.loads(raw[len("data:"):].strip()))
                        except Exception:
                            pass
                    if result_q.qsize() >= 1:
                        break
        except Exception:
            pass

    t = threading.Thread(target=_reader, daemon=True)
    t.start()
    time.sleep(0.4)  # let connection establish

    post_evidence(relay, task_id, "updated")

    received = None
    try:
        received = result_q.get(timeout=6)
    except queue.Empty:
        pass
    stop_event.set()

    assert received is not None, "SSE subscriber did not receive live event"
    assert received.get("task_id") == task_id


def test_es5_multi_subscriber(relay):
    """ES5: Multiple subscribers on the same task all receive one POST."""
    task_id = f"es5-multi-{time.time_ns()}"
    q1: queue.Queue = queue.Queue()
    q2: queue.Queue = queue.Queue()
    stop = threading.Event()

    def _reader(out_q):
        try:
            with requests.get(
                f"{relay}/tasks/{task_id}/evidence-stream",
                stream=True,
                timeout=12,
            ) as resp:
                for raw in resp.iter_lines(chunk_size=1, decode_unicode=True):
                    if stop.is_set():
                        break
                    if raw and raw.startswith("data:"):
                        try:
                            out_q.put(json.loads(raw[len("data:"):].strip()))
                        except Exception:
                            pass
                    if out_q.qsize() >= 1:
                        break
        except Exception:
            pass

    t1 = threading.Thread(target=_reader, args=(q1,), daemon=True)
    t2 = threading.Thread(target=_reader, args=(q2,), daemon=True)
    t1.start()
    t2.start()
    time.sleep(0.5)

    post_evidence(relay, task_id, "updated")

    r1, r2 = None, None
    try:
        r1 = q1.get(timeout=6)
    except queue.Empty:
        pass
    try:
        r2 = q2.get(timeout=6)
    except queue.Empty:
        pass
    stop.set()

    assert r1 is not None, "Subscriber 1 did not receive event"
    assert r2 is not None, "Subscriber 2 did not receive event"


def test_es6_task_isolation(relay):
    """ES6: t1 evidence not delivered to t2 SSE subscriber."""
    task_id_1 = f"es6-t1-{time.time_ns()}"
    task_id_2 = f"es6-t2-{time.time_ns()}"
    t2_received: queue.Queue = queue.Queue()
    stop = threading.Event()

    def _reader():
        try:
            with requests.get(
                f"{relay}/tasks/{task_id_2}/evidence-stream",
                stream=True,
                timeout=8,
            ) as resp:
                for raw in resp.iter_lines(chunk_size=1, decode_unicode=True):
                    if stop.is_set():
                        break
                    if raw and raw.startswith("data:"):
                        try:
                            t2_received.put(json.loads(raw[len("data:"):].strip()))
                        except Exception:
                            pass
        except Exception:
            pass

    t = threading.Thread(target=_reader, daemon=True)
    t.start()
    time.sleep(0.3)

    post_evidence(relay, task_id_1, "updated")

    time.sleep(1.2)  # wait for any erroneous delivery
    stop.set()

    assert t2_received.empty(), (
        f"t2 subscriber received unexpected event from t1: "
        f"{t2_received.get_nowait() if not t2_received.empty() else 'N/A'}"
    )


def test_es7_sse_event_format(relay):
    """ES7: SSE event contains 'event: evidence' line and 'data:' line."""
    task_id = f"es7-fmt-{time.time_ns()}"
    post_evidence(relay, task_id, "requested")

    event_lines = []
    data_lines = []
    stop = threading.Event()

    def _reader():
        try:
            with requests.get(
                f"{relay}/tasks/{task_id}/evidence-stream",
                stream=True,
                timeout=6,
            ) as resp:
                for raw in resp.iter_lines(chunk_size=1, decode_unicode=True):
                    if stop.is_set():
                        break
                    if raw == "event: evidence":
                        event_lines.append(raw)
                    if raw and raw.startswith("data:"):
                        data_lines.append(raw)
                    if event_lines and data_lines:
                        stop.set()
                        break
        except Exception:
            pass

    t = threading.Thread(target=_reader, daemon=True)
    t.start()
    t.join(timeout=7)
    stop.set()

    assert event_lines, "Missing 'event: evidence' line in SSE output"
    assert data_lines, "Missing 'data:' line in SSE output"


def test_es8_replay_seq_order(relay):
    """ES8: Replayed events start at seq=0 and are in order."""
    task_id = f"es8-seq-{time.time_ns()}"
    for et in ["requested", "updated", "completed"]:
        post_evidence(relay, task_id, et)

    evts = collect_sse_events(relay, task_id, n=3, timeout=6)
    assert len(evts) >= 1, "No replayed events received"

    seqs = [e.get("seq") for e in evts]
    assert seqs[0] == 0, f"First seq should be 0, got {seqs[0]}"
    for i in range(1, len(seqs)):
        assert seqs[i] == seqs[i - 1] + 1, (
            f"Seq not sequential at index {i}: {seqs}"
        )


def test_es9_reconnect_replay(relay):
    """ES9: After disconnect, reconnect receives full replay from seq=0."""
    task_id = f"es9-reconnect-{time.time_ns()}"
    post_evidence(relay, task_id, "requested")
    post_evidence(relay, task_id, "updated")

    # First connection
    evts1 = collect_sse_events(relay, task_id, n=2, timeout=6)
    assert len(evts1) >= 2, f"First connection: expected 2 events, got {len(evts1)}"

    # Second connection (reconnect)
    evts2 = collect_sse_events(relay, task_id, n=2, timeout=6)
    assert len(evts2) >= 2, f"Reconnect: expected 2 events, got {len(evts2)}"
    assert evts2[0].get("seq") == 0, "Reconnect replay should start from seq=0"


def test_es10_capabilities_evidence_stream(relay):
    """ES10: /status capabilities includes evidence_stream=True."""
    r = requests.get(f"{relay}/status", timeout=5)
    assert r.status_code == 200
    body = r.json()
    # capabilities live under agent_card in /status response
    caps = body.get("agent_card", {}).get("capabilities", {})
    assert caps.get("evidence_stream") is True, (
        f"capabilities.evidence_stream not True; full caps: {caps}"
    )


def test_es11_agent_card_evidence_stream(relay):
    """ES11: /.well-known/acp.json capabilities includes evidence_stream=True."""
    r = requests.get(f"{relay}/.well-known/acp.json", timeout=5)
    assert r.status_code == 200
    body = r.json()
    # capabilities live under self in /.well-known/acp.json response
    caps = body.get("self", {}).get("capabilities", {})
    assert caps.get("evidence_stream") is True, (
        f"AgentCard capabilities.evidence_stream not True; full caps: {caps}"
    )


def test_es12_high_frequency_write(relay):
    """ES12: 5 rapid POSTs → SSE subscriber receives all 5 (5/5)."""
    task_id = f"es12-hf-{time.time_ns()}"
    received: queue.Queue = queue.Queue()
    stop = threading.Event()

    def _reader():
        try:
            with requests.get(
                f"{relay}/tasks/{task_id}/evidence-stream",
                stream=True,
                timeout=15,
            ) as resp:
                for raw in resp.iter_lines(chunk_size=1, decode_unicode=True):
                    if stop.is_set():
                        break
                    if raw and raw.startswith("data:"):
                        try:
                            received.put(json.loads(raw[len("data:"):].strip()))
                        except Exception:
                            pass
                    if received.qsize() >= 5:
                        break
        except Exception:
            pass

    t = threading.Thread(target=_reader, daemon=True)
    t.start()
    time.sleep(0.4)

    for _ in range(5):
        post_evidence(relay, task_id, "updated")

    items = []
    deadline = time.time() + 10
    while len(items) < 5 and time.time() < deadline:
        try:
            items.append(received.get(timeout=0.2))
        except queue.Empty:
            pass
    stop.set()

    assert len(items) == 5, f"Expected 5 events, got {len(items)}"
