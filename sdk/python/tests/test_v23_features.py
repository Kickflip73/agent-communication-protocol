"""
v2.3 Feature Tests
==================
1. spec/core-v1.0.md — supported_transports documented in AgentCard schema
2. RelayClient.send(auto_stream=True) — sync variant
3. AsyncRelayClient.send(auto_stream=True) — async variant
"""
from __future__ import annotations

import os
import time
import unittest
from unittest.mock import patch

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from acp_sdk.relay_client import RelayClient, AsyncRelayClient


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — produce fresh dicts each call to prevent cross-test mutation
# ─────────────────────────────────────────────────────────────────────────────

def _send_ok():
    """Return a fresh copy each call."""
    return {"ok": True, "message_id": "msg_test_001"}


_SSE_REPLY_EVENT = {"type": "acp.message", "text": "Hello back!", "role": "assistant"}

_AGENT_CARD_STREAMING = {
    "name": "TestAgent",
    "acp_version": "1.0",
    "capabilities": {
        "streaming": True,
        "supported_transports": ["http", "ws"],
    },
}

# spec path — repo root is 3 levels above sdk/python/tests/
_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.normpath(os.path.join(_TESTS_DIR, "../../.."))
_SPEC_PATH = os.path.join(_REPO_ROOT, "spec", "core-v1.0.md")


# ─────────────────────────────────────────────────────────────────────────────
# ST-DOC-1  spec/core-v1.0.md contains supported_transports
# ─────────────────────────────────────────────────────────────────────────────

