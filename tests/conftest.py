"""
ACP Test Suite — conftest.py
=============================
Global pytest configuration.

Key concerns addressed here:
1. HTTP proxy bypass: the sandbox has http_proxy=127.0.0.1:8118 set globally.
   This causes all requests.get/post calls to localhost relay instances to fail.
   We remove proxy env vars for the entire session AND provide a clean env dict
   for relay subprocesses.

2. Relay subprocess env: relay subprocesses inherit proxy env vars which breaks
   their public IP detection and WebSocket connections.  Use `clean_subprocess_env()`
   when launching relay processes.
"""
import os
import subprocess
import pytest

_PROXY_VARS = (
    "http_proxy", "HTTP_PROXY",
    "https_proxy", "HTTPS_PROXY",
    "all_proxy", "ALL_PROXY",
    "ftp_proxy", "FTP_PROXY",
    "no_proxy", "NO_PROXY",
)


def clean_subprocess_env() -> dict:
    """Return a copy of os.environ with all proxy variables removed.
    Use as `env=` kwarg when spawning relay subprocesses."""
    env = os.environ.copy()
    for var in _PROXY_VARS:
        env.pop(var, None)
    return env


def pytest_addoption(parser):
    parser.addoption(
        "--with-p2p", action="store_true", default=False,
        help="Include tests that require P2P WebSocket connectivity (needs public IP)",
    )


def pytest_collection_modifyitems(config, items):
    """Skip P2P-dependent tests unless --with-p2p flag is passed."""
    if config.getoption("--with-p2p", default=False):
        return  # run everything
    skip_p2p = pytest.mark.skip(reason="Requires P2P public IP (pass --with-p2p to enable)")
    for item in items:
        if "p2p" in item.keywords:
            item.add_marker(skip_p2p)


@pytest.fixture(autouse=True, scope="session")
def bypass_http_proxy():
    """Remove proxy env vars from the current process for the entire test session.

    This ensures that requests.get/post calls issued from test code go directly
    to localhost without being proxied through 127.0.0.1:8118.
    """
    _removed = []
    for var in _PROXY_VARS:
        if var in os.environ:
            _removed.append((var, os.environ.pop(var)))
    yield
    # Restore (good citizenship — other tests after the session may need them)
    for var, val in _removed:
        os.environ[var] = val
