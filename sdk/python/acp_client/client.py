"""
acp_client.client — Synchronous RelayClient for acp_relay.py.

Zero external dependencies — uses stdlib urllib only.

Wraps the acp_relay.py HTTP API:
  GET  /status              — relay status + AgentCard
  GET  /.well-known/acp.json — AgentCard
  GET  /link                — shareable acp:// link
  GET  /peers               — list connected peers
  GET  /peer/{id}           — single peer info
  POST /message:send        — send message to primary peer
  POST /peer/{id}/send      — send to specific peer
  GET  /recv                — poll received messages
  GET  /stream              — SSE event stream
  GET  /tasks               — list tasks (with filters)
  POST /tasks/create        — create / delegate task
  POST /tasks/{id}:update   — update task state
  POST /tasks/{id}:cancel   — cancel task
  POST /tasks/{id}/continue — resume input_required task
  POST /skills/query        — QuerySkill

Usage:
    from acp_client import RelayClient

    client = RelayClient("http://localhost:7901")
    resp = client.send("Hello from acp-client!")
    print(resp)

    for msg in client.recv():
        print(msg)
"""
from __future__ import annotations

import json
import time
import logging
import urllib.request
import urllib.error
from typing import Any, Dict, Generator, List, Optional

from .exceptions import (
    ACPError,
    ConnectionError as ACPConnectionError,
    PeerNotFoundError,
    TaskNotFoundError,
    TaskNotCancelableError,
    SendError,
    _raise_from_response,
)
from .models import AgentCard, Message, Task, TaskStatus

logger = logging.getLogger("acp_client")

# ─────────────────────────────────────────────────────────────
# Low-level HTTP helpers (stdlib only)
# ─────────────────────────────────────────────────────────────

def _http_get(url: str, timeout: float = 10.0) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        raise ACPConnectionError(f"GET {url} failed: {e}", url=url) from e


def _http_post(url: str, body: dict, timeout: float = 10.0) -> dict:
    data = json.dumps(body, ensure_ascii=False).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body_bytes = e.read()
        try:
            return json.loads(body_bytes.decode())
        except Exception:
            return {"ok": False, "error": f"HTTP {e.code}: {body_bytes.decode()[:200]}"}
    except urllib.error.URLError as e:
        raise ACPConnectionError(f"POST {url} failed: {e}", url=url) from e


# ─────────────────────────────────────────────────────────────
# RelayClient
# ─────────────────────────────────────────────────────────────