class TestSpecDocumentation(unittest.TestCase):
    """Verify supported_transports is documented in spec/core-v1.0.md."""

    def test_spec_file_exists(self):
        self.assertTrue(os.path.exists(_SPEC_PATH), f"spec/core-v1.0.md must exist at {_SPEC_PATH}")

    def test_supported_transports_in_schema(self):
        """AgentCard JSON example must include supported_transports field."""
        with open(_SPEC_PATH, encoding="utf-8") as f:
            content = f.read()
        self.assertIn(
            "supported_transports",
            content,
            "spec/core-v1.0.md must document 'supported_transports' in AgentCard schema",
        )

    def test_supported_transports_in_capability_table(self):
        """Capability flags table must describe supported_transports with string[] type."""
        with open(_SPEC_PATH, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("supported_transports", content)
        self.assertIn("string[]", content)

    def test_supported_transports_example_values(self):
        """Spec must mention at least one example transport value (http / ws / h2c)."""
        with open(_SPEC_PATH, encoding="utf-8") as f:
            content = f.read()
        has_example = any(v in content for v in ('"http"', '"ws"', '"h2c"'))
        self.assertTrue(has_example, "Spec must include example transport values like 'http', 'ws'")


# ─────────────────────────────────────────────────────────────────────────────
# ST-AS-1  auto_stream=False (default) — no change to existing behavior
# ─────────────────────────────────────────────────────────────────────────────

class TestAutoStreamDisabled(unittest.TestCase):
    """auto_stream=False must behave identically to the old send()."""

    def test_send_without_auto_stream_calls_post(self):
        client = RelayClient("http://localhost:7901")
        with patch("acp_sdk.relay_client._http_post", return_value=_send_ok()) as mock_post:
            result = client.send("hello")
        mock_post.assert_called_once()
        self.assertTrue(result["ok"])
        self.assertNotIn("reply", result)

    def test_send_explicit_false_calls_post(self):
        client = RelayClient("http://localhost:7901")
        with patch("acp_sdk.relay_client._http_post", return_value=_send_ok()) as mock_post:
            result = client.send("hello", auto_stream=False)
        mock_post.assert_called_once()
        self.assertTrue(result["ok"])
        self.assertNotIn("reply", result)


# ─────────────────────────────────────────────────────────────────────────────
# ST-AS-2  auto_stream=True, peer supports streaming — reply captured
# ─────────────────────────────────────────────────────────────────────────────

class TestAutoStreamEnabledWithStreaming(unittest.TestCase):
    """auto_stream=True, peer advertises streaming → reply captured from SSE."""

    def test_reply_captured_when_peer_streams(self):
        client = RelayClient("http://localhost:7901")

        def fake_stream(timeout=60.0):
            """Yield one message event immediately."""
            time.sleep(0.05)
            yield _SSE_REPLY_EVENT

        with patch.object(client, "capabilities", return_value={"streaming": True}), \
             patch.object(client, "stream", side_effect=fake_stream), \
             patch("acp_sdk.relay_client._http_post", return_value=_send_ok()):
            result = client.send("ping", auto_stream=True, stream_timeout=5.0)

        self.assertTrue(result["ok"])
        self.assertIn("reply", result, "reply key must be present when SSE event received")
        self.assertEqual(result["reply"]["type"], "acp.message")

    def test_send_result_message_id_preserved_with_auto_stream(self):
        client = RelayClient("http://localhost:7901")

        def fake_stream(timeout=60.0):
            yield _SSE_REPLY_EVENT

        with patch.object(client, "capabilities", return_value={"streaming": True}), \
             patch.object(client, "stream", side_effect=fake_stream), \
             patch("acp_sdk.relay_client._http_post", return_value=_send_ok()):
            result = client.send("ping", auto_stream=True)

        self.assertEqual(result["message_id"], "msg_test_001")


# ─────────────────────────────────────────────────────────────────────────────
# ST-AS-3  auto_stream=True, peer does NOT support streaming — fallback
# ─────────────────────────────────────────────────────────────────────────────

class TestAutoStreamFallbackNoStreaming(unittest.TestCase):
    """auto_stream=True but peer has streaming=False → plain HTTP send."""

    def test_falls_back_to_http_when_no_streaming(self):
        client = RelayClient("http://localhost:7901")

        with patch.object(client, "capabilities", return_value={"streaming": False}), \
             patch("acp_sdk.relay_client._http_post", return_value=_send_ok()) as mock_post:
            result = client.send("ping", auto_stream=True)

        self.assertTrue(result["ok"])
        self.assertNotIn("reply", result, "no 'reply' key when peer does not stream")
        mock_post.assert_called_once()

    def test_falls_back_when_capabilities_raises(self):
        """If capabilities() throws, auto_stream falls back gracefully."""
        client = RelayClient("http://localhost:7901")

        with patch.object(client, "capabilities", side_effect=Exception("timeout")), \
             patch("acp_sdk.relay_client._http_post", return_value=_send_ok()) as mock_post:
            result = client.send("ping", auto_stream=True)

        self.assertTrue(result["ok"])
        self.assertNotIn("reply", result)


# ─────────────────────────────────────────────────────────────────────────────
# ST-AS-4  auto_stream timeout — no crash, plain result returned
# ─────────────────────────────────────────────────────────────────────────────

class TestAutoStreamTimeout(unittest.TestCase):
    """auto_stream=True, SSE produces no acp.message within timeout → plain result."""

    def test_timeout_returns_plain_result(self):
        client = RelayClient("http://localhost:7901")

        def fake_stream_empty(timeout=60.0):
            return iter([])  # no events

        with patch.object(client, "capabilities", return_value={"streaming": True}), \
             patch.object(client, "stream", side_effect=fake_stream_empty), \
             patch("acp_sdk.relay_client._http_post", return_value=_send_ok()):
            result = client.send("ping", auto_stream=True, stream_timeout=0.2)

        self.assertTrue(result["ok"])
        self.assertNotIn("reply", result)


# ─────────────────────────────────────────────────────────────────────────────
# ST-AS-5  AsyncRelayClient.send(auto_stream=True) — async variant
# ─────────────────────────────────────────────────────────────────────────────

class TestAsyncAutoStream(unittest.IsolatedAsyncioTestCase):
    """Async auto_stream — basic smoke tests."""

    async def test_async_send_no_auto_stream(self):
        client = AsyncRelayClient("http://localhost:7901")
        with patch.object(client, "_post", return_value=_send_ok()) as mock_post:
            result = await client.send("hello")
        self.assertTrue(result["ok"])
        mock_post.assert_called_once()
        self.assertNotIn("reply", result)

    async def test_async_send_auto_stream_fallback_no_streaming(self):
        client = AsyncRelayClient("http://localhost:7901")
        with patch.object(client, "capabilities", return_value={"streaming": False}), \
             patch.object(client, "_post", return_value=_send_ok()):
            result = await client.send("hello", auto_stream=True)
        self.assertTrue(result["ok"])
        self.assertNotIn("reply", result)

    async def test_async_send_auto_stream_captures_reply(self):
        client = AsyncRelayClient("http://localhost:7901")

        async def fake_stream(timeout=60.0):
            yield _SSE_REPLY_EVENT

        with patch.object(client, "capabilities", return_value={"streaming": True}), \
             patch.object(client, "stream", side_effect=fake_stream), \
             patch.object(client, "_post", return_value=_send_ok()):
            result = await client.send("hello", auto_stream=True, stream_timeout=5.0)

        self.assertTrue(result["ok"])
        self.assertIn("reply", result)
        self.assertEqual(result["reply"]["type"], "acp.message")


# ─────────────────────────────────────────────────────────────────────────────
# ST-AS-6  AgentCard supported_transports field accessible via SDK
# ─────────────────────────────────────────────────────────────────────────────

class TestSupportedTransportsViaSDK(unittest.TestCase):
    """capabilities() method returns supported_transports list."""

    def test_supported_transports_in_capabilities(self):
        client = RelayClient("http://localhost:7901")
        with patch("acp_sdk.relay_client._http_get", return_value=_AGENT_CARD_STREAMING):
            caps = client.capabilities()
        self.assertIn("supported_transports", caps)
        self.assertIsInstance(caps["supported_transports"], list)
        self.assertIn("http", caps["supported_transports"])

    def test_supported_transports_h2c(self):
        """Verify h2c appears in transport list when HTTP/2 enabled."""
        card_h2 = {
            "capabilities": {
                "streaming": True,
                "supported_transports": ["http", "ws", "h2c"],
            }
        }
        client = RelayClient("http://localhost:7901")
        with patch("acp_sdk.relay_client._http_get", return_value=card_h2):
            caps = client.capabilities()
        self.assertIn("h2c", caps["supported_transports"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
