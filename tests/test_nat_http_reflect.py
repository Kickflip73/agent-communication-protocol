#!/usr/bin/env python3
"""
tests/test_nat_http_reflect.py

Unit tests for v1.4 DCUtR HTTP reflection fallback.

Tests that when STUN fails, DCUtRPuncher.attempt() falls back to
_relay_get_public_ip() (HTTP reflection) to discover the public IP.

These tests mock the network calls so they work in sandbox without real STUN/relay.
"""

import asyncio
import json
import sys
import os
import unittest
from unittest.mock import patch, AsyncMock, MagicMock

# Add relay directory to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "relay"))

import pytest


@pytest.fixture(autouse=True, scope="module")
def relay_imports():
    """Import relay module globals needed for tests."""
    import importlib
    import acp_relay
    # Reset relevant _status fields for test isolation
    acp_relay._status["relay_base_url"] = None
    yield acp_relay
    acp_relay._status["relay_base_url"] = None


class TestHTTPReflectionFallback:
    """Tests for DCUtR STUN-fail → HTTP-reflection fallback path."""

    def test_relay_get_public_ip_success(self):
        """_relay_get_public_ip returns IP string on success."""
        import acp_relay
        import urllib.request

        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"ip": "1.2.3.4"}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch.object(urllib.request, "urlopen", return_value=mock_resp):
            result = acp_relay._relay_get_public_ip("https://relay.example.com", timeout=1.0)

        assert result == "1.2.3.4", f"Expected '1.2.3.4', got {result!r}"

    def test_relay_get_public_ip_timeout(self):
        """_relay_get_public_ip returns None on network timeout."""
        import acp_relay
        import urllib.error

        with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            result = acp_relay._relay_get_public_ip("https://relay.example.com", timeout=0.1)

        assert result is None

    def test_relay_get_public_ip_invalid_json(self):
        """_relay_get_public_ip returns None when response is not valid JSON."""
        import acp_relay
        import urllib.request

        mock_resp = MagicMock()
        mock_resp.read.return_value = b"not json"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch.object(urllib.request, "urlopen", return_value=mock_resp):
            result = acp_relay._relay_get_public_ip("https://relay.example.com", timeout=1.0)

        assert result is None

    def test_relay_status_stores_relay_base_url(self):
        """After setting relay_base_url in _status, DCUtRPuncher can read it."""
        import acp_relay

        acp_relay._status["relay_base_url"] = "https://acp-relay.workers.dev"
        assert acp_relay._status.get("relay_base_url") == "https://acp-relay.workers.dev"
        # Cleanup
        acp_relay._status["relay_base_url"] = None

    def test_dcutr_http_reflect_used_when_stun_fails(self):
        asyncio.run(self._async_test_dcutr_http_reflect_used_when_stun_fails())

    async def _async_test_dcutr_http_reflect_used_when_stun_fails(self):
        """When STUN fails and relay_base_url is set, HTTP reflection is attempted."""
        import acp_relay

        # Set up relay_base_url in status
        acp_relay._status["relay_base_url"] = "https://acp-relay.workers.dev"

        puncher = acp_relay.DCUtRPuncher()

        # Mock: STUN fails
        async def mock_stun_fail(*args, **kwargs):
            return None

        # Mock: HTTP reflection succeeds
        def mock_http_reflect(relay_base, timeout=3.0):
            return "203.0.113.5"  # TEST-NET-3 (RFC 5737, documentation use)

        # Mock: relay_ws that echoes back a failure (so punch doesn't succeed,
        # but we can verify reflection was called)
        http_reflect_calls = []

        def tracking_http_reflect(relay_base, timeout=3.0):
            http_reflect_calls.append(relay_base)
            return "203.0.113.5"

        # Mock the signal exchange to raise early (we only test address discovery phase)
        async def mock_ws_send(msg):
            raise ConnectionError("mock peer not ready")

        mock_ws = AsyncMock()
        mock_ws.send = mock_ws_send

        with patch.object(acp_relay.STUNClient, "get_public_address",
                          new=mock_stun_fail), \
             patch.object(acp_relay, "_relay_get_public_ip",
                          side_effect=tracking_http_reflect), \
             patch.object(acp_relay, "_broadcast_sse_event", return_value=None):
            result = await puncher.attempt(mock_ws, local_port=9001)

        # STUN failed, so HTTP reflection should have been called
        assert len(http_reflect_calls) >= 1, (
            "Expected _relay_get_public_ip to be called when STUN fails, "
            f"but it was called {len(http_reflect_calls)} times"
        )
        assert http_reflect_calls[0] == "https://acp-relay.workers.dev"

        # Cleanup
        acp_relay._status["relay_base_url"] = None

    def test_dcutr_no_http_reflect_when_no_relay_base(self):
        asyncio.run(self._async_test_dcutr_no_http_reflect_when_no_relay_base())

    async def _async_test_dcutr_no_http_reflect_when_no_relay_base(self):
        """When relay_base_url is not set, HTTP reflection is skipped gracefully."""
        import acp_relay

        acp_relay._status["relay_base_url"] = None

        puncher = acp_relay.DCUtRPuncher()

        async def mock_stun_fail(*args, **kwargs):
            return None

        http_reflect_calls = []

        def tracking_http_reflect(relay_base, timeout=3.0):
            http_reflect_calls.append(relay_base)
            return None

        async def mock_ws_send(msg):
            raise ConnectionError("mock peer not ready")

        mock_ws = AsyncMock()
        mock_ws.send = mock_ws_send

        with patch.object(acp_relay.STUNClient, "get_public_address",
                          new=mock_stun_fail), \
             patch.object(acp_relay, "_relay_get_public_ip",
                          side_effect=tracking_http_reflect), \
             patch.object(acp_relay, "_broadcast_sse_event", return_value=None):
            result = await puncher.attempt(mock_ws, local_port=9001)

        # HTTP reflection should NOT be called when relay_base_url is unset
        assert len(http_reflect_calls) == 0, (
            "Expected _relay_get_public_ip NOT to be called when relay_base_url is None, "
            f"but it was called {len(http_reflect_calls)} times"
        )