class RelayClient:
    """
    Synchronous HTTP client for acp_relay.py (acp-client v1.7).

    Zero external dependencies — uses stdlib urllib.

    Args:
        base_url: Relay HTTP endpoint (default: "http://localhost:7901").
        timeout:  Default request timeout in seconds (default: 10).

    Example:
        from acp_client import RelayClient

        client = RelayClient("http://localhost:7901")
        print(client.status())
        client.send("Hello!")
        for msg in client.recv():
            print(msg["text"])
    """

    def __init__(
        self,
        base_url: str = "http://localhost:7901",
        timeout: float = 10.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ── Status & Discovery ────────────────────────────────────────────────

    def status(self) -> dict:
        """Return relay status dict (version, connected, peer count, etc.)."""
        return _http_get(f"{self.base_url}/status", self.timeout)

    def card(self) -> AgentCard:
        """Return this node's AgentCard (.well-known/acp.json)."""
        raw = _http_get(f"{self.base_url}/.well-known/acp.json", self.timeout)
        return AgentCard.from_dict(raw)

    def card_raw(self) -> dict:
        """Return the raw AgentCard dict without parsing."""
        return _http_get(f"{self.base_url}/.well-known/acp.json", self.timeout)

    def link(self) -> str:
        """Return the acp:// link for this node (share with peers)."""
        data = _http_get(f"{self.base_url}/link", self.timeout)
        return data.get("link", "")

    def capabilities(self) -> dict:
        """Return the relay's declared capabilities dict."""
        try:
            raw = _http_get(f"{self.base_url}/.well-known/acp.json", self.timeout)
            return raw.get("capabilities", {})
        except Exception:
            return {}

    def supported_interfaces(self) -> List[str]:
        """Return supported interface groups (v2.5+)."""
        try:
            raw = _http_get(f"{self.base_url}/.well-known/acp.json", self.timeout)
            return list(raw.get("supported_interfaces", []))
        except Exception:
            return []

    def identity(self) -> dict:
        """Return the DID identity block (v1.3+)."""
        raw = _http_get(f"{self.base_url}/.well-known/acp.json", self.timeout)
        return raw.get("identity", {})

    def did_document(self) -> dict:
        """Return the W3C DID Document (v1.3+)."""
        return _http_get(f"{self.base_url}/.well-known/did.json", self.timeout)

    def is_connected(self) -> bool:
        """Return True if at least one peer is currently connected."""
        try:
            return bool(self.status().get("connected", False))
        except Exception:
            return False

    # ── Peer Management ───────────────────────────────────────────────────

    def peers(self) -> List[dict]:
        """List all connected peers."""
        data = _http_get(f"{self.base_url}/peers", self.timeout)
        return data.get("peers", [])

    def peer(self, peer_id: str) -> dict:
        """Get info for a specific peer."""
        return _http_get(f"{self.base_url}/peer/{peer_id}", self.timeout)

    def wait_for_peer(self, timeout: float = 30.0, poll_interval: float = 1.0) -> bool:
        """
        Block until a peer connects or timeout expires.

        Returns:
            True if a peer connected within the timeout window, False otherwise.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.is_connected():
                return True
            time.sleep(poll_interval)
        return False

    # ── Messaging ─────────────────────────────────────────────────────────

    def send(
        self,
        text: str = None,
        *,
        parts: List[dict] = None,
        role: str = "user",
        message_id: str = None,
    ) -> dict:
        """
        Send a message to the primary connected peer.

        Args:
            text:       Plain text content.
            parts:      Structured Part list (overrides ``text``).
            role:       Message role ("user" | "assistant"). Default "user".
            message_id: Client-assigned idempotency key.

        Returns:
            {"ok": True, "message_id": "msg_..."} on success.

        Raises:
            SendError: If the relay rejects the message.
            ValueError: If neither ``text`` nor ``parts`` is provided.
        """
        body: Dict[str, Any] = {"role": role}
        if message_id:
            body["message_id"] = message_id
        if parts:
            body["parts"] = parts
        elif text is not None:
            body["text"] = text
        else:
            raise ValueError("Provide either 'text' or 'parts'")

        resp = _http_post(f"{self.base_url}/message:send", body, self.timeout)
        if not resp.get("ok"):
            raise SendError(resp.get("error", "send failed"), response=resp)
        return resp

    def send_to_peer(
        self,
        peer_id: str,
        text: str = None,
        *,
        parts: List[dict] = None,
        role: str = "user",
        message_id: str = None,
    ) -> dict:
        """
        Send a message to a specific peer (multi-session, v0.6).

        Args:
            peer_id: Session-id of the target peer (from peers()).
            text:    Plain text content.
            parts:   Structured Part list.
            role:    Message role.
        """
        body: Dict[str, Any] = {"role": role}
        if message_id:
            body["message_id"] = message_id
        if parts:
            body["parts"] = parts
        elif text is not None:
            body["text"] = text
        else:
            raise ValueError("Provide either 'text' or 'parts'")

        resp = _http_post(f"{self.base_url}/peer/{peer_id}/send", body, self.timeout)
        _raise_from_response(resp, peer_id=peer_id)
        return resp

    def recv(self, limit: int = 50) -> List[dict]:
        """
        Poll received messages (non-SSE).

        Returns:
            List of raw message dicts, oldest first.
        """
        data = _http_get(f"{self.base_url}/recv?limit={limit}", self.timeout)
        return data.get("messages", [])

    def recv_messages(self, limit: int = 50) -> List[Message]:
        """Return received messages as ``Message`` model objects."""
        return [Message.from_dict(m) for m in self.recv(limit)]

    def reply(self, correlation_id: str, text: str) -> dict:
        """Send a reply correlated to a specific message id."""
        return _http_post(
            f"{self.base_url}/reply",
            {"correlation_id": correlation_id, "content": text},
            self.timeout,
        )

    def send_and_recv(
        self,
        text: str,
        timeout: float = 30.0,
        poll_interval: float = 0.5,
    ) -> Optional[dict]:
        """
        Send a message and wait for the first new reply that arrives after it.

        Returns:
            The first new message dict received after the send, or None on timeout.
        """
        before = len(self.recv(limit=200))
        self.send(text)

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            msgs = self.recv(limit=200)
            if len(msgs) > before:
                return msgs[-1]
            time.sleep(poll_interval)
        return None

    # ── SSE Stream ────────────────────────────────────────────────────────

    def stream(self, timeout: float = 60.0) -> Generator[dict, None, None]:
        """
        Subscribe to the SSE event stream.

        Yields parsed event dicts until ``timeout`` seconds elapse or the
        connection is closed by the server.

        Example:
            for event in client.stream(timeout=120):
                if event.get("type") == "acp.message":
                    print(event)
        """
        import socket as _socket

        req = urllib.request.Request(
            f"{self.base_url}/stream",
            headers={"Accept": "text/event-stream"},
        )
        deadline = time.monotonic() + timeout
        try:
            resp = urllib.request.urlopen(req, timeout=min(timeout, 30.0))
            buffer = ""
            while time.monotonic() < deadline:
                chunk = resp.read(512)
                if not chunk:
                    break
                buffer += chunk.decode("utf-8", errors="replace")
                while "\n\n" in buffer:
                    event_str, buffer = buffer.split("\n\n", 1)
                    data_lines = [
                        line[5:]
                        for line in event_str.splitlines()
                        if line.startswith("data:")
                    ]
                    if data_lines:
                        raw = "".join(data_lines)
                        try:
                            yield json.loads(raw)
                        except json.JSONDecodeError:
                            yield {"_raw": raw}
        except (urllib.error.URLError, OSError, _socket.timeout):
            return

    # ── Tasks ─────────────────────────────────────────────────────────────

    def tasks(
        self,
        status: str = None,
        peer_id: str = None,
        created_after: str = None,
        updated_after: str = None,
        sort: str = None,
        cursor: str = None,
        limit: int = None,
    ) -> List[dict]:
        """
        List tasks with optional filters (v1.4+).

        Args:
            status:        Filter by state (submitted/working/completed/failed/…).
            peer_id:       Filter by peer agent id.
            created_after: ISO-8601 lower bound on creation time.
            updated_after: ISO-8601 lower bound on update time.
            sort:          "asc" or "desc" (default "desc").
            cursor:        Pagination cursor from previous response.
            limit:         Maximum number of tasks to return.

        Returns:
            List of raw task dicts.
        """
        params: List[str] = []
        for key, val in [
            ("status", status), ("peer_id", peer_id),
            ("created_after", created_after), ("updated_after", updated_after),
            ("sort", sort), ("cursor", cursor),
        ]:
            if val is not None:
                params.append(f"{key}={val}")
        if limit is not None:
            params.append(f"limit={limit}")

        url = f"{self.base_url}/tasks"
        if params:
            url += "?" + "&".join(params)
        return _http_get(url, self.timeout).get("tasks", [])

    def get_task(self, task_id: str) -> Task:
        """
        Fetch a single task by id.

        Returns:
            Task model object.

        Raises:
            TaskNotFoundError: If the relay returns a not-found response.
        """
        raw = _http_get(f"{self.base_url}/tasks/{task_id}", self.timeout)
        _raise_from_response(raw, task_id=task_id)
        return Task.from_dict(raw)

    def create_task(self, payload: dict, delegate: bool = False) -> dict:
        """
        Create a task locally or delegate it to the connected peer.

        Args:
            payload:  Task payload (description, input, etc.).
            delegate: If True, forward the task to the peer.

        Returns:
            {"ok": True, "task_id": "...", "state": "submitted"}
        """
        return _http_post(
            f"{self.base_url}/tasks/create",
            {"payload": payload, "delegate": delegate},
            self.timeout,
        )

    def update_task(self, task_id: str, state: str, output: dict = None) -> dict:
        """Update a task's state (and optionally its output payload)."""
        body: dict = {"state": state}
        if output:
            body["output"] = output
        return _http_post(f"{self.base_url}/tasks/{task_id}:update", body, self.timeout)

    def cancel_task(self, task_id: str, raise_on_terminal: bool = False) -> dict:
        """
        Cancel a task (v1.5.2, idempotent).

        Args:
            task_id:           Task to cancel.
            raise_on_terminal: If True, raise TaskNotCancelableError when the
                               task is already in a terminal state (409).

        Raises:
            TaskNotCancelableError: If ``raise_on_terminal=True`` and the task
                                    is already completed/failed.
        """
        resp = _http_post(f"{self.base_url}/tasks/{task_id}:cancel", {}, self.timeout)
        if raise_on_terminal and resp.get("error") == "ERR_TASK_NOT_CANCELABLE":
            raise TaskNotCancelableError(task_id)
        return resp

    def continue_task(
        self,
        task_id: str,
        text: str = None,
        parts: List[dict] = None,
    ) -> dict:
        """
        Resume a task that is waiting for additional input (input_required, v0.5).
        """
        body: dict = {}
        if parts:
            body["parts"] = parts
        elif text is not None:
            body["text"] = text
        return _http_post(f"{self.base_url}/tasks/{task_id}/continue", body, self.timeout)

    def wait_for_task(
        self,
        task_id: str,
        timeout: float = 60.0,
        poll_interval: float = 1.0,
    ) -> Task:
        """
        Poll a task until it reaches a terminal state or timeout expires.

        Returns:
            Final Task model (may still be non-terminal if timeout was reached).
        """
        TERMINAL = {"completed", "failed", "canceled"}
        deadline = time.monotonic() + timeout
        task = self.get_task(task_id)
        while not task.is_terminal() and time.monotonic() < deadline:
            time.sleep(poll_interval)
            task = self.get_task(task_id)
        return task

    # ── Skills / QuerySkill ───────────────────────────────────────────────

    def query_skills(
        self,
        skill_id: str = None,
        capability: str = None,
    ) -> dict:
        """
        Query the peer's available skills (QuerySkill, v0.5).

        Args:
            skill_id:   Exact skill id to look up.
            capability: Filter by capability keyword.
        """
        body: dict = {}
        if skill_id:
            body["skill_id"] = skill_id
        if capability:
            body["capability"] = capability
        return _http_post(f"{self.base_url}/skills/query", body, self.timeout)

    # ── Webhooks ──────────────────────────────────────────────────────────

    def register_webhook(self, url: str) -> dict:
        """Register a push-webhook URL for incoming messages."""
        return _http_post(
            f"{self.base_url}/webhooks/register",
            {"url": url},
            self.timeout,
        )

    def __repr__(self) -> str:
        return f"<RelayClient base_url={self.base_url!r}>"
