"""
test_context_query.py — v2.15 GET /context/<ctx_id>/messages tests

Scenario:
  - Start one relay (Alpha) + one relay (Beta) connected via --join
  - Send messages with context_id from both sides
  - Query /context/<ctx_id>/messages and verify correct filtering
  - Test since_seq, sort, limit, pagination, and error cases
"""

import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

import pytest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RELAY_PY = os.path.join(BASE_DIR, "relay", "acp_relay.py")


# ─── helpers ────────────────────────────────────────────────────────────────

def _free_port_pair():
    for _ in range(200):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            ws = s.getsockname()[1]
        try:
            with socket.socket() as s2:
                s2.bind(("127.0.0.1", ws + 100))
                return ws
        except OSError:
            continue
    raise RuntimeError("no free port pair")


def _clean_env():
    env = {k: v for k, v in os.environ.items()
           if k not in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")}
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _http(url, method="GET", body=None, timeout=5):
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read()), e.code
    except Exception as e:
        return {"_exc": str(e)}, 0


def _wait_http(url, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def _wait_tcp(host, port, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            pass
        time.sleep(0.2)
    return False


def _drain_stdout(proc):
    def _drain():
        try:
            while True:
                line = proc.stdout.readline()
                if not line:
                    break
        except Exception:
            pass
    threading.Thread(target=_drain, daemon=True).start()


def _start_relay(ws_port, name, join=None):
    http_port = ws_port + 100
    cmd = [sys.executable, RELAY_PY,
           "--name", name,
           "--port", str(ws_port),
           "--http-host", "127.0.0.1"]
    if join:
        cmd += ["--join", join]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=_clean_env(),
    )
    # Step 1: wait for HTTP ready
    assert _wait_http(f"http://127.0.0.1:{http_port}/status", timeout=30), \
        f"{name} HTTP not ready on :{http_port}"
    # Step 2: wait for WS to be up — poll /status until link contains 'tok_'
    # (link is only set after WS listener + public IP detection completes)
    import re as _re
    deadline = time.time() + 50
    ws_ready = False
    while time.time() < deadline:
        st, code = _http(f"http://127.0.0.1:{http_port}/status")
        if code == 200:
            lnk = st.get("link", "") or st.get("acp_link", "") or ""
            if _re.search(r"tok_[a-f0-9]+", lnk):
                ws_ready = True
                break
        time.sleep(0.5)
    assert ws_ready, f"{name} WS/link not ready within 50s (port {ws_port})"
    _drain_stdout(proc)
    return proc


def _send_msg(http_port, text, context_id=None, role="agent"):
    body = {
        "parts": [{"type": "text", "content": text}],
        "role": role,
    }
    if context_id:
        body["context_id"] = context_id
    return _http(f"http://127.0.0.1:{http_port}/message:send", method="POST", body=body)


# ─── fixture ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def dual_relay():
    """Alpha (host) + Beta (guest --join Alpha), both HTTP-accessible."""
    import re as _re

    alpha_ws = _free_port_pair()
    alpha_http = alpha_ws + 100
    alpha = _start_relay(alpha_ws, "CTX-Alpha")

    # Get Alpha's local ACP link (extract token from /status link)
    deadline = time.time() + 30
    alpha_link = None
    while time.time() < deadline:
        st, code = _http(f"http://127.0.0.1:{alpha_http}/status")
        if code == 200:
            lnk = st.get("link", "") or ""
            m = _re.search(r"acp://[^/]+:\d+/(tok_[a-f0-9]+)", lnk)
            if m:
                tok = m.group(1)
                alpha_link = f"acp://127.0.0.1:{alpha_ws}/{tok}"
                break
        time.sleep(0.5)
    assert alpha_link, "could not get Alpha local ACP link"

    beta_ws = _free_port_pair()
    beta_http = beta_ws + 100
    # Beta is guest mode — don't use _start_relay (which waits for tok_ in link);
    # instead start manually and just wait for HTTP ready + Alpha sees connected peer.
    import re as _re2  # noqa (already have _re above)
    beta = subprocess.Popen(
        [sys.executable, RELAY_PY,
         "--name", "CTX-Beta",
         "--port", str(beta_ws),
         "--http-host", "127.0.0.1",
         "--join", alpha_link],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=_clean_env(),
    )
    assert _wait_http(f"http://127.0.0.1:{beta_http}/status", timeout=30), \
        "CTX-Beta HTTP not ready"
    _drain_stdout(beta)

    # Wait until Alpha sees Beta as connected
    deadline2 = time.time() + 20
    while time.time() < deadline2:
        peers, _ = _http(f"http://127.0.0.1:{alpha_http}/peers")
        if any(p.get("connected") for p in peers.get("peers", [])):
            break
        time.sleep(0.4)

    yield alpha_http, beta_http

    alpha.terminate()
    beta.terminate()


# ─── tests ──────────────────────────────────────────────────────────────────

def test_cq1_empty_context(dual_relay):
    """CQ1: Query non-existent context_id returns empty list."""
    alpha_http, _ = dual_relay
    resp, code = _http(f"http://127.0.0.1:{alpha_http}/context/nonexistent_ctx/messages")
    assert code == 200, f"CQ1: expected 200, got {code}: {resp}"
    assert resp["context_id"] == "nonexistent_ctx"
    assert resp["messages"] == []
    assert resp["count"] == 0
    assert resp["total"] == 0
    assert resp["has_more"] is False


def test_cq2_messages_returned_for_context(dual_relay):
    """CQ2: Messages sent with context_id appear in /context/<id>/messages."""
    alpha_http, _ = dual_relay
    ctx = f"ctx_{uuid.uuid4().hex[:8]}"

    # Send 3 messages with this context_id
    for i in range(3):
        resp, code = _send_msg(alpha_http, f"hello {i}", context_id=ctx)
        assert code == 200, f"CQ2: send {i} failed: {resp}"

    # Give relay a moment to record
    time.sleep(0.3)

    result, code = _http(f"http://127.0.0.1:{alpha_http}/context/{ctx}/messages")
    assert code == 200, f"CQ2: query failed: {result}"
    assert result["context_id"] == ctx
    assert result["count"] == 3, f"CQ2: expected 3 messages, got {result['count']}"
    for msg in result["messages"]:
        assert msg["context_id"] == ctx


def test_cq3_context_isolation(dual_relay):
    """CQ3: Messages from different context_ids do not mix."""
    alpha_http, _ = dual_relay
    ctx_a = f"ctx_a_{uuid.uuid4().hex[:6]}"
    ctx_b = f"ctx_b_{uuid.uuid4().hex[:6]}"

    _send_msg(alpha_http, "msg in A", context_id=ctx_a)
    _send_msg(alpha_http, "msg in A 2", context_id=ctx_a)
    _send_msg(alpha_http, "msg in B", context_id=ctx_b)
    time.sleep(0.3)

    res_a, _ = _http(f"http://127.0.0.1:{alpha_http}/context/{ctx_a}/messages")
    res_b, _ = _http(f"http://127.0.0.1:{alpha_http}/context/{ctx_b}/messages")

    assert res_a["count"] == 2, f"CQ3: ctx_a expected 2, got {res_a['count']}"
    assert res_b["count"] == 1, f"CQ3: ctx_b expected 1, got {res_b['count']}"
    for m in res_a["messages"]:
        assert m["context_id"] == ctx_a
    for m in res_b["messages"]:
        assert m["context_id"] == ctx_b


def test_cq4_since_seq(dual_relay):
    """CQ4: since_seq filters out older messages."""
    alpha_http, _ = dual_relay
    ctx = f"ctx_seq_{uuid.uuid4().hex[:6]}"

    seq_list = []
    for i in range(4):
        r, _ = _send_msg(alpha_http, f"seq msg {i}", context_id=ctx)
        seq_list.append(r.get("server_seq", 0))
    time.sleep(0.3)

    # All 4
    all_msgs, _ = _http(f"http://127.0.0.1:{alpha_http}/context/{ctx}/messages")
    assert all_msgs["count"] == 4, f"CQ4: expected 4, got {all_msgs['count']}"

    # Since the 2nd message seq → should get 2 (3rd + 4th)
    pivot = seq_list[1]
    partial, _ = _http(f"http://127.0.0.1:{alpha_http}/context/{ctx}/messages?since_seq={pivot}")
    assert partial["count"] == 2, f"CQ4: since_seq={pivot} expected 2, got {partial['count']}"
    for m in partial["messages"]:
        assert (m.get("server_seq") or 0) > pivot


def test_cq5_sort_desc(dual_relay):
    """CQ5: sort=desc returns newest message first."""
    alpha_http, _ = dual_relay
    ctx = f"ctx_sort_{uuid.uuid4().hex[:6]}"

    for i in range(3):
        _send_msg(alpha_http, f"sorted {i}", context_id=ctx)
    time.sleep(0.3)

    asc, _ = _http(f"http://127.0.0.1:{alpha_http}/context/{ctx}/messages?sort=asc")
    desc, _ = _http(f"http://127.0.0.1:{alpha_http}/context/{ctx}/messages?sort=desc")

    assert asc["count"] == 3 and desc["count"] == 3
    asc_seqs = [m.get("server_seq") or 0 for m in asc["messages"]]
    desc_seqs = [m.get("server_seq") or 0 for m in desc["messages"]]
    assert asc_seqs == sorted(asc_seqs), "CQ5: asc order broken"
    assert desc_seqs == sorted(desc_seqs, reverse=True), "CQ5: desc order broken"


def test_cq6_limit_and_has_more(dual_relay):
    """CQ6: limit caps results and has_more reflects overflow."""
    alpha_http, _ = dual_relay
    ctx = f"ctx_lim_{uuid.uuid4().hex[:6]}"

    for i in range(5):
        _send_msg(alpha_http, f"lim {i}", context_id=ctx)
    time.sleep(0.3)

    res, code = _http(f"http://127.0.0.1:{alpha_http}/context/{ctx}/messages?limit=3")
    assert code == 200
    assert res["count"] == 3, f"CQ6: expected 3, got {res['count']}"
    assert res["total"] == 5, f"CQ6: expected total=5, got {res['total']}"
    assert res["has_more"] is True, "CQ6: has_more should be True"


def test_cq7_invalid_path(dual_relay):
    """CQ7: Malformed /context path returns 404."""
    alpha_http, _ = dual_relay
    resp, code = _http(f"http://127.0.0.1:{alpha_http}/context//messages")
    # empty context_id → 400
    assert code in (400, 404), f"CQ7: expected 400/404, got {code}"


def test_cq8_capability_declared(dual_relay):
    """CQ8: /.well-known/acp.json declares context_query capability."""
    alpha_http, _ = dual_relay
    resp, code = _http(f"http://127.0.0.1:{alpha_http}/.well-known/acp.json")
    assert code == 200, f"CQ8: AgentCard fetch failed: {resp}"
    # Endpoint returns {"self": <card>, "peer": ...}
    card = resp.get("self", resp)
    caps = card.get("capabilities", {})
    assert caps.get("context_query") is True, \
        f"CQ8: context_query not declared in capabilities: {caps}"
