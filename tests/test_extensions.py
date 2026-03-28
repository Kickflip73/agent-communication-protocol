"""
tests/test_extensions.py
========================
Tests for ACP v2.8 Extension mechanism.

Covers:
  - AgentCard always includes 'extensions' field (default empty list)
  - Built-in extensions auto-registered (hmac, mdns, h2c)
  - --extensions CLI flag manual append
  - Extension object field validation (uri required, required defaults false, params defaults empty)
  - SDK Extension dataclass: construction, to_dict, from_dict
  - SDK AgentCard: extensions field parsed, serialised, convenience methods
  - Backward compat: old responses without 'extensions' field parse correctly
  - _make_builtin_extensions() reflects runtime state
  - Deduplication of extension URIs
"""

import sys
import os
import json
import importlib

import pytest

# ── path setup ────────────────────────────────────────────────────────────────
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SDK_PATH   = os.path.join(REPO_ROOT, "sdk", "python")
RELAY_PATH = os.path.join(REPO_ROOT, "relay")

if SDK_PATH not in sys.path:
    sys.path.insert(0, SDK_PATH)
if RELAY_PATH not in sys.path:
    sys.path.insert(0, RELAY_PATH)

from acp_client.models import AgentCard, Extension  # noqa: E402


# ══════════════════════════════════════════════════════════════════════════════
# 1. Extension dataclass — construction & defaults
# ══════════════════════════════════════════════════════════════════════════════

class TestExtensionDefaults:
    """Extension object field validation."""

    def test_uri_required(self):
        """Extension must have a uri."""
        ext = Extension(uri="acp:ext:hmac-v1")
        assert ext.uri == "acp:ext:hmac-v1"

    def test_required_defaults_false(self):
        """required defaults to False."""
        ext = Extension(uri="acp:ext:hmac-v1")
        assert ext.required is False

    def test_params_defaults_empty_dict(self):
        """params defaults to empty dict."""
        ext = Extension(uri="acp:ext:hmac-v1")
        assert ext.params == {}

    def test_explicit_required_true(self):
        ext = Extension(uri="https://corp.example.com/ext/billing", required=True)
        assert ext.required is True

    def test_explicit_params(self):
        ext = Extension(uri="acp:ext:hmac-v1", params={"scheme": "hmac-sha256"})
        assert ext.params["scheme"] == "hmac-sha256"

    def test_repr_contains_uri(self):
        ext = Extension(uri="acp:ext:mdns-v1")
        assert "acp:ext:mdns-v1" in repr(ext)

    def test_repr_shows_required_when_true(self):
        ext = Extension(uri="acp:ext:mdns-v1", required=True)
        assert "required" in repr(ext)


# ══════════════════════════════════════════════════════════════════════════════
# 2. Extension serialisation / deserialisation
# ══════════════════════════════════════════════════════════════════════════════

class TestExtensionSerialization:
    """Extension.to_dict / from_dict round-trip."""

    def test_to_dict_basic(self):
        ext = Extension(uri="acp:ext:hmac-v1")
        d = ext.to_dict()
        assert d["uri"] == "acp:ext:hmac-v1"
        assert d["required"] is False
        # params omitted when empty
        assert "params" not in d

    def test_to_dict_with_params(self):
        ext = Extension(uri="acp:ext:hmac-v1", params={"scheme": "hmac-sha256"})
        d = ext.to_dict()
        assert d["params"] == {"scheme": "hmac-sha256"}

    def test_from_dict_basic(self):
        d = {"uri": "acp:ext:mdns-v1"}
        ext = Extension.from_dict(d)
        assert ext.uri == "acp:ext:mdns-v1"
        assert ext.required is False
        assert ext.params == {}

    def test_from_dict_full(self):
        d = {"uri": "acp:ext:hmac-v1", "required": True, "params": {"scheme": "hmac-sha256"}}
        ext = Extension.from_dict(d)
        assert ext.uri == "acp:ext:hmac-v1"
        assert ext.required is True
        assert ext.params["scheme"] == "hmac-sha256"

    def test_from_dict_missing_uri_raises(self):
        with pytest.raises(ValueError, match="uri"):
            Extension.from_dict({"required": False})

    def test_from_dict_non_dict_raises(self):
        with pytest.raises(ValueError):
            Extension.from_dict("acp:ext:hmac-v1")

    def test_round_trip(self):
        ext = Extension(uri="https://corp.example.com/ext/billing", required=True,
                        params={"tier": "pro", "version": "2"})
        restored = Extension.from_dict(ext.to_dict())
        assert restored.uri == ext.uri
        assert restored.required == ext.required
        assert restored.params == ext.params


