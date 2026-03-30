#!/usr/bin/env python3
"""
tests/test_nat_integration.py — v2.19.0 NAT Auto-Traversal Integration Tests

Tests that /peers/connect auto-selects the correct NAT traversal strategy
and that GET /status returns connection_type.

Note: HTTP port = WS port + 100 (no --http-port flag in acp_relay.py).

Test matrix:
  NI1  GET /status includes connection_type field (None before any connect)
  NI2  connection_type is set after /peers/connect (any valid value)
  NI3  connection_type = "relay" for force_relay path (module-level unit test)
  NI4  _broadcast_sse_event appends dcutr_started to _sse_subscribers
  NI5  relay_fallback SSE event payload contains 'reason' field
  NI6  /peers/connect response has ok=True and peer_id/token field

Goal: 6/6 PASS
"""

import sys
import os
import json
import time
import signal
import socket
import subprocess
import threading
import urllib.request

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "relay"))

RELAY_PY = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _free_ws_port() -> int:
    """Return a free WS port where WS port + 100 is also free."""
    for _ in range(30):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            p = s.getsockname()[1]
        if p < 65000:
            try:
                with socket.socket() as s2:
                    s2.bind(("127.0.0.1", p + 100))
                return p
            except OSError:
                continue
    raise RuntimeError("Could not find a free WS+HTTP port pair")


def _clean_env() -> dict:
    env = os.environ.copy()
    for v in ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY",
              "all_proxy", "ALL_PROXY", "no_proxy", "NO_PROXY"):
        env.pop(v, None)
    return env


def _start_relay(ws_port: int, name: str = "TestRelay",
                 extra_args: list = None) -> subprocess.Popen:
    """Start relay subprocess; HTTP port = ws_port + 100."""
    cmd = [
        sys.executable, RELAY_PY,
        "--name", name,
        "--port", str(ws_port),
        "--http-host", "127.0.0.1",
    ]
    if extra_args:
        cmd.extend(extra_args)
    return subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_clean_env(),
        preexec_fn=os.setpgrp,
    )


def _kill_relay(proc: subprocess.Popen, timeout: float = 8.0):
    """Terminate relay gracefully; SIGKILL if needed."""
    try:
        proc.terminate()
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
            proc.wait(timeout=3)
        except Exception:
            pass
    except Exception:
        pass


def _wait_ready(ws_port: int, timeout: float = 18.0) -> bool:
    """Wait for relay HTTP port (ws_port + 100) to become responsive."""
    hp = ws_port + 100
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = urllib.request.urlopen(
                f"http://127.0.0.1:{hp}/status", timeout=2
            )
            if resp.status == 200:
                return True
        except Exception:
            pass
        time.sleep(0.4)
    return False


def _wait_link_ready(ws_port: int, timeout: float = 25.0) -> str | None:
    """Wait until /link returns a non-null link (relay session established)."""
    hp = ws_port + 100
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{hp}/link", timeout=3
            ) as r:
                d = json.loads(r.read())
                lnk = d.get("link")
                if lnk and lnk.startswith("acp://"):
                    return lnk
        except Exception:
            pass
        time.sleep(0.5)
    return None


def _get_status(ws_port: int) -> dict:
    hp = ws_port + 100
    with urllib.request.urlopen(
        f"http://127.0.0.1:{hp}/status", timeout=5
    ) as r:
        return json.loads(r.read())


def _post_json(url: str, body: dict, timeout: float = 20.0) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


# ── Load relay module for unit tests (NI3/NI4/NI5) ──────────────────────────
import importlib.util as _ilu

def _load_relay_module(alias: str):
    """Load acp_relay as a fresh module under the given alias."""
    spec = _ilu.spec_from_file_location(alias, RELAY_PY)
    mod = _ilu.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except SystemExit:
        pass
    return mod


# ══════════════════════════════════════════════════════════════════════════════
# NI1 — GET /status includes connection_type field (None before connect)
# ══════════════════════════════════════════════════════════════════════════════

