#!/usr/bin/env python3
"""
ACP P2P Relay v0.3
==================
Zero-server, zero-code-change P2P Agent communication.

Communication modes (参考 A2A v1.0):
  1. Sync    — POST /send + wait for reply_to correlation      (request/response)
  2. Async   — POST /tasks/create → GET /tasks/{id}  polling   (fire-and-forget)
  3. Stream  — GET /stream  SSE push                           (real-time events)
  4. Push    — Agent registers webhook; daemon POSTs updates   (callback)

Usage:
  python3 acp_relay.py --name "Agent-A" --skills "summarize,code-review"
  python3 acp_relay.py --name "Agent-B" --join acp://1.2.3.4:7801/tok_xxx

Requires: pip install websockets
"""
import asyncio
import json
import uuid
import time
import argparse
import logging
import threading
import signal
import sys
import socket
import os
from collections import deque
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import urllib.request
import urllib.error
import datetime

try:
    import websockets
    import websockets.exceptions
except ImportError:
    print("❌ Missing dependency: pip install websockets")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [acp] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("acp-p2p")

VERSION = "0.3"

# ── Task lifecycle states (A2A-aligned) ───────────────────────────────────────
TASK_SUBMITTED  = "submitted"
TASK_WORKING    = "working"
TASK_COMPLETED  = "completed"
TASK_FAILED     = "failed"
TASK_CANCELLED  = "cancelled"
TERMINAL_STATES = {TASK_COMPLETED, TASK_FAILED, TASK_CANCELLED}

# ── Global state ──────────────────────────────────────────────────────────────
_recv_queue: deque = deque(maxlen=1000)       # raw incoming messages
_peer_ws    = None
_loop       = None
_inbox_path: str | None = None

# Task registry  {task_id -> task_dict}
_tasks: dict[str, dict] = {}

# Pending sync calls  {correlation_id -> asyncio.Future}
_sync_pending: dict[str, asyncio.Future] = {}

# SSE subscribers  [deque, ...]
_sse_subscribers: list[deque] = []

# Push-notification webhooks  [url, ...]
_push_webhooks: list[str] = []

_status: dict = {
    "acp_version":       VERSION,
    "connected":         False,
    "role":              None,
    "link":              None,
    "agent_name":        None,
    "agent_card":        None,
    "peer_card":         None,
    "ws_port":           7801,
    "http_port":         7901,
    "messages_sent":     0,
    "messages_received": 0,
    "reconnect_count":   0,
    "tasks_created":     0,
    "started_at":        None,
}
# ─────────────────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"

def _make_id(prefix="msg") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"

def _make_token() -> str:
    return "tok_" + uuid.uuid4().hex[:16]

def _make_agent_card(name: str, skills: list[str]) -> dict:
    return {
        "name":        name,
        "version":     "1.0.0",
        "acp_version": VERSION,
        "skills":      skills,
        "description": f"ACP P2P Agent: {name}",
        "http_port":   _status["http_port"],
        "timestamp":   _now(),
        "communication_modes": ["sync", "async", "stream", "push"],
    }

# ── Task helpers ──────────────────────────────────────────────────────────────

def _create_task(payload: dict) -> dict:
    task_id = _make_id("task")
    task = {
        "id":         task_id,
        "status":     TASK_SUBMITTED,
        "created_at": _now(),
        "updated_at": _now(),
        "payload":    payload,
        "artifacts":  [],
        "history":    [],
    }
    _tasks[task_id] = task
    _status["tasks_created"] += 1
    return task

def _update_task(task_id: str, status: str, artifact=None, error=None) -> dict | None:
    task = _tasks.get(task_id)
    if not task:
        return None
    task["status"]     = status
    task["updated_at"] = _now()
    if artifact:
        task["artifacts"].append(artifact)
    if error:
        task["error"] = error
    # broadcast task update via SSE and push
    _broadcast_event({
        "event":   "task.updated",
        "task_id": task_id,
        "status":  status,
        "artifact": artifact,
    })
    return task

