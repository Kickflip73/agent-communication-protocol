#!/usr/bin/env python3
"""
ACP v2.13 — Event Replay (?since=<seq>) Tests
==============================================
Tests for GET /stream?since=<seq> and GET /ws/stream?since=<seq>
reconnect-without-data-loss feature.

Test cases:
  RP1: /stream?since=0 replays all stored events immediately
  RP2: /stream?since=<mid_seq> replays only events after that seq
  RP3: /stream without ?since works as before (no regression)
  RP4: /ws/stream?since=0 replays events over WebSocket immediately
  RP5: capabilities.event_replay is true in AgentCard
  RP6: /stream?since=<last_seq> replays nothing (correct no-op)

Architecture:
- Single relay in host mode (with proxy env for token registration)
- Events injected via /message:send
- Replay verified by checking received event seqs

Run:
    python3 -m pytest tests/test_event_replay.py -v --timeout=60
"""

import sys, os, re, time, json, socket, threading, subprocess, asyncio
import pytest
import requests
import websockets

RELAY_PATH = os.path.join(os.path.dirname(__file__), "../relay/acp_relay.py")

# ── Proxy env recovery (same pattern as test_ws_stream.py) ────────────────────

_PROXY_VARS = ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY",
               "no_proxy", "NO_PROXY")
_GATEWAY_PROXY_ENV: dict = {}
try:
    import pathlib
    for _pid_path in pathlib.Path("/proc").iterdir():
        if _pid_path.name.isdigit():
            _env_file = _pid_path / "environ"
            try:
                _data = _env_file.read_bytes().decode("utf-8", errors="replace")
                _pairs = {k: v for k, v in (
                    e.split("=", 1) for e in _data.split("\x00") if "=" in e
                )}
                if _pairs.get("http_proxy") or _pairs.get("HTTP_PROXY"):
                    _GATEWAY_PROXY_ENV = {k: _pairs[k] for k in _PROXY_VARS if k in _pairs}
                    break
            except Exception:
                continue
except Exception:
    pass


def _relay_env() -> dict:
    env = os.environ.copy()
    env.update(_GATEWAY_PROXY_ENV)
    return env


# ── Port allocation ────────────────────────────────────────────────────────────

def _free_port() -> int:
    for _ in range(300):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            ws = s.getsockname()[1]
        try:
            with socket.socket() as s2:
                s2.bind(("127.0.0.1", ws + 100))
                return ws
        except OSError:
            continue
    raise RuntimeError("No free port pair found")


# ── Module-scoped relay ────────────────────────────────────────────────────────

_ws_port:   int = 0
_http_port: int = 0
_relay_proc: subprocess.Popen | None = None


