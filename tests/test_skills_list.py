"""
test_skills_list.py — ACP v2.10 Skills-lite: GET /skills endpoint + structured AgentCard skills

Tests:
  SK1: GET /skills basic — returns skills list and total fields
  SK2: GET /skills?tag=nlp — filter by tag (exact match)
  SK3: GET /skills?q=summar — keyword search across id/name/description
  SK4: GET /skills pagination — limit/offset parameters
  SK5: GET /skills error handling — non-integer limit returns 400
  SK6: AgentCard /.well-known/acp.json — skills field is structured object array
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

# Structured skills JSON to pass via --skills flag
_SKILLS_JSON = json.dumps([
    {
        "id": "summarize",
        "name": "Text Summarization",
        "description": "Summarizes long documents into concise summaries",
        "tags": ["text", "nlp"],
        "examples": ["Summarize this article", "TL;DR this document"],
        "input_modes": ["text"],
        "output_modes": ["text"],
    },
    {
        "id": "translate",
        "name": "Language Translation",
        "description": "Translates text between languages",
        "tags": ["text", "nlp", "i18n"],
        "examples": ["Translate to French", "Translate to Japanese"],
        "input_modes": ["text"],
        "output_modes": ["text"],
    },
    {
        "id": "code-review",
        "name": "Code Review",
        "description": "Reviews code for bugs, style, and best practices",
        "tags": ["code", "engineering"],
        "examples": ["Review this Python function"],
        "input_modes": ["text"],
        "output_modes": ["text"],
    },
])


def _free_port():
    """Return an OS-assigned free port where port AND port+100 are both free."""
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
    """Wait until relay is up."""
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
    """GET request, returns (status_code, parsed_json)."""
    with urllib.request.urlopen(
        f"http://localhost:{HTTP_PORT}{path}", timeout=5
    ) as r:
        return r.status, json.loads(r.read())


def _get_err(path):
    """GET that handles error responses, returning (status, body)."""
    req = urllib.request.Request(f"http://localhost:{HTTP_PORT}{path}")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


@pytest.fixture(scope="module", autouse=True)
def single_relay():
    global _proc
    env = _make_env()
    _proc = subprocess.Popen(
        [
            sys.executable, RELAY_PATH,
            "--port", str(WS_PORT),
            "--name", "SKAgent",
            "--skills", _SKILLS_JSON,
        ],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
    )
    if not _wait_ready():
        _proc.kill()
        pytest.fail(f"Relay (HTTP:{HTTP_PORT}) did not start in time")
    yield
    _proc.terminate()
    try:
        _proc.wait(timeout=6)
    except subprocess.TimeoutExpired:
        _proc.kill()


# ─────────────────────────────────────────────────────────────────────────────
# SK1: GET /skills basic — returns skills list and total
# ─────────────────────────────────────────────────────────────────────────────

def test_sk1_basic_skills_list():
    """SK1: GET /skills with no params returns all skills, total, has_more."""
    status, data = _get("/skills")
    assert status == 200, f"Expected 200, got {status}: {data}"
    assert "skills"   in data, f"Missing 'skills' key: {data}"
    assert "total"    in data, f"Missing 'total' key: {data}"
    assert "has_more" in data, f"Missing 'has_more' key: {data}"
    assert isinstance(data["skills"],  list), "skills must be a list"
    assert isinstance(data["total"],   int),  "total must be an integer"
    assert isinstance(data["has_more"], bool), "has_more must be bool"

    # We started with 3 structured skills
    assert data["total"] == 3, f"Expected total=3 for 3 registered skills: {data}"
    assert len(data["skills"]) == 3, f"Expected 3 skills in list: {data}"
    assert data["has_more"] is False, f"has_more should be False (total <= default limit 50): {data}"

    # Verify each skill has required structured fields
    for skill in data["skills"]:
        assert "id"   in skill, f"Skill missing 'id': {skill}"
        assert "name" in skill, f"Skill missing 'name': {skill}"
        assert isinstance(skill.get("tags", []),    list), f"tags must be list: {skill}"
        assert isinstance(skill.get("examples", []), list), f"examples must be list: {skill}"


# ─────────────────────────────────────────────────────────────────────────────
# SK2: GET /skills?tag=nlp — filter by tag (exact match)
# ─────────────────────────────────────────────────────────────────────────────

def test_sk2_filter_by_tag():
    """SK2: GET /skills?tag=nlp returns only skills tagged with 'nlp'."""
    status, data = _get("/skills?tag=nlp")
    assert status == 200, f"Expected 200: {data}"
    assert "skills" in data, f"Missing 'skills': {data}"
    assert "total"  in data, f"Missing 'total': {data}"

    # 'summarize' and 'translate' both have tag 'nlp'; 'code-review' does not
    assert data["total"] == 2, f"Expected total=2 for tag=nlp: {data}"
    assert len(data["skills"]) == 2, f"Expected 2 skills for tag=nlp: {data}"

    # All returned skills must have the 'nlp' tag
    for skill in data["skills"]:
        assert "nlp" in skill.get("tags", []), (
            f"Skill '{skill.get('id')}' returned for tag=nlp but doesn't have 'nlp' tag: {skill}"
        )

    # Verify 'code-review' is not in results
    ids = [s["id"] for s in data["skills"]]
    assert "code-review" not in ids, f"'code-review' should not appear in tag=nlp results: {ids}"

    # Filter by a tag that matches no skills
    status2, data2 = _get("/skills?tag=nonexistent")
    assert status2 == 200, f"Expected 200 for nonexistent tag: {data2}"
    assert data2["total"] == 0, f"Expected total=0 for nonexistent tag: {data2}"
    assert data2["skills"] == [], f"Expected empty skills for nonexistent tag: {data2}"


# ─────────────────────────────────────────────────────────────────────────────
# SK3: GET /skills?q=summar — keyword search
# ─────────────────────────────────────────────────────────────────────────────

def test_sk3_keyword_search():
    """SK3: GET /skills?q=summar searches id/name/description (case-insensitive)."""
    status, data = _get("/skills?q=summar")
    assert status == 200, f"Expected 200: {data}"
    assert "skills" in data, f"Missing 'skills': {data}"
    assert "total"  in data, f"Missing 'total': {data}"

    # 'summarize' matches id + description containing "summarize"
    assert data["total"] >= 1, f"Expected at least 1 match for q=summar: {data}"
    ids = [s["id"] for s in data["skills"]]
    assert "summarize" in ids, f"Expected 'summarize' in results for q=summar: {ids}"

    # Test case-insensitivity: uppercase search
    status2, data2 = _get("/skills?q=SUMMAR")
    assert status2 == 200
    ids2 = [s["id"] for s in data2["skills"]]
    assert "summarize" in ids2, f"Case-insensitive search failed for q=SUMMAR: {ids2}"

    # Test search by description keyword
    status3, data3 = _get("/skills?q=best%20practices")
    assert status3 == 200
    ids3 = [s["id"] for s in data3["skills"]]
    assert "code-review" in ids3, (
        f"Expected 'code-review' matching 'best practices' in description: {ids3}"
    )

    # Test q with no matches
    status4, data4 = _get("/skills?q=zzznomatch999")
    assert status4 == 200
    assert data4["total"] == 0, f"Expected 0 results for nonsense query: {data4}"


# ─────────────────────────────────────────────────────────────────────────────
# SK4: GET /skills pagination — limit/offset
# ─────────────────────────────────────────────────────────────────────────────

def test_sk4_pagination():
    """SK4: limit/offset pagination works correctly for /skills."""
    # Get page 1: limit=2, offset=0
    status1, page1 = _get("/skills?limit=2&offset=0")
    assert status1 == 200, f"Expected 200: {page1}"
    assert len(page1["skills"]) <= 2, f"limit=2 should return at most 2 skills: {page1}"
    assert page1["total"] == 3, f"Expected total=3: {page1}"
    assert page1["has_more"] is True, f"has_more should be True (3 skills, page size 2): {page1}"
    assert page1["next_offset"] == 2, f"next_offset should be 2: {page1}"

    # Get page 2: limit=2, offset=2
    status2, page2 = _get("/skills?limit=2&offset=2")
    assert status2 == 200, f"Expected 200: {page2}"
    assert len(page2["skills"]) == 1, f"Page 2 should have 1 skill (3-2=1): {page2}"
    assert page2["has_more"] is False, f"has_more should be False on last page: {page2}"

    # Verify no overlap between pages
    ids1 = {s["id"] for s in page1["skills"]}
    ids2 = {s["id"] for s in page2["skills"]}
    overlap = ids1 & ids2
    assert len(overlap) == 0, f"Pagination overlap detected: {overlap}"

    # limit=100 (exceeds total): has_more=False, returns all
    status3, all_data = _get("/skills?limit=100&offset=0")
    assert status3 == 200
    assert len(all_data["skills"]) == 3, f"Expected all 3 skills with limit=100: {all_data}"
    assert all_data["has_more"] is False, f"has_more should be False when returning all: {all_data}"

    # offset beyond total: empty result
    status4, empty_data = _get("/skills?offset=100")
    assert status4 == 200
    assert len(empty_data["skills"]) == 0, f"Expected empty list for offset beyond total: {empty_data}"
    assert empty_data["has_more"] is False


# ─────────────────────────────────────────────────────────────────────────────
# SK5: GET /skills error handling — non-integer limit/offset → 400
# ─────────────────────────────────────────────────────────────────────────────

def test_sk5_error_handling_invalid_params():
    """SK5: Non-integer limit or offset returns 400 ERR_INVALID_REQUEST."""
    # Non-integer limit
    status_l, data_l = _get_err("/skills?limit=abc&offset=0")
    assert status_l == 400, (
        f"Expected 400 for limit=abc: status={status_l}, data={data_l}"
    )
    assert data_l.get("error_code") == "ERR_INVALID_REQUEST", (
        f"Expected ERR_INVALID_REQUEST for limit=abc: {data_l}"
    )

    # Non-integer offset
    status_o, data_o = _get_err("/skills?limit=10&offset=xyz")
    assert status_o == 400, (
        f"Expected 400 for offset=xyz: status={status_o}, data={data_o}"
    )
    assert data_o.get("error_code") == "ERR_INVALID_REQUEST", (
        f"Expected ERR_INVALID_REQUEST for offset=xyz: {data_o}"
    )

    # Both invalid
    status_b, data_b = _get_err("/skills?limit=foo&offset=bar")
    assert status_b == 400, (
        f"Expected 400 for limit=foo&offset=bar: status={status_b}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# SK6: AgentCard /.well-known/acp.json — skills is structured object array
# ─────────────────────────────────────────────────────────────────────────────

def test_sk6_agentcard_structured_skills():
    """SK6: AgentCard skills field is a structured object array (not plain strings)."""
    status, data = _get("/.well-known/acp.json")
    assert status == 200, f"Expected 200 from AgentCard: {data}"

    # Card may be wrapped in {"self": ..., "peer": ...} or returned directly
    card = data.get("self", data)
    assert "skills" in card, f"AgentCard missing 'skills' key: {card}"

    skills = card["skills"]
    assert isinstance(skills, list), f"skills must be a list: {skills}"
    assert len(skills) == 3, f"Expected 3 skills in AgentCard: {skills}"

    # Every skill must be a structured object (not a plain string)
    for skill in skills:
        assert isinstance(skill, dict), (
            f"Each skill must be a dict (structured object), got: {type(skill)} — {skill}"
        )
        assert "id"   in skill, f"Skill missing 'id': {skill}"
        assert "name" in skill, f"Skill missing 'name': {skill}"
        assert "tags" in skill, f"Skill missing 'tags': {skill}"
        assert isinstance(skill["tags"],         list), f"tags must be list: {skill}"
        assert isinstance(skill.get("examples", []), list), f"examples must be list: {skill}"
        assert isinstance(skill.get("input_modes", []), list), f"input_modes must be list: {skill}"
        assert isinstance(skill.get("output_modes", []), list), f"output_modes must be list: {skill}"

    # Verify specific skill content
    skill_ids = [s["id"] for s in skills]
    assert "summarize"   in skill_ids, f"'summarize' not found in AgentCard skills: {skill_ids}"
    assert "translate"   in skill_ids, f"'translate' not found in AgentCard skills: {skill_ids}"
    assert "code-review" in skill_ids, f"'code-review' not found in AgentCard skills: {skill_ids}"

    # Verify 'summarize' has expected structured fields
    summarize = next(s for s in skills if s["id"] == "summarize")
    assert summarize["name"] == "Text Summarization", (
        f"Unexpected name for 'summarize': {summarize['name']}"
    )
    assert "nlp" in summarize["tags"], (
        f"Expected 'nlp' tag on 'summarize': {summarize['tags']}"
    )

    # Verify endpoints.skills is declared in AgentCard
    endpoints = card.get("endpoints", {})
    assert "skills" in endpoints, (
        f"AgentCard endpoints missing 'skills' key (v2.10): {endpoints}"
    )
    assert endpoints["skills"] == "/skills", (
        f"Unexpected skills endpoint: {endpoints['skills']}"
    )


# ─────────────────────────────────────────────────────────────────────────────

def run_tests():
    """Pytest entry point for direct execution."""
    pytest.main([__file__, "-v"])


if __name__ == "__main__":
    run_tests()
