"""
Tests for supported_transports capability field (v2.2)
ST1: AgentCard contains supported_transports field
ST2: supported_transports is a list
ST3: supported_transports contains at least 'http' and 'ws'
ST4: h2c only present when HTTP/2 enabled (default: not enabled)
ST5: supported_transports exposed under capabilities (not top-level)
"""
import os
import signal
import socket
import subprocess
import sys
import time

import pytest
import requests

RELAY_PATH = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_ready(url: str, timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{url}/status", timeout=1)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.25)
    return False


@pytest.fixture(scope="module", autouse=True)
def relay_instance(request):
    env = os.environ.copy()
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        env.pop(k, None)

    ws_port = _free_port()
    http_port = ws_port + 100

    p = subprocess.Popen(
        [sys.executable, RELAY_PATH, "--port", str(ws_port), "--name", "TestAgent-ST"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
        cwd=os.path.join(os.path.dirname(__file__), ".."),
    )

    target_url = f"http://127.0.0.1:{http_port}"
    if not _wait_ready(target_url):
        p.terminate()
        p.wait(timeout=5)
        pytest.fail(f"relay did not start on port {http_port}")

    def _cleanup():
        p.send_signal(signal.SIGTERM)
        try:
            p.wait(timeout=8)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
    request.addfinalizer(_cleanup)

    # store for tests to use
    request.config._st_target_url = target_url


def _get_card(request):
    url = request.config._st_target_url
    r = requests.get(f"{url}/.well-known/acp.json", timeout=5)
    body = r.json()
    return body.get("self", body)


def test_st1_field_present(request):
    card = _get_card(request)
    caps = card.get("capabilities", {})
    assert "supported_transports" in caps, (
        f"supported_transports missing from capabilities; keys={list(caps.keys())}"
    )


def test_st2_is_list(request):
    card = _get_card(request)
    val = card["capabilities"]["supported_transports"]
    assert isinstance(val, list), f"expected list, got {type(val)}: {val!r}"


def test_st3_contains_http_and_ws(request):
    card = _get_card(request)
    transports = card["capabilities"]["supported_transports"]
    assert "http" in transports, f"'http' not in {transports}"
    assert "ws" in transports,   f"'ws' not in {transports}"


def test_st4_h2c_not_in_default(request):
    """h2c should NOT appear unless --http2 flag is passed"""
    card = _get_card(request)
    transports = card["capabilities"]["supported_transports"]
    assert "h2c" not in transports, (
        f"h2c should not appear in default (non-HTTP/2) mode: {transports}"
    )


def test_st5_under_capabilities_not_root(request):
    """supported_transports must be nested under capabilities, not at card root"""
    card = _get_card(request)
    assert "supported_transports" not in card, (
        "supported_transports should not be at card root"
    )
    assert "supported_transports" in card.get("capabilities", {}), (
        "supported_transports should be under capabilities"
    )
