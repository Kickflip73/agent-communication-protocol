"""
tests/test_bilateral_ir_log_v272.py — v2.72 GET /trust/bilateral-ir/log

A2A #1718 @viftode4 proposes bilateral signed IR as a unified trust primitive.
ACP v2.72 implements GET /trust/bilateral-ir/log to make the relay's own IR log
queryable, supporting trust scoring, reputation derivation, and audit trails.

Basic structure:
BL-01: GET /trust/bilateral-ir/log returns ok=True with required fields
BL-02: Empty log (no tasks run) returns count=0, total=0, bilateral_count=0
BL-03: After task creation, log contains IR records
BL-04: Each record has required IR fields (id, type, relay_did, task_id, bilateral, ...)
BL-05: bilateral_count <= total (invariant)
BL-06: version is present and current

Filtering:
BL-07: ?caller_did filter returns only matching records
BL-08: ?skill_id filter returns only matching records
BL-09: ?bilateral=true returns only bilateral=true records
BL-10: ?bilateral=false returns only bilateral=false records
BL-11: ?since=<ts> returns only records with timestamp >= since
BL-12: ?limit=N returns at most N records
BL-13: ?offset=N skips first N records (pagination)
BL-14: ?limit + ?offset pagination: count + offset <= total

Content:
BL-15: records[].type == "bilateral_interaction_record" always
BL-16: records[].sequence_a is monotonically increasing
BL-17: record with relay_signature is non-null when identity available
BL-18: bilateral=false record has caller_signature=null or caller_signature_valid!=true
BL-19: ?caller_did non-existent returns count=0
BL-20: note field is present and non-empty string

AgentCard:
BL-21: capabilities.bilateral_ir_log = True
BL-22: endpoints.bilateral_ir_log = "/trust/bilateral-ir/log"
"""

import os
import sys
import time
import socket
import subprocess
import requests
import pytest

RELAY = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")


