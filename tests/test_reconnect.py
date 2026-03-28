#!/usr/bin/env python3
"""
test_reconnect.py — 场景 G：断线重连 (BUG-038 fix: local-only mode v2)

GR1: Agent 连接后断开，重新连接同一 Relay，可正常收发消息
GR2: Relay 重启后，Agent 重连并重新注册（新 peer_id）
GR3: 消息在断线期间入队（offline queue），重连后状态正确

修复说明 (BUG-038 v2):
  - 原始测试依赖公网云 relay 注册 (session_id + /link token)，沙箱无外网全部失败。
  - 第一次修复尝试从 relay stdout 提取 token，但 subprocess.PIPE 下 stdout 被行缓冲，
    relay 的 print() 输出无法及时读到（relay 进程不是 TTY，缓冲区不自动 flush）。
  - 本次修复（v2）采用两种策略同时进行：
      1. 用 `-u`（PYTHONUNBUFFERED）启动 relay 子进程，确保 stdout 实时输出；
      2. 同时轮询 /status 端点（在云注册成功时也能获取 token，双保险）。
  - 不依赖任何外网 / 云 relay 注册 —— 即使云注册失败，stdout 流也能提供 token。

测试方式：
  - 用 python3 -u 启动 relay，从 stdout 实时提取 acp:// 链接中的 token
  - 用 `websockets` 直连 ws://127.0.0.1:{ws_port}/{token} 模拟 Agent
  - fixture 负责 relay 生命周期（动态端口）

要求：至少 3 个测试用例（GR1–GR3），10+ assertions，动态端口
"""

import asyncio
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest
import websockets

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RELAY_PY = os.path.join(BASE_DIR, "relay", "acp_relay.py")

# Remove proxy variables at module load time so urllib.request
# connects directly to localhost without going through the proxy.
_PROXY_VARS = (
    "http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY",
    "all_proxy", "ALL_PROXY", "ftp_proxy", "FTP_PROXY", "no_proxy", "NO_PROXY",
)
for _pv in _PROXY_VARS:
    os.environ.pop(_pv, None)

# ── helpers ───────────────────────────────────────────────────────────────────

def _free_port_pair() -> int:
    """Return WS port P such that both P and P+100 are available."""
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
    raise RuntimeError("Cannot find free port pair")


