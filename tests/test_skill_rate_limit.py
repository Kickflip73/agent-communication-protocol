"""
test_skill_rate_limit.py — v2.53 skill.rate_limit テストスイート

SRL1  — rate_limit absent → always allowed (backward-compat)
SRL2  — requests_per_minute=3: first 3 calls succeed, 4th returns 429 ERR_RATE_LIMIT
SRL3  — 429 response includes limit_type / limit / current_count / reset_in_seconds / skill_id / peer_id
SRL4  — burst=2 extends rpm window: rpm=2 + burst=2 → 4 calls succeed, 5th is 429
SRL5  — requests_per_day=2: first 2 succeed, 3rd returns 429
SRL6  — different peer_ids have independent counters (per-peer isolation)
SRL7  — different skill_ids have independent counters (per-skill isolation)
SRL8  — skill not declared with rate_limit → always allowed
SRL9  — limit_type "requests_per_day" present in 429 body when day quota exceeded
SRL10 — rate_limit + authorization_tier: tier failure still returns 403, not 429
SRL11 — rate_limit + param_constraints: param failure still returns 400, not 429
SRL12 — capabilities.skill_rate_limit == True in GET /status
"""

import json, os, sys, time, subprocess, threading, urllib.request, urllib.error

RELAY_PY = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")


def _wait_ready(hp, timeout=12):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{hp}/status", timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.25)
    return False


def _start(ws_port, skills, extra=None):
    hp = ws_port + 100
    env = os.environ.copy()
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        env.pop(k, None)
    cmd = [sys.executable, RELAY_PY,
           "--port", str(ws_port), "--name", f"RLRelay{ws_port}",
           "--local-only", "--test-mode",
           "--skills", json.dumps(skills)]
    if extra:
        cmd.extend(extra)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    for s in (proc.stdout, proc.stderr):
        threading.Thread(target=lambda x=s: x.read(), daemon=True).start()
    assert _wait_ready(hp), f"relay on :{hp} failed"
    return proc, hp


def _http(method, hp, path, body=None):
    url = f"http://127.0.0.1:{hp}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _task(hp, skill_id, peer_id=None):
    body = {"role": "agent", "text": "test", "skill_id": skill_id}
    if peer_id:
        body["peer_id"] = peer_id
    return _http("POST", hp, "/tasks", body)


# ─── SRL1 ────────────────────────────────────────────────────────────────────
def test_srl1_no_rate_limit_always_allowed():
    skills = [{"id": "no_rl", "name": "No Rate Limit"}]
    p, hp = _start(51000, skills)
    try:
        for _ in range(5):
            s, b = _task(hp, "no_rl")
            assert s == 201, f"Expected 201, got {s}: {b}"
    finally:
        p.terminate(); p.wait(timeout=5)


# ─── SRL2 ────────────────────────────────────────────────────────────────────
def test_srl2_rpm_limit_enforced():
    skills = [{"id": "rpm3", "name": "RPM3", "rate_limit": {"requests_per_minute": 3}}]
    p, hp = _start(51001, skills)
    try:
        for i in range(3):
            s, b = _task(hp, "rpm3", "peer_a")
            assert s == 201, f"Call {i+1} failed: {s} {b}"
        s, b = _task(hp, "rpm3", "peer_a")
        assert s == 429, f"4th call should be 429, got {s}: {b}"
        assert b.get("error_code") == "ERR_RATE_LIMIT"
    finally:
        p.terminate(); p.wait(timeout=5)


# ─── SRL3 ────────────────────────────────────────────────────────────────────
def test_srl3_429_response_detail():
    skills = [{"id": "rpm2", "name": "RPM2", "rate_limit": {"requests_per_minute": 2}}]
    p, hp = _start(51002, skills)
    try:
        _task(hp, "rpm2", "p1")
        _task(hp, "rpm2", "p1")
        s, b = _task(hp, "rpm2", "p1")
        assert s == 429
        assert b["error_code"] == "ERR_RATE_LIMIT"
        assert b["limit_type"] == "requests_per_minute"
        assert b["limit"] == 2
        assert "current_count" in b
        assert "reset_in_seconds" in b
        assert b["skill_id"] == "rpm2"
        assert b["peer_id"] == "p1"
        assert b["ok"] is False
    finally:
        p.terminate(); p.wait(timeout=5)


# ─── SRL4 ────────────────────────────────────────────────────────────────────
def test_srl4_burst_extends_rpm():
    skills = [{"id": "burst_sk", "name": "Burst", "rate_limit": {"requests_per_minute": 2, "burst": 2}}]
    p, hp = _start(51003, skills)
    try:
        # rpm=2 + burst=2 → 4 should succeed
        for i in range(4):
            s, b = _task(hp, "burst_sk", "peer_b")
            assert s == 201, f"Call {i+1} should succeed: {s} {b}"
        # 5th should be 429
        s, b = _task(hp, "burst_sk", "peer_b")
        assert s == 429, f"5th call should be 429, got {s}: {b}"
        assert b["limit_type"] == "requests_per_minute"
        assert b["effective_limit"] == 4  # rpm + burst
    finally:
        p.terminate(); p.wait(timeout=5)


# ─── SRL5 ────────────────────────────────────────────────────────────────────
def test_srl5_requests_per_day_enforced():
    skills = [{"id": "rpd2", "name": "RPD2", "rate_limit": {"requests_per_day": 2}}]
    p, hp = _start(51004, skills)
    try:
        _task(hp, "rpd2", "peer_c")
        _task(hp, "rpd2", "peer_c")
        s, b = _task(hp, "rpd2", "peer_c")
        assert s == 429, f"3rd call should be 429, got {s}: {b}"
        assert b["limit_type"] == "requests_per_day"
        assert b["limit"] == 2
    finally:
        p.terminate(); p.wait(timeout=5)


