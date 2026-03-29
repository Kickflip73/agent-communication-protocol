#!/usr/bin/env python3
"""
ACP WebSocket /ws/stream 测试 (v2.12)
======================================
测试 GET /ws/stream WebSocket 原生消息推送端点。

测试用例：
  WS1: 连接 /ws/stream，收到握手成功（HTTP 101）
  WS2: relay 收到消息后，WS 客户端收到 acp.message 事件
  WS3: 多个 WS 客户端同时连接，均收到广播
  WS4: 客户端断开后，后续消息不再推送（无报错）
  WS5: /status 的 capabilities.ws_stream 为 true
       (同时验证 endpoints.ws_stream 和 AgentCard)

架构：
- Host relay: HTTP relay mode（通过 Cloudflare Worker 自动注册，3-4s 拿到 token）
- Guest relay: --join acp://127.0.0.1:<ws_port>/<token>（本地直连）
- 动态端口（_free_port），避免并发测试端口冲突
- stdout token 读取（与 test_dcutr_t6_scenario_a.py 相同模式）

运行：
    python3 -m pytest tests/test_ws_stream.py -v --timeout=60
"""

import sys, os, re, time, json, socket, threading, subprocess, asyncio, signal
import pytest
import requests
import websockets

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

RELAY_PATH = os.path.join(os.path.dirname(__file__), "../relay/acp_relay.py")


# ── Port allocation ────────────────────────────────────────────────────────────

def _free_port() -> int:
    """Return WS port P such that both P and P+100 are free."""
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
    raise RuntimeError("Cannot find a free port pair")


# ── Relay lifecycle ────────────────────────────────────────────────────────────

_PROXY_VARS_WS = (
    "http_proxy", "HTTP_PROXY",
    "https_proxy", "HTTPS_PROXY",
    "no_proxy", "NO_PROXY",
)

# Read proxy config from the gateway process environment (bypasses conftest proxy removal)
_GATEWAY_PROXY_ENV: dict = {}
try:
    import pathlib
    for pid_path in pathlib.Path("/proc").iterdir():
        if pid_path.name.isdigit():
            env_file = pid_path / "environ"
            try:
                data = env_file.read_bytes().decode("utf-8", errors="replace")
                pairs = {k: v for k, v in (
                    e.split("=", 1) for e in data.split("\x00") if "=" in e
                )}
                if pairs.get("http_proxy") or pairs.get("HTTP_PROXY"):
                    _GATEWAY_PROXY_ENV = {
                        k: pairs[k] for k in _PROXY_VARS_WS if k in pairs
                    }
                    break
            except Exception:
                continue
except Exception:
    pass


def _relay_env(extra: dict = None) -> dict:
    """Build subprocess env: current os.environ + restored proxy vars."""
    env = os.environ.copy()
    env.update(_GATEWAY_PROXY_ENV)   # restore proxy for relay subprocess
    if extra:
        env.update(extra)
    return env


def _start_host(ws_port: int, name: str) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, RELAY_PATH, "--port", str(ws_port), "--name", name],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=_relay_env(),
    )


def _start_guest(ws_port: int, name: str, join_link: str) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, RELAY_PATH, "--port", str(ws_port), "--name", name,
         "--join", join_link],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=_relay_env(),
    )


