"""
Unit tests for acp_relay.py core helpers and logic.

Covers (v0.9 P1):
  - _err()            : error response builder
  - _make_id()        : id generation
  - _make_token()     : token generation
  - _now()            : timestamp format
  - _make_text_part() : Part constructors
  - _make_file_part()
  - _make_data_part()
  - _validate_part()  : per-part validation
  - _validate_parts() : list validation
  - _hmac_sign()      : HMAC-SHA256 signing
  - _hmac_verify()    : HMAC verification (correct / tampered / no secret)
  - Task state constants and TERMINAL_STATES set
  - _load_config_file(): JSON and YAML parsing, precedence
  - parse_link()      : acp:// link parsing
"""
import sys
import os
import unittest
import tempfile
import json
import hmac
import hashlib

# ── Import relay module directly ───────────────────────────────────────────
# acp_relay.py lives at relay/acp_relay.py; add it to sys.path
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_RELAY_DIR = os.path.join(_REPO_ROOT, "relay")
sys.path.insert(0, _RELAY_DIR)

# websockets import guard — relay exits(1) if missing; stub it out for unit tests
import unittest.mock as mock
sys.modules.setdefault("websockets", mock.MagicMock())
sys.modules.setdefault("websockets.exceptions", mock.MagicMock())

import acp_relay as relay   # noqa: E402  (import after path setup)


# ══════════════════════════════════════════════════════════════════════════════
# _err() — error response builder
# ══════════════════════════════════════════════════════════════════════════════

class TestErrHelper(unittest.TestCase):

    def test_basic_structure(self):
        body, status = relay._err(relay.ERR_INVALID_REQUEST, "bad input")
        self.assertEqual(body["ok"], False)
        self.assertEqual(body["error_code"], relay.ERR_INVALID_REQUEST)
        self.assertEqual(body["error"], "bad input")
        self.assertEqual(status, 400)

    def test_custom_http_status(self):
        _, status = relay._err(relay.ERR_NOT_CONNECTED, "no peer", 503)
        self.assertEqual(status, 503)

    def test_failed_message_id_included(self):
        body, _ = relay._err(relay.ERR_MSG_TOO_LARGE, "too big", 413,
                             failed_message_id="msg_abc")
        self.assertEqual(body["failed_message_id"], "msg_abc")

    def test_failed_message_id_absent_by_default(self):
        body, _ = relay._err(relay.ERR_INTERNAL, "boom")
        self.assertNotIn("failed_message_id", body)

    def test_all_error_codes_are_strings(self):
        codes = [
            relay.ERR_NOT_CONNECTED, relay.ERR_MSG_TOO_LARGE,
            relay.ERR_NOT_FOUND, relay.ERR_INVALID_REQUEST,
            relay.ERR_TIMEOUT, relay.ERR_INTERNAL,
        ]
        for code in codes:
            self.assertIsInstance(code, str)
            body, _ = relay._err(code, "test")
            self.assertEqual(body["error_code"], code)


# ══════════════════════════════════════════════════════════════════════════════
# ID / token generators
# ══════════════════════════════════════════════════════════════════════════════

class TestIdGenerators(unittest.TestCase):

    def test_make_id_default_prefix(self):
        mid = relay._make_id()
        self.assertTrue(mid.startswith("msg_"))
        self.assertGreater(len(mid), 4)

    def test_make_id_custom_prefix(self):
        tid = relay._make_id("task")
        self.assertTrue(tid.startswith("task_"))

    def test_make_id_uniqueness(self):
        ids = {relay._make_id() for _ in range(200)}
        self.assertEqual(len(ids), 200)

    def test_make_token_format(self):
        tok = relay._make_token()
        self.assertTrue(tok.startswith("tok_"))
        self.assertEqual(len(tok), 4 + 16)  # "tok_" + 16 hex chars

    def test_make_token_uniqueness(self):
        tokens = {relay._make_token() for _ in range(200)}
        self.assertEqual(len(tokens), 200)

    def test_now_iso8601(self):
        ts = relay._now()
        self.assertTrue(ts.endswith("Z"))
        self.assertIn("T", ts)
        # Should be parseable
        import datetime
        datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))


# ══════════════════════════════════════════════════════════════════════════════
# Part constructors
# ══════════════════════════════════════════════════════════════════════════════

