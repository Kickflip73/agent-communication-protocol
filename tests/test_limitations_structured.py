"""
test_limitations_structured.py — ACP v2.20 Structured Limitations[] Tests

Tests for LimitationObject format in AgentCard.
Ref: A2A IS#1694 — stable vs runtime limitations split

Test IDs: LIM-01 through LIM-18
"""

import json
import pytest
import subprocess
import sys
import time
import os
import requests
import signal

RELAY_PATH = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")

# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def start_relay(ws_port: int, extra_args: list[str] = None, wait: float = 3.5) -> subprocess.Popen:
    cmd = [
        sys.executable, RELAY_PATH,
        "--port", str(ws_port),
        "--name", f"test-agent-lim-{ws_port}",
    ]
    if extra_args:
        cmd.extend(extra_args)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(wait)
    return proc


def http_port(ws_port: int) -> int:
    """HTTP port = WS port + 100 (ACP relay convention)."""
    return ws_port + 100


def stop_relay(proc: subprocess.Popen):
    if proc and proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def get_card(ws_port: int) -> dict:
    """Fetch AgentCard from /.well-known/acp.json (HTTP port = WS port + 100)."""
    hp = http_port(ws_port)
    r = requests.get(f"http://127.0.0.1:{hp}/.well-known/acp.json", timeout=5)
    r.raise_for_status()
    raw = r.json()
    return raw.get("self", raw)  # unwrap {"self": {...}} envelope


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

WS_NO_LIM   = 18520
WS_CSV_LIM  = 18521
WS_JSON_LIM = 18522
WS_MIX_LIM  = 18523


@pytest.fixture(scope="module")
def relay_no_limitations():
    proc = start_relay(WS_NO_LIM)
    yield proc
    stop_relay(proc)


@pytest.fixture(scope="module")
def relay_csv_limitations():
    proc = start_relay(WS_CSV_LIM, ["--limitations", "no_file_access,no_internet"])
    yield proc
    stop_relay(proc)


@pytest.fixture(scope="module")
def relay_json_limitations():
    limitations = json.dumps([
        {"kind": "modality", "code": "image-input-unsupported",
         "message": "Cannot process images", "permanent": True},
        {"kind": "scale", "code": "max-10mb",
         "message": "Max 10MB files", "permanent": True},
        {"kind": "capability", "code": "no_internet",
         "message": "No outbound internet access", "permanent": False},
    ])
    proc = start_relay(WS_JSON_LIM, ["--limitations-json", limitations])
    yield proc
    stop_relay(proc)


@pytest.fixture(scope="module")
def relay_mixed_kinds():
    limitations = json.dumps([
        {"kind": "domain", "code": "english-only", "message": "English only", "permanent": True},
        {"kind": "access", "code": "no_write", "message": "Read-only mode", "permanent": False},
        {"kind": "other", "code": "beta-feature", "message": "Beta limitations apply"},
    ])
    proc = start_relay(WS_MIX_LIM, ["--limitations-json", limitations])
    yield proc
    stop_relay(proc)


# ─────────────────────────────────────────────────────────────
# LIM-01 – LIM-03: No limitations (default)
# ─────────────────────────────────────────────────────────────

class TestNoLimitations:
    def test_LIM01_limitations_field_present(self, relay_no_limitations):
        """AgentCard must contain 'limitations' field even when empty"""
        card = get_card(WS_NO_LIM)
        assert "limitations" in card, "AgentCard missing 'limitations' field"

    def test_LIM02_limitations_empty_array(self, relay_no_limitations):
        """Default limitations must be empty array"""
        card = get_card(WS_NO_LIM)
        assert card["limitations"] == [], f"Expected [], got {card['limitations']}"

    def test_LIM03_capabilities_limitations_structured_true(self, relay_no_limitations):
        """capabilities.limitations_structured must be True (signals v2.20 format)"""
        card = get_card(WS_NO_LIM)
        caps = card.get("capabilities", {})
        assert caps.get("limitations_structured") is True, \
            f"capabilities.limitations_structured not True: {caps.get('limitations_structured')}"


# ─────────────────────────────────────────────────────────────
# LIM-04 – LIM-09: CSV string → LimitationObject promotion
# ─────────────────────────────────────────────────────────────

class TestCSVLimitations:
    def test_LIM04_two_entries_created(self, relay_csv_limitations):
        """--limitations 'a,b' must produce 2 LimitationObject entries"""
        card = get_card(WS_CSV_LIM)
        lims = card["limitations"]
        assert len(lims) == 2, f"Expected 2 limitations, got {len(lims)}: {lims}"

    def test_LIM05_each_entry_is_object(self, relay_csv_limitations):
        """Each limitation must be a dict (LimitationObject), not a string"""
        card = get_card(WS_CSV_LIM)
        for lim in card["limitations"]:
            assert isinstance(lim, dict), f"Limitation is not a dict: {lim!r}"

    def test_LIM06_required_fields_present(self, relay_csv_limitations):
        """Each LimitationObject must have: kind, code, message, permanent"""
        card = get_card(WS_CSV_LIM)
        for lim in card["limitations"]:
            for field in ("kind", "code", "message", "permanent"):
                assert field in lim, f"Missing field '{field}' in limitation: {lim}"

    def test_LIM07_csv_default_kind_capability(self, relay_csv_limitations):
        """CSV-promoted limitations must default to kind='capability'"""
        card = get_card(WS_CSV_LIM)
        for lim in card["limitations"]:
            assert lim["kind"] == "capability", \
                f"Expected kind=capability for CSV-promoted, got: {lim['kind']}"

    def test_LIM08_csv_default_permanent_true(self, relay_csv_limitations):
        """CSV-promoted limitations must default to permanent=True"""
        card = get_card(WS_CSV_LIM)
        for lim in card["limitations"]:
            assert lim["permanent"] is True, \
                f"Expected permanent=True for CSV-promoted, got: {lim['permanent']}"

    def test_LIM09_csv_codes_preserved(self, relay_csv_limitations):
        """CSV-promoted limitation codes must match input strings"""
        card = get_card(WS_CSV_LIM)
        codes = {lim["code"] for lim in card["limitations"]}
        assert "no_file_access" in codes, f"'no_file_access' not found in codes: {codes}"
        assert "no_internet" in codes, f"'no_internet' not found in codes: {codes}"


