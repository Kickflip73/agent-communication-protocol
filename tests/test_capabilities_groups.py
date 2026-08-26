"""
test_capabilities_groups.py — ACP v0.9 AgentCard capabilities.groups

Tests the structured grouping of flat capabilities fields, aligned with A2A v1.0
AgentCapabilities structure.  The groups field is a nested object inside the
existing flat capabilities dict, keeping full backward compatibility.

Group definitions:
  messaging   — message transport quality features
  tasks       — task lifecycle management features
  identity    — cryptographic identity & signing features
  transport   — protocol transport binding features
  discovery   — agent discovery & metadata features

Tests:
  CG1: capabilities.groups exists in AgentCard response (/.well-known/acp.json)
  CG2: groups.messaging contains correct fields
  CG3: groups.tasks contains correct fields
  CG4: groups.identity contains correct fields
  CG5: groups.transport contains correct fields
  CG6: groups.discovery contains correct fields
  CG7: legacy flat capabilities fields still present (backward compat)
  CG8: GET /status also returns capabilities.groups (via agent_card)
"""

import json
import pytest
import subprocess
import time
import sys
import os
import urllib.request
import urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RELAY_PATH = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _free_port():
    """Return an OS-assigned free WS port where port AND port+100 are both free."""
    import socket
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
    raise RuntimeError("Could not find a free port pair (ws + ws+100)")


WS_PORT   = _free_port()
HTTP_PORT = WS_PORT + 100

_proc = None


def _make_env():
    env = os.environ.copy()
    for k in ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY"):
        env.pop(k, None)
    return env


def _wait_ready(timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://localhost:{HTTP_PORT}/.well-known/acp.json", timeout=1
            ) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.2)
    return False


def _get(path):
    """GET path, return (http_status, parsed_json)."""
    req = urllib.request.Request(f"http://localhost:{HTTP_PORT}{path}")
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _agent_card():
    """Fetch /.well-known/acp.json and return the 'self' sub-object (the actual AgentCard)."""
    status, data = _get("/.well-known/acp.json")
    assert status == 200, f"/.well-known/acp.json returned {status}: {data}"
    assert "self" in data, f"/.well-known/acp.json response missing 'self' key; got: {list(data.keys())}"
    return data["self"]


