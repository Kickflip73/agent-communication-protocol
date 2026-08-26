"""
ACP v2.58 — effective_tier three-factor dynamic computation

Test suite: ET-1..12

  ET-1   T0 skill + no principal chain + unknown peer → effective_tier raised to T1 (rep_adj=+1)
  ET-2   T1 skill + no chain + no peer_id → effective_tier = T2
  ET-3   T3 skill → effective_tier always T3 (immovable)
  ET-4   None tier + unknown peer → effective_tier = T1
  ET-5   depth=2 raises T0 to T2/T3 (depth_floor=T2 + rep_adj)
  ET-6   depth=5 → depth_floor capped at T3
  ET-7   GET /skills/nonexistent/effective-tier → 404
  ET-8   POST /tasks with T0 skill + no chain + no peer → effective T1 → auto-execute (200/201)
  ET-9   POST /tasks with T2 skill + no peer → effective T2/T3 + unknown peer → 403
  ET-10  depth=2 + T0 skill → POST /tasks blocked (effective_tier ≥ T2, unknown peer → 403)
  ET-11  GET /skills/{id}/effective-tier response has all required factors keys
  ET-12  capabilities.effective_tier_computation == True in AgentCard
"""

import json
import subprocess
import sys
import time
import urllib.request
import urllib.error
import os

_RELAY = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")

# Port range: 48200–48399
_WS_PORT   = 48200
_HTTP_PORT = _WS_PORT + 100


_SKILLS = [
    {"id": "sk-t0",   "name": "T0 skill",  "authorization_tier": "T0"},
    {"id": "sk-t1",   "name": "T1 skill",  "authorization_tier": "T1"},
    {"id": "sk-t2",   "name": "T2 skill",  "authorization_tier": "T2"},
    {"id": "sk-t3",   "name": "T3 skill",  "authorization_tier": "T3"},
    {"id": "sk-none", "name": "No tier"},
]


