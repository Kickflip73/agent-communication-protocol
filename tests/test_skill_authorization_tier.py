"""
test_skill_authorization_tier.py — v2.49 skill.authorization_tier enforcement tests

Tests the per-skill authorization tier feature:
  T0/T1/null — auto-execute (no trust requirement)
  T2         — requires caller trust_score >= 0.7
  T3         — requires trust_score >= 0.9 + verified_identity signal

Uses --test-mode relay + /debug/inject to simulate peer trust contexts.

Test IDs: SAT1–SAT12
"""

import json
import time
import threading
import subprocess
import urllib.request
import urllib.error
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))


def wait_http_ready(http_port, timeout=15):
    """Wait until relay HTTP port responds with 200."""
    import time
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
        time.sleep(0.3)
    return False

RELAY_PY = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")


def _start_relay(ws_port: int, http_port: int, skills: list[dict]) -> subprocess.Popen:
    """Start a relay with given skills declared in AgentCard.

    HTTP port is always ws_port + 100 (ACP convention). http_port arg is
    just for readability — must equal ws_port + 100.
    """
    skills_json = json.dumps(skills)
    env = os.environ.copy()
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        env.pop(k, None)
    proc = subprocess.Popen(
        [
            sys.executable, RELAY_PY,
            "--port", str(ws_port),
            "--name", "TierTestRelay",
            "--local-only",
            "--skills", skills_json,
            "--test-mode",
        ],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
    )
    for s in (proc.stdout, proc.stderr):
        threading.Thread(target=lambda x=s: x.read(), daemon=True).start()
    assert wait_http_ready(http_port, timeout=25), f"relay on :{http_port} did not start"
    return proc


def _http(method: str, http_port: int, path: str, body: dict | None = None) -> tuple[int, dict]:
    url = f"http://127.0.0.1:{http_port}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _inject_peer(http_port: int, peer_name: str, msg: str = "hello") -> None:
    """Register a peer via /debug/inject."""
    status, body = _http("POST", http_port, "/debug/inject", {
        "from": peer_name, "parts": [{"type": "text", "text": msg}]
    })
    assert status == 200, f"/debug/inject failed: {status} {body}"


def _get_peers(http_port: int) -> dict:
    """Return peers as a dict {peer_id: info}. Handles both dict and list responses."""
    status, body = _http("GET", http_port, "/peers")
    assert status == 200, f"/peers failed: {status} {body}"
    raw = body.get("peers", {})
    if isinstance(raw, list):
        # Older response format: list of peer objects with "id" field
        return {p.get("id", p.get("peer_id", str(i))): p for i, p in enumerate(raw)}
    return raw


def _find_peer_id(http_port: int, name: str) -> str | None:
    peers = _get_peers(http_port)
    for pid, info in peers.items():
        if info.get("agent_name") == name or info.get("name") == name:
            return pid
    return None


def _create_task(http_port: int, skill_id: str | None = None,
                 peer_id: str | None = None) -> tuple[int, dict]:
    body: dict = {"role": "agent", "text": "do task"}
    if skill_id:
        body["skill_id"] = skill_id
    if peer_id:
        body["peer_id"] = peer_id
    return _http("POST", http_port, "/tasks", body)


# ─── Fixtures (manual, to avoid conftest conflicts) ──────────────────────────

