"""
test_peers_pagination.py — ACP v2.27 GET /peers pagination + filter + vouch_chain

Tests:
  PP1:  GET /peers no params — backward compat, returns pagination block
  PP2:  GET /peers?limit=1&offset=0 — first page (1 item)
  PP3:  GET /peers?limit=1&offset=1 — second page (1 item)
  PP4:  GET /peers?limit=50&offset=99 — offset beyond total → empty page, has_more=false
  PP5:  GET /peers?filter=connected — only connected peers
  PP6:  GET /peers?filter=disconnected — only disconnected peers
  PP7:  GET /peers?filter=all — same as no filter
  PP8:  GET /peers?filter=invalid — returns 400 ERR_INVALID_FILTER
  PP9:  GET /peers — response includes total/total_filtered/active fields
  PP10: GET /peers?limit=bad — falls back to default 50, no error
  PP11: GET /peers — pagination.next_offset is null when no more pages
  PP12: GET /peers — pagination.next_offset is correct when has_more=true
  VC1:  POST /trust/vouch — add a vouch entry
  VC2:  GET /trust/vouch — list vouch entries
  VC3:  POST /trust/vouch missing voucher_did → 400
  VC4:  GET /trust/vouch pagination — limit/offset
  VC5:  AgentCard trust.signals includes vouch_chain type after adding entry
"""

import json
import pytest
import subprocess
import time
import urllib.request
import urllib.error
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RELAY_PATH = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")


