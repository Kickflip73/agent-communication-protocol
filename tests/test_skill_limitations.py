"""
test_skill_limitations.py — ACP v2.28 per-skill limitations[] field (ref A2A #1694)

Tests:
  SL1:  GET /skills — each skill has a 'limitations' field (empty list when not declared)
  SL2:  GET /skills — skill with declared limitations returns LimitationObject[]
  SL3:  LimitationObject has required fields: kind, code, message, permanent
  SL4:  Limitation string shorthand is auto-promoted to LimitationObject
  SL5:  GET /skills?has_limitation=capability — returns only skills with capability limitation
  SL6:  GET /skills?has_limitation=no_audio_input — filter by code (exact match)
  SL7:  GET /skills?has_limitation=modality — returns skills with modality limitation kind
  SL8:  GET /skills?has_limitation=nonexistent — returns empty list (no match)
  SL9:  POST /skills/query — response includes skill_limitations_declared field
  SL10: POST /skills/query — skill_limitations_declared matches declared limitations
  SL11: AgentCard /.well-known/acp.json — skill objects include limitations field
  SL12: capabilities.skill_limitations=True declared in AgentCard
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

# Skills JSON with limitations declared at skill level
_SKILLS_JSON = json.dumps([
    {
        "id": "summarize",
        "name": "Text Summarization",
        "description": "Summarizes long documents",
        "tags": ["text", "nlp"],
        "input_modes": ["text"],
        "output_modes": ["text"],
        # No limitations — should default to []
    },
    {
        "id": "transcribe",
        "name": "Audio Transcription",
        "description": "Transcribes audio to text",
        "tags": ["audio", "nlp"],
        "input_modes": ["audio", "text"],
        "output_modes": ["text"],
        "limitations": [
            # String shorthand — should be auto-promoted to LimitationObject
            "no_realtime_streaming",
            # Full LimitationObject
            {
                "kind": "modality",
                "code": "no_video_input",
                "message": "Video input is not supported; audio only",
                "permanent": True,
            },
        ],
    },
    {
        "id": "code-review",
        "name": "Code Review",
        "description": "Reviews code for bugs and style",
        "tags": ["code"],
        "input_modes": ["text"],
        "output_modes": ["text"],
        "limitations": [
            {
                "kind": "capability",
                "code": "no_audio_input",
                "message": "Cannot process audio files",
                "permanent": True,
            },
            {
                "kind": "domain",
                "code": "no_binary_analysis",
                "message": "Cannot analyze compiled binaries",
                "permanent": False,
            },
        ],
    },
])


def _find_free_port() -> int:
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def relay():
    ws_port   = _find_free_port()
    http_port = ws_port + 100
    proc = subprocess.Popen(
        [sys.executable, RELAY_PATH, "--port", str(ws_port),
         "--name", "LimAgent", "--skills", _SKILLS_JSON],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    base = f"http://127.0.0.1:{http_port}"
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


def _get(base, path):
    try:
        with urllib.request.urlopen(f"{base}{path}", timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _post(base, path, body):
    data = json.dumps(body).encode()
    req  = urllib.request.Request(
        f"{base}{path}", data=data,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


# ─── Tests ────────────────────────────────────────────────────────────────────

def test_SL1_all_skills_have_limitations_field(relay):
    """Every skill must have a 'limitations' field (empty list when not declared)."""
    _, body = _get(relay, "/skills")
    for skill in body["skills"]:
        assert "limitations" in skill, f"skill {skill['id']} missing limitations field"
        assert isinstance(skill["limitations"], list)


def test_SL2_declared_limitations_present(relay):
    """Skill with declared limitations returns LimitationObject[]."""
    _, body = _get(relay, "/skills")
    skill = next(s for s in body["skills"] if s["id"] == "transcribe")
    assert len(skill["limitations"]) == 2, "transcribe should have 2 limitations"


def test_SL3_limitation_object_has_required_fields(relay):
    """LimitationObject must have: kind, code, message, permanent."""
    _, body = _get(relay, "/skills")
    skill = next(s for s in body["skills"] if s["id"] == "code-review")
    for lim in skill["limitations"]:
        for field in ("kind", "code", "message", "permanent"):
            assert field in lim, f"LimitationObject missing '{field}' in skill code-review"
        assert isinstance(lim["permanent"], bool)


def test_SL4_string_shorthand_promoted_to_object(relay):
    """String limitation shorthand must be promoted to LimitationObject."""
    _, body = _get(relay, "/skills")
    skill = next(s for s in body["skills"] if s["id"] == "transcribe")
    # First entry was a string "no_realtime_streaming"
    lim0 = skill["limitations"][0]
    assert "kind" in lim0 and "code" in lim0 and "message" in lim0 and "permanent" in lim0
    assert lim0["code"] == "no_realtime_streaming"


def test_SL5_filter_by_limitation_kind_capability(relay):
    """GET /skills?has_limitation=capability — returns skills with capability kind.
    
    Note: string shorthand is promoted to kind='capability', so 'transcribe'
    (which has "no_realtime_streaming" string) also appears here.
    'summarize' has no limitations and must NOT appear.
    """
    _, body = _get(relay, "/skills?has_limitation=capability")
    ids = [s["id"] for s in body["skills"]]
    assert "code-review"  in ids, "code-review explicitly declares capability limitation"
    assert "transcribe"   in ids, "transcribe's string shorthand is promoted to kind=capability"
    assert "summarize" not in ids, "summarize has no limitations at all"


def test_SL6_filter_by_limitation_code(relay):
    """GET /skills?has_limitation=no_audio_input — returns code-review only."""
    _, body = _get(relay, "/skills?has_limitation=no_audio_input")
    ids = [s["id"] for s in body["skills"]]
    assert ids == ["code-review"]


def test_SL7_filter_by_limitation_kind_modality(relay):
    """GET /skills?has_limitation=modality — returns transcribe (has modality limitation)."""
    _, body = _get(relay, "/skills?has_limitation=modality")
    ids = [s["id"] for s in body["skills"]]
    assert "transcribe" in ids
    assert "summarize" not in ids


def test_SL8_filter_no_match_returns_empty(relay):
    """GET /skills?has_limitation=nonexistent — empty skills list."""
    _, body = _get(relay, "/skills?has_limitation=nonexistent_limitation_xyz")
    assert body["skills"] == []
    assert body["total"] == 0


def test_SL9_query_skill_includes_limitations_declared(relay):
    """POST /skills/query — response includes skill_limitations_declared field."""
    status, body = _post(relay, "/skills/query", {"skill_id": "code-review"})
    assert status == 200
    assert "skill_limitations_declared" in body, "Missing skill_limitations_declared in QuerySkill response"


def test_SL10_query_skill_limitations_match_declared(relay):
    """POST /skills/query — skill_limitations_declared matches what was declared."""
    _, body = _post(relay, "/skills/query", {"skill_id": "code-review"})
    lims = body["skill_limitations_declared"]
    assert len(lims) == 2
    codes = {lim["code"] for lim in lims}
    assert "no_audio_input"    in codes
    assert "no_binary_analysis" in codes


def test_SL11_agent_card_skills_include_limitations(relay):
    """AgentCard /.well-known/acp.json — skill objects include limitations field."""
    _, body = _get(relay, "/.well-known/acp.json")
    card   = body.get("self", body)
    skills = card.get("skills", [])
    assert len(skills) > 0
    for skill in skills:
        assert "limitations" in skill, f"AgentCard skill {skill.get('id')} missing limitations"


def test_SL12_capability_flag_declared(relay):
    """capabilities.skill_limitations=True must be declared."""
    _, body = _get(relay, "/.well-known/acp.json")
    card = body.get("self", body)
    caps = card.get("capabilities", {})
    assert caps.get("skill_limitations") is True, "capabilities.skill_limitations must be True"