class TestPartConstructors(unittest.TestCase):

    def test_make_text_part(self):
        p = relay._make_text_part("hello")
        self.assertEqual(p["type"], "text")
        self.assertEqual(p["content"], "hello")

    def test_make_file_part_minimal(self):
        p = relay._make_file_part("https://example.com/f.pdf")
        self.assertEqual(p["type"], "file")
        self.assertEqual(p["url"], "https://example.com/f.pdf")
        self.assertEqual(p["media_type"], "application/octet-stream")
        self.assertNotIn("filename", p)

    def test_make_file_part_with_filename(self):
        p = relay._make_file_part("https://x.com/img.png", "image/png", "img.png")
        self.assertEqual(p["media_type"], "image/png")
        self.assertEqual(p["filename"], "img.png")

    def test_make_data_part(self):
        data = {"invoice_id": 42, "amount": 9.99}
        p = relay._make_data_part(data)
        self.assertEqual(p["type"], "data")
        self.assertEqual(p["content"], data)


# ══════════════════════════════════════════════════════════════════════════════
# _validate_part() / _validate_parts()
# ══════════════════════════════════════════════════════════════════════════════

class TestValidatePart(unittest.TestCase):

    # ── valid parts ──────────────────────────────────────────────────────────

    def test_valid_text_part(self):
        ok, err = relay._validate_part({"type": "text", "content": "hi"})
        self.assertTrue(ok)
        self.assertEqual(err, "")

    def test_valid_file_part(self):
        ok, err = relay._validate_part({"type": "file", "url": "https://x.com/f.txt"})
        self.assertTrue(ok)

    def test_valid_data_part(self):
        ok, err = relay._validate_part({"type": "data", "content": {"key": "val"}})
        self.assertTrue(ok)

    def test_valid_data_part_null_content(self):
        # content=None is allowed (caller's choice)
        ok, err = relay._validate_part({"type": "data", "content": None})
        self.assertTrue(ok)

    # ── invalid parts ────────────────────────────────────────────────────────

    def test_text_part_missing_content(self):
        ok, err = relay._validate_part({"type": "text"})
        self.assertFalse(ok)
        self.assertIn("content", err)

    def test_text_part_non_string_content(self):
        ok, err = relay._validate_part({"type": "text", "content": 42})
        self.assertFalse(ok)

    def test_file_part_missing_url(self):
        ok, err = relay._validate_part({"type": "file"})
        self.assertFalse(ok)
        self.assertIn("url", err)

    def test_data_part_missing_content_key(self):
        ok, err = relay._validate_part({"type": "data"})
        self.assertFalse(ok)

    def test_unknown_type(self):
        ok, err = relay._validate_part({"type": "audio"})
        self.assertFalse(ok)
        self.assertIn("audio", err)

    def test_missing_type(self):
        ok, err = relay._validate_part({"content": "x"})
        self.assertFalse(ok)


class TestValidateParts(unittest.TestCase):

    def test_valid_list(self):
        parts = [
            {"type": "text", "content": "hello"},
            {"type": "data", "content": {}},
        ]
        ok, err = relay._validate_parts(parts)
        self.assertTrue(ok)

    def test_empty_list(self):
        ok, err = relay._validate_parts([])
        self.assertFalse(ok)
        self.assertIn("non-empty", err)

    def test_none_list(self):
        ok, err = relay._validate_parts(None)
        self.assertFalse(ok)

    def test_error_includes_index(self):
        parts = [
            {"type": "text", "content": "ok"},
            {"type": "text"},   # bad
        ]
        ok, err = relay._validate_parts(parts)
        self.assertFalse(ok)
        self.assertIn("parts[1]", err)

    def test_single_valid_part(self):
        ok, err = relay._validate_parts([{"type": "text", "content": "x"}])
        self.assertTrue(ok)


# ══════════════════════════════════════════════════════════════════════════════
# HMAC signing / verification
# ══════════════════════════════════════════════════════════════════════════════