@pytest.fixture(scope="module", autouse=True)
def relay_server():
    global _ws_port, _http_port, _relay_proc

    _ws_port   = _free_port()
    _http_port = _ws_port + 100

    _relay_proc = subprocess.Popen(
        [sys.executable, RELAY_PATH, "--port", str(_ws_port), "--name", "ReplayHost"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=_relay_env(),
    )

    # Wait HTTP ready
    for _ in range(150):
        try:
            r = requests.get(f"http://127.0.0.1:{_http_port}/status", timeout=0.5)
            if r.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(0.1)

    yield

    if _relay_proc and _relay_proc.poll() is None:
        _relay_proc.terminate()
        try:
            _relay_proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            _relay_proc.kill()
            _relay_proc.wait(timeout=2)


def _base() -> str:
    return f"http://127.0.0.1:{_http_port}"


def _inject_messages(n: int, prefix: str = "replay-test") -> list[int]:
    """
    Inject n messages into the host relay via a guest relay.
    Returns list of seq numbers from the event_log endpoint.
    
    Uses host+guest pair: guest sends message → host dispatches → SSE broadcast
    → event_log populated.
    """
    # Snapshot current event_log seq before injection
    pre_seqs = _get_event_log_seqs()
    pre_max = max(pre_seqs) if pre_seqs else 0

    # Start a guest relay that joins the host
    guest_ws = _free_port()
    guest_http = guest_ws + 100

    # Need the host link first
    host_link = _wait_host_link(_http_port, timeout=20)
    if not host_link:
        return []

    gp = subprocess.Popen(
        [sys.executable, RELAY_PATH, "--port", str(guest_ws), "--name", f"InjectGuest-{prefix}",
         "--join", host_link],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=_relay_env(),
    )
    try:
        # Wait for guest to connect
        if not _wait_connected(guest_http, timeout=20):
            return []

        for i in range(n):
            try:
                requests.post(
                    f"http://127.0.0.1:{guest_http}/message:send",
                    json={"role": "user",
                          "parts": [{"type": "text", "content": f"{prefix}-{i}"}],
                          "message_id": f"{prefix}-{i}-{time.time():.6f}"},
                    timeout=5,
                )
            except Exception:
                pass
            time.sleep(0.05)

        time.sleep(0.4)
    finally:
        if gp.poll() is None:
            gp.terminate()
            try:
                gp.wait(timeout=5)
            except subprocess.TimeoutExpired:
                gp.kill()

    # Return newly added seqs
    post_seqs = _get_event_log_seqs()
    return [s for s in post_seqs if s > pre_max]


def _get_event_log_seqs() -> list[int]:
    """Get seq numbers from event_log via a quick since=0 SSE read with short timeout."""
    seqs = []
    try:
        with requests.get(f"{_base()}/stream?since=0", stream=True, timeout=3) as resp:
            for line in resp.iter_lines(chunk_size=1):
                if line and line.startswith(b"data:"):
                    try:
                        evt = json.loads(line[5:].strip())
                        s = evt.get("seq")
                        if s:
                            seqs.append(s)
                    except Exception:
                        pass
    except requests.exceptions.ReadTimeout:
        pass
    except Exception:
        pass
    return seqs


def _wait_host_link(http_port: int, timeout: float = 20) -> str | None:
    """Wait for host relay to publish its acp:// link via HTTP polling."""
    ws_port = http_port - 100
    deadline = time.time() + timeout
    while time.time() < deadline:
        for ep in ("/link", "/status"):
            try:
                d = requests.get(f"http://127.0.0.1:{http_port}{ep}", timeout=1).json()
                raw = d.get("link") or ""
                if raw:
                    return re.sub(r"acp://[^:]+:", "acp://127.0.0.1:", raw)
                tok = d.get("session_id")
                if tok and tok not in (None, "None"):
                    return f"acp://127.0.0.1:{ws_port}/{tok}"
            except Exception:
                pass
        time.sleep(0.2)
    return None


def _wait_connected(http_port: int, timeout: float = 20) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            d = requests.get(f"http://127.0.0.1:{http_port}/status", timeout=1).json()
            if d.get("connected") is True or d.get("peer_count", 0) >= 1:
                return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


# ══════════════════════════════════════════════════════════════════════════════
# RP1: /stream?since=0 replays all stored events
# ══════════════════════════════════════════════════════════════════════════════

def test_rp1_stream_since_zero_replays_all():
    """RP1: GET /stream?since=0 immediately returns all stored events."""
    # Inject 3 messages to populate event log
    seqs = _inject_messages(3, "rp1")
    assert len(seqs) >= 3, f"Expected ≥3 events captured, got {seqs}"

    # Now connect with since=0 — should receive all stored events immediately
    replayed: list[dict] = []
    with requests.get(f"{_base()}/stream?since=0", stream=True, timeout=5) as resp:
        assert resp.status_code == 200
        for line in resp.iter_lines(chunk_size=1):
            if line and line.startswith(b"data:"):
                try:
                    evt = json.loads(line[5:].strip())
                    if evt.get("type") == "message":
                        replayed.append(evt)
                        if len(replayed) >= 3:
                            break
                except Exception:
                    pass

    assert len(replayed) >= 3, f"Expected ≥3 replayed events, got {len(replayed)}"
    # seq should be monotonically increasing
    rep_seqs = [e["seq"] for e in replayed]
    assert rep_seqs == sorted(rep_seqs), f"Replayed events not ordered: {rep_seqs}"


# ══════════════════════════════════════════════════════════════════════════════
# RP2: /stream?since=<mid_seq> replays only events after that seq
# ══════════════════════════════════════════════════════════════════════════════

def test_rp2_stream_since_mid_seq():
    """RP2: since=<mid_seq> returns only events with seq > mid_seq."""
    seqs = _inject_messages(4, "rp2")
    assert len(seqs) >= 4, f"Expected ≥4, got {seqs}"

    mid = seqs[1]  # pick 2nd event's seq as cutoff

    # Background thread reads replay events; stop once we have enough or timeout
    replayed: list[dict] = []
    stop_ev = threading.Event()

    def _reader():
        try:
            with requests.get(f"{_base()}/stream?since={mid}", stream=True, timeout=10) as resp:
                for line in resp.iter_lines(chunk_size=1):
                    if stop_ev.is_set():
                        break
                    if line and line.startswith(b"data:"):
                        try:
                            evt = json.loads(line[5:].strip())
                            if evt.get("type") == "message":
                                replayed.append(evt)
                                if len(replayed) >= 3:
                                    stop_ev.set()
                        except Exception:
                            pass
        except Exception:
            pass

    t = threading.Thread(target=_reader, daemon=True)
    t.start()
    t.join(timeout=8)
    stop_ev.set()

    rep_seqs = [e["seq"] for e in replayed]
    assert len(rep_seqs) >= 1, f"Expected ≥1 replayed event after seq={mid}, got none"
    assert all(s > mid for s in rep_seqs), \
        f"Expected all seq > {mid}, got {rep_seqs}"


# ══════════════════════════════════════════════════════════════════════════════
# RP3: /stream without ?since — no regression
# ══════════════════════════════════════════════════════════════════════════════

def test_rp3_stream_no_since_no_regression():
    """RP3: /stream without ?since still works — live events arrive after connect."""
    received: list[dict] = []
    stop_ev = threading.Event()

    def _collector():
        try:
            with requests.get(f"{_base()}/stream", stream=True, timeout=15) as resp:
                for line in resp.iter_lines(chunk_size=1):
                    if stop_ev.is_set():
                        break
                    if line and line.startswith(b"data:"):
                        try:
                            evt = json.loads(line[5:].strip())
                            if evt.get("type") == "message":
                                received.append(evt)
                        except Exception:
                            pass
        except Exception:
            pass

    t = threading.Thread(target=_collector, daemon=True)
    t.start()
    time.sleep(0.3)

    # Need guest relay to trigger broadcast
    host_link = _wait_host_link(_http_port, timeout=15)
    assert host_link, "Host link unavailable"

    guest_ws = _free_port()
    guest_http = guest_ws + 100
    gp = subprocess.Popen(
        [sys.executable, RELAY_PATH, "--port", str(guest_ws), "--name", "RP3Guest",
         "--join", host_link],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=_relay_env(),
    )
    try:
        assert _wait_connected(guest_http, timeout=20), "Guest failed to connect"
        requests.post(
            f"http://127.0.0.1:{guest_http}/message:send",
            json={"role": "user",
                  "parts": [{"type": "text", "content": "rp3-live"}],
                  "message_id": f"rp3-live-{time.time():.6f}"},
            timeout=5,
        )
        time.sleep(0.5)
    finally:
        if gp.poll() is None:
            gp.terminate()
            try:
                gp.wait(timeout=5)
            except subprocess.TimeoutExpired:
                gp.kill()

    stop_ev.set()
    t.join(timeout=3)

    assert len(received) >= 1, f"Expected ≥1 live event, got {received}"


# ══════════════════════════════════════════════════════════════════════════════
# RP4: /ws/stream?since=0 replays events over WebSocket
# ══════════════════════════════════════════════════════════════════════════════

def test_rp4_ws_stream_since_replay():
    """RP4: GET /ws/stream?since=0 replays stored events over WebSocket immediately."""
    seqs = _inject_messages(2, "rp4")
    assert len(seqs) >= 2, f"Expected ≥2 injected events, got {seqs}"

    replayed: list[dict] = []

    async def _ws_replay():
        ws_url = f"ws://127.0.0.1:{_http_port}/ws/stream?since=0"
        async with websockets.connect(ws_url, open_timeout=10) as ws:
            deadline = asyncio.get_event_loop().time() + 8.0
            while True:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    break
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=remaining)
                    evt = json.loads(msg)
                    if evt.get("event") == "acp.message":
                        replayed.append(evt)
                        if len(replayed) >= 2:
                            break
                except asyncio.TimeoutError:
                    break

    asyncio.run(_ws_replay())

    assert len(replayed) >= 2, f"Expected ≥2 replayed WS events, got {replayed}"
    data_seqs = [e["data"]["seq"] for e in replayed]
    assert data_seqs == sorted(data_seqs), f"WS replayed events not ordered: {data_seqs}"