# ─── SRL6 ────────────────────────────────────────────────────────────────────
def test_srl6_per_peer_isolation():
    skills = [{"id": "iso_sk", "name": "Isolated", "rate_limit": {"requests_per_minute": 1}}]
    p, hp = _start(51005, skills)
    try:
        # peer_x uses up its quota
        s, b = _task(hp, "iso_sk", "peer_x")
        assert s == 201
        s, b = _task(hp, "iso_sk", "peer_x")
        assert s == 429, f"peer_x 2nd call should be limited: {s}"

        # peer_y has its own independent counter
        s, b = _task(hp, "iso_sk", "peer_y")
        assert s == 201, f"peer_y should have fresh quota: {s} {b}"
        s, b = _task(hp, "iso_sk", "peer_y")
        assert s == 429, f"peer_y 2nd call should be limited: {s}"
    finally:
        p.terminate(); p.wait(timeout=5)


# ─── SRL7 ────────────────────────────────────────────────────────────────────
def test_srl7_per_skill_isolation():
    skills = [
        {"id": "sk_a", "name": "Skill A", "rate_limit": {"requests_per_minute": 1}},
        {"id": "sk_b", "name": "Skill B", "rate_limit": {"requests_per_minute": 1}},
    ]
    p, hp = _start(51006, skills)
    try:
        # sk_a uses up its quota
        s, _ = _task(hp, "sk_a", "peer_d")
        assert s == 201
        s, _ = _task(hp, "sk_a", "peer_d")
        assert s == 429

        # sk_b has its own independent counter
        s, b = _task(hp, "sk_b", "peer_d")
        assert s == 201, f"sk_b should be independent: {s} {b}"
    finally:
        p.terminate(); p.wait(timeout=5)


# ─── SRL8 ────────────────────────────────────────────────────────────────────
def test_srl8_skill_without_rate_limit_unaffected():
    skills = [
        {"id": "limited",   "name": "Limited",   "rate_limit": {"requests_per_minute": 1}},
        {"id": "unlimited", "name": "Unlimited"},
    ]
    p, hp = _start(51007, skills)
    try:
        # unlimited can be called many times
        for _ in range(10):
            s, b = _task(hp, "unlimited", "peer_e")
            assert s == 201, f"Unlimited skill should always pass: {s} {b}"
    finally:
        p.terminate(); p.wait(timeout=5)


# ─── SRL9 ────────────────────────────────────────────────────────────────────
def test_srl9_rpd_limit_type_in_response():
    skills = [{"id": "rpd1", "name": "RPD1", "rate_limit": {"requests_per_day": 1}}]
    p, hp = _start(51008, skills)
    try:
        _task(hp, "rpd1", "peer_f")
        s, b = _task(hp, "rpd1", "peer_f")
        assert s == 429
        assert b["limit_type"] == "requests_per_day"
        assert "reset_in_seconds" in b
        # reset for daily should be up to 86400
        assert 0 <= b["reset_in_seconds"] <= 86400
    finally:
        p.terminate(); p.wait(timeout=5)


# ─── SRL10 ───────────────────────────────────────────────────────────────────
def test_srl10_tier_failure_not_rate_limit():
    """Tier T2 failure returns 403 (not 429) even if rate_limit is configured."""
    skills = [{"id": "t2rl", "name": "T2+RL",
               "authorization_tier": "T2",
               "rate_limit": {"requests_per_minute": 10}}]
    p, hp = _start(51009, skills)
    try:
        # No peer registered → T2 fails for unknown peer
        s, b = _task(hp, "t2rl", "unknown_low_trust_peer")
        # Should be 403 ERR_AUTHORIZATION_TIER (tier check happens before rate_limit)
        assert s == 403, f"Expected 403, got {s}: {b}"
        assert b.get("error_code") == "ERR_AUTHORIZATION_TIER"
    finally:
        p.terminate(); p.wait(timeout=5)


# ─── SRL11 ───────────────────────────────────────────────────────────────────
def test_srl11_param_failure_not_rate_limit():
    """param_constraints violation returns 400 (not 429)."""
    skills = [{"id": "pcrl", "name": "PC+RL",
               "param_constraints": {"amount": {"type": "number", "min": 1, "max": 100}},
               "rate_limit": {"requests_per_minute": 10}}]
    p, hp = _start(51010, skills)
    try:
        # amount=999 violates max=100
        body = {"role": "agent", "text": "pay", "skill_id": "pcrl",
                "params": {"amount": 999}}
        s, b = _http("POST", hp, "/tasks", body)
        assert s == 400, f"Expected 400, got {s}: {b}"
        assert b.get("error_code") == "ERR_PARAM_CONSTRAINT"
    finally:
        p.terminate(); p.wait(timeout=5)


# ─── SRL12 ───────────────────────────────────────────────────────────────────
def test_srl12_capabilities_flag():
    """GET /status must include capabilities.skill_rate_limit = True."""
    skills = [{"id": "any", "name": "Any"}]
    p, hp = _start(51011, skills)
    try:
        s, b = _http("GET", hp, "/status")
        assert s == 200
        # capabilities live under agent_card.capabilities
        caps = (b.get("agent_card") or {}).get("capabilities", {})
        assert caps.get("skill_rate_limit") is True, \
            f"skill_rate_limit capability missing: {caps}"
    finally:
        p.terminate(); p.wait(timeout=5)