class TestHMACHelpers(unittest.TestCase):

    def setUp(self):
        # Save and set secret
        self._orig_secret = relay._hmac_secret
        relay._hmac_secret = b"test-secret-key-32chars-padding!"

    def tearDown(self):
        relay._hmac_secret = self._orig_secret

    def test_sign_returns_hex_string(self):
        sig = relay._hmac_sign("msg_abc", "2026-03-21T10:00:00Z")
        self.assertIsInstance(sig, str)
        # hex string: 64 chars for SHA-256
        self.assertEqual(len(sig), 64)
        # valid hex
        int(sig, 16)

    def test_sign_deterministic(self):
        sig1 = relay._hmac_sign("msg_abc", "2026-03-21T10:00:00Z")
        sig2 = relay._hmac_sign("msg_abc", "2026-03-21T10:00:00Z")
        self.assertEqual(sig1, sig2)

    def test_sign_different_for_different_inputs(self):
        sig1 = relay._hmac_sign("msg_abc", "2026-03-21T10:00:00Z")
        sig2 = relay._hmac_sign("msg_xyz", "2026-03-21T10:00:00Z")
        self.assertNotEqual(sig1, sig2)

    def test_verify_correct_sig(self):
        ts = "2026-03-21T10:00:00Z"
        sig = relay._hmac_sign("msg_123", ts)
        self.assertTrue(relay._hmac_verify("msg_123", ts, sig))

    def test_verify_tampered_sig(self):
        ts = "2026-03-21T10:00:00Z"
        sig = relay._hmac_sign("msg_123", ts)
        bad_sig = sig[:-4] + "dead"  # corrupt last 4 chars
        self.assertFalse(relay._hmac_verify("msg_123", ts, bad_sig))

    def test_verify_tampered_message_id(self):
        ts = "2026-03-21T10:00:00Z"
        sig = relay._hmac_sign("msg_123", ts)
        self.assertFalse(relay._hmac_verify("msg_456", ts, sig))

    def test_verify_tampered_timestamp(self):
        sig = relay._hmac_sign("msg_123", "2026-03-21T10:00:00Z")
        self.assertFalse(relay._hmac_verify("msg_123", "2026-03-21T10:00:01Z", sig))

    def test_verify_no_secret_always_true(self):
        """When no secret is set, all messages are accepted (graceful interop)."""
        relay._hmac_secret = None
        result = relay._hmac_verify("msg_xxx", "ts_xxx", "any_sig_value")
        self.assertTrue(result)

    def test_sign_matches_manual_hmac(self):
        """Cross-check with manual stdlib HMAC computation."""
        msg_id = "msg_verify_me"
        ts     = "2026-03-21T12:00:00Z"
        payload = f"{msg_id}:{ts}".encode()
        expected = hmac.new(b"test-secret-key-32chars-padding!",
                            payload, hashlib.sha256).hexdigest()
        self.assertEqual(relay._hmac_sign(msg_id, ts), expected)


class TestHMACReplayWindow(unittest.TestCase):
    """Tests for v1.1 _hmac_check_replay_window()."""

    def setUp(self):
        self._orig_window = relay._HMAC_REPLAY_WINDOW
        relay._HMAC_REPLAY_WINDOW = 300  # reset to default

    def tearDown(self):
        relay._HMAC_REPLAY_WINDOW = self._orig_window

    def _ts_offset(self, delta_seconds: int) -> str:
        """Return an ISO-8601 UTC timestamp offset by delta_seconds from now."""
        import datetime
        t = datetime.datetime.utcnow() + datetime.timedelta(seconds=delta_seconds)
        return t.strftime("%Y-%m-%dT%H:%M:%SZ")

    def test_within_window_ok(self):
        ts = self._ts_offset(0)   # now
        ok, reason = relay._hmac_check_replay_window(ts)
        self.assertTrue(ok, reason)

    def test_slightly_past_ok(self):
        ts = self._ts_offset(-60)  # 1 minute ago
        ok, reason = relay._hmac_check_replay_window(ts)
        self.assertTrue(ok, reason)

    def test_slightly_future_ok(self):
        ts = self._ts_offset(+60)  # 1 minute in future (clock skew)
        ok, reason = relay._hmac_check_replay_window(ts)
        self.assertTrue(ok, reason)

    def test_too_old_rejected(self):
        ts = self._ts_offset(-400)  # 400 seconds ago > 300 window
        ok, reason = relay._hmac_check_replay_window(ts)
        self.assertFalse(ok)
        self.assertIn("outside replay-window", reason)

    def test_too_future_rejected(self):
        ts = self._ts_offset(+400)  # 400 seconds in future
        ok, reason = relay._hmac_check_replay_window(ts)
        self.assertFalse(ok)

    def test_missing_ts_rejected(self):
        ok, reason = relay._hmac_check_replay_window("")
        self.assertFalse(ok)
        self.assertIn("missing ts", reason)

    def test_none_ts_rejected(self):
        # None is coerced to "" by the caller in production code, but test directly
        ok, reason = relay._hmac_check_replay_window(None)
        self.assertFalse(ok)

    def test_invalid_ts_rejected(self):
        ok, reason = relay._hmac_check_replay_window("not-a-timestamp")
        self.assertFalse(ok)
        self.assertIn("unparseable ts", reason)

    def test_custom_window_honored(self):
        relay._HMAC_REPLAY_WINDOW = 10  # very tight
        ts = self._ts_offset(-15)  # 15 s ago > 10 s window
        ok, reason = relay._hmac_check_replay_window(ts)
        self.assertFalse(ok)

    def test_custom_window_within(self):
        relay._HMAC_REPLAY_WINDOW = 600  # 10 minutes
        ts = self._ts_offset(-400)  # 400 s ago, within 600 s window
        ok, reason = relay._hmac_check_replay_window(ts)
        self.assertTrue(ok, reason)


