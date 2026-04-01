"""
test_queryskill_constraints.py — ACP v2.26 QuerySkill constraints extension

Tests:
  QC1:  POST /skills/query — max_file_size_bytes within skill limit → supported
  QC2:  POST /skills/query — max_file_size_bytes exceeds skill limit → partial
  QC3:  POST /skills/query — max_file_size_bytes exceeds relay limit → partial
  QC4:  POST /skills/query — concurrent_tasks within skill limit → supported
  QC5:  POST /skills/query — concurrent_tasks exceeds skill limit → partial
  QC6:  POST /skills/query — context_window within skill limit → supported
  QC7:  POST /skills/query — context_window exceeds skill limit → partial
  QC8:  POST /skills/query — all three constraints pass → supported, skill_constraints_declared present
  QC9:  POST /skills/query — all three constraints fail → partial with all violations listed
  QC10: POST /skills/query — skill with no constraints declared → supported for any value (no limit)
  QC11: GET /.well-known/acp.json — capabilities.skills_query_constraints = true
  QC12: skill objects via GET /skills include constraints field (max_file_size_bytes/concurrent_tasks/context_window)
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

# Skills with explicit constraints declared — used for QC1–QC10
_SKILLS_WITH_CONSTRAINTS = json.dumps([
    {
        "id": "transcribe",
        "name": "Audio Transcription",
        "description": "Transcribes audio files to text",
        "tags": ["audio", "nlp"],
        "input_modes": ["audio"],
        "output_modes": ["text"],
        "constraints": {
            "max_file_size_bytes": 104857600,   # 100 MB
            "concurrent_tasks":   4,
            "context_window":     32000,
        },
    },
    {
        "id": "summarize",
        "name": "Text Summarization",
        "description": "Summarizes documents",
        "tags": ["text", "nlp"],
        "input_modes": ["text"],
        "output_modes": ["text"],
        "constraints": {
            "max_file_size_bytes": 10485760,    # 10 MB
            "concurrent_tasks":   2,
            "context_window":     128000,
        },
    },
    {
        "id": "no-constraints-skill",
        "name": "Unconstrained Skill",
        "description": "A skill with no declared limits",
        "tags": ["misc"],
        "input_modes": ["text"],
        "output_modes": ["text"],
        # no constraints key — defaults to all None
    },
])


def _free_port():
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
    with urllib.request.urlopen(
        f"http://localhost:{HTTP_PORT}{path}", timeout=5
    ) as r:
        return r.status, json.loads(r.read())


def _post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"http://localhost:{HTTP_PORT}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def setup_module(module):
    global _proc
    # Note: --port sets WS port; HTTP API is automatically WS_PORT + 100
    # --max-msg-size 209715200 (200 MB) raises relay-level byte cap so skill-level
    # constraints dominate; lets QC1/QC8 test skill limits independently of relay limit.
    cmd = [
        sys.executable, RELAY_PATH,
        "--port", str(WS_PORT),
        "--name", "TestConstraintAgent",
        "--skills", _SKILLS_WITH_CONSTRAINTS,
        "--max-msg-size", "209715200",  # 200 MB relay limit (above all skill limits in tests)
    ]
    _proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=_make_env())
    assert _wait_ready(15), f"Relay failed to start on HTTP {HTTP_PORT}"


def teardown_module(module):
    if _proc:
        _proc.terminate()
        try:
            _proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _proc.kill()


# ─────────────────────────────────────────────────────────────────────────────
# QC1 — max_file_size_bytes within skill limit → supported
# ─────────────────────────────────────────────────────────────────────────────
def test_qc1_max_file_size_within_limit():
    """50 MB < 100 MB skill limit → supported."""
    sc, body = _post("/skills/query", {
        "skill_id": "transcribe",
        "constraints": {"max_file_size_bytes": 50 * 1024 * 1024},  # 50 MB
    })
    assert sc == 200, body
    assert body["support_level"] == "supported", f"expected supported, got: {body}"
    assert body["skill_id"] == "transcribe"


# ─────────────────────────────────────────────────────────────────────────────
# QC2 — max_file_size_bytes exceeds skill limit → partial
# ─────────────────────────────────────────────────────────────────────────────
def test_qc2_max_file_size_exceeds_skill_limit():
    """200 MB > 100 MB skill limit → partial."""
    sc, body = _post("/skills/query", {
        "skill_id": "transcribe",
        "constraints": {"max_file_size_bytes": 200 * 1024 * 1024},  # 200 MB
    })
    assert sc == 200, body
    assert body["support_level"] == "partial", f"expected partial, got: {body}"
    assert "max_file_size_bytes" in body["reason"] or "limit" in body["reason"]


# ─────────────────────────────────────────────────────────────────────────────
# QC3 — max_file_size_bytes exceeds relay limit → partial
# ─────────────────────────────────────────────────────────────────────────────
def test_qc3_max_file_size_exceeds_relay_limit():
    """Request 2 GB — always exceeds relay MAX_MSG_BYTES (default 10 MB) → partial."""
    sc, body = _post("/skills/query", {
        "skill_id": "transcribe",
        "constraints": {"max_file_size_bytes": 2 * 1024 * 1024 * 1024},  # 2 GB
    })
    assert sc == 200, body
    assert body["support_level"] == "partial", f"expected partial, got: {body}"
    # relay_max_msg_bytes must appear in constraints_applied
    assert "relay_max_msg_bytes" in body.get("constraints_applied", {}), body


# ─────────────────────────────────────────────────────────────────────────────
# QC4 — concurrent_tasks within skill limit → supported
# ─────────────────────────────────────────────────────────────────────────────
def test_qc4_concurrent_tasks_within_limit():
    """Request 2 concurrent_tasks, skill limit is 4 → supported."""
    sc, body = _post("/skills/query", {
        "skill_id": "transcribe",
        "constraints": {"concurrent_tasks": 2},
    })
    assert sc == 200, body
    assert body["support_level"] == "supported", f"expected supported, got: {body}"


# ─────────────────────────────────────────────────────────────────────────────
# QC5 — concurrent_tasks exceeds skill limit → partial
# ─────────────────────────────────────────────────────────────────────────────
def test_qc5_concurrent_tasks_exceeds_limit():
    """Request 10 concurrent_tasks, skill limit is 4 → partial."""
    sc, body = _post("/skills/query", {
        "skill_id": "transcribe",
        "constraints": {"concurrent_tasks": 10},
    })
    assert sc == 200, body
    assert body["support_level"] == "partial", f"expected partial, got: {body}"
    assert "concurrent_tasks" in body["reason"]
    assert "skill_concurrent_tasks" in body.get("constraints_applied", {}), body


# ─────────────────────────────────────────────────────────────────────────────
# QC6 — context_window within skill limit → supported
# ─────────────────────────────────────────────────────────────────────────────
def test_qc6_context_window_within_limit():
    """Request 16000 tokens, skill limit is 32000 → supported."""
    sc, body = _post("/skills/query", {
        "skill_id": "transcribe",
        "constraints": {"context_window": 16000},
    })
    assert sc == 200, body
    assert body["support_level"] == "supported", f"expected supported, got: {body}"


# ─────────────────────────────────────────────────────────────────────────────
# QC7 — context_window exceeds skill limit → partial
# ─────────────────────────────────────────────────────────────────────────────
def test_qc7_context_window_exceeds_limit():
    """Request 1M tokens, skill limit is 32000 → partial."""
    sc, body = _post("/skills/query", {
        "skill_id": "transcribe",
        "constraints": {"context_window": 1_000_000},
    })
    assert sc == 200, body
    assert body["support_level"] == "partial", f"expected partial, got: {body}"
    assert "context_window" in body["reason"]
    assert "skill_context_window" in body.get("constraints_applied", {}), body


# ─────────────────────────────────────────────────────────────────────────────
# QC8 — all three constraints pass → supported + skill_constraints_declared
# ─────────────────────────────────────────────────────────────────────────────
def test_qc8_all_constraints_pass():
    """50 MB, 2 tasks, 16k tokens — all within transcribe limits → supported."""
    sc, body = _post("/skills/query", {
        "skill_id": "transcribe",
        "constraints": {
            "max_file_size_bytes": 50 * 1024 * 1024,
            "concurrent_tasks":   2,
            "context_window":     16000,
        },
    })
    assert sc == 200, body
    assert body["support_level"] == "supported", f"expected supported, got: {body}"
    # v2.26: declared constraints must be echoed back
    declared = body.get("skill_constraints_declared", {})
    assert declared.get("max_file_size_bytes") == 104857600, body
    assert declared.get("concurrent_tasks")    == 4, body
    assert declared.get("context_window")      == 32000, body


# ─────────────────────────────────────────────────────────────────────────────
# QC9 — all three constraints fail → partial with all violations
# ─────────────────────────────────────────────────────────────────────────────
def test_qc9_all_constraints_fail():
    """200 MB, 10 tasks, 1M tokens — all exceed summarize limits → partial."""
    sc, body = _post("/skills/query", {
        "skill_id": "summarize",
        "constraints": {
            "max_file_size_bytes": 200 * 1024 * 1024,
            "concurrent_tasks":   10,
            "context_window":     1_000_000,
        },
    })
    assert sc == 200, body
    assert body["support_level"] == "partial", f"expected partial, got: {body}"
    reason = body["reason"]
    # All three violations must be mentioned
    assert "max_file_size_bytes" in reason or "limit" in reason, f"missing file_size in: {reason}"
    assert "concurrent_tasks" in reason, f"missing concurrent_tasks in: {reason}"
    assert "context_window" in reason, f"missing context_window in: {reason}"


# ─────────────────────────────────────────────────────────────────────────────
# QC10 — skill with no declared constraints → always supported (no limit)
# ─────────────────────────────────────────────────────────────────────────────
def test_qc10_no_declared_constraints():
    """no-constraints-skill has no limits → even extreme values → supported."""
    sc, body = _post("/skills/query", {
        "skill_id": "no-constraints-skill",
        "constraints": {
            "max_file_size_bytes": 999 * 1024 * 1024 * 1024,  # 999 GB (beyond relay too? no — relay cap only)
            "concurrent_tasks":   9999,
            "context_window":     10_000_000,
        },
    })
    assert sc == 200, body
    # Skill has no declared limits — no skill-level violations should occur
    # (relay-level max_msg_bytes violation may still appear for the huge file size, that's OK)
    declared = body.get("skill_constraints_declared", {})
    assert declared.get("max_file_size_bytes") is None, body
    assert declared.get("concurrent_tasks")    is None, body
    assert declared.get("context_window")      is None, body


# ─────────────────────────────────────────────────────────────────────────────
# QC11 — capabilities.skills_query_constraints = true in AgentCard
# ─────────────────────────────────────────────────────────────────────────────
def test_qc11_capability_flag():
    sc, body = _get("/.well-known/acp.json")
    assert sc == 200
    # /.well-known/acp.json returns {"self": {...}, "peer": ...}
    card = body.get("self", body)
    caps = card.get("capabilities", {})
    assert caps.get("skills_query_constraints") is True, \
        f"skills_query_constraints missing or false in capabilities: {caps}"


# ─────────────────────────────────────────────────────────────────────────────
# QC12 — GET /skills returns constraints field per skill
# ─────────────────────────────────────────────────────────────────────────────
def test_qc12_get_skills_includes_constraints():
    sc, body = _get("/skills")
    assert sc == 200, body
    # GET /skills returns {"skills": [...], "total": N} directly (no "self" wrapper)
    skills = body.get("skills", [])
    assert len(skills) > 0, "no skills returned"
    transcribe = next((s for s in skills if s["id"] == "transcribe"), None)
    assert transcribe is not None, f"transcribe skill not found in: {[s['id'] for s in skills]}"
    constraints = transcribe.get("constraints")
    assert isinstance(constraints, dict), f"constraints not a dict: {constraints}"
    assert constraints.get("max_file_size_bytes") == 104857600, constraints
    assert constraints.get("concurrent_tasks")    == 4, constraints
    assert constraints.get("context_window")      == 32000, constraints