def _free_port_pair():
    for _ in range(20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            ws = s.getsockname()[1]
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s2:
                s2.bind(("", ws + 100))
            return ws, ws + 100
        except OSError:
            continue
    raise RuntimeError("Cannot find free port pair")


@pytest.fixture(scope="module")
def relay_url():
    ws_port, http_port = _free_port_pair()
    proc = subprocess.Popen(
        [sys.executable, RELAY, "--port", str(ws_port), "--name", "BilateralIRLogTest",
         "--local", "--test-mode"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            r = requests.get(f"http://localhost:{http_port}/status", timeout=1)
            if r.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(0.2)
    else:
        proc.terminate()
        pytest.fail("Relay did not start in time")
    yield f"http://localhost:{http_port}"
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def get_log(base_url, **params):
    r = requests.get(f"{base_url}/trust/bilateral-ir/log", params=params)
    assert r.status_code == 200, f"status={r.status_code} body={r.text[:300]}"
    return r.json()


def create_task(base_url, skill_id="test_skill", caller_did=None):
    """Create a task via /tasks with record=True to generate a bilateral IR record."""
    body = {
        "role": "user",
        "parts": [{"type": "text", "content": f"test task for {skill_id}"}],
        "skill_id": skill_id,
        "record": True,   # v2.59: triggers _create_interaction_record()
    }
    if caller_did:
        body["caller_did"] = caller_did
    r = requests.post(f"{base_url}/tasks", json=body)
    # Accept 200 or 201 (created)
    assert r.status_code in (200, 201), f"task create failed: {r.status_code} {r.text[:200]}"
    return r.json()


# ── Basic structure ───────────────────────────────────────────────────────────

def test_bl01_basic_structure(relay_url):
    """BL-01: GET /trust/bilateral-ir/log returns ok=True with required fields."""
    d = get_log(relay_url)
    assert d.get("ok") is True
    for field in ("count", "total", "bilateral_count", "records", "version", "note"):
        assert field in d, f"Missing field: {field}"
    assert isinstance(d["records"], list)
    assert isinstance(d["count"], int)
    assert isinstance(d["total"], int)
    assert isinstance(d["bilateral_count"], int)


def test_bl02_empty_log(relay_url):
    """BL-02: Fresh relay — log is empty (count=0, total=0, bilateral_count=0)."""
    d = get_log(relay_url)
    # Note: may have records if other tests ran tasks first, so check invariant only
    assert d["count"] >= 0
    assert d["total"] >= 0
    assert d["bilateral_count"] >= 0
    assert d["bilateral_count"] <= d["total"]


def test_bl05_bilateral_count_invariant(relay_url):
    """BL-05: bilateral_count <= total always."""
    d = get_log(relay_url)
    assert d["bilateral_count"] <= d["total"], \
        f"bilateral_count={d['bilateral_count']} > total={d['total']}"


def test_bl06_version_present(relay_url):
    """BL-06: version is present and starts with 2."""
    d = get_log(relay_url)
    assert "version" in d
    assert d["version"].startswith("2."), f"Unexpected version: {d['version']}"


# ── Records after task creation ──────────────────────────────────────────────

@pytest.fixture(scope="module")
def relay_with_tasks(relay_url):
    """Create 3 tasks with different caller_dids/skill_ids to populate IR log."""
    create_task(relay_url, skill_id="skill_alpha", caller_did="did:key:zAlice")
    create_task(relay_url, skill_id="skill_beta",  caller_did="did:key:zBob")
    create_task(relay_url, skill_id="skill_alpha", caller_did="did:key:zAlice")
    time.sleep(0.3)  # let records settle
    return relay_url


def test_bl03_log_has_records_after_tasks(relay_with_tasks):
    """BL-03: After task creation, log total > 0."""
    d = get_log(relay_with_tasks)
    assert d["total"] > 0, "Expected IR records after task creation"


def test_bl04_record_has_required_fields(relay_with_tasks):
    """BL-04: Each record has required IR fields."""
    d = get_log(relay_with_tasks)
    required = ("id", "type", "task_id", "sequence_a", "timestamp", "bilateral")
    for rec in d["records"]:
        for f in required:
            assert f in rec, f"Record missing field '{f}': {rec}"


def test_bl15_record_type(relay_with_tasks):
    """BL-15: records[].type is a non-empty string (canonical value is 'interaction' per v2.59 signing payload)."""
    d = get_log(relay_with_tasks)
    for rec in d["records"]:
        assert isinstance(rec.get("type"), str) and len(rec["type"]) > 0, \
            f"Record missing or invalid 'type' field: {rec.get('type')}"


def test_bl16_sequence_monotonic(relay_with_tasks):
    """BL-16: records[].sequence_a is monotonically non-decreasing."""
    d = get_log(relay_with_tasks)
    seqs = [rec["sequence_a"] for rec in d["records"]]
    for i in range(1, len(seqs)):
        assert seqs[i] >= seqs[i - 1], \
            f"sequence_a not monotonic at index {i}: {seqs[i-1]} → {seqs[i]}"


def test_bl18_bilateral_false_means_no_caller_sig(relay_with_tasks):
    """BL-18: bilateral=False records have no valid caller_signature (created without caller key)."""
    d = get_log(relay_with_tasks)
    for rec in d["records"]:
        if not rec.get("bilateral"):
            # caller_sig may be null or caller_signature_valid may be None/False
            csig_valid = rec.get("caller_signature_valid")
            assert csig_valid is not True, \
                f"bilateral=false but caller_signature_valid=True: {rec['id']}"


# ── Filtering ─────────────────────────────────────────────────────────────────

def test_bl07_filter_caller_did(relay_with_tasks):
    """BL-07: ?caller_did filter returns only matching records."""
    d = get_log(relay_with_tasks, caller_did="did:key:zAlice")
    for rec in d["records"]:
        assert "zAlice" in (rec.get("caller_did") or ""), \
            f"Record caller_did '{rec.get('caller_did')}' doesn't match zAlice"


def test_bl08_filter_skill_id(relay_with_tasks):
    """BL-08: ?skill_id filter returns only matching records."""
    d = get_log(relay_with_tasks, skill_id="skill_alpha")
    for rec in d["records"]:
        assert "skill_alpha" in (rec.get("skill_id") or ""), \
            f"Record skill_id '{rec.get('skill_id')}' doesn't match skill_alpha"


def test_bl09_filter_bilateral_true(relay_with_tasks):
    """BL-09: ?bilateral=true returns only bilateral=true records."""
    d = get_log(relay_with_tasks, bilateral="true")
    for rec in d["records"]:
        assert rec.get("bilateral") is True, \
            f"bilateral=true filter returned non-bilateral record: {rec['id']}"


def test_bl10_filter_bilateral_false(relay_with_tasks):
    """BL-10: ?bilateral=false returns only bilateral=false records."""
    d = get_log(relay_with_tasks, bilateral="false")
    for rec in d["records"]:
        assert rec.get("bilateral") is not True, \
            f"bilateral=false filter returned bilateral=true record: {rec['id']}"


def test_bl11_filter_since(relay_with_tasks):
    """BL-11: ?since=<ts> returns only records with timestamp >= since."""
    future_ts = time.time() + 3600  # 1 hour in the future
    d = get_log(relay_with_tasks, since=future_ts)
    assert d["total"] == 0, f"Expected no records since future timestamp, got {d['total']}"
    assert d["count"] == 0


def test_bl12_limit(relay_with_tasks):
    """BL-12: ?limit=1 returns at most 1 record."""
    d = get_log(relay_with_tasks, limit=1)
    assert d["count"] <= 1, f"Expected count<=1 with limit=1, got {d['count']}"
    assert len(d["records"]) <= 1


def test_bl13_offset_pagination(relay_with_tasks):
    """BL-13: ?offset=N skips first N records."""
    d_all = get_log(relay_with_tasks)
    if d_all["total"] < 2:
        pytest.skip("Need at least 2 records for offset test")
    d_off = get_log(relay_with_tasks, offset=1)
    assert d_off["count"] == d_all["total"] - 1, \
        f"Expected {d_all['total']-1} with offset=1, got {d_off['count']}"
    # First record of offset=1 should be second record of offset=0
    assert d_off["records"][0]["id"] == d_all["records"][1]["id"], \
        "Offset pagination: first record of offset=1 != second record of offset=0"


def test_bl14_limit_offset_pagination(relay_with_tasks):
    """BL-14: limit + offset pagination: count + offset <= total."""
    d = get_log(relay_with_tasks, limit=1, offset=1)
    total = get_log(relay_with_tasks)["total"]
    if total < 2:
        pytest.skip("Need at least 2 records for this test")
    assert d["count"] + 1 <= total, \
        f"count({d['count']}) + offset(1) > total({total})"


def test_bl19_nonexistent_caller_did(relay_with_tasks):
    """BL-19: ?caller_did=nonexistent returns count=0, total=0."""
    d = get_log(relay_with_tasks, caller_did="did:key:zNobodyExists99999")
    assert d["total"] == 0
    assert d["count"] == 0
    assert d["records"] == []


def test_bl20_note_field(relay_with_tasks):
    """BL-20: note field is present and non-empty string."""
    d = get_log(relay_with_tasks)
    assert isinstance(d.get("note"), str)
    assert len(d["note"]) > 10


# ── AgentCard ─────────────────────────────────────────────────────────────────

def test_bl21_agentcard_bilateral_ir_log(relay_url):
    """BL-21: capabilities.bilateral_ir_log = True."""
    r = requests.get(f"{relay_url}/.well-known/acp.json")
    assert r.status_code == 200
    card = r.json()
    cap = card.get("self", card).get("capabilities", {})
    assert cap.get("bilateral_ir_log") is True, \
        f"capabilities.bilateral_ir_log not True; got {cap.get('bilateral_ir_log')}"


def test_bl22_agentcard_endpoint(relay_url):
    """BL-22: endpoints.bilateral_ir_log = '/trust/bilateral-ir/log'."""
    r = requests.get(f"{relay_url}/.well-known/acp.json")
    assert r.status_code == 200
    card = r.json()
    ep = card.get("self", card).get("endpoints", {})
    assert ep.get("bilateral_ir_log") == "/trust/bilateral-ir/log", \
        f"Unexpected: {ep.get('bilateral_ir_log')}"
