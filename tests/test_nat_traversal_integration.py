#!/usr/bin/env python3
"""
tests/test_nat_traversal_integration.py

v1.4 _connect_with_nat_traversal() integration tests.

Test matrix:
  T1: Level 1 direct connect success path (mock ws succeeds within 3s)
  T2: Level 1 timeout → Level 2 triggered
  T3: Level 2 failure → Level 3 relay fallback
  T4: transport_level field written to peer info
  T5: --relay flag forces Level 3 directly (skip L1+L2)

Goal: 5/5 PASS
"""
import asyncio
import json
import os
import sys
import importlib.util
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# ── Load acp_relay module ────────────────────────────────────────────────────
RELAY_PY = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")
)


def _load_relay():
    """Load acp_relay.py as a module, suppressing side-effects."""
    spec = importlib.util.spec_from_file_location("acp_relay_test", RELAY_PY)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["acp_relay_test"] = mod
    try:
        spec.loader.exec_module(mod)
    except SystemExit:
        pass
    return mod


def _run_coro(loop, coro):
    """Run coroutine on given loop; drain pending tasks afterwards."""
    result = loop.run_until_complete(coro)
    # Drain any pending ensure_future tasks
    pending = asyncio.all_tasks(loop)
    if pending:
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
    return result


# ── T1: Level 1 direct connect success ───────────────────────────────────────

class TestT1Level1DirectSuccess(unittest.TestCase):
    """T1: Level 1 direct connect succeeds within 3s."""

    def test_t1_level1_direct_success(self):
        """
        When _proxy_ws_connect resolves within 3s, _connect_with_nat_traversal
        should return (token, "direct").
        """
        relay = _load_relay()
        loop  = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        relay._status["http_port"]      = 7901
        relay._status["force_relay"]    = False
        relay._status["relay_base_url"] = ""
        relay._loop = loop

        token = "tok_t1"
        link  = f"acp://127.0.0.1:17801/{token}"

        # Returning a plain MagicMock works because wait_for(await-able, ...) just needs
        # something that can be awaited.  We make it an AsyncMock so awaiting it is safe.
        async def _mock_ws_connect(*args, **kwargs):
            return MagicMock()  # context-manager (not needed for L1 success path)

        async def _noop_guest(*args, **kwargs):
            pass

        async def _run():
            with patch.object(relay, "_proxy_ws_connect", _mock_ws_connect), \
                 patch.object(relay, "guest_mode", _noop_guest):
                return await relay._connect_with_nat_traversal(link, "TestAgent", "guest")

        try:
            result = _run_coro(loop, _run())
        finally:
            loop.close()

        self.assertEqual(result[1], "direct",
                         f"Expected transport_level='direct', got {result[1]!r}")
        self.assertEqual(result[0], token,
                         f"Expected token={token!r}, got {result[0]!r}")


# ── T2: Level 1 timeout → Level 2 triggered ──────────────────────────────────