# ══════════════════════════════════════════════════════════════════════════════
# 3. AgentCard extensions field — SDK model
# ══════════════════════════════════════════════════════════════════════════════

class TestAgentCardExtensionsField:
    """AgentCard includes extensions in model and serialisation."""

    def test_default_extensions_empty_list(self):
        """AgentCard.extensions defaults to empty list."""
        card = AgentCard(name="Test")
        assert card.extensions == []

    def test_to_dict_always_emits_extensions(self):
        """to_dict always emits 'extensions' key."""
        card = AgentCard(name="Test")
        d = card.to_dict()
        assert "extensions" in d
        assert d["extensions"] == []

    def test_to_dict_with_extensions(self):
        card = AgentCard(
            name="Test",
            extensions=[
                Extension(uri="acp:ext:hmac-v1", params={"scheme": "hmac-sha256"}),
                Extension(uri="acp:ext:mdns-v1"),
            ],
        )
        d = card.to_dict()
        assert len(d["extensions"]) == 2
        assert d["extensions"][0]["uri"] == "acp:ext:hmac-v1"
        assert d["extensions"][1]["uri"] == "acp:ext:mdns-v1"

    def test_from_dict_parses_extensions(self):
        raw = {
            "name": "Agent",
            "extensions": [
                {"uri": "acp:ext:hmac-v1", "required": False, "params": {"scheme": "hmac-sha256"}},
                {"uri": "acp:ext:mdns-v1"},
            ],
        }
        card = AgentCard.from_dict(raw)
        assert len(card.extensions) == 2
        assert isinstance(card.extensions[0], Extension)
        assert card.extensions[0].uri == "acp:ext:hmac-v1"
        assert card.extensions[1].uri == "acp:ext:mdns-v1"


# ══════════════════════════════════════════════════════════════════════════════
# 4. Backward compatibility
# ══════════════════════════════════════════════════════════════════════════════

class TestBackwardCompat:
    """Old AgentCard responses without 'extensions' field parse gracefully."""

    def test_from_dict_no_extensions_field(self):
        """Responses without 'extensions' deserialise to empty list."""
        old_card = {
            "name": "LegacyAgent",
            "version": "2.7.0",
            "acp_version": "2.7.0",
            "capabilities": {"streaming": True},
        }
        card = AgentCard.from_dict(old_card)
        assert card.extensions == []

    def test_from_dict_null_extensions(self):
        """extensions: null treated as empty list."""
        raw = {"name": "Agent", "extensions": None}
        card = AgentCard.from_dict(raw)
        assert card.extensions == []

    def test_from_dict_malformed_extension_skipped(self):
        """Malformed extension entries are skipped (forward compat)."""
        raw = {
            "name": "Agent",
            "extensions": [
                {"uri": "acp:ext:hmac-v1"},   # valid
                {"required": False},           # missing uri — skip
                "not-a-dict",                  # wrong type — skip
            ],
        }
        card = AgentCard.from_dict(raw)
        # Only the valid one is kept
        assert len(card.extensions) == 1
        assert card.extensions[0].uri == "acp:ext:hmac-v1"


# ══════════════════════════════════════════════════════════════════════════════
# 5. AgentCard convenience methods for extensions
# ══════════════════════════════════════════════════════════════════════════════

