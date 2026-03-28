#!/usr/bin/env python3
"""
test_reconnect.py — 场景 GR：断线重连 (BUG-038 local-only rewrite v3)

GR1: 同 relay 重连 — Alpha(host) + Beta(guest --join Alpha)，Beta 重启重连
GR2: Relay 重启 — Kill Alpha(host) 重启后 Beta(guest) 重新连接
GR3: 离线队列 — Alpha 离线期间 Beta 发消息，重连后验证状态

设计原则（BUG-038 v3 修复）:
  - **local-only relay-to-relay 模式**：
    * Alpha relay: host mode（等待 incoming WS 连接）
    * Beta relay:  guest mode（--join acp://127.0.0.1:alpha_ws/token）
    * 直接使用 ws:// URL 互连，不依赖公网云 relay
  - 不使用原始 WebSocket client（无 websockets 库）
  - token 从 Alpha relay stdout 实时提取（PYTHONUNBUFFERED=1）
  - Beta relay 用 --join 启动，跳过 NAT 三级策略（直接调用 guest_mode）
  - 所有 assertion 通过 HTTP API 完成（/status, /peers, /peer/{id}/send 等）

架构说明：
  host_mode 的 WS server 在公网 IP 探测完成后启动（约 35s），
  token 通过 stdout 提取后立即启动 Beta(--join)，所以总等待约 35s。

运行：
  pytest tests/test_reconnect.py -v
  pytest tests/test_reconnect.py -v --timeout=200
"""

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

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RELAY_PY = os.path.join(BASE_DIR, "relay", "acp_relay.py")

_PROXY_VARS = (
    "http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY",
    "all_proxy", "ALL_PROXY", "ftp_proxy", "FTP_PROXY", "no_proxy", "NO_PROXY",
)
for _pv in _PROXY_VARS:
    os.environ.pop(_pv, None)


# ── 端口分配 ──────────────────────────────────────────────────────────────────

def _free_port() -> int:
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
    raise RuntimeError("Cannot find a free port pair (ws + ws+100)")


# ── 环境变量 ──────────────────────────────────────────────────────────────────

def _clean_env() -> dict:
    """Return os.environ copy without proxy vars, with PYTHONUNBUFFERED=1."""
    env = os.environ.copy()
    for v in _PROXY_VARS:
        env.pop(v, None)
    env["PYTHONUNBUFFERED"] = "1"
    return env


# ── HTTP helpers ──────────────────────────────────────────────────────────────

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


def _http_post(url: str, body: dict, timeout: float = 8) -> tuple:
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


# ── Relay 生命周期 ─────────────────────────────────────────────────────────────

