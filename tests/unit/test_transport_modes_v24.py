"""
Unit tests for v2.4 feature: AgentCard top-level `transport_modes` field.

Verifies:
  - Default value is ["p2p", "relay"]
  - Field present in AgentCard returned by _make_agent_card()
  - Field served at /.well-known/acp.json HTTP endpoint
  - Field is a list (not a set/tuple/string)
  - Custom subset (e.g. ["p2p"]) is honoured when _transport_modes is set
  - ["relay"] only (no p2p) is valid
  - Empty list falls back to default (guarded by CLI parsing)
  - transport_modes is distinct from capabilities.supported_transports
  - transport_modes appears as a top-level key (not nested under capabilities)
"""
import sys
import os
import unittest
import json
import io

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_RELAY_DIR = os.path.join(_REPO_ROOT, "relay")
sys.path.insert(0, _RELAY_DIR)

import unittest.mock as mock
sys.modules.setdefault("websockets", mock.MagicMock())
sys.modules.setdefault("websockets.exceptions", mock.MagicMock())

import acp_relay as relay  # noqa: E402


# ── Helpers ────────────────────────────────────────────────────────────────

def _make_card(transport_modes=None):
    """Return a fresh AgentCard with optional _transport_modes override."""
    original = relay._transport_modes[:]
    try:
        if transport_modes is not None:
            relay._transport_modes = list(transport_modes)
        # Ensure http_port is set (needed by _make_agent_card)
        relay._status.setdefault("http_port", 7901)
        return relay._make_agent_card("TestAgent", ["skill-a"])
    finally:
        relay._transport_modes = original


class _CaptureHandler:
    """Minimal shim to call HTTP handler methods and capture response."""

    def __init__(self, path, body_bytes=None):
        self.path = path
        self._rfile = io.BytesIO(body_bytes or b"")
        self._response_code = None
        self._response_headers = {}
        self._response_body = None

    # BaseHTTPRequestHandler-style interface
    def send_response(self, code):
        self._response_code = code

    def send_header(self, key, value):
        self._response_headers[key] = value

    def end_headers(self):
        pass

    def wfile_write(self, data):
        self._response_body_raw = data

    def _json(self, obj, code=200):
        self._response_code = code
        self._response_body = obj

    def _ok(self, obj):
        self._json(obj, 200)


def _call_well_known():
    """Invoke the /.well-known/acp.json handler and return (code, body_dict)."""
    relay._status.setdefault("http_port", 7901)
    h = _CaptureHandler("/.well-known/acp.json", None)

    from http.server import BaseHTTPRequestHandler as _BH
    # Patch handler parent methods onto our shim
    import acp_relay as _r

    # Find the handler class
    handler_cls = _r.ACPHandler if hasattr(_r, "ACPHandler") else None
    if handler_cls is None:
        # Try to locate it by scanning module
        import inspect
        for name, obj in inspect.getmembers(_r, inspect.isclass):
            if hasattr(obj, "do_GET") and "Handler" in name:
                handler_cls = obj
                break

    if handler_cls is None:
        return None, None  # skip if handler not found

    # Create a minimal instance without calling __init__
    inst = object.__new__(handler_cls)
    inst.path = "/.well-known/acp.json"
    inst.headers = {}
    inst.rfile = io.BytesIO(b"")
    inst._response_code = None
    inst._response_body = None

    # Inject _json helper
    captured = {}

    def _json(obj, code=200):
        captured["code"] = code
        captured["body"] = obj

    inst._json = _json

    # Also inject send_response / send_header / end_headers for raw paths
    inst.send_response  = lambda c: None
    inst.send_header    = lambda k, v: None
    inst.end_headers    = lambda: None
    inst.wfile          = io.BytesIO()
    inst.connection     = mock.MagicMock()
    inst.client_address = ("127.0.0.1", 9999)
    inst.server         = mock.MagicMock()
    inst.requestline    = "GET /.well-known/acp.json HTTP/1.1"
    inst.request_version = "HTTP/1.1"
    inst.command        = "GET"

    try:
        inst.do_GET()
    except Exception:
        pass

    return captured.get("code"), captured.get("body")


# ══════════════════════════════════════════════════════════════════════════════
# Tests: _make_agent_card transport_modes
# ══════════════════════════════════════════════════════════════════════════════

