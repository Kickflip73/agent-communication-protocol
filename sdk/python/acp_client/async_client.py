"""
acp_client.async_client — Async RelayClient for acp_relay.py.

Zero external dependencies — uses stdlib asyncio + run_in_executor to
offload urllib calls without blocking the event loop.

Optional extras:
  pip install acp-client[async]   # adds httpx for native async HTTP

Usage:
    from acp_client import AsyncRelayClient

    async def main():
        async with AsyncRelayClient("http://localhost:7901") as client:
            await client.send("Hello async!")
            async for event in client.stream(timeout=30):
                print(event)

    import asyncio
    asyncio.run(main())
"""
from __future__ import annotations

import asyncio
import json
import queue as _queue
import time
import urllib.error
import urllib.request
from typing import Any, AsyncGenerator, Dict, List, Optional

from .client import _http_get, _http_post
from .exceptions import (
    ACPError,
    PeerNotFoundError,
    SendError,
    TaskNotCancelableError,
    _raise_from_response,
)
from .models import AgentCard, Message, Task, TaskStatus

import logging
logger = logging.getLogger("acp_client.async")


class AsyncRelayClient:
    """
    Async HTTP client for acp_relay.py (acp-client v1.7).

    Zero external dependencies — offloads stdlib urllib calls via
    ``asyncio.get_running_loop().run_in_executor()``.

    Supports all ACP features up to v2.7:
      - Async send/recv/stream
      - Multi-session peer registry (v0.6)
      - Task lifecycle with input_required / cancelling (v0.5 / v2.6)
      - context_id multi-turn grouping (v0.7)
      - Structured Parts: text / file / data (v0.5)
      - QuerySkill API (v0.5)
      - DID identity (v1.3+)
      - SSE named events + seq (v2.5+)
      - AgentCard limitations (v2.7+)

    Args:
        base_url: Relay HTTP endpoint (default: "http://localhost:7901").
        timeout:  Default request timeout in seconds (default: 10).
    """

    def __init__(
        self,
        base_url: str = "http://localhost:7901",
        timeout: float = 10.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def __aenter__(self) -> "AsyncRelayClient":
        return self

    async def __aexit__(self, *args) -> None:
        pass  # No persistent connection to close

    async def close(self) -> None:
        """No-op — kept for API compatibility."""

    # ── Internal helpers ─────────────────────────────────────────────────

    async def _get(self, path: str) -> dict:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, _http_get, f"{self.base_url}{path}", self.timeout
        )

    async def _post(self, path: str, body: dict) -> dict:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, _http_post, f"{self.base_url}{path}", body, self.timeout
        )

    # ── Status & Discovery ────────────────────────────────────────────────

    async def status(self) -> dict:
        """Return relay status dict."""
        return await self._get("/status")

    async def card(self) -> AgentCard:
        """Return this node's AgentCard."""
        raw = await self._get("/.well-known/acp.json")
        return AgentCard.from_dict(raw)

    async def card_raw(self) -> dict:
        """Return the raw AgentCard dict without parsing."""
        return await self._get("/.well-known/acp.json")

    async def link(self) -> str:
        """Return the acp:// link for this node."""
        data = await self._get("/link")
        return data.get("link", "")

    async def capabilities(self) -> dict:
        """Return the relay's declared capabilities dict."""
        try:
            raw = await self._get("/.well-known/acp.json")
            return raw.get("capabilities", {})
        except Exception:
            return {}

    async def supported_interfaces(self) -> List[str]:
        """Return supported interface groups (v2.5+)."""
        try:
            raw = await self._get("/.well-known/acp.json")
            return list(raw.get("supported_interfaces", []))
        except Exception:
            return []

    async def identity(self) -> dict:
        """Return the DID identity block (v1.3+)."""
        raw = await self._get("/.well-known/acp.json")
        return raw.get("identity", {})

    async def did_document(self) -> dict:
        """Return the W3C DID Document (v1.3+)."""
        return await self._get("/.well-known/did.json")

    async def is_connected(self) -> bool:
        """Return True if at least one peer is connected."""
        try:
            st = await self.status()
            return bool(st.get("connected", False))
        except Exception:
            return False

    async def sse_seq_enabled(self) -> bool:
        """Return True if the relay supports SSE event sequencing (v2.5+)."""
        caps = await self.capabilities()
        return bool(caps.get("sse_seq", False))

    # ── Peer Management ───────────────────────────────────────────────────

    async def peers(self) -> List[dict]:
        """List all connected peers."""
        data = await self._get("/peers")
        return data.get("peers", [])

    async def peer(self, peer_id: str) -> dict:
        """Get info for a specific peer."""
        return await self._get(f"/peer/{peer_id}")

    async def connect_peer(self, link: str) -> dict:
        """Connect to a new peer via its acp:// link (v0.6)."""
        return await self._post("/peers/connect", {"link": link})

    async def is_connected_to(self, peer_id: str) -> bool:
        """Return True if the given peer_id is in the current peer list."""
        peers = await self.peers()
        return any(p.get("peer_id") == peer_id for p in peers)

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
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if await self.is_connected():
                return True
            await asyncio.sleep(poll_interval)
        return False

    # ── Messaging ─────────────────────────────────────────────────────────

    async def send(
        self,
        text: str = None,
        *,
        parts: List[dict] = None,
        role: str = "user",
        message_id: str = None,
        task_id: str = None,
        context_id: str = None,
        create_task: bool = False,
        sync: bool = False,
        sync_timeout: float = 30.0,
    ) -> dict:
        """
        Send a message to the primary connected peer.

        Args:
            text:         Plain text content.
            parts:        Structured Part list (overrides ``text``).
            role:         Message role ("user" | "agent"). Default "user".
            message_id:   Client-assigned idempotency key.
            task_id:      Associate with an existing task (v0.5).
            context_id:   Multi-turn context group identifier (v0.7).
            create_task:  Auto-create a task for this message.
            sync:         Block until the peer replies (v0.5).
            sync_timeout: Seconds to wait for sync reply.

        Returns:
            {"ok": True, "message_id": "msg_..."}

        Raises:
            SendError: If the relay rejects the request.
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
        if task_id:
            body["task_id"] = task_id
        if context_id:
            body["context_id"] = context_id
        if create_task:
            body["create_task"] = True
        if sync:
            body["sync"] = True
            body["timeout"] = int(sync_timeout)

        resp = await self._post("/message:send", body)
        if not resp.get("ok"):
            raise SendError(resp.get("error", "send failed"), response=resp)
        return resp

    async def send_to_peer(
        self,
        peer_id: str,
        text: str = None,
        *,
        parts: List[dict] = None,
        role: str = "user",
        message_id: str = None,
        task_id: str = None,
        context_id: str = None,
    ) -> dict:
        """
        Send a message to a specific peer (multi-session, v0.6).

        Args:
            peer_id:    Session-id of the target peer.
            text:       Plain text content.
            parts:      Structured Part list.
            role:       Message role.
            message_id: Idempotency key.
            task_id:    Associate with a task.
            context_id: Multi-turn context group.
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
        if task_id:
            body["task_id"] = task_id
        if context_id:
            body["context_id"] = context_id

        resp = await self._post(f"/peer/{peer_id}/send", body)
        _raise_from_response(resp, peer_id=peer_id)
        return resp

    async def recv(self, limit: int = 50) -> List[dict]:
        """Poll received messages (non-SSE)."""
        data = await self._get(f"/recv?limit={limit}")
        return data.get("messages", [])

    async def recv_messages(self, limit: int = 50) -> List[Message]:
        """Return received messages as Message model objects."""
        return [Message.from_dict(m) for m in await self.recv(limit)]

    # ── SSE Async Stream ──────────────────────────────────────────────────

    async def stream(self, timeout: float = 60.0) -> AsyncGenerator[dict, None]:
        """
        Async generator that yields parsed SSE events.

        Runs the blocking SSE reader in a thread pool via run_in_executor,
        bridging it to the async caller through a queue.

        Example:
            async for event in client.stream(timeout=120):
                if event.get("type") == "acp.message":
                    handle(event)
        """
        q: _queue.Queue = _queue.Queue()
        sentinel = object()

        def _read_sse():
            req = urllib.request.Request(
                f"{self.base_url}/stream",
                headers={"Accept": "text/event-stream"},
            )
            try:
                resp = urllib.request.urlopen(req, timeout=min(timeout, 30.0))
                buffer = ""
                deadline = time.monotonic() + timeout
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
                                q.put(json.loads(raw))
                            except json.JSONDecodeError:
                                q.put({"_raw": raw})
            except Exception:
                pass
            finally:
                q.put(sentinel)

        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, _read_sse)

        while True:
            try:
                item = q.get_nowait()
                if item is sentinel:
                    return
                yield item
            except _queue.Empty:
                await asyncio.sleep(0.05)

    # ── Tasks ─────────────────────────────────────────────────────────────

    async def tasks(
        self,
        status: str = None,
        peer_id: str = None,
        created_after: str = None,
        updated_after: str = None,
        sort: str = None,
        cursor: str = None,
        limit: int = None,
    ) -> List[dict]:
        """List tasks with optional filters (v1.4+)."""
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

        path = "/tasks"
        if params:
            path += "?" + "&".join(params)
        data = await self._get(path)
        return data.get("tasks", [])

    async def get_task(self, task_id: str) -> Task:
        """Fetch a single task by id as a Task model."""
        raw = await self._get(f"/tasks/{task_id}")
        _raise_from_response(raw, task_id=task_id)
        return Task.from_dict(raw)

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
        """Update a task's state."""
        body: dict = {"state": state}
        if output:
            body["output"] = output
        if artifact:
            body["artifact"] = artifact
        return await self._post(f"/tasks/{task_id}:update", body)

    async def cancel_task(self, task_id: str, raise_on_terminal: bool = False) -> dict:
        """
        Cancel a task (v1.5.2, idempotent).

        Raises:
            TaskNotCancelableError: If ``raise_on_terminal=True`` and the task
                                    is already in a terminal state.
        """
        resp = await self._post(f"/tasks/{task_id}:cancel", {})
        if raise_on_terminal and resp.get("error") == "ERR_TASK_NOT_CANCELABLE":
            raise TaskNotCancelableError(task_id)
        return resp

    async def continue_task(
        self,
        task_id: str,
        text: str = None,
        parts: List[dict] = None,
    ) -> dict:
        """Resume an input_required task with additional input (v0.5)."""
        body: dict = {}
        if parts:
            body["parts"] = parts
        elif text is not None:
            body["text"] = text
        return await self._post(f"/tasks/{task_id}/continue", body)

    async def wait_for_task(
        self,
        task_id: str,
        timeout: float = 60.0,
        poll_interval: float = 1.0,
    ) -> Task:
        """
        Poll a task until it reaches a terminal state or timeout expires.

        Returns:
            Final Task model (may still be non-terminal on timeout).
        """
        deadline = time.monotonic() + timeout
        task = await self.get_task(task_id)
        while not task.is_terminal() and time.monotonic() < deadline:
            await asyncio.sleep(poll_interval)
            task = await self.get_task(task_id)
        return task

    # ── Skills / QuerySkill ───────────────────────────────────────────────

    async def query_skills(
        self,
        query: str = None,
        skill_id: str = None,
        capability: str = None,
        limit: int = None,
    ) -> dict:
        """Query this agent's available skills (QuerySkill, v0.5)."""
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

    # ── Discover (mDNS, v0.7) ─────────────────────────────────────────────

    async def discover(self) -> List[dict]:
        """
        List LAN peers discovered via mDNS (v0.7).
        Requires relay started with ``--advertise-mdns``.
        """
        data = await self._get("/discover")
        return data.get("peers", [])

    def __repr__(self) -> str:
        return f"<AsyncRelayClient base_url={self.base_url!r}>"