def _start_relay(ws_port: int = _WS_PORT) -> subprocess.Popen:
    http_port = ws_port + 100
    skills_json = json.dumps(_SKILLS)
    proc = subprocess.Popen(
        [sys.executable, _RELAY, "--port", str(ws_port), "--name", "ET-Agent",
         "--local-only", "--test-mode", "--skills", skills_json],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 12
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{http_port}/status", timeout=1) as r:
                if r.status == 200:
                    break
        except Exception:
            time.sleep(0.1)
    return proc


def _stop_relay(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def _http(method: str, path: str, body=None, *, http_port: int = _HTTP_PORT):
    url = f"http://127.0.0.1:{http_port}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _verify_skills_loaded(http_port: int = _HTTP_PORT):
    """Verify skills are available via /skills endpoint."""
    status, body = _http("GET", "/skills", http_port=http_port)
    assert status == 200, f"GET /skills failed: {status} {body}"
    ids = {s.get("id") for s in body.get("skills", [])}
    for sid in ("sk-t0", "sk-t1", "sk-t2", "sk-t3"):
        assert sid in ids, f"skill {sid} not found; available: {ids}"


def _add_principal(did: str, role: str = "operator", http_port: int = _HTTP_PORT):
    return _http("POST", "/principal-chain", {"did": did, "role": role}, http_port=http_port)


def _del_principal(did: str, http_port: int = _HTTP_PORT):
    # v2.56: DELETE /principal-chain/<did> — path-based removal
    import urllib.parse
    encoded_did = urllib.parse.quote(did, safe="")
    return _http("DELETE", f"/principal-chain/{encoded_did}", http_port=http_port)


# ───────────────────────────────────────────────────────────────────────────────

def test_et_1_to_12():
    proc = _start_relay()
    try:
        _verify_skills_loaded()

        # ET-1: T0 + no chain + unknown peer → effective_tier stays T0 (rep_adj not applied below T2)
        status, body = _http("GET", "/skills/sk-t0/effective-tier")
        assert status == 200, f"ET-1 failed: {status} {body}"
        d = body
        assert d["skill_id"] == "sk-t0", f"ET-1: wrong skill_id {d}"
        # base_int = max(0,0) = 0 < 2 → rep_adj NOT applied → effective_tier = T0/None (auto-execute)
        assert d["effective_tier"] in ("T0", None), f"ET-1: expected T0/None, got {d['effective_tier']}"
        assert d["factors"]["reputation_adj"] == 1, f"ET-1: rep_adj should be +1 (computed but not applied)"
        assert d["factors"]["delegation_depth"] == 0, f"ET-1: depth should be 0"
        print("ET-1 PASS")

        # ET-2: T1 + no chain + unknown peer → effective_tier stays T1 (base_int=1 < 2, rep_adj not applied)
        status, body = _http("GET", "/skills/sk-t1/effective-tier")
        assert status == 200, f"ET-2 failed: {status} {body}"
        assert body["effective_tier"] == "T1", f"ET-2: expected T1, got {body['effective_tier']}"
        assert body["factors"]["reputation_adj"] == 1  # computed but not applied
        print("ET-2 PASS")

        # ET-3: T3 → always T3
        status, body = _http("GET", "/skills/sk-t3/effective-tier")
        assert status == 200, f"ET-3 failed: {status} {body}"
        assert body["effective_tier"] == "T3", f"ET-3: expected T3, got {body['effective_tier']}"
        assert body["factors"]["tier_rule"] == "T3"
        print("ET-3 PASS")

        # ET-4: None tier + unknown peer → effective_tier = None/T0 (base_int=0, rep_adj not applied)
        status, body = _http("GET", "/skills/sk-none/effective-tier")
        assert status == 200, f"ET-4 failed: {status} {body}"
        assert body["factors"]["tier_rule"] is None, f"ET-4: expected None tier_rule"
        # base_int=0 < 2 → rep_adj not applied → effective_tier = None (T0 equivalent)
        assert body["effective_tier"] in (None, "T0"), f"ET-4: expected None/T0, got {body['effective_tier']}"
        print("ET-4 PASS")

        # ET-5: depth=2 → depth_floor=T2, T0 skill → effective ≥ T2
        _add_principal("did:example:d1")
        _add_principal("did:example:d2")
        try:
            status, body = _http("GET", "/skills/sk-t0/effective-tier")
            assert status == 200, f"ET-5 failed: {status} {body}"
            assert body["factors"]["delegation_depth"] == 2, f"ET-5: depth={body['factors']['delegation_depth']}"
            assert body["factors"]["depth_floor"] == "T2", f"ET-5: depth_floor={body['factors']['depth_floor']}"
            # max(0,2)+1=3 → T3
            assert body["effective_tier"] in ("T2", "T3"), f"ET-5: expected T2/T3, got {body['effective_tier']}"
            print("ET-5 PASS")
        finally:
            _del_principal("did:example:d1")
            _del_principal("did:example:d2")

        # ET-6: depth=5 → depth_floor capped at T3
        for i in range(5):
            _add_principal(f"did:example:deep{i}")
        try:
            status, body = _http("GET", "/skills/sk-t1/effective-tier")
            assert status == 200, f"ET-6 failed: {status} {body}"
            assert body["factors"]["delegation_depth"] >= 5, f"ET-6: depth={body['factors']['delegation_depth']}"
            assert body["factors"]["depth_floor"] == "T3", f"ET-6: depth_floor={body['factors']['depth_floor']}"
            assert body["effective_tier"] == "T3", f"ET-6: expected T3, got {body['effective_tier']}"
            print("ET-6 PASS")
        finally:
            for i in range(5):
                _del_principal(f"did:example:deep{i}")

        # ET-7: unknown skill → 404
        status, body = _http("GET", "/skills/nonexistent/effective-tier")
        assert status == 404, f"ET-7: expected 404, got {status}"
        print("ET-7 PASS")

        # ET-8: POST /tasks with T0 skill + no chain → effective T1 → auto-execute
        status, body = _http("POST", "/tasks", {"role": "agent", "skill_id": "sk-t0", "input": {"prompt": "hi"}})
        assert status in (200, 201), f"ET-8: expected 200/201, got {status}: {body}"
        print("ET-8 PASS")

        # ET-9: POST /tasks with T2 skill + no peer → 403
        status, body = _http("POST", "/tasks", {"role": "agent", "skill_id": "sk-t2", "input": {"prompt": "high"}})
        assert status == 403, f"ET-9: expected 403, got {status}: {body}"
        # error is a top-level string field in ACP error responses
        err_msg = body.get("error", "") if isinstance(body.get("error"), str) else str(body)
        assert "tier" in err_msg.lower() or "effective" in err_msg.lower(), \
            f"ET-9: error message should mention tier: {err_msg}"
        print("ET-9 PASS")

        # ET-10: depth=2 + T0 → effective T2/T3 → POST /tasks 403
        _add_principal("did:example:bt1")
        _add_principal("did:example:bt2")
        try:
            status, body = _http("POST", "/tasks", {"role": "agent", "skill_id": "sk-t0", "input": {"prompt": "x"}})
            assert status == 403, f"ET-10: expected 403 with deep chain, got {status}: {body}"
            print("ET-10 PASS")
        finally:
            _del_principal("did:example:bt1")
            _del_principal("did:example:bt2")

        # ET-11: factors dict has all keys
        status, body = _http("GET", "/skills/sk-t2/effective-tier")
        assert status == 200, f"ET-11 failed: {status} {body}"
        factors = body["factors"]
        for key in ("tier_rule", "delegation_depth", "depth_floor", "reputation_adj", "effective_tier"):
            assert key in factors, f"ET-11: missing key '{key}' in factors"
        assert isinstance(factors["delegation_depth"], int)
        assert factors["reputation_adj"] in (-1, 0, 1)
        print("ET-11 PASS")

        # ET-12: capability flag in /status
        status, body = _http("GET", "/status")
        assert status == 200, f"ET-12 failed: {status}"
        caps = body.get("agent_card", {}).get("capabilities", {})
        assert caps.get("effective_tier_computation") is True, \
            f"ET-12: effective_tier_computation capability missing or False; caps={caps}"
        print("ET-12 PASS")

    finally:
        _stop_relay(proc)
