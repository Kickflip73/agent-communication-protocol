"""
tests/test_governance_metadata_v292.py

v2.92: Tests for derivation_rights and credential_lifecycle fields in governance_metadata.
Validates RFC-003 schema additions (aeoess SDK v1.37.0 alignment).

Test IDs: GM01–GM16

Pattern from tests/test_governance_metadata.py:
  - HTTP API port = ws_port + 100
  - _start_relay uses --local-only --test-mode for fast startup
  - AgentCard is at /.well-known/acp.json → d.get("self") or d
  - capabilities are in AgentCard, not in /status
"""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

# ──────────────────────────────────────────────────────────────────────────────
# Helpers (matching pattern from tests/test_governance_metadata.py)
# ──────────────────────────────────────────────────────────────────────────────

RELAY_PATH = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")
_BASE_PORT = 15200   # distinct from test_governance_metadata.py's 15100


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_relay(ws_port: int, extra_args=None):
    """Start relay in local test mode. HTTP API = ws_port + 100."""
    http_port = ws_port + 100
    cmd = [sys.executable, RELAY_PATH, "--port", str(ws_port),
           "--local-only", "--test-mode"]
    if extra_args:
        cmd += extra_args
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{http_port}/status", timeout=1
            ) as r:
                if r.status == 200:
                    return proc, http_port
        except Exception:
            time.sleep(0.15)
    proc.terminate()
    raise RuntimeError(f"Relay failed to start on HTTP port {http_port}")


