"""
test_skill_param_constraints.py — v2.50 skill.param_constraints tests

Tests parameter-level invocation constraint validation at POST /tasks.
ConstraintRule fields: type, required, min, max, allowed_values, pattern.

Test IDs: SPC1–SPC18
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


def wait_http_ready(http_port, timeout=12):
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


def _start_relay(ws_port: int, skills: list) -> subprocess.Popen:
    http_port = ws_port + 100
    env = os.environ.copy()
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        env.pop(k, None)
    proc = subprocess.Popen(
        [sys.executable, RELAY_PY,
         "--port", str(ws_port), "--name", "PCTestRelay",
         "--local-only", "--test-mode",
         "--skills", json.dumps(skills)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
    )
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


def _task(http_port, skill_id=None, params=None):
    body = {"role": "agent", "text": "do task"}
    if skill_id:
        body["skill_id"] = skill_id
    if params is not None:
        body["params"] = params
    return _http("POST", http_port, "/tasks", body)


class R:
    """Relay fixture: ws_port, http_port = ws_port+100."""
    def __init__(self, ws_port, skills):
        self.ws_port = ws_port
        self.http_port = ws_port + 100
        self.proc = _start_relay(ws_port, skills)

    def cleanup(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()


# ─── SPC1: no param_constraints → 201 regardless of params ──────────────────
def test_spc1_no_constraints_passes():
    """SPC1: skill without param_constraints → any params accepted."""
    r = R(46000, [{"id": "plain_skill", "name": "Plain"}])
    try:
        s, b = _task(r.http_port, "plain_skill", {"amount": 9999, "currency": "BTC"})
        assert s == 201, f"{s}: {b}"
    finally:
        r.cleanup()


# ─── SPC2: no params in request, no required fields → 201 ───────────────────
def test_spc2_no_params_no_required():
    """SPC2: skill has param_constraints but no required fields; no params → 201."""
    skills = [{"id": "opt_skill", "name": "Opt",
               "param_constraints": {"amount": {"type": "number", "max": 1000}}}]
    r = R(46001, skills)
    try:
        s, b = _task(r.http_port, "opt_skill", params=None)
        assert s == 201, f"{s}: {b}"
    finally:
        r.cleanup()


# ─── SPC3: required param missing → 400 ERR_PARAM_CONSTRAINT ────────────────
def test_spc3_required_param_missing():
    """SPC3: required param absent → 400 ERR_PARAM_CONSTRAINT."""
    skills = [{"id": "transfer", "name": "Transfer",
               "param_constraints": {"amount": {"required": True, "type": "number"}}}]
    r = R(46002, skills)
    try:
        s, b = _task(r.http_port, "transfer", params={"currency": "USD"})
        assert s == 400, f"{s}: {b}"
        assert b.get("error_code") == "ERR_PARAM_CONSTRAINT"
        assert any("amount" in v for v in b.get("violated_params", []))
    finally:
        r.cleanup()


# ─── SPC4: required param present → 201 ─────────────────────────────────────
def test_spc4_required_param_present():
    """SPC4: required param present with correct type → 201."""
    skills = [{"id": "transfer", "name": "Transfer",
               "param_constraints": {"amount": {"required": True, "type": "number"}}}]
    r = R(46003, skills)
    try:
        s, b = _task(r.http_port, "transfer", params={"amount": 42.5})
        assert s == 201, f"{s}: {b}"
    finally:
        r.cleanup()


# ─── SPC5: type check — wrong type → 400 ────────────────────────────────────
def test_spc5_type_check_fail():
    """SPC5: param declared as 'number' but string passed → 400."""
    skills = [{"id": "pay", "name": "Pay",
               "param_constraints": {"amount": {"type": "number"}}}]
    r = R(46004, skills)
    try:
        s, b = _task(r.http_port, "pay", params={"amount": "one hundred"})
        assert s == 400, f"{s}: {b}"
        assert b.get("error_code") == "ERR_PARAM_CONSTRAINT"
        assert any("amount" in v for v in b.get("violated_params", []))
    finally:
        r.cleanup()


# ─── SPC6: max constraint — value exceeds max → 400 ─────────────────────────
def test_spc6_max_exceeded():
    """SPC6: numeric value > max → 400."""
    skills = [{"id": "pay", "name": "Pay",
               "param_constraints": {"amount": {"type": "number", "max": 1000}}}]
    r = R(46005, skills)
    try:
        s, b = _task(r.http_port, "pay", params={"amount": 1500})
        assert s == 400, f"{s}: {b}"
        assert b.get("error_code") == "ERR_PARAM_CONSTRAINT"
        assert any("amount" in v for v in b.get("violated_params", []))
    finally:
        r.cleanup()


# ─── SPC7: max constraint — value within max → 201 ──────────────────────────
def test_spc7_max_within_bound():
    """SPC7: numeric value <= max → 201."""
    skills = [{"id": "pay", "name": "Pay",
               "param_constraints": {"amount": {"type": "number", "max": 1000}}}]
    r = R(46006, skills)
    try:
        s, b = _task(r.http_port, "pay", params={"amount": 999})
        assert s == 201, f"{s}: {b}"
    finally:
        r.cleanup()


# ─── SPC8: min constraint — value below min → 400 ───────────────────────────
def test_spc8_min_violated():
    """SPC8: numeric value < min → 400."""
    skills = [{"id": "order", "name": "Order",
               "param_constraints": {"quantity": {"type": "integer", "min": 1}}}]
    r = R(46007, skills)
    try:
        s, b = _task(r.http_port, "order", params={"quantity": 0})
        assert s == 400, f"{s}: {b}"
        assert any("quantity" in v for v in b.get("violated_params", []))
    finally:
        r.cleanup()


# ─── SPC9: allowed_values — value not in list → 400 ─────────────────────────
def test_spc9_allowed_values_fail():
    """SPC9: value not in allowed_values → 400."""
    skills = [{"id": "trade", "name": "Trade",
               "param_constraints": {
                   "currency": {"type": "string",
                                "allowed_values": ["USD", "EUR", "CNY"]}
               }}]
    r = R(46008, skills)
    try:
        s, b = _task(r.http_port, "trade", params={"currency": "BTC"})
        assert s == 400, f"{s}: {b}"
        assert any("currency" in v for v in b.get("violated_params", []))
    finally:
        r.cleanup()


# ─── SPC10: allowed_values — value in list → 201 ────────────────────────────
def test_spc10_allowed_values_pass():
    """SPC10: value in allowed_values → 201."""
    skills = [{"id": "trade", "name": "Trade",
               "param_constraints": {
                   "currency": {"type": "string",
                                "allowed_values": ["USD", "EUR", "CNY"]}
               }}]
    r = R(46009, skills)
    try:
        s, b = _task(r.http_port, "trade", params={"currency": "USD"})
        assert s == 201, f"{s}: {b}"
    finally:
        r.cleanup()


# ─── SPC11: pattern constraint — no match → 400 ──────────────────────────────
def test_spc11_pattern_fail():
    """SPC11: string value does not match pattern → 400."""
    skills = [{"id": "verify", "name": "Verify",
               "param_constraints": {
                   "code": {"type": "string", "pattern": r"\d{6}"}
               }}]
    r = R(46010, skills)
    try:
        s, b = _task(r.http_port, "verify", params={"code": "abc"})
        assert s == 400, f"{s}: {b}"
        assert any("code" in v for v in b.get("violated_params", []))
    finally:
        r.cleanup()


# ─── SPC12: pattern constraint — match → 201 ────────────────────────────────
def test_spc12_pattern_pass():
    """SPC12: string value matches pattern → 201."""
    skills = [{"id": "verify", "name": "Verify",
               "param_constraints": {
                   "code": {"type": "string", "pattern": r"\d{6}"}
               }}]
    r = R(46011, skills)
    try:
        s, b = _task(r.http_port, "verify", params={"code": "123456"})
        assert s == 201, f"{s}: {b}"
    finally:
        r.cleanup()


# ─── SPC13: multiple violations → all reported ───────────────────────────────
def test_spc13_multiple_violations():
    """SPC13: multiple params violate constraints → all listed in violated_params."""
    skills = [{"id": "order", "name": "Order",
               "param_constraints": {
                   "amount":   {"required": True, "type": "number", "max": 1000},
                   "currency": {"required": True, "allowed_values": ["USD", "EUR"]},
               }}]
    r = R(46012, skills)
    try:
        # amount absent (required), currency invalid
        s, b = _task(r.http_port, "order", params={"currency": "BTC"})
        assert s == 400, f"{s}: {b}"
        violations = b.get("violated_params", [])
        assert len(violations) >= 2, f"expected >=2 violations, got: {violations}"
        combined = " ".join(violations)
        assert "amount" in combined
        assert "currency" in combined
    finally:
        r.cleanup()


# ─── SPC14: unknown skill_id → no constraint check → 201 ────────────────────
def test_spc14_unknown_skill_no_check():
    """SPC14: skill_id not in AgentCard → no constraint enforcement → 201."""
    skills = [{"id": "known", "name": "Known",
               "param_constraints": {"amount": {"required": True}}}]
    r = R(46013, skills)
    try:
        s, b = _task(r.http_port, "ghost_skill", params={})
        assert s == 201, f"{s}: {b}"
    finally:
        r.cleanup()


# ─── SPC15: string length min/max ────────────────────────────────────────────
def test_spc15_string_length_constraints():
    """SPC15: string min/max check length (not numeric value)."""
    skills = [{"id": "msg", "name": "Msg",
               "param_constraints": {
                   "text": {"type": "string", "min": 3, "max": 10}
               }}]
    r = R(46014, skills)
    try:
        # Too short
        s1, b1 = _task(r.http_port, "msg", params={"text": "hi"})
        assert s1 == 400, f"expected 400 for short string, got {s1}: {b1}"

        # Just right
        s2, b2 = _task(r.http_port, "msg", params={"text": "hello"})
        assert s2 == 201, f"expected 201 for valid string, got {s2}: {b2}"

        # Too long
        s3, b3 = _task(r.http_port, "msg", params={"text": "this is too long"})
        assert s3 == 400, f"expected 400 for long string, got {s3}: {b3}"
    finally:
        r.cleanup()


# ─── SPC16: violated_params in error response ────────────────────────────────
def test_spc16_error_response_structure():
    """SPC16: 400 error response must include error_code, skill_id, violated_params."""
    skills = [{"id": "strict", "name": "Strict",
               "param_constraints": {"x": {"required": True}}}]
    r = R(46015, skills)
    try:
        s, b = _task(r.http_port, "strict", params={})
        assert s == 400
        assert b.get("error_code") == "ERR_PARAM_CONSTRAINT"
        assert "skill_id" in b
        assert b["skill_id"] == "strict"
        assert "violated_params" in b
        assert isinstance(b["violated_params"], list)
        assert len(b["violated_params"]) >= 1
    finally:
        r.cleanup()


# ─── SPC17: param_constraints declared in GET /skills ────────────────────────
def test_spc17_param_constraints_in_skills_list():
    """SPC17: GET /skills returns param_constraints field per skill."""
    skills = [
        {"id": "pay", "name": "Pay",
         "param_constraints": {
             "amount":   {"type": "number", "max": 1000},
             "currency": {"allowed_values": ["USD", "EUR"]},
         }},
        {"id": "query", "name": "Query"},  # no constraints
    ]
    r = R(46016, skills)
    try:
        s, b = _http("GET", r.http_port, "/skills")
        assert s == 200
        skills_list = b.get("skills", [])
        by_id = {sk["id"]: sk for sk in skills_list if isinstance(sk, dict)}

        pay_pc = by_id["pay"].get("param_constraints")
        assert pay_pc is not None, "pay should have param_constraints"
        assert "amount" in pay_pc
        assert "currency" in pay_pc

        query_pc = by_id["query"].get("param_constraints")
        assert query_pc is None, "query should have null param_constraints"
    finally:
        r.cleanup()


# ─── SPC18: capabilities.skill_param_constraints declared ────────────────────
def test_spc18_capability_declared():
    """SPC18: AgentCard must advertise capabilities.skill_param_constraints=true."""
    r = R(46017, [{"id": "s1", "name": "S1"}])
    try:
        s, b = _http("GET", r.http_port, "/status")
        assert s == 200
        caps = (b.get("agent_card") or {}).get("capabilities", {})
        assert caps.get("skill_param_constraints") is True, \
            f"capabilities.skill_param_constraints not True: {list(caps.keys())[-5:]}"
    finally:
        r.cleanup()