# ─────────────────────────────────────────────────────────────
# LIM-10 – LIM-15: JSON structured limitations
# ─────────────────────────────────────────────────────────────

class TestJSONLimitations:
    def test_LIM10_three_entries_created(self, relay_json_limitations):
        """--limitations-json with 3 entries must produce 3 LimitationObject entries"""
        card = get_card(WS_JSON_LIM)
        lims = card["limitations"]
        assert len(lims) == 3, f"Expected 3 limitations, got {len(lims)}: {lims}"

    def test_LIM11_kinds_preserved(self, relay_json_limitations):
        """LimitationObject kinds must be preserved from JSON input"""
        card = get_card(WS_JSON_LIM)
        kinds = {lim["code"]: lim["kind"] for lim in card["limitations"]}
        assert kinds["image-input-unsupported"] == "modality"
        assert kinds["max-10mb"] == "scale"
        assert kinds["no_internet"] == "capability"

    def test_LIM12_permanent_preserved(self, relay_json_limitations):
        """LimitationObject permanent flag must be preserved"""
        card = get_card(WS_JSON_LIM)
        perms = {lim["code"]: lim["permanent"] for lim in card["limitations"]}
        assert perms["image-input-unsupported"] is True
        assert perms["max-10mb"] is True
        assert perms["no_internet"] is False  # runtime degradation

    def test_LIM13_messages_preserved(self, relay_json_limitations):
        """LimitationObject messages must be preserved from JSON input"""
        card = get_card(WS_JSON_LIM)
        msgs = {lim["code"]: lim["message"] for lim in card["limitations"]}
        assert "Cannot process images" in msgs["image-input-unsupported"]
        assert "Max 10MB" in msgs["max-10mb"]

    def test_LIM14_stable_runtime_split(self, relay_json_limitations):
        """Stable (permanent=True) and runtime (permanent=False) limitations coexist"""
        card = get_card(WS_JSON_LIM)
        stable = [l for l in card["limitations"] if l["permanent"] is True]
        runtime = [l for l in card["limitations"] if l["permanent"] is False]
        assert len(stable) == 2, f"Expected 2 stable limitations, got {len(stable)}"
        assert len(runtime) == 1, f"Expected 1 runtime limitation, got {len(runtime)}"

    def test_LIM15_json_overrides_csv(self):
        """--limitations-json takes precedence over --limitations (both provided)"""
        WS_PORT = 18525
        lim_json = json.dumps([{"kind": "domain", "code": "json-wins", "message": "JSON wins", "permanent": True}])
        proc = start_relay(WS_PORT, [
            "--limitations", "csv-entry",
            "--limitations-json", lim_json,
        ])
        try:
            card = get_card(WS_PORT)
            codes = [l["code"] for l in card["limitations"]]
            assert "json-wins" in codes, f"JSON entry not found: {codes}"
            assert "csv-entry" not in codes, f"CSV entry should be overridden: {codes}"
        finally:
            stop_relay(proc)


# ─────────────────────────────────────────────────────────────
# LIM-16 – LIM-18: Kind validation and edge cases
# ─────────────────────────────────────────────────────────────

class TestLimitationKinds:
    def test_LIM16_all_valid_kinds_accepted(self, relay_mixed_kinds):
        """All 6 valid kinds must be accepted: capability|modality|scale|domain|access|other"""
        card = get_card(WS_MIX_LIM)
        kinds = {lim["kind"] for lim in card["limitations"]}
        assert "domain" in kinds
        assert "access" in kinds
        assert "other" in kinds

    def test_LIM17_invalid_kind_coerced_to_other(self):
        """Invalid kind values must be coerced to 'other'"""
        WS_PORT = 18526
        lim_json = json.dumps([{"kind": "INVALID_KIND", "code": "test", "message": "test"}])
        proc = start_relay(WS_PORT, ["--limitations-json", lim_json])
        try:
            card = get_card(WS_PORT)
            lims = card["limitations"]
            assert len(lims) == 1
            assert lims[0]["kind"] == "other", \
                f"Invalid kind should be coerced to 'other', got: {lims[0]['kind']}"
        finally:
            stop_relay(proc)

    def test_LIM18_permanent_defaults_true_when_omitted(self, relay_mixed_kinds):
        """permanent field must default to True when omitted in JSON input"""
        card = get_card(WS_MIX_LIM)
        # "beta-feature" entry had no permanent field — should default to True
        beta = next((l for l in card["limitations"] if l["code"] == "beta-feature"), None)
        assert beta is not None, "beta-feature limitation not found"
        assert beta["permanent"] is True, \
            f"permanent should default to True when omitted, got: {beta['permanent']}"
