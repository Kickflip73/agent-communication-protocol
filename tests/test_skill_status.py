"""
test_skill_status.py — v2.29: GET /skills/<id>/status per-skill availability probe

SS1  — known skill, no limitations → available=True, reason=None
SS2  — known skill, runtime capability limitation → available=False, reason set
SS3  — known skill, runtime access limitation → available=False, reason set
SS4  — known skill, permanent limitation → available=True (permanent lims don't block)
SS5  — known skill, string-shorthand limitation → available=True (no runtime flag)
SS6  — unknown skill_id → 404 ERR_NOT_FOUND
SS7  — empty skill_id in path → 400 ERR_INVALID_REQUEST
SS8  — skill with multiple limitations: first runtime cap → available=False
SS9  — capabilities.skill_status_probe declared
SS10 — last_checked field present in response
SS11 — endpoints.skill_status declared in agent card
SS12 — skill with permanent=True capability limitation → available=True
"""

import json
import sys
import os
import time
import subprocess
import socket
import urllib.request
import urllib.error
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
RELAY_PATH = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")


# ── helpers ──────────────────────────────────────────────────────────────────

def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_relay(skills_json, name="TestAgent"):
    ws_port   = _free_port()
    http_port = ws_port + 100
    proc = subprocess.Popen(
        [sys.executable, RELAY_PATH, "--port", str(ws_port), "--name", name,
         "--skills", skills_json],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    base = f"http://127.0.0.1:{http_port}"
    for _ in range(75):
        try:
            urllib.request.urlopen(f"{base}/.well-known/acp.json", timeout=1)
            return proc, base
        except Exception:
            time.sleep(0.2)
    proc.kill()
    raise RuntimeError(f"Relay (HTTP:{http_port}) did not start in time")


def _get(base, path):
    try:
        with urllib.request.urlopen(f"{base}{path}", timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


# ── shared fixtures ───────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def relay_plain():
    skills = json.dumps([{"id": "summarize", "name": "Summarize", "description": "text summary"}])
    proc, base = _start_relay(skills)
    yield base
    proc.kill(); proc.wait()


@pytest.fixture(scope="module")
def relay_runtime_cap():
    skills = json.dumps([{
        "id": "image_gen",
        "name": "Image Gen",
        "limitations": [{"kind": "capability", "code": "no_gpu",
                         "message": "GPU unavailable", "permanent": False}],
    }])
    proc, base = _start_relay(skills)
    yield base
    proc.kill(); proc.wait()


@pytest.fixture(scope="module")
def relay_runtime_access():
    skills = json.dumps([{
        "id": "db_query",
        "name": "DB Query",
        "limitations": [{"kind": "access", "code": "db_down",
                         "message": "database offline", "permanent": False}],
    }])
    proc, base = _start_relay(skills)
    yield base
    proc.kill(); proc.wait()


@pytest.fixture(scope="module")
def relay_permanent_lim():
    skills = json.dumps([{
        "id": "translate",
        "name": "Translate",
        "limitations": [{"kind": "modality", "code": "no_audio",
                         "message": "audio not supported", "permanent": True}],
    }])
    proc, base = _start_relay(skills)
    yield base
    proc.kill(); proc.wait()


@pytest.fixture(scope="module")
def relay_string_lim():
    skills = json.dumps([{
        "id": "ocr",
        "name": "OCR",
        "limitations": ["no_handwriting", "english_only"],
    }])
    proc, base = _start_relay(skills)
    yield base
    proc.kill(); proc.wait()


@pytest.fixture(scope="module")
def relay_multi_lim():
    skills = json.dumps([{
        "id": "video",
        "name": "Video",
        "limitations": [
            {"kind": "modality", "code": "no_audio", "permanent": True},
            {"kind": "capability", "code": "encoder_busy",
             "message": "encoder busy", "permanent": False},
        ],
    }])
    proc, base = _start_relay(skills)
    yield base
    proc.kill(); proc.wait()


# ── tests ─────────────────────────────────────────────────────────────────────

class TestSkillStatusProbe:

    def test_ss1_plain_skill_available(self, relay_plain):
        status, data = _get(relay_plain, "/skills/summarize/status")
        assert status == 200
        assert data["skill_id"]  == "summarize"
        assert data["available"] is True
        assert data["reason"]    is None

    def test_ss2_runtime_capability_unavailable(self, relay_runtime_cap):
        status, data = _get(relay_runtime_cap, "/skills/image_gen/status")
        assert status == 200
        assert data["available"] is False
        assert data["reason"] is not None
        assert "gpu" in data["reason"].lower() or "GPU" in data["reason"]

    def test_ss3_runtime_access_unavailable(self, relay_runtime_access):
        status, data = _get(relay_runtime_access, "/skills/db_query/status")
        assert status == 200
        assert data["available"] is False
        assert data["reason"] is not None

    def test_ss4_permanent_limitation_still_available(self, relay_permanent_lim):
        status, data = _get(relay_permanent_lim, "/skills/translate/status")
        assert status == 200
        assert data["available"] is True
        assert data["reason"]    is None

    def test_ss5_string_shorthand_available(self, relay_string_lim):
        status, data = _get(relay_string_lim, "/skills/ocr/status")
        assert status == 200
        assert data["available"] is True

    def test_ss6_unknown_skill_404(self, relay_plain):
        status, data = _get(relay_plain, "/skills/nonexistent_skill/status")
        assert status == 404
        assert data["error_code"] == "ERR_NOT_FOUND"

    def test_ss7_empty_skill_id_400(self, relay_plain):
        """Path /skills//status should yield 400."""
        status, data = _get(relay_plain, "/skills//status")
        assert status == 400
        assert data.get("error_code") == "ERR_INVALID_REQUEST"

    def test_ss8_multi_lim_first_runtime_triggers(self, relay_multi_lim):
        status, data = _get(relay_multi_lim, "/skills/video/status")
        assert status == 200
        assert data["available"] is False
        assert "encoder" in (data["reason"] or "").lower()

    def test_ss9_capability_declared(self, relay_plain):
        _, raw = _get(relay_plain, "/.well-known/acp.json")
        card = raw.get("self", raw)
        assert card["capabilities"].get("skill_status_probe") is True

    def test_ss10_last_checked_present(self, relay_plain):
        _, data = _get(relay_plain, "/skills/summarize/status")
        assert "last_checked" in data
        assert data["last_checked"] is not None

    def test_ss11_endpoint_declared(self, relay_plain):
        _, raw = _get(relay_plain, "/.well-known/acp.json")
        card = raw.get("self", raw)
        assert "skill_status" in card.get("endpoints", {})

    def test_ss12_permanent_cap_limitation_available(self):
        """permanent=True capability limitation must NOT block availability."""
        skills = json.dumps([{
            "id": "forever_limited",
            "limitations": [{"kind": "capability", "code": "no_feature_x", "permanent": True}],
        }])
        proc, base = _start_relay(skills)
        try:
            status, data = _get(base, "/skills/forever_limited/status")
            assert status == 200
            assert data["available"] is True
        finally:
            proc.kill(); proc.wait()
