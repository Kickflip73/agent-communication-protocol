"""
test_t3_human_confirmation.py — v2.51 T3 human_confirmation tests

Tests the two-phase T3 execution flow:
  POST /tasks  →  confirmation_pending  (when skill.human_confirmation_required=true + T3)
  POST /tasks/{id}:confirm              →  submitted
  POST /tasks/{id}:reject               →  failed

Test IDs: T3C1–T3C14
"""

import json
import time
import threading
import subprocess
import urllib.request
import urllib.error
import os
import sys

RELAY_PY = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")


def wait_http_ready(http_port, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{http_port}/status", timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def _kill_port(port):
    """Kill any process holding the given TCP port (best-effort)."""
    import signal as _sig
    try:
        import subprocess as _sp
        result = _sp.run(
            ["ss", "-tlnp", f"sport = :{port}"],
            capture_output=True, text=True, timeout=3
        )
        for line in result.stdout.splitlines():
            if f":{port}" in line and "pid=" in line:
                pid_str = line.split("pid=")[1].split(",")[0]
                try:
                    os.kill(int(pid_str), _sig.SIGKILL)
                except Exception:
                    pass
    except Exception:
        pass
    time.sleep(0.3)


def _start_relay(ws_port, skills, extra_flags=None):
    http_port = ws_port + 100
    # Pre-clean: kill any lingering process on ws_port or http_port
    _kill_port(ws_port)
    _kill_port(http_port)
    env = os.environ.copy()
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        env.pop(k, None)
    cmd = [sys.executable, RELAY_PY,
           "--port", str(ws_port), "--name", "T3CRelay",
           "--local-only", "--test-mode",
           "--skills", json.dumps(skills)]
    if extra_flags:
        cmd.extend(extra_flags)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    for s in (proc.stdout, proc.stderr):
        threading.Thread(target=lambda x=s: x.read(), daemon=True).start()
    assert wait_http_ready(http_port), f"relay on :{http_port} did not start"
    return proc


def _http(method, http_port, path, body=None):
    url = f"http://127.0.0.1:{http_port}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _inject_peer_with_trust(http_port, peer_name, trust_override=None):
    """Inject a peer via /debug/inject with optional trust_override, return peer_id."""
    body = {"from": peer_name, "parts": [{"type": "text", "text": "hello"}]}
    if trust_override:
        body["trust_override"] = trust_override
    s, b = _http("POST", http_port, "/debug/inject", body)
    assert s == 200, f"inject failed: {s} {b}"
    # /debug/inject returns peer_id directly (v2.48+)
    peer_id = b.get("peer_id")
    if not peer_id:
        # fallback: search /peers
        _, pr = _http("GET", http_port, "/peers")
        raw = pr.get("peers") or {}
        if isinstance(raw, list):
            peer_id = next(
                (p.get("id") or p.get("peer_id") for p in raw
                 if p.get("agent_name") == peer_name or p.get("name") == peer_name),
                None
            )
        else:
            peer_id = next(
                (pid for pid, p in raw.items()
                 if p.get("agent_name") == peer_name or p.get("name") == peer_name),
                None
            )
    assert peer_id, f"peer '{peer_name}' not found after inject"
    return peer_id


T3_SKILL_WITH_CONFIRM = {
    "id": "deploy",
    "name": "Deploy",
    "authorization_tier": "T3",
    "human_confirmation_required": True,
}

T3_SKILL_NO_CONFIRM = {
    "id": "delete",
    "name": "Delete",
    "authorization_tier": "T3",
    "human_confirmation_required": False,
}

T2_SKILL = {
    "id": "send_msg",
    "name": "Send",
    "authorization_tier": "T2",
    "human_confirmation_required": True,  # should be ignored (not T3)
}

# trust_override values that yield trust_score >= 0.9 + verified_identity signal
# card_sig(0.35) + did_consistent(0.20) + ping<50ms(0.20) + messages>100(0.15) = 0.90
T3_TRUST_OVERRIDE = {
    "card_sig_valid": True,
    "did_consistent": True,
    "ping_rtt_ms": 20,
    "message_count": 150,
    "verified_identity": True,
}

T2_TRUST_OVERRIDE = {
    "card_sig_valid": True,
    "did_consistent": True,
    "ping_rtt_ms": 20,
}  # card_sig(0.35) + did_consistent(0.20) + ping(0.20) = 0.75 >= 0.7

LOW_TRUST_OVERRIDE = {}  # no overrides → trust_score ≈ 0


# ── T3C1: T3 + human_confirmation_required → confirmation_pending ────────────
def test_t3c1_confirmation_pending_on_create():
    """T3C1: POST /tasks with T3 + human_confirmation_required=true → 201 + confirmation_pending."""
    ws, hp = 47000, 47100
    proc = _start_relay(ws, [T3_SKILL_WITH_CONFIRM])
    try:
        peer_id = _inject_peer_with_trust(hp, "trusted_peer", T3_TRUST_OVERRIDE)
        s, b = _http("POST", hp, "/tasks", {
            "role": "agent", "text": "deploy to prod",
            "skill_id": "deploy", "peer_id": peer_id,
        })
        assert s == 201, f"{s}: {b}"
        task = b.get("task", {})
        assert task.get("status") == "confirmation_pending", f"Expected confirmation_pending, got: {task.get('status')}"
        assert task.get("confirmation_required") is True
    finally:
        proc.terminate(); proc.wait(timeout=5)


# ── T3C2: T3 + human_confirmation_required=false → submitted immediately ─────
def test_t3c2_no_confirmation_flag_submitted():
    """T3C2: T3 skill with human_confirmation_required=false → submitted (no gate)."""
    ws, hp = 47001, 47101
    proc = _start_relay(ws, [T3_SKILL_NO_CONFIRM])
    try:
        peer_id = _inject_peer_with_trust(hp, "peer2", T3_TRUST_OVERRIDE)
        s, b = _http("POST", hp, "/tasks", {
            "role": "agent", "text": "do delete",
            "skill_id": "delete", "peer_id": peer_id,
        })
        assert s == 201, f"{s}: {b}"
        assert b["task"]["status"] == "submitted"
        assert b["task"].get("confirmation_required") is not True
    finally:
        proc.terminate(); proc.wait(timeout=5)


# ── T3C3: T2 skill with human_confirmation_required=true → submitted (ignored) ─
def test_t3c3_t2_skill_confirmation_ignored():
    """T3C3: human_confirmation_required=true on T2 skill → submitted (only T3 gated).
    Uses T3_TRUST_OVERRIDE to ensure reputation_adj=-1 counters bilateral_ir_adj=+1,
    keeping effective_tier at T2 (trust score 0.90, verified_identity=True, msgs=150).
    """
    ws, hp = 47002, 47102
    proc = _start_relay(ws, [T2_SKILL])
    try:
        peer_id = _inject_peer_with_trust(hp, "peer3", T3_TRUST_OVERRIDE)
        s, b = _http("POST", hp, "/tasks", {
            "role": "agent", "text": "send it",
            "skill_id": "send_msg", "peer_id": peer_id,
        })
        assert s == 201, f"{s}: {b}"
        assert b["task"]["status"] == "submitted"
    finally:
        proc.terminate(); proc.wait(timeout=5)


# ── T3C4: :confirm transitions confirmation_pending → submitted ──────────────
def test_t3c4_confirm_transitions_to_submitted():
    """T3C4: POST /tasks/{id}:confirm on confirmation_pending task → 200 + submitted."""
    ws, hp = 47003, 47103
    proc = _start_relay(ws, [T3_SKILL_WITH_CONFIRM])
    try:
        peer_id = _inject_peer_with_trust(hp, "p4", T3_TRUST_OVERRIDE)
        _, create = _http("POST", hp, "/tasks", {
            "role": "agent", "text": "deploy",
            "skill_id": "deploy", "peer_id": peer_id,
        })
        task_id = create["task"]["id"]
        assert create["task"]["status"] == "confirmation_pending"

        s, b = _http("POST", hp, f"/tasks/{task_id}:confirm")
        assert s == 200, f"{s}: {b}"
        assert b.get("ok") is True
        assert b.get("status") == "submitted"

        # Verify task store updated (GET /tasks/{id} returns task directly, no wrapper)
        _, tget = _http("GET", hp, f"/tasks/{task_id}")
        assert tget.get("status") == "submitted"
    finally:
        proc.terminate(); proc.wait(timeout=5)


# ── T3C5: :reject transitions confirmation_pending → rejected (v2.66) ────────
def test_t3c5_reject_transitions_to_failed():
    """T3C5: POST /tasks/{id}:reject on confirmation_pending task → 200 + rejected.
    v2.66: status changed from 'failed' → 'rejected' (A2A v1.0.0 alignment).
    """
    ws, hp = 47004, 47104
    proc = _start_relay(ws, [T3_SKILL_WITH_CONFIRM])
    try:
        peer_id = _inject_peer_with_trust(hp, "p5", T3_TRUST_OVERRIDE)
        _, create = _http("POST", hp, "/tasks", {
            "role": "agent", "text": "deploy",
            "skill_id": "deploy", "peer_id": peer_id,
        })
        task_id = create["task"]["id"]
        assert create["task"]["status"] == "confirmation_pending"

        s, b = _http("POST", hp, f"/tasks/{task_id}:reject", {"reason": "Too risky"})
        assert s == 200, f"{s}: {b}"
        assert b.get("ok") is True
        assert b.get("status") == "rejected", \
            f"v2.66: T3 :reject should yield 'rejected' (was 'failed'), got: {b.get('status')}"
        assert "Too risky" in b.get("reason", "")

        _, tget = _http("GET", hp, f"/tasks/{task_id}")
        assert tget.get("status") == "rejected"
    finally:
        proc.terminate(); proc.wait(timeout=5)


# ── T3C6: :confirm on non-existent task → 404 ───────────────────────────────
def test_t3c6_confirm_nonexistent_task():
    """T3C6: :confirm on unknown task_id → 404."""
    ws, hp = 47005, 47105
    proc = _start_relay(ws, [T3_SKILL_WITH_CONFIRM])
    try:
        s, b = _http("POST", hp, "/tasks/ghost-id:confirm")
        assert s == 404, f"{s}: {b}"
    finally:
        proc.terminate(); proc.wait(timeout=5)


# ── T3C7: :confirm on already-submitted task → 200 idempotent ───────────────
def test_t3c7_confirm_already_submitted_idempotent():
    """T3C7: :confirm on submitted (non-T3) task → 200 with 'already confirmed' note."""
    ws, hp = 47006, 47106
    proc = _start_relay(ws, [{"id": "plain", "name": "Plain"}])
    try:
        _, cr = _http("POST", hp, "/tasks", {"role": "agent", "text": "go", "skill_id": "plain"})
        tid = cr["task"]["id"]
        assert cr["task"]["status"] == "submitted"

        s, b = _http("POST", hp, f"/tasks/{tid}:confirm")
        assert s == 200, f"{s}: {b}"
        assert b.get("ok") is True
        assert "already" in (b.get("note") or "").lower()
    finally:
        proc.terminate(); proc.wait(timeout=5)


# ── T3C8: :confirm on working task → 409 ERR_CONFIRM_NOT_PENDING ─────────────
def test_t3c8_confirm_working_task_conflict():
    """T3C8: :confirm on working task → 409 ERR_CONFIRM_NOT_PENDING."""
    ws, hp = 47007, 47107
    proc = _start_relay(ws, [{"id": "wk", "name": "Wk"}])
    try:
        _, cr = _http("POST", hp, "/tasks", {"role": "agent", "text": "go", "skill_id": "wk"})
        tid = cr["task"]["id"]
        # Transition to working via update
        _http("POST", hp, f"/tasks/{tid}/update", {"status": "working"})

        s, b = _http("POST", hp, f"/tasks/{tid}:confirm")
        assert s == 409, f"{s}: {b}"
        assert b.get("error_code") == "ERR_CONFIRM_NOT_PENDING"
    finally:
        proc.terminate(); proc.wait(timeout=5)


# ── T3C9: --auto-confirm-t3 bypasses gate → submitted directly ──────────────
def test_t3c9_auto_confirm_t3_flag():
    """T3C9: --auto-confirm-t3 bypasses confirmation gate → submitted directly."""
    ws, hp = 47008, 47108
    proc = _start_relay(ws, [T3_SKILL_WITH_CONFIRM], extra_flags=["--auto-confirm-t3"])
    try:
        peer_id = _inject_peer_with_trust(hp, "p9", T3_TRUST_OVERRIDE)
        s, b = _http("POST", hp, "/tasks", {
            "role": "agent", "text": "deploy",
            "skill_id": "deploy", "peer_id": peer_id,
        })
        assert s == 201, f"{s}: {b}"
        assert b["task"]["status"] == "submitted", f"Expected submitted with --auto-confirm-t3, got: {b['task']['status']}"
    finally:
        proc.terminate(); proc.wait(timeout=5)


# ── T3C10: GET /tasks/{id} shows confirmation_required=true ─────────────────
def test_t3c10_get_task_shows_confirmation_flag():
    """T3C10: GET /tasks/{id} on a confirmation_pending task includes confirmation_required=true."""
    ws, hp = 47009, 47109
    proc = _start_relay(ws, [T3_SKILL_WITH_CONFIRM])
    try:
        peer_id = _inject_peer_with_trust(hp, "p10", T3_TRUST_OVERRIDE)
        _, cr = _http("POST", hp, "/tasks", {
            "role": "agent", "text": "deploy",
            "skill_id": "deploy", "peer_id": peer_id,
        })
        tid = cr["task"]["id"]
        # GET /tasks/{id} returns task directly (no wrapper)
        s, b = _http("GET", hp, f"/tasks/{tid}")
        assert s == 200, f"{s}: {b}"
        assert b.get("status") == "confirmation_pending", f"Got: {b}"
        assert b.get("confirmation_required") is True
    finally:
        proc.terminate(); proc.wait(timeout=5)


# ── T3C11: :reject with no reason body → default reason ──────────────────────
def test_t3c11_reject_no_body_default_reason():
    """T3C11: :reject with no request body → 200 + rejected with default reason.
    v2.66: status changed from 'failed' → 'rejected' (A2A v1.0.0 alignment).
    """
    ws, hp = 47010, 47110
    proc = _start_relay(ws, [T3_SKILL_WITH_CONFIRM])
    try:
        peer_id = _inject_peer_with_trust(hp, "p11", T3_TRUST_OVERRIDE)
        _, cr = _http("POST", hp, "/tasks", {
            "role": "agent", "text": "deploy",
            "skill_id": "deploy", "peer_id": peer_id,
        })
        tid = cr["task"]["id"]
        s, b = _http("POST", hp, f"/tasks/{tid}:reject")
        assert s == 200, f"{s}: {b}"
        assert b.get("ok") is True
        assert b.get("status") == "rejected", \
            f"v2.66: T3 :reject should yield 'rejected' (was 'failed'), got: {b.get('status')}"
        assert b.get("reason")  # some reason present
    finally:
        proc.terminate(); proc.wait(timeout=5)


# ── T3C12: tier check still runs before confirmation gate ────────────────────
def test_t3c12_tier_check_before_confirmation():
    """T3C12: T3 + human_confirmation + insufficient trust → 403 ERR_AUTHORIZATION_TIER (not confirmation_pending)."""
    ws, hp = 47011, 47111
    proc = _start_relay(ws, [T3_SKILL_WITH_CONFIRM])
    try:
        # Peer with no trust override → score ~0, should fail T3 tier check
        peer_id = _inject_peer_with_trust(hp, "weak_peer")  # no trust_override → low score
        s, b = _http("POST", hp, "/tasks", {
            "role": "agent", "text": "deploy",
            "skill_id": "deploy", "peer_id": peer_id,
        })
        assert s == 403, f"{s}: {b}"
        assert b.get("error_code") == "ERR_AUTHORIZATION_TIER"
    finally:
        proc.terminate(); proc.wait(timeout=5)


# ── T3C13: capabilities.t3_human_confirmation declared ──────────────────────
def test_t3c13_capability_declared():
    """T3C13: AgentCard must advertise capabilities.t3_human_confirmation=true."""
    ws, hp = 47012, 47112
    proc = _start_relay(ws, [T3_SKILL_WITH_CONFIRM])
    try:
        s, b = _http("GET", hp, "/status")
        assert s == 200
        caps = (b.get("agent_card") or {}).get("capabilities", {})
        assert caps.get("t3_human_confirmation") is True, \
            f"t3_human_confirmation not True in capabilities: {list(caps.keys())[-6:]}"
    finally:
        proc.terminate(); proc.wait(timeout=5)


# ── T3C14: GET /skills shows human_confirmation_required per skill ───────────
def test_t3c14_skills_list_shows_human_confirmation():
    """T3C14: GET /skills returns human_confirmation_required field per skill."""
    ws, hp = 47013, 47113
    proc = _start_relay(ws, [T3_SKILL_WITH_CONFIRM, T3_SKILL_NO_CONFIRM])
    try:
        s, b = _http("GET", hp, "/skills")
        assert s == 200
        by_id = {sk["id"]: sk for sk in b.get("skills", []) if isinstance(sk, dict)}
        assert by_id["deploy"].get("human_confirmation_required") is True
        assert by_id["delete"].get("human_confirmation_required") is False
    finally:
        proc.terminate(); proc.wait(timeout=5)