# ══════════════════════════════════════════════════════════════════════════════
# Task state constants
# ══════════════════════════════════════════════════════════════════════════════

class TestTaskStateConstants(unittest.TestCase):

    def test_state_values(self):
        self.assertEqual(relay.TASK_SUBMITTED,      "submitted")
        self.assertEqual(relay.TASK_WORKING,        "working")
        self.assertEqual(relay.TASK_COMPLETED,      "completed")
        self.assertEqual(relay.TASK_FAILED,         "failed")
        self.assertEqual(relay.TASK_INPUT_REQUIRED, "input_required")

    def test_terminal_states(self):
        self.assertIn(relay.TASK_COMPLETED, relay.TERMINAL_STATES)
        self.assertIn(relay.TASK_FAILED,    relay.TERMINAL_STATES)
        self.assertNotIn(relay.TASK_SUBMITTED,      relay.TERMINAL_STATES)
        self.assertNotIn(relay.TASK_WORKING,        relay.TERMINAL_STATES)
        self.assertNotIn(relay.TASK_INPUT_REQUIRED, relay.TERMINAL_STATES)

    def test_interrupted_states(self):
        self.assertIn(relay.TASK_INPUT_REQUIRED, relay.INTERRUPTED_STATES)
        self.assertNotIn(relay.TASK_COMPLETED,   relay.INTERRUPTED_STATES)

    def test_terminal_and_interrupted_disjoint(self):
        self.assertEqual(relay.TERMINAL_STATES & relay.INTERRUPTED_STATES, set())

    def test_five_states_total(self):
        all_states = {
            relay.TASK_SUBMITTED, relay.TASK_WORKING,
            relay.TASK_COMPLETED, relay.TASK_FAILED,
            relay.TASK_INPUT_REQUIRED,
        }
        self.assertEqual(len(all_states), 5)


# ══════════════════════════════════════════════════════════════════════════════
# _load_config_file() — JSON and YAML config file parser
# ══════════════════════════════════════════════════════════════════════════════

