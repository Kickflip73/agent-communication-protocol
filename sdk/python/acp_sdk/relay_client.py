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

    def capabilities(self) -> dict:
        """
        Return the relay's declared capabilities block from AgentCard (v1.6+).

        Includes fields such as:
          - http2 (bool): HTTP/2 h2c transport enabled
          - did_identity (bool): DID self-sovereign identity enabled
          - hmac_signing (bool): HMAC-SHA256 message signing enabled
          - mdns (bool): mDNS LAN discovery enabled

        Returns:
            dict of capability name → value, or empty dict if unavailable.
        """
        try:
            card = self.card()
            return card.get("capabilities", {})
        except Exception:
            return {}

    def identity(self) -> dict:
        """
        Return this node's identity block (v1.3+, did:acp:).

        Returns:
            dict with keys: did, public_key_b64, scheme
            Example: {"did": "did:acp:abc123...", "public_key_b64": "...", "scheme": "ed25519"}
        """
        card = self.card()
        return card.get("identity", {})

    def did_document(self) -> dict:
        """
        Fetch the W3C DID Document for this node (v1.3+).

        Endpoint: GET /.well-known/did.json
        Returns a W3C DID Document with Ed25519VerificationKey2020
        and ACPRelay service endpoint.

        Returns:
            W3C DID Document dict.
        """
        return _http_get(f"{self.base_url}/.well-known/did.json", self.timeout)

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

    def tasks(
        self,
        status: str = None,
        peer_id: str = None,
        created_after: str = None,
        updated_after: str = None,
        sort: str = None,
        cursor: str = None,
        limit: int = None,
    ) -> list[dict]:
        """
        List tasks with optional filters (v1.4+).

        Args:
            status:         Filter by task state (submitted/working/completed/failed/input_required/canceled).
            peer_id:        Filter by peer agent id.
            created_after:  ISO-8601 timestamp; return only tasks created after this time.
            updated_after:  ISO-8601 timestamp; return only tasks updated after this time.
            sort:           Sort order: "asc" or "desc" (default "desc").
            cursor:         Pagination cursor from previous response.
            limit:          Max number of tasks to return.

        Returns:
            List of task dicts.
        """
        params: list[str] = []
        if status:
            params.append(f"status={status}")
        if peer_id:
            params.append(f"peer_id={peer_id}")
        if created_after:
            params.append(f"created_after={created_after}")
        if updated_after:
            params.append(f"updated_after={updated_after}")
        if sort:
            params.append(f"sort={sort}")
        if cursor:
            params.append(f"cursor={cursor}")
        if limit is not None:
            params.append(f"limit={limit}")
        url = f"{self.base_url}/tasks"
        if params:
            url += "?" + "&".join(params)
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

    def cancel_task(self, task_id: str, raise_on_terminal: bool = False) -> dict:
        """
        Cancel a task (v1.5.2, spec §10).

        Cancel semantics are synchronous and idempotent:
        - Canceling an active task returns {"state": "canceled"}.
        - Canceling an already-canceled task returns 200 (idempotent, no error).
        - Canceling a completed/failed task returns ERR_TASK_NOT_CANCELABLE (409).

        Args:
            task_id:           Task id to cancel.
            raise_on_terminal: If True, raise ValueError when task is in terminal
                               state (completed/failed). Default False (match server
                               idempotent behavior — return the error dict).

        Returns:
            Server response dict, e.g. {"state": "canceled"} or error dict.
        """
        result = _http_post(f"{self.base_url}/tasks/{task_id}:cancel", {}, self.timeout)
        # _http_post swallows HTTPError and returns the error body as a dict.
        # Detect ERR_TASK_NOT_CANCELABLE (409) by checking the error field.
        if raise_on_terminal and isinstance(result, dict) and result.get("error") == "ERR_TASK_NOT_CANCELABLE":
            raise ValueError(
                f"Task {task_id!r} is in a terminal state and cannot be canceled. "
                f"Server: {result}"
            )
        return result

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
# ─────────────────────────────────────────────
# AsyncRelayClient — stdlib-only async client (v0.9)
# ─────────────────────────────────────────────