def _start_host_relay(ws_port: int, name: str = "Alpha") -> subprocess.Popen:
    """
    Start a relay in host mode (default: no --join).
    WS server starts after public-IP detection (~35s in sandbox).
    Returns process handle; use _wait_host_link() to get token.
    """
    return subprocess.Popen(
        [sys.executable, "-u", RELAY_PY,
         "--name", name,
         "--port", str(ws_port),
         "--http-host", "127.0.0.1"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
        env=_clean_env(),
    )


def _start_guest_relay(ws_port: int, name: str, join_link: str) -> subprocess.Popen:
    """
    Start a relay in guest mode (--join <link>).
    Beta will call guest_mode() directly (no NAT traversal, no duplicate WS issue).
    Returns process handle.
    """
    return subprocess.Popen(
        [sys.executable, "-u", RELAY_PY,
         "--name", name,
         "--port", str(ws_port),
         "--http-host", "127.0.0.1",
         "--join", join_link],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
        env=_clean_env(),
    )


def _wait_http_ready(http_port: int, timeout: float = 15) -> bool:
    """Wait until relay HTTP server returns 200 on /status."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{http_port}/status", timeout=2
            ) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def _wait_host_link(proc: subprocess.Popen, http_port: int, timeout: float = 45) -> str | None:
    """
    Wait for the host relay to produce an acp:// link (stdout + HTTP fallback).
    Returns local link "acp://127.0.0.1:<ws_port>/tok_xxx" or None.

    Strategy:
      A) Read relay stdout in background thread, extract tok_xxx
      B) Poll /link and /status HTTP endpoints in parallel
    """
    token_holder: dict = {"link": None}
    lock = threading.Lock()

    def _stdout_reader():
        try:
            for line in proc.stdout:
                m = re.search(r"acp://[^\s/]+:(\d+)/(tok_[a-f0-9]+)", line)
                if m and not token_holder["link"]:
                    with lock:
                        token_holder["link"] = f"acp://127.0.0.1:{m.group(1)}/{m.group(2)}"
        except Exception:
            pass

    t = threading.Thread(target=_stdout_reader, daemon=True)
    t.start()

    deadline = time.time() + timeout
    while time.time() < deadline:
        with lock:
            if token_holder["link"]:
                return token_holder["link"]

        for endpoint in ("/link", "/status"):
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{http_port}{endpoint}", timeout=2
                ) as r:
                    d = json.loads(r.read())
                    raw = d.get("link", "") or ""
                    if raw:
                        local = re.sub(r"acp://[^:]+:", "acp://127.0.0.1:", raw)
                        with lock:
                            token_holder["link"] = local
                        return local
            except Exception:
                pass
        time.sleep(0.3)
    return None


def _kill_relay(proc: subprocess.Popen, wait_secs: float = 8) -> None:
    """Terminate relay process gracefully, then force-kill if needed."""
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=wait_secs)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=2)
    except Exception:
        pass


def _wait_connected(http_port: int, timeout: float = 15) -> bool:
    """Poll /status until connected=True or peer_count >= 1."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        st, _ = _http_get(f"http://127.0.0.1:{http_port}/status")
        if st.get("connected") is True or st.get("peer_count", 0) >= 1:
            return True
        time.sleep(0.3)
    return False