def _stop(proc):
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def _get(hp, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{hp}{path}", timeout=5) as r:
        return r.status, json.loads(r.read())


def _card(hp):
    """Fetch AgentCard from /.well-known/acp.json, handling self-wrapper."""
    _, raw = _get(hp, "/.well-known/acp.json")
    return raw.get("self") or raw


# ──────────────────────────────────────────────────────────────────────────────
# GM01–GM04: derivation_rights structure via GET /governance-metadata
# ──────────────────────────────────────────────────────────────────────────────

class TestDerivationRights:
    def test_GM01_governance_endpoint_200(self):
        proc, hp = _start_relay(
            _BASE_PORT,
            extra_args=["--governance-metadata", '{"trust_score": 0.85}']
        )
        try:
            status, _ = _get(hp, "/governance-metadata")
            assert status == 200
        finally:
            _stop(proc)

    def test_GM02_derivation_rights_present(self):
        proc, hp = _start_relay(
            _BASE_PORT + 2,
            extra_args=["--governance-metadata", '{"trust_score": 0.85}']
        )
        try:
            _, resp = _get(hp, "/governance-metadata")
            gm = resp["governance_metadata"]
            assert "derivation_rights" in gm, "derivation_rights must be present in governance_metadata"
        finally:
            _stop(proc)

    def test_GM03_derivation_rights_required_fields(self):
        proc, hp = _start_relay(
            _BASE_PORT + 4,
            extra_args=["--governance-metadata", '{"trust_score": 0.85}']
        )
        try:
            _, resp = _get(hp, "/governance-metadata")
            dr = resp["governance_metadata"]["derivation_rights"]
            assert "retention_permitted" in dr
            assert "export_permitted" in dr
            assert isinstance(dr["retention_permitted"], bool)
            assert isinstance(dr["export_permitted"], bool)
        finally:
            _stop(proc)

    def test_GM04_derivation_rights_optional_fields(self):
        proc, hp = _start_relay(
            _BASE_PORT + 6,
            extra_args=["--governance-metadata", '{"trust_score": 0.85}']
        )
        try:
            _, resp = _get(hp, "/governance-metadata")
            dr = resp["governance_metadata"]["derivation_rights"]
            if "retention_ttl" in dr and dr["retention_ttl"] is not None:
                assert isinstance(dr["retention_ttl"], int)
            if "derivation_classes" in dr:
                assert isinstance(dr["derivation_classes"], list)
            if "export_requires_consent" in dr:
                assert isinstance(dr["export_requires_consent"], bool)
            if "derivation_audit_required" in dr:
                assert isinstance(dr["derivation_audit_required"], bool)
        finally:
            _stop(proc)


# ──────────────────────────────────────────────────────────────────────────────
# GM05–GM08: credential_lifecycle structure
# ──────────────────────────────────────────────────────────────────────────────

class TestCredentialLifecycle:
    def test_GM05_credential_lifecycle_present(self):
        proc, hp = _start_relay(
            _BASE_PORT + 8,
            extra_args=["--governance-metadata", '{"trust_score": 0.85}']
        )
        try:
            _, resp = _get(hp, "/governance-metadata")
            gm = resp["governance_metadata"]
            assert "credential_lifecycle" in gm
        finally:
            _stop(proc)

    def test_GM06_credential_lifecycle_is_object(self):
        proc, hp = _start_relay(
            _BASE_PORT + 10,
            extra_args=["--governance-metadata", '{"trust_score": 0.85}']
        )
        try:
            _, resp = _get(hp, "/governance-metadata")
            cl = resp["governance_metadata"]["credential_lifecycle"]
            assert isinstance(cl, dict)
        finally:
            _stop(proc)

    def test_GM07_credential_lifecycle_revocation_endpoint(self):
        proc, hp = _start_relay(
            _BASE_PORT + 12,
            extra_args=["--governance-metadata", '{"trust_score": 0.85}']
        )
        try:
            _, resp = _get(hp, "/governance-metadata")
            cl = resp["governance_metadata"]["credential_lifecycle"]
            if cl.get("revocation_endpoint") is not None:
                assert isinstance(cl["revocation_endpoint"], str)
        finally:
            _stop(proc)

    def test_GM08_credential_lifecycle_numeric_fields(self):
        proc, hp = _start_relay(
            _BASE_PORT + 14,
            extra_args=["--governance-metadata", '{"trust_score": 0.85}']
        )
        try:
            _, resp = _get(hp, "/governance-metadata")
            cl = resp["governance_metadata"]["credential_lifecycle"]
            for field in ("max_session_duration", "credential_ttl", "revocation_check_frequency"):
                if field in cl and cl[field] is not None:
                    assert isinstance(cl[field], (int, float)), f"{field} must be numeric"
        finally:
            _stop(proc)


# ──────────────────────────────────────────────────────────────────────────────
# GM09–GM11: capability flags (in AgentCard.capabilities, not /status)
# ──────────────────────────────────────────────────────────────────────────────

class TestCapabilityFlags:
    def test_GM09_derivation_rights_capability_flag(self):
        proc, hp = _start_relay(
            _BASE_PORT + 16,
            extra_args=["--governance-metadata", '{"trust_score": 0.85}']
        )
        try:
            card = _card(hp)
            caps = card.get("capabilities", {})
            assert caps.get("derivation_rights") is True
        finally:
            _stop(proc)

    def test_GM10_credential_lifecycle_capability_flag(self):
        proc, hp = _start_relay(
            _BASE_PORT + 18,
            extra_args=["--governance-metadata", '{"trust_score": 0.85}']
        )
        try:
            card = _card(hp)
            caps = card.get("capabilities", {})
            assert caps.get("credential_lifecycle") is True
        finally:
            _stop(proc)

    def test_GM11_governance_metadata_capability_flag(self):
        proc, hp = _start_relay(
            _BASE_PORT + 20,
            extra_args=["--governance-metadata", '{"trust_score": 0.85}']
        )
        try:
            card = _card(hp)
            caps = card.get("capabilities", {})
            assert caps.get("governance_metadata") is True
        finally:
            _stop(proc)


# ──────────────────────────────────────────────────────────────────────────────
# GM12–GM13: AgentCard inclusion
# ──────────────────────────────────────────────────────────────────────────────

class TestAgentCardInclusion:
    def test_GM12_agentcard_has_governance_metadata(self):
        proc, hp = _start_relay(
            _BASE_PORT + 22,
            extra_args=["--governance-metadata", '{"trust_score": 0.85}']
        )
        try:
            card = _card(hp)
            assert "governance_metadata" in card, "AgentCard must include governance_metadata block"
        finally:
            _stop(proc)

    def test_GM13_agentcard_governance_has_derivation_rights(self):
        proc, hp = _start_relay(
            _BASE_PORT + 24,
            extra_args=["--governance-metadata", '{"trust_score": 0.85}']
        )
        try:
            card = _card(hp)
            gm = card.get("governance_metadata", {})
            assert "derivation_rights" in gm
            assert "credential_lifecycle" in gm
        finally:
            _stop(proc)


# ──────────────────────────────────────────────────────────────────────────────
# GM14–GM16: edge cases
# ──────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_GM14_no_governance_flags_false(self):
        proc, hp = _start_relay(_BASE_PORT + 26, extra_args=["--no-identity"])
        try:
            card = _card(hp)
            caps = card.get("capabilities", {})
            assert not caps.get("derivation_rights", False)
            assert not caps.get("credential_lifecycle", False)
        finally:
            _stop(proc)

    def test_GM15_no_governance_agentcard_missing_block(self):
        proc, hp = _start_relay(_BASE_PORT + 28, extra_args=["--no-identity"])
        try:
            card = _card(hp)
            assert "governance_metadata" not in card
        finally:
            _stop(proc)

    def test_GM16_schema_version_present_when_governance_enabled(self):
        proc, hp = _start_relay(
            _BASE_PORT + 30,
            extra_args=["--governance-metadata", '{"trust_score": 0.85}']
        )
        try:
            _, resp = _get(hp, "/governance-metadata")
            gm = resp["governance_metadata"]
            assert gm.get("schema_version") == "1.0"
        finally:
            _stop(proc)
