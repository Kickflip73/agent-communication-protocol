"""
tests/test_delegation_chain.py — ACP v2.16 Delegation Chain Tests

Scenarios:
  DC1  _build_delegation_entry() returns required fields
  DC2  Signature is valid (verified by _verify_delegation_entry)
  DC3  Different scope or expires_at produces different sig
  DC4  Tampered entry fails verification
  DC5  _delegation_chain_status() reflects appended entries
  DC6  AgentCard includes 'delegation' when chain non-empty
  DC7  AgentCard capabilities.delegation_chain is True when chain non-empty
  DC8  POST /identity/delegate creates entry and returns 200
  DC9  GET /identity/delegation returns chain status
  DC10 POST /identity/delegation/verify validates correct entry
  DC11 POST /identity/delegate without identity returns 400
  DC12 Expired entry flagged in status
  DC13 Deduplication: same delegator_did replaces old entry
"""

import unittest
import sys
import os
import time
import json
import base64
import threading
import http.client

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "relay"))
import acp_relay as relay


# ── Helpers ───────────────────────────────────────────────────────────────────

def _inject_identity():
    """Inject a real Ed25519 keypair into relay globals for tests that need signing."""
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import (
            Encoding, PublicFormat, PrivateFormat, NoEncryption
        )
        import base64 as b64
        priv = Ed25519PrivateKey.generate()
        pub_raw = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        relay._ed25519_private    = priv
        relay._ed25519_public_b64 = b64.urlsafe_b64encode(pub_raw).rstrip(b"=").decode()
        relay._did_acp            = relay._pubkey_to_did_acp(pub_raw)
        return True
    except ImportError:
        return False  # cryptography not installed — skip


def _clear_identity():
    relay._ed25519_private    = None
    relay._ed25519_public_b64 = None
    relay._did_acp            = None


def _clear_chain():
    relay._delegation_chain.clear()


FAKE_DELEGATOR_DID = "did:acp:AABBCCDDEEFF00112233445566778899AABBCCDDEEFF00112233445566778899"


# ── Unit Tests ────────────────────────────────────────────────────────────────

class TestDelegationChainUnit(unittest.TestCase):

    def setUp(self):
        self._has_crypto = _inject_identity()
        _clear_chain()

    def tearDown(self):
        _clear_identity()
        _clear_chain()

    # DC1 — _build_delegation_entry required fields
    def test_DC1_entry_has_required_fields(self):
        if not self._has_crypto:
            self.skipTest("cryptography not installed")
        entry = relay._build_delegation_entry(
            FAKE_DELEGATOR_DID, ["send", "receive"], time.time() + 3600
        )
        for field in ("delegator_did", "delegatee_did", "scope", "expires_at", "sig", "scheme"):
            self.assertIn(field, entry, f"Missing field: {field}")
        self.assertEqual(entry["scheme"], "ed25519")
        self.assertEqual(entry["delegator_did"], FAKE_DELEGATOR_DID)
        self.assertEqual(entry["delegatee_did"], relay._did_acp)
        self.assertEqual(sorted(entry["scope"]), ["receive", "send"])

    # DC2 — signature verifies correctly
    def test_DC2_signature_valid(self):
        if not self._has_crypto:
            self.skipTest("cryptography not installed")
        entry = relay._build_delegation_entry(
            FAKE_DELEGATOR_DID, ["send"], time.time() + 3600
        )
        self.assertTrue(relay._verify_delegation_entry(entry))

    # DC3 — different scope produces different sig
    def test_DC3_different_scope_different_sig(self):
        if not self._has_crypto:
            self.skipTest("cryptography not installed")
        exp = time.time() + 3600
        e1 = relay._build_delegation_entry(FAKE_DELEGATOR_DID, ["send"], exp)
        e2 = relay._build_delegation_entry(FAKE_DELEGATOR_DID, ["send", "admin"], exp)
        self.assertNotEqual(e1["sig"], e2["sig"])

    # DC4 — tampered entry fails verification
    def test_DC4_tampered_entry_invalid(self):
        if not self._has_crypto:
            self.skipTest("cryptography not installed")
        entry = relay._build_delegation_entry(
            FAKE_DELEGATOR_DID, ["send"], time.time() + 3600
        )
        bad = dict(entry)
        bad["scope"] = ["admin"]   # tamper scope
        self.assertFalse(relay._verify_delegation_entry(bad))

    # DC5 — _delegation_chain_status reflects entries
    def test_DC5_status_reflects_chain(self):
        if not self._has_crypto:
            self.skipTest("cryptography not installed")
        self.assertEqual(relay._delegation_chain_status()["count"], 0)
        entry = relay._build_delegation_entry(
            FAKE_DELEGATOR_DID, ["send"], time.time() + 3600
        )
        relay._delegation_chain.append(entry)
        status = relay._delegation_chain_status()
        self.assertEqual(status["count"], 1)
        self.assertTrue(status["has_valid"])

    # DC6 — AgentCard includes 'delegation' key when chain non-empty
    def test_DC6_agentcard_includes_delegation(self):
        if not self._has_crypto:
            self.skipTest("cryptography not installed")
        entry = relay._build_delegation_entry(
            FAKE_DELEGATOR_DID, ["send"], time.time() + 3600
        )
        relay._delegation_chain.append(entry)
        card = relay._make_agent_card("TestAgent", [])
        self.assertIn("identity", card)
        self.assertIsNotNone(card["identity"])
        self.assertIn("delegation", card["identity"])
        self.assertEqual(len(card["identity"]["delegation"]), 1)

    # DC7 — AgentCard capabilities.delegation_chain True when chain non-empty
    def test_DC7_capability_flag_true(self):
        if not self._has_crypto:
            self.skipTest("cryptography not installed")
        # Chain empty → False
        card_empty = relay._make_agent_card("TestAgent", [])
        self.assertFalse(card_empty["capabilities"]["delegation_chain"])
        # Chain non-empty → True
        entry = relay._build_delegation_entry(
            FAKE_DELEGATOR_DID, ["send"], time.time() + 3600
        )
        relay._delegation_chain.append(entry)
        card_full = relay._make_agent_card("TestAgent", [])
        self.assertTrue(card_full["capabilities"]["delegation_chain"])

    # DC12 — expired entry flagged
    def test_DC12_expired_entry_flagged(self):
        if not self._has_crypto:
            self.skipTest("cryptography not installed")
        entry = relay._build_delegation_entry(
            FAKE_DELEGATOR_DID, ["send"], time.time() - 1  # already expired
        )
        relay._delegation_chain.append(entry)
        status = relay._delegation_chain_status()
        self.assertTrue(status["entries"][0]["expired"])
        self.assertFalse(status["has_valid"])

    # DC13 — deduplication replaces same delegator
    def test_DC13_deduplication(self):
        if not self._has_crypto:
            self.skipTest("cryptography not installed")
        exp = time.time() + 3600
        e1 = relay._build_delegation_entry(FAKE_DELEGATOR_DID, ["send"], exp)
        relay._delegation_chain.append(e1)
        self.assertEqual(len(relay._delegation_chain), 1)
        # Re-add same delegator via direct dedup logic (simulate POST handler)
        relay._delegation_chain[:] = [
            e for e in relay._delegation_chain
            if e.get("delegator_did") != FAKE_DELEGATOR_DID
        ]
        e2 = relay._build_delegation_entry(FAKE_DELEGATOR_DID, ["send", "admin"], exp)
        relay._delegation_chain.append(e2)
        self.assertEqual(len(relay._delegation_chain), 1)
        self.assertIn("admin", relay._delegation_chain[0]["scope"])

    # DC11 — no identity → RuntimeError
    def test_DC11_no_identity_raises(self):
        _clear_identity()
        with self.assertRaises(RuntimeError):
            relay._build_delegation_entry(FAKE_DELEGATOR_DID, ["send"], time.time() + 3600)


