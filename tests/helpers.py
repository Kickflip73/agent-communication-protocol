"""
ACP Test Suite — helpers.py
============================
Shared utilities for test modules.  Import from here rather than from
conftest to avoid conftest shadowing issues when pytest discovers tests
from a subdirectory that has its own conftest.py.
"""
import os

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
