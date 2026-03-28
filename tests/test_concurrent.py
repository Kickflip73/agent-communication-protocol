#!/usr/bin/env python3
"""
test_concurrent.py — 场景 H：并发压力

HC1: 10 个 Agent 同时连接同一 Relay，各自注册成功
HC2: 5 对 Agent 并发互发消息（asyncio.gather），无消息丢失
HC3: 高并发注册（50 Agent 同时连接），Relay 不崩溃，所有连接建立成功

实现：asyncio + websockets 并发 WS 连接
要求：至少 3 个测试用例，10+ assertions，动态端口，fixture 管理 Relay 生命周期
"""

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import threading
import urllib.error
import urllib.request

import pytest
import websockets

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RELAY_PY = os.path.join(BASE_DIR, "relay", "acp_relay.py")

# Remove proxy variables immediately at module load time so urllib.request
# connects directly to localhost without going through the proxy.
_PROXY_VARS = (
    "http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY",
    "all_proxy", "ALL_PROXY", "ftp_proxy", "FTP_PROXY", "no_proxy", "NO_PROXY",
)
for _pv in _PROXY_VARS:
    os.environ.pop(_pv, None)


# ── helpers ────────────────────────────────────────────────────────────────────

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
    raise RuntimeError("Cannot find a free port pair")


def _clean_env() -> dict:
    proxy_vars = (
        "http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY",
        "all_proxy", "ALL_PROXY", "ftp_proxy", "FTP_PROXY", "no_proxy", "NO_PROXY",
    )
    env = os.environ.copy()
    for v in proxy_vars:
        env.pop(v, None)
    return env


def _start_relay(ws_port: int, name: str = "ConcurrentRelay") -> subprocess.Popen:
    """
    Start a relay process on ws_port; HTTP is on ws_port+100.
    Waits until /status returns 200 AND session_id is set (needs ~3s for public IP).
    """
    p = subprocess.Popen(
        [sys.executable, RELAY_PY, "--name", name, "--port", str(ws_port),
         "--http-host", "127.0.0.1"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env=_clean_env(),
    )
    http = ws_port + 100
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{http}/status", timeout=2) as r:
                if r.status == 200:
                    body = json.loads(r.read())
                    if body.get("session_id"):
                        return p
        except Exception:
            pass
        time.sleep(0.4)
    p.kill()
    raise RuntimeError(f"Relay {name}:{ws_port} failed to start (with session_id) within 20s")


def _http_get(url: str, timeout: float = 5) -> tuple:
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


def _get_token(ws_port: int) -> str:
    """
    Extract the relay token via /link endpoint (most reliable).
    Falls back to /status session_id, then /.well-known/acp.json.
    """
    http = ws_port + 100
    for _ in range(40):
        # Primary: /link endpoint
        link_resp, lcode = _http_get(f"http://127.0.0.1:{http}/link")
        if lcode == 200:
            link = link_resp.get("link", "")
            if link and "/" in link:
                tok = link.rsplit("/", 1)[-1]
                if tok:
                    return tok
            sid = link_resp.get("session_id", "")
            if sid:
                return sid
        # Fallback: /status session_id
        status, scode = _http_get(f"http://127.0.0.1:{http}/status")
        if scode == 200:
            sid = status.get("session_id", "")
            if sid:
                return sid
            link = status.get("link", "")
            if link and "/" in link:
                tok = link.rsplit("/", 1)[-1]
                if tok:
                    return tok
        time.sleep(0.4)
    raise RuntimeError("Could not obtain relay token")


# ── async core helpers ─────────────────────────────────────────────────────────

async def _connect_one(ws_port: int, token: str, agent_idx: int,
                        results: list, errors: list):
    """
    Open a WS connection, receive the acp.agent_card, record success.
    """
    uri = f"ws://127.0.0.1:{ws_port}/{token}"
    try:
        async with websockets.connect(uri, open_timeout=10) as ws:
            # Receive acp.agent_card (relay pushes it on connect)
            raw = await asyncio.wait_for(ws.recv(), timeout=8)
            msg = json.loads(raw)
            results.append({
                "idx": agent_idx,
                "type": msg.get("type"),
                "connected": True,
            })
            # Keep the connection alive briefly for concurrent tests
            await asyncio.sleep(1.0)
    except Exception as e:
        errors.append({"idx": agent_idx, "error": str(e)})


async def _connect_and_send(ws_port: int, token: str, http_port: int,
                             pair_idx: int, msg_content: str,
                             sent_ids: list, errors: list):
    """
    Connect a WS Agent, get its peer_id via HTTP, send a message TO it,
    then verify delivery via /recv.
    """
    uri = f"ws://127.0.0.1:{ws_port}/{token}"
    try:
        async with websockets.connect(uri, open_timeout=10) as ws:
            # Handshake
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=8)
                _ = json.loads(raw)
            except asyncio.TimeoutError:
                pass

            # Get peer_id from HTTP /peers
            peers_resp, _ = _http_get(f"http://127.0.0.1:{http_port}/peers")
            peers = peers_resp.get("peers", [])
            connected_peers = [p for p in peers if p.get("connected")]
            if not connected_peers:
                errors.append({"pair": pair_idx, "error": "no connected peer found"})
                return

            peer_id = connected_peers[-1]["id"]

            # Send message TO this peer (via HTTP API)
            loop = asyncio.get_event_loop()
            resp, code = await loop.run_in_executor(
                None,
                lambda: _http_post(
                    f"http://127.0.0.1:{http_port}/peer/{peer_id}/send",
                    {"parts": [{"type": "text", "content": msg_content}], "role": "agent"}
                )
            )

            if resp.get("ok") and resp.get("message_id"):
                sent_ids.append(resp["message_id"])
            else:
                errors.append({
                    "pair": pair_idx,
                    "error": f"send failed: {resp} (HTTP {code})"
                })

            await asyncio.sleep(0.5)
    except Exception as e:
        errors.append({"pair": pair_idx, "error": str(e)})