class RelayFixture:
    def __init__(self, ws_port: int, http_port: int, skills: list[dict]):
        assert http_port == ws_port + 100, "http_port must be ws_port + 100 (ACP convention)"
        self.http_port = http_port
        self.proc = _start_relay(ws_port, http_port, skills)

    def cleanup(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()


# ─── SAT1: null tier → always allowed ────────────────────────────────────────
def test_sat1_null_tier_always_allowed():
    """SAT1: skill with no tier declared — task creation always succeeds."""
    skills = [{"id": "summarize", "name": "Summarize", "description": "Text summarizer"}]
    f = RelayFixture(43500, 43600, skills)
    try:
        status, body = _create_task(f.http_port, skill_id="summarize")
        assert status == 201, f"expected 201, got {status}: {body}"
        assert body.get("ok") is True
    finally:
        f.cleanup()


# ─── SAT2: T0 tier → always allowed ──────────────────────────────────────────
def test_sat2_t0_always_allowed():
    """SAT2: T0 skill (observe only) — auto-execute, no trust needed."""
    skills = [{"id": "status_query", "name": "StatusQuery",
               "authorization_tier": "T0"}]
    f = RelayFixture(43501, 43601, skills)
    try:
        status, body = _create_task(f.http_port, skill_id="status_query")
        assert status == 201, f"expected 201, got {status}: {body}"
    finally:
        f.cleanup()


# ─── SAT3: T1 tier → always allowed ──────────────────────────────────────────
def test_sat3_t1_always_allowed():
    """SAT3: T1 skill (read-only) — auto-execute, no trust needed."""
    skills = [{"id": "read_data", "name": "ReadData",
               "authorization_tier": "T1"}]
    f = RelayFixture(43502, 43602, skills)
    try:
        status, body = _create_task(f.http_port, skill_id="read_data")
        assert status == 201, f"expected 201, got {status}: {body}"
    finally:
        f.cleanup()


# ─── SAT4: T2 tier + no peer_id → 403 ────────────────────────────────────────
def test_sat4_t2_no_peer_denied():
    """SAT4: T2 skill, caller peer unknown (no peer_id) → 403 ERR_AUTHORIZATION_TIER."""
    skills = [{"id": "send_email", "name": "SendEmail",
               "authorization_tier": "T2"}]
    f = RelayFixture(43503, 43603, skills)
    try:
        status, body = _create_task(f.http_port, skill_id="send_email", peer_id=None)
        assert status == 403, f"expected 403, got {status}: {body}"
        assert body.get("error_code") == "ERR_AUTHORIZATION_TIER"
        assert "T2" in body.get("error", "")
    finally:
        f.cleanup()


# ─── SAT5: T2 tier + low-trust peer → 403 ────────────────────────────────────
def test_sat5_t2_low_trust_denied():
    """SAT5: T2 skill, injected peer has trust_score ~0 (no card_sig, no pings) → 403."""
    skills = [{"id": "write_file", "name": "WriteFile",
               "authorization_tier": "T2"}]
    f = RelayFixture(43504, 43604, skills)
    try:
        _inject_peer(f.http_port, "LowTrustBot")
        peer_id = _find_peer_id(f.http_port, "LowTrustBot")
        assert peer_id is not None, "peer not registered"

        status, body = _create_task(f.http_port, skill_id="write_file", peer_id=peer_id)
        # injected peer has no card_sig/pings/messages → trust_score ~0 < 0.7
        assert status == 403, f"expected 403, got {status}: {body}"
        assert body.get("error_code") == "ERR_AUTHORIZATION_TIER"
    finally:
        f.cleanup()


# ─── SAT6: T3 tier + no peer → 403 ───────────────────────────────────────────
def test_sat6_t3_no_peer_denied():
    """SAT6: T3 skill, no peer_id → 403 (unknown caller cannot satisfy T3)."""
    skills = [{"id": "delete_account", "name": "DeleteAccount",
               "authorization_tier": "T3"}]
    f = RelayFixture(43505, 43605, skills)
    try:
        status, body = _create_task(f.http_port, skill_id="delete_account")
        assert status == 403, f"expected 403, got {status}: {body}"
        assert body.get("error_code") == "ERR_AUTHORIZATION_TIER"
        assert "T3" in body.get("error", "")
    finally:
        f.cleanup()


# ─── SAT7: unknown skill_id → allowed (no tier restriction) ──────────────────
def test_sat7_unknown_skill_allowed():
    """SAT7: skill_id not declared in AgentCard → no enforcement → 201."""
    skills = [{"id": "known_skill", "name": "KnownSkill", "authorization_tier": "T3"}]
    f = RelayFixture(43506, 43606, skills)
    try:
        # Use a skill_id not in the card
        status, body = _create_task(f.http_port, skill_id="ghost_skill")
        assert status == 201, f"expected 201, got {status}: {body}"
    finally:
        f.cleanup()


# ─── SAT8: no skill_id in request → allowed ──────────────────────────────────
def test_sat8_no_skill_id_allowed():
    """SAT8: task created without skill_id → no tier check → 201."""
    skills = [{"id": "dangerous_op", "name": "DangerousOp",
               "authorization_tier": "T3"}]
    f = RelayFixture(43507, 43607, skills)
    try:
        status, body = _create_task(f.http_port, skill_id=None)
        assert status == 201, f"expected 201, got {status}: {body}"
    finally:
        f.cleanup()


# ─── SAT9: invalid tier value in skill config → treated as null → allowed ────
def test_sat9_invalid_tier_treated_as_null():
    """SAT9: skill with authorization_tier='T99' (invalid) → parsed as null → 201."""
    skills = [{"id": "action", "name": "Action",
               "authorization_tier": "T99"}]  # invalid value
    f = RelayFixture(43508, 43608, skills)
    try:
        status, body = _create_task(f.http_port, skill_id="action")
        assert status == 201, f"expected 201, got {status}: {body}"
    finally:
        f.cleanup()


# ─── SAT10: tier check error response contains skill_id and peer_id ──────────
def test_sat10_error_response_contains_context():
    """SAT10: 403 response must include skill_id and peer_id fields for debugging."""
    skills = [{"id": "risky_write", "name": "RiskyWrite",
               "authorization_tier": "T2"}]
    f = RelayFixture(43509, 43609, skills)
    try:
        _inject_peer(f.http_port, "WeakAgent")
        peer_id = _find_peer_id(f.http_port, "WeakAgent")
        assert peer_id is not None

        status, body = _create_task(f.http_port, skill_id="risky_write", peer_id=peer_id)
        assert status == 403
        assert "skill_id" in body, f"missing skill_id in: {body}"
        assert "peer_id" in body, f"missing peer_id in: {body}"
        assert body["skill_id"] == "risky_write"
    finally:
        f.cleanup()


# ─── SAT11: capabilities.skill_authorization_tiers declared in AgentCard ──────
def test_sat11_capability_declared():
    """SAT11: AgentCard must advertise capabilities.skill_authorization_tiers=true.

    /.well-known/acp.json returns {"self": <AgentCard>, "peer": ...}.
    Capabilities are at body["self"]["capabilities"].
    """
    skills = [{"id": "write_data", "name": "WriteData", "authorization_tier": "T2"}]
    # Use dynamic ports to avoid conflicts with lingering relay processes
    import socket as _sock
    with _sock.socket() as _s:
        _s.bind(("", 0))
        _ws = _s.getsockname()[1]
    f = RelayFixture(_ws, _ws + 100, skills)
    try:
        # Try /.well-known/acp.json first (self.capabilities)
        status, body = _http("GET", f.http_port, "/.well-known/acp.json")
        assert status == 200
        self_card = body.get("self") or body
        caps = self_card.get("capabilities", {})
        if not caps:
            # Fallback: check /status agent_card
            s2, b2 = _http("GET", f.http_port, "/status")
            assert s2 == 200
            caps = (b2.get("agent_card") or {}).get("capabilities", {})
        assert caps.get("skill_authorization_tiers") is True, \
            f"capabilities.skill_authorization_tiers not set in caps: {list(caps.keys())[:10]}"
    finally:
        f.cleanup()


# ─── SAT12: authorization_tier appears in GET /skills response ────────────────
def test_sat12_tier_in_skills_list():
    """SAT12: GET /skills returns authorization_tier field for each skill."""
    skills = [
        {"id": "query_op",  "name": "QueryOp",  "authorization_tier": "T0"},
        {"id": "write_op",  "name": "WriteOp",  "authorization_tier": "T2"},
        {"id": "delete_op", "name": "DeleteOp", "authorization_tier": "T3"},
        {"id": "plain_op",  "name": "PlainOp"},  # no tier
    ]
    f = RelayFixture(43511, 43611, skills)
    try:
        status, body = _http("GET", f.http_port, "/skills")
        assert status == 200
        skills_list = body.get("skills", [])
        by_id = {s["id"]: s for s in skills_list if isinstance(s, dict)}

        assert by_id["query_op"].get("authorization_tier") == "T0"
        assert by_id["write_op"].get("authorization_tier") == "T2"
        assert by_id["delete_op"].get("authorization_tier") == "T3"
        assert by_id["plain_op"].get("authorization_tier") is None
    finally:
        f.cleanup()
