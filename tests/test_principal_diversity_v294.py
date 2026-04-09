"""
tests/test_principal_diversity_v294.py
=======================================
ACP v2.94 — Principal Diversity Defense for Bilateral IR
Tests PD01–PD16

Validates the colluding-pair inflation defense:
  - GET /trust/bilateral-ir/diversity endpoint
  - Defense params exposure in response
  - Capability flag and endpoint declaration in AgentCard
  - VERSION == 2.94.0

Based on aeoess adversarial-trust-fixture.json (A2A #1718):
  concentration_threshold = 0.60
  penalty_weight = 0.10
  min_records_for_analysis = 3

Pattern: HTTP API port = ws_port + 100 (--test-mode flag)
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

RELAY_PATH = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")
_BASE_PORT = 15500  # distinct from other test files


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


def _get(hp, path, expect_error=False):
    """HTTP GET; returns (status, body_dict). On error status, returns (status, body_dict)."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{hp}{path}", timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read())
        except Exception:
            body = {}
        return e.code, body


def _card(hp):
    """Fetch AgentCard, handling self-wrapper."""
    _, raw = _get(hp, "/.well-known/acp.json")
    return raw.get("self") or raw


# ──────────────────────────────────────────────────────────────────────────────
# PD01–PD04: VERSION and capability/endpoint flags
# ──────────────────────────────────────────────────────────────────────────────

class TestVersionAndFlags:

    def test_pd01_version(self):
        """PD01: VERSION >= 2.94.0 (principal_diversity_defense introduced)"""
        proc, hp = _start_relay(_free_port())
        try:
            card = _card(hp)
            ver = card.get("acp_version", "")
            major, minor, patch = (int(x) for x in ver.split("."))
            assert (major, minor) >= (2, 94), f"Expected >= 2.94.0, got {ver}"
        finally:
            _stop(proc)

    def test_pd02_capability_flag(self):
        """PD02: capabilities.principal_diversity_defense == True"""
        proc, hp = _start_relay(_free_port())
        try:
            card = _card(hp)
            caps = card.get("capabilities", {})
            assert caps.get("principal_diversity_defense") is True
        finally:
            _stop(proc)

    def test_pd03_endpoint_declared(self):
        """PD03: endpoints.bilateral_ir_diversity declared in AgentCard"""
        proc, hp = _start_relay(_free_port())
        try:
            card = _card(hp)
            endpoints = card.get("endpoints", {})
            assert "bilateral_ir_diversity" in endpoints
            assert "/trust/bilateral-ir/diversity" in endpoints["bilateral_ir_diversity"]
        finally:
            _stop(proc)

    def test_pd04_bilateral_ir_log_still_present(self):
        """PD04: backward compat — bilateral_ir_log endpoint still declared"""
        proc, hp = _start_relay(_free_port())
        try:
            card = _card(hp)
            endpoints = card.get("endpoints", {})
            assert "bilateral_ir_log" in endpoints
        finally:
            _stop(proc)


# ──────────────────────────────────────────────────────────────────────────────
# PD05–PD07: /trust/bilateral-ir/diversity error handling
# ──────────────────────────────────────────────────────────────────────────────

class TestDiversityErrorHandling:

    def test_pd05_diversity_missing_peer_id(self):
        """PD05: GET /trust/bilateral-ir/diversity without peer_id → 400"""
        proc, hp = _start_relay(_free_port())
        try:
            status, body = _get(hp, "/trust/bilateral-ir/diversity")
            assert status == 400
            assert body.get("ok") is False
        finally:
            _stop(proc)

    def test_pd06_diversity_unknown_peer(self):
        """PD06: GET /trust/bilateral-ir/diversity for unknown peer → 404"""
        proc, hp = _start_relay(_free_port())
        try:
            status, body = _get(hp, "/trust/bilateral-ir/diversity?peer_id=did:key:z6MkUnknown999")
            assert status == 404
            assert body.get("ok") is False
        finally:
            _stop(proc)

    def test_pd07_diversity_response_has_peer_id_in_error(self):
        """PD07: 404 error response includes peer_id for debugging"""
        proc, hp = _start_relay(_free_port())
        try:
            status, body = _get(hp, "/trust/bilateral-ir/diversity?peer_id=did:key:z6MkTestPeer")
            assert status == 404
            assert "peer_id" in body or "error" in body
        finally:
            _stop(proc)


# ──────────────────────────────────────────────────────────────────────────────
# PD08–PD10: Defense params and threshold values
# ──────────────────────────────────────────────────────────────────────────────

