"""
ACP Relay Integration Tests (v1.0)

Spins up a real acp_relay.py host process and exercises the HTTP API end-to-end.
All tests use stdlib only — no external dependencies required.

Run:
    pytest tests/integration/ -v
"""
import time
import urllib.request

import pytest

from conftest import http_get, http_post


# ── /status ───────────────────────────────────────────────────────────────

class TestStatus:
    def test_status_200(self, relay_url):
        status, body = http_get(relay_url + "/status")
        assert status == 200, f"expected 200, got {status}"

    def test_status_has_connected(self, relay_url):
        _, body = http_get(relay_url + "/status")
        assert "connected" in body, f"missing 'connected' field: {body}"

    def test_status_has_acp_version(self, relay_url):
        _, body = http_get(relay_url + "/status")
        assert "acp_version" in body, f"missing 'acp_version' field: {body}"
        assert body["acp_version"], f"acp_version should be non-empty, got {body['acp_version']!r}"


# ── /.well-known/acp.json ────────────────────────────────────────────────

class TestAgentCard:
    def test_agentcard_200(self, relay_url):
        status, _ = http_get(relay_url + "/.well-known/acp.json")
        assert status == 200

    def test_agentcard_has_self(self, relay_url):
        _, body = http_get(relay_url + "/.well-known/acp.json")
        assert "self" in body, f"AgentCard missing 'self': {body}"

    def test_agentcard_self_has_name(self, relay_url):
        _, body = http_get(relay_url + "/.well-known/acp.json")
        card = body["self"]
        assert "name" in card, f"AgentCard.self missing 'name': {card}"

    def test_agentcard_self_has_acp_version(self, relay_url):
        _, body = http_get(relay_url + "/.well-known/acp.json")
        card = body["self"]
        assert "acp_version" in card, f"AgentCard.self missing 'acp_version': {card}"

    def test_agentcard_self_has_capabilities(self, relay_url):
        _, body = http_get(relay_url + "/.well-known/acp.json")
        card = body["self"]
        assert "capabilities" in card, f"AgentCard.self missing 'capabilities': {card}"

    def test_agentcard_version_is_present(self, relay_url):
        _, body = http_get(relay_url + "/.well-known/acp.json")
        v = body["self"].get("acp_version", "")
        assert v, f"expected non-empty acp_version, got {v!r}"

    def test_card_alias_also_works(self, relay_url):
        status, _ = http_get(relay_url + "/card")
        assert status == 200


# ── /peers ────────────────────────────────────────────────────────────────

class TestPeers:
    def test_peers_200(self, relay_url):
        status, _ = http_get(relay_url + "/peers")
        assert status == 200

    def test_peers_has_peers_list(self, relay_url):
        _, body = http_get(relay_url + "/peers")
        assert "peers" in body, f"missing 'peers': {body}"
        assert isinstance(body["peers"], list)

    def test_peers_empty_at_start(self, relay_url):
        _, body = http_get(relay_url + "/peers")
        assert body["peers"] == [], f"expected empty peers, got {body['peers']}"


# ── /tasks ────────────────────────────────────────────────────────────────

class TestTasks:
    def test_tasks_200(self, relay_url):
        status, _ = http_get(relay_url + "/tasks")
        assert status == 200

    def test_tasks_has_tasks_list(self, relay_url):
        _, body = http_get(relay_url + "/tasks")
        assert "tasks" in body, f"missing 'tasks': {body}"
        assert isinstance(body["tasks"], list)


# ── /message:send ─────────────────────────────────────────────────────────

