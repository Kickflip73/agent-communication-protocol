#!/usr/bin/env python3
"""
tests/test_nat_signaling.py

Unit tests for NAT traversal HTTP signaling helpers (v1.4):
  _relay_get_public_ip()
  _relay_announce()
  _relay_get_peer_addr()

Uses a local mock HTTP server to simulate the Cloudflare Worker
/acp/myip, /acp/announce, /acp/peer endpoints (no network required).

Run: python3 tests/test_nat_signaling.py
     pytest tests/test_nat_signaling.py
"""

import json
import os
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

# ── Import helpers from relay ──────────────────────────────────────────────
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from relay.acp_relay import _relay_get_public_ip, _relay_announce, _relay_get_peer_addr
from helpers import clean_subprocess_env

# ── Shared announce store for mock server ─────────────────────────────────
_MOCK_STORE: dict = {}  # token → {ip, port, nat_type, ts}

MOCK_HOST = "127.0.0.1"
MOCK_PORT = 19876


class MockWorkerHandler(BaseHTTPRequestHandler):
    """Minimal mock of Cloudflare Worker v2.1 NAT signaling endpoints."""

    def log_message(self, fmt, *args):
        pass  # suppress access logs in tests

    def _json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == "/acp/myip":
            self._json({"ip": "203.0.113.42", "ts": int(time.time() * 1000)})

        elif path == "/acp/peer":
            token = (params.get("token") or [""])[0]
            if not token:
                self._json({"error": "token required"}, 400)
                return
            record = _MOCK_STORE.pop(token, None)
            if record is None:
                self._json({"error": "peer not found or expired", "token": token}, 404)
            else:
                self._json({"ok": True, "token": token, **record,
                            "fetched_at": int(time.time() * 1000)})
        else:
            self._json({"error": "not_found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(body)
        except Exception:
            self._json({"error": "invalid json"}, 400)
            return

        if self.path == "/acp/announce":
            token = data.get("token")
            ip = data.get("ip")
            port = data.get("port")
            if not (token and ip and port):
                self._json({"error": "token, ip, port required"}, 400)
                return
            _MOCK_STORE[token] = {
                "ip": str(ip), "port": int(port),
                "nat_type": str(data.get("nat_type", "unknown")),
                "ts": int(time.time() * 1000),
            }
            self._json({"ok": True, "token": token, "expires_in": 30})
        else:
            self._json({"error": "not_found"}, 404)


def start_mock_server():
    server = HTTPServer((MOCK_HOST, MOCK_PORT), MockWorkerHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


# ── Test helpers ──────────────────────────────────────────────────────────
_results = []

def ok(name, passed, note=""):
    sym = "✅" if passed else "❌"
    _results.append((name, passed, note))
    print(f"  {sym} {name}" + (f" — {note}" if note else ""))


BASE_URL = f"http://{MOCK_HOST}:{MOCK_PORT}"


def run_tests():
    _MOCK_STORE.clear()
    print("=" * 55)
    print("ACP NAT Signaling Helper Tests (v1.4)")
    print("=" * 55)

    # ── T1: _relay_get_public_ip ──────────────────────────────────────────
    print("\n[T1] _relay_get_public_ip()")
    ip = _relay_get_public_ip(BASE_URL, timeout=3.0)
    ok("T1-1 returns non-None", ip is not None, f"ip={ip}")
    ok("T1-2 returns valid IP string", isinstance(ip, str) and len(ip) > 0, f"ip={ip!r}")
    ok("T1-3 returns expected mock IP", ip == "203.0.113.42", f"got={ip!r}")

    # ── T2: _relay_announce ───────────────────────────────────────────────
    print("\n[T2] _relay_announce()")
    result = _relay_announce(BASE_URL, token="tok_test001",
                             ip="203.0.113.42", port=7801,
                             nat_type="full_cone", timeout=3.0)
    ok("T2-1 announce returns True", result is True, f"result={result}")
    ok("T2-2 record stored in mock", "tok_test001" in _MOCK_STORE,
       f"store_keys={list(_MOCK_STORE.keys())}")
    stored = _MOCK_STORE.get("tok_test001", {})
    ok("T2-3 stored ip matches", stored.get("ip") == "203.0.113.42",
       f"stored_ip={stored.get('ip')!r}")
    ok("T2-4 stored port matches", stored.get("port") == 7801,
       f"stored_port={stored.get('port')}")
    ok("T2-5 stored nat_type matches", stored.get("nat_type") == "full_cone",
       f"stored_nat={stored.get('nat_type')!r}")

    # ── T3: _relay_get_peer_addr ──────────────────────────────────────────
    print("\n[T3] _relay_get_peer_addr()")
    # Ensure record exists (T2 may have populated it; re-insert to be safe)
    _MOCK_STORE["tok_test001"] = {"ip": "203.0.113.42", "port": 7801,
                                   "nat_type": "full_cone",
                                   "ts": int(time.time() * 1000)}
    peer = _relay_get_peer_addr(BASE_URL, token="tok_test001", timeout=3.0)
    ok("T3-1 returns non-None", peer is not None, f"peer={peer}")
    ok("T3-2 ip field present", peer is not None and "ip" in peer,
       f"keys={list(peer.keys()) if peer else 'None'}")
    ok("T3-3 ip value correct", peer is not None and peer.get("ip") == "203.0.113.42",
       f"ip={peer.get('ip') if peer else None!r}")
    ok("T3-4 port value correct", peer is not None and peer.get("port") == 7801,
       f"port={peer.get('port') if peer else None}")
    ok("T3-5 record deleted after fetch (one-time)", "tok_test001" not in _MOCK_STORE,
       f"store_after={list(_MOCK_STORE.keys())}")

    # ── T4: one-time fetch — second get returns None ──────────────────────
    print("\n[T4] One-time semantics (second fetch returns None)")
    peer2 = _relay_get_peer_addr(BASE_URL, token="tok_test001", timeout=3.0)
    ok("T4-1 second fetch returns None", peer2 is None, f"peer2={peer2}")

    # ── T5: error handling ────────────────────────────────────────────────
    print("\n[T5] Error / edge case handling")

    # announce with missing fields
    result_bad = _relay_announce(BASE_URL, token="", ip="1.2.3.4",
                                 port=7801, timeout=3.0)
    ok("T5-1 announce empty token → False", result_bad is False,
       f"result={result_bad}")

    # get_public_ip with unreachable server
    ip_bad = _relay_get_public_ip("http://127.0.0.1:19999", timeout=0.3)
    ok("T5-2 myip unreachable → None", ip_bad is None, f"ip_bad={ip_bad}")

    # get_peer_addr for nonexistent token
    peer_none = _relay_get_peer_addr(BASE_URL, token="tok_nonexistent", timeout=3.0)
    ok("T5-3 peer not found → None", peer_none is None, f"peer_none={peer_none}")

    # ── T6: roundtrip (announce → get_peer) ──────────────────────────────
    print("\n[T6] Full announce→fetch roundtrip")
    tok = "tok_roundtrip_xyz"
    ann = _relay_announce(BASE_URL, token=tok, ip="10.0.0.5",
                          port=9999, nat_type="restricted", timeout=3.0)
    ok("T6-1 announce succeeds", ann is True)
    fetched = _relay_get_peer_addr(BASE_URL, token=tok, timeout=3.0)
    ok("T6-2 fetch returns data", fetched is not None)
    ok("T6-3 ip roundtrips correctly",
       fetched is not None and fetched.get("ip") == "10.0.0.5",
       f"ip={fetched.get('ip') if fetched else None}")
    ok("T6-4 port roundtrips correctly",
       fetched is not None and fetched.get("port") == 9999,
       f"port={fetched.get('port') if fetched else None}")
    ok("T6-5 nat_type roundtrips",
       fetched is not None and fetched.get("nat_type") == "restricted",
       f"nat_type={fetched.get('nat_type') if fetched else None}")

    # ── Summary ───────────────────────────────────────────────────────────
    passed = sum(1 for _, p, _ in _results if p)
    total  = len(_results)
    print(f"\n{'='*55}")
    print(f"NAT Signaling Tests: {passed}/{total} PASS"
          + (" ✅" if passed == total else ""))
    if passed < total:
        print("FAIL 項：")
        for name, p, note in _results:
            if not p:
                print(f"  ❌ {name}" + (f" — {note}" if note else ""))
    print("=" * 55)
    return passed == total


def test_nat_signaling():
    """pytest entry point."""
    server = start_mock_server()
    time.sleep(0.1)
    try:
        assert run_tests(), "NAT signaling tests failed"
    finally:
        server.shutdown()


if __name__ == "__main__":
    server = start_mock_server()
    time.sleep(0.1)
    ok_all = run_tests()
    server.shutdown()
    sys.exit(0 if ok_all else 1)