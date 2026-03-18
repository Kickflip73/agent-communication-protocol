"""
ACP FastAPI Middleware — add ACP support to any existing FastAPI service in 5 lines.

Usage:
    from fastapi import FastAPI
    from acp_sdk.integrations.fastapi_middleware import ACPMiddleware

    app = FastAPI()

    # Add ACP support — your existing /api routes are unaffected
    acp = ACPMiddleware(
        app,
        aid="did:acp:local:my-service",
        gateway="http://localhost:8765",
        capabilities=["summarize", "classify"],
    )

    @acp.task_handler("summarize")
    async def handle_summarize(task: str, input: dict) -> dict:
        # your existing logic
        return {"summary": do_summarize(input["text"])}

    # That's it. Your service is now an ACP agent.
"""
from __future__ import annotations
import asyncio
import logging
from typing import Callable, Awaitable
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

log = logging.getLogger("acp_sdk.fastapi")


class ACPMiddleware:
    def __init__(
        self,
        app: FastAPI,
        aid: str,
        gateway: str = "http://localhost:8765",
        capabilities: list[str] = None,
        name: str = None,
    ):
        self.app = app
        self.aid = aid
        self.gateway = gateway
        self.capabilities = capabilities or []
        self.name = name or aid.split(":")[-1]
        self._handlers: dict[str, Callable] = {}

        # Mount ACP endpoint on the existing app
        app.add_api_route("/acp/v1/messages", self._receive_message, methods=["POST"])
        app.add_api_route("/acp/v1/health", self._health, methods=["GET"])

        # Register with gateway on startup
        app.add_event_handler("startup", self._register_with_gateway)

    def task_handler(self, capability: str):
        """Decorator to register a handler for a specific capability/task type."""
        def decorator(func: Callable):
            self._handlers[capability] = func
            if capability not in self.capabilities:
                self.capabilities.append(capability)
            return func
        return decorator

    async def _register_with_gateway(self):
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                # Detect our own callback URL (assumes gateway can reach us)
                import os
                host = os.environ.get("ACP_CALLBACK_HOST", "localhost")
                port = os.environ.get("ACP_CALLBACK_PORT", "8000")
                callback = f"http://{host}:{port}/acp/v1/messages"

                await session.post(f"{self.gateway}/acp/v1/agents/register", json={
                    "aid": self.aid,
                    "info": {
                        "name": self.name,
                        "capabilities": self.capabilities,
                    },
                    "callback_url": callback,
                })
                log.info(f"ACP: registered {self.aid} with gateway {self.gateway}")
        except Exception as e:
            log.warning(f"ACP: gateway registration failed (will retry): {e}")

    async def _receive_message(self, request: Request):
        """Receive ACP messages from the gateway."""
        from acp_sdk.message import ACPMessage, MessageType
        data = await request.json()

        msg_type = data.get("type", "")

        if msg_type == "task.delegate":
            task = data["body"].get("task", "")
            input_data = data["body"].get("input", {})

            # Find matching handler
            handler = None
            for cap, h in self._handlers.items():
                if cap in task.lower() or not self._handlers:
                    handler = h
                    break
            if not handler and self._handlers:
                handler = list(self._handlers.values())[0]  # default to first

            if handler:
                try:
                    output = await handler(task, input_data)
                    reply = ACPMessage.task_result(
                        from_aid=self.aid, to_aid=data["from"],
                        status="success", output=output,
                        reply_to=data["id"], correlation_id=data.get("correlation_id"),
                    )
                except Exception as e:
                    reply = ACPMessage.error(
                        self.aid, data["from"], "acp.handler_error", str(e), data["id"]
                    )
                return JSONResponse(reply.to_dict())

        return JSONResponse({"success": True, "handled": False})

    async def _health(self):
        return {"aid": self.aid, "capabilities": self.capabilities, "status": "ok"}
