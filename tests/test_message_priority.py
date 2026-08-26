"""
ACP v2.38 — Message Priority tests (MP1–MP9)

POST /message:send supports optional 'priority' field: critical|high|normal|low
Default: normal. /recv returns messages sorted by priority (critical first).

Tests:
- MP1: capabilities.message_priority is True in agent_card
- MP2: /status includes priority_counts dict with all four levels
- MP3: POST /message:send with valid priority returns ok:True
- MP4: POST /message:send with invalid priority returns 400
- MP5: POST /message:send without priority defaults to normal
- MP6: message frame sent to peer contains priority field
- MP7: /recv returns messages sorted critical > high > normal > low
- MP8: priority_counts in /status increments per send
- MP9: all four valid priority values are accepted
"""

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

# ── helpers ───────────────────────────────────────────────────────────────────

RELAY_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")


def _free_port():
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _http(port, path, method="GET", body=None):
    url = f"http://127.0.0.1:{port}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read()), e.code
        except Exception:
            return {}, e.code


def _start_relay(ws_port, name, join=None, local_only=True):
    env = os.environ.copy()
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        env.pop(k, None)
    cmd = [sys.executable, RELAY_SCRIPT, "--port", str(ws_port), "--name", name]
    if join:
        cmd += ["--join", join]
    if local_only and not join:
        cmd += ["--local-only"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    for s in (proc.stdout, proc.stderr):
        threading.Thread(target=lambda x=s: x.read(), daemon=True).start()
    return proc


def _wait_for(fn, timeout=15, interval=0.4):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if fn():
            return True
        time.sleep(interval)
    return False


# ── module-scoped fixture: Alpha (standalone) + Beta (connected to Alpha) ─────

@pytest.fixture(scope="module")
def mp_pair():
    a_ws = _free_port()
    a_http = a_ws + 100
    b_ws = _free_port()
    b_http = b_ws + 100

    alpha = _start_relay(a_ws, "MP-Alpha")
    time.sleep(1)

    local_link = None
    for _ in range(30):
        data, code = _http(a_http, "/status")
        if code == 200 and data.get("link"):
            raw = data["link"]
            token = raw.split("/")[-1] if "/" in raw else None
            if token:
                local_link = f"acp://127.0.0.1:{a_ws}/{token}"
                break
        time.sleep(0.5)
    assert local_link, "Alpha never generated a link"

    beta = _start_relay(b_ws, "MP-Beta", join=local_link)
    time.sleep(2)

    ok = _wait_for(
        lambda: any(p.get("connected") for p in _http(a_http, "/peers")[0].get("peers", [])),
        timeout=15,
    )
    assert ok, "Alpha never saw Beta as connected"

    yield {"a_http": a_http, "a_ws": a_ws, "b_http": b_http, "b_ws": b_ws}

    alpha.terminate()
    beta.terminate()
    alpha.wait()
    beta.wait()


# ── MP1 ───────────────────────────────────────────────────────────────────────

def test_mp1_capability_declared(mp_pair):
    """MP1: capabilities.message_priority must be True in agent_card."""
    data, code = _http(mp_pair["a_http"], "/status")
    assert code == 200
    caps = (data.get("agent_card") or {}).get("capabilities", {})
    assert caps.get("message_priority") is True, (
        f"message_priority missing from capabilities: {caps}"
    )


# ── MP2 ───────────────────────────────────────────────────────────────────────

def test_mp2_status_has_priority_counts(mp_pair):
    """MP2: /status must include priority_counts with all four levels."""
    data, code = _http(mp_pair["a_http"], "/status")
    assert code == 200
    pc = data.get("priority_counts")
    assert isinstance(pc, dict), "priority_counts missing or not a dict"
    for level in ("critical", "high", "normal", "low"):
        assert level in pc, f"priority_counts missing level '{level}'"


# ── MP3 ───────────────────────────────────────────────────────────────────────

def test_mp3_send_with_valid_priority(mp_pair):
    """MP3: POST /message:send with priority='high' must return ok:True."""
    resp, code = _http(mp_pair["a_http"], "/message:send", method="POST", body={
        "text": "high priority message",
        "role": "agent",
        "priority": "high",
    })
    assert code == 200, f"Expected 200, got {code}: {resp}"
    assert resp.get("ok") is True


# ── MP4 ───────────────────────────────────────────────────────────────────────

def test_mp4_invalid_priority_returns_400(mp_pair):
    """MP4: POST /message:send with invalid priority must return 400."""
    resp, code = _http(mp_pair["a_http"], "/message:send", method="POST", body={
        "text": "test",
        "role": "agent",
        "priority": "URGENT",  # invalid
    })
    assert code == 400, f"Expected 400, got {code}: {resp}"


# ── MP5 ───────────────────────────────────────────────────────────────────────

def test_mp5_default_priority_is_normal(mp_pair):
    """MP5: POST /message:send without priority defaults to normal."""
    # Send without priority field, then check Beta received a message with priority='normal'
    _http(mp_pair["b_http"], "/recv")  # drain Beta's queue
    _http(mp_pair["a_http"], "/message:send", method="POST", body={
        "text": "no priority specified",
        "role": "agent",
    })
    time.sleep(0.5)
    recv, _ = _http(mp_pair["b_http"], "/recv")
    msgs = recv.get("messages", [])
    assert msgs, "Beta received no messages"
    # Priority field in the message frame
    raw = msgs[0].get("raw") or msgs[0]
    prio = raw.get("priority", "normal")
    assert prio == "normal", f"Expected default priority 'normal', got '{prio}'"


# ── MP6 ───────────────────────────────────────────────────────────────────────

def test_mp6_priority_field_in_received_frame(mp_pair):
    """MP6: The message frame received by peer must contain the priority field."""
    _http(mp_pair["b_http"], "/recv")  # drain
    _http(mp_pair["a_http"], "/message:send", method="POST", body={
        "text": "critical alert",
        "role": "agent",
        "priority": "critical",
    })
    time.sleep(0.5)
    recv, _ = _http(mp_pair["b_http"], "/recv")
    msgs = recv.get("messages", [])
    assert msgs, "Beta received no messages"
    raw = msgs[0].get("raw") or msgs[0]
    assert raw.get("priority") == "critical", (
        f"Expected priority='critical' in frame, got: {raw.get('priority')}"
    )


# ── MP7 ───────────────────────────────────────────────────────────────────────

def test_mp7_recv_sorted_by_priority(mp_pair):
    """MP7: /recv must return messages sorted critical > high > normal > low."""
    # Send from Beta → Alpha in reverse-priority order: low, normal, high, critical
    _http(mp_pair["a_http"], "/recv")  # drain Alpha's queue
    for prio in ("low", "normal", "high", "critical"):
        _http(mp_pair["b_http"], "/message:send", method="POST", body={
            "text": f"priority={prio}",
            "role": "agent",
            "priority": prio,
        })
        time.sleep(0.1)

    # Wait for all 4 to arrive — poll /messages (non-destructive) until count >= 4
    ok = _wait_for(
        lambda: _http(mp_pair["a_http"], "/messages?limit=10&sort=asc")[0].get("total", 0) >= 4
                or len(_http(mp_pair["a_http"], "/status")[0].get("priority_counts", {})) > 0,
        timeout=10,
    )
    time.sleep(1.2)  # extra buffer for WS delivery

    recv, _ = _http(mp_pair["a_http"], "/recv")
    msgs = recv.get("messages", [])
    assert len(msgs) >= 4, f"Expected 4 messages, got {len(msgs)}"

    # Extract priority from each
    _ORDER = {"critical": 0, "high": 1, "normal": 2, "low": 3}
    priorities = []
    for m in msgs[:4]:
        raw = m.get("raw") or m
        priorities.append(raw.get("priority", "normal"))

    order_values = [_ORDER.get(p, 2) for p in priorities]
    assert order_values == sorted(order_values), (
        f"Messages not sorted by priority: {priorities} (expected critical>high>normal>low)"
    )


# ── MP8 ───────────────────────────────────────────────────────────────────────

def test_mp8_priority_counts_increments(mp_pair):
    """MP8: priority_counts in /status must increment when messages are sent."""
    before, _ = _http(mp_pair["a_http"], "/status")
    critical_before = before.get("priority_counts", {}).get("critical", 0)

    _http(mp_pair["a_http"], "/message:send", method="POST", body={
        "text": "count me",
        "role": "agent",
        "priority": "critical",
    })

    after, _ = _http(mp_pair["a_http"], "/status")
    critical_after = after.get("priority_counts", {}).get("critical", 0)
    assert critical_after == critical_before + 1, (
        f"priority_counts.critical: expected {critical_before + 1}, got {critical_after}"
    )


# ── MP9 ───────────────────────────────────────────────────────────────────────

def test_mp9_all_four_priorities_accepted(mp_pair):
    """MP9: All four priority values (critical/high/normal/low) must be accepted."""
    for prio in ("critical", "high", "normal", "low"):
        resp, code = _http(mp_pair["a_http"], "/message:send", method="POST", body={
            "text": f"test {prio}",
            "role": "agent",
            "priority": prio,
        })
        assert code == 200, f"priority='{prio}' rejected with {code}: {resp}"
        assert resp.get("ok") is True, f"priority='{prio}' returned ok!=True: {resp}"
