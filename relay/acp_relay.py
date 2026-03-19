#!/usr/bin/env python3
"""
ACP P2P Relay v0.5
==================
Zero-server, zero-code-change P2P Agent communication.

v0.5 changes (2026-03-19):
  - Task state machine: 5 states (submitted/working/completed/failed/input_required)
  - Structured Part model: text / file / data (with media_type + filename)
  - Message idempotency: client-generated message_id, server-side dedup
  - Structured SSE events: type=status | artifact | message | peer
  - AgentCard v2: /.well-known/acp.json with capabilities block
  - /message:send endpoint (A2A-aligned) alongside legacy /send
  - /tasks/{id}:cancel (A2A-aligned)

Design principles (confirmed 2026-03-19):
  1. Lightweight & zero-config
  2. True P2P — no middleman, relay punches holes only
  3. Practical — any Agent, any framework, curl-compatible
  4. Personal/team focus — not enterprise complexity
  5. Standardization — MCP standardized Agent<->Tool, ACP standardizes Agent<->Agent

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
    print("Missing dependency: pip install websockets")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [acp] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("acp-p2p")

VERSION = "0.6-dev"


# ══════════════════════════════════════════════════════════════════════════════
# Proxy-aware WebSocket connector (v0.6)
# ══════════════════════════════════════════════════════════════════════════════

def _get_proxy_for_host(host):
    """
    Detect if a host should go through the HTTP proxy.
    Returns (proxy_host, proxy_port) or None for direct connection.
    Respects no_proxy / NO_PROXY environment variables.
    """
    import ipaddress as _ipa

    no_proxy_raw = os.environ.get("no_proxy", "") or os.environ.get("NO_PROXY", "")
    no_proxy_entries = [e.strip() for e in no_proxy_raw.split(",") if e.strip()]

    def _in_no_proxy(h):
        for entry in no_proxy_entries:
            if entry.startswith(".") and h.endswith(entry):
                return True
            if h == entry:
                return True
            try:
                net = _ipa.ip_network(entry, strict=False)
                if _ipa.ip_address(h) in net:
                    return True
            except ValueError:
                pass
        return False

    if _in_no_proxy(host):
        return None  # direct

    proxy_url = os.environ.get("http_proxy") or os.environ.get("HTTP_PROXY")
    if not proxy_url:
        return None

    from urllib.parse import urlparse as _up
    p = _up(proxy_url)
    return (p.hostname, p.port)


async def _proxy_ws_connect(uri, **kwargs):
    """
    Connect to a WebSocket URI via proxy if needed.
    Compatible with websockets <12 (Python 3.9) and >=12.
    """
    import inspect as _inspect
    from urllib.parse import urlparse as _up
    parsed = _up(uri)
    host = parsed.hostname
    proxy = _get_proxy_for_host(host)
    _supports_proxy = "proxy" in _inspect.signature(websockets.connect).parameters

    if proxy is None:
        # No proxy needed — never pass proxy= parameter at all
        # proxy=None in new websockets can trigger unexpected behavior
        # Just connect directly without proxy kwarg on both old and new versions
        _saved = {k: os.environ.pop(k, None) for k in
                  ["http_proxy","https_proxy","HTTP_PROXY","HTTPS_PROXY"]}
        try:
            return await websockets.connect(uri, **kwargs)
        finally:
            for k, v in _saved.items():
                if v is not None: os.environ[k] = v
    else:
        proxy_url = os.environ.get("http_proxy") or os.environ.get("HTTP_PROXY", "")
        if _supports_proxy:
            return await websockets.connect(uri, proxy=proxy_url, **kwargs)
        return await websockets.connect(uri, **kwargs)

MAX_MSG_BYTES = 1 * 1024 * 1024

# ── Task states ────────────────────────────────────────────────────────────────
#
#  submitted -> working -> completed  (terminal)
#                       -> failed     (terminal)
#                       -> input_required  (interrupted; resumes via /tasks/{id}/continue)
#
# Deliberately NO: canceled/rejected/auth_required — over-engineered for personal use.
#
TASK_SUBMITTED      = "submitted"
TASK_WORKING        = "working"
TASK_COMPLETED      = "completed"
TASK_FAILED         = "failed"
TASK_INPUT_REQUIRED = "input_required"

TERMINAL_STATES    = {TASK_COMPLETED, TASK_FAILED}
INTERRUPTED_STATES = {TASK_INPUT_REQUIRED}

# ── Global state ───────────────────────────────────────────────────────────────
_recv_queue: deque = deque(maxlen=1000)
_peer_ws    = None
_loop       = None
_inbox_path = None

_tasks: dict         = {}
_sync_pending: dict  = {}
_sse_subscribers     = []
_push_webhooks       = []

# Idempotency cache (bounded)
_seen_message_ids: dict = {}
_SEEN_MAX = 2000

_status: dict = {
    "acp_version":       VERSION,
    "connected":         False,
    "role":              None,
    "link":              None,
    "session_id":        None,
    "agent_name":        None,
    "agent_card":        None,
    "peer_card":         None,
    "ws_port":           7801,
    "http_port":         7901,
    "messages_sent":     0,
    "messages_received": 0,
    "messages_deduped":  0,
    "reconnect_count":   0,
    "tasks_created":     0,
    "started_at":        None,
    "max_msg_bytes":     MAX_MSG_BYTES,
    "server_seq":        0,
}

def _now():
    return datetime.datetime.utcnow().isoformat() + "Z"

def _make_id(prefix="msg"):
    return f"{prefix}_{uuid.uuid4().hex[:12]}"

def _make_token():
    return "tok_" + uuid.uuid4().hex[:16]


# ══════════════════════════════════════════════════════════════════════════════
# Part model (v0.5)
# ══════════════════════════════════════════════════════════════════════════════

def _make_text_part(text):
    return {"type": "text", "content": text}

def _make_file_part(url, media_type="application/octet-stream", filename=None):
    """File Part uses URL reference — ACP does not pass raw bytes inline."""
    p = {"type": "file", "url": url, "media_type": media_type}
    if filename:
        p["filename"] = filename
    return p

def _make_data_part(data):
    """Structured-data Part — arbitrary JSON value."""
    return {"type": "data", "content": data}

def _validate_part(part):
    """Returns (ok:bool, error:str)."""
    t = part.get("type")
    if t == "text":
        if not isinstance(part.get("content"), str):
            return False, "text part requires string 'content'"
    elif t == "file":
        if not part.get("url"):
            return False, "file part requires 'url'"
    elif t == "data":
        if "content" not in part:
            return False, "data part requires 'content'"
    else:
        return False, f"unknown part type '{t}'; expected text|file|data"
    return True, ""

def _validate_parts(parts):
    if not parts:
        return False, "parts must be a non-empty list"
    for i, p in enumerate(parts):
        ok, err = _validate_part(p)
        if not ok:
            return False, f"parts[{i}]: {err}"
    return True, ""


# ══════════════════════════════════════════════════════════════════════════════
# AgentCard v2
# ══════════════════════════════════════════════════════════════════════════════

def _make_agent_card(name, skills):
    return {
        "name":        name,
        "version":     "1.0.0",
        "acp_version": VERSION,
        "description": f"ACP P2P Agent: {name}",
        "http_port":   _status["http_port"],
        "timestamp":   _now(),
        "skills":      [{"id": s, "name": s} for s in skills],
        "capabilities": {
            "streaming":          True,
            "push_notifications": True,
            "input_required":     True,
            "part_types":         ["text", "file", "data"],
            "max_msg_bytes":      MAX_MSG_BYTES,
            "query_skill":        True,
            "server_seq":         True,
        },
        "auth":      {"schemes": ["none"]},
        "endpoints": {
            "send":         "/message:send",
            "stream":       "/stream",
            "tasks":        "/tasks",
            "agent_card":   "/.well-known/acp.json",
            "skills_query": "/skills/query",
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# Message Sequencing (v0.6)
# ══════════════════════════════════════════════════════════════════════════════

def _next_seq():
    """Return next monotonically-increasing server_seq for outbound messages."""
    _status["server_seq"] += 1
    return _status["server_seq"]


# ══════════════════════════════════════════════════════════════════════════════
# Idempotency
# ══════════════════════════════════════════════════════════════════════════════

def _check_and_record_message_id(message_id):
    """Returns True if new (process), False if duplicate (skip)."""
    if not message_id:
        return True
    if message_id in _seen_message_ids:
        _status["messages_deduped"] += 1
        log.info(f"Duplicate message_id={message_id}, skipped")
        return False
    _seen_message_ids[message_id] = {"ts": _now()}
    if len(_seen_message_ids) > _SEEN_MAX:
        oldest = next(iter(_seen_message_ids))
        del _seen_message_ids[oldest]
    return True


# ══════════════════════════════════════════════════════════════════════════════
# Structured SSE broadcast (v0.5)
# ══════════════════════════════════════════════════════════════════════════════

def _broadcast_sse_event(event_type, payload):
    """
    Broadcast a typed SSE event to all subscribers + webhooks.

    Types:
      status   -> {task_id, state, error?}
      artifact -> {task_id, artifact}
      message  -> {message_id, role, parts, task_id?}
      peer     -> {event: connected|disconnected, session_id?}
    """
    event = {"type": event_type, "ts": _now(), **payload}
    for q in _sse_subscribers:
        q.append(event)
    if _push_webhooks:
        body = json.dumps(event, ensure_ascii=False).encode()
        for url in list(_push_webhooks):
            threading.Thread(target=_deliver_push, args=(url, body), daemon=True).start()

def _deliver_push(url, body):
    try:
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=5)
        log.info(f"Push delivered -> {url}")
    except Exception as e:
        log.warning(f"Push failed -> {url}: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# Task helpers
# ══════════════════════════════════════════════════════════════════════════════

def _create_task(payload, message_id=None):
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
    if message_id:
        task["origin_message_id"] = message_id
    _tasks[task_id] = task
    _status["tasks_created"] += 1
    _broadcast_sse_event("status", {"task_id": task_id, "state": TASK_SUBMITTED})
    return task

def _update_task(task_id, state, artifact=None, error=None, message=None):
    task = _tasks.get(task_id)
    if not task:
        return None
    # Guard: terminal tasks cannot be re-activated
    if task["status"] in TERMINAL_STATES and state not in TERMINAL_STATES:
        log.warning(f"Task {task_id} already terminal ('{task['status']}'), ignoring -> '{state}'")
        return task

    old_state = task["status"]
    task["status"]     = state
    task["updated_at"] = _now()
    if artifact:
        task["artifacts"].append(artifact)
    if error:
        task["error"] = error
    if message:
        task["history"].append(message)

    if state != old_state:
        _broadcast_sse_event("status", {"task_id": task_id, "state": state, "error": error})
    if artifact:
        _broadcast_sse_event("artifact", {"task_id": task_id, "artifact": artifact})

    return task


# ══════════════════════════════════════════════════════════════════════════════
# Persistence
# ══════════════════════════════════════════════════════════════════════════════

def _persist(entry):
    if _inbox_path:
        try:
            with open(_inbox_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
# Incoming message handler
# ══════════════════════════════════════════════════════════════════════════════

def _on_message(raw):
    if len(raw.encode()) > MAX_MSG_BYTES:
        log.warning(f"Message too large ({len(raw.encode())} bytes), dropped")
        return
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("Non-JSON frame, ignored")
        return

    msg_type   = msg.get("type", "")
    message_id = msg.get("message_id") or msg.get("id")

    if msg_type == "acp.agent_card":
        _status["peer_card"] = msg.get("card")
        peer = msg.get("card", {})
        log.info(f"AgentCard from: {peer.get('name')} | acp={peer.get('acp_version')}")
        return

    if msg_type == "acp.reply":
        corr = msg.get("correlation_id")
        if corr and corr in _sync_pending:
            fut = _sync_pending.pop(corr)
            if not fut.done():
                _loop.call_soon_threadsafe(fut.set_result, msg)
        return

    if msg_type == "task.updated":
        task_id = msg.get("task_id")
        if task_id and task_id in _tasks:
            _update_task(task_id, msg.get("status", TASK_WORKING), artifact=msg.get("artifact"))
        return

    # Business message — idempotency check
    if not _check_and_record_message_id(message_id):
        return

    # Structured Parts-based message (v0.5)
    if msg.get("parts"):
        entry = {
            "id":          message_id or _make_id(),
            "message_id":  message_id,
            "received_at": time.time(),
            "role":        msg.get("role", "agent"),
            "parts":       msg["parts"],
            "task_id":     msg.get("task_id"),
            "context_id":  msg.get("context_id"),
            "raw":         msg,
        }
        _recv_queue.append(entry)
        _persist(entry)
        _status["messages_received"] += 1
        _broadcast_sse_event("message", {
            "message_id": message_id,
            "role":       msg.get("role", "agent"),
            "parts":      msg["parts"],
            "task_id":    msg.get("task_id"),
        })
        log.info(f"Message ({len(msg['parts'])} parts) from={msg.get('from','?')}")
        return

    # Legacy unstructured message
    entry = {"id": message_id or _make_id(), "message_id": message_id,
             "received_at": time.time(), "content": msg}
    _recv_queue.append(entry)
    _persist(entry)
    _status["messages_received"] += 1
    _broadcast_sse_event("message", {"message_id": message_id, "role": "agent", "parts": [{"type": "text", "content": str(msg)}]})
    log.info(f"Message (legacy): type={msg_type} from={msg.get('from','?')}")


# ══════════════════════════════════════════════════════════════════════════════
# WebSocket helpers
# ══════════════════════════════════════════════════════════════════════════════

async def _ws_send(msg):
    if _peer_ws is None:
        raise ConnectionError("No P2P connection")
    await _peer_ws.send(json.dumps(msg, ensure_ascii=False))
    _status["messages_sent"] += 1

def _ws_send_sync(msg):
    asyncio.run_coroutine_threadsafe(_ws_send(msg), _loop).result(timeout=10)

async def _send_agent_card(ws):
    await ws.send(json.dumps({"type": "acp.agent_card", "message_id": _make_id("card"),
                               "ts": _now(), "card": _status["agent_card"]}))


# ══════════════════════════════════════════════════════════════════════════════
# HOST mode
# ══════════════════════════════════════════════════════════════════════════════

async def host_mode(token, ws_port, http_port):
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
        _status["connected"]  = True
        _status["session_id"] = "sess_" + uuid.uuid4().hex[:12]
        _status["started_at"] = _status["started_at"] or time.time()
        await _send_agent_card(websocket)
        _broadcast_sse_event("peer", {"event": "connected", "session_id": _status["session_id"]})

        print(f"\n{'='*55}")
        print(f"ACP P2P v{VERSION} - peer connected")
        print(f"  Send:   POST http://localhost:{http_port}/message:send")
        print(f"  Recv:   GET  http://localhost:{http_port}/recv")
        print(f"  Stream: GET  http://localhost:{http_port}/stream")
        print(f"  Card:   GET  http://localhost:{http_port}/.well-known/acp.json")
        print(f"  Tasks:  GET  http://localhost:{http_port}/tasks")
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
            _broadcast_sse_event("peer", {"event": "disconnected"})

    log.info("Detecting public IP...")
    public_ip = await asyncio.get_event_loop().run_in_executor(None, lambda: get_public_ip(4.0))
    display_ip = public_ip or get_local_ip()
    link = f"acp://{display_ip}:{ws_port}/{token}"
    _status["link"] = link

    async with websockets.serve(on_guest, "0.0.0.0", ws_port):
        print(f"\n{'='*60}")
        print(f"ACP P2P v{VERSION} - service started")
        print(f"  IP: {'public' if public_ip else 'LAN'} {display_ip}")
        print(f"\n  Your link:")
        print(f"  {link}")
        print(f"\n  Waiting for peer...")
        print(f"{'='*60}\n")
        await asyncio.Future()


# ══════════════════════════════════════════════════════════════════════════════
# GUEST mode
# ══════════════════════════════════════════════════════════════════════════════

async def guest_mode(host, ws_port, token, http_port):
    global _peer_ws
    uri = f"ws://{host}:{ws_port}/{token}"
    MAX_RETRIES = 10
    retry = 0

    while retry < MAX_RETRIES:
        try:
            log.info(f"{'Reconnecting #' + str(retry) if retry else 'Connecting to'}: {uri}")
            async with await _proxy_ws_connect(uri, ping_interval=20, ping_timeout=10) as ws:
                _peer_ws = ws
                _status["connected"]  = True
                _status["session_id"] = "sess_" + uuid.uuid4().hex[:12]
                _status["started_at"] = _status["started_at"] or time.time()
                if retry > 0:
                    _status["reconnect_count"] += 1
                await _send_agent_card(ws)
                _broadcast_sse_event("peer", {"event": "connected", "session_id": _status["session_id"]})

                print(f"\n{'='*55}")
                print(f"ACP P2P v{VERSION} - {'reconnected' if retry else 'connected'}")
                print(f"  Peer: {host}:{ws_port}")
                print(f"  Send:   POST http://localhost:{http_port}/message:send")
                print(f"  Stream: GET  http://localhost:{http_port}/stream")
                print(f"{'='*55}\n")

                retry = 0
                async for raw in ws:
                    _on_message(raw)

        except ConnectionRefusedError:
            log.warning(f"Refused - retry in {2**retry}s ({retry+1}/{MAX_RETRIES})")
        except websockets.exceptions.ConnectionClosed:
            log.info(f"Closed - retry in {2**retry}s")
        except OSError as e:
            log.warning(f"Network error: {e}")
        finally:
            _peer_ws = None
            _status["connected"] = False
            _status["peer_card"] = None
            _broadcast_sse_event("peer", {"event": "disconnected"})

        retry += 1
        if retry < MAX_RETRIES:
            await asyncio.sleep(min(2 ** retry, 60))

    print(f"\nGave up after {MAX_RETRIES} retries")
    sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════════
# Local HTTP interface
# ══════════════════════════════════════════════════════════════════════════════

class LocalHTTP(BaseHTTPRequestHandler):
    def log_message(self, *_): pass

    def _json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n) if n else b"{}"
        return json.loads(raw) if raw.strip() else {}

    def do_OPTIONS(self):
        self.send_response(200)
        for h, v in [("Access-Control-Allow-Origin","*"),
                     ("Access-Control-Allow-Methods","GET,POST,DELETE,OPTIONS"),
                     ("Access-Control-Allow-Headers","Content-Type")]:
            self.send_header(h, v)
        self.end_headers()

    # ── GET ───────────────────────────────────────────────────────────────────

    def do_GET(self):
        parsed = urlparse(self.path)
        p  = parsed.path
        qs = parse_qs(parsed.query)

        if p in ("/card", "/.well-known/acp.json"):
            self._json({"self": _status.get("agent_card"), "peer": _status.get("peer_card")})

        elif p == "/status":
            self._json(_status)

        elif p == "/link":
            self._json({"link": _status.get("link"), "session_id": _status.get("session_id")})

        elif p.startswith("/wait/"):
            corr = p[len("/wait/"):]
            timeout = float(qs.get("timeout", ["30"])[0])
            future = _loop.create_future()
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

        elif p == "/recv":
            limit = int(qs.get("limit", ["50"])[0])
            msgs  = [_recv_queue.popleft() for _ in range(min(limit, len(_recv_queue)))]
            self._json({"messages": msgs, "count": len(msgs), "remaining": len(_recv_queue)})

        elif p == "/tasks":
            state_filter = qs.get("state", [None])[0]
            tasks = list(_tasks.values())
            if state_filter:
                tasks = [t for t in tasks if t["status"] == state_filter]
            self._json({"tasks": tasks, "count": len(tasks)})

        elif p.startswith("/tasks/"):
            # /tasks/{id}  or  /tasks/{id}:subscribe (SSE for single task)
            rest = p[len("/tasks/"):]
            if rest.endswith(":subscribe"):
                task_id = rest[:-len(":subscribe")]
                task = _tasks.get(task_id)
                if not task:
                    self._json({"error": "task not found"}, 404)
                    return
                # SSE stream filtered to this task
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                q = deque()
                _sse_subscribers.append(q)
                try:
                    while True:
                        if q:
                            evt = q.popleft()
                            if evt.get("task_id") == task_id or evt.get("type") == "peer":
                                data = f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
                                self.wfile.write(data.encode())
                                self.wfile.flush()
                            if evt.get("type") == "status" and evt.get("state") in TERMINAL_STATES:
                                break
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
                task = _tasks.get(rest)
                if task:
                    self._json(task)
                else:
                    self._json({"error": "task not found"}, 404)

        elif p == "/history":
            history = []
            if _inbox_path and os.path.exists(_inbox_path):
                with open(_inbox_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try: history.append(json.loads(line))
                            except Exception: pass
            limit = int(qs.get("limit", ["100"])[0])
            self._json({"history": history[-limit:], "total": len(history)})

        elif p == "/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            q = deque()
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

        # /message:send  — primary v0.5 endpoint (A2A-aligned)
        # Accepts: {message_id?, role?, parts, task_id?, context_id?, sync?, timeout?}
        if p == "/message:send":
            try:
                body = self._read_body()

                # Build structured message
                parts = body.get("parts")
                if parts:
                    ok, err = _validate_parts(parts)
                    if not ok:
                        self._json({"ok": False, "error": err}, 400)
                        return
                else:
                    # Auto-wrap plain text in a text Part
                    text = body.get("text") or body.get("content") or ""
                    parts = [_make_text_part(str(text))] if text else []
                    if not parts:
                        self._json({"ok": False, "error": "provide 'parts' or 'text'"}, 400)
                        return

                message_id = body.get("message_id") or _make_id("msg")
                msg = {
                    "type":       "acp.message",
                    "message_id": message_id,
                    "server_seq": _next_seq(),
                    "ts":         _now(),
                    "from":       _status.get("agent_name", "unknown"),
                    "role":       body.get("role", "user"),
                    "parts":      parts,
                }
                if body.get("task_id"):
                    msg["task_id"] = body["task_id"]
                if body.get("context_id"):
                    msg["context_id"] = body["context_id"]

                serialized = json.dumps(msg, ensure_ascii=False)
                if len(serialized.encode()) > MAX_MSG_BYTES:
                    self._json({"ok": False, "error": f"message too large (max {MAX_MSG_BYTES} bytes)"}, 413)
                    return

                want_sync = body.get("sync", False)
                timeout   = float(body.get("timeout", 30))

                # Create task if requested
                task = None
                if body.get("create_task", False):
                    task = _create_task({"parts": parts}, message_id=message_id)
                    msg["task_id"] = task["id"]
                    if task:
                        _update_task(task["id"], TASK_WORKING)

                if want_sync:
                    msg["correlation_id"] = message_id
                    future = _loop.create_future()
                    _sync_pending[message_id] = future
                    _ws_send_sync(msg)
                    try:
                        reply = asyncio.run_coroutine_threadsafe(
                            asyncio.wait_for(asyncio.shield(future), timeout=timeout), _loop
                        ).result(timeout=timeout + 2)
                        _sync_pending.pop(message_id, None)
                        if task:
                            _update_task(task["id"], TASK_COMPLETED, artifact={"parts": reply.get("parts", [])})
                        self._json({"ok": True, "message_id": message_id, "reply": reply,
                                    "task": task})
                    except asyncio.TimeoutError:
                        _sync_pending.pop(message_id, None)
                        if task:
                            _update_task(task["id"], TASK_FAILED, error="reply timeout")
                        self._json({"ok": False, "error": "reply timeout", "message_id": message_id}, 408)
                else:
                    _ws_send_sync(msg)
                    self._json({"ok": True, "message_id": message_id, "task": task})

            except ConnectionError as e:
                self._json({"ok": False, "error": str(e)}, 503)
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)

        # /send  — legacy endpoint (backward-compat)
        elif p == "/send":
            try:
                msg = self._read_body()
                msg.setdefault("id",         _make_id())
                msg.setdefault("ts",         _now())
                msg.setdefault("from",       _status.get("agent_name", "unknown"))
                msg.setdefault("session_id", _status.get("session_id"))
                serialized = json.dumps(msg, ensure_ascii=False)
                if len(serialized.encode()) > MAX_MSG_BYTES:
                    self._json({"ok": False, "error": f"too large (max {MAX_MSG_BYTES})"}, 413)
                    return
                want_sync = msg.pop("sync", False)
                timeout   = float(msg.pop("timeout", 30))
                if want_sync:
                    corr = msg.get("id")
                    msg["correlation_id"] = corr
                    future = _loop.create_future()
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

        elif p == "/reply":
            try:
                body = self._read_body()
                msg  = {"type": "acp.reply", "message_id": _make_id(), "ts": _now(),
                        "from": _status.get("agent_name", "unknown"),
                        "correlation_id": body.get("correlation_id"),
                        "content": body.get("content"),
                        "parts":   body.get("parts"),}
                _ws_send_sync(msg)
                self._json({"ok": True})
            except ConnectionError as e:
                self._json({"ok": False, "error": str(e)}, 503)
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)

        # /tasks/create — create a task (optionally delegate to peer)
        elif p == "/tasks/create" or p == "/tasks":
            try:
                body = self._read_body()
                task = _create_task(body.get("payload", body),
                                    message_id=body.get("message_id"))
                if body.get("delegate", False):
                    _ws_send_sync({"type": "task.delegate", "message_id": _make_id(), "ts": _now(),
                                   "from": _status.get("agent_name"), "task_id": task["id"],
                                   "payload": task["payload"]})
                self._json({"ok": True, "task": task}, 201)
            except ConnectionError as e:
                self._json({"ok": False, "error": str(e)}, 503)
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)

        # /tasks/{id}/update — update task state + optional artifact
        elif p.startswith("/tasks/") and p.endswith("/update"):
            task_id = p[len("/tasks/"):-len("/update")]
            try:
                body = self._read_body()
                task = _update_task(task_id, body.get("status", TASK_WORKING),
                                    artifact=body.get("artifact"), error=body.get("error"))
                if task is None:
                    self._json({"error": "task not found"}, 404)
                    return
                try:
                    _ws_send_sync({"type": "task.updated", "message_id": _make_id(), "ts": _now(),
                                   "from": _status.get("agent_name"), "task_id": task_id,
                                   "status": body.get("status", TASK_WORKING),
                                   "artifact": body.get("artifact")})
                except ConnectionError:
                    pass
                self._json({"ok": True, "task": task})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)

        # /tasks/{id}/continue — resume input_required task
        elif p.startswith("/tasks/") and p.endswith("/continue"):
            task_id = p[len("/tasks/"):-len("/continue")]
            try:
                body = self._read_body()
                task = _tasks.get(task_id)
                if not task:
                    self._json({"error": "task not found"}, 404)
                    return
                if task["status"] not in INTERRUPTED_STATES:
                    self._json({"error": f"task is not in interrupted state (is: {task['status']})"}, 409)
                    return
                _update_task(task_id, TASK_WORKING)
                # Forward continuation message to peer
                parts = body.get("parts") or [_make_text_part(str(body.get("text", "")))]
                msg = {"type": "acp.message", "message_id": _make_id(), "ts": _now(),
                       "from": _status.get("agent_name"), "role": "user",
                       "parts": parts, "task_id": task_id}
                try:
                    _ws_send_sync(msg)
                except ConnectionError:
                    pass
                self._json({"ok": True, "task": task})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)

        # /tasks/{id}:cancel — A2A-aligned cancel endpoint
        elif p.startswith("/tasks/") and p.endswith(":cancel"):
            task_id = p[len("/tasks/"):-len(":cancel")]
            task = _tasks.get(task_id)
            if not task:
                self._json({"error": "task not found"}, 404)
            elif task["status"] in TERMINAL_STATES:
                self._json({"error": f"task already in terminal state: {task['status']}"}, 409)
            else:
                _update_task(task_id, TASK_FAILED, error="canceled by client")
                self._json({"ok": True, "task_id": task_id, "status": TASK_FAILED})

        elif p == "/webhooks/register":
            try:
                body = self._read_body()
                url  = body.get("url", "").strip()
                if not url:
                    self._json({"error": "url required"}, 400)
                    return
                if url not in _push_webhooks:
                    _push_webhooks.append(url)
                self._json({"ok": True, "registered": url, "total": len(_push_webhooks)})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)

        elif p == "/webhooks/deregister":
            try:
                body = self._read_body()
                url  = body.get("url", "").strip()
                if url in _push_webhooks:
                    _push_webhooks.remove(url)
                self._json({"ok": True, "remaining": len(_push_webhooks)})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)

        # /skills/query — QuerySkill: runtime capability introspection (v0.6, inspired by A2A PR#1655)
        # Request:  {"skill_id": "summarize", "constraints": {"file_size_bytes": 52428800}}
        # Response: {"skill_id": "...", "support_level": "supported|partial|unsupported",
        #            "reason": "...", "constraints_applied": {...}, "agent": {...}}
        elif p == "/skills/query":
            try:
                body = self._read_body()
                skill_id    = (body.get("skill_id") or "").strip()
                constraints = body.get("constraints") or {}

                agent_card  = _status.get("agent_card") or {}
                known_skills = {s["id"] for s in agent_card.get("skills", [])}
                capabilities = agent_card.get("capabilities", {})

                # Determine support level
                if not skill_id:
                    # No skill_id: return full skill list
                    self._json({
                        "skills": list(known_skills),
                        "capabilities": capabilities,
                        "agent": {"name": agent_card.get("name"), "acp_version": VERSION},
                    })
                    return

                if skill_id in known_skills:
                    # Check constraints against known capabilities
                    violations = []
                    if "file_size_bytes" in constraints:
                        max_bytes = capabilities.get("max_msg_bytes", MAX_MSG_BYTES)
                        if constraints["file_size_bytes"] > max_bytes:
                            violations.append(f"file_size_bytes {constraints['file_size_bytes']} exceeds max {max_bytes}")

                    if violations:
                        support_level = "partial"
                        reason = "; ".join(violations)
                        constraints_applied = {"max_msg_bytes": capabilities.get("max_msg_bytes", MAX_MSG_BYTES)}
                    else:
                        support_level = "supported"
                        reason = f"Skill '{skill_id}' is available"
                        constraints_applied = {}
                else:
                    support_level = "unsupported"
                    reason = f"Skill '{skill_id}' not registered on this agent"
                    constraints_applied = {}

                self._json({
                    "skill_id":            skill_id,
                    "support_level":       support_level,
                    "reason":              reason,
                    "constraints_applied": constraints_applied,
                    "known_skills":        sorted(known_skills),
                    "agent": {
                        "name":        agent_card.get("name"),
                        "acp_version": VERSION,
                    },
                })
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
                self._json({"error": f"already terminal: {task['status']}"}, 409)
            else:
                _update_task(task_id, TASK_FAILED, error="deleted")
                self._json({"ok": True, "task_id": task_id})
        else:
            self._json({"error": "not found"}, 404)


def run_http(port):
    HTTPServer(("127.0.0.1", port), LocalHTTP).serve_forever()


# ══════════════════════════════════════════════════════════════════════════════
# Network helpers
# ══════════════════════════════════════════════════════════════════════════════

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def get_public_ip(timeout=4.0):
    for url in ["https://api.ipify.org", "https://ifconfig.me/ip", "https://icanhazip.com"]:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": f"acp-p2p/{VERSION}"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                ip = resp.read().decode().strip()
                if ip and "." in ip and len(ip) <= 45:
                    return ip
        except Exception:
            continue
    return None

def parse_link(link):
    """Returns (host, port, token, scheme)"""
    if link.startswith("acp+wss://") or link.startswith("acp+ws://"):
        # HTTP polling relay: acp+wss://relay.host/acp/TOKEN
        scheme = "http_relay"
        parsed = urlparse(link.replace("acp+wss://", "https://", 1).replace("acp+ws://", "http://", 1))
        base_url = f"{'https' if link.startswith('acp+wss://') else 'http'}://{parsed.netloc}"
        token = parsed.path.strip("/").split("/")[-1]  # last segment
        return base_url, 0, token, scheme
    scheme = "ws"
    parsed = urlparse(link.replace("acp://", "http://", 1))
    return parsed.hostname or "localhost", parsed.port or 7801, parsed.path.strip("/"), scheme


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

def main():
    global _loop, _status, _inbox_path, MAX_MSG_BYTES

    parser = argparse.ArgumentParser(description=f"ACP P2P v{VERSION} — zero-server Agent communication")
    parser.add_argument("--name",         default="ACP-Agent")
    parser.add_argument("--join",         default=None, help="acp:// link to connect to")
    parser.add_argument("--port",         type=int, default=7801)
    parser.add_argument("--skills",       default="")
    parser.add_argument("--inbox",        default=None)
    parser.add_argument("--max-msg-size", type=int, default=MAX_MSG_BYTES)
    args = parser.parse_args()

    MAX_MSG_BYTES = args.max_msg_size
    _status["max_msg_bytes"] = MAX_MSG_BYTES

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
        print("\nACP P2P shutting down")
        _loop.stop()
        sys.exit(0)
    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        if args.join:
            result = parse_link(args.join)
            if len(result) == 4:
                host, port, token, scheme = result
            else:
                host, port, token = result; scheme = "ws"
            if scheme == "http_relay":
                log.info(f"Transport: HTTP polling relay -> {host}")
                _loop.run_until_complete(_http_relay_guest(host, token, http_port))
            else:
                _loop.run_until_complete(guest_mode(host, port, token, http_port))
        else:
            token = _make_token()
            _loop.run_until_complete(host_mode(token, ws_port, http_port))
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()


# ══════════════════════════════════════════════════════════════════════════════
# Transport C: HTTP Polling Relay (acp+wss:// scheme)
# 适用于严格沙箱/K8s 环境，双方只需 HTTP 出站能力，无需入站端口
# ══════════════════════════════════════════════════════════════════════════════

async def _http_relay_guest(relay_base_url: str, token: str, http_port: int):
    """
    用 HTTP Polling 替代 WebSocket，接入公共中继服务器。
    relay_base_url: 例如 https://acp-relay.workers.dev
    token:          会话 token
    """
    import urllib.request as _req
    import urllib.error as _uerr

    join_url  = f"{relay_base_url}/acp/{token}/join"
    send_url  = f"{relay_base_url}/acp/{token}/send"
    poll_url  = f"{relay_base_url}/acp/{token}/poll"

    agent_card = _make_agent_card(_status["agent_name"], [])

    # 注册到会话
    try:
        body = json.dumps(agent_card).encode()
        r = _req.urlopen(_req.Request(join_url, data=body,
                         headers={"Content-Type": "application/json"}), timeout=10)
        resp = json.loads(r.read())
        log.info(f"Joined HTTP relay session: {token}")
    except Exception as e:
        log.error(f"Failed to join relay: {e}")
        return

    _status["connected"]  = True
    _status["session_id"] = token
    _status["started_at"] = _status["started_at"] or time.time()

    print(f"\n{'='*55}")
    print(f"ACP v{VERSION} - connected via HTTP relay")
    print(f"  Relay: {relay_base_url}")
    print(f"  Token: {token}")
    print(f"  Send:  POST http://localhost:{http_port}/message:send")
    print(f"  Poll:  GET  http://localhost:{http_port}/stream")
    print(f"{'='*55}\n")

    # 注入发消息函数（覆盖 WS 发送，改为 HTTP POST）
    async def _http_send(msg: dict):
        try:
            body = json.dumps(msg).encode()
            _req.urlopen(_req.Request(send_url, data=body,
                         headers={"Content-Type": "application/json"}), timeout=10)
        except Exception as e:
            log.warning(f"HTTP send failed: {e}")

    # 把 _http_send 挂到全局，供 LocalHTTP handler 调用
    global _http_relay_send
    _http_relay_send = _http_send

    # 轮询消息循环
    since = 0.0
    POLL_INTERVAL = 1.5  # 秒

    while True:
        try:
            url = f"{poll_url}?since={since}"
            r = _req.urlopen(url, timeout=15)
            data = json.loads(r.read())
            msgs = data.get("messages", [])
            for msg in msgs:
                # 跳过自己发的
                if msg.get("from") != _status["agent_name"]:
                    _on_message(json.dumps(msg))
                if msg.get("ts", 0) > since:
                    since = msg["ts"]
        except _uerr.URLError as e:
            log.warning(f"Poll error: {e}, retry in {POLL_INTERVAL}s")
        except Exception as e:
            log.warning(f"Poll exception: {e}")

        await asyncio.sleep(POLL_INTERVAL)

_http_relay_send = None  # 由 _http_relay_guest 设置