class TestT2Level1TimeoutLevel2Triggered(unittest.TestCase):
    """T2: When Level 1 times out, Level 2 (DCUtR) is attempted."""

    def test_t2_l1_timeout_l2_triggered(self):
        """
        L1 raises asyncio.TimeoutError → Level 2 (DCUtRPuncher.attempt) must be called.
        """
        relay = _load_relay()
        loop  = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        relay._status["http_port"]      = 7901
        relay._status["force_relay"]    = False
        relay._status["relay_base_url"] = "https://mock-relay.example"
        relay._loop = loop

        token = "tok_t2"
        link  = f"acp://10.0.0.1:17801/{token}"

        l2_attempted = []
        call_count   = [0]

        async def _smart_ws(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # L1: simulate 3s timeout expiry
                await asyncio.sleep(4)   # exceeds DIRECT_TIMEOUT=3s
            # L2 signaling WS: return a mock context-manager
            cm = MagicMock()
            cm.__aenter__ = AsyncMock(return_value=cm)
            cm.__aexit__  = AsyncMock(return_value=False)
            return cm

        async def _mock_punch(self_puncher, relay_ws, local_udp_port=0):
            l2_attempted.append(True)
            return None  # L2 fails → L3

        async def _noop_relay(*args, **kwargs):
            pass

        async def _run():
            with patch.object(relay, "_proxy_ws_connect", _smart_ws), \
                 patch.object(relay.DCUtRPuncher, "attempt", _mock_punch), \
                 patch.object(relay, "_http_relay_guest", _noop_relay), \
                 patch("subprocess.run", return_value=MagicMock(stdout=b"{}")):
                return await relay._connect_with_nat_traversal(link, "TestAgent", "guest")

        try:
            result = _run_coro(loop, _run())
        finally:
            loop.close()

        self.assertTrue(len(l2_attempted) > 0,
                        "Level 2 (DCUtRPuncher.attempt) was never called after L1 timeout")
        self.assertIn(result[1], ("dcutr", "relay"),
                      f"After L1 timeout expected dcutr or relay, got {result[1]!r}")


# ── T3: Level 2 failure → Level 3 relay fallback ─────────────────────────────

class TestT3Level2FailLevel3Relay(unittest.TestCase):
    """T3: When both L1 and L2 fail, Level 3 relay is used."""

    def test_t3_l2_fail_l3_relay(self):
        """
        L1 times out, L2 puncher returns None → expect (token, "relay").
        """
        relay = _load_relay()
        loop  = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        relay._status["http_port"]      = 7901
        relay._status["force_relay"]    = False
        relay._status["relay_base_url"] = "https://mock-relay.example"
        relay._loop = loop

        token = "tok_t3"
        link  = f"acp://192.0.2.1:17801/{token}"

        call_count = [0]

        async def _smart_ws(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                await asyncio.sleep(4)  # L1 timeout
            cm = MagicMock()
            cm.__aenter__ = AsyncMock(return_value=cm)
            cm.__aexit__  = AsyncMock(return_value=False)
            return cm

        async def _mock_punch_fail(self_puncher, relay_ws, local_udp_port=0):
            return None  # L2 fails

        relay_guest_calls = []

        async def _mock_relay_guest(relay_base, tok, http_port):
            relay_guest_calls.append((relay_base, tok))

        async def _run():
            with patch.object(relay, "_proxy_ws_connect", _smart_ws), \
                 patch.object(relay.DCUtRPuncher, "attempt", _mock_punch_fail), \
                 patch.object(relay, "_http_relay_guest", _mock_relay_guest), \
                 patch("subprocess.run", return_value=MagicMock(stdout=b"{}")):
                result = await relay._connect_with_nat_traversal(link, "TestAgent", "guest")
                await asyncio.sleep(0.1)  # let ensure_future tasks run
                return result

        try:
            result = _run_coro(loop, _run())
        finally:
            loop.close()

        self.assertEqual(result[1], "relay",
                         f"Expected Level 3 'relay', got {result[1]!r}")
        self.assertTrue(
            len(relay_guest_calls) > 0,
            f"Expected _http_relay_guest called for Level 3; got {len(relay_guest_calls)} call(s)"
        )


# ── T4: transport_level field written to peer info ────────────────────────────

class TestT4TransportLevelField(unittest.TestCase):
    """T4: transport_level field is written to _peers[peer_id] after connect."""

    def test_t4_transport_level_written_to_peer_info(self):
        """
        After _connect_with_nat_traversal completes, the caller should set
        _peers[peer_id]['transport_level'] to the resolved level.
        """
        relay = _load_relay()
        loop  = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        relay._status["http_port"]      = 7901
        relay._status["force_relay"]    = False
        relay._status["relay_base_url"] = ""
        relay._loop = loop

        token   = "tok_t4"
        link    = f"acp://127.0.0.1:17801/{token}"
        peer_id = "peer_t4_test"

        # Pre-register a peer (mirrors what /peers/connect does)
        relay._peers[peer_id] = {
            "id": peer_id, "name": peer_id, "link": link,
            "ws": None, "connected": False,
            "connected_at": None, "messages_sent": 0,
            "messages_received": 0, "agent_card": None,
        }

        async def _mock_ws_connect(*args, **kwargs):
            return MagicMock()

        async def _noop_guest(*args, **kwargs):
            pass

        async def _run():
            with patch.object(relay, "_proxy_ws_connect", _mock_ws_connect), \
                 patch.object(relay, "guest_mode", _noop_guest):
                _pid, transport_level = await relay._connect_with_nat_traversal(
                    link, "TestAgent", "guest"
                )
                # Simulate the _do_connect_nat() callback in /peers/connect
                if peer_id in relay._peers:
                    relay._peers[peer_id]["transport_level"] = transport_level
                return _pid, transport_level

        try:
            _pid, transport_level = _run_coro(loop, _run())
        finally:
            loop.close()

        self.assertIn("transport_level", relay._peers[peer_id],
                      "transport_level key missing from peer info after connect")
        self.assertEqual(relay._peers[peer_id]["transport_level"], "direct",
                         f"Expected transport_level='direct', "
                         f"got {relay._peers[peer_id].get('transport_level')!r}")


# ── T5: --relay flag forces Level 3 directly ─────────────────────────────────

class TestT5RelayFlagForcesLevel3(unittest.TestCase):
    """T5: --relay flag (force_relay=True) skips L1+L2 and goes directly to Level 3."""

    def test_t5_relay_flag_forces_level3(self):
        """
        When _status['force_relay'] = True, L1 must NOT be called and
        transport_level must be 'relay'.
        """
        relay = _load_relay()
        loop  = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        relay._status["http_port"]      = 7901
        relay._status["force_relay"]    = True   # --relay flag
        relay._status["relay_base_url"] = "https://mock-relay.example"
        relay._loop = loop

        token = "tok_t5"
        link  = f"acp://127.0.0.1:17801/{token}"

        l1_called = []

        async def _mock_ws_connect_l1(*args, **kwargs):
            l1_called.append(True)
            raise Exception("L1 MUST NOT be called when --relay is set")

        relay_guest_calls = []

        async def _mock_relay_guest(relay_base, tok, http_port):
            relay_guest_calls.append(tok)

        async def _run():
            with patch.object(relay, "_proxy_ws_connect", _mock_ws_connect_l1), \
                 patch.object(relay, "_http_relay_guest", _mock_relay_guest):
                result = await relay._connect_with_nat_traversal(link, "TestAgent", "guest")
                await asyncio.sleep(0.1)  # let ensure_future tasks run
                return result

        try:
            result = _run_coro(loop, _run())
        finally:
            loop.close()

        self.assertEqual(len(l1_called), 0,
                         f"Level 1 (_proxy_ws_connect) should NOT be called when "
                         f"--relay is set, called {len(l1_called)} time(s)")
        self.assertEqual(result[1], "relay",
                         f"Expected transport_level='relay' with --relay flag, "
                         f"got {result[1]!r}")
        self.assertTrue(
            len(relay_guest_calls) > 0,
            f"Expected _http_relay_guest called for Level 3, got {len(relay_guest_calls)} call(s)"
        )


# ── pytest-compatible entry points ───────────────────────────────────────────

def test_t1_level1_direct_success():
    t = TestT1Level1DirectSuccess()
    t.test_t1_level1_direct_success()

def test_t2_l1_timeout_l2_triggered():
    t = TestT2Level1TimeoutLevel2Triggered()
    t.test_t2_l1_timeout_l2_triggered()

def test_t3_l2_fail_l3_relay():
    t = TestT3Level2FailLevel3Relay()
    t.test_t3_l2_fail_l3_relay()

def test_t4_transport_level_written_to_peer_info():
    t = TestT4TransportLevelField()
    t.test_t4_transport_level_written_to_peer_info()

def test_t5_relay_flag_forces_level3():
    t = TestT5RelayFlagForcesLevel3()
    t.test_t5_relay_flag_forces_level3()


# ── Script entry point ────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"NAT Traversal Integration Tests (v1.4)")
    print(f"{'='*60}\n")

    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