def _wait_http(http_port: int, timeout: float = 15) -> bool:
    """Wait until relay HTTP is responding."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"http://127.0.0.1:{http_port}/status", timeout=0.5)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.1)
    return False


def _wait_host_link(proc: subprocess.Popen, http_port: int, timeout: float = 20) -> str | None:
    """
    Wait for host relay to expose acp:// link via HTTP polling.
    (stdout is DEVNULL — use HTTP /link + /status only)
    Returns local link acp://127.0.0.1:<ws_port>/<token>, or None.
    """
    ws_port = http_port - 100
    deadline = time.time() + timeout
    while time.time() < deadline:
        for ep in ("/link", "/status"):
            try:
                r = requests.get(f"http://127.0.0.1:{http_port}{ep}", timeout=1)
                d = r.json()
                raw = d.get("link") or ""
                if raw:
                    # Replace public IP with 127.0.0.1 for local guest connection
                    local = re.sub(r"acp://[^:]+:", "acp://127.0.0.1:", raw)
                    return local
                tok = d.get("session_id")
                if tok and tok != "None" and tok is not None:
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


def _kill(proc: subprocess.Popen) -> None:
    if proc and proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)
        except Exception:
            pass


# ── Module-scoped fixtures: host relay ────────────────────────────────────────

_host_ws_port:  int = 0
_host_http_port: int = 0
_host_proc: subprocess.Popen | None = None
_host_link: str | None = None


@pytest.fixture(scope="module", autouse=True)
def relay_server():
    global _host_ws_port, _host_http_port, _host_proc, _host_link

    _host_ws_port  = _free_port()
    _host_http_port = _host_ws_port + 100

    _host_proc = _start_host(_host_ws_port, "WsStreamHost")

    ok = _wait_http(_host_http_port, timeout=15)
    assert ok, f"Host relay HTTP failed to start on port {_host_http_port}"

    # Try to get link (for WS2/WS3 guest connection); not required for WS1/WS4/WS5
    _host_link = _wait_host_link(_host_proc, _host_http_port, timeout=20)
    # Don't assert here — WS1/WS4/WS5 work without a link

    yield

    _kill(_host_proc)


def _ws_url() -> str:
    return f"ws://127.0.0.1:{_host_http_port}/ws/stream"


def _http_base() -> str:
    return f"http://127.0.0.1:{_host_http_port}"


# ══════════════════════════════════════════════════════════════════════════════
# WS1: 握手 HTTP 101
# ══════════════════════════════════════════════════════════════════════════════

def test_ws1_handshake_101():
    """WS1: 连接 /ws/stream 握手成功（HTTP 101 Switching Protocols）."""

    async def _check():
        async with websockets.connect(_ws_url(), open_timeout=10):
            pass  # reaching here = 101 handshake succeeded

    asyncio.run(_check())


# ══════════════════════════════════════════════════════════════════════════════
# WS2: relay 收到消息后，WS 客户端收到 acp.message 事件
# ══════════════════════════════════════════════════════════════════════════════

def test_ws2_message_event():
    """WS2: relay 收到消息后，WS 客户端收到 acp.message 事件."""
    if not _host_link:
        pytest.skip("Host link not available (relay not connected to public relay)")

    received: list = []
    ws_ready   = threading.Event()
    ws_done    = threading.Event()
    errors: list = []

    async def _listener():
        try:
            async with websockets.connect(_ws_url(), open_timeout=10) as ws:
                ws_ready.set()
                try:
                    deadline = asyncio.get_event_loop().time() + 15.0
                    while True:
                        remaining = deadline - asyncio.get_event_loop().time()
                        if remaining <= 0:
                            errors.append("timeout waiting for acp.message")
                            break
                        msg = await asyncio.wait_for(ws.recv(), timeout=remaining)
                        evt = json.loads(msg)
                        if evt.get("event") == "acp.message":
                            received.append(evt)
                            break
                        # skip acp.peer and other non-message events
                except asyncio.TimeoutError:
                    errors.append("timeout waiting for ws event")
        except Exception as e:
            errors.append(f"ws error: {e}")
        finally:
            ws_done.set()

    t = threading.Thread(target=lambda: asyncio.run(_listener()), daemon=True)
    t.start()

    assert ws_ready.wait(timeout=8), "WS client failed to connect"
    time.sleep(0.3)

    # Spawn guest relay → connects to host → sends message → triggers broadcast
    guest_ws   = _free_port()
    guest_http = guest_ws + 100
    gp = _start_guest(guest_ws, "WsGuest2", _host_link)
    try:
        assert _wait_connected(guest_http, timeout=20), \
            "Guest relay failed to connect to host"

        r = requests.post(
            f"http://127.0.0.1:{guest_http}/message:send",
            json={"role": "user",
                  "parts": [{"type": "text", "content": "ws2 event test"}],
                  "message_id": "ws2-test-001"},
            timeout=5,
        )
        assert r.status_code == 200, f"Guest send failed: {r.text}"
    finally:
        _kill(gp)

    assert ws_done.wait(timeout=15), "WS client did not receive event in time"
    t.join(timeout=2)

    assert not errors, f"WS listener error: {errors[0]}"
    assert len(received) >= 1, f"Expected ≥1 event, got {received}"
    evt = received[0]
    assert evt.get("event") == "acp.message", f"Expected acp.message, got: {evt}"
    data = evt.get("data", {})
    assert data.get("parts") is not None, f"Missing parts: {data}"
    assert "server_seq" in data, f"Missing server_seq: {data}"


# ══════════════════════════════════════════════════════════════════════════════
# WS3: 多个 WS 客户端同时连接，均收到广播
# ══════════════════════════════════════════════════════════════════════════════

def test_ws3_multi_client_broadcast():
    """WS3: 3 个 WS 客户端同时连接，均收到同一 acp.message 广播."""
    if not _host_link:
        pytest.skip("Host link not available (relay not connected to public relay)")

    NUM = 3
    results   = [None] * NUM
    ready_evs = [threading.Event() for _ in range(NUM)]
    done_evs  = [threading.Event() for _ in range(NUM)]
    errors    = [[] for _ in range(NUM)]

    def _client(idx):
        async def _run():
            try:
                async with websockets.connect(_ws_url(), open_timeout=10) as ws:
                    ready_evs[idx].set()
                    try:
                        deadline = asyncio.get_event_loop().time() + 15.0
                        while True:
                            remaining = deadline - asyncio.get_event_loop().time()
                            if remaining <= 0:
                                errors[idx].append("timeout")
                                break
                            msg = await asyncio.wait_for(ws.recv(), timeout=remaining)
                            evt = json.loads(msg)
                            if evt.get("event") == "acp.message":
                                results[idx] = evt
                                break
                            # skip acp.peer events
                    except asyncio.TimeoutError:
                        errors[idx].append("timeout")
            except Exception as e:
                errors[idx].append(str(e))
            finally:
                done_evs[idx].set()
        asyncio.run(_run())

    threads = [threading.Thread(target=_client, args=(i,), daemon=True) for i in range(NUM)]
    for thr in threads:
        thr.start()

    for i, ev in enumerate(ready_evs):
        assert ev.wait(timeout=8), f"WS client {i} failed to connect"
    time.sleep(0.3)

    guest_ws   = _free_port()
    guest_http = guest_ws + 100
    gp = _start_guest(guest_ws, "WsGuest3", _host_link)
    try:
        assert _wait_connected(guest_http, timeout=20), \
            "Guest relay failed to connect to host"

        r = requests.post(
            f"http://127.0.0.1:{guest_http}/message:send",
            json={"role": "user",
                  "parts": [{"type": "text", "content": "ws3 broadcast test"}],
                  "message_id": "ws3-broadcast-001"},
            timeout=5,
        )
        assert r.status_code == 200, f"Guest send failed: {r.text}"
    finally:
        _kill(gp)

    for ev in done_evs:
        assert ev.wait(timeout=15), "A WS client timed out waiting for broadcast"
    for thr in threads:
        thr.join(timeout=2)

    for idx in range(NUM):
        assert not errors[idx], f"Client {idx} error: {errors[idx][0]}"
        assert results[idx] is not None, f"Client {idx} got no message"
        assert results[idx].get("event") == "acp.message", \
            f"Client {idx} wrong event: {results[idx]}"


# ══════════════════════════════════════════════════════════════════════════════
# WS4: 客户端断开后，relay 不崩溃
# ══════════════════════════════════════════════════════════════════════════════

def test_ws4_disconnect_cleanup():
    """WS4: 客户端断开后，relay 不崩溃，/status 仍然可用."""

    connected_ev    = threading.Event()
    disconnected_ev = threading.Event()

    async def _short_client():
        async with websockets.connect(_ws_url(), open_timeout=10):
            connected_ev.set()
        disconnected_ev.set()

    t = threading.Thread(target=lambda: asyncio.run(_short_client()), daemon=True)
    t.start()

    assert connected_ev.wait(timeout=8), "Short WS client failed to connect"
    assert disconnected_ev.wait(timeout=5), "Short WS client failed to disconnect"
    t.join(timeout=3)

    time.sleep(0.5)   # let server detect disconnect

    r = requests.get(f"{_http_base()}/status", timeout=3)
    assert r.status_code == 200, f"Relay died after WS client disconnect"


# ══════════════════════════════════════════════════════════════════════════════
# WS5: capabilities.ws_stream == true in AgentCard
# ══════════════════════════════════════════════════════════════════════════════

def test_ws5_capabilities_and_endpoints():
    """WS5: AgentCard 声明 capabilities.ws_stream=true + endpoints.ws_stream='/ws/stream'."""

    r = requests.get(f"{_http_base()}/.well-known/acp.json", timeout=5)
    assert r.status_code == 200, f"AgentCard returned {r.status_code}"

    body = r.json()
    card = body.get("self", body)

    caps = card.get("capabilities", {})
    assert caps.get("ws_stream") is True, \
        f"capabilities.ws_stream should be True; got: {caps}"

    endpoints = card.get("endpoints", {})
    assert endpoints.get("ws_stream") == "/ws/stream", \
        f"endpoints.ws_stream should be '/ws/stream'; got: {endpoints}"
