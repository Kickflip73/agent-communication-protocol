"""
ACP v2.79 — GET /protocol-binding + AgentCard protocol_binding declaration
A2A §5.8 custom protocol binding URI identification.
PB-01 .. PB-25
"""

import time
import subprocess
import sys
import os
import pytest
import requests

PORT     = 18803
HTTP     = 18903
BASE_URL = f"http://localhost:{HTTP}"

RELAY_PY  = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")
PB_URL    = f"{BASE_URL}/protocol-binding"
CARD_URL  = f"{BASE_URL}/.well-known/acp.json"


@pytest.fixture(scope="module")
def relay():
    proc = subprocess.Popen(
        [sys.executable, RELAY_PY, "--port", str(PORT), "--name", "test-v279", "--test-mode"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(3.5)
    yield proc
    proc.terminate()
    proc.wait()


# ─── PB-01..PB-05: Basic endpoint ─────────────────────────────────────────────

def test_pb01_get_protocol_binding_200(relay):
    """PB-01: GET /protocol-binding returns 200."""
    r = requests.get(PB_URL, timeout=5)
    assert r.status_code == 200


def test_pb02_ok_true(relay):
    """PB-02: Response has ok=True."""
    d = requests.get(PB_URL, timeout=5).json()
    assert d.get("ok") is True


def test_pb03_binding_uri_present(relay):
    """PB-03: binding_uri field is present."""
    d = requests.get(PB_URL, timeout=5).json()
    assert "binding_uri" in d


def test_pb04_binding_uri_value(relay):
    """PB-04: binding_uri is urn:acp:binding:p2p-relay/v1."""
    d = requests.get(PB_URL, timeout=5).json()
    assert d.get("binding_uri") == "urn:acp:binding:p2p-relay/v1"


def test_pb05_version_field(relay):
    """PB-05: Response includes version >= 2.79."""
    d = requests.get(PB_URL, timeout=5).json()
    version = d.get("version", "")
    major, minor, *_ = version.split(".")
    assert (int(major), int(minor)) >= (2, 79), f"Expected >= 2.79, got {version}"


# ─── PB-06..PB-10: Required fields ────────────────────────────────────────────

def test_pb06_binding_name(relay):
    """PB-06: binding_name is present and non-empty."""
    d = requests.get(PB_URL, timeout=5).json()
    assert d.get("binding_name"), "binding_name missing or empty"


def test_pb07_transport(relay):
    """PB-07: transport field is present and non-empty."""
    d = requests.get(PB_URL, timeout=5).json()
    assert d.get("transport"), "transport field missing or empty"


def test_pb08_addressing_scheme(relay):
    """PB-08: addressing field contains acp:// scheme."""
    d = requests.get(PB_URL, timeout=5).json()
    addressing = d.get("addressing", "")
    assert "acp://" in addressing, f"Expected acp:// in addressing, got: {addressing}"


def test_pb09_nat_traversal_true(relay):
    """PB-09: nat_traversal is True."""
    d = requests.get(PB_URL, timeout=5).json()
    assert d.get("nat_traversal") is True


def test_pb10_nat_levels(relay):
    """PB-10: nat_levels is 3."""
    d = requests.get(PB_URL, timeout=5).json()
    assert d.get("nat_levels") == 3


# ─── PB-11..PB-15: Streaming + spec fields ────────────────────────────────────

def test_pb11_supports_sse(relay):
    """PB-11: supports_sse is True."""
    d = requests.get(PB_URL, timeout=5).json()
    assert d.get("supports_sse") is True


def test_pb12_supports_ws(relay):
    """PB-12: supports_ws is True."""
    d = requests.get(PB_URL, timeout=5).json()
    assert d.get("supports_ws") is True


def test_pb13_description_present(relay):
    """PB-13: description field is present and non-empty."""
    d = requests.get(PB_URL, timeout=5).json()
    assert d.get("description"), "description missing or empty"


def test_pb14_a2a_ref_pr1619(relay):
    """PB-14: a2a_ref references PR #1619."""
    d = requests.get(PB_URL, timeout=5).json()
    a2a_ref = d.get("a2a_ref", "")
    assert "1619" in a2a_ref, f"Expected PR #1619 in a2a_ref, got: {a2a_ref}"


def test_pb15_spec_url_present(relay):
    """PB-15: spec_url field is present."""
    d = requests.get(PB_URL, timeout=5).json()
    assert "spec_url" in d
    assert d["spec_url"].startswith("https://")


# ─── PB-16..PB-20: Method validation + AgentCard integration ──────────────────

def test_pb16_post_method_not_allowed(relay):
    """PB-16: POST /protocol-binding returns 405."""
    r = requests.post(PB_URL, json={}, timeout=5)
    assert r.status_code == 405
    assert r.json().get("code") == "ERR_METHOD_NOT_ALLOWED"


def test_pb17_agentcard_has_protocol_binding_field(relay):
    """PB-17: AgentCard top-level includes protocol_binding field."""
    d = requests.get(CARD_URL, timeout=5).json()
    self_card = d.get("self", d)
    assert "protocol_binding" in self_card, "protocol_binding missing from AgentCard"


def test_pb18_agentcard_protocol_binding_uri(relay):
    """PB-18: AgentCard protocol_binding.binding_uri matches endpoint."""
    d = requests.get(CARD_URL, timeout=5).json()
    self_card = d.get("self", d)
    pb = self_card.get("protocol_binding", {})
    assert pb.get("binding_uri") == "urn:acp:binding:p2p-relay/v1"


def test_pb19_capabilities_protocol_binding_true(relay):
    """PB-19: AgentCard capabilities.protocol_binding is True."""
    d = requests.get(CARD_URL, timeout=5).json()
    caps = d.get("self", d).get("capabilities", {})
    assert caps.get("protocol_binding") is True


def test_pb20_endpoints_protocol_binding(relay):
    """PB-20: AgentCard endpoints includes protocol_binding path."""
    d = requests.get(CARD_URL, timeout=5).json()
    endpoints = d.get("self", d).get("endpoints", {})
    assert "protocol_binding" in endpoints
    assert endpoints["protocol_binding"] == "/protocol-binding"


# ─── PB-21..PB-25: Content consistency + A2A §5.8 alignment ──────────────────

def test_pb21_binding_version_present(relay):
    """PB-21: binding_version field is present."""
    d = requests.get(PB_URL, timeout=5).json()
    assert "binding_version" in d


def test_pb22_base_protocol_present(relay):
    """PB-22: base_protocol field is present and non-empty."""
    d = requests.get(PB_URL, timeout=5).json()
    assert d.get("base_protocol"), "base_protocol missing or empty"


def test_pb23_agentcard_and_endpoint_consistent(relay):
    """PB-23: AgentCard protocol_binding and /protocol-binding return same binding_uri."""
    card_d = requests.get(CARD_URL, timeout=5).json()
    pb_d = requests.get(PB_URL, timeout=5).json()
    card_pb = card_d.get("self", card_d).get("protocol_binding", {})
    assert card_pb.get("binding_uri") == pb_d.get("binding_uri")


def test_pb24_binding_uri_is_urn(relay):
    """PB-24: binding_uri follows URN scheme (urn:acp:...)."""
    d = requests.get(PB_URL, timeout=5).json()
    assert d.get("binding_uri", "").startswith("urn:acp:"), \
        f"Expected urn:acp: prefix, got: {d.get('binding_uri')}"


def test_pb25_version_is_2_79(relay):
    """PB-25: VERSION is 2.79.x (development round complete)."""
    d = requests.get(CARD_URL, timeout=5).json()
    version = d.get("self", d).get("version", "")
    major, minor, *_ = version.split(".")
    assert (int(major), int(minor)) >= (2, 79), f"Expected >= 2.79, got {version}"