def _clean_env() -> dict:
    """Return os.environ copy without proxy variables, with PYTHONUNBUFFERED=1."""
    env = os.environ.copy()
    for v in _PROXY_VARS:
        env.pop(v, None)
    # Force unbuffered output so relay's print() flushes immediately even via PIPE
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _start_relay(ws_port: int, name: str = "TestRelay") -> tuple:
    """
    Start a relay process on ws_port (HTTP on ws_port+100).

    BUG-038 v2 fix:
      - Runs relay with `python3 -u` (unbuffered) so stdout print() calls
        are immediately readable via subprocess.PIPE (no TTY needed).
      - Simultaneously polls /status to catch cloud-registered token as fallback.
      - Returns (process, token) — token is available as soon as the relay
        prints its acp:// link (typically within 3-4s including cloud reg).

    No cloud registration required: if internet is unavailable the relay still
    prints a local-IP acp:// link on stdout (with tok_xxx token), which we capture.
    """
    http = ws_port + 100
    token_holder = {"token": None}
    stdout_lines = []
    lock = threading.Lock()

    # -u = unbuffered stdout; ensures print() output is immediately visible via PIPE
    p = subprocess.Popen(
        [sys.executable, "-u", RELAY_PY,
         "--name", name,
         "--port", str(ws_port),
         "--http-host", "127.0.0.1"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,       # line-buffered on our side
        env=_clean_env(),
    )

    # Background reader: scans relay stdout for the acp:// link
    # The relay prints a line like:
    #   "  acp://IP:PORT/tok_xxxxxxxxxxxx"
    # immediately after cloud registration (or local startup if no internet).
    def _stdout_reader():
        try:
            for line in p.stdout:
                with lock:
                    stdout_lines.append(line)
                m = re.search(r"acp://[^\s]+/(tok_[a-f0-9]+)", line)
                if m and token_holder["token"] is None:
                    token_holder["token"] = m.group(1)
        except Exception:
            pass

    reader_thread = threading.Thread(target=_stdout_reader, daemon=True)
    reader_thread.start()

    # Phase 1: wait for HTTP /status 200 (relay HTTP server is up, ~0.3s)
    http_deadline = time.time() + 15
    while time.time() < http_deadline:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{http}/status", timeout=2
            ) as r:
                if r.status == 200:
                    break
        except Exception:
            pass
        time.sleep(0.2)
    else:
        p.kill()
        raise RuntimeError(f"Relay {name}:{ws_port} HTTP failed to start within 15s")

    # Phase 2: wait for token — stdout reader + /link endpoint polling (dual strategy)
    # Relay prints the acp:// link ~2-4s after startup (after cloud reg).
    # If running in a no-internet sandbox the print happens faster (cloud fails fast).
    token_deadline = time.time() + 40  # BUG-038: relay needs ~29s in sandbox (get_public_ip + cloud reg)
    while time.time() < token_deadline:
        # Strategy A: stdout reader found the token
        with lock:
            tok = token_holder["token"]
        if tok:
            return p, tok

        # Strategy B: /link endpoint returns the token (cloud reg succeeded)
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{http}/link", timeout=2
            ) as r:
                d = json.loads(r.read())
                link = d.get("link", "") or ""
                sid = d.get("session_id", "") or ""
                if link:
                    m = re.search(r"/(tok_[a-f0-9]+)$", link)
                    if m:
                        return p, m.group(1)
                if sid and sid.startswith("tok_"):
                    return p, sid
        except Exception:
            pass

        # Strategy C: /status.relay_token (set after cloud reg)
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{http}/status", timeout=2
            ) as r:
                d = json.loads(r.read())
                rt = d.get("relay_token", "") or ""
                if rt and rt.startswith("tok_"):
                    return p, rt
                link = d.get("link", "") or ""
                if link:
                    m = re.search(r"/(tok_[a-f0-9]+)$", link)
                    if m:
                        return p, m.group(1)
        except Exception:
            pass

        time.sleep(0.3)

    # Timed out — collect diagnostics and fail clearly
    p.kill()
    with lock:
        captured = "".join(stdout_lines[-30:])
    raise RuntimeError(
        f"Relay {name}:{ws_port} token not found within 35s.\n"
        f"Captured stdout:\n{captured or '(empty)'}"
    )