def _find_free_port() -> int:
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def relay():
    """Start a relay instance for the module; yield HTTP base URL; stop on teardown."""
    ws_port   = _find_free_port()
    http_port = ws_port + 100   # HTTP API = WS port + 100 (per relay convention)
    proc = subprocess.Popen(
        [sys.executable, RELAY_PATH, "--port", str(ws_port), "--name", "TestAgent"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    base = f"http://127.0.0.1:{http_port}"
    # Wait for relay to be ready (up to 15s)
    for _ in range(75):
        try:
            urllib.request.urlopen(f"{base}/.well-known/acp.json", timeout=1)
            break
        except Exception:
            time.sleep(0.2)
    else:
        proc.kill()
        raise RuntimeError(f"Relay (HTTP:{http_port}) did not start in time")
    yield base
    proc.kill()
    proc.wait()


def _get(base: str, path: str) -> tuple:
    """GET request → (status, body_dict)."""
    try:
        with urllib.request.urlopen(f"{base}{path}", timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _post(base: str, path: str, body: dict) -> tuple:
    """POST request → (status, body_dict)."""
    data = json.dumps(body).encode()
    req  = urllib.request.Request(
        f"{base}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


# ─── Pagination Tests ─────────────────────────────────────────────────────────

def test_PP1_no_params_backward_compat(relay):
    """GET /peers without params must include pagination block (backward compat)."""
    status, body = _get(relay, "/peers")
    assert status == 200
    assert "peers" in body
    assert "pagination" in body, "v2.27: pagination block must be present"
    pg = body["pagination"]
    assert "limit" in pg
    assert "offset" in pg
    assert "filter" in pg
    assert "has_more" in pg


def test_PP2_limit_1_offset_0(relay):
    """GET /peers?limit=1&offset=0 — at most 1 item returned."""
    status, body = _get(relay, "/peers?limit=1&offset=0")
    assert status == 200
    assert len(body["peers"]) <= 1
    assert body["pagination"]["limit"] == 1
    assert body["pagination"]["offset"] == 0


def test_PP3_limit_1_offset_1(relay):
    """GET /peers?limit=1&offset=1 — page 2 (may be empty if < 2 peers)."""
    status, body = _get(relay, "/peers?limit=1&offset=1")
    assert status == 200
    assert body["pagination"]["offset"] == 1
    assert body["pagination"]["limit"] == 1


def test_PP4_offset_beyond_total(relay):
    """GET /peers?offset=999 — empty page, has_more=false."""
    status, body = _get(relay, "/peers?limit=50&offset=999")
    assert status == 200
    assert body["peers"] == []
    assert body["pagination"]["has_more"] is False
    assert body["pagination"]["next_offset"] is None


def test_PP5_filter_connected(relay):
    """GET /peers?filter=connected — all returned peers must be connected."""
    status, body = _get(relay, "/peers?filter=connected")
    assert status == 200
    assert body["pagination"]["filter"] == "connected"
    for p in body["peers"]:
        assert p["connected"] is True, f"peer {p['id']} is not connected"


def test_PP6_filter_disconnected(relay):
    """GET /peers?filter=disconnected — all returned peers must be disconnected."""
    status, body = _get(relay, "/peers?filter=disconnected")
    assert status == 200
    assert body["pagination"]["filter"] == "disconnected"
    for p in body["peers"]:
        assert p["connected"] is False, f"peer {p['id']} is connected"


def test_PP7_filter_all(relay):
    """GET /peers?filter=all — same count as no filter."""
    status_all, body_all   = _get(relay, "/peers?filter=all")
    status_none, body_none = _get(relay, "/peers")
    assert status_all == 200 and status_none == 200
    assert body_all["total"] == body_none["total"]


def test_PP8_filter_invalid_returns_400(relay):
    """GET /peers?filter=badvalue → 400 ERR_INVALID_FILTER."""
    status, body = _get(relay, "/peers?filter=badvalue")
    assert status == 400
    assert body.get("error_code") == "ERR_INVALID_FILTER"


def test_PP9_response_shape(relay):
    """GET /peers — response includes total/total_filtered/active fields."""
    status, body = _get(relay, "/peers")
    assert status == 200
    assert "total"          in body
    assert "total_filtered" in body
    assert "active"         in body
    assert isinstance(body["total"],          int)
    assert isinstance(body["total_filtered"], int)
    assert isinstance(body["active"],         int)


def test_PP10_invalid_limit_defaults(relay):
    """GET /peers?limit=abc — should not crash, return 200 with default limit."""
    status, body = _get(relay, "/peers?limit=abc")
    assert status == 200
    assert "peers" in body
    # default limit is 50
    assert body["pagination"]["limit"] == 50


def test_PP11_next_offset_null_when_no_more(relay):
    """When has_more=false, next_offset must be null."""
    status, body = _get(relay, "/peers?limit=200&offset=0")
    assert status == 200
    if not body["pagination"]["has_more"]:
        assert body["pagination"]["next_offset"] is None


def test_PP12_next_offset_correct(relay):
    """When has_more=true, next_offset == offset + limit."""
    # Artificially limit to 0 to force has_more (only works if there are peers)
    # Just verify the arithmetic formula holds when has_more is true
    # We'll use limit=1; if total>1 then has_more should be true
    status, body = _get(relay, "/peers?limit=1&offset=0")
    assert status == 200
    pg = body["pagination"]
    if pg["has_more"]:
        assert pg["next_offset"] == pg["offset"] + pg["limit"]


# ─── Vouch Chain Tests ────────────────────────────────────────────────────────

def test_VC1_post_vouch(relay):
    """POST /trust/vouch — add a vouch entry successfully."""
    status, body = _post(relay, "/trust/vouch", {
        "voucher_did": "did:acp:abc123",
        "comment":     "Verified in integration test",
    })
    assert status == 200
    assert body["ok"] is True
    assert "vouch_id" in body
    assert body["entry"]["voucher_did"] == "did:acp:abc123"
    assert body["entry"]["comment"] == "Verified in integration test"
    assert body["entry"]["vouched_at"] is not None


def test_VC2_get_vouch_list(relay):
    """GET /trust/vouch — list contains the entry added in VC1."""
    status, body = _get(relay, "/trust/vouch")
    assert status == 200
    assert body["ok"] is True
    assert body["total"] >= 1
    dids = [v["voucher_did"] for v in body["vouches"]]
    assert "did:acp:abc123" in dids


def test_VC3_post_vouch_missing_did(relay):
    """POST /trust/vouch without voucher_did → 400 ERR_MISSING_FIELD."""
    status, body = _post(relay, "/trust/vouch", {"comment": "no did provided"})
    assert status == 400
    assert body.get("error_code") == "ERR_MISSING_FIELD"


def test_VC4_get_vouch_pagination(relay):
    """GET /trust/vouch?limit=1&offset=0 — pagination works."""
    # First add a second vouch so total >= 2
    _post(relay, "/trust/vouch", {"voucher_did": "did:acp:paginationtest"})
    status, body = _get(relay, "/trust/vouch?limit=1&offset=0")
    assert status == 200
    assert len(body["vouches"]) == 1
    assert body["pagination"]["limit"] == 1
    if body["total"] > 1:
        assert body["pagination"]["has_more"] is True
        assert body["pagination"]["next_offset"] == 1


def test_VC5_agent_card_vouch_chain_signal(relay):
    """AgentCard trust.signals includes vouch_chain signal (enabled=true after vouches)."""
    status, body = _get(relay, "/.well-known/acp.json")
    assert status == 200
    agent_card = body.get("self", body)
    trust = agent_card.get("trust", {})
    signals = trust.get("signals", [])
    vouch_signals = [s for s in signals if s.get("type") == "vouch_chain"]
    assert len(vouch_signals) == 1, "Expected exactly one vouch_chain trust signal"
    sig = vouch_signals[0]
    # VC1 + VC4 each added a vouch, so enabled should be True
    assert sig["enabled"] is True
    assert sig["details"]["count"] >= 1