class TestAgentCardExtensionMethods:
    """has_extension / get_extension / required_extensions helpers."""

    def setup_method(self):
        self.card = AgentCard(
            name="Agent",
            extensions=[
                Extension(uri="acp:ext:hmac-v1", params={"scheme": "hmac-sha256"}),
                Extension(uri="acp:ext:mdns-v1"),
                Extension(uri="https://corp.example.com/ext/billing", required=True),
            ],
        )

    def test_has_extension_present(self):
        assert self.card.has_extension("acp:ext:hmac-v1") is True

    def test_has_extension_absent(self):
        assert self.card.has_extension("acp:ext:h2c-v1") is False

    def test_get_extension_returns_object(self):
        ext = self.card.get_extension("acp:ext:hmac-v1")
        assert ext is not None
        assert ext.uri == "acp:ext:hmac-v1"
        assert ext.params["scheme"] == "hmac-sha256"

    def test_get_extension_absent_returns_none(self):
        assert self.card.get_extension("acp:ext:nonexistent") is None

    def test_required_extensions(self):
        req = self.card.required_extensions()
        assert len(req) == 1
        assert req[0].uri == "https://corp.example.com/ext/billing"

    def test_required_extensions_empty_when_none_required(self):
        card = AgentCard(
            name="Agent",
            extensions=[Extension(uri="acp:ext:hmac-v1")],
        )
        assert card.required_extensions() == []


# ══════════════════════════════════════════════════════════════════════════════
# 6. Relay: _make_builtin_extensions and _make_agent_card
# ══════════════════════════════════════════════════════════════════════════════

class TestRelayExtensions:
    """Test relay-side extension auto-registration."""

    def _import_relay(self):
        """Import acp_relay module with fresh state."""
        if "acp_relay" in sys.modules:
            del sys.modules["acp_relay"]
        import acp_relay
        return acp_relay

    def test_builtin_extensions_empty_by_default(self):
        relay = self._import_relay()
        # Reset runtime state
        relay._hmac_secret = None
        relay._mdns_running = False
        relay._http2_enabled = False
        exts = relay._make_builtin_extensions()
        assert exts == []

    def test_builtin_hmac_registered_when_secret_set(self):
        relay = self._import_relay()
        relay._hmac_secret = b"test-secret"
        relay._mdns_running = False
        relay._http2_enabled = False
        exts = relay._make_builtin_extensions()
        uris = [e["uri"] for e in exts]
        assert "acp:ext:hmac-v1" in uris
        # Check params
        hmac_ext = next(e for e in exts if e["uri"] == "acp:ext:hmac-v1")
        assert hmac_ext["params"]["scheme"] == "hmac-sha256"

    def test_builtin_mdns_registered_when_mdns_running(self):
        relay = self._import_relay()
        relay._hmac_secret = None
        relay._mdns_running = True
        relay._http2_enabled = False
        exts = relay._make_builtin_extensions()
        uris = [e["uri"] for e in exts]
        assert "acp:ext:mdns-v1" in uris

    def test_builtin_h2c_registered_when_http2_enabled(self):
        relay = self._import_relay()
        relay._hmac_secret = None
        relay._mdns_running = False
        relay._http2_enabled = True
        exts = relay._make_builtin_extensions()
        uris = [e["uri"] for e in exts]
        assert "acp:ext:h2c-v1" in uris

    def test_builtin_all_three_registered(self):
        relay = self._import_relay()
        relay._hmac_secret = b"secret"
        relay._mdns_running = True
        relay._http2_enabled = True
        exts = relay._make_builtin_extensions()
        uris = [e["uri"] for e in exts]
        assert "acp:ext:hmac-v1" in uris
        assert "acp:ext:mdns-v1" in uris
        assert "acp:ext:h2c-v1" in uris

    def test_agent_card_always_has_extensions_key(self):
        """_make_agent_card always emits 'extensions' key."""
        relay = self._import_relay()
        relay._hmac_secret = None
        relay._mdns_running = False
        relay._http2_enabled = False
        relay._extensions = []
        relay._limitations = []
        relay._transport_modes = ["p2p", "relay"]
        relay._supported_interfaces_override = None
        relay._status["http_port"] = 7901
        relay._status["p2p_enabled"] = False
        relay._ed25519_private = None
        card = relay._make_agent_card("TestAgent", [])
        assert "extensions" in card
        assert isinstance(card["extensions"], list)

    def test_agent_card_extensions_empty_when_no_capabilities(self):
        relay = self._import_relay()
        relay._hmac_secret = None
        relay._mdns_running = False
        relay._http2_enabled = False
        relay._extensions = []
        relay._limitations = []
        relay._transport_modes = ["p2p", "relay"]
        relay._supported_interfaces_override = None
        relay._status["http_port"] = 7901
        relay._status["p2p_enabled"] = False
        relay._ed25519_private = None
        card = relay._make_agent_card("TestAgent", [])
        assert card["extensions"] == []

    def test_agent_card_user_declared_extensions_merged(self):
        """User-declared _extensions are merged with built-in ones."""
        relay = self._import_relay()
        relay._hmac_secret = None
        relay._mdns_running = False
        relay._http2_enabled = False
        relay._extensions = [{"uri": "https://corp.example.com/ext/billing", "required": False, "params": {}}]
        relay._limitations = []
        relay._transport_modes = ["p2p", "relay"]
        relay._supported_interfaces_override = None
        relay._status["http_port"] = 7901
        relay._status["p2p_enabled"] = False
        relay._ed25519_private = None
        card = relay._make_agent_card("TestAgent", [])
        uris = [e["uri"] for e in card["extensions"]]
        assert "https://corp.example.com/ext/billing" in uris

    def test_extension_deduplication_by_uri(self):
        """If same URI appears in built-in and user-declared, it's deduplicated."""
        relay = self._import_relay()
        relay._hmac_secret = b"secret"
        relay._mdns_running = False
        relay._http2_enabled = False
        # User also declares hmac explicitly
        relay._extensions = [{"uri": "acp:ext:hmac-v1", "required": False, "params": {}}]
        relay._limitations = []
        relay._transport_modes = ["p2p", "relay"]
        relay._supported_interfaces_override = None
        relay._status["http_port"] = 7901
        relay._status["p2p_enabled"] = False
        relay._ed25519_private = None
        card = relay._make_agent_card("TestAgent", [])
        uris = [e["uri"] for e in card["extensions"]]
        # hmac-v1 should appear exactly once
        assert uris.count("acp:ext:hmac-v1") == 1

    def test_extension_required_false_default_in_relay(self):
        """Built-in extensions have required=False."""
        relay = self._import_relay()
        relay._hmac_secret = b"secret"
        relay._mdns_running = True
        relay._http2_enabled = True
        relay._extensions = []
        relay._limitations = []
        relay._transport_modes = ["p2p", "relay"]
        relay._supported_interfaces_override = None
        relay._status["http_port"] = 7901
        relay._status["p2p_enabled"] = False
        relay._ed25519_private = None
        card = relay._make_agent_card("TestAgent", [])
        for ext in card["extensions"]:
            assert ext["required"] is False, f"{ext['uri']} should not be required"