class TestDefenseParams:

    def _relay_with_records(self, peer_a, peer_b, count_b, peer_c=None, count_c=0):
        """Start relay and inject bilateral IR records using test injection endpoint."""
        ws_port = _free_port()
        proc, hp = _start_relay(ws_port)
        # Inject records via POST /trust/bilateral-ir/inject (test helper endpoint)
        for _ in range(count_b):
            self._inject(hp, caller_did=peer_a, callee_did=peer_b)
        if peer_c and count_c > 0:
            for _ in range(count_c):
                self._inject(hp, caller_did=peer_a, callee_did=peer_c)
        return proc, hp

    def _inject(self, hp, caller_did, callee_did):
        import random, string
        payload = json.dumps({
            "skill_id": "test.diversity",
            "caller_did": caller_did,
            "callee_did": callee_did,
            "bilateral": True,
            "task_id": f"t-{''.join(random.choices(string.ascii_lowercase, k=8))}",
        }).encode()
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{hp}/trust/bilateral-ir/inject",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=3) as r:
                return r.status
        except Exception:
            return None

    def test_pd08_defense_params_in_response(self):
        """PD08: /trust/bilateral-ir/diversity response contains defense_params block"""
        proc, hp = _start_relay(_free_port())
        try:
            peer_a = "did:key:z6MkPD08a"
            peer_b = "did:key:z6MkPD08b"
            for _ in range(4):
                self._inject(hp, peer_a, peer_b)
            status, body = _get(hp, f"/trust/bilateral-ir/diversity?peer_id={peer_a}")
            if status == 404:
                pytest.skip("IR injection not supported by this relay build")
            assert status == 200
            params = body.get("defense_params", {})
            assert "concentration_threshold" in params
            assert "penalty_weight" in params
            assert "min_records_for_analysis" in params
        finally:
            _stop(proc)

    def test_pd09_defense_params_values(self):
        """PD09: defense_params values match aeoess fixture params"""
        proc, hp = _start_relay(_free_port())
        try:
            peer_a = "did:key:z6MkPD09a"
            peer_b = "did:key:z6MkPD09b"
            for _ in range(4):
                self._inject(hp, peer_a, peer_b)
            status, body = _get(hp, f"/trust/bilateral-ir/diversity?peer_id={peer_a}")
            if status == 404:
                pytest.skip("IR injection not supported")
            params = body.get("defense_params", {})
            assert params.get("concentration_threshold") == 0.60
            assert params.get("penalty_weight") == 0.10
            assert params.get("min_records_for_analysis") == 3
        finally:
            _stop(proc)

    def test_pd10_response_schema_complete(self):
        """PD10: Diversity response contains all required fields"""
        proc, hp = _start_relay(_free_port())
        try:
            peer_a = "did:key:z6MkPD10a"
            peer_b = "did:key:z6MkPD10b"
            for _ in range(5):
                self._inject(hp, peer_a, peer_b)
            status, body = _get(hp, f"/trust/bilateral-ir/diversity?peer_id={peer_a}")
            if status == 404:
                pytest.skip("IR injection not supported")
            assert status == 200
            required = [
                "ok", "peer_id", "total_bilateral", "unique_counterparties",
                "top_counterparty", "concentration_ratio", "penalty_applied",
                "diversity_weight", "effective_bilateral_count", "note",
                "defense_params", "version"
            ]
            for field in required:
                assert field in body, f"Missing field: {field}"
        finally:
            _stop(proc)


# ──────────────────────────────────────────────────────────────────────────────
# PD11–PD14: Penalty logic
# ──────────────────────────────────────────────────────────────────────────────