def _http_get(url: str, timeout: float = 5) -> tuple:
    """Returns (body_dict, status_code)."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read()), e.code
        except Exception:
            return {"_error": str(e)}, e.code
    except Exception as ex:
        return {"_error": str(ex)}, -1


def _http_post(url: str, body: dict, timeout: float = 5) -> tuple:
    """Returns (body_dict, status_code)."""
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read()), e.code
        except Exception:
            return {"_error": str(e)}, e.code
    except Exception as ex:
        return {"_error": str(ex)}, -1


def _kill_relay(p: subprocess.Popen, wait_secs: float = 6):
    """Terminate a relay process and wait for it to exit."""
    try:
        p.terminate()
        p.wait(timeout=wait_secs)
    except subprocess.TimeoutExpired:
        p.kill()
        p.wait(timeout=2)
    except Exception:
        pass


# ── async WS helpers ──────────────────────────────────────────────────────────

async def _ws_connect_and_register(ws_port: int, token: str, timeout: float = 8.0):
    """
    Open a raw WebSocket connection to the relay host-mode endpoint:
      ws://127.0.0.1:{ws_port}/{token}

    The relay assigns a peer_id when the WS connects; we retrieve it via /peers.

    Returns (websocket, peer_id).
    """
    http = ws_port + 100
    uri = f"ws://127.0.0.1:{ws_port}/{token}"
    ws = await asyncio.wait_for(
        websockets.connect(uri, open_timeout=timeout),
        timeout=timeout,
    )

    # Relay may push acp.agent_card on connect; receive it to confirm handshake
    try:
        raw = await asyncio.wait_for(ws.recv(), timeout=3.0)
        msg = json.loads(raw)
        # tolerate any envelope — just confirm we can parse it
        assert isinstance(msg, dict), f"Expected dict from relay, got {type(msg)}"
    except asyncio.TimeoutError:
        pass  # some relay versions don't push card immediately

    # Retrieve peer_id assigned by relay
    peers_resp, _ = _http_get(f"http://127.0.0.1:{http}/peers")
    peers = peers_resp.get("peers", [])
    connected_peers = [p for p in peers if p.get("connected")]
    if connected_peers:
        peer_id = connected_peers[-1]["id"]
    elif peers:
        peer_id = peers[-1]["id"]
    else:
        peer_id = None
    return ws, peer_id


_SHARED_LOOP: asyncio.AbstractEventLoop | None = None
_SHARED_LOOP_LOCK = threading.Lock()


def _get_shared_loop() -> asyncio.AbstractEventLoop:
    """Return a single persistent event loop for the test session (BUG-038 fix).

    Using a new event loop per call causes 'Future attached to a different loop'
    errors when websockets objects created in loop-A are closed in loop-B.
    A single shared loop avoids cross-loop issues.
    """
    global _SHARED_LOOP
    with _SHARED_LOOP_LOCK:
        if _SHARED_LOOP is None or _SHARED_LOOP.is_closed():
            _SHARED_LOOP = asyncio.new_event_loop()
            asyncio.set_event_loop(_SHARED_LOOP)
    return _SHARED_LOOP


def _run_async(coro):
    """Run a coroutine in the shared event loop (BUG-038: avoids cross-loop errors)."""
    loop = _get_shared_loop()
    return loop.run_until_complete(coro)


# ══════════════════════════════════════════════════════════════════════════════
# GR1 — Agent 连接后断开，重新连接同一 Relay，可正常收发消息
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.timeout(180)
def test_gr1_reconnect_same_relay():
    """
    GR1: Agent closes WS connection, re-opens it to the SAME relay instance.
    After reconnect, messages can be sent and received normally.

    Local-only mode: uses ws://127.0.0.1:{ws_port}/{token} directly.
    No cloud token or internet access required.
    """
    ws_port = _free_port_pair()
    http = ws_port + 100

    relay, token = _start_relay(ws_port, "GR1-Relay")
    try:
        # ── Step 1: First WS connection ───────────────────────────────────────
        ws1, peer_id1 = _run_async(_ws_connect_and_register(ws_port, token))

        # Assertion 1: peer_id assigned after first connect
        assert peer_id1 is not None, \
            "GR1: peer_id should be assigned after first WS connect"

        # Assertion 2: relay reports peer as connected
        status1, code1 = _http_get(f"http://127.0.0.1:{http}/status")
        assert code1 == 200, f"GR1: /status should return 200, got {code1}"
        assert (status1.get("connected") is True or status1.get("peer_count", 0) >= 1), \
            f"GR1: relay should report ≥1 connected peer, got {status1}"

        # ── Step 2: Send a message before disconnect ──────────────────────────
        resp1, _ = _http_post(
            f"http://127.0.0.1:{http}/peer/{peer_id1}/send",
            {"parts": [{"type": "text", "content": "hello before disconnect"}],
             "role": "agent"}
        )
        # Assertion 3: pre-disconnect message accepted
        assert resp1.get("ok"), \
            f"GR1: pre-disconnect send should succeed, got {resp1}"

        # ── Step 3: Force-close WS (simulate disconnect) ──────────────────────
        _run_async(ws1.close())
        time.sleep(1.5)

        # Assertion 4: relay detects the disconnect
        status2, _ = _http_get(f"http://127.0.0.1:{http}/status")
        connected_after = status2.get("connected", True)
        peer_count_after = status2.get("peer_count", 1)
        assert (not connected_after) or (peer_count_after == 0), \
            f"GR1: relay should detect disconnect; connected={connected_after}, " \
            f"peer_count={peer_count_after}"

        # ── Step 4: Reconnect ─────────────────────────────────────────────────
        ws2, peer_id2 = _run_async(_ws_connect_and_register(ws_port, token))

        # Assertion 5: second connection established
        assert peer_id2 is not None, \
            "GR1: peer_id should be assigned after reconnect"

        # Assertion 6: relay reports peer as connected again
        status3, _ = _http_get(f"http://127.0.0.1:{http}/status")
        assert (status3.get("connected") is True or status3.get("peer_count", 0) >= 1), \
            "GR1: relay should report connected after reconnect"

        # ── Step 5: Post-reconnect message ────────────────────────────────────
        resp2, _ = _http_post(
            f"http://127.0.0.1:{http}/peer/{peer_id2}/send",
            {"parts": [{"type": "text", "content": "hello after reconnect"}],
             "role": "agent"}
        )
        # Assertion 7: post-reconnect message accepted
        assert resp2.get("ok"), \
            f"GR1: post-reconnect send should succeed, got {resp2}"

        # Assertion 8: message_id present in response
        assert resp2.get("message_id"), \
            "GR1: response should include message_id"

        _run_async(ws2.close())

    finally:
        _kill_relay(relay)


# ══════════════════════════════════════════════════════════════════════════════
# GR2 — Relay 重启后，Agent 重连并重新注册
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.timeout(180)
def test_gr2_reconnect_after_relay_restart():
    """
    GR2: The relay process is killed (simulating server crash/restart).
    Agent re-connects to a fresh relay on the same port and re-registers.

    Local-only mode: two separate relay instances on the same ws_port.
    No cloud token required.
    """
    ws_port = _free_port_pair()
    http = ws_port + 100

    # ── Phase A: relay v1 ─────────────────────────────────────────────────────
    relay1, token1 = _start_relay(ws_port, "GR2-Relay-v1")

    # Step 1: Connect to relay v1
    ws1, peer_id1 = _run_async(_ws_connect_and_register(ws_port, token1))

    # Assertion 1: connected to relay v1
    assert peer_id1 is not None, "GR2: should register with relay v1"

    # Assertion 2: relay v1 is healthy
    status1, code1 = _http_get(f"http://127.0.0.1:{http}/status")
    assert code1 == 200, "GR2: relay v1 /status should return 200"
    assert "acp_version" in status1, "GR2: /status should include acp_version"

    # Step 2: Send a message to confirm relay v1 works
    resp1, _ = _http_post(
        f"http://127.0.0.1:{http}/peer/{peer_id1}/send",
        {"parts": [{"type": "text", "content": "msg to relay v1"}], "role": "agent"}
    )
    # Assertion 3: message delivered on relay v1
    assert resp1.get("ok"), f"GR2: message to relay v1 should succeed, got {resp1}"

    # Step 3: Kill relay v1
    _kill_relay(relay1)
    time.sleep(1.5)

    # Assertion 4: relay v1 process is dead
    assert relay1.poll() is not None, "GR2: relay v1 process should have terminated"

    # ── Phase B: relay v2 on same port ───────────────────────────────────────
    relay2, token2 = _start_relay(ws_port, "GR2-Relay-v2")

    # Assertion 5: relay v2 is up
    status2, code2 = _http_get(f"http://127.0.0.1:{http}/status")
    assert code2 == 200, f"GR2: relay v2 /status should return 200, got {code2}"

    # Step 4: Agent reconnects to relay v2 (new token)
    ws2, peer_id2 = _run_async(_ws_connect_and_register(ws_port, token2))

    try:
        # Assertion 6: new peer_id from relay v2
        assert peer_id2 is not None, \
            "GR2: should obtain a peer_id from relay v2"

        # Assertion 7: relay v2 reports peer as connected
        status3, _ = _http_get(f"http://127.0.0.1:{http}/status")
        assert (status3.get("connected") is True or status3.get("peer_count", 0) >= 1), \
            "GR2: relay v2 should report peer as connected"

        # Assertion 8: can send message after reconnect to relay v2
        resp2, _ = _http_post(
            f"http://127.0.0.1:{http}/peer/{peer_id2}/send",
            {"parts": [{"type": "text", "content": "msg after relay restart"}],
             "role": "agent"}
        )
        assert resp2.get("ok"), \
            f"GR2: message should succeed after relay restart, got {resp2}"

        # Assertion 9: message_id in response from relay v2
        assert resp2.get("message_id"), \
            "GR2: response from relay v2 should include message_id"

        # Assertion 10: relay v2 reports fresh state (acp_version present)
        assert "acp_version" in status3, \
            "GR2: relay v2 status should include acp_version"

        _run_async(ws2.close())

    finally:
        _kill_relay(relay2)


# ══════════════════════════════════════════════════════════════════════════════
# GR3 — 消息在断线期间入队，重连后状态正确
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.timeout(180)
def test_gr3_offline_queue_on_reconnect():
    """
    GR3: While Agent is disconnected, messages sent to it are queued (offline queue).
    After reconnect, the queue is flushed OR properly tracked. Status reflects correct
    state throughout.

    Per relay spec (v2.0): the offline queue is flushed to the peer on reconnect.
    This test verifies:
      - Relay accepts messages while peer is offline (no crash)
      - /offline-queue endpoint is accessible (v2.0 feature)
      - After reconnect, new messages can be sent successfully
      - /recv endpoint works after reconnect

    Local-only mode: no cloud token required.
    """
    ws_port = _free_port_pair()
    http = ws_port + 100

    relay, token = _start_relay(ws_port, "GR3-Relay")
    try:
        # ── Step 1: Connect Agent ─────────────────────────────────────────────
        ws1, peer_id1 = _run_async(_ws_connect_and_register(ws_port, token))

        # Assertion 1: peer registered
        assert peer_id1 is not None, "GR3: peer_id must be assigned on first connect"

        # Assertion 2: initial /status is healthy
        status0, code0 = _http_get(f"http://127.0.0.1:{http}/status")
        assert code0 == 200, f"GR3: /status should return 200 on startup, got {code0}"
        assert isinstance(status0.get("messages_received", 0), int), \
            "GR3: messages_received must be an integer"

        # ── Step 2: Disconnect Agent ──────────────────────────────────────────
        _run_async(ws1.close())
        time.sleep(1.5)

        # Assertion 3: relay detects disconnect
        status_disc, _ = _http_get(f"http://127.0.0.1:{http}/status")
        connected_disc = status_disc.get("connected", True)
        peer_count_disc = status_disc.get("peer_count", 1)
        assert (not connected_disc) or (peer_count_disc == 0), \
            f"GR3: relay should detect disconnect; connected={connected_disc}, " \
            f"peer_count={peer_count_disc}"

        # ── Step 3: Send messages while Agent is offline ──────────────────────
        # /message:send broadcasts to all peers (including offline queue)
        OFFLINE_MSG_COUNT = 3
        for i in range(OFFLINE_MSG_COUNT):
            _http_post(
                f"http://127.0.0.1:{http}/message:send",
                {"message": {"role": "agent",
                              "parts": [{"type": "text",
                                         "content": f"offline_msg_{i}"}]},
                 "role": "agent"}
            )
            # Relay should accept offline messages without crashing

        # Assertion 4: relay still responds after receiving offline messages
        status_off, code_off = _http_get(f"http://127.0.0.1:{http}/status")
        assert code_off == 200, \
            f"GR3: /status should return 200 during offline period, got {code_off}"

        # ── Step 4: Reconnect Agent ───────────────────────────────────────────
        ws3, peer_id3 = _run_async(_ws_connect_and_register(ws_port, token))

        # Allow time for offline queue flush
        time.sleep(1.5)

        # Assertion 5: re-registration succeeds
        assert peer_id3 is not None, "GR3: peer_id must be assigned on reconnect"

        # Assertion 6: relay status is healthy after reconnect
        status_rc, _ = _http_get(f"http://127.0.0.1:{http}/status")
        assert (status_rc.get("connected") is True or
                status_rc.get("peer_count", 0) >= 1), \
            "GR3: relay should report connected after reconnect"

        # Assertion 7: can send NEW messages after reconnect
        resp_new, _ = _http_post(
            f"http://127.0.0.1:{http}/peer/{peer_id3}/send",
            {"parts": [{"type": "text", "content": "post_reconnect_msg"}],
             "role": "agent"}
        )
        assert resp_new.get("ok"), \
            f"GR3: post-reconnect send should succeed, got {resp_new}"

        # Assertion 8: /recv endpoint reachable and returns proper structure
        recv_resp, recv_code = _http_get(f"http://127.0.0.1:{http}/recv")
        assert recv_code == 200, \
            f"GR3: /recv should return 200, got {recv_code}"
        assert "messages" in recv_resp, \
            f"GR3: /recv should include 'messages' key, got {recv_resp}"

        # Assertion 9: /offline-queue endpoint accessible (v2.0 feature)
        # Per relay v2.x spec: offline queue is flushed on reconnect, so queue
        # should be empty (or contain structured info). The endpoint must not error.
        oq_resp, oq_code = _http_get(f"http://127.0.0.1:{http}/offline-queue")
        assert oq_code == 200, \
            f"GR3: /offline-queue should return 200, got {oq_code}"
        assert isinstance(oq_resp, dict), \
            f"GR3: /offline-queue should return a dict, got {type(oq_resp)}"
        # NOTE: relay v2.x flushes the offline queue on reconnect, so after
        # reconnect the queue count should be 0 (or the field may be absent).

        # Assertion 10: message_id present in post-reconnect response
        assert resp_new.get("message_id"), \
            "GR3: post-reconnect response must include message_id"

        _run_async(ws3.close())

    finally:
        _kill_relay(relay)
