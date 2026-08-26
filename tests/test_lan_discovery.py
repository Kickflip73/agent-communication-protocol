"""
ACP v2.1 — LAN Port-Scan Discovery Tests (LD1–LD10)

Tests for GET /peers/discover endpoint and _lan_port_scan() internals.
"""
import sys
import os
import json
import time
import socket
import threading
import unittest
from unittest.mock import patch, MagicMock
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "relay"))
import acp_relay as relay


# ─────────────────────────────────────────────────────────────────────────────
# Helpers: minimal ACP-look-alike HTTP server for probing tests
# ─────────────────────────────────────────────────────────────────────────────

_MOCK_AGENT_CARD = {
    "name": "TestAgent-Scanner",
    "version": "2.1",
    "token": "tok_scan_test",
    "ws_port": 7801,
    "http_port": 7901,
    "capabilities": {"lan_port_scan": True},
    "endpoints": {"peers_discover": "/peers/discover"},
}


class _MockACPServer(BaseHTTPRequestHandler):
    """Minimal HTTP server that serves /.well-known/acp.json."""

    def do_GET(self):
        if self.path == "/.well-known/acp.json":
            body = json.dumps({"self": _MOCK_AGENT_CARD}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass  # Suppress test output


def _start_mock_acp_server():
    """Start a mock ACP server on a free port. Returns (server, port, thread)."""
    srv = HTTPServer(("127.0.0.1", 0), _MockACPServer)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, port, t


def _free_port():
    """Return an OS-assigned free port (closed immediately)."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestTCPOpen(unittest.TestCase):
    """LD1–LD2: _tcp_open() unit tests."""

    def test_LD1_open_port_returns_true(self):
        """LD1: _tcp_open returns True when port is open."""
        srv, port, _ = _start_mock_acp_server()
        try:
            self.assertTrue(relay._tcp_open("127.0.0.1", port, timeout=1.0))
        finally:
            srv.shutdown()

    def test_LD2_closed_port_returns_false(self):
        """LD2: _tcp_open returns False when port is closed."""
        port = _free_port()  # immediately closed
        self.assertFalse(relay._tcp_open("127.0.0.1", port, timeout=0.2))


class TestProbeACP(unittest.TestCase):
    """LD3–LD4: _probe_acp() unit tests."""

    def test_LD3_real_acp_server_returns_card(self):
        """LD3: _probe_acp returns card dict for a real ACP server."""
        srv, port, _ = _start_mock_acp_server()
        try:
            result = relay._probe_acp("127.0.0.1", port, timeout=2.0)
            self.assertIsNotNone(result)
            self.assertIn("self", result)
            self.assertEqual(result["self"]["name"], "TestAgent-Scanner")
        finally:
            srv.shutdown()

    def test_LD4_non_acp_server_returns_none(self):
        """LD4: _probe_acp returns None for a non-ACP HTTP server."""

        class _PlainHTTP(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"not json")
            def log_message(self, *a): pass

        srv = HTTPServer(("127.0.0.1", 0), _PlainHTTP)
        port = srv.server_address[1]
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            result = relay._probe_acp("127.0.0.1", port, timeout=1.0)
            self.assertIsNone(result)
        finally:
            srv.shutdown()


class TestGetLanIP(unittest.TestCase):
    """LD5: _get_lan_ip() returns a plausible IP or None."""

    def test_LD5_returns_string_or_none(self):
        """LD5: _get_lan_ip returns a dotted-quad string or None."""
        ip = relay._get_lan_ip()
        if ip is not None:
            parts = ip.split(".")
            self.assertEqual(len(parts), 4, f"Expected dotted-quad, got: {ip}")
            for p in parts:
                self.assertTrue(p.isdigit())


class TestLanPortScan(unittest.TestCase):
    """LD6–LD9: _lan_port_scan() integration-style tests."""

    def test_LD6_finds_mock_server_on_loopback(self):
        """LD6: _lan_port_scan finds an ACP relay on 127.x subnet (localhost probe)."""
        srv, port, _ = _start_mock_acp_server()
        try:
            result = relay._lan_port_scan(
                subnet="127.0.0",
                ports=[port],
                max_workers=8,
            )
            self.assertIsNone(result["error"])
            names = [r["name"] for r in result["found"]]
            self.assertIn("TestAgent-Scanner", names)
            self.assertGreater(result["duration_ms"], 0)
        finally:
            srv.shutdown()

    def test_LD7_no_hosts_found_on_empty_subnet(self):
        """LD7: _lan_port_scan on a non-routable subnet returns empty found list."""
        closed_port = _free_port()  # immediately closed
        result = relay._lan_port_scan(
            subnet="198.51.100",  # TEST-NET-2 — RFC5737, never routed
            ports=[closed_port],
            max_workers=16,
        )
        self.assertIsNone(result["error"])
        self.assertEqual(result["found"], [])
        self.assertGreater(result["scanned_hosts"], 0)

    def test_LD8_bad_ip_returns_error(self):
        """LD8: _lan_port_scan returns error when LAN IP is unavailable."""
        with patch.object(relay, "_get_lan_ip", return_value=None):
            result = relay._lan_port_scan(subnet=None)
        self.assertIsNotNone(result["error"])
        self.assertEqual(result["found"], [])

    def test_LD9_result_schema(self):
        """LD9: _lan_port_scan result always has required keys."""
        result = relay._lan_port_scan(
            subnet="198.51.100",
            ports=[_free_port()],
            max_workers=4,
        )
        required_keys = ["found", "scanned_hosts", "scanned_ports", "subnet", "duration_ms", "error"]
        for key in required_keys:
            self.assertIn(key, result, f"Missing key: {key}")
        self.assertIsInstance(result["found"], list)
        self.assertIsInstance(result["scanned_hosts"], int)
        self.assertIsInstance(result["scanned_ports"], int)


class TestPeersDiscoverEndpoint(unittest.TestCase):
    """LD10: GET /peers/discover HTTP endpoint smoke test."""

    def test_LD10_endpoint_returns_valid_json(self):
        """LD10: GET /peers/discover on a running relay returns valid scan result."""
        import urllib.request
        import urllib.error

        # Start a target ACP mock server
        target_srv, target_port, _ = _start_mock_acp_server()

        # Start the real ACP relay on a different port
        relay_http_port = _free_port()
        relay_ws_port   = _free_port()

        relay._status["http_port"] = relay_http_port
        relay._status["ws_port"]   = relay_ws_port
        relay._status["agent_name"] = "ScannerRelay"
        relay._status["agent_card"]  = {}

        server = relay.ThreadingHTTPServer(("127.0.0.1", relay_http_port), relay.LocalHTTP)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        time.sleep(0.05)

        try:
            url = (
                f"http://127.0.0.1:{relay_http_port}/peers/discover"
                f"?subnet=127.0.0&ports={target_port}&workers=4"
            )
            with urllib.request.urlopen(url, timeout=8) as resp:
                body = json.loads(resp.read())

            self.assertIn("found", body)
            self.assertIn("scanned_hosts", body)
            self.assertIn("scanned_ports", body)
            self.assertIn("duration_ms", body)
            self.assertIn("total_found", body)
            self.assertIsInstance(body["found"], list)

            # Should have found our mock target
            names = [r.get("name") for r in body["found"]]
            self.assertIn("TestAgent-Scanner", names, f"Scan result: {body}")

        finally:
            server.shutdown()
            target_srv.shutdown()


if __name__ == "__main__":
    unittest.main(verbosity=2)