class AsyncRelayClient:
    """
    Async HTTP client for acp_relay.py (v0.8).

    **Zero external dependencies** — uses stdlib asyncio + urllib only.
    No aiohttp, no httpx, no requests. Truly optional extras.

    Supports all ACP v0.8 features:
      - Async send/recv/stream
      - Multi-session peer registry (v0.6)
      - Task lifecycle with input_required (v0.5)
      - context_id multi-turn grouping (v0.7)
      - Structured Parts: text / file / data (v0.5)
      - QuerySkill API (v0.5)
      - LAN discovery (v0.7, requires --advertise-mdns on relay)

    Usage:
        # Context manager (recommended)
        async with AsyncRelayClient("http://localhost:7901") as client:
            await client.send("Hello async!")
            async for event in client.stream(timeout=30):
                print(event)

        # Manual lifecycle
        client = AsyncRelayClient("http://localhost:7901")
        resp = await client.send("Hello")
        await client.close()

    Comparison with aiohttp-based approach:
        The previous AsyncRelayClient required `pip install aiohttp`.
        This implementation uses only asyncio.get_event_loop() +
        loop.run_in_executor() to offload stdlib urllib calls without
        blocking the event loop — no third-party packages needed.
    """

    def __init__(self, base_url: str = "http://localhost:7901", timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def __aenter__(self) -> "AsyncRelayClient":
        return self

    async def __aexit__(self, *args) -> None:
        pass  # no persistent connection to close

    async def close(self) -> None:
        """No-op — kept for API compatibility with aiohttp-based clients."""
        pass

    # ── Internal helpers ────────────────────────────────────────────────

    async def _get(self, path: str) -> dict:
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, _http_get, f"{self.base_url}{path}", self.timeout
        )

    async def _post(self, path: str, body: dict) -> dict:
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, _http_post, f"{self.base_url}{path}", body, self.timeout
        )

    # ── Status & discovery ──────────────────────────────────────────────

    async def status(self) -> dict:
        """Get relay status, version, and AgentCard."""
        return await self._get("/status")

    async def card(self) -> dict:
        """Get AgentCard (.well-known/acp.json)."""
        return await self._get("/.well-known/acp.json")

    async def link(self) -> str:
        """Get the acp:// link for this node."""
        data = await self._get("/link")
        return data.get("link", "")

    async def discover(self) -> list[dict]:
        """
        List LAN peers discovered via mDNS (v0.7).
        Requires relay started with --advertise-mdns.
        """
        data = await self._get("/discover")
        return data.get("peers", [])

    # ── Peer management ─────────────────────────────────────────────────

    async def peers(self) -> list[dict]:
        """List all connected peers (multi-session, v0.6)."""
        data = await self._get("/peers")
        return data.get("peers", [])

    async def peer(self, peer_id: str) -> dict:
        """Get info for a specific peer."""
        return await self._get(f"/peer/{peer_id}")

    async def connect_peer(self, link: str) -> dict:
        """
        Connect to a new peer via its acp:// link (v0.6).

        Args:
            link: The acp:// (or acp+wss://) link from the other agent.
        """
        return await self._post("/peers/connect", {"link": link})

    async def is_connected(self) -> bool:
        """Return True if at least one peer is connected."""
        try:
            st = await self.status()
            return st.get("connected", False)
        except Exception:
            return False

    # ── Messaging ───────────────────────────────────────────────────────

    async def send(
        self,
        text: str = None,
        *,
        parts: list[dict] = None,
        role: str = "user",
        message_id: str = None,
        task_id: str = None,
        context_id: str = None,
        create_task: bool = False,
        sync: bool = False,
        sync_timeout: float = 30.0,
    ) -> dict:
        """
        Send a message to the connected peer (primary).

        Args:
            text:         Plain text content (shorthand for parts=[{type:text,...}]).
            parts:        Structured Part list. Overrides `text`.
            role:         Message role ("user" | "agent"). Default "user".
            message_id:   Client-assigned idempotency key. Auto-generated if omitted.
            task_id:      Associate message with an existing task (v0.5).
            context_id:   Multi-turn context group identifier (v0.7).
            create_task:  Auto-create a task for this message (v0.5).
            sync:         Block until peer replies (v0.5).
            sync_timeout: Seconds to wait for sync reply (default 30).

        Returns:
            {"ok": True, "message_id": "msg_..."} on success,
            or {"ok": False, "error_code": "ERR_...", "error": "..."} on failure.
        """
        body: dict = {"role": role}
        if message_id:
            body["message_id"] = message_id
        if parts:
            body["parts"] = parts
        elif text is not None:
            body["text"] = text
        else:
            raise ValueError("Provide either 'text' or 'parts'")
        if task_id:
            body["task_id"] = task_id
        if context_id:
            body["context_id"] = context_id
        if create_task:
            body["create_task"] = True
        if sync:
            body["sync"] = True
            body["timeout"] = int(sync_timeout)
        return await self._post("/message:send", body)

    async def send_to_peer(
        self,
        peer_id: str,
        text: str = None,
        *,
        parts: list[dict] = None,
        role: str = "user",
        message_id: str = None,
        task_id: str = None,
        context_id: str = None,
    ) -> dict:
        """
        Send a message to a specific peer (multi-session, v0.6).

        Args:
            peer_id:    The session_id of the target peer.
            text:       Plain text content.
            parts:      Structured Part list.
            role:       Message role.
            message_id: Client-assigned idempotency key.
            task_id:    Associate with an existing task (v0.5).
            context_id: Multi-turn context group identifier (v0.7).
        """
        body: dict = {"role": role}
        if message_id:
            body["message_id"] = message_id
        if parts:
            body["parts"] = parts
        elif text is not None:
            body["text"] = text
        else:
            raise ValueError("Provide either 'text' or 'parts'")
        if task_id:
            body["task_id"] = task_id
        if context_id:
            body["context_id"] = context_id
        return await self._post(f"/peer/{peer_id}/send", body)

    async def recv(self, limit: int = 50) -> list[dict]:
        """Poll received messages (non-SSE)."""
        data = await self._get(f"/recv?limit={limit}")
        return data.get("messages", [])

    # ── SSE async stream ────────────────────────────────────────────────

    async def stream(self, timeout: float = 60.0):
        """
        Async generator that yields parsed SSE events.

        Each yielded item is a dict (parsed from the data: line).
        Iterates until `timeout` seconds elapse or connection closes.

        Usage:
            async for event in client.stream(timeout=120):
                if event.get("type") == "acp.message":
                    handle_message(event)

        Implemented using run_in_executor to offload blocking I/O without
        requiring aiohttp or any external async HTTP library.
        """
        import asyncio
        import queue as _queue

        q: _queue.Queue = _queue.Queue()
        sentinel = object()

        def _read_sse():
            """Blocking SSE reader — runs in thread pool."""
            req = urllib.request.Request(
                f"{self.base_url}/stream",
                headers={"Accept": "text/event-stream"},
            )
            try:
                resp = urllib.request.urlopen(req, timeout=min(timeout, 30.0))
                buffer = ""
                deadline = time.time() + timeout
                while time.time() < deadline:
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
                                q.put(json.loads(raw))
                            except json.JSONDecodeError:
                                q.put({"_raw": raw})
            except Exception:
                pass
            finally:
                q.put(sentinel)

        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, _read_sse)

        while True:
            # Non-blocking queue check with small async sleep
            try:
                item = q.get_nowait()
                if item is sentinel:
                    return
                yield item
            except _queue.Empty:
                await asyncio.sleep(0.05)

    # ── Tasks ───────────────────────────────────────────────────────────

    async def tasks(
        self,
        status: str = None,
        peer_id: str = None,
        created_after: str = None,
        updated_after: str = None,
        sort: str = None,
        cursor: str = None,
        limit: int = None,
    ) -> list[dict]:
        """
        List tasks with optional filters (v1.4+).

        Args:
            status:         Filter by task state.
            peer_id:        Filter by peer agent id.
            created_after:  ISO-8601 timestamp.
            updated_after:  ISO-8601 timestamp.
            sort:           "asc" or "desc".
            cursor:         Pagination cursor.
            limit:          Max results.
        """
        params: list[str] = []
        if status:
            params.append(f"status={status}")
        if peer_id:
            params.append(f"peer_id={peer_id}")
        if created_after:
            params.append(f"created_after={created_after}")
        if updated_after:
            params.append(f"updated_after={updated_after}")
        if sort:
            params.append(f"sort={sort}")
        if cursor:
            params.append(f"cursor={cursor}")
        if limit is not None:
            params.append(f"limit={limit}")
        path = "/tasks"
        if params:
            path += "?" + "&".join(params)
        data = await self._get(path)
        return data.get("tasks", [])

    async def get_task(self, task_id: str) -> dict:
        """Get details for a specific task."""
        return await self._get(f"/tasks/{task_id}")

    async def create_task(
        self,
        payload: dict,
        delegate: bool = False,
    ) -> dict:
        """Create a task locally or delegate to peer."""
        return await self._post(
            "/tasks/create",
            {"payload": payload, "delegate": delegate},
        )

    async def update_task(
        self,
        task_id: str,
        state: str,
        output: dict = None,
        artifact: dict = None,
    ) -> dict:
        """
        Update a task's state.

        Args:
            task_id:  Task to update.
            state:    New state (working/completed/failed/input_required).
            output:   Result payload (for completed).
            artifact: Artifact object with parts (for completed, v0.8).
        """
        body: dict = {"state": state}
        if output:
            body["output"] = output
        if artifact:
            body["artifact"] = artifact
        return await self._post(f"/tasks/{task_id}:update", body)

    async def continue_task(self, task_id: str, text: str = None, parts: list[dict] = None) -> dict:
        """
        Resume an input_required task with additional input (v0.5).

        Args:
            task_id: The task awaiting input.
            text:    Follow-up text.
            parts:   Follow-up parts.
        """
        body: dict = {}
        if parts:
            body["parts"] = parts
        elif text is not None:
            body["text"] = text
        return await self._post(f"/tasks/{task_id}/continue", body)

    async def capabilities(self) -> dict:
        """
        Return the relay's declared capabilities block (v1.6+).
        Includes: http2, did_identity, hmac_signing, mdns, etc.
        """
        try:
            card = await self._get("/.well-known/acp.json")
            return card.get("capabilities", {})
        except Exception:
            return {}

    async def identity(self) -> dict:
        """Return this node's identity block (v1.3+, did:acp:)."""
        card = await self._get("/.well-known/acp.json")
        return card.get("identity", {})

    async def did_document(self) -> dict:
        """Fetch the W3C DID Document for this node (v1.3+)."""
        return await self._get("/.well-known/did.json")

    async def cancel_task(self, task_id: str, raise_on_terminal: bool = False) -> dict:
        """
        Cancel a task (v1.5.2, spec §10 — synchronous + idempotent).

        Args:
            task_id:           Task id to cancel.
            raise_on_terminal: If True, raise ValueError on 409 (terminal state).
        """
        try:
            return await self._post(f"/tasks/{task_id}:cancel", {})
        except Exception as e:
            # Handle 409 ERR_TASK_NOT_CANCELABLE
            if hasattr(e, "status") and e.status == 409:  # type: ignore[attr-defined]
                if raise_on_terminal:
                    raise ValueError(
                        f"Task {task_id!r} is in a terminal state and cannot be canceled."
                    ) from e
                return {"error": "ERR_TASK_NOT_CANCELABLE", "task_id": task_id}
            raise

    async def wait_for_task(
        self,
        task_id: str,
        timeout: float = 60.0,
        poll_interval: float = 1.0,
    ) -> dict:
        """
        Poll a task until it reaches a terminal state or timeout.

        Terminal states: completed, failed, canceled.

        Returns:
            Final task dict, or last-known state on timeout.
        """
        import asyncio
        TERMINAL = {"completed", "failed", "canceled"}
        deadline = time.time() + timeout
        while time.time() < deadline:
            task = await self.get_task(task_id)
            if task.get("status") in TERMINAL:
                return task
            await asyncio.sleep(poll_interval)
        return task  # return last known state

    # ── Skills / QuerySkill ─────────────────────────────────────────────

    async def query_skills(
        self,
        query: str = None,
        skill_id: str = None,
        capability: str = None,
        limit: int = None,
    ) -> dict:
        """
        Query this agent's available skills (QuerySkill, v0.5).

        Args:
            query:      Free-text search query.
            skill_id:   Exact skill id lookup.
            capability: Filter by capability keyword.
            limit:      Max results to return.
        """
        body: dict = {}
        if query:
            body["query"] = query
        if skill_id:
            body["skill_id"] = skill_id
        if capability:
            body["capability"] = capability
        if limit:
            body["limit"] = limit
        return await self._post("/skills/query", body)

    # ── Convenience ─────────────────────────────────────────────────────

    async def wait_for_peer(
        self,
        timeout: float = 30.0,
        poll_interval: float = 1.0,
    ) -> bool:
        """
        Async-wait until a peer connects or timeout expires.

        Returns:
            True if a peer connected, False on timeout.
        """
        import asyncio
        deadline = time.time() + timeout
        while time.time() < deadline:
            if await self.is_connected():
                return True
            await asyncio.sleep(poll_interval)
        return False

    def __repr__(self) -> str:
        return f"<AsyncRelayClient base_url={self.base_url!r}>"
