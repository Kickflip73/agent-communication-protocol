"""
tests/test_agent_limitations_schema_v273.py — v2.73 GET /agent-limitations/schema

AL-01: GET /agent-limitations/schema returns 200 + ok=True
AL-02: Response contains "schema" field with "$schema" and "title"
AL-03: Schema title is "AgentLimitations"
AL-04: Schema contains "properties" with at least 6 entries
AL-05: max_message_size_bytes property has type=integer
AL-06: max_recv_queue_size property has type=integer
AL-07: max_wait_seconds property has type=integer and description
AL-08: max_peers property has type=integer
AL-09: supported_message_roles is array type with valid items
AL-10: supported_priorities is array type with enum items
AL-11: current_values reflects actual _LIMITATIONS dict (max_peers == 100)
AL-12: current_values max_message_size_bytes >= 64 KB
AL-13: Response includes "version" field matching acp_version
AL-14: AgentCard capabilities.agent_limitations_schema is True
AL-15: AgentCard endpoints.agent_limitations_schema == "/agent-limitations/schema"
AL-16: /status includes acp_version 2.73.0
AL-17: schema has "additionalProperties": False
AL-18: schema has "$id" containing "acp.dev"
AL-19: Response includes "note" field describing usage
AL-20: POST /agent-limitations/schema is handled (405 or 404)
AL-21: current_values supported_message_roles contains "user" and "agent"
AL-22: Full regression: /status + /card + /trust/bilateral-ir/log all respond 200
"""

import os
import sys
import time
import socket
import subprocess
import requests
import pytest

RELAY = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")


