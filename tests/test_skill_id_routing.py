"""
Skill ID Routing — v3.19 client-directed skill selection

Tests skill_id field in POST /message/send (Direct Message) and POST /tasks/create.
Aligned with A2A #1989 (Client-directed skill selection) and #2008 (Generalized capability descriptors).

Test matrix:
  test_skr_01  skill_id in /message/send → response includes skill_id
  test_skr_02  no skill_id in /message/send → normal behavior (backward compat)
  test_skr_03  skill_id not declared in AgentCard → 400 ERR_SKILL_NOT_FOUND
  test_skr_04  skill_id in /tasks/create → already supported (regression)
  test_skr_05  AgentCard declares capabilities.skill_id_routing=true
  test_skr_06  skill_id with parts[] (structured message)
  test_skr_07  skill_id with text field (legacy text mode)
  test_skr_08  skill_id with context_id propagation
"""
import json
import os
import socket
import subprocess
import sys
import time

import pytest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RELAY_PY = os.path.join(BASE_DIR, "relay", "acp_relay.py")


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _free_port_pair():
    """Return a free (ws_port, http_port) pair."""
    for _ in range(100):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            ws = s.getsockname()[1]
        try:
            with socket.socket() as s2:
                s2.bind(("127.0.0.1", ws + 100))
                return ws, ws + 100
        except OSError:
            continue
    raise RuntimeError("Cannot find free port pair")


def _clean_env():
    env = {k: v for k, v in os.environ.items()
           if k not in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")}
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _http(url, method="GET", body=None, timeout=5):
    import urllib.request, urllib.error
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read()), e.code
    except Exception as e:
        return None, -1


def _start_relay(ws_port, http_port, name="SKRRelay", skills=None):
    """Start a relay subprocess."""
    cmd = [
        sys.executable, "-u", "relay/acp_relay.py",
        "--port", str(ws_port),
        "--http-port", str(http_port),
        "--http-host", "127.0.0.1",
        "--name", name,
        "--local-only",
    ]
    if skills:
        cmd += ["--skills", skills]
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        env=_clean_env(), cwd=BASE_DIR,
    )
    deadline = time.time() + 15
    while time.time() < deadline:
        if proc.poll() is not None:
            out, err = proc.communicate()
            raise RuntimeError(f"Relay exited early. stdout: {out}\nstderr: {err}")
        try:
            _, code = _http(f"http://127.0.0.1:{http_port}/status")
            if code == 200:
                return proc
        except Exception:
            pass
        time.sleep(0.3)
    proc.terminate()
    raise RuntimeError(f"Relay did not start within 15s")


