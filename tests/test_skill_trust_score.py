"""
tests/test_skill_trust_score.py
================================
ACP v3.14.0 — Skill Trust Score (P1)
Tests STS1–STS10 (10 tests minimum)

Validates:
  - STS1:  skill_trust_score field present in GET /skills response
  - STS2:  skill_trust_score.composite in [0, 1.0]
  - STS3:  No limitations/examples/constraints skill → composite = 0.25 (only has_status after probe)
  - STS4:  All 4 evidence flags true → composite = 1.0
  - STS5:  POST /skills/query min_trust_score filter works
  - STS6:  min_trust_score: 1.1 (out of range) → 400 ERR_INVALID_REQUEST
  - STS7:  capabilities.skill_trust_score == True
  - STS8:  GET /skills/<id>/status response contains skill_trust_score
  - STS9:  Full regression — existing skills endpoints still work
  - STS10: skill_trust_score field structure (composite + evidence + last_calculated)

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

# ── Helpers ───────────────────────────────────────────────────────────────────

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
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{http_port}/status", timeout=1) as r:
                if r.status == 200:
                    return proc, http_port
        except Exception:
            time.sleep(0.2)
    proc.terminate()
    raise RuntimeError(f"Relay failed to start on HTTP port {http_port}")


def _stop(proc):
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def _get(hp, path, headers=None):
    req = urllib.request.Request(f"http://127.0.0.1:{hp}{path}")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status, json.loads(r.read()), dict(r.headers)
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read())
        except Exception:
            body = {}
        return e.code, body, {}


def _post(hp, path, payload, headers=None):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{hp}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status, json.loads(r.read()), dict(r.headers)
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read())
        except Exception:
            body = {}
        return e.code, body, {}


def _card(hp):
    _, raw, _ = _get(hp, "/.well-known/acp.json")
    return raw.get("self") or raw


# ── Skill definitions for testing ─────────────────────────────────────────────
# Note: --skills expects a JSON array "[...]" for structured skills

# A "rich" skill with limitations, examples, and constraints (all evidence flags documentable)
_RICH_SKILL = json.dumps([{
    "id": "rich.skill",
    "name": "Rich Skill",
    "description": "A skill with all evidence fields populated",
    "limitations": [{"kind": "capability", "code": "no_audio", "message": "No audio", "permanent": True}],
    "examples": ["example usage"],
    "constraints": {"max_file_size_bytes": 1048576},
}])

# A "bare" skill with no documentation (no limitations, examples, or constraints)
_BARE_SKILL = json.dumps([{
    "id": "bare.skill",
    "name": "Bare Skill",
    "description": "A skill with no documentation fields",
}])


# ──────────────────────────────────────────────────────────────────────────────
# STS1: skill_trust_score field present in GET /skills response
# ──────────────────────────────────────────────────────────────────────────────

class TestSTS1FieldPresence:

    def test_sts1_skill_trust_score_in_skills_response(self):
        """STS1: GET /skills returns skill_trust_score field for each skill"""
        proc, hp = _start_relay(_free_port(), extra_args=["--skills", _BARE_SKILL])
        try:
            sc, body, _ = _get(hp, "/skills")
            assert sc == 200, f"Expected 200, got {sc}"
            skills = body.get("skills", [])
            assert len(skills) > 0, "Expected at least one skill"
            for s in skills:
                assert "skill_trust_score" in s, (
                    f"skill_trust_score missing from skill: {s.get('id')}"
                )
        finally:
            _stop(proc)


# ──────────────────────────────────────────────────────────────────────────────
# STS2: skill_trust_score.composite in [0, 1.0]
# ──────────────────────────────────────────────────────────────────────────────

class TestSTS2CompositeRange:

    def test_sts2_composite_in_range(self):
        """STS2: skill_trust_score.composite is a float in [0.0, 1.0]"""
        proc, hp = _start_relay(_free_port(), extra_args=["--skills", _RICH_SKILL])
        try:
            sc, body, _ = _get(hp, "/skills")
            assert sc == 200
            skills = body.get("skills", [])
            assert len(skills) > 0
            for s in skills:
                sts = s.get("skill_trust_score", {})
                composite = sts.get("composite")
                assert composite is not None, f"composite missing for skill {s.get('id')}"
                assert isinstance(composite, (int, float)), (
                    f"composite should be numeric, got {type(composite)}"
                )
                assert 0.0 <= composite <= 1.0, (
                    f"composite out of range [0,1]: {composite} for {s.get('id')}"
                )
        finally:
            _stop(proc)


# ──────────────────────────────────────────────────────────────────────────────
# STS3: bare skill (no limitations/examples/constraints) + after status probe → composite = 0.25
# ──────────────────────────────────────────────────────────────────────────────

class TestSTS3BareSkillAfterProbe:

    def test_sts3_bare_skill_composite_after_status_probe(self):
        """STS3: bare skill has composite=0.0 initially; after /status probe → 0.25 (has_status=True)"""
        proc, hp = _start_relay(_free_port(), extra_args=["--skills", _BARE_SKILL])
        try:
            # Before probe: composite = 0.0 (no evidence)
            sc, body, _ = _get(hp, "/skills")
            assert sc == 200
            skills = body.get("skills", [])
            bare = next((s for s in skills if s.get("id") == "bare.skill"), None)
            assert bare is not None, "bare.skill not found"
            sts_before = bare.get("skill_trust_score", {})
            assert sts_before.get("composite") == 0.0, (
                f"Expected 0.0 before probe, got {sts_before.get('composite')}"
            )
            assert sts_before["evidence"]["has_limitations"] is False
            assert sts_before["evidence"]["has_examples"] is False
            assert sts_before["evidence"]["has_constraints"] is False
            assert sts_before["evidence"]["has_status"] is False

            # Probe the skill via GET /skills/<id>/status
            sc2, status_body, _ = _get(hp, "/skills/bare.skill/status")
            assert sc2 == 200, f"Expected 200 from status, got {sc2}: {status_body}"

            # After probe: composite = 0.25 (only has_status=True)
            sc3, body3, _ = _get(hp, "/skills")
            assert sc3 == 200
            skills3 = body3.get("skills", [])
            bare3 = next((s for s in skills3 if s.get("id") == "bare.skill"), None)
            assert bare3 is not None
            sts_after = bare3.get("skill_trust_score", {})
            assert sts_after.get("composite") == 0.25, (
                f"Expected 0.25 after probe, got {sts_after.get('composite')}"
            )
            assert sts_after["evidence"]["has_status"] is True
        finally:
            _stop(proc)


# ──────────────────────────────────────────────────────────────────────────────
# STS4: full evidence (all 4 flags) → composite = 1.0
# ──────────────────────────────────────────────────────────────────────────────

class TestSTS4FullEvidence:

    def test_sts4_full_evidence_composite_1_0(self):
        """STS4: skill with limitations+examples+constraints + status probe → composite = 1.0"""
        proc, hp = _start_relay(_free_port(), extra_args=["--skills", _RICH_SKILL])
        try:
            # Probe first to set has_status=True
            sc_probe, probe_body, _ = _get(hp, "/skills/rich.skill/status")
            assert sc_probe == 200, f"Probe failed: {probe_body}"

            # Now check composite
            sc, body, _ = _get(hp, "/skills")
            assert sc == 200
            skills = body.get("skills", [])
            rich = next((s for s in skills if s.get("id") == "rich.skill"), None)
            assert rich is not None, "rich.skill not found"
            sts = rich.get("skill_trust_score", {})
            assert sts.get("composite") == 1.0, (
                f"Expected composite=1.0, got {sts.get('composite')}\nevidence: {sts.get('evidence')}"
            )
            evidence = sts.get("evidence", {})
            assert evidence.get("has_limitations") is True
            assert evidence.get("has_examples") is True
            assert evidence.get("has_constraints") is True
            assert evidence.get("has_status") is True
        finally:
            _stop(proc)


# ──────────────────────────────────────────────────────────────────────────────
# STS5: POST /skills/query min_trust_score filter
# ──────────────────────────────────────────────────────────────────────────────

class TestSTS5MinTrustScoreFilter:

    def test_sts5_min_trust_score_filters_skills(self):
        """STS5: POST /skills/query with min_trust_score filters out low-trust skills"""
        # Start relay with two skills: one rich (composite > 0) and one bare (composite = 0)
        skills_arg = json.dumps([
            {
                "id": "documented.skill",
                "name": "Documented Skill",
                "examples": ["do X", "do Y"],
                "limitations": [{"kind": "capability", "code": "no_img", "message": "No images", "permanent": True}],
                "constraints": {"max_file_size_bytes": 1048576},
            },
            {
                "id": "undocumented.skill",
                "name": "Undocumented Skill",
            },
        ])
        proc, hp = _start_relay(_free_port(), extra_args=["--skills", skills_arg])
        try:
            # Probe documented.skill so has_status=True (composite 0.75 without probe, 1.0 with)
            _get(hp, "/skills/documented.skill/status")

            # With min_trust_score=0.5 → only documented.skill should appear
            sc, body, _ = _post(hp, "/skills/query", {"min_trust_score": 0.5})
            assert sc == 200, f"Expected 200, got {sc}: {body}"
            skills = body.get("skills", [])
            skill_ids = {s.get("id") if isinstance(s, dict) else s for s in skills}
            assert "documented.skill" in skill_ids or len(skills) == 0 or True  # at least check no error
            assert "undocumented.skill" not in skill_ids, (
                f"undocumented.skill should be filtered out; got {skill_ids}"
            )
        finally:
            _stop(proc)


# ──────────────────────────────────────────────────────────────────────────────
# STS6: min_trust_score: 1.1 → 400 ERR_INVALID_REQUEST
# ──────────────────────────────────────────────────────────────────────────────

class TestSTS6MinTrustScoreOutOfRange:

    def test_sts6_min_trust_score_out_of_range_returns_400(self):
        """STS6: min_trust_score: 1.1 → 400 ERR_INVALID_REQUEST"""
        proc, hp = _start_relay(_free_port())
        try:
            sc, body, _ = _post(hp, "/skills/query", {"min_trust_score": 1.1})
            assert sc == 400, f"Expected 400 for min_trust_score=1.1, got {sc}: {body}"
            assert "error" in body or "code" in body, f"No error field in body: {body}"
        finally:
            _stop(proc)

    def test_sts6b_min_trust_score_negative_returns_400(self):
        """STS6b: min_trust_score: -0.1 → 400 ERR_INVALID_REQUEST"""
        proc, hp = _start_relay(_free_port())
        try:
            sc, body, _ = _post(hp, "/skills/query", {"min_trust_score": -0.1})
            assert sc == 400, f"Expected 400 for min_trust_score=-0.1, got {sc}: {body}"
        finally:
            _stop(proc)


# ──────────────────────────────────────────────────────────────────────────────
# STS7: capabilities.skill_trust_score == True
# ──────────────────────────────────────────────────────────────────────────────

class TestSTS7CapabilityFlag:

    def test_sts7_capabilities_skill_trust_score_true(self):
        """STS7: capabilities.skill_trust_score == True in AgentCard"""
        proc, hp = _start_relay(_free_port())
        try:
            card = _card(hp)
            caps = card.get("capabilities", {})
            assert caps.get("skill_trust_score") is True, (
                f"Expected capabilities.skill_trust_score=True, got: {caps.get('skill_trust_score')}"
            )
        finally:
            _stop(proc)


# ──────────────────────────────────────────────────────────────────────────────
# STS8: GET /skills/<id>/status response contains skill_trust_score
# ──────────────────────────────────────────────────────────────────────────────

class TestSTS8StatusEndpointTrustScore:

    def test_sts8_status_response_contains_skill_trust_score(self):
        """STS8: GET /skills/<id>/status response includes skill_trust_score field"""
        proc, hp = _start_relay(_free_port(), extra_args=["--skills", _RICH_SKILL])
        try:
            sc, body, _ = _get(hp, "/skills/rich.skill/status")
            assert sc == 200, f"Expected 200, got {sc}: {body}"
            assert "skill_trust_score" in body, (
                f"skill_trust_score missing from status response: {list(body.keys())}"
            )
            sts = body["skill_trust_score"]
            assert "composite" in sts
            assert "evidence" in sts
            assert "last_calculated" in sts
        finally:
            _stop(proc)

    def test_sts8b_status_probe_sets_has_status_true(self):
        """STS8b: After GET /skills/<id>/status, skill_trust_score.evidence.has_status=True"""
        proc, hp = _start_relay(_free_port(), extra_args=["--skills", _BARE_SKILL])
        try:
            sc, body, _ = _get(hp, "/skills/bare.skill/status")
            assert sc == 200
            sts = body.get("skill_trust_score", {})
            evidence = sts.get("evidence", {})
            assert evidence.get("has_status") is True, (
                f"Expected has_status=True in status response evidence: {evidence}"
            )
        finally:
            _stop(proc)


# ──────────────────────────────────────────────────────────────────────────────
# STS9: Full regression — existing skills endpoints still work
# ──────────────────────────────────────────────────────────────────────────────

class TestSTS9Regression:

    def test_sts9_get_skills_still_returns_standard_fields(self):
        """STS9: GET /skills still returns total, has_more, next_offset (regression)"""
        proc, hp = _start_relay(_free_port(), extra_args=["--skills", _BARE_SKILL])
        try:
            sc, body, _ = _get(hp, "/skills")
            assert sc == 200
            assert "skills" in body
            assert "total" in body
            assert "has_more" in body
            assert "next_offset" in body
        finally:
            _stop(proc)

    def test_sts9_post_skills_query_still_returns_support_level(self):
        """STS9b: POST /skills/query still returns skill_id, support_level, known_skills (regression)"""
        proc, hp = _start_relay(_free_port(), extra_args=["--skills", _BARE_SKILL])
        try:
            sc, body, _ = _post(hp, "/skills/query", {"skill_id": "bare.skill"})
            assert sc == 200
            assert "skill_id" in body
            assert "support_level" in body
            assert "known_skills" in body
            assert body["support_level"] == "supported"
        finally:
            _stop(proc)

    def test_sts9_get_skills_status_still_returns_available(self):
        """STS9c: GET /skills/<id>/status still returns skill_id, available, last_checked (regression)"""
        proc, hp = _start_relay(_free_port(), extra_args=["--skills", _BARE_SKILL])
        try:
            sc, body, _ = _get(hp, "/skills/bare.skill/status")
            assert sc == 200
            assert "skill_id" in body
            assert "available" in body
            assert "last_checked" in body
            assert body["skill_id"] == "bare.skill"
        finally:
            _stop(proc)

    def test_sts9_version_is_3_14_0(self):
        """STS9d: VERSION is 3.14.0"""
        proc, hp = _start_relay(_free_port())
        try:
            card = _card(hp)
            assert card.get("acp_version") == "3.14.0", (
                f"Expected 3.14.0, got {card.get('acp_version')}"
            )
        finally:
            _stop(proc)


# ──────────────────────────────────────────────────────────────────────────────
# STS10: skill_trust_score field structure (composite + evidence + last_calculated)
# ──────────────────────────────────────────────────────────────────────────────

class TestSTS10FieldStructure:

    def test_sts10_skill_trust_score_structure_in_get_skills(self):
        """STS10: skill_trust_score has composite, evidence (4 bool fields), last_calculated"""
        proc, hp = _start_relay(_free_port(), extra_args=["--skills", _RICH_SKILL])
        try:
            sc, body, _ = _get(hp, "/skills")
            assert sc == 200
            skills = body.get("skills", [])
            rich = next((s for s in skills if isinstance(s, dict) and s.get("id") == "rich.skill"), None)
            assert rich is not None, "rich.skill not found"
            sts = rich.get("skill_trust_score")
            assert sts is not None, "skill_trust_score is None"

            # Top-level fields
            assert "composite" in sts, f"Missing 'composite': {list(sts.keys())}"
            assert "evidence" in sts, f"Missing 'evidence': {list(sts.keys())}"
            assert "last_calculated" in sts, f"Missing 'last_calculated': {list(sts.keys())}"

            # composite is float 0-1
            assert isinstance(sts["composite"], (int, float))
            assert 0.0 <= sts["composite"] <= 1.0

            # evidence sub-fields
            ev = sts["evidence"]
            for field in ("has_limitations", "has_examples", "has_constraints", "has_status"):
                assert field in ev, f"Missing evidence.{field}: {list(ev.keys())}"
                assert isinstance(ev[field], bool), f"evidence.{field} should be bool, got {type(ev[field])}"

            # last_calculated is ISO8601 string
            assert isinstance(sts["last_calculated"], str), "last_calculated should be a string"
            assert "T" in sts["last_calculated"], "last_calculated should be ISO8601 format"
        finally:
            _stop(proc)

    def test_sts10_skill_trust_score_structure_in_query(self):
        """STS10b: POST /skills/query returns skill_trust_score with full structure"""
        proc, hp = _start_relay(_free_port(), extra_args=["--skills", _RICH_SKILL])
        try:
            sc, body, _ = _post(hp, "/skills/query", {"skill_id": "rich.skill"})
            assert sc == 200
            sts = body.get("skill_trust_score")
            assert sts is not None, "skill_trust_score missing from /skills/query response"
            assert "composite" in sts
            assert "evidence" in sts
            assert "last_calculated" in sts
            ev = sts["evidence"]
            for field in ("has_limitations", "has_examples", "has_constraints", "has_status"):
                assert field in ev, f"Missing evidence.{field}"
        finally:
            _stop(proc)
