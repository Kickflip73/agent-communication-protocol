"""
ACP v2.56 — principal_chain[] OBO delegation chain

Test suite: PC-1..10
  PC-1  GET /principal-chain on fresh relay → count=0, empty list
  PC-2  POST /principal-chain — add an entry, verify response
  PC-3  GET /principal-chain — confirms added entry
  PC-4  POST again (same DID) — upserts (not duplicates)
  PC-5  DELETE /principal-chain/<did> — removes entry
  PC-6  DELETE non-existent DID → 404 response
  PC-7  AgentCard trust block has principal_chain when populated
  PC-8  AgentCard trust.principal_chain absent when chain empty
  PC-9  GET /peers/{id}/principal-chain — unknown peer → 404
  PC-10 GET /peers/{id}/principal-chain — peer w/ AgentCard containing chain → 200
"""

import json
import subprocess
import sys
import time
import urllib.request
import urllib.error
import os

_RELAY = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")


def _start_relay(ws_port: int):
    http_port = ws_port + 100
    proc = subprocess.Popen(
        [sys.executable, _RELAY, "--port", str(ws_port), "--name", "PrincipalTestAgent",
         "--local-only", "--test-mode"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{http_port}/status", timeout=1) as r:
                if r.status == 200:
                    return proc, http_port
        except Exception:
            time.sleep(0.15)
    proc.terminate()
    raise RuntimeError(f"Relay failed to start on HTTP port {http_port}")


def _get(hp: int, path: str):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{hp}{path}", timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _post(hp: int, path: str, body: dict):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{hp}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _delete(hp: int, path: str):
    req = urllib.request.Request(
        f"http://127.0.0.1:{hp}{path}",
        method="DELETE",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _inject_peer_with_chain(hp: int, name: str, chain: list) -> str:
    """Inject a peer with an AgentCard that contains a principal_chain in trust block."""
    card = {
        "name": name,
        "trust": {"scheme": "none", "enabled": False, "principal_chain": chain},
    }
    s, b = _post(hp, "/debug/inject", {
        "from": name,
        "parts": [{"kind": "text", "text": "init"}],
        "agent_card": card,
    })
    assert s == 200, f"inject failed: {s} {b}"
    return b["peer_id"]


def test_pc_1_to_10():
    proc, hp = _start_relay(52600)  # WS=52600, HTTP=52700
    try:
        TEST_DID_A = "did:acp:TestPrincipalAlpha"
        TEST_DID_B = "did:acp:TestPrincipalBeta"

        # ── PC-1: GET /principal-chain on fresh relay → empty ─────────────────
        s, b = _get(hp, "/principal-chain")
        assert s == 200,              f"PC-1 status: {s}"
        assert b.get("ok") is True,   f"PC-1 ok: {b}"
        assert b.get("count") == 0,   f"PC-1 count: {b}"
        assert b.get("principal_chain") == [], f"PC-1 chain: {b}"
        assert "self_did" in b,       f"PC-1 missing self_did: {b}"

        # ── PC-2: POST /principal-chain — add entry ───────────────────────────
        s, b = _post(hp, "/principal-chain", {"did": TEST_DID_A, "role": "orchestrator"})
        assert s == 200,              f"PC-2 status: {s}"
        assert b.get("ok") is True,   f"PC-2 ok: {b}"
        assert b.get("did") == TEST_DID_A, f"PC-2 did: {b}"
        assert b.get("role") == "orchestrator", f"PC-2 role: {b}"
        assert b.get("count") == 1,   f"PC-2 count: {b}"
        assert "added_at" in b,       f"PC-2 missing added_at: {b}"

        # ── PC-3: GET /principal-chain — confirms added entry ─────────────────
        s, b = _get(hp, "/principal-chain")
        assert s == 200,              f"PC-3 status: {s}"
        assert b.get("count") == 1,   f"PC-3 count: {b}"
        chain = b.get("principal_chain", [])
        assert len(chain) == 1,       f"PC-3 chain len: {b}"
        assert chain[0]["did"] == TEST_DID_A, f"PC-3 did: {chain}"

        # ── PC-4: POST same DID again → upsert (no duplicate) ────────────────
        _post(hp, "/principal-chain", {"did": TEST_DID_A, "role": "owner"})
        s, b = _get(hp, "/principal-chain")
        assert b.get("count") == 1,   f"PC-4 still 1 after upsert: {b}"
        assert b["principal_chain"][0]["role"] == "owner", f"PC-4 role updated: {b}"

        # ── PC-4b: Add second entry ───────────────────────────────────────────
        _post(hp, "/principal-chain", {"did": TEST_DID_B, "role": "delegator"})
        s, b = _get(hp, "/principal-chain")
        assert b.get("count") == 2,   f"PC-4b count: {b}"

        # ── PC-5: DELETE /principal-chain/<did> ───────────────────────────────
        s, b = _delete(hp, f"/principal-chain/{TEST_DID_A}")
        assert s == 200,              f"PC-5 status: {s}"
        assert b.get("ok") is True,   f"PC-5 ok: {b}"
        assert b.get("removed") is True, f"PC-5 removed: {b}"
        assert b.get("count") == 1,   f"PC-5 count: {b}"

        # ── PC-6: DELETE non-existent DID → 404 ──────────────────────────────
        s, b = _delete(hp, f"/principal-chain/{TEST_DID_A}")
        assert s == 404,              f"PC-6 status: {s}"
        assert b.get("removed") is False, f"PC-6 removed=False: {b}"

        # ── PC-7: AgentCard trust block has principal_chain when populated ────
        with urllib.request.urlopen(f"http://127.0.0.1:{hp}/.well-known/acp.json", timeout=3) as r:
            acp = json.loads(r.read())
        card_self = acp.get("self") or acp
        trust = card_self.get("trust", {})
        # B is still in chain
        chain_in_card = trust.get("principal_chain", [])
        assert len(chain_in_card) >= 1, f"PC-7 trust.principal_chain: {trust}"
        assert any(e.get("did") == TEST_DID_B for e in chain_in_card), f"PC-7 B in chain: {chain_in_card}"

        # ── PC-8: After clearing, trust.principal_chain is absent/empty ───────
        _delete(hp, f"/principal-chain/{TEST_DID_B}")
        with urllib.request.urlopen(f"http://127.0.0.1:{hp}/.well-known/acp.json", timeout=3) as r:
            acp2 = json.loads(r.read())
        trust2 = (acp2.get("self") or acp2).get("trust", {})
        assert not trust2.get("principal_chain"), f"PC-8 chain absent after clear: {trust2}"

        # ── PC-9: GET /peers/{id}/principal-chain — unknown peer → 404 ────────
        s, b = _get(hp, "/peers/nonexistent_xyz/principal-chain")
        assert s == 404,              f"PC-9 status: {s}"
        assert b.get("error_code") == "ERR_PEER_NOT_FOUND", f"PC-9 code: {b}"

        # ── PC-10: GET /peers/{id}/principal-chain — peer with chain → 200 ────
        PEER_CHAIN = [
            {"did": "did:acp:RemoteOrch", "role": "orchestrator"},
            {"did": "did:acp:RemoteOwner", "role": "owner"},
        ]
        peer_id = _inject_peer_with_chain(hp, "ChainedPeer", PEER_CHAIN)
        s, b = _get(hp, f"/peers/{peer_id}/principal-chain")
        assert s == 200,              f"PC-10 status: {s} {b}"
        assert b.get("ok") is True,   f"PC-10 ok: {b}"
        assert b.get("count") == 2,   f"PC-10 count: {b}"
        assert b.get("source") == "agent_card", f"PC-10 source: {b}"
        returned_chain = b.get("principal_chain", [])
        assert len(returned_chain) == 2, f"PC-10 chain len: {returned_chain}"

    finally:
        proc.terminate()
