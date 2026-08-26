"""
Tests for AsyncRelayClient — stdlib-only async HTTP client (v0.9).

These tests use unittest.mock to patch urllib calls, so no running relay
is needed. They verify:
  - correct URL construction for all endpoints
  - correct request bodies (message_id, context_id, task_id, parts, etc.)
  - async context manager protocol (__aenter__ / __aexit__)
  - wait_for_task terminal-state detection
  - wait_for_peer polling
  - query_skills parameter passing
"""
import asyncio
import json
import sys
import unittest
from unittest.mock import MagicMock, patch, AsyncMock

sys.path.insert(0, ".")
from acp_sdk.relay_client import AsyncRelayClient


# ── Helper to run async tests ──────────────────────────────────────────

def run(coro):
    return asyncio.run(coro)


# ── Fixtures ────────────────────────────────────────────────────────────

BASE = "http://localhost:7901"


def make_client():
    return AsyncRelayClient(BASE, timeout=5.0)


def mock_get_response(payload: dict):
    """Patch _http_get to return payload."""
    return patch(
        "acp_sdk.relay_client._http_get",
        return_value=payload,
    )


def mock_post_response(payload: dict):
    """Patch _http_post to return payload."""
    return patch(
        "acp_sdk.relay_client._http_post",
        return_value=payload,
    )


# ── Context manager ──────────────────────────────────────────────────────

class TestContextManager(unittest.TestCase):
    def test_context_manager_returns_self(self):
        async def go():
            async with AsyncRelayClient(BASE) as c:
                self.assertIsInstance(c, AsyncRelayClient)
        run(go())

    def test_close_is_noop(self):
        async def go():
            c = AsyncRelayClient(BASE)
            await c.close()  # should not raise
        run(go())


# ── Status & discovery ────────────────────────────────────────────────────

class TestStatus(unittest.TestCase):
    def test_status_url(self):
        with mock_get_response({"connected": True}) as m:
            result = run(make_client().status())
        m.assert_called_once_with(f"{BASE}/status", 5.0)
        self.assertTrue(result["connected"])

    def test_card_url(self):
        with mock_get_response({"acp_version": "0.8"}) as m:
            run(make_client().card())
        m.assert_called_once_with(f"{BASE}/.well-known/acp.json", 5.0)

    def test_link_url(self):
        with mock_get_response({"link": "acp://1.2.3.4:7801/tok_abc"}) as m:
            link = run(make_client().link())
        self.assertEqual(link, "acp://1.2.3.4:7801/tok_abc")

    def test_discover_url(self):
        with mock_get_response({"peers": [{"name": "AgentB"}]}) as m:
            peers = run(make_client().discover())
        m.assert_called_once_with(f"{BASE}/discover", 5.0)
        self.assertEqual(len(peers), 1)

    def test_is_connected_true(self):
        with mock_get_response({"connected": True}):
            result = run(make_client().is_connected())
        self.assertTrue(result)

    def test_is_connected_false_on_error(self):
        with patch("acp_sdk.relay_client._http_get", side_effect=Exception("conn refused")):
            result = run(make_client().is_connected())
        self.assertFalse(result)


# ── Peer management ───────────────────────────────────────────────────────

class TestPeers(unittest.TestCase):
    def test_peers_url(self):
        with mock_get_response({"peers": []}) as m:
            run(make_client().peers())
        m.assert_called_once_with(f"{BASE}/peers", 5.0)

    def test_peer_url(self):
        with mock_get_response({"peer_id": "p1"}) as m:
            run(make_client().peer("p1"))
        m.assert_called_once_with(f"{BASE}/peer/p1", 5.0)

    def test_connect_peer(self):
        link = "acp://1.2.3.4:7801/tok_xyz"
        with mock_post_response({"ok": True}) as m:
            run(make_client().connect_peer(link))
        m.assert_called_once_with(f"{BASE}/peers/connect", {"link": link}, 5.0)


# ── Messaging ─────────────────────────────────────────────────────────────

class TestSend(unittest.TestCase):
    def test_send_text(self):
        with mock_post_response({"ok": True, "message_id": "msg_abc"}) as m:
            result = run(make_client().send("hello"))
        m.assert_called_once_with(
            f"{BASE}/message:send",
            {"role": "user", "text": "hello"},
            5.0,
        )
        self.assertEqual(result["message_id"], "msg_abc")

    def test_send_with_message_id(self):
        with mock_post_response({"ok": True}) as m:
            run(make_client().send("hi", message_id="msg_custom"))
        _, body, _ = m.call_args[0]
        self.assertEqual(body["message_id"], "msg_custom")

    def test_send_with_context_id(self):
        with mock_post_response({"ok": True}) as m:
            run(make_client().send("hi", context_id="ctx_123"))
        _, body, _ = m.call_args[0]
        self.assertEqual(body["context_id"], "ctx_123")

    def test_send_with_task_id(self):
        with mock_post_response({"ok": True}) as m:
            run(make_client().send("hi", task_id="task_abc"))
        _, body, _ = m.call_args[0]
        self.assertEqual(body["task_id"], "task_abc")

    def test_send_with_create_task(self):
        with mock_post_response({"ok": True}) as m:
            run(make_client().send("hi", create_task=True))
        _, body, _ = m.call_args[0]
        self.assertTrue(body["create_task"])

    def test_send_sync_mode(self):
        with mock_post_response({"ok": True, "reply": "done"}) as m:
            run(make_client().send("hi", sync=True, sync_timeout=15.0))
        _, body, _ = m.call_args[0]
        self.assertTrue(body["sync"])
        self.assertEqual(body["timeout"], 15)

    def test_send_parts(self):
        parts = [{"type": "text", "content": "hi"}, {"type": "data", "content": {"k": "v"}}]
        with mock_post_response({"ok": True}) as m:
            run(make_client().send(parts=parts))
        _, body, _ = m.call_args[0]
        self.assertEqual(body["parts"], parts)

    def test_send_no_content_raises(self):
        async def go():
            with self.assertRaises(ValueError):
                await make_client().send()
        run(go())

    def test_send_to_peer_all_fields(self):
        with mock_post_response({"ok": True}) as m:
            run(make_client().send_to_peer(
                "p1", "hi",
                context_id="ctx_x",
                task_id="task_y",
                message_id="msg_z",
            ))
        url, body, _ = m.call_args[0]
        self.assertIn("/peer/p1/send", url)
        self.assertEqual(body["context_id"], "ctx_x")
        self.assertEqual(body["task_id"], "task_y")
        self.assertEqual(body["message_id"], "msg_z")

    def test_recv(self):
        with mock_get_response({"messages": [{"type": "acp.message"}]}) as m:
            msgs = run(make_client().recv(limit=10))
        self.assertEqual(len(msgs), 1)
        self.assertIn("recv?limit=10", m.call_args[0][0])