class TestLoadConfigFile(unittest.TestCase):

    def _write(self, content, suffix=".json"):
        f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
        f.write(content)
        f.flush()
        f.close()
        return f.name

    # ── JSON ─────────────────────────────────────────────────────────────────

    def test_json_basic(self):
        path = self._write('{"name": "TestAgent", "port": 9000}')
        cfg = relay._load_config_file(path)
        self.assertEqual(cfg["name"], "TestAgent")
        self.assertEqual(cfg["port"], 9000)
        os.unlink(path)

    def test_json_bool_values(self):
        path = self._write('{"verbose": true, "relay": false}')
        cfg = relay._load_config_file(path)
        self.assertTrue(cfg["verbose"])
        self.assertFalse(cfg["relay"])
        os.unlink(path)

    def test_json_all_supported_keys(self):
        data = {
            "name": "A", "port": 7801, "join": None, "relay": False,
            "relay-url": "https://x.com", "skills": "s1,s2",
            "inbox": "/tmp/x.jsonl", "max-msg-size": 2048,
            "secret": "key", "advertise-mdns": False,
            "identity": "~/.acp/id.json", "verbose": True
        }
        path = self._write(json.dumps(data))
        cfg = relay._load_config_file(path)
        self.assertEqual(cfg["name"], "A")
        self.assertEqual(cfg["relay-url"], "https://x.com")
        os.unlink(path)

    # ── YAML ─────────────────────────────────────────────────────────────────

    def test_yaml_basic(self):
        path = self._write("name: YAMLAgent\nport: 8080\n", suffix=".yaml")
        cfg = relay._load_config_file(path)
        self.assertEqual(cfg["name"], "YAMLAgent")
        self.assertEqual(cfg["port"], 8080)
        os.unlink(path)

    def test_yaml_bool_true_variants(self):
        path = self._write("verbose: true\nrelay: yes\n", suffix=".yaml")
        cfg = relay._load_config_file(path)
        self.assertTrue(cfg["verbose"])
        self.assertTrue(cfg["relay"])
        os.unlink(path)

    def test_yaml_bool_false_variants(self):
        path = self._write("verbose: false\nrelay: no\n", suffix=".yaml")
        cfg = relay._load_config_file(path)
        self.assertFalse(cfg["verbose"])
        self.assertFalse(cfg["relay"])
        os.unlink(path)

    def test_yaml_ignores_comments(self):
        content = "# this is a comment\nname: AgentX\n# another comment\nport: 7777\n"
        path = self._write(content, suffix=".yaml")
        cfg = relay._load_config_file(path)
        self.assertEqual(cfg["name"], "AgentX")
        self.assertEqual(cfg["port"], 7777)
        self.assertNotIn("# this is a comment", cfg)
        os.unlink(path)

    def test_yaml_string_with_colon_in_value(self):
        path = self._write("relay-url: https://relay.example.com\n", suffix=".yaml")
        cfg = relay._load_config_file(path)
        self.assertEqual(cfg["relay-url"], "https://relay.example.com")
        os.unlink(path)

    # ── Error handling ────────────────────────────────────────────────────────

    def test_missing_file_exits(self):
        with self.assertRaises(SystemExit):
            relay._load_config_file("/tmp/definitely_does_not_exist_acp_test.json")

    def test_empty_json_returns_empty_dict(self):
        path = self._write("{}")
        cfg = relay._load_config_file(path)
        self.assertEqual(cfg, {})
        os.unlink(path)

    def test_empty_yaml_returns_empty_dict(self):
        path = self._write("# just comments\n", suffix=".yaml")
        cfg = relay._load_config_file(path)
        self.assertEqual(cfg, {})
        os.unlink(path)


# ══════════════════════════════════════════════════════════════════════════════
# parse_link() — acp:// link parser
# ══════════════════════════════════════════════════════════════════════════════

class TestParseLink(unittest.TestCase):
    """
    parse_link() returns (host, port, token, scheme).

    Scheme values:
      "ws"         — standard acp:// link (P2P WebSocket; auto-fallback to relay)
      "http_relay" — acp+wss:// or acp+ws:// direct relay link
    """

    def test_p2p_link_scheme_is_ws(self):
        host, port, token, scheme = relay.parse_link("acp://1.2.3.4:7801/tok_abc123")
        self.assertEqual(host, "1.2.3.4")
        self.assertEqual(port, 7801)
        self.assertEqual(token, "tok_abc123")
        self.assertEqual(scheme, "ws")   # standard link → ws (auto-selects P2P or relay)

    def test_wss_relay_link_scheme_is_http_relay(self):
        host, port, token, scheme = relay.parse_link(
            "acp+wss://relay.example.com/acp/tok_xyz"
        )
        self.assertEqual(scheme, "http_relay")
        self.assertEqual(token, "tok_xyz")

    def test_ws_relay_link_scheme_is_http_relay(self):
        host, port, token, scheme = relay.parse_link(
            "acp+ws://relay.example.com/acp/tok_xyz"
        )
        self.assertEqual(scheme, "http_relay")
        self.assertEqual(token, "tok_xyz")

    def test_localhost_link(self):
        host, port, token, scheme = relay.parse_link("acp://127.0.0.1:7801/tok_test")
        self.assertEqual(host, "127.0.0.1")
        self.assertEqual(port, 7801)
        self.assertEqual(token, "tok_test")
        self.assertEqual(scheme, "ws")

    def test_default_port_when_absent(self):
        host, port, token, scheme = relay.parse_link("acp://myhost/tok_noport")
        self.assertEqual(host, "myhost")
        self.assertEqual(port, 7801)   # default port


