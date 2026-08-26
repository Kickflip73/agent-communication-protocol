"""
tests/test_acp_json_media_type.py
===================================
ACP v3.14.0 — application/acp+json media type support (P2)
Tests AMT1–AMT8 (8 tests, minimum 6 required)

Validates:
  - AMT1: Default response Content-Type is application/json (backward compat)
  - AMT2: Request with Accept: application/acp+json → response Content-Type = application/acp+json
  - AMT3: POST /skills/query with Content-Type: application/acp+json is accepted (200)
  - AMT4: POST /message:send with Content-Type: application/acp+json is accepted
  - AMT5: capabilities.acp_json_media_type == True
  - AMT6: Regular POST with application/json still accepted (no regression)
  - AMT7: Accept: application/acp+json works on /status endpoint
  - AMT8: Accept header fallback — unknown Accept type → default application/json

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


def _get(hp, path, extra_headers=None):
    req = urllib.request.Request(f"http://127.0.0.1:{hp}{path}")
    if extra_headers:
        for k, v in extra_headers.items():
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


def _post(hp, path, payload, content_type="application/json", extra_headers=None):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{hp}{path}",
        data=data,
        headers={"Content-Type": content_type},
        method="POST",
    )
    if extra_headers:
        for k, v in extra_headers.items():
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


# ── Tests ────────────────────────────────────────────────────────────────────


class TestAMT1DefaultContentType:

    def test_amt1_default_content_type_is_application_json(self):
        """AMT1: Default response Content-Type is application/json (backward compat)"""
        proc, hp = _start_relay(_free_port())
        try:
            sc, body, headers = _get(hp, "/status")
            assert sc == 200
            ct = headers.get("Content-Type", "")
            assert "application/json" in ct, (
                f"Default Content-Type should be application/json, got: {ct}"
            )
            # Must NOT be acp+json when no Accept header
            assert "acp+json" not in ct, (
                f"Content-Type should not be acp+json without Accept header: {ct}"
            )
        finally:
            _stop(proc)


class TestAMT2AcceptAcpJson:

    def test_amt2_accept_acp_json_header_triggers_acp_json_response(self):
        """AMT2: Request with Accept: application/acp+json → response Content-Type = application/acp+json"""
        proc, hp = _start_relay(_free_port())
        try:
            sc, body, headers = _get(hp, "/status", extra_headers={"Accept": "application/acp+json"})
            assert sc == 200
            ct = headers.get("Content-Type", "")
            assert "application/acp+json" in ct, (
                f"Expected application/acp+json in Content-Type, got: {ct}"
            )
            assert "charset=utf-8" in ct, f"Expected charset=utf-8 in Content-Type, got: {ct}"
        finally:
            _stop(proc)


class TestAMT3PostWithAcpJsonContentType:

    def test_amt3_post_skills_query_with_acp_json_content_type(self):
        """AMT3: POST /skills/query with Content-Type: application/acp+json is accepted (200)"""
        proc, hp = _start_relay(_free_port())
        try:
            sc, body, headers = _post(
                hp, "/skills/query", {},
                content_type="application/acp+json",
            )
            assert sc == 200, (
                f"Expected 200 for POST /skills/query with application/acp+json, got {sc}: {body}"
            )
            # Response should be valid JSON (skills list or similar)
            assert isinstance(body, dict), f"Expected dict response, got: {type(body)}"
        finally:
            _stop(proc)


class TestAMT4PostMessageWithAcpJsonContentType:

    def test_amt4_post_message_send_with_acp_json_content_type(self):
        """AMT4: POST /message:send with Content-Type: application/acp+json is accepted (not 415)"""
        proc, hp = _start_relay(_free_port())
        try:
            sc, body, _ = _post(
                hp, "/message:send",
                {"role": "user", "parts": [{"type": "text", "text": "hello from acp+json"}]},
                content_type="application/acp+json",
            )
            # Critical assertion: Content-Type application/acp+json must NOT cause 415 rejection
            assert sc != 415, f"Got 415 Unsupported Media Type — application/acp+json not accepted"
            # Accept 200, 201, or 503 (ERR_NOT_CONNECTED; relay not peered in test mode — that's OK)
            # The key is that the media type was accepted by the relay (not 415)
            assert sc in (200, 201, 503), f"Expected 200/201/503, got {sc}: {body}"
            if sc == 503:
                # Confirm it's a relay not-connected error, not a media type error
                assert body.get("error_code") == "ERR_NOT_CONNECTED", (
                    f"503 should be ERR_NOT_CONNECTED, got: {body.get('error_code')}"
                )
        finally:
            _stop(proc)


class TestAMT5CapabilityFlag:

    def test_amt5_capabilities_acp_json_media_type_true(self):
        """AMT5: capabilities.acp_json_media_type == True in AgentCard"""
        proc, hp = _start_relay(_free_port())
        try:
            card = _card(hp)
            caps = card.get("capabilities", {})
            assert caps.get("acp_json_media_type") is True, (
                f"Expected capabilities.acp_json_media_type=True, got: {caps.get('acp_json_media_type')}"
            )
        finally:
            _stop(proc)


class TestAMT6ApplicationJsonRegression:

    def test_amt6_application_json_still_accepted(self):
        """AMT6: Regular POST with Content-Type: application/json still accepted (no regression)"""
        proc, hp = _start_relay(_free_port())
        try:
            sc, body, _ = _post(hp, "/skills/query", {}, content_type="application/json")
            assert sc == 200, f"Expected 200 for application/json, got {sc}: {body}"
        finally:
            _stop(proc)


class TestAMT7AcceptOnStatusEndpoint:

    def test_amt7_accept_acp_json_on_skills_endpoint(self):
        """AMT7: Accept: application/acp+json works on GET /skills endpoint"""
        proc, hp = _start_relay(_free_port())
        try:
            sc, body, headers = _get(
                hp, "/skills",
                extra_headers={"Accept": "application/acp+json"},
            )
            assert sc == 200
            ct = headers.get("Content-Type", "")
            assert "application/acp+json" in ct, (
                f"Expected application/acp+json Content-Type for /skills, got: {ct}"
            )
        finally:
            _stop(proc)


class TestAMT8AcceptFallback:

    def test_amt8_unknown_accept_type_falls_back_to_application_json(self):
        """AMT8: Accept: application/xml → response is still application/json (fallback)"""
        proc, hp = _start_relay(_free_port())
        try:
            sc, body, headers = _get(
                hp, "/status",
                extra_headers={"Accept": "application/xml"},
            )
            assert sc == 200
            ct = headers.get("Content-Type", "")
            # Should default to application/json, not acp+json
            assert "application/json" in ct, (
                f"Expected fallback to application/json, got: {ct}"
            )
        finally:
            _stop(proc)