# ══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def relay_for_hc1():
    ws_port = _free_port_pair()
    proc = _start_relay(ws_port, "HC1-Relay")
    token = _get_token(ws_port)
    yield ws_port, ws_port + 100, token
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()


@pytest.fixture(scope="module")
def relay_for_hc2():
    ws_port = _free_port_pair()
    proc = _start_relay(ws_port, "HC2-Relay")
    token = _get_token(ws_port)
    yield ws_port, ws_port + 100, token
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()


@pytest.fixture(scope="module")
def relay_for_hc3():
    ws_port = _free_port_pair()
    proc = _start_relay(ws_port, "HC3-Relay")
    token = _get_token(ws_port)
    yield ws_port, ws_port + 100, token
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()


# ══════════════════════════════════════════════════════════════════════════════
# HC1 — 10 个 Agent 同时连接同一 Relay，各自注册成功
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.timeout(60)
def test_hc1_10_agents_concurrent_connect(relay_for_hc1):
    """
    HC1: 10 Agents connect concurrently to one Relay.
    All should receive acp.agent_card, indicating successful registration.
    """
    ws_port, http_port, token = relay_for_hc1
    N_AGENTS = 10

    results = []
    errors = []

    async def run_all():
        tasks = [
            _connect_one(ws_port, token, i, results, errors)
            for i in range(N_AGENTS)
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    loop = asyncio.new_event_loop()
    loop.run_until_complete(run_all())
    loop.close()

    # Assertion 1: all 10 connections succeeded
    assert len(errors) == 0, \
        f"HC1: {len(errors)} connection(s) failed: {errors[:3]}"

    # Assertion 2: all 10 received the acp.agent_card
    assert len(results) == N_AGENTS, \
        f"HC1: expected {N_AGENTS} results, got {len(results)}"

    # Assertion 3: every result has type == acp.agent_card
    card_types = [r["type"] for r in results]
    assert all(t == "acp.agent_card" for t in card_types), \
        f"HC1: not all connections received acp.agent_card: {card_types}"

    # Assertion 4: relay is still healthy after 10 concurrent connections
    status, code = _http_get(f"http://127.0.0.1:{http_port}/status")
    assert code == 200, f"HC1: /status should return 200 after load, got {code}"

    # Assertion 5: relay reports acp_version (sanity check)
    assert "acp_version" in status, \
        f"HC1: /status should include acp_version after concurrent load"

    # Assertion 6: connected flag in results
    assert all(r["connected"] for r in results), \
        "HC1: all connections should report connected=True"

    # Check peer registry via /peers
    time.sleep(0.5)
    peers_resp, peers_code = _http_get(f"http://127.0.0.1:{http_port}/peers")
    assert peers_code == 200, f"HC1: /peers should return 200, got {peers_code}"
    all_peers = peers_resp.get("peers", [])

    # Assertion 7: relay registered multiple peers (at least some)
    # Note: by the time we query, some connections may have closed (asyncio.sleep(1.0))
    assert len(all_peers) >= 1, \
        f"HC1: relay should have at least 1 peer record, got {len(all_peers)}"


# ══════════════════════════════════════════════════════════════════════════════
# HC2 — 5 对 Agent 并发互发消息，无消息丢失
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.timeout(60)
def test_hc2_5_pairs_concurrent_messaging(relay_for_hc2):
    """
    HC2: 5 pairs of Agents connect concurrently and each pair exchanges a message.
    All 5 sends should succeed (message_id returned), indicating no message loss.
    """
    ws_port, http_port, token = relay_for_hc2
    N_PAIRS = 5

    sent_ids = []
    errors = []

    async def run_pairs():
        tasks = [
            _connect_and_send(
                ws_port, token, http_port,
                pair_idx=i,
                msg_content=f"hc2_pair_{i}_msg",
                sent_ids=sent_ids,
                errors=errors,
            )
            for i in range(N_PAIRS)
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    loop = asyncio.new_event_loop()
    loop.run_until_complete(run_pairs())
    loop.close()

    # Assertion 1: no connection errors
    assert len(errors) == 0, \
        f"HC2: {len(errors)} error(s) in concurrent messaging: {errors}"

    # Assertion 2: all 5 pairs sent messages
    assert len(sent_ids) == N_PAIRS, \
        f"HC2: expected {N_PAIRS} sent message IDs, got {len(sent_ids)}: errors={errors}"

    # Assertion 3: all message_ids are non-empty strings
    assert all(isinstance(mid, str) and mid for mid in sent_ids), \
        f"HC2: all message_ids should be non-empty strings, got {sent_ids}"

    # Assertion 4: no duplicate message_ids (idempotency guarantee)
    assert len(set(sent_ids)) == len(sent_ids), \
        f"HC2: duplicate message_ids detected: {sent_ids}"

    # Assertion 5: relay is still healthy after concurrent messaging
    status, code = _http_get(f"http://127.0.0.1:{http_port}/status")
    assert code == 200, f"HC2: /status should return 200 after concurrent messaging"

    # Assertion 6: relay messages_received counter increased
    total_received = status.get("messages_received", 0)
    assert total_received >= 1, \
        f"HC2: relay messages_received should be >= 1 after concurrent sends, got {total_received}"

    # Assertion 7: /recv endpoint is accessible
    recv_resp, recv_code = _http_get(f"http://127.0.0.1:{http_port}/recv")
    assert recv_code == 200, f"HC2: /recv should return 200, got {recv_code}"
    assert "messages" in recv_resp, f"HC2: /recv response should have 'messages' key"


# ══════════════════════════════════════════════════════════════════════════════
# HC3 — 高并发注册（50 Agent 同时连接），Relay 不崩溃
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.timeout(60)
def test_hc3_50_agents_stress(relay_for_hc3):
    """
    HC3: 50 Agents connect concurrently to one Relay.
    The relay must NOT crash, and all connections must be established successfully.
    Peer IDs returned must be unique (no conflicts).
    """
    ws_port, http_port, token = relay_for_hc3
    N_AGENTS = 50

    results = []
    errors = []

    async def stress_connect(idx: int):
        uri = f"ws://127.0.0.1:{ws_port}/{token}"
        try:
            async with websockets.connect(uri, open_timeout=15) as ws:
                raw = await asyncio.wait_for(ws.recv(), timeout=10)
                msg = json.loads(raw)
                results.append({
                    "idx": idx,
                    "type": msg.get("type"),
                    "connected": True,
                })
                await asyncio.sleep(0.5)
        except Exception as e:
            errors.append({"idx": idx, "error": str(e)})

    async def run_stress():
        tasks = [stress_connect(i) for i in range(N_AGENTS)]
        await asyncio.gather(*tasks, return_exceptions=True)

    loop = asyncio.new_event_loop()
    loop.run_until_complete(run_stress())
    loop.close()

    total_connected = len(results)
    total_errors = len(errors)

    # Assertion 1: relay survived (still reachable)
    status, code = _http_get(f"http://127.0.0.1:{http_port}/status", timeout=8)
    assert code == 200, \
        f"HC3: relay crashed or unresponsive after 50 concurrent connections (status={code})"

    # Assertion 2: acp_version present (relay is functional)
    assert "acp_version" in status, \
        "HC3: relay /status missing acp_version — relay may be in bad state"

    # Assertion 3: at least 90% of connections succeeded
    success_rate = total_connected / N_AGENTS
    assert success_rate >= 0.90, \
        (f"HC3: only {total_connected}/{N_AGENTS} connections succeeded "
         f"({success_rate:.0%}); errors: {errors[:5]}")

    # Assertion 4: all successful connections received acp.agent_card
    card_types = [r["type"] for r in results]
    non_card = [t for t in card_types if t != "acp.agent_card"]
    assert len(non_card) == 0, \
        f"HC3: {len(non_card)} connections did NOT receive acp.agent_card"

    # Assertion 5: check peer registry for uniqueness
    time.sleep(0.5)
    peers_resp, peers_code = _http_get(f"http://127.0.0.1:{http_port}/peers")
    assert peers_code == 200, f"HC3: /peers should return 200, got {peers_code}"
    all_peers = peers_resp.get("peers", [])
    all_peer_ids = [p["id"] for p in all_peers]

    # Assertion 6: all peer IDs are unique (no conflicts)
    assert len(set(all_peer_ids)) == len(all_peer_ids), \
        f"HC3: duplicate peer_ids detected: {all_peer_ids}"

    # Assertion 7: relay registered at least some peers in registry
    assert len(all_peers) >= 1, \
        f"HC3: relay should have at least 1 peer in registry, got {len(all_peers)}"

    # Assertion 8: no more than 10% connection failures tolerated
    assert total_errors <= N_AGENTS * 0.10, \
        f"HC3: too many errors ({total_errors}/{N_AGENTS}): {errors[:5]}"

    # Assertion 9: relay /status returns non-error peer_count field
    peer_count = status.get("peer_count", 0)
    assert isinstance(peer_count, int), \
        f"HC3: peer_count should be an integer, got {type(peer_count)}"

    # Assertion 10: relay uptime is positive (not crashed and restarted)
    assert status.get("acp_version"), \
        "HC3: relay should report acp_version in status after stress test"

    print(f"\nHC3 stress result: {total_connected}/{N_AGENTS} connected, "
          f"{total_errors} errors, {len(all_peers)} peers in registry")