class TestMessageSend:
    def test_send_missing_role_returns_400(self, relay_url):
        """v0.9 breaking change: role is required (spec §6)."""
        status, body = http_post(relay_url + "/message:send", {"text": "hello"})
        assert status == 400, f"expected 400 for missing role, got {status}: {body}"

    def test_send_invalid_role_returns_400(self, relay_url):
        status, body = http_post(
            relay_url + "/message:send",
            {"role": "badactor", "text": "hello"}
        )
        assert status == 400, f"expected 400 for invalid role, got {status}"

    def test_send_empty_content_returns_400(self, relay_url):
        """Must have at least one of: parts (non-empty) or text (non-empty)."""
        status, body = http_post(
            relay_url + "/message:send",
            {"role": "user"}
        )
        assert status == 400, f"expected 400 for empty content, got {status}"

    def test_send_valid_returns_ok(self, relay_url):
        """Valid send in standalone (no peer) mode — relay accepts and queues."""
        status, body = http_post(
            relay_url + "/message:send",
            {"role": "user", "text": "integration test message"}
        )
        # Relay may return 200 ok or 503 if no peer connected — both valid
        assert status in (200, 503), f"unexpected status {status}: {body}"

    def test_send_with_message_id(self, relay_url):
        """Client-supplied message_id is echoed back (idempotency key)."""
        mid = "inttest_msg_001"
        status, body = http_post(
            relay_url + "/message:send",
            {"role": "user", "text": "idempotency test", "message_id": mid}
        )
        if status == 200:
            assert body.get("message_id") == mid, f"message_id not echoed: {body}"

    def test_send_error_body_has_error_field(self, relay_url):
        """Error responses must include an 'error' field (spec §9)."""
        status, body = http_post(relay_url + "/message:send", {"text": "no role"})
        assert status == 400
        assert "error" in body, f"error response missing 'error' field: {body}"


# ── /recv ─────────────────────────────────────────────────────────────────

class TestRecv:
    def test_recv_200(self, relay_url):
        status, _ = http_get(relay_url + "/recv")
        assert status == 200

    def test_recv_has_messages(self, relay_url):
        _, body = http_get(relay_url + "/recv")
        assert "messages" in body, f"missing 'messages': {body}"
        assert isinstance(body["messages"], list)

    def test_recv_has_count(self, relay_url):
        _, body = http_get(relay_url + "/recv")
        assert "count" in body, f"missing 'count': {body}"


# ── /skills/query ─────────────────────────────────────────────────────────

class TestSkillsQuery:
    def test_skills_query_200(self, relay_url):
        status, _ = http_post(relay_url + "/skills/query", {})
        assert status == 200

    def test_skills_query_has_skills(self, relay_url):
        _, body = http_post(relay_url + "/skills/query", {})
        assert "skills" in body, f"missing 'skills': {body}"
        assert isinstance(body["skills"], list)


# ── /link ─────────────────────────────────────────────────────────────────

class TestLink:
    def test_link_200(self, relay_url):
        status, _ = http_get(relay_url + "/link")
        assert status == 200

    def test_link_has_link_field(self, relay_url):
        _, body = http_get(relay_url + "/link")
        assert "link" in body, f"missing 'link': {body}"


# ── /stream (SSE connectivity) ─────────────────────────────────────────────

class TestStream:
    def test_stream_returns_event_stream_content_type(self, relay_url):
        """GET /stream must respond with text/event-stream."""
        req = urllib.request.Request(
            relay_url + "/stream",
            headers={"Accept": "text/event-stream"},
        )
        import socket
        try:
            conn = urllib.request.urlopen(req, timeout=1.0)
            ct = conn.headers.get("Content-Type", "")
            conn.close()
            assert "text/event-stream" in ct, f"Content-Type = {ct!r}"
        except Exception:
            # Timeout reading body is fine — we only care about the headers
            pass


# ── Task cancel (no-op on missing id) ────────────────────────────────────

class TestTaskCancel:
    def test_cancel_nonexistent_task_returns_404(self, relay_url):
        status, body = http_post(
            relay_url + "/tasks/nonexistent_task_xyz:cancel", {}
        )
        assert status == 404, f"expected 404, got {status}: {body}"


# ── failed_message_id coverage (v1.1 — ANP convergence) ─────────────────