# ── SSE + Push broadcast ──────────────────────────────────────────────────────

def _broadcast_event(event: dict):
    """Fan-out an event to all SSE subscribers and registered push webhooks."""
    event.setdefault("ts", _now())
    # SSE
    for q in _sse_subscribers:
        q.append(event)
    # Push webhooks (fire-and-forget in a thread)
    if _push_webhooks:
        body = json.dumps(event, ensure_ascii=False).encode()
        for url in list(_push_webhooks):
            threading.Thread(target=_deliver_push, args=(url, body), daemon=True).start()

def _deliver_push(url: str, body: bytes):
    try:
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
        log.info(f"📤 Push delivered → {url}")
    except Exception as e:
        log.warning(f"Push failed → {url}: {e}")

# ── Persistence ───────────────────────────────────────────────────────────────

def _persist(entry: dict):
    if _inbox_path:
        try:
            with open(_inbox_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

# ── Incoming message handler ──────────────────────────────────────────────────

def _on_message(raw: str):
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("Received non-JSON frame, ignored")
        return

    msg_type = msg.get("type", "")

    # ── Internal: AgentCard exchange ──────────────────────────────────────────
    if msg_type == "acp.agent_card":
        _status["peer_card"] = msg.get("card")
        peer = msg.get("card", {})
        log.info(f"📋 AgentCard received: {peer.get('name')} | skills: {peer.get('skills')}")
        return

    # ── Internal: sync reply ──────────────────────────────────────────────────
    if msg_type == "acp.reply":
        corr = msg.get("correlation_id")
        if corr and corr in _sync_pending:
            fut = _sync_pending.pop(corr)
            if not fut.done():
                _loop.call_soon_threadsafe(fut.set_result, msg)
        return

    # ── Internal: task status update from peer ────────────────────────────────
    if msg_type == "task.updated":
        task_id = msg.get("task_id")
        if task_id and task_id in _tasks:
            _update_task(task_id, msg.get("status", TASK_WORKING),
                         artifact=msg.get("artifact"))
        _broadcast_event(msg)
        return

    # ── Business message ──────────────────────────────────────────────────────
    entry = {
        "id":          msg.get("id", _make_id()),
        "received_at": time.time(),
        "content":     msg,
    }
    _recv_queue.append(entry)
    _persist(entry)
    _status["messages_received"] += 1
    _broadcast_event({"event": "message.received", "message": msg})
    log.info(f"📨 Received: type={msg_type} from={msg.get('from','?')}")

# ── WebSocket send helpers ────────────────────────────────────────────────────

async def _ws_send(msg: dict):
    if _peer_ws is None:
        raise ConnectionError("No P2P connection (waiting or reconnecting)")
    await _peer_ws.send(json.dumps(msg, ensure_ascii=False))
    _status["messages_sent"] += 1

def _ws_send_sync(msg: dict):
    future = asyncio.run_coroutine_threadsafe(_ws_send(msg), _loop)
    future.result(timeout=10)

async def _send_agent_card(ws):
    card_msg = {
        "type": "acp.agent_card",
        "id":   _make_id(),
        "ts":   _now(),
        "card": _status["agent_card"],
    }
    await ws.send(json.dumps(card_msg))


# ══════════════════════════════════════════════════════════════════════════════
# HOST mode
# ══════════════════════════════════════════════════════════════════════════════

async def host_mode(token: str, ws_port: int, http_port: int):
    global _peer_ws

    async def on_guest(websocket):
        global _peer_ws
        try:
            path = websocket.request.path
        except AttributeError:
            path = getattr(websocket, "path", "/")

        if path.strip("/") != token:
            await websocket.send(json.dumps({"type": "error", "code": "invalid_token"}))
            await websocket.close()
            return

        _peer_ws = websocket
        _status["connected"] = True
        _status["started_at"] = _status["started_at"] or time.time()
        await _send_agent_card(websocket)
        _broadcast_event({"event": "peer.connected"})

        print(f"\n{'='*55}")
        print(f"✅ Peer connected — P2P channel established (no server)")
        print(f"   Send:   POST http://localhost:{http_port}/send")
        print(f"   Recv:   GET  http://localhost:{http_port}/recv")
        print(f"   Stream: GET  http://localhost:{http_port}/stream")
        print(f"{'='*55}\n")

        try:
            async for raw in websocket:
                _on_message(raw)
        except websockets.exceptions.ConnectionClosed:
            log.info("Peer disconnected")
        finally:
            _peer_ws = None
            _status["connected"] = False
            _status["peer_card"] = None
            _broadcast_event({"event": "peer.disconnected"})

    log.info("Detecting public IP...")
    public_ip = await asyncio.get_event_loop().run_in_executor(
        None, lambda: get_public_ip(4.0)
    )
    display_ip = public_ip or get_local_ip()
    link = f"acp://{display_ip}:{ws_port}/{token}"
    _status["link"] = link

    async with websockets.serve(on_guest, "0.0.0.0", ws_port):
        print(f"\n{'='*60}")
        print(f"✅ ACP P2P v{VERSION} — service started")
        print(f"   IP: {'public' if public_ip else 'LAN'} {display_ip}")
        print(f"")
        print(f"🔗 Your link (forward to the other agent):")
        print(f"   {link}")
        print(f"")
        print(f"⏳ Waiting for peer...")
        print(f"{'='*60}\n")
        await asyncio.Future()


# ══════════════════════════════════════════════════════════════════════════════
# GUEST mode (with auto-reconnect)
# ══════════════════════════════════════════════════════════════════════════════

async def guest_mode(host: str, ws_port: int, token: str, http_port: int):
    global _peer_ws
    uri = f"ws://{host}:{ws_port}/{token}"
    MAX_RETRIES = 10
    retry = 0

    while retry < MAX_RETRIES:
        try:
            log.info(f"{'Reconnecting #' + str(retry) if retry else 'Connecting to'}: {uri}")
            async with websockets.connect(uri, ping_interval=20, ping_timeout=10) as ws:
                _peer_ws = ws
                _status["connected"] = True
                _status["started_at"] = _status["started_at"] or time.time()
                if retry > 0:
                    _status["reconnect_count"] += 1
                await _send_agent_card(ws)
                _broadcast_event({"event": "peer.connected"})

                print(f"\n{'='*55}")
                print(f"✅ {'Reconnected' if retry else 'Connected'} — P2P direct (no server)")
                print(f"   Peer: {host}:{ws_port}")
                print(f"   Send:   POST http://localhost:{http_port}/send")
                print(f"   Recv:   GET  http://localhost:{http_port}/recv")
                print(f"   Stream: GET  http://localhost:{http_port}/stream")
                print(f"{'='*55}\n")

                retry = 0
                async for raw in ws:
                    _on_message(raw)

        except ConnectionRefusedError:
            log.warning(f"Connection refused — retry in {2**retry}s ({retry+1}/{MAX_RETRIES})")
        except websockets.exceptions.ConnectionClosed:
            log.info(f"Connection closed — retry in {2**retry}s ({retry+1}/{MAX_RETRIES})")
        except OSError as e:
            log.warning(f"Network error: {e} — retry in {2**retry}s")
        finally:
            _peer_ws = None
            _status["connected"] = False
            _status["peer_card"] = None
            _broadcast_event({"event": "peer.disconnected"})

        retry += 1
        if retry < MAX_RETRIES:
            await asyncio.sleep(min(2 ** retry, 60))

    print(f"\n❌ Gave up after {MAX_RETRIES} retries")
    sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════════
# Local HTTP interface
# ══════════════════════════════════════════════════════════════════════════════

class LocalHTTP(BaseHTTPRequestHandler):
    def log_message(self, *_): pass

    # ── helpers ───────────────────────────────────────────────────────────────

    def _json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n) if n else b"{}"
        return json.loads(raw) if raw.strip() else {}

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # ── GET ───────────────────────────────────────────────────────────────────

    def do_GET(self):
        parsed = urlparse(self.path)
        p  = parsed.path
        qs = parse_qs(parsed.query)

        # ── status / link / card ──────────────────────────────────────────────
        if p == "/status":
            self._json(_status)

        elif p == "/link":
            self._json({"link": _status.get("link")})

        elif p == "/card":
            self._json({"self": _status.get("agent_card"), "peer": _status.get("peer_card")})

        # ── [1] SYNC: wait for correlated reply ───────────────────────────────
        # GET /wait/{correlation_id}?timeout=30
        elif p.startswith("/wait/"):
            corr    = p[len("/wait/"):]
            timeout = float(qs.get("timeout", ["30"])[0])
            future: asyncio.Future = _loop.create_future()
            _sync_pending[corr] = future
            try:
                result = asyncio.run_coroutine_threadsafe(
                    asyncio.wait_for(asyncio.shield(future), timeout=timeout), _loop
                ).result(timeout=timeout + 2)
                _sync_pending.pop(corr, None)
                self._json({"ok": True, "reply": result})
            except asyncio.TimeoutError:
                _sync_pending.pop(corr, None)
                self._json({"ok": False, "error": "timeout"}, 408)
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)

        # ── [2] ASYNC: recv queue / task polling ──────────────────────────────
        elif p == "/recv":
            limit = int(qs.get("limit", ["50"])[0])
            msgs  = [_recv_queue.popleft() for _ in range(min(limit, len(_recv_queue)))]
            self._json({"messages": msgs, "count": len(msgs), "remaining": len(_recv_queue)})

        elif p == "/tasks":
            status_filter = qs.get("status", [None])[0]
            tasks = list(_tasks.values())
            if status_filter:
                tasks = [t for t in tasks if t["status"] == status_filter]
            self._json({"tasks": tasks, "count": len(tasks)})

        elif p.startswith("/tasks/"):
            task_id = p[len("/tasks/"):]
            task = _tasks.get(task_id)
            if task:
                self._json(task)
            else:
                self._json({"error": "task not found"}, 404)

        # ── history ───────────────────────────────────────────────────────────
        elif p == "/history":
            history = []
            if _inbox_path and os.path.exists(_inbox_path):
                with open(_inbox_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                history.append(json.loads(line))
                            except Exception:
                                pass
            limit = int(qs.get("limit", ["100"])[0])
            self._json({"history": history[-limit:], "total": len(history)})

        # ── [3] STREAM: SSE real-time events ──────────────────────────────────
        elif p == "/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            q: deque = deque()
            _sse_subscribers.append(q)
            try:
                while True:
                    if q:
                        evt = q.popleft()
                        data = f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
                        self.wfile.write(data.encode())
                        self.wfile.flush()
                    else:
                        self.wfile.write(b": keepalive\n\n")
                        self.wfile.flush()
                        time.sleep(1)
            except Exception:
                pass
            finally:
                if q in _sse_subscribers:
                    _sse_subscribers.remove(q)

        else:
            self._json({"error": "not found"}, 404)

    # ── POST ──────────────────────────────────────────────────────────────────

    def do_POST(self):
        parsed = urlparse(self.path)
        p = parsed.path

        # ── [1] SYNC send: fire + block until correlated reply ────────────────
        # POST /send  body: {..., "sync": true, "timeout": 30}
        # POST /send  body: {...}  (async, no wait)
        if p == "/send":
            try:
                msg = self._read_body()
                msg.setdefault("id",   _make_id())
                msg.setdefault("ts",   _now())
                msg.setdefault("from", _status.get("agent_name", "unknown"))

                want_sync = msg.pop("sync", False)
                timeout   = float(msg.pop("timeout", 30))

                if want_sync:
                    corr = msg.get("id")  # use msg id as correlation key
                    msg["correlation_id"] = corr
                    future: asyncio.Future = _loop.create_future()
                    _sync_pending[corr] = future
                    _ws_send_sync(msg)
                    try:
                        reply = asyncio.run_coroutine_threadsafe(
                            asyncio.wait_for(asyncio.shield(future), timeout=timeout), _loop
                        ).result(timeout=timeout + 2)
                        _sync_pending.pop(corr, None)
                        self._json({"ok": True, "id": corr, "reply": reply})
                    except asyncio.TimeoutError:
                        _sync_pending.pop(corr, None)
                        self._json({"ok": False, "error": "reply timeout"}, 408)
                else:
                    _ws_send_sync(msg)
                    self._json({"ok": True, "id": msg["id"]})

            except ConnectionError as e:
                self._json({"ok": False, "error": str(e)}, 503)
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)

        # ── [1] SYNC reply: respond to a received message ─────────────────────
        # POST /reply  body: {"correlation_id": "...", "content": ...}
        elif p == "/reply":
            try:
                body = self._read_body()
                msg = {
                    "type":           "acp.reply",
                    "id":             _make_id(),
                    "ts":             _now(),
                    "from":           _status.get("agent_name", "unknown"),
                    "correlation_id": body.get("correlation_id"),
                    "content":        body.get("content"),
                }
                _ws_send_sync(msg)
                self._json({"ok": True})
            except ConnectionError as e:
                self._json({"ok": False, "error": str(e)}, 503)
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)

        # ── [2] ASYNC: create a task ──────────────────────────────────────────
        # POST /tasks/create  body: {payload, delegate: true/false}
        elif p == "/tasks/create":
            try:
                body    = self._read_body()
                task    = _create_task(body.get("payload", body))
                # optionally delegate to peer immediately
                if body.get("delegate", False):
                    delegate_msg = {
                        "type":    "task.delegate",
                        "id":      _make_id(),
                        "ts":      _now(),
                        "from":    _status.get("agent_name", "unknown"),
                        "task_id": task["id"],
                        "payload": task["payload"],
                    }
                    _ws_send_sync(delegate_msg)
                self._json({"ok": True, "task": task}, 201)
            except ConnectionError as e:
                self._json({"ok": False, "error": str(e)}, 503)
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)

        # ── [2] ASYNC: update task status (called by peer's agent) ────────────
        # POST /tasks/{id}/update  body: {status, artifact?, error?}
        elif p.startswith("/tasks/") and p.endswith("/update"):
            task_id = p[len("/tasks/"):-len("/update")]
            try:
                body = self._read_body()
                task = _update_task(
                    task_id,
                    body.get("status", TASK_WORKING),
                    artifact=body.get("artifact"),
                    error=body.get("error"),
                )
                if task is None:
                    self._json({"error": "task not found"}, 404)
                else:
                    # notify peer of status change
                    notify_msg = {
                        "type":     "task.updated",
                        "id":       _make_id(),
                        "ts":       _now(),
                        "from":     _status.get("agent_name", "unknown"),
                        "task_id":  task_id,
                        "status":   body.get("status", TASK_WORKING),
                        "artifact": body.get("artifact"),
                    }
                    try:
                        _ws_send_sync(notify_msg)
                    except ConnectionError:
                        pass  # peer may be offline; task state still updated locally
                    self._json({"ok": True, "task": task})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)

        # ── [4] PUSH: register / deregister webhook ───────────────────────────
        # POST /webhooks/register  body: {"url": "https://..."}
        elif p == "/webhooks/register":
            try:
                body = self._read_body()
                url  = body.get("url", "").strip()
                if not url:
                    self._json({"error": "url required"}, 400)
                    return
                if url not in _push_webhooks:
                    _push_webhooks.append(url)
                log.info(f"📌 Webhook registered: {url}")
                self._json({"ok": True, "registered": url, "total": len(_push_webhooks)})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)

        elif p == "/webhooks/deregister":
            try:
                body = self._read_body()
                url  = body.get("url", "").strip()
                if url in _push_webhooks:
                    _push_webhooks.remove(url)
                    log.info(f"📌 Webhook deregistered: {url}")
                self._json({"ok": True, "remaining": len(_push_webhooks)})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)

        else:
            self._json({"error": "not found"}, 404)

    # ── DELETE ────────────────────────────────────────────────────────────────

    def do_DELETE(self):
        p = urlparse(self.path).path
        if p.startswith("/tasks/"):
            task_id = p[len("/tasks/"):]
            task = _tasks.get(task_id)
            if not task:
                self._json({"error": "task not found"}, 404)
            elif task["status"] in TERMINAL_STATES:
                self._json({"error": "task already in terminal state"}, 409)
            else:
                _update_task(task_id, TASK_CANCELLED)
                self._json({"ok": True, "task_id": task_id, "status": TASK_CANCELLED})
        else:
            self._json({"error": "not found"}, 404)


