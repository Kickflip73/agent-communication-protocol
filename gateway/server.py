"""
ACP Gateway — lightweight message router + agent registry.
Run: python server.py  (or via Docker)

Agents register themselves on startup, then send/receive messages through the gateway.
No peer-to-peer addressing needed — agents only talk to the gateway.
"""
import asyncio
import json
import logging
import time
import uuid
from typing import Optional
from contextlib import asynccontextmanager

try:
    from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
    from fastapi.responses import JSONResponse
    import uvicorn
except ImportError:
    raise ImportError("pip install fastapi uvicorn")

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'sdk', 'python'))
from acp_sdk.message import ACPMessage, MessageType

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("acp-gateway")

# ─── Registry ────────────────────────────────────────────────────────────────

class AgentRegistry:
    def __init__(self):
        self._agents: dict[str, dict] = {}          # aid → info
        self._ws_connections: dict[str, WebSocket] = {}  # aid → websocket
        self._http_callbacks: dict[str, str] = {}   # aid → callback URL

    def register(self, aid: str, info: dict, callback_url: str = None):
        self._agents[aid] = {
            "aid": aid,
            "name": info.get("name", aid),
            "capabilities": info.get("capabilities", []),
            "metadata": info.get("metadata", {}),
            "registered_at": time.time(),
            "status": "available",
        }
        if callback_url:
            self._http_callbacks[aid] = callback_url
        log.info(f"Registered: {aid} caps={info.get('capabilities', [])}")

    def unregister(self, aid: str):
        self._agents.pop(aid, None)
        self._http_callbacks.pop(aid, None)
        self._ws_connections.pop(aid, None)
        log.info(f"Unregistered: {aid}")

    def attach_ws(self, aid: str, ws: WebSocket):
        self._ws_connections[aid] = ws

    def detach_ws(self, aid: str):
        self._ws_connections.pop(aid, None)

    def get(self, aid: str) -> Optional[dict]:
        return self._agents.get(aid)

    def find_by_capability(self, capability: str) -> list[dict]:
        return [a for a in self._agents.values()
                if capability in a.get("capabilities", [])]

    def all_agents(self) -> list[dict]:
        return list(self._agents.values())

    async def deliver(self, msg: ACPMessage) -> Optional[dict]:
        """Deliver message to recipient. Returns response if sync, else None."""
        to = msg.to

        # WebSocket delivery (preferred — real-time)
        ws = self._ws_connections.get(to)
        if ws:
            try:
                await ws.send_text(msg.to_json())
                log.debug(f"WS delivered: {msg.type} → {to}")
                return None  # Async; response comes via separate message
            except Exception as e:
                log.warning(f"WS delivery failed for {to}: {e}")
                self.detach_ws(to)

        # HTTP callback delivery
        callback = self._http_callbacks.get(to)
        if callback:
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        callback, json=msg.to_dict(), timeout=aiohttp.ClientTimeout(total=30)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            return data
                        log.warning(f"HTTP callback returned {resp.status} for {to}")
            except Exception as e:
                log.warning(f"HTTP callback failed for {to}: {e}")

        return None  # Agent not reachable

registry = AgentRegistry()

# ─── Message store (in-memory, for agents polling) ───────────────────────────

class MessageStore:
    def __init__(self):
        self._queues: dict[str, list[dict]] = {}

    def enqueue(self, aid: str, msg_dict: dict):
        self._queues.setdefault(aid, []).append(msg_dict)

    def dequeue(self, aid: str, limit: int = 10) -> list[dict]:
        q = self._queues.get(aid, [])
        msgs, self._queues[aid] = q[:limit], q[limit:]
        return msgs

msg_store = MessageStore()

# ─── FastAPI app ──────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("ACP Gateway starting...")
    yield
    log.info("ACP Gateway stopped.")

app = FastAPI(
    title="ACP Gateway",
    description="Agent Communication Protocol — Message Router & Registry",
    version="0.1.0",
    lifespan=lifespan,
)

# ─── REST endpoints ───────────────────────────────────────────────────────────

