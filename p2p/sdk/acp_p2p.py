"""
ACP-P2P SDK — 去中心化 Agent 通信

两个 Agent 无需任何第三方，直接点对点通信。

快速开始（10行代码）：

    from acp_p2p import P2PAgent

    # Agent A（接收方）
    agent = P2PAgent("summarizer", port=7700)

    @agent.on_task
    async def handle(task, input_data):
        return {"summary": input_data["text"][:50]}

    agent.start()  # 开始监听，打印自己的 ACP URI

    # Agent B（发送方）—— 知道 A 的 URI 就能通信
    result = await agent.send(
        to="acp://192.168.1.42:7700/summarizer",
        task="Summarize this",
        input={"text": "Long article..."}
    )
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import time
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

log = logging.getLogger("acp_p2p")

# ─── ACP URI ─────────────────────────────────────────────────────────────────

@dataclass
class ACPURI:
    """
    Represents an ACP-P2P URI: acp://<host>:<port>/<name>?caps=...&key=...
    """
    host: str
    port: int
    name: str
    caps: list[str] = None
    psk: str = None          # Pre-shared key for v0.1 auth

    @classmethod
    def parse(cls, uri: str) -> "ACPURI":
        if not uri.startswith("acp://"):
            raise ValueError(f"Not an ACP URI: {uri}")
        # Treat as http:// for urlparse
        parsed = urlparse(uri.replace("acp://", "http://", 1))
        qs = parse_qs(parsed.query)
        caps = qs.get("caps", [""])[0].split(",") if qs.get("caps") else []
        caps = [c for c in caps if c]
        return cls(
            host=parsed.hostname or "localhost",
            port=parsed.port or 7700,
            name=parsed.path.lstrip("/"),
            caps=caps,
            psk=qs.get("key", [None])[0],
        )

    def to_string(self, include_caps: bool = True) -> str:
        qs_parts = {}
        if include_caps and self.caps:
            qs_parts["caps"] = ",".join(self.caps)
        if self.psk:
            qs_parts["key"] = self.psk
        qs = urlencode(qs_parts) if qs_parts else ""
        uri = f"acp://{self.host}:{self.port}/{self.name}"
        if qs:
            uri += f"?{qs}"
        return uri

    @property
    def receive_url(self) -> str:
        return f"http://{self.host}:{self.port}/acp/v1/receive"

    @property
    def identity_url(self) -> str:
        return f"http://{self.host}:{self.port}/acp/v1/identity"

    def __str__(self) -> str:
        return self.to_string()


def get_local_ip() -> str:
    """Get the machine's LAN IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ─── Message helpers ─────────────────────────────────────────────────────────

def make_message(
    msg_type: str,
    from_uri: str,
    to_uri: str,
    body: dict,
    correlation_id: str = None,
    reply_to: str = None,
) -> dict:
    return {
        "acp": "0.1",
        "id": "msg_" + uuid.uuid4().hex[:16],
        "type": msg_type,
        "from": from_uri,
        "to": to_uri,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "body": body,
        **({"correlation_id": correlation_id} if correlation_id else {}),
        **({"reply_to": reply_to} if reply_to else {}),
    }


# ─── P2PAgent ────────────────────────────────────────────────────────────────

TaskHandler = Callable[[str, dict], Awaitable[Optional[dict]]]