def _wait_disconnected(http_port: int, timeout: float = 10) -> bool:
    """Poll /status until connected=False and peer_count == 0."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        st, _ = _http_get(f"http://127.0.0.1:{http_port}/status")
        if not st.get("connected", True) and st.get("peer_count", 1) == 0:
            return True
        time.sleep(0.3)
    return False


def _send_msg(http_port: int, peer_id: str, content: str) -> tuple:
    """Send a message to a specific peer. Returns (resp_dict, http_code)."""
    return _http_post(
        f"http://127.0.0.1:{http_port}/peer/{peer_id}/send",
        {"parts": [{"type": "text", "content": content}], "role": "agent"},
    )


# ── Alpha host relay fixture ───────────────────────────────────────────────────
# Shared across GR1/GR2/GR3 to avoid re-doing 35s public-IP detection per test.

_shared_alpha_state: dict = {}


def _ensure_alpha_host(alpha_ws: int) -> tuple:
    """
    Returns (alpha_proc, alpha_http, alpha_link, alpha_ws) —
    starts Alpha host relay if not already running.
    Note: alpha_ws is provided to allow test isolation.
    """
    alpha_http = alpha_ws + 100
    proc = _start_host_relay(alpha_ws, "GR-Alpha")
    assert _wait_http_ready(alpha_http, timeout=15), \
        "Alpha relay HTTP did not start within 15s"
    link = _wait_host_link(proc, alpha_http, timeout=45)
    assert link is not None, \
        "Alpha relay did not produce an acp:// link within 45s"
    return proc, alpha_http, link


# ══════════════════════════════════════════════════════════════════════════════
# GR1 — 同 relay 重连：Beta(guest) 断开后重新连接 Alpha(host)
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.timeout(200)
def test_gr1_reconnect_same_relay():
    """
    GR1: Alpha relay (host) + Beta relay (guest --join Alpha).
    Beta disconnects (kill), then restarts with --join and reconnects.
    After reconnect, Alpha-side messaging works normally.

    local-only relay-to-relay mode (BUG-038 v3):
      - No raw WS client
      - No public cloud token
      - Beta --join acp://127.0.0.1:<alpha_ws>/<token>
    """
    alpha_ws = _free_port()
    beta_ws  = _free_port()
    alpha_http = alpha_ws + 100
    beta_http  = beta_ws  + 100

    # ── Start Alpha (host) ────────────────────────────────────────────────────
    alpha_proc, _, alpha_link = _ensure_alpha_host(alpha_ws)
    try:
        # ── Phase 1: Start Beta (guest --join Alpha) ──────────────────────────
        beta_proc = _start_guest_relay(beta_ws, "GR1-Beta", alpha_link)
        try:
            assert _wait_http_ready(beta_http, timeout=15), \
                "GR1: Beta relay HTTP did not start within 15s"

            # Assertion 1: Alpha detects Beta connected
            assert _wait_connected(alpha_http, timeout=20), \
                "GR1: Alpha should report connected=True after Beta joins"

            # Assertion 2: Beta detects Alpha connected
            assert _wait_connected(beta_http, timeout=20), \
                "GR1: Beta should report connected=True after joining Alpha"

            # ── Phase 2: Alpha sends to Beta (pre-disconnect) ─────────────────
            # Get peer_id from Alpha's perspective
            peers_resp, _ = _http_get(f"http://127.0.0.1:{alpha_http}/peers")
            alpha_peers = peers_resp.get("peers", [])
            # Assertion 3: Alpha has at least one connected peer
            assert alpha_peers, "GR1: Alpha should have at least one peer"
            connected_peers = [p for p in alpha_peers if p.get("connected")]
            assert connected_peers, "GR1: Alpha should have at least one connected peer"
            peer_id = connected_peers[0]["id"]

            resp1, code1 = _send_msg(alpha_http, peer_id, "hello_before_disconnect")
            # Assertion 4: pre-disconnect send succeeds
            assert resp1.get("ok"), \
                f"GR1: pre-disconnect Alpha→Beta send should succeed; got {resp1}"
            assert resp1.get("message_id"), \
                "GR1: pre-disconnect response must include message_id"

            # ── Phase 3: Kill Beta (disconnect) ───────────────────────────────
            _kill_relay(beta_proc)

        finally:
            # Make sure beta_proc is cleaned up even if assertion fails
            if "beta_proc" in dir():
                try:
                    _kill_relay(beta_proc)
                except Exception:
                    pass

        # Assertion 5: Beta process terminated
        assert beta_proc.poll() is not None, \
            "GR1: Beta relay should be terminated after kill"

        # Assertion 6: Alpha detects disconnect
        assert _wait_disconnected(alpha_http, timeout=15), \
            "GR1: Alpha should detect Beta disconnection within 15s"

        # ── Phase 4: Restart Beta (reconnect to same Alpha) ───────────────────
        beta_proc2 = _start_guest_relay(beta_ws, "GR1-Beta-v2", alpha_link)
        try:
            assert _wait_http_ready(beta_http, timeout=15), \
                "GR1: Beta v2 HTTP should start within 15s"

            # Assertion 7: Alpha detects new connection
            assert _wait_connected(alpha_http, timeout=20), \
                "GR1: Alpha should detect Beta v2 reconnection within 20s"

            # Assertion 8: Beta v2 also reports connected
            assert _wait_connected(beta_http, timeout=20), \
                "GR1: Beta v2 should report connected=True"

            # ── Phase 5: Send message after reconnect ─────────────────────────
            peers_resp2, _ = _http_get(f"http://127.0.0.1:{alpha_http}/peers")
            alpha_peers2 = peers_resp2.get("peers", [])
            connected_peers2 = [p for p in alpha_peers2 if p.get("connected")]
            # Assertion 9: Alpha has connected peer after reconnect
            assert connected_peers2, "GR1: Alpha should have a connected peer after reconnect"
            peer_id2 = connected_peers2[0]["id"]

            resp2, _ = _send_msg(alpha_http, peer_id2, "hello_after_reconnect")
            # Assertion 10: post-reconnect send succeeds
            assert resp2.get("ok"), \
                f"GR1: post-reconnect send should succeed; got {resp2}"

            # Assertion 11: message_id in response
            assert resp2.get("message_id"), \
                "GR1: post-reconnect response must include message_id"

            # Assertion 12: Alpha /status healthy after reconnect
            st_alpha, code_a = _http_get(f"http://127.0.0.1:{alpha_http}/status")
            assert code_a == 200, f"GR1: Alpha /status should return 200; got {code_a}"
            assert "acp_version" in st_alpha, "GR1: Alpha /status must include acp_version"

        finally:
            _kill_relay(beta_proc2)

    finally:
        _kill_relay(alpha_proc)


# ══════════════════════════════════════════════════════════════════════════════
# GR2 — Relay 重启：Kill Alpha(host)，重启后 Beta(guest) 重新连接
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.timeout(200)
def test_gr2_reconnect_after_relay_restart():
    """
    GR2: Alpha relay (host) + Beta relay (guest). Alpha is killed (crash).
    A new Alpha host relay starts on the same port. Beta reconnects with --join.
    Messaging is verified after restart.

    local-only relay-to-relay mode (BUG-038 v3).
    """
    alpha_ws = _free_port()
    beta_ws  = _free_port()
    alpha_http = alpha_ws + 100
    beta_http  = beta_ws  + 100

    # ── Start Alpha v1 (host) ─────────────────────────────────────────────────
    alpha_proc1, _, alpha_link1 = _ensure_alpha_host(alpha_ws)
    try:
        # ── Start Beta (guest --join Alpha v1) ────────────────────────────────
        beta_proc = _start_guest_relay(beta_ws, "GR2-Beta", alpha_link1)
        try:
            assert _wait_http_ready(beta_http, timeout=15), \
                "GR2: Beta HTTP did not start within 15s"
            assert _wait_connected(alpha_http, timeout=20), \
                "GR2: Alpha v1 should report connected after Beta joins"
            assert _wait_connected(beta_http, timeout=20), \
                "GR2: Beta should report connected after joining Alpha v1"

            # Get connected peer from Beta's perspective
            peers_resp, _ = _http_get(f"http://127.0.0.1:{beta_http}/peers")
            beta_peers = peers_resp.get("peers", [])
            connected_beta_peers = [p for p in beta_peers if p.get("connected")]
            # Assertion 1: Beta has a connected peer
            assert connected_beta_peers, "GR2: Beta should have a connected peer to Alpha v1"
            beta_peer_id = connected_beta_peers[0]["id"]

            # Send message Beta → Alpha v1
            resp1, _ = _send_msg(beta_http, beta_peer_id, "msg_to_alpha_v1")
            # Assertion 2: Beta→Alpha v1 message succeeds
            assert resp1.get("ok"), f"GR2: Beta→Alpha v1 message should succeed; got {resp1}"

            # ── Kill Alpha v1 ─────────────────────────────────────────────────
            _kill_relay(alpha_proc1)
            # Assertion 3: Alpha v1 process terminated
            assert alpha_proc1.poll() is not None, \
                "GR2: Alpha v1 should be terminated after kill"

            # Beta should detect disconnect
            assert _wait_disconnected(beta_http, timeout=15), \
                "GR2: Beta should detect Alpha v1 disconnect within 15s"

        finally:
            if beta_proc.poll() is None:
                _kill_relay(beta_proc)

    finally:
        if alpha_proc1.poll() is None:
            _kill_relay(alpha_proc1)

    # ── Start Alpha v2 (new host, same port) ──────────────────────────────────
    alpha_proc2, _, alpha_link2 = _ensure_alpha_host(alpha_ws)
    try:
        # ── Restart Beta with --join new Alpha v2 ────────────────────────────
        beta_proc2 = _start_guest_relay(beta_ws, "GR2-Beta-v2", alpha_link2)
        try:
            assert _wait_http_ready(beta_http, timeout=15), \
                "GR2: Beta v2 HTTP did not start within 15s"
            assert _wait_connected(alpha_http, timeout=20), \
                "GR2: Alpha v2 should report connected after Beta v2 joins"
            assert _wait_connected(beta_http, timeout=20), \
                "GR2: Beta v2 should report connected to Alpha v2"

            # Assertion 4: Alpha v2 /status is healthy
            st_alpha2, code_a2 = _http_get(f"http://127.0.0.1:{alpha_http}/status")
            assert code_a2 == 200, f"GR2: Alpha v2 /status should return 200; got {code_a2}"
            assert "acp_version" in st_alpha2, "GR2: Alpha v2 /status must include acp_version"

            # Get connected peer from Alpha v2
            peers_resp2, _ = _http_get(f"http://127.0.0.1:{alpha_http}/peers")
            alpha_peers2 = peers_resp2.get("peers", [])
            connected_alpha_peers2 = [p for p in alpha_peers2 if p.get("connected")]
            # Assertion 5: Alpha v2 has a connected peer
            assert connected_alpha_peers2, "GR2: Alpha v2 should have a connected peer"
            alpha_peer_id2 = connected_alpha_peers2[0]["id"]

            # Send message Alpha v2 → Beta v2
            resp2, _ = _send_msg(alpha_http, alpha_peer_id2, "msg_after_alpha_restart")
            # Assertion 6: post-restart send succeeds
            assert resp2.get("ok"), \
                f"GR2: Alpha v2 → Beta v2 send should succeed; got {resp2}"
            assert resp2.get("message_id"), \
                "GR2: post-restart response must include message_id"

            # Assertion 7: Beta v2 /status healthy
            st_beta2, code_b2 = _http_get(f"http://127.0.0.1:{beta_http}/status")
            assert code_b2 == 200, f"GR2: Beta v2 /status should return 200; got {code_b2}"

        finally:
            _kill_relay(beta_proc2)

    finally:
        _kill_relay(alpha_proc2)


# ══════════════════════════════════════════════════════════════════════════════
# GR3 — 离线队列：Alpha(host) 离线期间 Beta(guest) 发消息，重连后验证
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.timeout(200)
def test_gr3_offline_queue_on_reconnect():
    """
    GR3: Alpha relay (host) + Beta relay (guest). Alpha is killed (offline).
    Beta sends messages while Alpha is offline — relay should queue or error gracefully.
    Alpha restarts (new host). Beta reconnects with --join to new Alpha.
    Post-reconnect messaging works normally.
    /offline-queue endpoint is verified throughout.

    local-only relay-to-relay mode (BUG-038 v3).
    """
    alpha_ws = _free_port()
    beta_ws  = _free_port()
    alpha_http = alpha_ws + 100
    beta_http  = beta_ws  + 100

    # ── Start Alpha v1 (host) ─────────────────────────────────────────────────
    alpha_proc1, _, alpha_link1 = _ensure_alpha_host(alpha_ws)
    try:
        # ── Start Beta (guest --join Alpha v1) ────────────────────────────────
        beta_proc = _start_guest_relay(beta_ws, "GR3-Beta", alpha_link1)
        try:
            assert _wait_http_ready(beta_http, timeout=15), \
                "GR3: Beta HTTP did not start within 15s"
            assert _wait_connected(alpha_http, timeout=20), \
                "GR3: Alpha v1 should report connected after Beta joins"
            assert _wait_connected(beta_http, timeout=20), \
                "GR3: Beta should report connected after joining Alpha v1"

            # Get peer_id from Beta's perspective
            peers_resp, _ = _http_get(f"http://127.0.0.1:{beta_http}/peers")
            beta_peers = peers_resp.get("peers", [])
            connected_beta_peers = [p for p in beta_peers if p.get("connected")]
            # Assertion 1: Beta has a connected peer
            assert connected_beta_peers, "GR3: Beta should have a connected peer to Alpha v1"
            beta_peer_id = connected_beta_peers[0]["id"]

            # Assertion 2: /offline-queue accessible before disconnect
            oq0, oq0_code = _http_get(f"http://127.0.0.1:{beta_http}/offline-queue")
            assert oq0_code == 200, \
                f"GR3: Beta /offline-queue should return 200 before disconnect; got {oq0_code}"

            # ── Kill Alpha v1 (simulate offline) ──────────────────────────────
            _kill_relay(alpha_proc1)
            # Assertion 3: Alpha v1 process terminated
            assert alpha_proc1.poll() is not None, \
                "GR3: Alpha v1 should be terminated after kill"

            # Wait for Beta to detect disconnect
            assert _wait_disconnected(beta_http, timeout=15), \
                "GR3: Beta should detect Alpha v1 disconnect within 15s"

        finally:
            if alpha_proc1.poll() is None:
                _kill_relay(alpha_proc1)

        # ── Phase 3: Beta sends messages while Alpha is offline ───────────────
        OFFLINE_MSG_COUNT = 3
        offline_results = []
        for i in range(OFFLINE_MSG_COUNT):
            r_off, c_off = _send_msg(beta_http, beta_peer_id, f"offline_msg_{i}")
            offline_results.append((r_off, c_off))

        # Assertion 4: Beta relay doesn't crash during offline sends
        st_off, code_off = _http_get(f"http://127.0.0.1:{beta_http}/status")
        assert code_off == 200, \
            f"GR3: Beta /status should return 200 during offline; got {code_off}"

        # Assertion 5: offline sends are queued or return an error (no silent crash)
        for r_off, c_off in offline_results:
            acceptable = (
                r_off.get("ok") is True or
                c_off in (503, 500, 400, 404) or
                r_off.get("error_code") is not None
            )
            assert acceptable, \
                f"GR3: offline send must be queued or return error; got {r_off} (HTTP {c_off})"

        # Assertion 6: /offline-queue accessible during offline
        oq1, oq1_code = _http_get(f"http://127.0.0.1:{beta_http}/offline-queue")
        assert oq1_code == 200, \
            f"GR3: Beta /offline-queue should return 200 during offline; got {oq1_code}"

    finally:
        if "beta_proc" in dir() and beta_proc.poll() is None:
            _kill_relay(beta_proc)

    # ── Phase 4: Restart Alpha v2 (new host) ─────────────────────────────────
    alpha_proc2, _, alpha_link2 = _ensure_alpha_host(alpha_ws)
    try:
        # ── Phase 5: Beta reconnects to new Alpha v2 ─────────────────────────
        # Kill old beta, restart with --join new Alpha
        _kill_relay(beta_proc)
        beta_proc2 = _start_guest_relay(beta_ws, "GR3-Beta-v2", alpha_link2)
        try:
            assert _wait_http_ready(beta_http, timeout=15), \
                "GR3: Beta v2 HTTP did not start within 15s"
            assert _wait_connected(alpha_http, timeout=20), \
                "GR3: Alpha v2 should report connected after Beta v2 joins"
            assert _wait_connected(beta_http, timeout=20), \
                "GR3: Beta v2 should report connected to Alpha v2"

            # Allow offline queue to flush
            time.sleep(1.5)

            # ── Phase 6: Post-reconnect messaging ────────────────────────────
            # Get peer_id from Beta v2 perspective
            peers_resp2, _ = _http_get(f"http://127.0.0.1:{beta_http}/peers")
            beta_peers2 = peers_resp2.get("peers", [])
            connected_beta_peers2 = [p for p in beta_peers2 if p.get("connected")]
            # Assertion 7: Beta v2 has a connected peer
            assert connected_beta_peers2, "GR3: Beta v2 should have a connected peer"
            beta_peer_id2 = connected_beta_peers2[0]["id"]

            resp_new, _ = _send_msg(beta_http, beta_peer_id2, "post_reconnect_msg")
            # Assertion 8: post-reconnect send succeeds
            assert resp_new.get("ok"), \
                f"GR3: post-reconnect Beta→Alpha v2 send should succeed; got {resp_new}"
            assert resp_new.get("message_id"), \
                "GR3: post-reconnect response must include message_id"

            # Assertion 9: /recv accessible after reconnect
            recv_resp, recv_code = _http_get(f"http://127.0.0.1:{beta_http}/recv")
            assert recv_code == 200, \
                f"GR3: Beta /recv should return 200 after reconnect; got {recv_code}"
            assert "messages" in recv_resp, \
                f"GR3: /recv should include 'messages' key; got {recv_resp}"

            # Assertion 10: /offline-queue accessible after reconnect
            oq2, oq2_code = _http_get(f"http://127.0.0.1:{beta_http}/offline-queue")
            assert oq2_code == 200, \
                f"GR3: Beta /offline-queue should return 200 after reconnect; got {oq2_code}"

            # Assertion 11: Alpha v2 /status healthy
            st_alpha2, code_a2 = _http_get(f"http://127.0.0.1:{alpha_http}/status")
            assert code_a2 == 200, \
                f"GR3: Alpha v2 /status should return 200 after reconnect; got {code_a2}"
            assert "acp_version" in st_alpha2, \
                "GR3: Alpha v2 /status must include acp_version"

        finally:
            _kill_relay(beta_proc2)

    finally:
        _kill_relay(alpha_proc2)