def test_ni1_status_connection_type():
    """NI1: GET /status includes connection_type field (None before any connect)."""
    wp = _free_ws_port()
    proc = _start_relay(wp, "NI1-Relay")
    try:
        assert _wait_ready(wp, 18), (
            f"Relay did not start on ws={wp} / http={wp+100}"
        )
        status = _get_status(wp)
        assert "connection_type" in status, (
            f"GET /status missing 'connection_type'. Keys: {list(status.keys())}"
        )
        ct = status["connection_type"]
        assert ct is None or ct in ("p2p_direct", "dcutr_direct", "relay"), (
            f"Unexpected connection_type before connect: {ct!r}"
        )
    finally:
        _kill_relay(proc)


# ══════════════════════════════════════════════════════════════════════════════
# NI2 — connection_type is set after /peers/connect
# ══════════════════════════════════════════════════════════════════════════════

def test_ni2_connection_type_set_after_connect():
    """NI2: After /peers/connect, connection_type is a valid transport string."""
    h_wp = _free_ws_port()
    g_wp = _free_ws_port()

    host_proc  = _start_relay(h_wp, "NI2-Host")
    guest_proc = _start_relay(g_wp, "NI2-Guest")
    try:
        # Wait for both relay sessions to be fully established
        host_link = _wait_link_ready(h_wp, 30)
        if not host_link:
            pytest.skip(
                "Host relay link not available (sandbox relay concurrency limit "
                "or external relay service unreachable) — skipping NI2"
            )
        guest_ready = _wait_ready(g_wp, 20)
        if not guest_ready:
            pytest.skip("Guest relay not ready in time — skipping NI2")

        # Guest connects to host
        g_hp = g_wp + 100
        result = _post_json(
            f"http://127.0.0.1:{g_hp}/peers/connect",
            {"link": host_link},
            timeout=20,
        )
        assert result.get("ok"), f"/peers/connect failed: {result}"

        # Poll until connection_type is set
        deadline = time.time() + 15
        ct = None
        while time.time() < deadline:
            try:
                st = _get_status(g_wp)
                ct = st.get("connection_type")
                if ct in ("p2p_direct", "dcutr_direct", "relay"):
                    break
            except Exception:
                pass
            time.sleep(0.5)

        assert ct in ("p2p_direct", "dcutr_direct", "relay"), (
            f"connection_type not set after connect; got {ct!r}"
        )
    finally:
        _kill_relay(host_proc)
        _kill_relay(guest_proc)


# ══════════════════════════════════════════════════════════════════════════════
# NI3 — force_relay path sets transport = "relay" (unit test)
# ══════════════════════════════════════════════════════════════════════════════