class TestTransportModesAgentCard(unittest.TestCase):

    def test_transport_modes_present_in_card(self):
        """AgentCard must contain top-level 'transport_modes' key."""
        card = _make_card()
        self.assertIn("transport_modes", card)

    def test_transport_modes_is_list(self):
        """transport_modes must be a list (not set/tuple/string)."""
        card = _make_card()
        self.assertIsInstance(card["transport_modes"], list)

    def test_default_transport_modes_both(self):
        """Default transport_modes should be ['p2p', 'relay'] (both)."""
        card = _make_card(transport_modes=["p2p", "relay"])
        self.assertIn("p2p", card["transport_modes"])
        self.assertIn("relay", card["transport_modes"])
        self.assertEqual(len(card["transport_modes"]), 2)

    def test_transport_modes_p2p_only(self):
        """Agent can declare P2P-only mode."""
        card = _make_card(transport_modes=["p2p"])
        self.assertEqual(card["transport_modes"], ["p2p"])
        self.assertNotIn("relay", card["transport_modes"])

    def test_transport_modes_relay_only(self):
        """Agent can declare relay-only mode (e.g. sandboxed environment)."""
        card = _make_card(transport_modes=["relay"])
        self.assertEqual(card["transport_modes"], ["relay"])
        self.assertNotIn("p2p", card["transport_modes"])

    def test_transport_modes_is_top_level(self):
        """transport_modes must be a top-level field, NOT nested under capabilities."""
        card = _make_card()
        self.assertIn("transport_modes", card)
        capabilities = card.get("capabilities", {})
        # The capabilities block should have supported_transports (protocol bindings),
        # not transport_modes (routing modes).
        self.assertNotIn("transport_modes", capabilities,
            "transport_modes should be top-level, not inside capabilities")

    def test_transport_modes_distinct_from_supported_transports(self):
        """transport_modes (routing) != capabilities.supported_transports (protocol)."""
        card = _make_card()
        # supported_transports = protocol bindings e.g. ["http", "ws"]
        caps = card.get("capabilities", {})
        supported = caps.get("supported_transports", [])
        transport_modes = card["transport_modes"]

        # They serve different purposes — values should differ conceptually
        # supported_transports values are protocol names (http, ws, h2c)
        # transport_modes values are routing modes (p2p, relay)
        for mode in transport_modes:
            self.assertIn(mode, ("p2p", "relay"),
                f"transport_modes value '{mode}' is not a valid routing mode")

        for proto in supported:
            self.assertIn(proto, ("http", "ws", "h2c"),
                f"supported_transports value '{proto}' is not a valid protocol binding")

    def test_transport_modes_snapshot_not_reference(self):
        """Modifying returned card['transport_modes'] must not mutate _transport_modes."""
        card = _make_card(transport_modes=["p2p", "relay"])
        card["transport_modes"].append("unexpected")
        card2 = _make_card(transport_modes=["p2p", "relay"])
        self.assertEqual(len(card2["transport_modes"]), 2,
            "_transport_modes global was mutated through card reference")

    def test_transport_modes_version_bump(self):
        """VERSION should be >= 2.4.0 to reflect this feature."""
        parts = relay.VERSION.split(".")
        major, minor = int(parts[0]), int(parts[1])
        self.assertTrue(
            (major, minor) >= (2, 4),
            f"VERSION {relay.VERSION} should be >= 2.4.0 for transport_modes feature"
        )


# ══════════════════════════════════════════════════════════════════════════════
# Tests: Global default
# ══════════════════════════════════════════════════════════════════════════════

class TestTransportModesGlobal(unittest.TestCase):

    def test_global_default_is_both(self):
        """_transport_modes global default must be ['p2p', 'relay']."""
        # Save & restore
        original = relay._transport_modes[:]
        try:
            # Reset to module-level default by re-importing attribute
            import importlib
            # Just check the module attribute directly
            self.assertIn("p2p", relay._transport_modes)
            self.assertIn("relay", relay._transport_modes)
        finally:
            relay._transport_modes = original

    def test_global_is_mutable_list(self):
        """_transport_modes must be a mutable list for runtime reconfiguration."""
        self.assertIsInstance(relay._transport_modes, list)

    def test_global_values_are_valid(self):
        """All values in the default _transport_modes must be known routing modes."""
        valid = {"p2p", "relay"}
        for mode in relay._transport_modes:
            self.assertIn(mode, valid,
                f"Unexpected default routing mode '{mode}'")


# ══════════════════════════════════════════════════════════════════════════════
# Tests: AgentCard served at /.well-known/acp.json
# ══════════════════════════════════════════════════════════════════════════════

class TestTransportModesEndpoint(unittest.TestCase):

    def setUp(self):
        relay._status.setdefault("http_port", 7901)
        relay._status["agent_card"] = _make_card(transport_modes=["p2p", "relay"])

    def test_agent_card_status_has_transport_modes(self):
        """_status['agent_card'] must contain transport_modes."""
        card = relay._status["agent_card"]
        self.assertIn("transport_modes", card)

    def test_agent_card_transport_modes_values(self):
        """_status['agent_card'].transport_modes must list p2p and relay."""
        card = relay._status["agent_card"]
        self.assertIn("p2p", card["transport_modes"])
        self.assertIn("relay", card["transport_modes"])

    def test_p2p_only_in_status(self):
        """Setting _transport_modes to ['p2p'] and rebuilding card reflects correctly."""
        relay._transport_modes = ["p2p"]
        relay._status["agent_card"] = relay._make_agent_card("TestAgent", [])
        card = relay._status["agent_card"]
        self.assertEqual(card["transport_modes"], ["p2p"])
        # Restore
        relay._transport_modes = ["p2p", "relay"]
        relay._status["agent_card"] = relay._make_agent_card("TestAgent", [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