# ─────────────────────────────────────────────────────────────────────────────
# Fixture: single relay (module-scoped, shared across all CG tests)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def single_relay():
    global _proc
    env = _make_env()
    _proc = subprocess.Popen(
        [sys.executable, RELAY_PATH, "--port", str(WS_PORT), "--name", "CGAgent"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
    )
    if not _wait_ready():
        _proc.kill()
        out, err = _proc.communicate()
        pytest.fail(
            f"Relay (HTTP:{HTTP_PORT}) did not start in time.\n"
            f"stdout: {out.decode()[:500]}\nstderr: {err.decode()[:500]}"
        )
    yield
    _proc.terminate()
    try:
        _proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        _proc.kill()
        _proc.wait()


# ─────────────────────────────────────────────────────────────────────────────
# CG1 — capabilities.groups exists in AgentCard
# ─────────────────────────────────────────────────────────────────────────────

def test_cg1_groups_exists():
    """CG1: capabilities.groups must exist in /.well-known/acp.json response."""
    card = _agent_card()
    caps = card.get("capabilities", {})
    assert "groups" in caps, (
        f"capabilities.groups missing from AgentCard. capabilities keys: {list(caps.keys())}"
    )
    groups = caps["groups"]
    assert isinstance(groups, dict), f"capabilities.groups must be a dict, got {type(groups)}"


# ─────────────────────────────────────────────────────────────────────────────
# CG2 — groups.messaging
# ─────────────────────────────────────────────────────────────────────────────

def test_cg2_messaging_group():
    """CG2: groups.messaging must contain the correct fields."""
    card = _agent_card()
    groups = card["capabilities"]["groups"]
    assert "messaging" in groups, f"groups.messaging missing. groups keys: {list(groups.keys())}"
    msg = groups["messaging"]
    required_fields = {"priority", "long_poll", "history", "broadcast", "delivery_ack"}
    missing = required_fields - set(msg.keys())
    assert not missing, f"groups.messaging missing fields: {missing}. got: {msg}"
    for k, v in msg.items():
        assert isinstance(v, bool), f"groups.messaging.{k} must be bool, got {type(v).__name__}"


# ─────────────────────────────────────────────────────────────────────────────
# CG3 — groups.tasks
# ─────────────────────────────────────────────────────────────────────────────

def test_cg3_tasks_group():
    """CG3: groups.tasks must contain the correct fields."""
    card = _agent_card()
    groups = card["capabilities"]["groups"]
    assert "tasks" in groups, f"groups.tasks missing. groups keys: {list(groups.keys())}"
    tasks = groups["tasks"]
    required_fields = {"pagination", "filtering", "state_machine"}
    missing = required_fields - set(tasks.keys())
    assert not missing, f"groups.tasks missing fields: {missing}. got: {tasks}"
    for k, v in tasks.items():
        assert isinstance(v, bool), f"groups.tasks.{k} must be bool, got {type(v).__name__}"


# ─────────────────────────────────────────────────────────────────────────────
# CG4 — groups.identity
# ─────────────────────────────────────────────────────────────────────────────

def test_cg4_identity_group():
    """CG4: groups.identity must contain the correct fields."""
    card = _agent_card()
    groups = card["capabilities"]["groups"]
    assert "identity" in groups, f"groups.identity missing. groups keys: {list(groups.keys())}"
    identity = groups["identity"]
    required_fields = {"hmac", "ed25519", "jwks", "card_signature"}
    missing = required_fields - set(identity.keys())
    assert not missing, f"groups.identity missing fields: {missing}. got: {identity}"
    for k, v in identity.items():
        assert isinstance(v, bool), f"groups.identity.{k} must be bool, got {type(v).__name__}"


# ─────────────────────────────────────────────────────────────────────────────
# CG5 — groups.transport
# ─────────────────────────────────────────────────────────────────────────────

def test_cg5_transport_group():
    """CG5: groups.transport must contain the correct fields."""
    card = _agent_card()
    groups = card["capabilities"]["groups"]
    assert "transport" in groups, f"groups.transport missing. groups keys: {list(groups.keys())}"
    transport = groups["transport"]
    required_fields = {"sse", "http2", "p2p_direct", "dcutr", "relay_fallback"}
    missing = required_fields - set(transport.keys())
    assert not missing, f"groups.transport missing fields: {missing}. got: {transport}"
    for k, v in transport.items():
        assert isinstance(v, bool), f"groups.transport.{k} must be bool, got {type(v).__name__}"


# ─────────────────────────────────────────────────────────────────────────────
# CG6 — groups.discovery
# ─────────────────────────────────────────────────────────────────────────────

def test_cg6_discovery_group():
    """CG6: groups.discovery must contain the correct fields."""
    card = _agent_card()
    groups = card["capabilities"]["groups"]
    assert "discovery" in groups, f"groups.discovery missing. groups keys: {list(groups.keys())}"
    discovery = groups["discovery"]
    required_fields = {"skills", "skills_openapi_spec", "limitations", "availability_schedule"}
    missing = required_fields - set(discovery.keys())
    assert not missing, f"groups.discovery missing fields: {missing}. got: {discovery}"
    for k, v in discovery.items():
        assert isinstance(v, bool), f"groups.discovery.{k} must be bool, got {type(v).__name__}"


# ─────────────────────────────────────────────────────────────────────────────
# CG7 — legacy flat capabilities fields still present (backward compat)
# ─────────────────────────────────────────────────────────────────────────────

def test_cg7_flat_capabilities_backward_compat():
    """CG7: Legacy flat capabilities fields must still be present (backward compatibility)."""
    card = _agent_card()
    caps = card.get("capabilities", {})

    legacy_fields = [
        # v0.6–v0.8 core
        "streaming", "push_notifications", "input_required", "multi_session",
        "hmac_signing", "lan_discovery", "context_id", "error_codes", "identity",
        # v1.x
        "did_identity", "availability", "extensions", "http2", "card_sig",
        "auto_card_verify", "offline_queue",
        # v2.x
        "lan_port_scan", "supported_transports", "sse_seq", "task_cancelling",
        "ws_stream", "event_replay", "trust_signals", "context_query",
        "delegation_chain", "availability_schedule", "trust_jwks",
        "limitations_structured", "limitations_patch", "limitations_filter",
        "peers_broadcast", "peers_broadcast_subset", "peers_broadcast_history",
        "peer_card_query", "peer_ping", "skills_query_constraints",
        "peers_pagination", "peers_vouch_chain", "skill_limitations",
        "skill_status_probe", "skill_limitations_patch", "error_failed_msg_id",
        "message_dedup", "pubkey_discovery", "peer_trust", "delivery_ack",
        "read_receipt", "typing_indicator", "message_priority", "recv_long_poll",
        "agent_limitations", "skills_openapi_spec",
        # v0.9
        "tasks_pagination",
    ]

    missing = [f for f in legacy_fields if f not in caps]
    assert not missing, (
        f"Backward-compat FAIL: these flat capabilities keys are missing: {missing}\n"
        f"capabilities keys present: {sorted(caps.keys())}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# CG8 — GET /status also returns capabilities.groups (via agent_card)
# ─────────────────────────────────────────────────────────────────────────────

def test_cg8_status_includes_groups():
    """CG8: GET /status must also surface capabilities.groups via agent_card field."""
    status, data = _get("/status")
    assert status == 200, f"GET /status returned {status}"
    agent_card = data.get("agent_card")
    assert agent_card is not None, (
        "GET /status response missing 'agent_card' field. "
        "This field should be populated after relay startup."
    )
    caps = agent_card.get("capabilities", {})
    assert "groups" in caps, (
        f"capabilities.groups missing from /status agent_card.capabilities. "
        f"capabilities keys: {list(caps.keys())}"
    )
    groups = caps["groups"]
    assert isinstance(groups, dict), f"capabilities.groups must be dict, got {type(groups)}"
    for group_name in ("messaging", "tasks", "identity", "transport", "discovery"):
        assert group_name in groups, (
            f"groups.{group_name} missing from /status capabilities.groups. "
            f"got groups keys: {list(groups.keys())}"
        )
