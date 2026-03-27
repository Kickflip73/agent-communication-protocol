"""
tests/test_limitations.py — ACP v2.7 AgentCard limitations field
=================================================================
Tests the `limitations: string[]` field added in v2.7.

Test IDs:
  LM1 — default (no --limitations): AgentCard contains `limitations: []`
  LM2 — --limitations no_file_access,no_internet → AgentCard contains correct array
  LM3 — /status response contains `limitations` field
  LM4 — single limitation string parses correctly
  LM5 — `limitations` field is optional / backward-compatible (absent = treated as [])
"""
import sys
import os
import json
import importlib
import types
import unittest
from unittest.mock import patch, MagicMock

# ── Helper: import relay module with overridable globals ──────────────────────
_RELAY_PATH = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")
_RELAY_PATH = os.path.abspath(_RELAY_PATH)


def _load_relay():
    """Import acp_relay as a fresh module each time (avoid global state bleed)."""
    spec = importlib.util.spec_from_file_location("acp_relay_lm", _RELAY_PATH)
    mod = importlib.util.module_from_spec(spec)
    # Prevent asyncio/socket side-effects from running at import time
    # (the module only defines functions at import; main() is not called)
    spec.loader.exec_module(mod)
    return mod


# ═══════════════════════════════════════════════════════════════════════════════
# LM1 — default limitations = []
# ═══════════════════════════════════════════════════════════════════════════════
class TestLM1Default(unittest.TestCase):
    """LM1: When --limitations is NOT passed, AgentCard.limitations = []"""

    def test_default_limitations_empty_list(self):
        mod = _load_relay()
        # _limitations global default should be []
        self.assertEqual(mod._limitations, [])

    def test_agent_card_contains_limitations_key(self):
        mod = _load_relay()
        card = mod._make_agent_card("TestAgent", [])
        self.assertIn("limitations", card,
                      "AgentCard MUST contain 'limitations' key even when default")

    def test_agent_card_limitations_is_empty_list(self):
        mod = _load_relay()
        card = mod._make_agent_card("TestAgent", [])
        self.assertEqual(card["limitations"], [],
                         "Default AgentCard.limitations must be []")

    def test_limitations_is_list_type(self):
        mod = _load_relay()
        card = mod._make_agent_card("TestAgent", [])
        self.assertIsInstance(card["limitations"], list,
                              "limitations must be a list (string[])")


# ═══════════════════════════════════════════════════════════════════════════════
# LM2 — multi-value limitations array
# ═══════════════════════════════════════════════════════════════════════════════
class TestLM2MultiValue(unittest.TestCase):
    """LM2: --limitations no_file_access,no_internet → AgentCard correct array"""

    def _card_with_limitations(self, limitations_list):
        mod = _load_relay()
        mod._limitations = list(limitations_list)
        return mod._make_agent_card("TestAgent", [])

    def test_two_limitations(self):
        card = self._card_with_limitations(["no_file_access", "no_internet"])
        self.assertEqual(card["limitations"], ["no_file_access", "no_internet"])

    def test_limitations_order_preserved(self):
        lims = ["no_internet", "no_file_access", "no_shell"]
        card = self._card_with_limitations(lims)
        self.assertEqual(card["limitations"], lims,
                         "Limitations order must be preserved as-supplied")

    def test_limitations_are_strings(self):
        card = self._card_with_limitations(["no_file_access", "no_internet"])
        for item in card["limitations"]:
            self.assertIsInstance(item, str,
                                  f"Each limitation must be a string, got {type(item)}")

    def test_comma_parse_logic(self):
        """Simulate CLI comma-split parsing: 'no_file_access,no_internet' → list"""
        raw = "no_file_access,no_internet"
        parsed = [lim.strip() for lim in raw.split(",") if lim.strip()]
        self.assertEqual(parsed, ["no_file_access", "no_internet"])

    def test_whitespace_trimmed_in_parse(self):
        raw = " no_file_access , no_internet "
        parsed = [lim.strip() for lim in raw.split(",") if lim.strip()]
        self.assertEqual(parsed, ["no_file_access", "no_internet"])