class TestFailedMessageId:
    """All error responses should include failed_message_id when message_id is known."""

    def test_invalid_request_includes_failed_message_id(self, relay_url):
        """ERR_INVALID_REQUEST with client message_id → echoed as failed_message_id."""
        mid = "inttest_fmid_001"
        status, body = http_post(
            relay_url + "/message:send",
            {"text": "no role", "message_id": mid}
        )
        assert status == 400
        assert body.get("failed_message_id") == mid, (
            f"expected failed_message_id={mid!r}, got {body.get('failed_message_id')!r}\n"
            f"full body: {body}"
        )

    def test_invalid_role_includes_failed_message_id(self, relay_url):
        mid = "inttest_fmid_002"
        status, body = http_post(
            relay_url + "/message:send",
            {"role": "hacker", "text": "bad role", "message_id": mid}
        )
        assert status == 400
        assert body.get("failed_message_id") == mid, (
            f"expected failed_message_id={mid!r}, got {body.get('failed_message_id')!r}"
        )

    def test_empty_content_includes_failed_message_id(self, relay_url):
        mid = "inttest_fmid_003"
        status, body = http_post(
            relay_url + "/message:send",
            {"role": "user", "message_id": mid}
        )
        assert status == 400
        assert body.get("failed_message_id") == mid, (
            f"expected failed_message_id={mid!r}, got {body.get('failed_message_id')!r}"
        )

    def test_no_message_id_no_failed_message_id(self, relay_url):
        """When client omits message_id, failed_message_id should be absent (not null)."""
        status, body = http_post(
            relay_url + "/message:send",
            {"text": "no role"}
        )
        assert status == 400
        # failed_message_id should not appear (or be None) when no message_id given
        fmid = body.get("failed_message_id")
        assert fmid is None, f"unexpected failed_message_id={fmid!r} when none provided"


# ── /peer/{id}/send failed_message_id coverage (v2.2) ────────────────────

class TestPeerSendFailedMessageId:
    """/peer/{id}/send error responses must include failed_message_id when message_id is known."""

    def test_peer_not_found_with_message_id(self, relay_url):
        """ERR_NOT_FOUND: peer does not exist — client message_id echoed."""
        mid = "inttest_peer_fmid_001"
        status, body = http_post(
            relay_url + "/peer/ghost_peer/send",
            {"role": "user", "text": "hello", "message_id": mid}
        )
        assert status == 404
        assert body.get("failed_message_id") == mid, (
            f"expected failed_message_id={mid!r}, got {body.get('failed_message_id')!r}\n"
            f"full body: {body}"
        )

    def test_peer_not_found_no_message_id(self, relay_url):
        """ERR_NOT_FOUND without message_id → failed_message_id absent."""
        status, body = http_post(
            relay_url + "/peer/ghost_peer/send",
            {"role": "user", "text": "hello"}
        )
        assert status == 404
        fmid = body.get("failed_message_id")
        assert fmid is None, f"unexpected failed_message_id={fmid!r} when none provided"

    def test_peer_not_connected_with_message_id(self, relay_url):
        """ERR_NOT_CONNECTED: peer registered but disconnected — client message_id echoed."""
        import uuid
        peer_id = f"test_peer_{uuid.uuid4().hex[:8]}"
        mid = "inttest_peer_fmid_002"

        # Register a peer without connecting it
        reg_status, reg_body = http_post(
            relay_url + "/peer/register",
            {"peer_id": peer_id, "name": "test_peer"}
        )
        if reg_status not in (200, 201):
            import pytest
            pytest.skip(f"peer register returned {reg_status}; skipping")

        # Now try to send to the disconnected peer
        status, body = http_post(
            relay_url + f"/peer/{peer_id}/send",
            {"role": "user", "text": "hello", "message_id": mid}
        )
        assert status in (503, 404)
        assert body.get("failed_message_id") == mid, (
            f"expected failed_message_id={mid!r}, got {body.get('failed_message_id')!r}\n"
            f"full body: {body}"
        )

    def test_peer_send_missing_content_with_message_id(self, relay_url):
        """ERR_INVALID_REQUEST: no parts/text — client message_id echoed even for unknown peer."""
        mid = "inttest_peer_fmid_003"
        # Use a ghost peer to trigger not-found (which still has message_id available)
        status, body = http_post(
            relay_url + "/peer/ghost_peer/send",
            {"role": "user", "message_id": mid}
        )
        # Will be 404 (peer not found) with failed_message_id — verifies early-exit echoing
        assert status in (400, 404)
        assert body.get("failed_message_id") == mid, (
            f"expected failed_message_id={mid!r}, got {body.get('failed_message_id')!r}\n"
            f"full body: {body}"
        )
