#!/usr/bin/env python3
"""
ACP Public Relay Server
=======================
中继服务器：运行在公网，负责转发两个 Relay 之间的消息。
Agent 侧不需要公网 IP，通过连接到这里的 Session 互相通信。

依赖: pip install websockets
运行: python3 relay_server.py [--host 0.0.0.0] [--port 7800]
"""
import asyncio
import json
import uuid
import time
import argparse
import logging
import signal
from typing import Any
try:
    import websockets
    
except ImportError:
    print("ERROR: pip install websockets")
    raise

logging.basicConfig(level=logging.INFO, format="%(asctime)s [relay] %(message)s")
log = logging.getLogger("acp-relay-server")

# session_id -> {peer_id -> websocket}
SESSIONS: dict[str, dict[str, Any]] = {}
SESSION_META: dict[str, dict] = {}   # session_id -> {created_at, creator}


def new_session_id() -> str:
    return uuid.uuid4().hex[:16]


def new_peer_id() -> str:
    return "peer_" + uuid.uuid4().hex[:8]


async def broadcast(session_id: str, sender_peer_id: str, message: dict):
    """Send message to all peers in session except the sender."""
    session = SESSIONS.get(session_id, {})
    dead = []
    for peer_id, ws in session.items():
        if peer_id == sender_peer_id:
            continue
        try:
            await ws.send(json.dumps(message))
        except Exception:
            dead.append(peer_id)
    for p in dead:
        session.pop(p, None)


async def handle_connection(websocket: Any):
    peer_id = new_peer_id()
    session_id = None

    try:
        # First message must be a join or create
        raw = await asyncio.wait_for(websocket.recv(), timeout=15.0)
        init = json.loads(raw)

        action = init.get("action")

        if action == "create":
            # Create a new session and return its ID
            session_id = new_session_id()
            SESSIONS[session_id] = {peer_id: websocket}
            SESSION_META[session_id] = {
                "created_at": time.time(),
                "creator": init.get("agent_name", "unknown"),
                "peer_count": 1,
            }
            await websocket.send(json.dumps({
                "type": "session.created",
                "session_id": session_id,
                "peer_id": peer_id,
                "link": f"acp://relay/{session_id}",
            }))
            log.info(f"Session created: {session_id} by {peer_id}")

        elif action == "join":
            # Join an existing session
            session_id = init.get("session_id")
            if not session_id or session_id not in SESSIONS:
                await websocket.send(json.dumps({
                    "type": "error",
                    "code": "session_not_found",
                    "message": f"Session '{session_id}' not found or expired.",
                }))
                return

            SESSIONS[session_id][peer_id] = websocket
            SESSION_META[session_id]["peer_count"] = len(SESSIONS[session_id])
            await websocket.send(json.dumps({
                "type": "session.joined",
                "session_id": session_id,
                "peer_id": peer_id,
                "peer_count": len(SESSIONS[session_id]),
            }))
            # Notify others that a new peer joined
            await broadcast(session_id, peer_id, {
                "type": "peer.joined",
                "peer_id": peer_id,
                "peer_count": len(SESSIONS[session_id]),
            })
            log.info(f"Peer {peer_id} joined session {session_id}")

        else:
            await websocket.send(json.dumps({
                "type": "error",
                "code": "invalid_init",
                "message": "First message must have action=create or action=join",
            }))
            return

        # Main message loop
        async for raw_msg in websocket:
            try:
                msg = json.loads(raw_msg)
                msg["_from_peer"] = peer_id
                msg["_session_id"] = session_id
                await broadcast(session_id, peer_id, msg)
            except json.JSONDecodeError:
                await websocket.send(json.dumps({
                    "type": "error",
                    "code": "invalid_json",
                }))

    except asyncio.TimeoutError:
        log.warning(f"Peer {peer_id} timed out during init")
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        # Cleanup
        if session_id and session_id in SESSIONS:
            SESSIONS[session_id].pop(peer_id, None)
            if not SESSIONS[session_id]:
                del SESSIONS[session_id]
                SESSION_META.pop(session_id, None)
                log.info(f"Session {session_id} closed (no peers)")
            else:
                await broadcast(session_id, peer_id, {
                    "type": "peer.left",
                    "peer_id": peer_id,
                    "peer_count": len(SESSIONS[session_id]),
                })


async def status_handler(websocket: Any):
    """Return server status (connected at /status)."""
    await websocket.send(json.dumps({
        "type": "server.status",
        "active_sessions": len(SESSIONS),
        "sessions": {
            sid: {"peer_count": len(peers), **SESSION_META.get(sid, {})}
            for sid, peers in SESSIONS.items()
        }
    }))


async def main(host: str, port: int):
    log.info(f"ACP Relay Server starting on ws://{host}:{port}")

    async def router(websocket: Any):
        path = websocket.request.path if hasattr(websocket, 'request') else getattr(websocket, 'path', '/')
        if path == "/status":
            await status_handler(websocket)
        else:
            await handle_connection(websocket)

    async with websockets.serve(router, host, port):
        log.info(f"✓ Relay server ready at ws://{host}:{port}")
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ACP Relay Server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=7800)
    args = parser.parse_args()
    asyncio.run(main(args.host, args.port))