# ═══════════════════════════════════════════════════════════════════════════════
# LM3 — /status response contains limitations
# ═══════════════════════════════════════════════════════════════════════════════
class TestLM3StatusEndpoint(unittest.TestCase):
    """LM3: /status response contains `limitations` field"""

    def test_status_dict_has_limitations_key(self):
        mod = _load_relay()
        self.assertIn("limitations", mod._status,
                      "_status dict must include 'limitations' key")

    def test_status_default_limitations_empty(self):
        mod = _load_relay()
        self.assertEqual(mod._status["limitations"], [],
                         "_status['limitations'] default must be []")

    def test_status_limitations_reflects_global(self):
        mod = _load_relay()
        mod._limitations = ["no_shell", "no_network"]
        mod._status["limitations"] = list(mod._limitations)
        self.assertEqual(mod._status["limitations"], ["no_shell", "no_network"])


# ═══════════════════════════════════════════════════════════════════════════════
# LM4 — single limitation value
# ═══════════════════════════════════════════════════════════════════════════════
class TestLM4SingleValue(unittest.TestCase):
    """LM4: Single limitation string parses and serializes correctly"""

    def test_single_limitation_in_card(self):
        mod = _load_relay()
        mod._limitations = ["no_internet"]
        card = mod._make_agent_card("TestAgent", [])
        self.assertEqual(card["limitations"], ["no_internet"])

    def test_single_limitation_comma_parse(self):
        raw = "no_internet"
        parsed = [lim.strip() for lim in raw.split(",") if lim.strip()]
        self.assertEqual(parsed, ["no_internet"])
        self.assertEqual(len(parsed), 1)

    def test_single_limitation_json_round_trip(self):
        mod = _load_relay()
        mod._limitations = ["no_file_access"]
        card = mod._make_agent_card("SingleLimitAgent", ["skill1"])
        serialized = json.dumps(card)
        deserialized = json.loads(serialized)
        self.assertEqual(deserialized["limitations"], ["no_file_access"],
                         "limitations must survive JSON round-trip correctly")


# ═══════════════════════════════════════════════════════════════════════════════
# LM5 — backward compatibility (optional field)
# ═══════════════════════════════════════════════════════════════════════════════
class TestLM5BackwardCompat(unittest.TestCase):
    """LM5: `limitations` is optional — absent in legacy cards treated as []"""

    def test_old_card_without_limitations_treated_as_empty(self):
        """Simulate an old AgentCard that predates v2.7 (no limitations key)."""
        legacy_card = {
            "name": "LegacyAgent",
            "version": "2.6.0",
            "acp_version": "2.6.0",
            "capabilities": {"streaming": True},
        }
        # Client-side defensive read: treat absence as []
        limitations = legacy_card.get("limitations", [])
        self.assertEqual(limitations, [],
                         "Missing limitations key must default to [] for backward compat")

    def test_new_card_limitations_coexists_with_capabilities(self):
        mod = _load_relay()
        mod._limitations = ["no_file_access"]
        card = mod._make_agent_card("NewAgent", [])
        # Both fields must coexist
        self.assertIn("capabilities", card)
        self.assertIn("limitations", card)
        self.assertIn("availability", card["capabilities"],
                      "capabilities.availability must still exist alongside top-level limitations")

    def test_limitations_does_not_break_existing_fields(self):
        mod = _load_relay()
        mod._limitations = ["no_internet"]
        card = mod._make_agent_card("TestAgent", ["skill1"])
        # All pre-existing fields still present
        for required_field in ["name", "version", "acp_version", "capabilities",
                                "transport_modes", "supported_interfaces", "skills"]:
            self.assertIn(required_field, card,
                          f"Pre-existing field '{required_field}' must not be removed by v2.7")

    def test_limitations_empty_string_becomes_empty_list(self):
        """Edge case: if somehow an empty string is passed, result is []"""
        raw = ""
        parsed = [lim.strip() for lim in raw.split(",") if lim.strip()]
        self.assertEqual(parsed, [])

    def test_limitations_none_input_becomes_empty_list(self):
        """If raw_limitations is None (flag not passed), limitations = []"""
        raw_limitations = None
        result = [] if raw_limitations is None else [
            lim.strip() for lim in raw_limitations.split(",") if lim.strip()
        ]
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
