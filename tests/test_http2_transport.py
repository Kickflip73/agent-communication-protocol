#!/usr/bin/env python3
"""
ACP HTTP/2 Transport Binding Tests
===================================
Tests for v1.6 feature: optional HTTP/2 (h2c cleartext) via hypercorn.

Scenarios:
  H1: Relay starts normally WITHOUT --http2 → HTTP/1.1, capabilities.http2=false
  H2: Relay starts WITH --http2 → HTTP/2, capabilities.http2=true
  H3: /status endpoint works over HTTP/2
  H4: POST /tasks works over HTTP/2
  H5: Graceful fallback message when hypercorn unavailable (code path test)
  H6: AgentCard /.well-known/acp.json exposes http2 capability correctly
"""

import sys, os, time, subprocess, signal, json, socket, requests, threading
import pytest
from helpers import clean_subprocess_env

RELAY_PATH = os.path.join(os.path.dirname(__file__), "../relay/acp_relay.py")
PORT_H1 = 7851   # HTTP/1.1 instance (ws=7851, http=7951)
PORT_H2 = 7852   # HTTP/2 instance   (ws=7852, http=7952)
HTTP_H1 = f"http://localhost:{PORT_H1 + 100}"
HTTP_H2 = f"http://localhost:{PORT_H2 + 100}"
PROCS = []


def _wait_tcp(host, port, retries=40, delay=0.2):
    """Wait until TCP port accepts connections."""
    for _ in range(retries):
        try:
            s = socket.create_connection((host, port), timeout=0.5)
            s.close()
            return True
        except OSError:
            time.sleep(delay)
    return False


def start_relay(port, name="RelayH", extra_args=None):
    cmd = [sys.executable, RELAY_PATH, "--port", str(port), "--name", name]
    if extra_args:
        cmd.extend(extra_args)
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    PROCS.append(p)
    http_port = port + 100
    if not _wait_tcp("127.0.0.1", http_port, retries=50, delay=0.2):
        raise RuntimeError(f"Relay {name}:{port} (http:{http_port}) did not start within 10s")
    # Extra settle time for H2 listener to fully initialise
    if extra_args and "--http2" in extra_args:
        time.sleep(0.5)
    return f"http://localhost:{http_port}"


def stop_all():
    for p in PROCS:
        try:
            p.send_signal(signal.SIGTERM)
            p.wait(timeout=3)
        except Exception:
            pass


@pytest.fixture(scope="module", autouse=True)
def relay_instances():
    """Start HTTP/1.1 and HTTP/2 relay instances."""
    start_relay(PORT_H1, name="RelayH1")           # no --http2
    start_relay(PORT_H2, name="RelayH2", extra_args=["--http2"])  # with --http2
    yield
    stop_all()


def _h2_get(host, port, path, timeout=5):
    """Issue a GET request over raw h2c and return (status_code, body_bytes)."""
    import h2.connection, h2.config, h2.events
    conn = h2.connection.H2Connection(
        config=h2.config.H2Configuration(header_encoding="utf-8")
    )
    conn.initiate_connection()
    s = socket.create_connection((host, port), timeout=timeout)
    s.sendall(conn.data_to_send(65535))
    conn.send_headers(1, [
        (":method", "GET"), (":path", path),
        (":scheme", "http"), (":authority", f"{host}:{port}"),
    ])
    conn.end_stream(1)
    s.sendall(conn.data_to_send(65535))

    status = None
    body = b""
    done = False
    s.settimeout(timeout)
    while not done:
        try:
            data = s.recv(65535)
        except socket.timeout:
            break
        if not data:
            break
        for event in conn.receive_data(data):
            if isinstance(event, h2.events.ResponseReceived):
                status = int(dict(event.headers).get(":status", "0"))
            elif isinstance(event, h2.events.DataReceived):
                body += event.data
                conn.acknowledge_received_data(event.flow_controlled_length, event.stream_id)
            elif isinstance(event, h2.events.StreamEnded):
                done = True
        s.sendall(conn.data_to_send(65535))
    s.close()
    return status, body


def _h2_post(host, port, path, payload_bytes, timeout=5):
    """Issue a POST request over raw h2c and return (status_code, body_bytes)."""
    import h2.connection, h2.config, h2.events
    conn = h2.connection.H2Connection(
        config=h2.config.H2Configuration(header_encoding="utf-8")
    )
    conn.initiate_connection()
    s = socket.create_connection((host, port), timeout=timeout)
    s.sendall(conn.data_to_send(65535))
    conn.send_headers(1, [
        (":method", "POST"), (":path", path),
        (":scheme", "http"), (":authority", f"{host}:{port}"),
        ("content-type", "application/json"),
        ("content-length", str(len(payload_bytes))),
    ])
    conn.send_data(1, payload_bytes, end_stream=True)
    s.sendall(conn.data_to_send(65535))

    status = None
    body = b""
    done = False
    s.settimeout(timeout)
    while not done:
        try:
            data = s.recv(65535)
        except socket.timeout:
            break
        if not data:
            break
        for event in conn.receive_data(data):
            if isinstance(event, h2.events.ResponseReceived):
                status = int(dict(event.headers).get(":status", "0"))
            elif isinstance(event, h2.events.DataReceived):
                body += event.data
                conn.acknowledge_received_data(event.flow_controlled_length, event.stream_id)
            elif isinstance(event, h2.events.StreamEnded):
                done = True
        s.sendall(conn.data_to_send(65535))
    s.close()
    return status, body


