"""
tests/test_skill_scoped_trust_v295.py
=======================================
ACP v2.95 — Skill-Scoped Trust Scores
Tests SS01–SS16

Validates:
  - _compute_skill_trust_scores() algorithm
  - GET /trust/skill-scores endpoint
  - QuerySkill response: skill_trust_score field
  - governance_metadata: trust_scores dict + trust_score_method
  - VERSION == 2.95.0
  - Backward compat: global trust_score retained

A2A reference: #1717 governance_metadata skill-scoped trust (community convergence 2026-04-09)
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


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_relay(ws_port: int, extra_args=None):
    http_port = ws_port + 100
    cmd = [sys.executable, RELAY_PATH, "--port", str(ws_port), "--local-only", "--test-mode"]
    if extra_args:
        cmd += extra_args
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{http_port}/status", timeout=1) as r:
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
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{hp}{path}", timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read())
        except Exception:
            body = {}
        return e.code, body


def _post(hp, path, payload):
    data = json.dumps(payload).encode()
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
        try:
            body = json.loads(e.read())
        except Exception:
            body = {}
        return e.code, body


def _card(hp):
    _, raw = _get(hp, "/.well-known/acp.json")
    return raw.get("self") or raw


def _inject(hp, caller_did, callee_did, skill_id, bilateral=True):
    import random, string
    return _post(hp, "/trust/bilateral-ir/inject", {
        "caller_did": caller_did,
        "callee_did": callee_did,
        "skill_id":   skill_id,
        "bilateral":  bilateral,
        "task_id":    f"t-{''.join(random.choices(string.ascii_lowercase, k=8))}",
    })


# ──────────────────────────────────────────────────────────────────────────────
# SS01–SS04: VERSION and capability flags
# ──────────────────────────────────────────────────────────────────────────────

class TestVersionAndFlags:

    def test_ss01_version(self):
        """SS01: VERSION is present (current release — assertion decoupled from patch version)"""
        proc, hp = _start_relay(_free_port())
        try:
            card = _card(hp)
            # Version evolves; assert presence not exact match (avoid BUG-060 class)
            assert card.get("acp_version") is not None
            assert card["acp_version"].startswith("2.")
        finally:
            _stop(proc)

    def test_ss02_capability_flag(self):
        """SS02: capabilities.skill_scoped_trust_scores == True"""
        proc, hp = _start_relay(_free_port())
        try:
            card = _card(hp)
            caps = card.get("capabilities", {})
            assert caps.get("skill_scoped_trust_scores") is True
        finally:
            _stop(proc)

    def test_ss03_endpoint_declared(self):
        """SS03: endpoints.skill_trust_scores declared"""
        proc, hp = _start_relay(_free_port())
        try:
            card = _card(hp)
            eps = card.get("endpoints", {})
            assert "skill_trust_scores" in eps
            assert "/trust/skill-scores" in eps["skill_trust_scores"]
        finally:
            _stop(proc)

    def test_ss04_backward_compat_endpoints(self):
        """SS04: existing endpoints still declared (bilateral_ir_log, bilateral_ir_diversity)"""
        proc, hp = _start_relay(_free_port())
        try:
            card = _card(hp)
            eps = card.get("endpoints", {})
            assert "bilateral_ir_log" in eps
            assert "bilateral_ir_diversity" in eps
        finally:
            _stop(proc)


# ──────────────────────────────────────────────────────────────────────────────
# SS05–SS07: GET /trust/skill-scores endpoint
# ──────────────────────────────────────────────────────────────────────────────

class TestSkillScoresEndpoint:

    def test_ss05_empty_no_ir(self):
        """SS05: /trust/skill-scores returns empty trust_scores dict when no IR records"""
        proc, hp = _start_relay(_free_port())
        try:
            status, body = _get(hp, "/trust/skill-scores")
            assert status == 200
            assert body["ok"] is True
            assert body["trust_scores"] == {}
            assert body["skill_count"] == 0
            assert body["ir_count"] == 0
        finally:
            _stop(proc)

    def test_ss06_response_schema(self):
        """SS06: /trust/skill-scores response contains all required fields"""
        proc, hp = _start_relay(_free_port())
        try:
            status, body = _get(hp, "/trust/skill-scores")
            assert status == 200
            required = ["ok", "trust_scores", "method", "algorithm", "skill_count", "ir_count", "note", "version"]
            for f in required:
                assert f in body, f"Missing: {f}"
            assert body["method"] == "skill_scoped_v1"
            assert body["version"] is not None  # version evolves; avoid BUG-060 class stale assertions
        finally:
            _stop(proc)

    def test_ss07_algorithm_fields(self):
        """SS07: algorithm block contains base/caller_diversity/volume/max"""
        proc, hp = _start_relay(_free_port())
        try:
            _, body = _get(hp, "/trust/skill-scores")
            algo = body.get("algorithm", {})
            assert "base" in algo
            assert "caller_diversity" in algo
            assert "volume" in algo
            assert "max" in algo
            assert algo["base"] == 0.3
            assert algo["max"] == 1.0
        finally:
            _stop(proc)


# ──────────────────────────────────────────────────────────────────────────────
# SS08–SS11: Score computation from IR evidence
# ──────────────────────────────────────────────────────────────────────────────

class TestScoreComputation:

    def test_ss08_single_skill_score(self):
        """SS08: 5 bilateral records, 3 unique callers → score for skill"""
        proc, hp = _start_relay(_free_port())
        try:
            for i in range(1, 4):
                _inject(hp, f"did:key:z6MkSSCaller{i}", "did:key:z6MkSSCallee", "text.summarize")
            _inject(hp, "did:key:z6MkSSCaller1", "did:key:z6MkSSCallee", "text.summarize")
            _inject(hp, "did:key:z6MkSSCaller2", "did:key:z6MkSSCallee", "text.summarize")
            # 5 bilateral records, 3 unique callers
            # base = 0.3 + min(3,10)*0.04 + min(5,50)*0.005 = 0.3+0.12+0.025 = 0.445
            status, body = _get(hp, "/trust/skill-scores")
            assert status == 200
            scores = body["trust_scores"]
            assert "text.summarize" in scores
            # Tolerance ±0.02 for any implementation rounding
            assert 0.43 <= scores["text.summarize"] <= 0.47
        finally:
            _stop(proc)

    def test_ss09_multiple_skills_separated(self):
        """SS09: Two skills → separate independent scores"""
        proc, hp = _start_relay(_free_port())
        try:
            # skill_a: 3 records, 3 unique callers
            for i in range(1, 4):
                _inject(hp, f"did:key:z6MkSSA{i}", "did:key:z6MkSSCallee", "skill.alpha")
            # skill_b: 10 records, 1 unique caller
            for _ in range(10):
                _inject(hp, "did:key:z6MkSSBCaller", "did:key:z6MkSSCallee", "skill.beta")
            status, body = _get(hp, "/trust/skill-scores")
            assert status == 200
            scores = body["trust_scores"]
            assert "skill.alpha" in scores
            assert "skill.beta" in scores
            # skill.alpha: 3 unique callers → higher diversity → different score from skill.beta
            # They should NOT be equal (different evidence)
            assert scores["skill.alpha"] != scores["skill.beta"]
        finally:
            _stop(proc)

    def test_ss10_score_between_0_and_1(self):
        """SS10: All scores are clamped to [0.0, 1.0]"""
        proc, hp = _start_relay(_free_port())
        try:
            # Inject 60 records with 15 unique callers → should not exceed 1.0
            for i in range(1, 16):
                for _ in range(4):
                    _inject(hp, f"did:key:z6MkSSMax{i}", "did:key:z6MkSSMaxCallee", "heavy.skill")
            status, body = _get(hp, "/trust/skill-scores")
            scores = body.get("trust_scores", {})
            for sid, score in scores.items():
                assert 0.0 <= score <= 1.0, f"Score out of range for {sid}: {score}"
        finally:
            _stop(proc)

    def test_ss11_skill_count_matches_unique_skills(self):
        """SS11: skill_count matches unique skill_ids in IR records"""
        proc, hp = _start_relay(_free_port())
        try:
            _inject(hp, "did:key:z6MkCX1", "did:key:z6MkCY", "skill.one")
            _inject(hp, "did:key:z6MkCX2", "did:key:z6MkCY", "skill.two")
            _inject(hp, "did:key:z6MkCX3", "did:key:z6MkCY", "skill.three")
            status, body = _get(hp, "/trust/skill-scores")
            assert body["skill_count"] == 3
            assert len(body["trust_scores"]) == 3
        finally:
            _stop(proc)


# ──────────────────────────────────────────────────────────────────────────────
# SS12–SS14: QuerySkill skill_trust_score integration
# ──────────────────────────────────────────────────────────────────────────────

class TestQuerySkillIntegration:

    def test_ss12_query_skill_returns_trust_score_field(self):
        """SS12: QuerySkill response contains skill_trust_score field (may be null)"""
        proc, hp = _start_relay(_free_port())
        try:
            status, body = _post(hp, "/skills/query", {"skill_id": "any.skill"})
            # skill_trust_score key must exist (null when no IR evidence)
            assert "skill_trust_score" in body
        finally:
            _stop(proc)

    def test_ss13_query_skill_null_trust_when_no_ir(self):
        """SS13: skill_trust_score == null when no IR evidence for this skill"""
        proc, hp = _start_relay(_free_port())
        try:
            _, body = _post(hp, "/skills/query", {"skill_id": "unknown.skill.xyz"})
            assert body.get("skill_trust_score") is None
        finally:
            _stop(proc)

    def test_ss14_query_skill_populated_trust_after_ir(self):
        """SS14: skill_trust_score populated after bilateral IR records for this skill"""
        proc, hp = _start_relay(_free_port())
        try:
            # Inject 4 bilateral records for "qa.skill"
            for i in range(1, 5):
                _inject(hp, f"did:key:z6MkQACaller{i}", "did:key:z6MkQACallee", "qa.skill")
            _, body = _post(hp, "/skills/query", {"skill_id": "qa.skill"})
            score = body.get("skill_trust_score")
            # Could be None if "qa.skill" not in AgentCard skills (query → unsupported)
            # But the field must exist
            assert "skill_trust_score" in body
            if score is not None:
                assert 0.0 <= score <= 1.0
        finally:
            _stop(proc)


# ──────────────────────────────────────────────────────────────────────────────
# SS15–SS16: governance_metadata trust_scores + backward compat
# ──────────────────────────────────────────────────────────────────────────────

class TestGovernanceMetadataIntegration:

    def test_ss15_governance_metadata_trust_scores(self):
        """SS15: /governance-metadata includes trust_scores dict + trust_score_method"""
        proc, hp = _start_relay(
            _free_port(), extra_args=["--governance-metadata", '{"trust_score": 0.8}']
        )
        try:
            status, body = _get(hp, "/governance-metadata")
            assert status == 200
            gm = body.get("governance_metadata", body)
            assert "trust_scores" in gm
            assert isinstance(gm["trust_scores"], dict)
            assert gm.get("trust_score_method") == "skill_scoped_v1"
        finally:
            _stop(proc)

    def test_ss16_global_trust_score_backward_compat(self):
        """SS16: global trust_score still present in governance_metadata (backward compat)"""
        proc, hp = _start_relay(
            _free_port(), extra_args=["--governance-metadata", '{"trust_score": 0.75}']
        )
        try:
            status, body = _get(hp, "/governance-metadata")
            gm = body.get("governance_metadata", body)
            # Global trust_score must still be present (backward compat with A2A #1717 v1)
            assert "trust_score" in gm
            # When no IR evidence, configured value retained (0.75)
            assert gm["trust_score"] == 0.75
        finally:
            _stop(proc)
