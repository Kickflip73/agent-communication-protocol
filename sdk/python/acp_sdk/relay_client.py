"""
RelayClient — direct HTTP client for a running acp_relay.py instance.

This client speaks the *actual* acp_relay.py HTTP API (v0.6):
  POST /message:send      — send a message to the connected peer
  POST /peer/{id}/send    — send to a specific peer (multi-session)
  GET  /recv              — poll pending received messages
  GET  /stream            — SSE event stream
  GET  /peers             — list connected peers
  GET  /peer/{id}         — get a single peer's info
  GET  /status            — relay status + AgentCard
  GET  /tasks             — list tasks
  POST /tasks/create      — create/delegate a task
  POST /tasks/{id}:update — update task state
  GET  /skills/query      — query peer capabilities (QuerySkill)

Unlike ACPClient (which speaks a hypothetical registry/cloud API),
RelayClient wraps the localhost relay process that every ACP node runs.

Usage (sync, no async required):
    from acp_sdk import RelayClient

    client = RelayClient("http://localhost:7901")

    # Send a text message to connected peer
    resp = client.send("Hello from Python SDK!")
    print(resp)   # {"ok": True, "message_id": "msg_..."}

    # List connected peers (multi-session, v0.6)
    peers = client.peers()
    for p in peers:
        print(p["peer_id"], p["name"])

    # Send to specific peer
    resp = client.send_to_peer(peers[0]["peer_id"], "Hi, targeted message!")

    # Subscribe to events (generator)
    for event in client.stream(timeout=30):
        print(event)

Usage (async):
    async with RelayClient.async_context("http://localhost:7901") as client:
        await client.async_send("Hello!")
"""
from __future__ import annotations

import json
import time
import logging
import urllib.request
import urllib.error
from typing import Any, Generator, Optional

logger = logging.getLogger("acp_sdk.relay_client")


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _http_get(url: str, timeout: float = 10.0) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


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


# ─────────────────────────────────────────────
# RelayClient
# ─────────────────────────────────────────────

