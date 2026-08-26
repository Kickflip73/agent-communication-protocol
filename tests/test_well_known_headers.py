#!/usr/bin/env python3
"""
test_well_known_headers.py — v2.47: RFC 8615 well-known endpoint headers

WH1: GET /.well-known/acp.json returns Content-Type: application/json; charset=utf-8
WH2: GET /.well-known/acp.json returns Cache-Control: no-cache, no-store
WH3: GET /.well-known/acp.json returns Access-Control-Allow-Origin: *
WH4: GET /.well-known/acp.json returns Vary: Accept
WH5: GET /.well-known/acp.json returns X-Content-Type-Options: nosniff
WH6: GET /.well-known/acp.json returns Access-Control-Allow-Methods containing GET
WH7: GET /.well-known/jwks.json returns same RFC 8615 headers
WH8: GET /status does NOT return Cache-Control (only .well-known endpoints get it)
WH9: capabilities.well_known_rfc8615=True in AgentCard
WH10: GET /.well-known/acp.json alias /card also returns RFC 8615 headers
"""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RELAY_PY = os.path.join(BASE_DIR, "relay", "acp_relay.py")


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def relay():
    # acp_relay.py: --port sets WS port; HTTP API = port + 100
    ws_port = _free_port()
    http_port = ws_port + 100
    proc = subprocess.Popen(
        [sys.executable, RELAY_PY,
         "--port", str(ws_port),
         "--name", "WH-Test-Agent"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait for startup (up to 15s)
    base_url = f"http://127.0.0.1:{http_port}"
    for _ in range(50):
        try:
            urllib.request.urlopen(f"{base_url}/.well-known/acp.json", timeout=2)
            break
        except Exception:
            time.sleep(0.3)
    else:
        proc.terminate()
        pytest.fail("Relay did not start within 15s")
    yield base_url
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def _head_response(url):
    """Return (status, headers_dict) for a GET request."""
    req = urllib.request.Request(url)
    try:
        resp = urllib.request.urlopen(req, timeout=5)
        return resp.status, dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers)


def test_wh1_content_type(relay):
    """WH1: Content-Type is application/json; charset=utf-8"""
    _, headers = _head_response(f"{relay}/.well-known/acp.json")
    ct = headers.get("Content-Type", "")
    assert "application/json" in ct
    assert "charset=utf-8" in ct.lower()


def test_wh2_cache_control(relay):
    """WH2: Cache-Control: no-cache, no-store"""
    _, headers = _head_response(f"{relay}/.well-known/acp.json")
    cc = headers.get("Cache-Control", "")
    assert "no-cache" in cc
    assert "no-store" in cc


def test_wh3_cors_origin(relay):
    """WH3: Access-Control-Allow-Origin: *"""
    _, headers = _head_response(f"{relay}/.well-known/acp.json")
    assert headers.get("Access-Control-Allow-Origin") == "*"


def test_wh4_vary(relay):
    """WH4: Vary: Accept"""
    _, headers = _head_response(f"{relay}/.well-known/acp.json")
    vary = headers.get("Vary", "")
    assert "Accept" in vary


def test_wh5_x_content_type_options(relay):
    """WH5: X-Content-Type-Options: nosniff"""
    _, headers = _head_response(f"{relay}/.well-known/acp.json")
    assert headers.get("X-Content-Type-Options", "").lower() == "nosniff"


def test_wh6_cors_methods(relay):
    """WH6: Access-Control-Allow-Methods contains GET"""
    _, headers = _head_response(f"{relay}/.well-known/acp.json")
    methods = headers.get("Access-Control-Allow-Methods", "")
    assert "GET" in methods


def test_wh7_jwks_rfc8615_headers(relay):
    """WH7: /.well-known/jwks.json also returns RFC 8615 headers"""
    _, headers = _head_response(f"{relay}/.well-known/jwks.json")
    assert "no-cache" in headers.get("Cache-Control", "")
    assert headers.get("X-Content-Type-Options", "").lower() == "nosniff"
    assert "Accept" in headers.get("Vary", "")


def test_wh8_status_no_cache_control(relay):
    """WH8: /status does NOT return Cache-Control (only .well-known gets it)"""
    _, headers = _head_response(f"{relay}/status")
    assert "Cache-Control" not in headers


def test_wh9_capability_flag(relay):
    """WH9: capabilities.well_known_rfc8615=True in AgentCard"""
    resp = urllib.request.urlopen(f"{relay}/.well-known/acp.json", timeout=5)
    card_resp = json.loads(resp.read())
    caps = card_resp.get("self", {}).get("capabilities", {})
    assert caps.get("well_known_rfc8615") is True


def test_wh10_card_alias_rfc8615_headers(relay):
    """WH10: /card alias also returns RFC 8615 headers"""
    _, headers = _head_response(f"{relay}/card")
    assert "no-cache" in headers.get("Cache-Control", "")
    assert headers.get("X-Content-Type-Options", "").lower() == "nosniff"