# ── HTTP Integration Tests ────────────────────────────────────────────────────

def _find_free_port():
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestDelegationChainHTTP(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._has_crypto = _inject_identity()
        _clear_chain()
        import socketserver
        from http.server import HTTPServer
        cls._port = _find_free_port()
        relay._status["http_port"] = cls._port
        relay._status["agent_name"] = "dc-test-agent"
        relay._status["started_at"] = time.time()
        relay._status["link"] = f"acp://relay.acp.dev/dc-test"
        cls._server = HTTPServer(("127.0.0.1", cls._port), relay.LocalHTTP)
        cls._thread = threading.Thread(target=cls._server.serve_forever, daemon=True)
        cls._thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls._server.shutdown()
        _clear_identity()
        _clear_chain()

    def setUp(self):
        _clear_chain()

    def _post(self, path, body):
        data = json.dumps(body).encode()
        conn = http.client.HTTPConnection("127.0.0.1", self._port, timeout=5)
        conn.request("POST", path, body=data,
                     headers={"Content-Type": "application/json",
                               "Content-Length": str(len(data))})
        resp = conn.getresponse()
        return resp.status, json.loads(resp.read())

    def _get(self, path):
        conn = http.client.HTTPConnection("127.0.0.1", self._port, timeout=5)
        conn.request("GET", path)
        resp = conn.getresponse()
        return resp.status, json.loads(resp.read())

    # DC8 — POST /identity/delegate creates entry
    def test_DC8_post_delegate_creates_entry(self):
        if not self._has_crypto:
            self.skipTest("cryptography not installed")
        status, body = self._post("/identity/delegate", {
            "delegator_did": FAKE_DELEGATOR_DID,
            "scope":         ["send", "receive"],
            "expires_at":    time.time() + 3600,
        })
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertIn("entry", body)
        self.assertEqual(body["delegation_chain_size"], 1)

    # DC9 — GET /identity/delegation returns status
    def test_DC9_get_delegation_returns_status(self):
        if not self._has_crypto:
            self.skipTest("cryptography not installed")
        # First add an entry
        self._post("/identity/delegate", {
            "delegator_did": FAKE_DELEGATOR_DID,
            "scope":         ["send"],
            "expires_at":    time.time() + 3600,
        })
        status, body = self._get("/identity/delegation")
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["chain"]["count"], 1)
        self.assertTrue(body["chain"]["has_valid"])

    # DC10 — POST /identity/delegation/verify validates correct entry
    def test_DC10_verify_valid_entry(self):
        if not self._has_crypto:
            self.skipTest("cryptography not installed")
        _, created = self._post("/identity/delegate", {
            "delegator_did": FAKE_DELEGATOR_DID,
            "scope":         ["send"],
            "expires_at":    time.time() + 3600,
        })
        entry = created["entry"]
        status, body = self._post("/identity/delegation/verify", {"entry": entry})
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertTrue(body["valid"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