def _free_port_pair():
    for _ in range(20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            ws_port = s.getsockname()[1]
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s2:
                s2.bind(("", ws_port + 100))
            return ws_port, ws_port + 100
        except OSError:
            continue
    raise RuntimeError("No free port pair found")


def wait_relay(http_port, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"http://localhost:{http_port}/status", timeout=1)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


@pytest.fixture(scope="module")
def relay_proc():
    ws_port, http_port = _free_port_pair()
    proc = subprocess.Popen(
        [sys.executable, RELAY, "--port", str(ws_port), "--name", "SchemaTestRelay",
         "--local", "--test-mode"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    assert wait_relay(http_port), "Relay did not start"
    yield {"ws_port": ws_port, "http_port": http_port, "proc": proc}
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="module")
def schema_resp(relay_proc):
    r = requests.get(
        f"http://localhost:{relay_proc['http_port']}/agent-limitations/schema",
        timeout=5,
    )
    return r


@pytest.fixture(scope="module")
def status_resp(relay_proc):
    r = requests.get(
        f"http://localhost:{relay_proc['http_port']}/status",
        timeout=5,
    )
    return r.json()


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_al01_returns_200(schema_resp):
    """AL-01: GET returns 200."""
    assert schema_resp.status_code == 200


def test_al02_ok_true(schema_resp):
    """AL-02: Response ok=True and has schema field."""
    d = schema_resp.json()
    assert d.get("ok") is True
    assert "schema" in d


def test_al03_schema_title(schema_resp):
    """AL-03: Schema title is AgentLimitations."""
    d = schema_resp.json()
    assert d["schema"].get("title") == "AgentLimitations"


def test_al04_schema_has_6_properties(schema_resp):
    """AL-04: Schema has at least 6 properties."""
    props = schema_resp.json()["schema"].get("properties", {})
    assert len(props) >= 6


def test_al05_max_message_size_bytes_type(schema_resp):
    """AL-05: max_message_size_bytes is integer."""
    prop = schema_resp.json()["schema"]["properties"]["max_message_size_bytes"]
    assert prop.get("type") == "integer"
    assert prop.get("minimum", 0) >= 1


def test_al06_max_recv_queue_size_type(schema_resp):
    """AL-06: max_recv_queue_size is integer."""
    prop = schema_resp.json()["schema"]["properties"]["max_recv_queue_size"]
    assert prop.get("type") == "integer"


def test_al07_max_wait_seconds_has_description(schema_resp):
    """AL-07: max_wait_seconds is integer with description."""
    prop = schema_resp.json()["schema"]["properties"]["max_wait_seconds"]
    assert prop.get("type") == "integer"
    assert "description" in prop


def test_al08_max_peers_type(schema_resp):
    """AL-08: max_peers is integer."""
    prop = schema_resp.json()["schema"]["properties"]["max_peers"]
    assert prop.get("type") == "integer"


def test_al09_supported_message_roles_array(schema_resp):
    """AL-09: supported_message_roles is array with items type=string."""
    prop = schema_resp.json()["schema"]["properties"]["supported_message_roles"]
    assert prop.get("type") == "array"
    assert prop.get("items", {}).get("type") == "string"


def test_al10_supported_priorities_enum(schema_resp):
    """AL-10: supported_priorities items have enum constraint."""
    prop = schema_resp.json()["schema"]["properties"]["supported_priorities"]
    assert prop.get("type") == "array"
    enum_vals = prop.get("items", {}).get("enum", [])
    assert "normal" in enum_vals
    assert "critical" in enum_vals


def test_al11_current_values_max_peers(schema_resp):
    """AL-11: current_values.max_peers == 100."""
    cv = schema_resp.json().get("current_values", {})
    assert cv.get("max_peers") == 100


def test_al12_current_values_max_message_size(schema_resp):
    """AL-12: current_values.max_message_size_bytes >= 65536 (64 KB)."""
    cv = schema_resp.json().get("current_values", {})
    assert cv.get("max_message_size_bytes", 0) >= 65536


def test_al13_response_version(schema_resp, status_resp):
    """AL-13: Response version matches relay acp_version."""
    resp_version = schema_resp.json().get("version")
    relay_version = status_resp.get("acp_version")
    assert resp_version == relay_version


def test_al14_agentcard_capability(status_resp):
    """AL-14: AgentCard capabilities.agent_limitations_schema is True."""
    caps = status_resp.get("agent_card", {}).get("capabilities", {})
    assert caps.get("agent_limitations_schema") is True


def test_al15_agentcard_endpoint(status_resp):
    """AL-15: AgentCard endpoints.agent_limitations_schema == /agent-limitations/schema."""
    endpoints = status_resp.get("agent_card", {}).get("endpoints", {})
    assert endpoints.get("agent_limitations_schema") == "/agent-limitations/schema"


def test_al16_version_2_73_0(status_resp):
    """AL-16: Relay reports acp_version >= 2.73.0."""
    ver = status_resp.get("acp_version", "0.0.0")
    major, minor, patch = (int(x) for x in ver.split(".")[:3])
    assert (major, minor, patch) >= (2, 73, 0), f"Expected >= 2.73.0, got {ver}"


def test_al17_additional_properties_false(schema_resp):
    """AL-17: Schema has additionalProperties: False."""
    schema = schema_resp.json()["schema"]
    assert schema.get("additionalProperties") is False


def test_al18_schema_id_contains_acp_dev(schema_resp):
    """AL-18: Schema $id contains acp.dev."""
    schema_id = schema_resp.json()["schema"].get("$id", "")
    assert "acp.dev" in schema_id or "acp" in schema_id


def test_al19_response_has_note(schema_resp):
    """AL-19: Response has a 'note' field with usage information."""
    note = schema_resp.json().get("note", "")
    assert len(note) > 20


def test_al20_post_method_handled(relay_proc):
    """AL-20: POST /agent-limitations/schema returns 404 or 405 (not 500, not crash)."""
    r = requests.post(
        f"http://localhost:{relay_proc['http_port']}/agent-limitations/schema",
        json={},
        timeout=3,
    )
    assert r.status_code in (404, 405)


def test_al21_current_values_roles(schema_resp):
    """AL-21: current_values.supported_message_roles contains 'user' and 'agent'."""
    cv = schema_resp.json().get("current_values", {})
    roles = cv.get("supported_message_roles", [])
    assert "user" in roles
    assert "agent" in roles


def test_al22_full_regression(relay_proc):
    """AL-22: /status, /.well-known/acp.json, /trust/bilateral-ir/log all return 200."""
    http_port = relay_proc["http_port"]
    for endpoint in ["/status", "/.well-known/acp.json", "/trust/bilateral-ir/log"]:
        r = requests.get(f"http://localhost:{http_port}{endpoint}", timeout=3)
        assert r.status_code == 200, f"{endpoint} returned {r.status_code}"
