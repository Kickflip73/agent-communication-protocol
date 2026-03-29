"""
test_availability_schedule.py — v2.17 availability_schedule tests

AS1  _parse_cron_field: wildcard, step, range, list
AS2  _next_cron_datetime: every-minute cron returns result 1 min in future
AS3  _next_cron_datetime: hourly cron (0 * * * *)
AS4  _next_cron_datetime: specific hour/min
AS5  _next_cron_datetime: invalid expression returns None
AS6  AgentCard: availability_schedule capability = False when no schedule
AS7  AgentCard: availability_schedule capability = True when schedule set
AS8  AgentCard: next_active_at auto-computed when schedule set and not explicit
AS9  AgentCard: next_active_at not overwritten when explicitly set
AS10 GET /availability: returns ok, mode, has_schedule when no availability configured
AS11 GET /availability: returns schedule + next_active_at when configured
AS12 POST /availability/heartbeat: stamps last_active_at, recomputes next_active_at
AS13 POST /availability/heartbeat: accepts body to update schedule
AS14 PATCH /.well-known/acp.json: accepts schedule + timezone fields
AS15 _parse_cron_field: day-of-week 0-6
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'relay'))

import datetime
import importlib
import types
import pytest
import json
import urllib.request
import subprocess
import time


# ── Import helpers directly ──────────────────────────────────────────────────

import acp_relay as _relay
from acp_relay import (
    _parse_cron_field,
    _next_cron_datetime,
    _availability_with_schedule,
)


# ── Unit tests ───────────────────────────────────────────────────────────────

class TestParseCronField:
    def test_AS1_wildcard(self):
        assert _parse_cron_field("*", 0, 5) == [0, 1, 2, 3, 4, 5]

    def test_AS1b_step(self):
        assert _parse_cron_field("*/15", 0, 59) == [0, 15, 30, 45]

    def test_AS1c_range(self):
        assert _parse_cron_field("1-3", 0, 5) == [1, 2, 3]

    def test_AS1d_list(self):
        assert _parse_cron_field("0,15,30,45", 0, 59) == [0, 15, 30, 45]

    def test_AS15_dow(self):
        result = _parse_cron_field("1-5", 0, 6)
        assert result == [1, 2, 3, 4, 5]  # Mon-Fri


class TestNextCronDatetime:
    def _utc(self, **kwargs):
        return datetime.datetime.now(datetime.timezone.utc).replace(**kwargs)

    def test_AS2_every_minute(self):
        """* * * * * — next should be exactly 1 minute from now"""
        after = datetime.datetime(2026, 3, 30, 2, 0, 0, tzinfo=datetime.timezone.utc)
        nxt = _next_cron_datetime("* * * * *", after_dt=after)
        assert nxt is not None
        assert nxt == after.replace(minute=1, second=0, microsecond=0)

    def test_AS3_hourly(self):
        """0 * * * * — top of next hour"""
        after = datetime.datetime(2026, 3, 30, 2, 15, 0, tzinfo=datetime.timezone.utc)
        nxt = _next_cron_datetime("0 * * * *", after_dt=after)
        assert nxt is not None
        assert nxt.minute == 0
        assert nxt.hour == 3

    def test_AS4_specific_hour_min(self):
        """0 8 * * * — next 08:00"""
        after = datetime.datetime(2026, 3, 30, 2, 0, 0, tzinfo=datetime.timezone.utc)
        nxt = _next_cron_datetime("0 8 * * *", after_dt=after)
        assert nxt is not None
        assert nxt.hour == 8 and nxt.minute == 0
        assert nxt.day == 30

    def test_AS4b_specific_past_today(self):
        """0 1 * * * — already past today (02:00), next is tomorrow 01:00"""
        after = datetime.datetime(2026, 3, 30, 2, 0, 0, tzinfo=datetime.timezone.utc)
        nxt = _next_cron_datetime("0 1 * * *", after_dt=after)
        assert nxt is not None
        assert nxt.hour == 1 and nxt.minute == 0
        assert nxt.day == 31  # next day

    def test_AS5_invalid_expression(self):
        """Invalid cron — should return None"""
        assert _next_cron_datetime("not-a-cron") is None
        assert _next_cron_datetime("* * * *") is None   # only 4 fields
        assert _next_cron_datetime("") is None


class TestAvailabilityWithSchedule:
    def test_AS8_auto_next_active_at(self):
        """schedule set, no next_active_at → auto-compute"""
        avail = {"mode": "cron", "schedule": "0 8 * * *"}
        result = _availability_with_schedule(avail)
        assert "next_active_at" in result
        assert result["next_active_at"].endswith("Z")

    def test_AS9_no_overwrite(self):
        """next_active_at already set → not overwritten"""
        avail = {"mode": "cron", "schedule": "0 8 * * *",
                 "next_active_at": "2026-04-01T08:00:00Z"}
        result = _availability_with_schedule(avail)
        assert result["next_active_at"] == "2026-04-01T08:00:00Z"

    def test_no_schedule(self):
        """no schedule → next_active_at unchanged (None)"""
        avail = {"mode": "persistent"}
        result = _availability_with_schedule(avail)
        assert "next_active_at" not in result


# ── HTTP integration tests ───────────────────────────────────────────────────

RELAY_BIN = os.path.join(os.path.dirname(__file__), '..', 'relay', 'acp_relay.py')
AS_WS = 8071
AS_HTTP = 8171


def start_relay_as(extra_env=None):
    env = {**os.environ}
    if extra_env:
        env.update(extra_env)
    return subprocess.Popen(
        [sys.executable, RELAY_BIN, "--name", "ASTest", "--port", str(AS_WS),
         "--http-host", "127.0.0.1"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env
    )


def wait_http(port, timeout=12):
    dl = time.time() + timeout
    while time.time() < dl:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/status", timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def http_get(port, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as r:
        data = json.loads(r.read())
        status = r.status
    # /.well-known/acp.json returns {"self": <AgentCard>, "peer": ...}
    # unwrap to AgentCard directly for convenience
    if isinstance(data, dict) and "self" in data and "peer" in data:
        data = data["self"]
    return data, status


def http_post(port, path, body=None):
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data,
        {"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read()), r.status


def http_patch(port, path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data,
        {"Content-Type": "application/json"}
    )
    req.get_method = lambda: "PATCH"
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read()), r.status


@pytest.fixture(scope="module")
def relay_as():
    proc = start_relay_as()
    assert wait_http(AS_HTTP), f"Relay HTTP {AS_HTTP} not ready"
    yield proc
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
        proc.wait(timeout=3)


class TestAvailabilityHTTP:
    def test_AS6_no_schedule_capability(self, relay_as):
        """AS6: availability_schedule=False when no schedule configured"""
        card, sc = http_get(AS_HTTP, "/.well-known/acp.json")
        assert sc == 200
        caps = card.get("capabilities", {})
        assert caps.get("availability_schedule") == False

    def test_AS10_get_availability_empty(self, relay_as):
        """AS10: GET /availability returns ok, mode=persistent, has_schedule=False"""
        d, sc = http_get(AS_HTTP, "/availability")
        assert sc == 200
        assert d.get("ok") is True
        assert d.get("mode") == "persistent"
        assert d.get("has_schedule") is False

    def test_AS14_patch_with_schedule(self, relay_as):
        """AS14: PATCH /.well-known/acp.json accepts schedule + timezone"""
        body = {"availability": {
            "mode": "cron",
            "schedule": "0 */4 * * *",
            "timezone": "UTC"
        }}
        d, sc = http_patch(AS_HTTP, "/.well-known/acp.json", body)
        assert sc == 200, f"PATCH failed: {d}"
        assert d.get("ok") is True

    def test_AS7_schedule_capability_true(self, relay_as):
        """AS7: availability_schedule=True after schedule configured"""
        card, sc = http_get(AS_HTTP, "/.well-known/acp.json")
        assert sc == 200
        caps = card.get("capabilities", {})
        assert caps.get("availability_schedule") is True

    def test_AS11_get_availability_with_schedule(self, relay_as):
        """AS11: GET /availability returns schedule + next_active_at"""
        d, sc = http_get(AS_HTTP, "/availability")
        assert sc == 200
        assert d.get("has_schedule") is True
        avail = d.get("availability", {})
        assert avail.get("schedule") == "0 */4 * * *"
        assert "next_active_at" in avail, f"next_active_at missing: {avail}"

    def test_AS8_agentcard_next_active_at(self, relay_as):
        """AS8: AgentCard.availability.next_active_at auto-computed from schedule"""
        card, sc = http_get(AS_HTTP, "/.well-known/acp.json")
        assert sc == 200
        avail = card.get("availability", {})
        assert "next_active_at" in avail, f"next_active_at missing from AgentCard: {avail}"
        assert avail["next_active_at"].endswith("Z")

    def test_AS12_heartbeat_stamp(self, relay_as):
        """AS12: POST /availability/heartbeat stamps last_active_at, recomputes next_active_at"""
        d, sc = http_post(AS_HTTP, "/availability/heartbeat")
        assert sc == 200
        assert d.get("ok") is True
        assert "last_active_at" in d
        assert "next_active_at" in d
        # next should be > last
        last = d["last_active_at"]
        nxt  = d["next_active_at"]
        assert nxt > last, f"next_active_at {nxt} should be after last_active_at {last}"

    def test_AS13_heartbeat_updates_schedule(self, relay_as):
        """AS13: POST /availability/heartbeat body can update schedule"""
        body = {"schedule": "*/30 * * * *"}
        d, sc = http_post(AS_HTTP, "/availability/heartbeat", body)
        assert sc == 200
        assert d.get("ok") is True
        avail = d.get("availability", {})
        assert avail.get("schedule") == "*/30 * * * *"
        # next_active_at should now be at a :00 or :30 boundary
        nxt = d.get("next_active_at", "")
        assert nxt.endswith("Z")


class TestAgentCardEndpoints:
    def test_endpoints_declared(self, relay_as):
        """AgentCard endpoints block includes availability + heartbeat"""
        card, sc = http_get(AS_HTTP, "/.well-known/acp.json")
        assert sc == 200
        endpoints = card.get("endpoints", {})
        assert endpoints.get("availability") == "/availability"
        assert endpoints.get("heartbeat") == "/availability/heartbeat"