def test_r1_relay_get_public_ip_success():
    """R1: _relay_get_public_ip returns IP on success."""
    TestHTTPReflectionFallback().test_relay_get_public_ip_success()
    print("✅ PASS  R1 _relay_get_public_ip success")


def test_r2_relay_get_public_ip_timeout():
    """R2: _relay_get_public_ip returns None on timeout."""
    TestHTTPReflectionFallback().test_relay_get_public_ip_timeout()
    print("✅ PASS  R2 _relay_get_public_ip timeout → None")


def test_r3_relay_get_public_ip_invalid_json():
    """R3: _relay_get_public_ip returns None for non-JSON response."""
    TestHTTPReflectionFallback().test_relay_get_public_ip_invalid_json()
    print("✅ PASS  R3 _relay_get_public_ip invalid JSON → None")


def test_r4_status_stores_relay_base_url():
    """R4: relay_base_url is stored in _status for DCUtR to read."""
    TestHTTPReflectionFallback().test_relay_status_stores_relay_base_url()
    print("✅ PASS  R4 _status relay_base_url round-trip")


def test_r5_dcutr_http_reflect_when_stun_fails():
    asyncio.run(_async_test_r5())

async def _async_test_r5():
    """R5: DCUtRPuncher uses HTTP reflection when STUN fails."""
    await TestHTTPReflectionFallback()._async_test_dcutr_http_reflect_used_when_stun_fails()
    print("✅ PASS  R5 DCUtR HTTP reflection fallback triggered on STUN fail")


def test_r6_dcutr_no_http_reflect_without_relay_base():
    asyncio.run(_async_test_r6())

async def _async_test_r6():
    """R6: DCUtRPuncher skips HTTP reflection when no relay_base_url."""
    await TestHTTPReflectionFallback()._async_test_dcutr_no_http_reflect_when_no_relay_base()
    print("✅ PASS  R6 DCUtR HTTP reflection skipped when relay_base_url=None")
