"""
tests/test_policy_compliance_v287.py
=====================================
Test suite: PC-1..10
  PC-1   GET /policy-compliance — default empty list
  PC-2   GET /.well-known/acp.json — policy_compliance field present
  PC-3   GET /status — policy_compliance field present
  PC-4   capabilities.policy_compliance = False when list is empty
  PC-5   --policy-compliance CLI flag: values appear in AgentCard
  PC-6   capabilities.policy_compliance = True when list non-empty
  PC-7   PATCH /policy-compliance replace mode
  PC-8   PATCH /policy-compliance incremental add/remove
  PC-9   PATCH /policy-compliance — invalid body → 400
  PC-10  GET /policy-compliance — endpoint declared in AgentCard endpoints

ACP v2.87 — policy_compliance governance standards (inspired by A2A #1717).
"""

import json
import subprocess
import sys
import time
import urllib.request
import urllib.error

_RELAY = "relay/acp_relay.py"


def _start_relay(ws_port: int, policy_compliance: str = None, no_identity: bool = True):
    http_port = ws_port + 100
    cmd = [sys.executable, _RELAY, "--port", str(ws_port), "--name", "PCTestAgent",
           "--local-only", "--test-mode"]
    if no_identity:
        cmd += ["--no-identity"]
    if policy_compliance:
        cmd += ["--policy-compliance", policy_compliance]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{http_port}/status", timeout=1) as r:
                if r.status == 200:
                    return proc, http_port
        except Exception:
            time.sleep(0.2)
    proc.terminate()
    raise RuntimeError(f"Relay failed to start on HTTP port {http_port}")


def _get(hp, path):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{hp}{path}", timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _patch(hp, path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{hp}{path}",
        data=data, headers={"Content-Type": "application/json"}, method="PATCH",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_pc_1_to_10():
    # ── PC-1..4: relay WITHOUT --policy-compliance ──
    proc_empty, hp_empty = _start_relay(53000)
    try:
        # PC-1: GET /policy-compliance — default empty
        s, b = _get(hp_empty, "/policy-compliance")
        assert s == 200, f"PC-1 status: {s}"
        assert b.get("ok") is True, f"PC-1 ok: {b}"
        assert b.get("policy_compliance") == [], f"PC-1 list: {b}"
        assert b.get("count") == 0, f"PC-1 count: {b}"

        # PC-2: GET /.well-known/acp.json — policy_compliance field present (empty list)
        # Note: response is {"self": <AgentCard>, "peer": null}; AgentCard fields are under "self"
        s, b = _get(hp_empty, "/.well-known/acp.json")
        assert s == 200, f"PC-2 status: {s}"
        card = b.get("self", b)  # support both wrapped and flat responses
        assert "policy_compliance" in card, f"PC-2 field missing in card: {card.keys()}"
        assert card["policy_compliance"] == [], f"PC-2 value: {card['policy_compliance']}"

        # PC-3: GET /status — policy_compliance field present
        s, b = _get(hp_empty, "/status")
        assert s == 200, f"PC-3 status: {s}"
        assert "policy_compliance" in b, f"PC-3 field missing in status: {b.keys()}"
        assert b["policy_compliance"] == [], f"PC-3 value: {b['policy_compliance']}"

        # PC-4: capabilities.policy_compliance = False when empty
        s, b = _get(hp_empty, "/.well-known/acp.json")
        card = b.get("self", b)
        cap = card.get("capabilities", {})
        assert cap.get("policy_compliance") is False, f"PC-4 capabilities.policy_compliance: {cap.get('policy_compliance')}"

        # PC-7: PATCH /policy-compliance replace mode
        s, b = _patch(hp_empty, "/policy-compliance", {"policy_compliance": ["OWASP-ASVS", "ATF-v2"]})
        assert s == 200, f"PC-7 patch status: {s}"
        assert b.get("ok") is True, f"PC-7 ok: {b}"
        assert set(b.get("policy_compliance", [])) == {"OWASP-ASVS", "ATF-v2"}, f"PC-7 list: {b}"
        assert b.get("count") == 2, f"PC-7 count: {b}"
        assert b.get("updated") is True, f"PC-7 updated: {b}"

        # Verify GET reflects patched state
        s, b = _get(hp_empty, "/policy-compliance")
        assert set(b.get("policy_compliance", [])) == {"OWASP-ASVS", "ATF-v2"}, f"PC-7 GET after patch: {b}"

        # PC-8: PATCH incremental add/remove
        s, b = _patch(hp_empty, "/policy-compliance", {"add": ["ISO-42001"], "remove": ["ATF-v2"]})
        assert s == 200, f"PC-8 status: {s}"
        result_set = set(b.get("policy_compliance", []))
        assert "ISO-42001" in result_set, f"PC-8 add missing: {result_set}"
        assert "ATF-v2" not in result_set, f"PC-8 remove failed: {result_set}"
        assert "OWASP-ASVS" in result_set, f"PC-8 existing lost: {result_set}"

        # PC-9: PATCH invalid body → 400
        s, b = _patch(hp_empty, "/policy-compliance", {"invalid_key": "bad"})
        assert s == 400, f"PC-9 status: {s}"
        assert b.get("ok") is False, f"PC-9 ok: {b}"

    finally:
        proc_empty.terminate()

    # ── PC-5, PC-6, PC-10: relay WITH --policy-compliance ──
    proc_full, hp_full = _start_relay(53100, policy_compliance="OWASP-ASVS,NIST-AIRMF")
    try:
        # PC-5: values appear in AgentCard
        s, b = _get(hp_full, "/.well-known/acp.json")
        assert s == 200, f"PC-5 status: {s}"
        card = b.get("self", b)
        pc_list = card.get("policy_compliance", [])
        assert "OWASP-ASVS" in pc_list, f"PC-5 OWASP-ASVS missing: {pc_list}"
        assert "NIST-AIRMF" in pc_list, f"PC-5 NIST-AIRMF missing: {pc_list}"

        # PC-6: capabilities.policy_compliance = True when non-empty
        cap = card.get("capabilities", {})
        assert cap.get("policy_compliance") is True, f"PC-6 capabilities.policy_compliance: {cap.get('policy_compliance')}"

        # PC-10: endpoint declared in AgentCard endpoints
        endpoints = card.get("endpoints", {})
        assert "policy_compliance" in endpoints, f"PC-10 endpoint missing: {list(endpoints.keys())}"
        assert endpoints["policy_compliance"] == "/policy-compliance", f"PC-10 endpoint value: {endpoints['policy_compliance']}"

    finally:
        proc_full.terminate()