# ══════════════════════════════════════════════════════════════════════════════
# 7. --extensions CLI flag parsing
# ══════════════════════════════════════════════════════════════════════════════

class TestExtensionsCLIFlag:
    """Verify --extensions bulk URI flag is wired correctly."""

    def test_extensions_bulk_uri_parsing(self):
        """Simulate what the relay does when --extensions is passed."""
        raw = "acp:ext:custom-v1,https://corp.example.com/ext/audit"
        uris = [u.strip() for u in raw.split(",") if u.strip()]
        assert "acp:ext:custom-v1" in uris
        assert "https://corp.example.com/ext/audit" in uris
        assert len(uris) == 2

    def test_extensions_bulk_dedup_with_existing(self):
        """Existing entries are not duplicated by --extensions."""
        existing = [{"uri": "acp:ext:custom-v1", "required": False, "params": {}}]
        raw = "acp:ext:custom-v1,acp:ext:new-v1"
        uris = [u.strip() for u in raw.split(",") if u.strip()]
        for uri in uris:
            if not any(e["uri"] == uri for e in existing):
                existing.append({"uri": uri, "required": False, "params": {}})
        result_uris = [e["uri"] for e in existing]
        assert result_uris.count("acp:ext:custom-v1") == 1
        assert "acp:ext:new-v1" in result_uris
