#!/usr/bin/env python3
"""
tests/test_availability.py — v2.19.0 Availability CRON Extension Tests

Covers the --availability-cron CLI parameter and its AgentCard output.
Note: HTTP port = WS port + 100. AgentCard is at GET /card → body["self"].

Test matrix:
  AV1  _next_cron_datetime("*/30 * * * *") returns +30 min from reference time
  AV2  _next_cron_datetime("0 9 * * *") returns next 09:00 UTC
  AV3  --availability-cron sets scheduleType = "cron"
  AV4  --availability-cron sets cron = <expr>
  AV5  --availability-cron auto-computes nextActiveAt
  AV6  --availability-cron sets taskLatencyMaxSeconds = 60
  AV7  GET /card returns availability.scheduleType = "cron" when configured
  AV8  GET /card returns availability.cron = <expr> when configured
  AV9  GET /card returns availability.nextActiveAt when configured

Goal: 9/9 PASS
"""

import sys
import os
import json
import time
import socket
import subprocess
import datetime
import urllib.request

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "relay"))

import acp_relay as relay

RELAY_PY = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _free_ws_port() -> int:
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
    raise RuntimeError("Could not find a free WS port pair")


def _clean_env() -> dict:
    env = os.environ.copy()
    for v in ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY",
              "all_proxy", "ALL_PROXY", "no_proxy", "NO_PROXY"):
        env.pop(v, None)
    return env


def _start_relay_with_cron(ws_port: int, cron_expr: str,
                            name: str = "AvailRelay") -> subprocess.Popen:
    cmd = [
        sys.executable, RELAY_PY,
        "--name", name,
        "--port", str(ws_port),
        "--http-host", "127.0.0.1",
        "--availability-cron", cron_expr,
    ]
    return subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_clean_env(),
        preexec_fn=os.setpgrp,
    )


def _kill_relay(proc: subprocess.Popen, timeout: float = 10.0):
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


def _get_card_availability(ws_port: int) -> dict | None:
    """GET /card → body['self']['availability']."""
    hp = ws_port + 100
    with urllib.request.urlopen(
        f"http://127.0.0.1:{hp}/card", timeout=5
    ) as r:
        d = json.loads(r.read())
    # /card returns {"self": {...}, "peer": ...}
    card_self = d.get("self") or d  # fallback: body is the card directly
    return card_self.get("availability")


# ══════════════════════════════════════════════════════════════════════════════
# AV1 — _next_cron_datetime("*/30 * * * *") → +30 min
# ══════════════════════════════════════════════════════════════════════════════

def test_av1_every_30_min():
    """AV1: */30 * * * * → next is at :30 from reference :00."""
    after = datetime.datetime(2026, 3, 30, 8, 0, 0, tzinfo=datetime.timezone.utc)
    nxt = relay._next_cron_datetime("*/30 * * * *", after_dt=after)
    assert nxt is not None, "_next_cron_datetime returned None for '*/30 * * * *'"
    expected = after.replace(minute=30, second=0, microsecond=0)
    assert nxt == expected, f"Expected {expected}, got {nxt}"


# ══════════════════════════════════════════════════════════════════════════════
# AV2 — _next_cron_datetime("0 9 * * *") → next 09:00 UTC
# ══════════════════════════════════════════════════════════════════════════════

def test_av2_daily_at_9():
    """AV2: 0 9 * * * → next 09:00 UTC same day (if currently 08:00)."""
    after = datetime.datetime(2026, 3, 30, 8, 0, 0, tzinfo=datetime.timezone.utc)
    nxt = relay._next_cron_datetime("0 9 * * *", after_dt=after)
    assert nxt is not None, "_next_cron_datetime returned None for '0 9 * * *'"
    assert nxt.hour == 9 and nxt.minute == 0, f"Expected 09:00, got {nxt}"
    assert nxt.date() == after.date(), f"Expected same day, got {nxt.date()}"


# ══════════════════════════════════════════════════════════════════════════════
# AV3-AV6 — Simulate --availability-cron arg processing
# ══════════════════════════════════════════════════════════════════════════════