def _stop_relay(proc):
    if proc and proc.poll() is None:
        proc.terminate()
        proc.wait(timeout=5)


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestSkillIdRouting:

    # ── test_skr_01 ──────────────────────────────────────────────────────────
    def test_skr_01_skill_id_in_message_send(self):
        """SKR-01: skill_id in POST /message/send → response includes skill_id."""
        ws, http = _free_port_pair()
        proc = _start_relay(ws, http, skills="file_read")
        try:
            body = {
                "message_id": "msg_skr_01",
                "role": "user",
                "skill_id": "file_read",
                "parts": [{"type": "text", "text": "Read the config file"}],
            }
            resp, code = _http(f"http://127.0.0.1:{http}/message/send", "POST", body)
            assert code == 200, f"expected 200, got {code}: {resp}"
            assert resp["ok"] is True
            assert resp.get("skill_id") == "file_read"
        finally:
            _stop_relay(proc)

    # ── test_skr_02 ──────────────────────────────────────────────────────────
    def test_skr_02_no_skill_id_backward_compat(self):
        """SKR-02: No skill_id in POST /message/send → normal behavior."""
        ws, http = _free_port_pair()
        proc = _start_relay(ws, http)
        try:
            body = {
                "role": "user",
                "parts": [{"type": "text", "text": "Hello world"}],
            }
            resp, code = _http(f"http://127.0.0.1:{http}/message/send", "POST", body)
            assert code == 200, f"expected 200, got {code}: {resp}"
            assert resp["ok"] is True
            assert "skill_id" not in resp  # absent when not specified
            assert resp.get("parts") == [{"type": "text", "text": "Hello world"}]
        finally:
            _stop_relay(proc)

    # ── test_skr_03 ──────────────────────────────────────────────────────────
    def test_skr_03_skill_not_found(self):
        """SKR-03: skill_id not declared in AgentCard → 400 ERR_SKILL_NOT_FOUND."""
        ws, http = _free_port_pair()
        proc = _start_relay(ws, http, skills="file_read")
        try:
            body = {
                "message_id": "msg_skr_03",
                "role": "user",
                "skill_id": "nonexistent_skill",
                "parts": [{"type": "text", "text": "This should fail"}],
            }
            resp, code = _http(f"http://127.0.0.1:{http}/message/send", "POST", body)
            assert code == 400, f"expected 400, got {code}: {resp}"
            assert resp.get("ok") is False
            assert resp.get("error_code") == "ERR_SKILL_NOT_FOUND"
            assert "nonexistent_skill" in resp.get("error", "")
            assert resp.get("failed_message_id") == "msg_skr_03"
        finally:
            _stop_relay(proc)

    # ── test_skr_04 ──────────────────────────────────────────────────────────
    def test_skr_04_tasks_create_skill_id_regression(self):
        """SKR-04: skill_id in POST /tasks/create → already supported (regression)."""
        ws, http = _free_port_pair()
        proc = _start_relay(ws, http, skills="file_read")
        try:
            body = {
                "role": "user",
                "skill_id": "file_read",
                "parts": [{"type": "text", "text": "Read the config file"}],
            }
            resp, code = _http(f"http://127.0.0.1:{http}/tasks/create", "POST", body)
            # tasks/create accepts skill_id and creates task
            assert code == 201, f"expected 201, got {code}: {resp}"
            assert resp["ok"] is True
            assert resp.get("task") is not None
        finally:
            _stop_relay(proc)

    # ── test_skr_05 ──────────────────────────────────────────────────────────
    def test_skr_05_capability_declared(self):
        """SKR-05: AgentCard declares capabilities.skill_id_routing=true."""
        ws, http = _free_port_pair()
        proc = _start_relay(ws, http, skills="file_read")
        try:
            card, code = _http(f"http://127.0.0.1:{http}/.well-known/acp.json")
            assert code == 200
            assert "self" in card
            caps = card["self"].get("capabilities", {})
            assert caps.get("skill_id_routing") is True
        finally:
            _stop_relay(proc)

    # ── test_skr_06 ──────────────────────────────────────────────────────────
    def test_skr_06_skill_id_with_parts(self):
        """SKR-06: skill_id with structured parts[] (structured message)."""
        ws, http = _free_port_pair()
        proc = _start_relay(ws, http, skills="file_read")
        try:
            body = {
                "message_id": "msg_skr_06",
                "role": "user",
                "skill_id": "file_read",
                "parts": [
                    {"type": "text", "text": "Read this file"},
                    {"type": "file", "url": "https://example.com/config.json", "filename": "config.json"},
                ],
            }
            resp, code = _http(f"http://127.0.0.1:{http}/message/send", "POST", body)
            assert code == 200
            assert resp["ok"] is True
            assert resp.get("skill_id") == "file_read"
            assert len(resp.get("parts", [])) == 2
        finally:
            _stop_relay(proc)

    # ── test_skr_07 ──────────────────────────────────────────────────────────
    def test_skr_07_skill_id_with_text(self):
        """SKR-07: skill_id with text field (legacy text mode)."""
        ws, http = _free_port_pair()
        proc = _start_relay(ws, http, skills="file_read")
        try:
            body = {
                "message_id": "msg_skr_07",
                "role": "user",
                "skill_id": "file_read",
                "text": "Read the config file",
            }
            resp, code = _http(f"http://127.0.0.1:{http}/message/send", "POST", body)
            assert code == 200
            assert resp["ok"] is True
            assert resp.get("skill_id") == "file_read"
            assert resp.get("parts") is not None
        finally:
            _stop_relay(proc)

    # ── test_skr_08 ──────────────────────────────────────────────────────────
    def test_skr_08_skill_id_with_context_id(self):
        """SKR-08: skill_id + context_id propagation."""
        ws, http = _free_port_pair()
        proc = _start_relay(ws, http, skills="file_read")
        try:
            body = {
                "message_id": "msg_skr_08",
                "role": "user",
                "skill_id": "file_read",
                "context_id": "ctx_skr_08",
                "parts": [{"type": "text", "text": "Read the config file"}],
            }
            resp, code = _http(f"http://127.0.0.1:{http}/message/send", "POST", body)
            assert code == 200
            assert resp["ok"] is True
            assert resp.get("skill_id") == "file_read"
            assert resp.get("context_id") == "ctx_skr_08"
        finally:
            _stop_relay(proc)