# ══════════════════════════════════════════════════════════════════════════════
# VERSION constant
# ══════════════════════════════════════════════════════════════════════════════

class TestVersion(unittest.TestCase):

    def test_version_is_string(self):
        self.assertIsInstance(relay.VERSION, str)

    def test_version_not_empty(self):
        self.assertTrue(len(relay.VERSION) > 0)

    def test_version_starts_with_digit(self):
        self.assertTrue(relay.VERSION[0].isdigit(),
                        f"VERSION '{relay.VERSION}' should start with a digit")


# ══════════════════════════════════════════════════════════════════════════════
# AgentCard availability block (v1.2)
# ══════════════════════════════════════════════════════════════════════════════

class TestAgentCardAvailability(unittest.TestCase):
    """Tests for v1.2 _availability block in _make_agent_card()."""

    def setUp(self):
        self._orig_availability = relay._availability
        self._orig_started      = relay._status.get("started_at")
        relay._status["started_at"] = 1774137600.0  # 2026-03-22T08:00:00+08 = 2026-03-22T00:00:00Z UTC

    def tearDown(self):
        relay._availability = self._orig_availability
        relay._status["started_at"] = self._orig_started

    def test_no_availability_block_by_default(self):
        relay._availability = {}
        card = relay._make_agent_card("test-agent", [])
        self.assertNotIn("availability", card)

    def test_capability_flag_false_when_no_availability(self):
        relay._availability = {}
        card = relay._make_agent_card("test-agent", [])
        self.assertFalse(card["capabilities"]["availability"])

    def test_availability_block_present_when_configured(self):
        relay._availability = {"mode": "heartbeat", "interval_seconds": 3600}
        card = relay._make_agent_card("test-agent", [])
        self.assertIn("availability", card)
        self.assertEqual(card["availability"]["mode"], "heartbeat")
        self.assertEqual(card["availability"]["interval_seconds"], 3600)

    def test_capability_flag_true_when_configured(self):
        relay._availability = {"mode": "cron", "interval_seconds": 7200}
        card = relay._make_agent_card("test-agent", [])
        self.assertTrue(card["capabilities"]["availability"])

    def test_last_active_at_auto_stamped(self):
        relay._availability = {"mode": "heartbeat"}
        card = relay._make_agent_card("test-agent", [])
        # started_at=1742601600.0 → 2026-03-22T00:00:00Z
        self.assertEqual(card["availability"]["last_active_at"], "2026-03-22T00:00:00Z")

    def test_last_active_at_not_overridden_if_explicit(self):
        relay._availability = {"mode": "heartbeat", "last_active_at": "2026-03-21T12:00:00Z"}
        card = relay._make_agent_card("test-agent", [])
        self.assertEqual(card["availability"]["last_active_at"], "2026-03-21T12:00:00Z")

    def test_next_active_at_preserved(self):
        relay._availability = {"mode": "heartbeat", "next_active_at": "2026-03-22T07:00:00Z"}
        card = relay._make_agent_card("test-agent", [])
        self.assertEqual(card["availability"]["next_active_at"], "2026-03-22T07:00:00Z")

    def test_availability_is_copy_not_reference(self):
        """Mutations to card['availability'] must not affect _availability global."""
        relay._availability = {"mode": "cron", "interval_seconds": 1800}
        card = relay._make_agent_card("test-agent", [])
        card["availability"]["mode"] = "MUTATED"
        self.assertEqual(relay._availability["mode"], "cron")

    def test_persistent_mode_stored_cleanly(self):
        relay._availability = {"mode": "persistent"}
        card = relay._make_agent_card("test-agent", [])
        self.assertIn("availability", card)
        self.assertEqual(card["availability"]["mode"], "persistent")

    def test_task_latency_field_accepted(self):
        relay._availability = {"mode": "heartbeat",
                               "interval_seconds": 3600,
                               "task_latency_max_seconds": 3600}
        card = relay._make_agent_card("test-agent", [])
        self.assertEqual(card["availability"]["task_latency_max_seconds"], 3600)


if __name__ == "__main__":
    unittest.main(verbosity=2)