# ══════════════════════════════════════════════════════════════════════════════
# RP5: capabilities.event_replay == true
# ══════════════════════════════════════════════════════════════════════════════

def test_rp5_capabilities_event_replay():
    """RP5: AgentCard declares capabilities.event_replay=true."""
    r = requests.get(f"{_base()}/.well-known/acp.json", timeout=5)
    assert r.status_code == 200
    body = r.json()
    card = body.get("self", body)
    caps = card.get("capabilities", {})
    assert caps.get("event_replay") is True, \
        f"capabilities.event_replay should be True; got {caps}"


# ══════════════════════════════════════════════════════════════════════════════
# RP6: /stream?since=<last_seq> returns no stored events (no-op)
# ══════════════════════════════════════════════════════════════════════════════

def test_rp6_stream_since_last_seq_no_replay():
    """RP6: since=<last_seq> replays nothing (only future events arrive)."""
    seqs = _inject_messages(2, "rp6")
    assert len(seqs) >= 2
    last_seq = max(seqs)

    # Collect events for 1s — should be empty (no new messages sent)
    collected: list[dict] = []
    stop_ev = threading.Event()

    def _collector():
        try:
            with requests.get(
                f"{_base()}/stream?since={last_seq}", stream=True, timeout=5
            ) as resp:
                for line in resp.iter_lines(chunk_size=1):
                    if stop_ev.is_set():
                        break
                    if line and line.startswith(b"data:"):
                        try:
                            evt = json.loads(line[5:].strip())
                            if evt.get("type") == "message":
                                collected.append(evt)
                        except Exception:
                            pass
        except Exception:
            pass

    t = threading.Thread(target=_collector, daemon=True)
    t.start()
    time.sleep(1.0)
    stop_ev.set()
    t.join(timeout=3)

    # Only keepalive lines expected — no message events
    assert len(collected) == 0, \
        f"Expected 0 replay events after last_seq={last_seq}, got {collected}"