@app.get("/acp/v1/health")
async def health():
    return {"status": "ok", "agents": len(registry.all_agents())}


@app.post("/acp/v1/agents/register")
async def register_agent(request: Request):
    """Register an agent. Call this on startup."""
    data = await request.json()
    aid = data.get("aid")
    if not aid:
        raise HTTPException(400, "Missing 'aid'")
    registry.register(aid, data.get("info", {}), data.get("callback_url"))
    return {"success": True, "aid": aid}


@app.delete("/acp/v1/agents/{aid_encoded}")
async def unregister_agent(aid_encoded: str):
    aid = aid_encoded.replace("_", ":")
    registry.unregister(aid)
    return {"success": True}


@app.get("/acp/v1/agents")
async def list_agents(capability: str = None):
    """Discover agents, optionally filtered by capability."""
    agents = registry.find_by_capability(capability) if capability else registry.all_agents()
    return {"agents": agents}


@app.post("/acp/v1/messages")
async def send_message(request: Request):
    """
    Send an ACP message. The gateway routes it to the recipient.

    Returns:
    - 200 + reply body: if recipient responded synchronously (HTTP callback)
    - 202 Accepted: message delivered async (WebSocket) or queued
    - 404: recipient not found
    """
    data = await request.json()
    try:
        msg = ACPMessage.from_dict(data)
    except Exception as e:
        raise HTTPException(400, f"Invalid ACP message: {e}")

    # Validate recipient exists (for non-topic messages)
    to = msg.to
    if not to.startswith("topic:"):
        if not registry.get(to):
            # Queue it anyway (agent might register soon), but warn
            log.warning(f"Unknown recipient: {to} — queueing message")
            msg_store.enqueue(to, data)
            return JSONResponse({"success": True, "queued": True}, status_code=202)

    # Try to deliver
    response = await registry.deliver(msg)
    if response:
        return JSONResponse(response, status_code=200)

    # Queue for polling agents
    msg_store.enqueue(to, data)
    return JSONResponse({"success": True, "delivered": "queued"}, status_code=202)


@app.get("/acp/v1/messages/inbox/{aid_encoded}")
async def poll_inbox(aid_encoded: str, limit: int = 10):
    """
    Poll for messages (for agents that can't receive WebSocket/HTTP callbacks).
    Simple long-polling alternative.
    """
    aid = aid_encoded.replace("__COLON__", ":")
    msgs = msg_store.dequeue(aid, limit)
    return {"messages": msgs, "count": len(msgs)}


# ─── WebSocket endpoint ───────────────────────────────────────────────────────

@app.websocket("/acp/v1/ws/{aid_encoded}")
async def ws_endpoint(websocket: WebSocket, aid_encoded: str):
    """
    WebSocket connection for real-time bidirectional messaging.
    aid_encoded: replace ':' with '__COLON__'

    Protocol:
    1. Client connects
    2. Client sends agent.hello to register
    3. Gateway delivers incoming messages as JSON text frames
    4. Client sends messages (routed by gateway)
    """
    aid = aid_encoded.replace("__COLON__", ":")
    await websocket.accept()
    registry.attach_ws(aid, websocket)
    log.info(f"WS connected: {aid}")

    # Flush any queued messages
    queued = msg_store.dequeue(aid)
    for qmsg in queued:
        await websocket.send_text(json.dumps(qmsg))

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = ACPMessage.from_dict(json.loads(raw))
            except Exception as e:
                await websocket.send_text(json.dumps({"error": f"Invalid message: {e}"}))
                continue

            # Handle agent.hello (registration)
            if msg.type == MessageType.AGENT_HELLO:
                registry.register(aid, msg.body)
                log.info(f"WS agent.hello from {aid}")
                continue

            # Route to recipient
            response = await registry.deliver(msg)
            if response:
                await websocket.send_text(json.dumps(response))

    except WebSocketDisconnect:
        registry.detach_ws(aid)
        log.info(f"WS disconnected: {aid}")


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8765, log_level="info")