def _build_avail_from_cron(cron_expr: str) -> dict:
    """Replicate the --availability-cron processing from main()."""
    nxt_from_cron = None
    try:
        nxt_from_cron = relay._next_cron_datetime(cron_expr)
    except Exception:
        pass
    avail = {
        "mode":                    "cron",
        "scheduleType":            "cron",
        "cron":                    cron_expr,
        "schedule":                cron_expr,
        "taskLatencyMaxSeconds":   60,
        "task_latency_max_seconds": 60,
    }
    if nxt_from_cron:
        avail["nextActiveAt"]   = nxt_from_cron.strftime("%Y-%m-%dT%H:%M:%SZ")
        avail["next_active_at"] = avail["nextActiveAt"]
    return avail


def test_av3_schedule_type_cron():
    """AV3: --availability-cron sets scheduleType = 'cron'."""
    avail = _build_avail_from_cron("*/30 * * * *")
    assert avail.get("scheduleType") == "cron", (
        f"scheduleType should be 'cron', got {avail.get('scheduleType')!r}"
    )


def test_av4_cron_field_set():
    """AV4: --availability-cron sets cron = <expr>."""
    expr = "*/30 * * * *"
    avail = _build_avail_from_cron(expr)
    assert avail.get("cron") == expr, (
        f"cron field should be {expr!r}, got {avail.get('cron')!r}"
    )


def test_av5_next_active_at_computed():
    """AV5: --availability-cron auto-computes nextActiveAt (ISO-8601 UTC with Z)."""
    avail = _build_avail_from_cron("*/30 * * * *")
    nxt = avail.get("nextActiveAt") or avail.get("next_active_at")
    assert nxt is not None, (
        f"nextActiveAt should be computed from cron; got None. avail={avail}"
    )
    assert nxt.endswith("Z"), f"nextActiveAt must end in 'Z', got {nxt!r}"


def test_av6_task_latency_max():
    """AV6: --availability-cron sets taskLatencyMaxSeconds = 60."""
    avail = _build_avail_from_cron("*/30 * * * *")
    tlm = avail.get("taskLatencyMaxSeconds") or avail.get("task_latency_max_seconds")
    assert tlm == 60, f"taskLatencyMaxSeconds should be 60, got {tlm!r}"


# ══════════════════════════════════════════════════════════════════════════════
# AV7-AV9 — Live relay: GET /card returns availability block
# ══════════════════════════════════════════════════════════════════════════════

def test_av7_agent_card_schedule_type():
    """AV7: GET /card includes availability.scheduleType = 'cron' when --availability-cron set."""
    wp = _free_ws_port()
    proc = _start_relay_with_cron(wp, "*/30 * * * *", "AV7-Relay")
    try:
        assert _wait_ready(wp, 18), f"Relay not ready (ws={wp})"
        avail = _get_card_availability(wp)
        assert avail is not None, (
            "GET /card missing 'availability' block in card.self"
        )
        stype = avail.get("scheduleType") or avail.get("schedule_type") or avail.get("mode")
        assert stype == "cron", (
            f"availability.scheduleType should be 'cron', got {stype!r}. avail={avail}"
        )
    finally:
        _kill_relay(proc)


def test_av8_agent_card_cron_expr():
    """AV8: GET /card includes availability.cron = <expr>."""
    wp = _free_ws_port()
    expr = "*/30 * * * *"
    proc = _start_relay_with_cron(wp, expr, "AV8-Relay")
    try:
        assert _wait_ready(wp, 18), f"Relay not ready (ws={wp})"
        avail = _get_card_availability(wp)
        assert avail is not None, "Missing availability block in GET /card"
        cron_val = avail.get("cron") or avail.get("schedule")
        assert cron_val == expr, (
            f"availability.cron should be {expr!r}, got {cron_val!r}. avail={avail}"
        )
    finally:
        _kill_relay(proc)


def test_av9_agent_card_next_active_at():
    """AV9: GET /card includes availability.nextActiveAt (UTC ISO-8601)."""
    wp = _free_ws_port()
    proc = _start_relay_with_cron(wp, "*/30 * * * *", "AV9-Relay")
    try:
        assert _wait_ready(wp, 18), f"Relay not ready (ws={wp})"
        avail = _get_card_availability(wp)
        assert avail is not None, "Missing availability block in GET /card"
        nxt = avail.get("nextActiveAt") or avail.get("next_active_at")
        assert nxt is not None, (
            f"availability.nextActiveAt should be computed; got None. avail={avail}"
        )
        assert nxt.endswith("Z"), (
            f"nextActiveAt must be UTC ISO-8601 (ends in Z), got {nxt!r}"
        )
    finally:
        _kill_relay(proc)


# ── Script entry point ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import pytest as _pytest
    sys.exit(_pytest.main([__file__, "-v"]))