# ── Tasks ─────────────────────────────────────────────────────────────────

class TestTasks(unittest.TestCase):
    def test_tasks_url(self):
        with mock_get_response({"tasks": []}) as m:
            run(make_client().tasks())
        m.assert_called_once_with(f"{BASE}/tasks", 5.0)

    def test_tasks_with_status_filter(self):
        with mock_get_response({"tasks": []}) as m:
            run(make_client().tasks(status="working"))
        self.assertIn("status=working", m.call_args[0][0])

    def test_get_task(self):
        with mock_get_response({"id": "task_1", "status": "working"}) as m:
            task = run(make_client().get_task("task_1"))
        m.assert_called_once_with(f"{BASE}/tasks/task_1", 5.0)
        self.assertEqual(task["status"], "working")

    def test_create_task(self):
        payload = {"description": "do something"}
        with mock_post_response({"ok": True, "task_id": "task_new"}) as m:
            run(make_client().create_task(payload, delegate=True))
        _, body, _ = m.call_args[0]
        self.assertEqual(body["payload"], payload)
        self.assertTrue(body["delegate"])

    def test_update_task_with_artifact(self):
        artifact = {"parts": [{"type": "text", "content": "result"}]}
        with mock_post_response({"ok": True}) as m:
            run(make_client().update_task("t1", "completed", artifact=artifact))
        url, body, _ = m.call_args[0]
        self.assertIn("t1", url)
        self.assertEqual(body["state"], "completed")
        self.assertEqual(body["artifact"], artifact)

    def test_continue_task(self):
        with mock_post_response({"ok": True}) as m:
            run(make_client().continue_task("t1", text="more info"))
        url, body, _ = m.call_args[0]
        self.assertIn("t1/continue", url)
        self.assertEqual(body["text"], "more info")

    def test_cancel_task(self):
        with mock_post_response({"ok": True}) as m:
            run(make_client().cancel_task("t1"))
        url, body, _ = m.call_args[0]
        self.assertIn("t1:cancel", url)

    def test_wait_for_task_immediate_terminal(self):
        with mock_get_response({"id": "t1", "status": "completed"}):
            task = run(make_client().wait_for_task("t1", timeout=5.0))
        self.assertEqual(task["status"], "completed")

    def test_wait_for_task_polls_until_done(self):
        results = [
            {"id": "t1", "status": "working"},
            {"id": "t1", "status": "working"},
            {"id": "t1", "status": "completed"},
        ]
        call_count = 0

        def fake_get(url, timeout):
            nonlocal call_count
            call_count += 1
            return results[min(call_count - 1, len(results) - 1)]

        with patch("acp_sdk.relay_client._http_get", side_effect=fake_get):
            task = run(make_client().wait_for_task("t1", timeout=5.0, poll_interval=0.01))
        self.assertEqual(task["status"], "completed")
        self.assertGreaterEqual(call_count, 3)


# ── Skills ────────────────────────────────────────────────────────────────

class TestQuerySkills(unittest.TestCase):
    def test_query_with_all_params(self):
        with mock_post_response({"ok": True, "skills": []}) as m:
            run(make_client().query_skills(
                query="summarize",
                skill_id="sk_1",
                capability="text",
                limit=5,
            ))
        _, body, _ = m.call_args[0]
        self.assertEqual(body["query"], "summarize")
        self.assertEqual(body["skill_id"], "sk_1")
        self.assertEqual(body["capability"], "text")
        self.assertEqual(body["limit"], 5)

    def test_query_empty_body(self):
        with mock_post_response({"ok": True, "skills": []}) as m:
            run(make_client().query_skills())
        _, body, _ = m.call_args[0]
        self.assertEqual(body, {})


# ── Wait for peer ─────────────────────────────────────────────────────────

class TestWaitForPeer(unittest.TestCase):
    def test_returns_true_when_connected(self):
        with mock_get_response({"connected": True}):
            result = run(make_client().wait_for_peer(timeout=2.0, poll_interval=0.01))
        self.assertTrue(result)

    def test_returns_false_on_timeout(self):
        with mock_get_response({"connected": False}):
            result = run(make_client().wait_for_peer(timeout=0.05, poll_interval=0.01))
        self.assertFalse(result)


# ── repr ──────────────────────────────────────────────────────────────────

class TestRepr(unittest.TestCase):
    def test_repr(self):
        c = AsyncRelayClient("http://localhost:7901")
        r = repr(c)
        self.assertIn("AsyncRelayClient", r)
        self.assertIn("localhost:7901", r)


if __name__ == "__main__":
    unittest.main(verbosity=2)
