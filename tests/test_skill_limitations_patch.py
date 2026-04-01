"""
test_skill_limitations_patch.py — v2.29: PATCH /skills/<id>/limitations

Runtime per-skill limitations update (ROADMAP v2.31 P1 feature).

SU1  — capabilities.skill_limitations_patch declared True
SU2  — PATCH replaces limitations[] for a known skill
SU3  — GET /skills/<id>/status returns unavailable after PATCH runtime limitation
SU4  — permanent limitation does NOT make skill unavailable in status probe
SU5  — clear limitations with empty [] — status reverts to available
SU6  — limitations_merge=true merges new entries into existing overrides
SU7  — PATCH /skills/<nonexistent>/limitations → 404
SU8  — GET /skills reflects runtime override in skill list
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


# ── helpers ───────────────────────────────────────────────────────────────────

def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_relay(skills_json, name="SU-Agent"):
    ws_port   = _free_port()
    http_port = ws_port + 100
    env = {k: v for k, v in os.environ.items()
           if k.upper() not in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                                 "http_proxy", "https_proxy", "all_proxy")}
    proc = subprocess.Popen(
        [sys.executable, RELAY_PATH, "--port", str(ws_port), "--name", name,
         "--skills", skills_json],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
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
    with urllib.request.urlopen(f"{base}{path}", timeout=5) as r:
        return json.loads(r.read())


def _patch(base, path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{base}{path}", data=data, method="PATCH",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


def _stop(proc):
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


# ── SU1: capability declared ──────────────────────────────────────────────────

def test_SU1_capability_declared():
    """capabilities.skill_limitations_patch must be True."""
    skills = json.dumps([{"id": "translate", "name": "Translate"}])
    proc, base = _start_relay(skills)
    try:
        card = _get(base, "/.well-known/acp.json")
        # AgentCard structure: {self: {capabilities: {...}}}
        caps = card.get("self", card).get("capabilities", {})
        assert caps.get("skill_limitations_patch") is True, (
            f"capabilities.skill_limitations_patch should be True, got caps={list(caps.keys())[-5:]}"
        )
    finally:
        _stop(proc)


# ── SU2: PATCH replaces limitations ──────────────────────────────────────────

def test_SU2_patch_replaces_limitations():
    """PATCH /skills/<id>/limitations replaces limitations[] for that skill."""
    skills = json.dumps([{"id": "summarize", "name": "Summarize", "limitations": []}])
    proc, base = _start_relay(skills)
    try:
        resp = _patch(base, "/skills/summarize/limitations", {
            "limitations": [
                {"kind": "capability", "code": "no_long_docs",
                 "message": "Cannot process > 50k tokens", "permanent": False}
            ]
        })
        assert resp.get("ok") is True
        assert resp.get("skill_id") == "summarize"
        lims = resp.get("limitations", [])
        assert len(lims) == 1
        assert lims[0]["code"] == "no_long_docs"
        assert lims[0]["permanent"] is False
    finally:
        _stop(proc)


# ── SU3: status reflects patched limitation ───────────────────────────────────

def test_SU3_status_reflects_patch():
    """GET /skills/<id>/status returns unavailable after PATCH with runtime limitation."""
    skills = json.dumps([{"id": "ocr", "name": "OCR", "limitations": []}])
    proc, base = _start_relay(skills)
    try:
        # Initially available
        status = _get(base, "/skills/ocr/status")
        assert status.get("available") is True

        # PATCH with runtime capability limitation (permanent=False)
        _patch(base, "/skills/ocr/limitations", {
            "limitations": [
                {"kind": "capability", "code": "gpu_unavailable",
                 "message": "GPU not available", "permanent": False}
            ]
        })

        # Now should be unavailable
        status2 = _get(base, "/skills/ocr/status")
        assert status2.get("available") is False
        # reason may contain either the code or the message
        reason = status2.get("reason") or ""
        assert "gpu_unavailable" in reason or "GPU not available" in reason
    finally:
        _stop(proc)


# ── SU4: permanent limitation still available ─────────────────────────────────

def test_SU4_permanent_limitation_still_available():
    """A permanent limitation does not mark skill unavailable in status probe."""
    skills = json.dumps([{"id": "translate", "name": "Translate"}])
    proc, base = _start_relay(skills)
    try:
        _patch(base, "/skills/translate/limitations", {
            "limitations": [
                {"kind": "modality", "code": "no_audio",
                 "message": "Audio not supported", "permanent": True}
            ]
        })
        status = _get(base, "/skills/translate/status")
        assert status.get("available") is True, (
            "permanent limitations should not mark skill unavailable"
        )
        # Limitation should appear in response
        lims = status.get("limitations", [])
        assert any(lim.get("code") == "no_audio" for lim in lims)
    finally:
        _stop(proc)


# ── SU5: clear limitations with empty array ───────────────────────────────────

def test_SU5_clear_with_empty_array():
    """PATCH with [] clears runtime override; status reverts to available."""
    skills = json.dumps([{"id": "search", "name": "Search"}])
    proc, base = _start_relay(skills)
    try:
        # Add runtime limitation → unavailable
        _patch(base, "/skills/search/limitations", {
            "limitations": [
                {"kind": "access", "code": "api_rate_limited",
                 "message": "Rate limited", "permanent": False}
            ]
        })
        status = _get(base, "/skills/search/status")
        assert status.get("available") is False

        # Clear it
        resp = _patch(base, "/skills/search/limitations", {"limitations": []})
        assert resp.get("ok") is True
        assert resp.get("limitations") == []

        # Should be available again
        status2 = _get(base, "/skills/search/status")
        assert status2.get("available") is True
    finally:
        _stop(proc)


# ── SU6: merge mode ───────────────────────────────────────────────────────────

def test_SU6_merge_mode():
    """limitations_merge=true merges new entries into existing overrides."""
    skills = json.dumps([{"id": "classify", "name": "Classify"}])
    proc, base = _start_relay(skills)
    try:
        # First PATCH: one limitation
        _patch(base, "/skills/classify/limitations", {
            "limitations": [
                {"kind": "capability", "code": "no_images",
                 "message": "No image input", "permanent": True}
            ]
        })
        # Second PATCH with merge=true
        resp = _patch(base, "/skills/classify/limitations", {
            "limitations": [
                {"kind": "scale", "code": "max_batch_10",
                 "message": "Max 10 per batch", "permanent": True}
            ],
            "limitations_merge": True
        })
        codes = [lim.get("code") for lim in resp.get("limitations", [])]
        assert "no_images" in codes, "Original limitation should survive merge"
        assert "max_batch_10" in codes, "New limitation should be added via merge"
    finally:
        _stop(proc)


# ── SU7: PATCH unknown skill → 404 ───────────────────────────────────────────

def test_SU7_unknown_skill_404():
    """PATCH /skills/<nonexistent>/limitations returns 404."""
    skills = json.dumps([{"id": "translate", "name": "Translate"}])
    proc, base = _start_relay(skills)
    try:
        try:
            _patch(base, "/skills/nonexistent_xyz/limitations", {"limitations": []})
            assert False, "Expected 404"
        except urllib.error.HTTPError as e:
            assert e.code == 404
    finally:
        _stop(proc)


# ── SU8: GET /skills returns merged limitations ───────────────────────────────

def test_SU8_get_skills_returns_overrides():
    """GET /skills reflects runtime override in the skills list."""
    skills = json.dumps([{"id": "embed", "name": "Embed", "limitations": []}])
    proc, base = _start_relay(skills)
    try:
        # Before: no limitations
        resp = _get(base, "/skills")
        embed = next((s for s in resp["skills"] if s["id"] == "embed"), None)
        assert embed is not None
        assert embed.get("limitations", []) == []

        # Patch
        _patch(base, "/skills/embed/limitations", {
            "limitations": [
                {"kind": "capability", "code": "no_multimodal",
                 "message": "Text only", "permanent": False}
            ]
        })

        # After: reflected in GET /skills
        resp2 = _get(base, "/skills")
        embed2 = next((s for s in resp2["skills"] if s["id"] == "embed"), None)
        assert embed2 is not None
        lims = embed2.get("limitations", [])
        assert any(lim.get("code") == "no_multimodal" for lim in lims), (
            "GET /skills should reflect runtime override"
        )
    finally:
        _stop(proc)