def test_ni3_connection_type_relay_unit():
    """NI3: When force_relay=True, _connect_with_nat_traversal returns 'relay' transport."""
    import asyncio
    from unittest.mock import patch

    mod = _load_relay_module("_relay_ni3_" + str(int(time.time())))

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    mod._status["http_port"]       = 7901
    mod._status["force_relay"]     = True
    mod._status["relay_base_url"]  = "https://mock-relay.example"
    mod._status["connection_type"] = None

    token = "tok_ni3test"
    link  = f"acp://127.0.0.1:17801/{token}"

    relay_calls = []

    async def _mock_relay_guest(base, tok, hp):
        relay_calls.append(tok)

    async def _run():
        with patch.object(mod, "_http_relay_guest", _mock_relay_guest):
            return await mod._connect_with_nat_traversal(link, "NI3", "guest")

    try:
        result = loop.run_until_complete(_run())
    finally:
        loop.close()

    assert result[1] == "relay", (
        f"Expected transport='relay' with force_relay=True, got {result[1]!r}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# NI4 — _broadcast_sse_event appends dcutr_started to _sse_subscribers
# ══════════════════════════════════════════════════════════════════════════════

def test_ni4_sse_dcutr_started():
    """NI4: _broadcast_sse_event delivers dcutr_started to _sse_subscribers."""
    mod = _load_relay_module("_relay_ni4_" + str(int(time.time())))

    # _sse_subscribers is a plain list at module level (line ~306 in relay)
    assert hasattr(mod, "_sse_subscribers"), (
        "acp_relay._sse_subscribers not defined — check module globals"
    )

    received = []

    class _MockQueue:
        def append(self, item):
            received.append(item)

    mock_q = _MockQueue()
    mod._sse_subscribers.append(mock_q)
    try:
        mod._broadcast_sse_event("peer", {"event": "dcutr_started"})
        mod._broadcast_sse_event("peer", {"event": "relay_fallback", "reason": "l1_l2_failed"})
    finally:
        mod._sse_subscribers.remove(mock_q)

    assert len(received) >= 2, (
        f"Expected ≥2 SSE events, got {len(received)}: {received}"
    )
    events_text = json.dumps(received)
    assert "dcutr_started" in events_text, (
        f"dcutr_started not found in SSE events"
    )
    assert "relay_fallback" in events_text, (
        f"relay_fallback not found in SSE events"
    )


# ══════════════════════════════════════════════════════════════════════════════
# NI5 — relay_fallback event contains 'reason' field
# ══════════════════════════════════════════════════════════════════════════════

def test_ni5_relay_fallback_reason():
    """NI5: relay_fallback event includes 'reason' field."""
    mod = _load_relay_module("_relay_ni5_" + str(int(time.time())))

    assert hasattr(mod, "_sse_subscribers"), (
        "acp_relay._sse_subscribers not defined"
    )

    received = []

    class _MockQueue:
        def append(self, item):
            received.append(item)

    mock_q = _MockQueue()
    mod._sse_subscribers.append(mock_q)
    try:
        mod._broadcast_sse_event("peer", {
            "event": "relay_fallback",
            "reason": "l1_l2_failed",
        })
    finally:
        mod._sse_subscribers.remove(mock_q)

    assert len(received) == 1, (
        f"Expected 1 SSE event, got {len(received)}"
    )
    payload = received[0]
    assert isinstance(payload, dict), f"Expected dict payload, got {type(payload)}"
    assert payload.get("event") == "relay_fallback", (
        f"Expected event=relay_fallback, got {payload.get('event')!r}"
    )
    assert "reason" in payload, (
        f"Missing 'reason' field in relay_fallback payload: {payload}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# NI6 — /peers/connect response has ok=True and peer identity field
# ══════════════════════════════════════════════════════════════════════════════

def test_ni6_peers_connect_response_structure():
    """NI6: /peers/connect response has ok=True and peer identity field."""
    h_wp = _free_ws_port()
    g_wp = _free_ws_port()

    host_proc  = _start_relay(h_wp, "NI6-Host")
    guest_proc = _start_relay(g_wp, "NI6-Guest")
    try:
        host_link = _wait_link_ready(h_wp, 30)
        if not host_link:
            pytest.skip(
                "Host relay link unavailable (sandbox relay limit) — skipping NI6"
            )
        if not _wait_ready(g_wp, 20):
            pytest.skip("Guest relay not ready — skipping NI6")

        g_hp = g_wp + 100
        result = _post_json(
            f"http://127.0.0.1:{g_hp}/peers/connect",
            {"link": host_link},
            timeout=20,
        )
        assert result.get("ok") is True, (
            f"/peers/connect should return ok=True; got {result}"
        )
        has_identity = (
            "peer_id" in result or "id" in result or
            "token" in result or "session_id" in result
        )
        assert has_identity, (
            f"/peers/connect response missing peer identity field: {result}"
        )
    finally:
        _kill_relay(host_proc)
        _kill_relay(guest_proc)


# ── Script entry point ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import pytest as _pytest
    sys.exit(_pytest.main([__file__, "-v"]))