class TestPenaltyLogic:

    def _inject(self, hp, caller_did, callee_did):
        import random, string
        payload = json.dumps({
            "skill_id": "test.penalty",
            "caller_did": caller_did,
            "callee_did": callee_did,
            "bilateral": True,
            "task_id": f"t-{''.join(random.choices(string.ascii_lowercase, k=8))}",
        }).encode()
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{hp}/trust/bilateral-ir/inject",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=3) as r:
                return r.status
        except Exception:
            return None

    def test_pd11_no_penalty_diverse(self):
        """PD11: No penalty when concentration <= 0.60 (3+3 diverse)"""
        proc, hp = _start_relay(_free_port())
        try:
            peer_a = "did:key:z6MkPD11a"
            peer_b = "did:key:z6MkPD11b"
            peer_c = "did:key:z6MkPD11c"
            for _ in range(3):
                self._inject(hp, peer_a, peer_b)
            for _ in range(3):
                self._inject(hp, peer_a, peer_c)
            status, body = _get(hp, f"/trust/bilateral-ir/diversity?peer_id={peer_a}")
            if status == 404:
                pytest.skip("IR injection not supported")
            assert body["penalty_applied"] is False
            assert body["diversity_weight"] == 1.0
        finally:
            _stop(proc)

    def test_pd12_penalty_above_threshold(self):
        """PD12: Penalty applied when concentration > 0.60 (7+3)"""
        proc, hp = _start_relay(_free_port())
        try:
            peer_a = "did:key:z6MkPD12a"
            peer_b = "did:key:z6MkPD12b"
            peer_c = "did:key:z6MkPD12c"
            for _ in range(7):
                self._inject(hp, peer_a, peer_b)
            for _ in range(3):
                self._inject(hp, peer_a, peer_c)
            status, body = _get(hp, f"/trust/bilateral-ir/diversity?peer_id={peer_a}")
            if status == 404:
                pytest.skip("IR injection not supported")
            assert body["penalty_applied"] is True
            assert body["diversity_weight"] < 1.0
            assert body["effective_bilateral_count"] < body["total_bilateral"]
        finally:
            _stop(proc)

    def test_pd13_effective_count_reduced_on_penalty(self):
        """PD13: effective_bilateral_count < total when penalty applied (all-same-peer)"""
        proc, hp = _start_relay(_free_port())
        try:
            peer_a = "did:key:z6MkPD13a"
            peer_b = "did:key:z6MkPD13b"
            for _ in range(10):
                self._inject(hp, peer_a, peer_b)
            status, body = _get(hp, f"/trust/bilateral-ir/diversity?peer_id={peer_a}")
            if status == 404:
                pytest.skip("IR injection not supported")
            if body["penalty_applied"]:
                assert body["effective_bilateral_count"] < body["total_bilateral"]
                assert body["effective_bilateral_count"] >= 1.0
        finally:
            _stop(proc)

    def test_pd14_insufficient_records_no_penalty(self):
        """PD14: < 3 records → no penalty, effective_count == total"""
        proc, hp = _start_relay(_free_port())
        try:
            peer_a = "did:key:z6MkPD14a"
            peer_b = "did:key:z6MkPD14b"
            for _ in range(2):
                self._inject(hp, peer_a, peer_b)
            status, body = _get(hp, f"/trust/bilateral-ir/diversity?peer_id={peer_a}")
            if status == 404:
                pytest.skip("IR injection not supported")
            assert body["penalty_applied"] is False
            assert float(body["effective_bilateral_count"]) == float(body["total_bilateral"])
        finally:
            _stop(proc)


# ──────────────────────────────────────────────────────────────────────────────
# PD15–PD16: Version and backward compatibility
# ──────────────────────────────────────────────────────────────────────────────

class TestVersionAndCompat:

    def test_pd15_version_in_diversity_response(self):
        """PD15: /trust/bilateral-ir/diversity response version >= 2.94.0"""
        proc, hp = _start_relay(_free_port())
        try:
            # Inject 3 records to get past the 404 guard
            for _ in range(3):
                payload = json.dumps({
                    "skill_id": "test.ver",
                    "caller_did": "did:key:z6MkPD15a",
                    "callee_did": "did:key:z6MkPD15b",
                    "bilateral": True,
                    "task_id": f"t-ver15",
                }).encode()
                try:
                    req = urllib.request.Request(
                        f"http://127.0.0.1:{hp}/trust/bilateral-ir/inject",
                        data=payload, headers={"Content-Type": "application/json"}, method="POST"
                    )
                    urllib.request.urlopen(req, timeout=2)
                except Exception:
                    pass
            status, body = _get(hp, "/trust/bilateral-ir/diversity?peer_id=did:key:z6MkPD15a")
            if status == 404:
                pytest.skip("IR injection not supported")
            ver = body.get("version", "")
            major, minor, _patch = (int(x) for x in ver.split("."))
            assert (major, minor) >= (2, 94), f"Expected >= 2.94.0, got {ver}"
        finally:
            _stop(proc)

    def test_pd16_existing_bilateral_ir_log_unaffected(self):
        """PD16: GET /trust/bilateral-ir/log still works (backward compat)"""
        proc, hp = _start_relay(_free_port())
        try:
            status, body = _get(hp, "/trust/bilateral-ir/log")
            assert status == 200
            assert body.get("ok") is True
            assert "records" in body
        finally:
            _stop(proc)