class P2PAgent:
    """
    去中心化 ACP Agent。

    用法：
        agent = P2PAgent("my-agent", port=7700)

        @agent.on_task
        async def handle(task: str, input: dict) -> dict:
            return {"result": process(input)}

        agent.start()
        # 输出: ACP URI: acp://192.168.1.42:7700/my-agent
        # 另一个 Agent 知道这个 URI 就能直接发消息过来

        # 主动发消息给另一个 Agent
        result = await agent.send(
            to="acp://192.168.1.50:7700/other-agent",
            task="Process this",
            input={"data": "..."},
        )
    """

    def __init__(
        self,
        name: str,
        port: int = 7700,
        host: str = None,           # None = auto-detect LAN IP
        psk: str = None,            # Pre-shared key for auth (optional)
        capabilities: list[str] = None,
        announce_public_ip: bool = False,
    ):
        self.name = name
        self.port = port
        self._psk = psk
        self.capabilities = capabilities or []
        self._task_handler: Optional[TaskHandler] = None
        self._message_handlers: dict[str, Callable] = {}
        self._server = None
        self._app = None

        # Determine host
        if host:
            self._host = host
        elif announce_public_ip:
            self._host = self._get_public_ip()
        else:
            self._host = get_local_ip()

        self.uri = ACPURI(
            host=self._host,
            port=port,
            name=name,
            caps=capabilities,
            psk=psk,
        )

    def _get_public_ip(self) -> str:
        try:
            import urllib.request
            return urllib.request.urlopen("https://api.ipify.org").read().decode()
        except Exception:
            return get_local_ip()

    # ── Decorators ────────────────────────────────────────────────────────────

    def on_task(self, func: TaskHandler) -> TaskHandler:
        """Decorator: handle task.delegate messages."""
        self._task_handler = func
        return func

    def on_message(self, msg_type: str):
        """Decorator: handle a specific message type."""
        def decorator(func):
            self._message_handlers[msg_type] = func
            return func
        return decorator

    # ── Send ──────────────────────────────────────────────────────────────────

    async def send(
        self,
        to: str,
        task: str,
        input: dict = None,
        constraints: dict = None,
        timeout: float = 30.0,
        correlation_id: str = None,
    ) -> Optional[dict]:
        """
        Send a task.delegate to another Agent by its ACP URI.
        Returns the task.result body, or None if async (202 Accepted).

        Example:
            result = await agent.send(
                to="acp://192.168.1.50:7700/worker",
                task="Summarize this text",
                input={"text": "Long article..."},
            )
            print(result["output"])
        """
        target = ACPURI.parse(to) if isinstance(to, str) else to
        msg = make_message(
            msg_type="task.delegate",
            from_uri=str(self.uri),
            to_uri=str(target),
            body={
                "task": task,
                "input": input or {},
                "constraints": constraints or {},
            },
            correlation_id=correlation_id or "corr_" + uuid.uuid4().hex[:8],
        )
        return await self._post(target.receive_url, msg, target.psk, timeout)

    async def send_raw(self, to: str, msg: dict, timeout: float = 30.0) -> Optional[dict]:
        """Send a raw ACP message dict to a URI."""
        target = ACPURI.parse(to) if isinstance(to, str) else to
        return await self._post(target.receive_url, msg, target.psk, timeout)

    async def discover(self, uri: str) -> Optional[dict]:
        """
        Fetch identity info from a remote Agent.
        Returns their identity dict (name, caps, uri) or None.
        """
        target = ACPURI.parse(uri)
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(target.identity_url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                    if r.status == 200:
                        return await r.json()
        except Exception as e:
            log.warning(f"discover({uri}) failed: {e}")
        return None

    async def _post(self, url: str, msg: dict, psk: str, timeout: float) -> Optional[dict]:
        try:
            import aiohttp
        except ImportError:
            raise ImportError("pip install aiohttp")

        headers = {"Content-Type": "application/json"}
        if psk:
            headers["X-ACP-PSK"] = psk

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=msg, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=timeout)
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    elif resp.status == 202:
                        return None  # Async, result comes via callback
                    else:
                        text = await resp.text()
                        log.error(f"POST {url} → {resp.status}: {text[:200]}")
                        return None
        except aiohttp.ClientConnectorError as e:
            raise ConnectionError(f"Cannot reach {url}: {e}")

    # ── Server ────────────────────────────────────────────────────────────────

    def start(self, block: bool = True, print_uri: bool = True):
        """
        Start the P2P agent server.

        block=True:  runs until Ctrl+C (suitable for standalone agents)
        block=False: starts in background (suitable for embedding in existing apps)
        """
        if print_uri:
            print(f"\n🔗 ACP URI: {self.uri}")
            print(f"   Share this URI with agents that need to reach you.\n")

        if block:
            asyncio.run(self._run_server())
        else:
            loop = asyncio.get_event_loop()
            loop.create_task(self._run_server())

    async def _run_server(self):
        """Start the HTTP server that receives ACP messages."""
        try:
            from aiohttp import web
        except ImportError:
            raise ImportError("pip install aiohttp")

        from aiohttp import web

        app = web.Application()
        app.router.add_post("/acp/v1/receive", self._handle_receive)
        app.router.add_get("/acp/v1/identity", self._handle_identity)
        app.router.add_get("/acp/v1/health", self._handle_health)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", self.port)
        await site.start()

        log.info(f"ACP-P2P: {self.name} listening on 0.0.0.0:{self.port}")

        # Keep running
        try:
            while True:
                await asyncio.sleep(3600)
        finally:
            await runner.cleanup()

    async def _handle_receive(self, request):
        from aiohttp import web

        # PSK auth check
        if self._psk:
            incoming_psk = request.headers.get("X-ACP-PSK", "")
            if incoming_psk != self._psk:
                return web.json_response({"error": "Unauthorized"}, status=401)

        try:
            msg = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        msg_type = msg.get("type", "")
        log.debug(f"[{self.name}] received {msg_type} from {msg.get('from', '?')}")

        # Route to appropriate handler
        if msg_type == "task.delegate":
            reply = await self._handle_task(msg)
        elif msg_type == "agent.hello":
            reply = self._make_hello_reply(msg)
        elif msg_type in self._message_handlers:
            reply = await self._message_handlers[msg_type](msg)
        else:
            # Acknowledge unknown types gracefully
            return web.json_response({"success": True, "handled": False}, status=202)

        if reply:
            return web.json_response(reply, status=200)
        return web.json_response({"success": True}, status=202)

    async def _handle_task(self, msg: dict) -> Optional[dict]:
        if not self._task_handler:
            return self._error_reply(msg, "acp.capability_missing", "No task handler registered")

        task = msg["body"].get("task", "")
        input_data = msg["body"].get("input", {})

        try:
            output = await self._task_handler(task, input_data)
            return make_message(
                msg_type="task.result",
                from_uri=str(self.uri),
                to_uri=msg["from"],
                body={"status": "success", "output": output or {}},
                reply_to=msg["id"],
                correlation_id=msg.get("correlation_id"),
            )
        except Exception as e:
            log.exception(f"[{self.name}] task handler error")
            return self._error_reply(msg, "acp.handler_error", str(e))

    def _handle_identity(self, request):
        from aiohttp import web
        return web.json_response({
            "uri": str(self.uri),
            "name": self.name,
            "capabilities": self.capabilities,
            "acp_version": "0.1",
            "protocol": "acp-p2p",
        })

    def _handle_health(self, request):
        from aiohttp import web
        return web.json_response({"status": "ok", "name": self.name, "uri": str(self.uri)})

    def _make_hello_reply(self, msg: dict) -> dict:
        return make_message(
            msg_type="agent.hello",
            from_uri=str(self.uri),
            to_uri=msg["from"],
            body={
                "name": self.name,
                "capabilities": self.capabilities,
                "acp_version": "0.1",
            },
            reply_to=msg["id"],
        )

    def _error_reply(self, msg: dict, code: str, message: str) -> dict:
        return make_message(
            msg_type="error",
            from_uri=str(self.uri),
            to_uri=msg.get("from", "unknown"),
            body={"code": code, "message": message},
            reply_to=msg.get("id"),
        )

    # ── Context manager support ────────────────────────────────────────────────

    async def __aenter__(self):
        asyncio.get_event_loop().create_task(self._run_server())
        await asyncio.sleep(0.1)  # Let server start
        return self

    async def __aexit__(self, *args):
        pass  # Server will stop when loop ends