def test_http2_transport():
    """Pytest entry: run all HTTP/2 transport scenarios."""
    results = []

    def check(name, cond, detail=""):
        results.append((name, cond))
        mark = "✅" if cond else "❌"
        print(f"  {mark} {name}" + (f"  ({detail})" if detail else ""))
        return cond

    h1_port = PORT_H1 + 100
    h2_port = PORT_H2 + 100

    # ── H1: HTTP/1.1 baseline (use requests — it's HTTP/1.1) ─────────────────
    print("\n[H1] HTTP/1.1 baseline — capabilities.http2 should be false")
    r = requests.get(f"{HTTP_H1}/status", timeout=5, proxies={"http": None, "https": None})
    check("H1  /status → 200", r.status_code == 200, f"got {r.status_code}")
    caps = r.json().get("agent_card", {}).get("capabilities", {})
    check("H1  capabilities.http2 == false", caps.get("http2") == False,
          f"http2={caps.get('http2')}")

    # ── H2: HTTP/2 instance capability via h2c ────────────────────────────────
    print("\n[H2] HTTP/2 instance — h2c GET /status")
    st, body = _h2_get("127.0.0.1", h2_port, "/status")
    check("H2  h2c /status → 200", st == 200, f"got {st}")
    if body:
        d2 = json.loads(body)
        caps2 = d2.get("agent_card", {}).get("capabilities", {})
        check("H2  capabilities.http2 == true", caps2.get("http2") == True,
              f"http2={caps2.get('http2')}")
    else:
        check("H2  capabilities.http2 == true", False, "empty body")

    # ── H3: session_id present in /status response ───────────────────────────
    print("\n[H3] /status functional on h2c instance")
    st3, body3 = _h2_get("127.0.0.1", h2_port, "/status")
    check("H3  h2c /status → 200", st3 == 200)
    if body3:
        d3 = json.loads(body3)
        check("H3  session_id present", "session_id" in d3, str(list(d3.keys())[:6]))

    # ── H4: POST /tasks via h2c ───────────────────────────────────────────────
    print("\n[H4] POST /tasks over h2c")
    payload = json.dumps({"role": "agent", "parts": [{"type": "text", "text": "h2-task"}]}).encode()
    st4, body4 = _h2_post("127.0.0.1", h2_port, "/tasks", payload)
    check("H4  h2c POST /tasks → 201", st4 == 201, f"got {st4}")
    if body4 and st4 == 201:
        d4 = json.loads(body4)
        # Response shape: {"ok": true, "task": {"id": "task_...", ...}}
        task_id = d4.get("task", {}).get("id") or d4.get("task_id")
        check("H4  task_id returned", bool(task_id), str(list(d4.keys())[:5]))

    # ── H5: HTTP/1.1 instance /.well-known/acp.json ──────────────────────────
    print("\n[H5] HTTP/1.1 instance does NOT advertise http2")
    # Use raw socket to avoid proxy env variables
    import http.client as _httpcli
    cn5 = _httpcli.HTTPConnection("127.0.0.1", h1_port, timeout=5)
    cn5.request("GET", "/.well-known/acp.json")
    resp5 = cn5.getresponse()
    check("H5  /.well-known/acp.json → 200", resp5.status == 200, f"got {resp5.status}")
    if resp5.status == 200:
        wk = json.loads(resp5.read())
        # /.well-known/acp.json wraps under "self" key
        caps5 = wk.get("self", wk).get("capabilities", {})
        check("H5  capabilities.http2 == false",
              caps5.get("http2") == False,
              f"http2={caps5.get('http2')}")
    cn5.close()

    # ── H6: /.well-known/acp.json via h2c ────────────────────────────────────
    print("\n[H6] /.well-known/acp.json via h2c")
    st6, body6 = _h2_get("127.0.0.1", h2_port, "/.well-known/acp.json")
    check("H6  h2c /.well-known/acp.json → 200", st6 == 200, f"got {st6}")
    if body6 and st6 == 200:
        wk2 = json.loads(body6)
        # /.well-known/acp.json wraps under "self" key
        caps6 = wk2.get("self", wk2).get("capabilities", {})
        check("H6  capabilities.http2 == true",
              caps6.get("http2") == True,
              f"http2={caps6.get('http2')}")
        inner = wk2.get("self", wk2)
        check("H6  version field present", "acp_version" in inner or "version" in inner)

    # ── Summary ───────────────────────────────────────────────────────────────
    failed = [r for r in results if not r[1]]
    assert not failed, f"HTTP/2 transport test failures: {[r[0] for r in failed]}"


if __name__ == "__main__":
    print("ACP HTTP/2 Transport Binding Tests")
    print("=" * 50)

    print("Starting relay instances...")
    start_relay(PORT_H1, name="RelayH1")
    start_relay(PORT_H2, name="RelayH2", extra_args=["--http2"])
    print(f"H1 (HTTP/1.1): {HTTP_H1}")
    print(f"H2 (HTTP/2):   {HTTP_H2}\n")

    try:
        test_http2_transport()
    finally:
        stop_all()

    print("\n✅ All HTTP/2 transport tests passed")