def run_http(port: int):
    HTTPServer(("127.0.0.1", port), LocalHTTP).serve_forever()


# ══════════════════════════════════════════════════════════════════════════════
# Network helpers
# ══════════════════════════════════════════════════════════════════════════════

def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def get_public_ip(timeout: float = 4.0) -> str | None:
    for url in ["https://api.ipify.org", "https://ifconfig.me/ip", "https://icanhazip.com"]:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "acp-p2p/0.3"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                ip = resp.read().decode().strip()
                if ip and "." in ip and len(ip) <= 45:
                    return ip
        except Exception:
            continue
    return None

def parse_link(link: str) -> tuple[str, int, str]:
    parsed = urlparse(link.replace("acp://", "http://", 1))
    return parsed.hostname or "localhost", parsed.port or 7801, parsed.path.strip("/")


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

def main():
    global _loop, _status, _inbox_path

    parser = argparse.ArgumentParser(description="ACP P2P v0.3 — zero-server direct Agent communication")
    parser.add_argument("--name",   default="ACP-Agent", help="Agent display name")
    parser.add_argument("--join",   default=None,        help="acp:// link to connect to (omit = initiator)")
    parser.add_argument("--port",   type=int, default=7801, help="WebSocket port (default 7801); HTTP = port+100")
    parser.add_argument("--skills", default="",          help="Comma-separated capability list")
    parser.add_argument("--inbox",  default=None,        help="Message persistence file (default /tmp/acp_inbox_<name>.jsonl)")
    args = parser.parse_args()

    ws_port   = args.port
    http_port = args.port + 100
    skills    = [s.strip() for s in args.skills.split(",") if s.strip()] if args.skills else []

    _status["agent_name"] = args.name
    _status["ws_port"]    = ws_port
    _status["http_port"]  = http_port
    _status["agent_card"] = _make_agent_card(args.name, skills)

    _inbox_path = args.inbox or f"/tmp/acp_inbox_{args.name.replace(' ', '_')}.jsonl"
    log.info(f"Message persistence: {_inbox_path}")

    threading.Thread(target=run_http, args=(http_port,), daemon=True).start()
    log.info(f"HTTP interface: http://127.0.0.1:{http_port}")

    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)

    def _shutdown(sig, frame):
        print("\n👋 ACP P2P shutting down")
        _loop.stop()
        sys.exit(0)
    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        if args.join:
            host, port, token = parse_link(args.join)
            _loop.run_until_complete(guest_mode(host, port, token, http_port))
        else:
            token = _make_token()
            _loop.run_until_complete(host_mode(token, ws_port, http_port))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