class RelayClient:
    """
    Synchronous HTTP client for acp_relay.py (v0.6).
    Zero external dependencies — uses stdlib urllib only.

    Args:
        base_url: The relay HTTP endpoint, e.g. "http://localhost:7901"
        timeout:  Default HTTP timeout in seconds.
    """

    def __init__(self, base_url: str = "http://localhost:7901", timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ── Status & discovery ────────────────────────────────────────────────

    def status(self) -> dict:
        """Get relay status, version, and AgentCard."""
        return _http_get(f"{self.base_url}/status", self.timeout)

    def card(self) -> dict:
        """Get this node's AgentCard (.well-known/acp.json)."""
        return _http_get(f"{self.base_url}/.well-known/acp.json", self.timeout)

    def link(self) -> str:
        """Get the ACP link for this node (share with peers)."""
        data = _http_get(f"{self.base_url}/link", self.timeout)
        return data.get("link", "")

    # ── Peer management (v0.6 multi-session) ─────────────────────────────

    def peers(self) -> list[dict]:
        """List all connected peers."""
        data = _http_get(f"{self.base_url}/peers", self.timeout)
        return data.get("peers", [])

    def peer(self, peer_id: str) -> dict:
        """Get info for a specific peer."""
        return _http_get(f"{self.base_url}/peer/{peer_id}", self.timeout)

    def is_connected(self) -> bool:
        """Return True if at least one peer is connected."""
        try:
            st = self.status()
            return st.get("connected", False)
        except Exception:
            return False

    # ── Messaging ─────────────────────────────────────────────────────────

    def send(
        self,
        text: str = None,
        *,
        parts: list[dict] = None,
        role: str = "user",
        message_id: str = None,
    ) -> dict:
        """
        Send a message to the currently connected peer (primary).

        Args:
            text:       Plain text content (convenience shorthand).
            parts:      Structured Part list (text/file/data). Overrides `text`.
            role:       Message role ("user" | "assistant"). Default "user".
            message_id: Client-assigned idempotency key. Auto-generated if omitted.

        Returns:
            {"ok": True, "message_id": "msg_..."} on success.
        """
        body: dict[str, Any] = {"role": role}
        if message_id:
            body["message_id"] = message_id
        if parts:
            body["parts"] = parts
        elif text is not None:
            body["text"] = text
        else:
            raise ValueError("Provide either 'text' or 'parts'")
        return _http_post(f"{self.base_url}/message:send", body, self.timeout)

    def send_to_peer(
        self,
        peer_id: str,
        text: str = None,
        *,
        parts: list[dict] = None,
        role: str = "user",
        message_id: str = None,
    ) -> dict:
        """
        Send a message to a specific peer (multi-session, v0.6).

        Args:
            peer_id: The session_id of the target peer (from peers() list).
            text:    Plain text content.
            parts:   Structured Part list.
            role:    Message role.
        """
        body: dict[str, Any] = {"role": role}
        if message_id:
            body["message_id"] = message_id
        if parts:
            body["parts"] = parts
        elif text is not None:
            body["text"] = text
        else:
            raise ValueError("Provide either 'text' or 'parts'")
        return _http_post(f"{self.base_url}/peer/{peer_id}/send", body, self.timeout)

    def recv(self, limit: int = 50) -> list[dict]:
        """
        Poll received messages (non-SSE mode).

        Returns:
            List of message dicts, oldest first.
        """
        data = _http_get(f"{self.base_url}/recv?limit={limit}", self.timeout)
        return data.get("messages", [])

    def reply(self, correlation_id: str, text: str) -> dict:
        """Send a reply tied to a specific message."""
        return _http_post(
            f"{self.base_url}/reply",
            {"correlation_id": correlation_id, "content": text},
            self.timeout,
        )

    # ── SSE stream ────────────────────────────────────────────────────────

    def stream(self, timeout: float = 60.0) -> Generator[dict, None, None]:
        """
        Subscribe to the SSE event stream.

        Yields parsed event dicts until `timeout` seconds have elapsed
        or the connection is closed.

        Example:
            for event in client.stream(timeout=120):
                if event.get("type") == "acp.message":
                    print("Got message:", event)
        """
        import socket
        req = urllib.request.Request(
            f"{self.base_url}/stream",
            headers={"Accept": "text/event-stream"},
        )
        deadline = time.time() + timeout
        try:
            resp = urllib.request.urlopen(req, timeout=min(timeout, 30.0))
            buffer = ""
            while time.time() < deadline:
                chunk = resp.read(512)
                if not chunk:
                    break
                buffer += chunk.decode("utf-8", errors="replace")
                # SSE: events are separated by double newline
                while "\n\n" in buffer:
                    event_str, buffer = buffer.split("\n\n", 1)
                    data_lines = [
                        line[5:]  # strip "data:" prefix
                        for line in event_str.splitlines()
                        if line.startswith("data:")
                    ]
                    if data_lines:
                        raw = "".join(data_lines)
                        try:
                            yield json.loads(raw)
                        except json.JSONDecodeError:
                            yield {"_raw": raw}
        except (urllib.error.URLError, OSError, socket.timeout):
            return

    # ── Tasks ─────────────────────────────────────────────────────────────

    def tasks(self, status: str = None) -> list[dict]:
        """List tasks, optionally filtered by status."""
        url = f"{self.base_url}/tasks"
        if status:
            url += f"?status={status}"
        data = _http_get(url, self.timeout)
        return data.get("tasks", [])

    def create_task(self, payload: dict, delegate: bool = False) -> dict:
        """
        Create a task locally or delegate to peer.

        Args:
            payload:  Task payload dict (description, input, etc.)
            delegate: If True, forward the task to the connected peer.
        """
        return _http_post(
            f"{self.base_url}/tasks/create",
            {"payload": payload, "delegate": delegate},
            self.timeout,
        )

    def update_task(self, task_id: str, state: str, output: dict = None) -> dict:
        """Update a task's state."""
        body: dict = {"state": state}
        if output:
            body["output"] = output
        return _http_post(
            f"{self.base_url}/tasks/{task_id}:update",
            body,
            self.timeout,
        )

    def cancel_task(self, task_id: str) -> dict:
        """Cancel a task."""
        return _http_post(f"{self.base_url}/tasks/{task_id}:cancel", {}, self.timeout)

    # ── Skills / QuerySkill ───────────────────────────────────────────────

    def query_skills(
        self,
        skill_id: str = None,
        capability: str = None,
    ) -> dict:
        """
        Query the peer's skills (QuerySkill, v0.5).

        Args:
            skill_id:   Exact skill id to look up.
            capability: Filter by capability keyword.
        """
        body = {}
        if skill_id:
            body["skill_id"] = skill_id
        if capability:
            body["capability"] = capability
        return _http_post(f"{self.base_url}/skills/query", body, self.timeout)

    # ── Webhooks ──────────────────────────────────────────────────────────

    def register_webhook(self, url: str) -> dict:
        """Register a push webhook for incoming messages."""
        return _http_post(
            f"{self.base_url}/webhooks/register",
            {"url": url},
            self.timeout,
        )

    # ── Convenience ───────────────────────────────────────────────────────

    def wait_for_peer(self, timeout: float = 30.0, poll_interval: float = 1.0) -> bool:
        """
        Block until a peer connects or timeout expires.

        Returns:
            True if a peer connected, False on timeout.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.is_connected():
                return True
            time.sleep(poll_interval)
        return False

    def send_and_recv(
        self,
        text: str,
        timeout: float = 30.0,
        poll_interval: float = 0.5,
    ) -> Optional[dict]:
        """
        Send a message and wait for the first reply that arrives after sending.

        Convenience method for simple request-response patterns.

        Returns:
            The first new message received after sending, or None on timeout.
        """
        # Snapshot current recv count
        before = len(self.recv(limit=200))
        result = self.send(text)
        if not result.get("ok"):
            return None

        deadline = time.time() + timeout
        while time.time() < deadline:
            msgs = self.recv(limit=200)
            if len(msgs) > before:
                return msgs[-1]  # latest message
            time.sleep(poll_interval)
        return None

    def __repr__(self) -> str:
        connected = self.is_connected()
        return f"<RelayClient base_url={self.base_url!r} connected={connected}>"


# ─────────────────────────────────────────────
# Async variant (optional, requires aiohttp)
# ─────────────────────────────────────────────

class AsyncRelayClient:
    """
    Async HTTP client for acp_relay.py (v0.6). Requires aiohttp.

    Example:
        async with AsyncRelayClient("http://localhost:7901") as client:
            await client.send("Hello async!")
            peers = await client.peers()
    """

    def __init__(self, base_url: str = "http://localhost:7901", timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = None

    async def __aenter__(self):
        try:
            import aiohttp
            self._session = aiohttp.ClientSession()
        except ImportError:
            raise ImportError("AsyncRelayClient requires aiohttp: pip install aiohttp")
        return self

    async def __aexit__(self, *args):
        if self._session:
            await self._session.close()

    async def _get(self, path: str) -> dict:
        async with self._session.get(
            f"{self.base_url}{path}",
            timeout=self.timeout,
        ) as resp:
            return await resp.json()

    async def _post(self, path: str, body: dict) -> dict:
        async with self._session.post(
            f"{self.base_url}{path}",
            json=body,
            timeout=self.timeout,
        ) as resp:
            return await resp.json()

    async def status(self) -> dict:
        return await self._get("/status")

    async def peers(self) -> list[dict]:
        data = await self._get("/peers")
        return data.get("peers", [])

    async def send(self, text: str, *, role: str = "user", message_id: str = None) -> dict:
        body: dict = {"role": role, "text": text}
        if message_id:
            body["message_id"] = message_id
        return await self._post("/message:send", body)

    async def send_to_peer(
        self, peer_id: str, text: str, *, role: str = "user"
    ) -> dict:
        return await self._post(f"/peer/{peer_id}/send", {"role": role, "text": text})

    async def recv(self, limit: int = 50) -> list[dict]:
        data = await self._get(f"/recv?limit={limit}")
        return data.get("messages", [])

    async def tasks(self) -> list[dict]:
        data = await self._get("/tasks")
        return data.get("tasks", [])

    async def create_task(self, payload: dict, delegate: bool = False) -> dict:
        return await self._post("/tasks/create", {"payload": payload, "delegate": delegate})

    async def query_skills(self, skill_id: str = None, capability: str = None) -> dict:
        body = {}
        if skill_id:
            body["skill_id"] = skill_id
        if capability:
            body["capability"] = capability
        return await self._post("/skills/query", body)
