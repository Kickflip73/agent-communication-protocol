#!/usr/bin/env python3
"""
ACP P2P Relay v0.7-dev (engine v2.1-alpha)
==========================================
Zero-server, zero-code-change P2P Agent communication.

v2.1-alpha changes (2026-03-26):
  - LAN port-scan discovery: GET /peers/discover
    TCP connect probe + /.well-known/acp.json fingerprint, no mDNS required
    Scans local /24 subnet in ~1-3s using 64-thread pool
    Optional params: ?subnet=192.168.1 ?ports=7901,7902 ?workers=32
    Merges mDNS cache automatically; deduplicates by host
    capabilities.lan_port_scan=true + endpoints.peers_discover advertised
    Works against any ACP relay regardless of --advertise-mdns flag

v0.7 changes (2026-03-20):
  - Optional HMAC-SHA256 message signing: --secret <shared_key>
    sig = HMAC-SHA256(secret, message_id + ":" + ts).hexdigest()
  - AgentCard trust block: { "scheme": "hmac-sha256" | "none", "enabled": bool }
  - AgentCard capabilities.hmac_signing + lan_discovery + context_id fields
  - Verification: warn-only on mismatch (never drop) — graceful interop
  - Without --secret: unsigned mode, fully backward compatible
  - mDNS LAN peer discovery: --advertise-mdns flag
    Pure stdlib UDP multicast 224.0.0.251:5354 — no zeroconf dependency
    GET /discover endpoint: list LAN peers with their acp:// links
    SSE event type=mdns for real-time new peer notifications
  - context_id: optional multi-turn conversation grouping (client-generated, server-echo)

v0.6 changes (2026-03-20):
  - Standardized error codes: 6 codes (ERR_NOT_CONNECTED/MSG_TOO_LARGE/NOT_FOUND/
    INVALID_REQUEST/TIMEOUT/INTERNAL) with failed_message_id for precise retries
  - Multi-session peer registry: /peers, /peer/{id}, /peer/{id}/send
  - AgentCard capabilities.multi_session=true

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
import hmac
import hashlib
import struct
import select
from collections import deque
from http.server import HTTPServer, BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import urllib.request
import urllib.error
import datetime

# Optional HTTP/2 support via hypercorn + h2 (not required; graceful fallback to HTTP/1.1)
try:
    import asyncio as _asyncio_h2
    import hypercorn.asyncio as _hypercorn_asyncio
    import hypercorn.config as _hypercorn_config
    _HTTP2_AVAILABLE = True
except ImportError:
    _HTTP2_AVAILABLE = False

try:
    import websockets
    import websockets.exceptions
except ImportError:
    print("Missing dependency: pip install websockets")
    sys.exit(1)

# ── Optional Ed25519 identity (v0.8) ───────────────────────────────────────
# Uses `cryptography` library if available; falls back gracefully without it.
try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey, Ed25519PublicKey,
    )
    from cryptography.hazmat.primitives.serialization import (
        Encoding, PublicFormat, PrivateFormat, NoEncryption,
    )
    from cryptography.exceptions import InvalidSignature as _Ed25519InvalidSignature
    import base64 as _base64
    _ED25519_AVAILABLE = True
except ImportError:
    _ED25519_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s [acp] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("acp-p2p")

VERSION = "2.1.0"


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

# ══════════════════════════════════════════════════════════════════════════════
# Standardized error codes (v0.6, inspired by ANP failed_msg_id)
# ══════════════════════════════════════════════════════════════════════════════
#
# ACP uses 6 error codes. Every error response includes:
#   { "ok": false, "error_code": "<CODE>", "error": "<human message>",
#     "failed_message_id": "<msg_id if applicable>" }
#
ERR_NOT_CONNECTED   = "ERR_NOT_CONNECTED"    # No peer connected
ERR_MSG_TOO_LARGE   = "ERR_MSG_TOO_LARGE"    # Message exceeds max_msg_bytes
ERR_NOT_FOUND       = "ERR_NOT_FOUND"        # Task/peer/resource not found
ERR_INVALID_REQUEST = "ERR_INVALID_REQUEST"  # Bad input (missing fields, invalid parts)
ERR_TIMEOUT         = "ERR_TIMEOUT"          # Sync wait timed out
ERR_INTERNAL        = "ERR_INTERNAL"         # Unexpected server error

def _err(code: str, message: str, http_status: int = 400,
         failed_message_id: str = None) -> tuple:
    """Build a standardized ACP error response dict + HTTP status code."""
    body = {"ok": False, "error_code": code, "error": message}
    if failed_message_id:
        body["failed_message_id"] = failed_message_id
    return body, http_status

# ── Task states ────────────────────────────────────────────────────────────────
#
#  submitted -> working -> completed  (terminal)
#                       -> failed     (terminal)
#                       -> input_required  (interrupted; resumes via /tasks/{id}/continue)
#
# BUG-002 fix (2026-03-23): added TASK_CANCELED — spec §3 defines 5 states including canceled.
#
TASK_SUBMITTED      = "submitted"
TASK_WORKING        = "working"
TASK_COMPLETED      = "completed"
TASK_FAILED         = "failed"
TASK_CANCELED       = "canceled"
TASK_INPUT_REQUIRED = "input_required"

TERMINAL_STATES    = {TASK_COMPLETED, TASK_FAILED, TASK_CANCELED}
INTERRUPTED_STATES = {TASK_INPUT_REQUIRED}

# ── Global state ───────────────────────────────────────────────────────────────
_recv_queue: deque = deque(maxlen=1000)
_peer_ws    = None
_loop       = None
_inbox_path = None

# v2.0: Offline delivery queue — buffers messages when peer is disconnected,
#        auto-flushes on reconnect.
OFFLINE_QUEUE_MAXLEN = 100          # per-peer max buffered messages
_offline_queue: dict  = {}          # { peer_id|"default": deque([msg, ...]) }
_offline_lock         = threading.Lock()

_tasks: dict         = {}
_sync_pending: dict  = {}
_sse_subscribers     = []
_push_webhooks       = []
_sse_notify          = threading.Event()   # BUG-009 fix: signal SSE handlers on new event

# Idempotency cache (bounded)
_seen_message_ids: dict = {}
_SEEN_MAX = 2000

# ── HMAC optional signing (v0.7) ──────────────────────────────────────────
# _hmac_secret: bytes | None
# When set, every outbound message gets a `sig` field:
#   sig = HMAC-SHA256(secret, message_id + ":" + ts_str).hexdigest()
# Inbound: if sig present AND secret set, verify; mismatch → log warning (not drop).
# If secret not set, sig is ignored on receive (graceful interop).
_hmac_secret: bytes = None

# ── HMAC replay-window (v1.1) ─────────────────────────────────────────────
# When HMAC signing is enabled (--secret), inbound messages must have a `ts`
# field within ±HMAC_REPLAY_WINDOW_SECONDS of server clock.
# This converts the security audit result from PARTIAL → PASS.
# Default: 300 seconds (5 minutes).  Override with --hmac-window <seconds>.
_HMAC_REPLAY_WINDOW: int = 300  # seconds


def _hmac_sign(message_id: str, ts) -> str:
    """Compute HMAC-SHA256(secret, '{message_id}:{ts}') as hex."""
    payload = f"{message_id}:{ts}".encode()
    return hmac.new(_hmac_secret, payload, hashlib.sha256).hexdigest()


def _hmac_check_replay_window(ts_str: str) -> tuple[bool, str]:
    """
    Returns (ok: bool, reason: str).
    Accepts ISO-8601 UTC timestamps (with or without trailing Z).
    If ts_str is missing/unparseable, returns (False, reason).
    Only called when _hmac_secret is set.
    """
    if not ts_str:
        return False, "missing ts field"
    try:
        ts_clean = ts_str.rstrip("Z")
        msg_time = datetime.datetime.fromisoformat(ts_clean)
        now_utc  = datetime.datetime.utcnow()
        skew     = abs((now_utc - msg_time).total_seconds())
        if skew > _HMAC_REPLAY_WINDOW:
            return False, f"ts outside replay-window ({skew:.0f}s > {_HMAC_REPLAY_WINDOW}s)"
        return True, "ok"
    except ValueError as exc:
        return False, f"unparseable ts: {exc}"


def _hmac_verify(message_id: str, ts, sig: str) -> bool:
    """Verify inbound sig. Returns True if valid (or if no secret configured)."""
    if not _hmac_secret:
        return True  # no secret = accept all
    expected = _hmac_sign(message_id, ts)
    return hmac.compare_digest(expected, sig)


# ── Ed25519 optional identity (v0.8) ──────────────────────────────────────
# When --identity flag is used:
#   - Generates (or loads) an Ed25519 keypair from ~/.acp/identity.json
#   - Every outbound message gets an `identity` block:
#       { "scheme": "ed25519", "public_key": "<base64url>", "sig": "<base64url>" }
#   - Signature covers canonical JSON of the message envelope (excluding identity.sig)
#   - Inbound: if identity.scheme==ed25519 present, verify sig; mismatch → warn only
# Without --identity: no identity block; fully backward compatible with v0.7.
_ed25519_private: "Ed25519PrivateKey | None" = None   # type: ignore
_ed25519_public_b64: str = None   # base64url-encoded 32-byte public key
_did_acp: str = None              # v1.3: did:acp:<base64url(pubkey)> — stable Agent identifier
_ca_cert_pem: str = None          # v1.5: optional PEM-encoded CA-signed certificate (hybrid identity)


def _pubkey_to_did_acp(pubkey_bytes: bytes) -> str:
    """Derive a did:acp: identifier from a raw 32-byte Ed25519 public key.

    Format: did:acp:<base64url-no-padding(pubkey)>
    Zero-dependency (stdlib base64 only); intentionally avoids base58 to keep
    the relay self-contained.  The 'acp' DID method is key-based — the DID IS
    the public key, no registry needed.

    Example:
        did:acp:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK  (conceptual)
    Actual (base64url):
        did:acp:AAEC...  (43 chars for a 32-byte key)
    """
    encoded = _base64.urlsafe_b64encode(pubkey_bytes).rstrip(b"=").decode()
    return f"did:acp:{encoded}"


def _ed25519_load_or_create(identity_path: str = None) -> bool:
    """Load existing Ed25519 keypair or generate a new one. Returns success."""
    global _ed25519_private, _ed25519_public_b64, _did_acp
    if not _ED25519_AVAILABLE:
        log.warning("Ed25519 identity requires: pip install cryptography")
        return False

    import json as _json
    import pathlib as _pathlib

    path = _pathlib.Path(identity_path or os.path.expanduser("~/.acp/identity.json"))
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        try:
            data = _json.loads(path.read_text())
            raw = _base64.urlsafe_b64decode(data["private_key"] + "==")
            _ed25519_private = Ed25519PrivateKey.from_private_bytes(raw)
            pub_raw = _ed25519_private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
            _ed25519_public_b64 = _base64.urlsafe_b64encode(pub_raw).rstrip(b"=").decode()
            _did_acp = _pubkey_to_did_acp(pub_raw)
            log.info(f"Ed25519 identity loaded from {path} | did={_did_acp}")
            return True
        except Exception as e:
            log.warning(f"Failed to load identity from {path}: {e} — generating new keypair")

    _ed25519_private = Ed25519PrivateKey.generate()
    pub_raw = _ed25519_private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    priv_raw = _ed25519_private.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    _ed25519_public_b64 = _base64.urlsafe_b64encode(pub_raw).rstrip(b"=").decode()
    _did_acp = _pubkey_to_did_acp(pub_raw)
    priv_b64 = _base64.urlsafe_b64encode(priv_raw).rstrip(b"=").decode()
    try:
        path.write_text(_json.dumps({
            "scheme":      "ed25519",
            "public_key":  _ed25519_public_b64,
            "did":         _did_acp,
            "private_key": priv_b64,
            "created_at":  _now(),
        }, indent=2))
        path.chmod(0o600)
        log.info(f"Ed25519 keypair generated and saved to {path} | did={_did_acp}")
    except Exception as e:
        log.warning(f"Could not save identity to {path}: {e} — keypair active for this session only")
    return True


def _ed25519_sign_msg(msg: dict) -> str:
    """Sign canonical message envelope (all fields except identity.sig). Returns base64url sig."""
    # Build canonical form: sorted keys, excluding identity.sig itself
    canonical = {k: v for k, v in msg.items() if k != "identity"}
    payload = json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    sig_bytes = _ed25519_private.sign(payload)
    return _base64.urlsafe_b64encode(sig_bytes).rstrip(b"=").decode()


def _ed25519_verify_msg(msg: dict, public_key_b64: str, sig_b64: str) -> bool:
    """Verify Ed25519 sig on inbound message. Returns True if valid."""
    if not _ED25519_AVAILABLE:
        return True  # can't verify — accept
    try:
        pub_raw = _base64.urlsafe_b64decode(public_key_b64 + "==")
        pub_key = Ed25519PublicKey.from_public_bytes(pub_raw)
        sig_bytes = _base64.urlsafe_b64decode(sig_b64 + "==")
        # Reconstruct canonical form (same as signing)
        canonical = {k: v for k, v in msg.items() if k != "identity"}
        payload = json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
        pub_key.verify(sig_bytes, payload)
        return True
    except (_Ed25519InvalidSignature, Exception):
        return False


# ── Multi-session peer registry (v0.6) ─────────────────────────────────────
# Stores all active peer connections keyed by peer_id (auto-assigned or named)
# Each entry: {id, name, link, ws, connected, connected_at, messages_sent,
#              messages_received, agent_card}
_peers: dict = {}       # peer_id -> peer info dict
_peer_id_counter = 0    # auto-increment for unnamed peers

def _make_peer_id():
    global _peer_id_counter
    _peer_id_counter += 1
    return f"peer_{_peer_id_counter:03d}"

def _register_peer(peer_id=None, link=None, ws=None):
    """Register or update a peer connection. Returns peer_id."""
    pid = peer_id or _make_peer_id()
    existing = _peers.get(pid, {})
    _peers[pid] = {
        "id":               pid,
        "name":             existing.get("name", pid),
        "link":             link or existing.get("link"),
        "ws":               ws or existing.get("ws"),
        "connected":        True,
        "connected_at":     existing.get("connected_at") or _now(),
        "messages_sent":    existing.get("messages_sent", 0),
        "messages_received": existing.get("messages_received", 0),
        "agent_card":       existing.get("agent_card"),
    }
    return pid

def _unregister_peer(peer_id):
    """Mark a peer as disconnected (retain for history)."""
    if peer_id in _peers:
        _peers[peer_id]["connected"] = False
        _peers[peer_id]["disconnected_at"] = _now()
        _peers[peer_id]["ws"] = None

def _get_peer_ws(peer_id=None):
    """Get WebSocket for a specific peer, or fallback to legacy _peer_ws."""
    if peer_id and peer_id in _peers:
        return _peers[peer_id].get("ws")
    # Legacy fallback: single-peer mode
    return _peer_ws

# ── /

_status: dict = {
    "acp_version":       VERSION,
    "connected":         False,
    "role":              None,
    "link":              None,
    "session_id":        None,
    "agent_name":        None,
    "agent_card":        None,
    "peer_card":         None,
    "peer_card_verification": None,       # v1.9: auto-verification result for peer AgentCard
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
    "peer_count":        0,    # v0.6: active peer count
}

def _now():
    return datetime.datetime.utcnow().isoformat() + "Z"

def _make_id(prefix="msg"):
    return f"{prefix}_{uuid.uuid4().hex[:12]}"

def _make_token():
    return "tok_" + uuid.uuid4().hex[:16]


# ══════════════════════════════════════════════════════════════════════════════
# mDNS-style LAN peer discovery (v0.7)
# Pure stdlib UDP multicast — no zeroconf dependency
# Multicast group: 224.0.0.251 port 5354 (avoid conflict with real mDNS :5353)
# ══════════════════════════════════════════════════════════════════════════════

_MDNS_GROUP   = "224.0.0.251"
_MDNS_PORT    = 5354
_MDNS_MAGIC   = b"ACP1"      # 4-byte protocol magic
_mdns_peers   = {}            # { "ip:port" -> {name, token, link, seen_at} }
_mdns_lock    = threading.Lock()
_mdns_thread  = None
_mdns_running = False


def _mdns_announce_payload(name: str, token: str, ws_port: int, http_port: int) -> bytes:
    """Build a compact UDP announce packet: MAGIC + JSON."""
    payload = {
        "v":    1,
        "name": name,
        "tok":  token,
        "wp":   ws_port,
        "hp":   http_port,
    }
    return _MDNS_MAGIC + json.dumps(payload, separators=(",", ":")).encode()


def _mdns_send_announce(name: str, token: str, ws_port: int, http_port: int):
    """Send one UDP multicast announce."""
    try:
        data = _mdns_announce_payload(name, token, ws_port, http_port)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.sendto(data, (_MDNS_GROUP, _MDNS_PORT))
        sock.close()
    except Exception as e:
        log.debug(f"mDNS announce error: {e}")


def _mdns_listener_loop(name: str, token: str, ws_port: int, http_port: int):
    """Background thread: listen for peer announces + re-announce self periodically."""
    global _mdns_running
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError:
            pass  # Windows doesn't have SO_REUSEPORT
        sock.bind(("", _MDNS_PORT))
        mreq = struct.pack("4sL", socket.inet_aton(_MDNS_GROUP), socket.INADDR_ANY)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        sock.setblocking(False)
        log.info(f"mDNS listener started on {_MDNS_GROUP}:{_MDNS_PORT}")
    except Exception as e:
        log.warning(f"mDNS listener failed to start: {e}")
        _mdns_running = False
        return

    last_announce = 0
    ANNOUNCE_INTERVAL = 30  # re-announce every 30 s
    PEER_TTL          = 120  # forget peers not heard from in 2 min

    while _mdns_running:
        now = time.time()

        # Re-announce self
        if now - last_announce > ANNOUNCE_INTERVAL:
            _mdns_send_announce(name, token, ws_port, http_port)
            last_announce = now

        # Listen for incoming announces
        readable, _, _ = select.select([sock], [], [], 1.0)
        if readable:
            try:
                data, addr = sock.recvfrom(1024)
                src_ip = addr[0]
                if not data.startswith(_MDNS_MAGIC):
                    continue
                payload = json.loads(data[len(_MDNS_MAGIC):].decode())
                peer_token = payload.get("tok", "")
                # Ignore our own announce
                if peer_token == token:
                    continue
                peer_ws_port   = payload.get("wp", 7801)
                peer_http_port = payload.get("hp", 7901)
                peer_link      = f"acp://{src_ip}:{peer_ws_port}/{peer_token}"
                peer_key       = f"{src_ip}:{peer_ws_port}"
                with _mdns_lock:
                    is_new = peer_key not in _mdns_peers
                    _mdns_peers[peer_key] = {
                        "name":      payload.get("name", "unknown"),
                        "token":     peer_token,
                        "link":      peer_link,
                        "ip":        src_ip,
                        "ws_port":   peer_ws_port,
                        "http_port": peer_http_port,
                        "seen_at":   now,
                    }
                if is_new:
                    log.info(f"mDNS: discovered peer '{payload.get('name')}' @ {peer_link}")
                    _broadcast_sse_event("mdns", {"event": "discovered",
                                                   "name": payload.get("name"),
                                                   "link": peer_link,
                                                   "ip":   src_ip})
            except Exception as e:
                log.debug(f"mDNS recv error: {e}")

        # Prune stale peers
        with _mdns_lock:
            stale = [k for k, v in _mdns_peers.items() if now - v["seen_at"] > PEER_TTL]
            for k in stale:
                log.info(f"mDNS: peer {k} expired (no announce for {PEER_TTL}s)")
                del _mdns_peers[k]

    sock.close()
    log.info("mDNS listener stopped")


def _mdns_start(name: str, token: str, ws_port: int, http_port: int):
    """Start mDNS advertise + listen in a background thread."""
    global _mdns_thread, _mdns_running
    _mdns_running = True
    _mdns_send_announce(name, token, ws_port, http_port)  # immediate first announce
    _mdns_thread = threading.Thread(
        target=_mdns_listener_loop,
        args=(name, token, ws_port, http_port),
        daemon=True, name="acp-mdns"
    )
    _mdns_thread.start()
    log.info("mDNS discovery started")


def _mdns_stop():
    """Stop mDNS background thread."""
    global _mdns_running
    _mdns_running = False


def _mdns_peer_list() -> list:
    """Return a serializable snapshot of discovered LAN peers."""
    with _mdns_lock:
        return [
            {k: v for k, v in p.items()}
            for p in _mdns_peers.values()
        ]


# ══════════════════════════════════════════════════════════════════════════════
# LAN port-scan discovery (v2.1)
# ══════════════════════════════════════════════════════════════════════════════

# Default ACP HTTP ports to probe (each host)
_ACP_SCAN_PORTS = [7901, 7902, 7903, 7911, 7921, 7931]
# TCP connect timeout in seconds (keep short — scanning ~254 hosts × N ports)
_SCAN_CONNECT_TIMEOUT = 0.15
# HTTP probe timeout (slightly longer — we already know port is open)
_SCAN_HTTP_TIMEOUT = 1.0


def _get_lan_ip() -> str | None:
    """Return the primary LAN IPv4 address of this machine."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


def _tcp_open(host: str, port: int, timeout: float) -> bool:
    """Return True if a TCP connection can be established."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def _probe_acp(host: str, port: int, timeout: float) -> dict | None:
    """
    Probe http://host:port/.well-known/acp.json.
    Returns parsed card dict on success, None otherwise.
    """
    url = f"http://{host}:{port}/.well-known/acp.json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ACP-Scanner/2.1"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read(65536))
                return data
    except Exception:
        return None
    return None


def _lan_port_scan(
    subnet: str | None = None,
    ports: list[int] | None = None,
    max_workers: int = 64,
    skip_self_port: int | None = None,
) -> dict:
    """
    Scan the local /24 subnet for ACP relays via TCP port probe +
    /.well-known/acp.json verification.

    Args:
        subnet:        e.g. "192.168.1"  (auto-detected when None)
        ports:         HTTP ports to try per host (default: _ACP_SCAN_PORTS)
        max_workers:   thread pool size
        skip_self_port: HTTP port of this relay (skip self to avoid self-discovery)

    Returns dict:
        {
          "found": [ {host, port, name, link, agent_card, latency_ms}, ... ],
          "scanned_hosts": N,
          "scanned_ports": M,
          "subnet": "x.x.x",
          "duration_ms": D,
          "error": str | null,
        }
    """
    import concurrent.futures

    if ports is None:
        ports = _ACP_SCAN_PORTS

    t0 = time.monotonic()
    lan_ip = _get_lan_ip()

    if subnet is None:
        if lan_ip is None:
            return {
                "found": [], "scanned_hosts": 0, "scanned_ports": 0,
                "subnet": None, "duration_ms": 0,
                "error": "Cannot determine LAN IP",
            }
        parts = lan_ip.split(".")
        if len(parts) != 4:
            return {
                "found": [], "scanned_hosts": 0, "scanned_ports": 0,
                "subnet": None, "duration_ms": 0,
                "error": f"Unexpected IP format: {lan_ip}",
            }
        subnet = ".".join(parts[:3])  # e.g. "192.168.1"

    # Build host list (skip .0 and .255; skip self)
    hosts = [f"{subnet}.{i}" for i in range(1, 255) if f"{subnet}.{i}" != lan_ip]

    found = []
    scanned_ports = 0

    def _check_host_port(host_port):
        host, port = host_port
        # Skip self
        if skip_self_port and host == lan_ip and port == skip_self_port:
            return None
        if not _tcp_open(host, port, _SCAN_CONNECT_TIMEOUT):
            return None
        # Port is open — probe for ACP
        t_probe = time.monotonic()
        card = _probe_acp(host, port, _SCAN_HTTP_TIMEOUT)
        if card is None:
            return None
        latency_ms = round((time.monotonic() - t_probe) * 1000, 1)
        # Extract identity info from AgentCard
        self_card = card.get("self", card)  # support wrapped {self:{...}} or flat
        name = self_card.get("name", f"acp-relay@{host}:{port}")
        # Reconstruct acp:// link from card if available
        link = None
        endpoints = self_card.get("endpoints", {})
        ws_host = self_card.get("host", host)
        ws_port_val = self_card.get("ws_port") or self_card.get("port")
        token = self_card.get("token")
        if ws_port_val and token:
            link = f"acp://{ws_host}:{ws_port_val}/{token}"
        return {
            "host": host,
            "http_port": port,
            "name": name,
            "link": link,
            "agent_card": self_card,
            "latency_ms": latency_ms,
        }

    tasks = [(h, p) for h in hosts for p in ports]
    scanned_ports = len(tasks)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as exe:
        for result in exe.map(_check_host_port, tasks):
            if result is not None:
                found.append(result)

    # De-duplicate by host (keep first port that responded)
    seen_hosts = set()
    deduped = []
    for r in found:
        if r["host"] not in seen_hosts:
            seen_hosts.add(r["host"])
            deduped.append(r)

    duration_ms = round((time.monotonic() - t0) * 1000)
    return {
        "found": deduped,
        "scanned_hosts": len(hosts),
        "scanned_ports": scanned_ports,
        "subnet": subnet,
        "duration_ms": duration_ms,
        "error": None,
    }


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

# ── Availability metadata (v1.2) ──────────────────────────────────────────
# Optional AgentCard 'availability' block for heartbeat/cron-type agents.
# Inspired by A2A issue #1667 (2026-03-21): AgentCard has no scheduling fields.
# ACP is the first Agent communication protocol to support this natively.
#
# Fields (all optional):
#   mode: "persistent" | "heartbeat" | "cron" | "manual"
#   interval_seconds: int         # heartbeat/cron wake interval
#   next_active_at:   ISO-8601 Z  # next scheduled wake (agent-maintained)
#   last_active_at:   ISO-8601 Z  # last wake time (auto-set on startup)
#   task_latency_max_seconds: int # worst-case task processing latency
_availability: dict  = {}         # empty = persistent (default behaviour)
_extensions:   list  = []         # v1.3: [{uri, required, params}] Extension list (opt-in)
_http2_enabled: bool = False      # v1.6: HTTP/2 transport binding (requires hypercorn+h2)


def _make_agent_card(name, skills):
    card = {
        "name":        name,
        "version":     VERSION,
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
            "multi_session":      True,   # v0.6: multiple simultaneous peer connections
            "hmac_signing":       bool(_hmac_secret),          # v0.7: optional HMAC-SHA256 message signing
            "lan_discovery":      _mdns_running,               # v0.7: mDNS LAN peer discovery
            "context_id":         True,                        # v0.7: optional multi-turn context grouping
            "error_codes":        True,                        # v0.6: standard ACP error codes
            "identity":           ("ed25519+ca" if (_ed25519_private and _ca_cert_pem)
                                  else "ed25519" if _ed25519_private else "none"),  # v0.8/v1.5: optional identity
            "did_identity":       bool(_did_acp),              # v1.3: did:acp: stable identifier + DID Document
            "availability":       bool(_availability),         # v1.2: heartbeat/cron availability metadata
            "extensions":         bool(_extensions),           # v1.3: Extension mechanism (URI-identified)
            "http2":              _http2_enabled,              # v1.6: HTTP/2 transport binding
            "card_sig":           bool(_ed25519_private),      # v1.8: AgentCard self-signature
            "auto_card_verify":   True,                        # v1.9: auto-verify peer AgentCard on connect
            "offline_queue":      True,                        # v2.0: buffer messages when peer offline, flush on reconnect
            "lan_port_scan":      True,                        # v2.1: TCP port-scan LAN discovery (no mDNS required)
        },
        "identity": ({
            "scheme":     "ed25519+ca" if _ca_cert_pem else "ed25519",
            "public_key": _ed25519_public_b64,
            "did":        _did_acp,            # v1.3: stable did:acp: identifier
            **( {"ca_cert": _ca_cert_pem} if _ca_cert_pem else {} ),  # v1.5: CA-signed cert (hybrid model)
        } if _ed25519_private else None),
        "trust": {
            "scheme":  "hmac-sha256" if _hmac_secret else "none",
            "enabled": bool(_hmac_secret),
        },
        "auth":      {"schemes": ["none"]},
        "endpoints": {
            "send":         "/message:send",
            "stream":       "/stream",
            "tasks":        "/tasks",
            "agent_card":   "/.well-known/acp.json",
            "did_document": "/.well-known/did.json",   # v1.3: W3C DID Document (requires --identity)
            "skills_query": "/skills/query",
            "peers":        "/peers",                  # v0.6
            "peer_send":    "/peer/{id}/send",         # v0.6
            "peers_connect": "/peers/connect",         # v0.6
            "discover":     "/discover",               # v0.7 mDNS LAN discovery
            "extensions":   "/extensions",             # v1.3: list/register extensions
            "verify_card":  "/verify/card",            # v1.8: verify any AgentCard self-signature
            "peer_verify":  "/peer/verify",            # v1.9: auto-verification result for connected peer
            "offline_queue": "/offline-queue",         # v2.0: inspect offline delivery queue
            "peers_discover": "/peers/discover",       # v2.1: TCP port-scan LAN discovery
        },
    }
    # v1.2: attach availability block only when configured (opt-in)
    if _availability:
        card["availability"] = dict(_availability)  # shallow copy
        # auto-stamp last_active_at if not explicitly set
        if "last_active_at" not in card["availability"]:
            started = _status.get("started_at")
            if started and isinstance(started, (int, float)):
                card["availability"]["last_active_at"] = (
                    datetime.datetime.utcfromtimestamp(started).strftime("%Y-%m-%dT%H:%M:%SZ")
                )
            else:
                card["availability"]["last_active_at"] = _now()

    # v1.3: attach extensions list only when declared (opt-in)
    if _extensions:
        card["extensions"] = list(_extensions)  # shallow copy

    return card


# ══════════════════════════════════════════════════════════════════════════════
# AgentCard Signature (v1.8)
# ══════════════════════════════════════════════════════════════════════════════

def _sign_agent_card(card: dict) -> dict:
    """
    Sign AgentCard with this Agent's Ed25519 private key (v1.8).

    The signature covers the canonical JSON of the card with the 'identity.card_sig'
    field excluded (to avoid circular reference). The resulting signature is stored
    in card['identity']['card_sig'] as a base64url string.

    Requires --identity flag.  No-op (returns card unchanged) when identity is disabled.

    Signed payload: json.dumps(card_without_card_sig, sort_keys=True, separators=(',',':')).
    This is deterministic and transport-independent.
    """
    if not _ed25519_private:
        return card

    # Build signable form: deep-copy card, remove card_sig from identity block
    import copy
    signable = copy.deepcopy(card)
    if "identity" in signable and signable["identity"]:
        signable["identity"].pop("card_sig", None)

    payload = json.dumps(signable, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    sig_bytes = _ed25519_private.sign(payload)
    sig_b64 = _base64.urlsafe_b64encode(sig_bytes).rstrip(b"=").decode()

    # Attach signature to identity block
    signed = copy.deepcopy(card)
    if signed.get("identity") is None:
        signed["identity"] = {}
    signed["identity"]["card_sig"] = sig_b64
    return signed


def _verify_agent_card(card: dict) -> dict:
    """
    Verify an AgentCard's Ed25519 self-signature (v1.8).

    Returns a dict with keys:
      - valid (bool): True if signature checks out
      - did (str|None): the signer's did:acp: (from card.identity.did)
      - public_key (str|None): base64url public key used to verify
      - error (str|None): human-readable reason if invalid
      - scheme (str): identity scheme from card.identity.scheme
    """
    if not _ED25519_AVAILABLE:
        return {"valid": None, "error": "Ed25519 library not available", "did": None,
                "public_key": None, "scheme": "unknown"}

    identity = card.get("identity") or {}
    pub_key_b64 = identity.get("public_key")
    sig_b64     = identity.get("card_sig")
    did         = identity.get("did")
    scheme      = identity.get("scheme", "none")

    if not pub_key_b64:
        return {"valid": False, "error": "identity.public_key missing", "did": did,
                "public_key": None, "scheme": scheme}
    if not sig_b64:
        return {"valid": False, "error": "identity.card_sig missing (unsigned card)", "did": did,
                "public_key": pub_key_b64, "scheme": scheme}

    try:
        import copy
        # Reconstruct the signable form (same as _sign_agent_card)
        signable = copy.deepcopy(card)
        if "identity" in signable and signable["identity"]:
            signable["identity"].pop("card_sig", None)

        payload = json.dumps(signable, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()

        pub_raw = _base64.urlsafe_b64decode(pub_key_b64 + "==")
        pub_key = Ed25519PublicKey.from_public_bytes(pub_raw)
        sig_bytes = _base64.urlsafe_b64decode(sig_b64 + "==")
        pub_key.verify(sig_bytes, payload)

        # Optionally verify did:acp: matches public_key
        did_consistent = None
        if did and did.startswith("did:acp:"):
            expected_did = "did:acp:" + _base64.urlsafe_b64encode(pub_raw).rstrip(b"=").decode()
            did_consistent = (did == expected_did)

        return {
            "valid": True,
            "did": did,
            "did_consistent": did_consistent,
            "public_key": pub_key_b64,
            "scheme": scheme,
            "error": None,
        }
    except _Ed25519InvalidSignature:
        return {"valid": False, "error": "signature verification failed", "did": did,
                "public_key": pub_key_b64, "scheme": scheme}
    except Exception as exc:
        return {"valid": False, "error": f"verification error: {exc}", "did": did,
                "public_key": pub_key_b64, "scheme": scheme}


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
    _sse_notify.set()   # BUG-009 fix: wake up SSE polling handlers immediately
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

def _create_task(payload, message_id=None, task_id=None, context_id=None):
    # BUG-006 fix: honour client-supplied task_id (idempotent — return existing if already known)
    if task_id and task_id in _tasks:
        return _tasks[task_id]
    task_id = task_id or _make_id("task")
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
    if context_id:
        task["context_id"] = context_id
    _tasks[task_id] = task
    _status["tasks_created"] += 1
    evt: dict = {"task_id": task_id, "state": TASK_SUBMITTED}
    if context_id:
        evt["context_id"] = context_id
    _broadcast_sse_event("status", evt)
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

    ctx = task.get("context_id")
    if state != old_state:
        evt: dict = {"task_id": task_id, "state": state, "error": error}
        if ctx:
            evt["context_id"] = ctx
        _broadcast_sse_event("status", evt)
    if artifact:
        aevt: dict = {"task_id": task_id, "artifact": artifact}
        if ctx:
            aevt["context_id"] = ctx
        _broadcast_sse_event("artifact", aevt)

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

    # HMAC verification (v0.7/v1.1) — sig mismatch: warn-only; replay-window: drop
    # Graceful: agents without --secret still interop fine (sig ignored when no secret).
    # Replay-window (v1.1): when --secret is set, ts MUST be within ±HMAC_REPLAY_WINDOW_SECONDS.
    if _hmac_secret and msg.get("sig") and message_id:
        ts_val = str(msg.get("ts", ""))
        # 1) Replay-window check — hard reject (drop message) to prevent replay attacks
        ok, reason = _hmac_check_replay_window(ts_val)
        if not ok:
            log.warning(f"⚠️  HMAC replay-window reject on {message_id}: {reason}")
            msg["_replay_rejected"] = True
            return  # drop the message; do NOT process further
        # 2) Signature check — warn-only (keep graceful interop for legacy agents)
        if not _hmac_verify(str(message_id), ts_val, msg["sig"]):
            log.warning(f"⚠️  HMAC sig mismatch on {message_id} — message accepted but flagged")
            msg["_sig_invalid"] = True

    # Ed25519 identity verification (v0.8) — warn-only; backward compatible
    # Any agent may include identity.scheme=ed25519; we verify if present regardless
    # of whether we ourselves have an identity configured.
    identity = msg.get("identity")
    if identity and identity.get("scheme") == "ed25519":
        pub_key_b64 = identity.get("public_key", "")
        sig_b64     = identity.get("sig", "")
        if pub_key_b64 and sig_b64 and _ED25519_AVAILABLE:
            if not _ed25519_verify_msg(msg, pub_key_b64, sig_b64):
                log.warning(f"⚠️  Ed25519 sig invalid on {message_id} from pubkey={pub_key_b64[:16]}...")
                msg["_ed25519_invalid"] = True
            else:
                msg["_ed25519_verified"] = True
                log.debug(f"✅ Ed25519 verified: {message_id} from {pub_key_b64[:16]}...")

    if msg_type == "acp.agent_card":
        card = msg.get("card") or {}
        _status["peer_card"] = card
        peer_name = card.get("name", "?")
        # v1.9: Auto-verify peer AgentCard self-signature on receipt
        if card.get("identity") and card["identity"].get("card_sig"):
            vr = _verify_agent_card(card)
            _status["peer_card_verification"] = vr
            if vr.get("valid"):
                log.info(f"✅ AgentCard verified: {peer_name} | did={vr.get('did', '?')[:28]}...")
            else:
                log.warning(f"⚠️  AgentCard sig INVALID: {peer_name} | {vr.get('error')}")
        else:
            _status["peer_card_verification"] = {
                "valid": None,
                "error": "peer card has no card_sig (unsigned — peer may not support v1.8+)",
                "did": card.get("identity", {}).get("did") if card.get("identity") else None,
                "public_key": card.get("identity", {}).get("public_key") if card.get("identity") else None,
                "scheme": (card.get("identity") or {}).get("scheme", "none"),
            }
            log.info(f"AgentCard from: {peer_name} (unsigned) | acp={card.get('acp_version')}")
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
        # 若消息携带 task_id，在本地注册同 id 的 task（对等任务追踪）
        incoming_task_id = msg.get("task_id")
        if incoming_task_id and incoming_task_id not in _tasks:
            task = {
                "id":         incoming_task_id,
                "status":     TASK_WORKING,
                "created_at": _now(),
                "updated_at": _now(),
                "payload":    {"parts": msg["parts"]},
                "artifacts":  [],
                "history":    [],
                "origin_message_id": message_id,
                "from_peer":  True,  # 标记为对端发起的 task
            }
            _tasks[incoming_task_id] = task
            _status["tasks_created"] += 1
            _broadcast_sse_event("status", {"task_id": incoming_task_id, "state": TASK_WORKING})
            log.info(f"Task registered from peer: {incoming_task_id}")

        entry = {
            "id":          message_id or _make_id(),
            "message_id":  message_id,
            "received_at": time.time(),
            "role":        msg.get("role", "agent"),
            "parts":       msg["parts"],
            "task_id":     incoming_task_id,
            "context_id":  msg.get("context_id"),
            "raw":         msg,
        }
        _recv_queue.append(entry)
        _persist(entry)
        _status["messages_received"] += 1
        # BUG-005 fix: update per-peer messages_received counter
        _from = msg.get("from", "")
        for pid, pinfo in _peers.items():
            if pinfo.get("name") == _from or pinfo.get("id") == _from:
                pinfo["messages_received"] = pinfo.get("messages_received", 0) + 1
                break
        else:
            # fallback: credit the first connected peer (single-peer common case)
            connected = [p for p in _peers.values() if p.get("connected")]
            if len(connected) == 1:
                connected[0]["messages_received"] = connected[0].get("messages_received", 0) + 1
        _broadcast_sse_event("message", {
            "message_id": message_id,
            "role":       msg.get("role", "agent"),
            "parts":      msg["parts"],
            "task_id":    incoming_task_id,
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

def _attach_sig(msg: dict) -> dict:
    """Attach HMAC sig (v0.7) and/or Ed25519 identity block (v0.8) to outbound message."""
    if _hmac_secret and "message_id" in msg and "ts" in msg:
        msg["sig"] = _hmac_sign(str(msg["message_id"]), str(msg["ts"]))
    if _ed25519_private is not None and "message_id" in msg:
        msg["identity"] = {
            "scheme":     "ed25519",
            "public_key": _ed25519_public_b64,
            "did":        _did_acp,            # v1.3: stable did:acp: identifier
        }
        # Sig is computed last (excludes identity.sig from canonical form)
        msg["identity"]["sig"] = _ed25519_sign_msg(msg)
    return msg


def _offline_enqueue(msg: dict, peer_id: str = "default") -> None:
    """Buffer a message for offline delivery. Called when peer is disconnected. (v2.0)"""
    with _offline_lock:
        if peer_id not in _offline_queue:
            _offline_queue[peer_id] = deque(maxlen=OFFLINE_QUEUE_MAXLEN)
        _offline_queue[peer_id].append({
            **msg,
            "_queued_at": _now(),
            "_offline_for_peer": peer_id,
        })
    log.debug(f"📥 offline_queue[{peer_id}] depth={len(_offline_queue[peer_id])}")


async def _offline_flush(ws, peer_id: str = "default") -> int:
    """
    Flush buffered offline messages to a newly (re)connected peer WebSocket. (v2.0)
    Returns the number of messages delivered.
    """
    with _offline_lock:
        q = _offline_queue.pop(peer_id, deque())
    if not q:
        return 0
    count = 0
    for msg in q:
        try:
            # Strip internal bookkeeping fields before delivery
            clean = {k: v for k, v in msg.items()
                     if not k.startswith("_offline_") and k != "_queued_at"}
            clean.setdefault("_was_queued", True)   # signal to receiver this was buffered
            await ws.send(json.dumps(clean, ensure_ascii=False))
            _status["messages_sent"] += 1
            count += 1
        except Exception as e:
            log.warning(f"offline_flush error on msg {msg.get('id','?')}: {e}")
            break
    log.info(f"📤 offline_flush: delivered {count} queued message(s) to peer '{peer_id}'")
    return count


def _offline_queue_snapshot() -> dict:
    """Return serializable snapshot of the offline queue for GET /offline-queue. (v2.0)"""
    with _offline_lock:
        return {
            peer_id: {
                "depth": len(q),
                "messages": [
                    {"id": m.get("id"), "type": m.get("type"), "queued_at": m.get("_queued_at")}
                    for m in q
                ],
            }
            for peer_id, q in _offline_queue.items()
        }


async def _ws_send(msg, peer_id=None):
    """Send msg over WebSocket.
    If peer_id is provided, route to that specific peer's WS connection.
    Falls back to legacy _peer_ws for single-peer / backward-compat.
    On ConnectionError: buffers to offline queue (v2.0).
    """
    ws = None
    if peer_id and peer_id in _peers:
        ws = _peers[peer_id].get("ws")
        if ws is None:
            # v2.0: peer known but offline — buffer for later delivery
            _offline_enqueue(msg, peer_id=peer_id)
            raise ConnectionError(f"Peer '{peer_id}' offline — message queued for delivery on reconnect")
        # Update per-peer counter
        _peers[peer_id]["messages_sent"] = _peers[peer_id].get("messages_sent", 0) + 1
    else:
        ws = _peer_ws
    if ws is None:
        # v2.0: no peer at all — buffer under "default" key
        _offline_enqueue(msg, peer_id=peer_id or "default")
        raise ConnectionError("No P2P connection — message queued for delivery on reconnect")
    await ws.send(json.dumps(_attach_sig(msg), ensure_ascii=False))
    _status["messages_sent"] += 1

def _ws_send_sync(msg, peer_id=None):
    asyncio.run_coroutine_threadsafe(_ws_send(msg, peer_id=peer_id), _loop).result(timeout=10)

async def _send_agent_card(ws):
    # v1.9: send signed AgentCard so peer can auto-verify upon receipt
    card = _status["agent_card"] or {}
    signed = _sign_agent_card(card)
    await ws.send(json.dumps({"type": "acp.agent_card", "message_id": _make_id("card"),
                               "ts": _now(), "card": signed}))


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

        # v0.6: register in multi-session peer registry
        peer_id = _register_peer(ws=websocket)
        _status["peer_count"] = sum(1 for p2 in _peers.values() if p2["connected"])

        # v2.0: flush offline queue for this peer (and "default" bucket) on reconnect
        flushed = await _offline_flush(websocket, peer_id=peer_id)
        if flushed == 0:
            flushed = await _offline_flush(websocket, peer_id="default")
        if flushed:
            log.info(f"📤 Flushed {flushed} offline message(s) to peer '{peer_id}' on connect")

        print(f"\n{'='*55}")
        print(f"ACP P2P v{VERSION} - peer connected [id={peer_id}]")
        print(f"  Send:     POST http://localhost:{http_port}/message:send")
        print(f"  Send→{peer_id}: POST http://localhost:{http_port}/peer/{peer_id}/send")
        print(f"  Peers:    GET  http://localhost:{http_port}/peers")
        print(f"  Recv:     GET  http://localhost:{http_port}/recv")
        print(f"  Stream:   GET  http://localhost:{http_port}/stream")
        print(f"  Card:     GET  http://localhost:{http_port}/.well-known/acp.json")
        print(f"  Tasks:    GET  http://localhost:{http_port}/tasks")
        print(f"{'='*55}\n")

        try:
            async for raw in websocket:
                _on_message(raw)
        except websockets.exceptions.ConnectionClosed:
            log.info(f"Peer {peer_id} disconnected")
        finally:
            _unregister_peer(peer_id)
            _peer_ws = None
            _status["connected"] = False
            _status["peer_card"] = None
            _status["peer_card_verification"] = None   # v1.9: clear on disconnect
            _status["peer_count"] = sum(1 for p2 in _peers.values() if p2["connected"])
            _broadcast_sse_event("peer", {"event": "disconnected", "peer_id": peer_id})

    log.info("Detecting public IP...")
    public_ip = await asyncio.get_event_loop().run_in_executor(None, lambda: get_public_ip(4.0))
    display_ip = public_ip or get_local_ip()
    p2p_link = f"acp://{display_ip}:{ws_port}/{token}"

    # ── 启动时预注册 relay session，使用与 P2P 相同的 token ──────────
    # 传输层对应用层透明：链接只暴露 token，底层用同一个 token 同时监听 P2P 和中继
    DEFAULT_RELAY = "https://black-silence-11c4.yuranliu888.workers.dev"
    relay_link = None
    relay_token = token  # ← 与 P2P token 保持一致，接收方降级时直接复用
    try:
        import subprocess as _sp_h
        # 用指定 token 创建 relay session（Worker 支持 POST /acp/new?token=xxx）
        r = _sp_h.run(
            ["curl", "-s", "--max-time", "8", "-X", "POST",
             f"{DEFAULT_RELAY}/acp/new?token={token}",
             "-H", "Content-Type: application/json", "-d", "{}"],
            capture_output=True, text=True
        )
        resp = json.loads(r.stdout)
        relay_token = resp.get("token", token)
        relay_link  = resp.get("link", f"acp+wss://{DEFAULT_RELAY.replace('https://','')}/acp/{token}")
        # 加入自己的 relay session（等对方来 join）
        _sp_h.run(
            ["curl", "-s", "--max-time", "8", "-X", "POST",
             f"{DEFAULT_RELAY}/acp/{relay_token}/join",
             "-H", "Content-Type: application/json",
             "-d", json.dumps({"name": _status.get("agent_name","ACP-Agent")})],
            capture_output=True
        )
        log.info(f"Relay session pre-registered with token: {relay_token}")
    except Exception as e:
        log.warning(f"Relay pre-register failed (P2P only): {e}")

    # 链接格式：acp://IP:PORT/TOKEN（应用层标识，不含传输层细节）
    link = p2p_link
    _status["link"] = link
    _status["relay_token"] = relay_token if relay_link else None

    # 同时在后台持续监听 relay（对方走中继时能收到消息）
    if relay_link:
        relay_base = DEFAULT_RELAY
        _status["relay_base_url"] = relay_base  # expose for DCUtR HTTP reflection (v1.4)
        asyncio.ensure_future(_http_relay_guest(relay_base, relay_token, http_port))

    async with websockets.serve(on_guest, "0.0.0.0", ws_port):
        print(f"\n{'='*60}")
        print(f"ACP P2P v{VERSION} - service started")
        print(f"  IP: {'public' if public_ip else 'LAN'} {display_ip}")
        print(f"\n  Your link (send this to peer):")
        print(f"  {link}")
        print(f"\n  Transport: P2P ready | Relay pre-registered (auto-fallback)")
        print(f"  Waiting for peer...")
        print(f"{'='*60}\n")
        await asyncio.Future()


# ══════════════════════════════════════════════════════════════════════════════
# GUEST mode
# ══════════════════════════════════════════════════════════════════════════════

async def guest_mode(host, ws_port, token, http_port, embedded_relay=None):
    """
    P2P 直连模式。连接失败超过 P2P_MAX_RETRIES 次后，
    自动降级到中继。传输层选择对应用层透明。
    token 同时是 P2P token 和 relay session token（同一标识符）。
    embedded_relay: 保留参数（兼容旧调用），实际不再需要
    """
    global _peer_ws
    _embedded_relay = embedded_relay  # 保留兼容性
    uri = f"ws://{host}:{ws_port}/{token}"
    P2P_MAX_RETRIES = 3   # P2P 最多尝试 3 次，失败后自动降级
    retry = 0

    while retry < P2P_MAX_RETRIES:
        try:
            log.info(f"{'Reconnecting #' + str(retry) if retry else 'Connecting to (P2P)'}: {uri}")
            async with await _proxy_ws_connect(uri, ping_interval=20, ping_timeout=10) as ws:
                _peer_ws = ws
                _status["connected"]  = True
                _status["session_id"] = "sess_" + uuid.uuid4().hex[:12]
                _status["started_at"] = _status["started_at"] or time.time()
                if retry > 0:
                    _status["reconnect_count"] += 1
                await _send_agent_card(ws)
                _broadcast_sse_event("peer", {"event": "connected", "session_id": _status["session_id"]})

                # v0.6: register in multi-session peer registry
                # BUG-003 fix: reuse the peer pre-registered by /peers/connect if link matches,
                # instead of creating a duplicate entry.
                peer_link = f"acp://{host}:{ws_port}/{token}"
                existing_pid = next(
                    (pid for pid, info in _peers.items()
                     if info.get("link") == peer_link and info.get("ws") is None),
                    None
                )
                if existing_pid:
                    _peers[existing_pid]["ws"] = ws
                    _peers[existing_pid]["connected"] = True
                    _peers[existing_pid]["connected_at"] = _now()
                    peer_id = existing_pid
                else:
                    peer_id = _register_peer(link=peer_link, ws=ws)
                _status["peer_count"] = sum(1 for p2 in _peers.values() if p2["connected"])

                # v2.0: flush offline queue on (re)connect
                flushed = await _offline_flush(ws, peer_id=peer_id)
                if flushed == 0:
                    flushed = await _offline_flush(ws, peer_id="default")
                if flushed:
                    log.info(f"📤 Flushed {flushed} offline message(s) to host '{peer_id}' on connect")

                print(f"\n{'='*55}")
                print(f"ACP P2P v{VERSION} - {'reconnected' if retry else 'connected'} [P2P] [id={peer_id}]")
                print(f"  Peer: {host}:{ws_port}")
                print(f"  Send:     POST http://localhost:{http_port}/message:send")
                print(f"  Send→{peer_id}: POST http://localhost:{http_port}/peer/{peer_id}/send")
                print(f"  Peers:    GET  http://localhost:{http_port}/peers")
                print(f"  Stream:   GET  http://localhost:{http_port}/stream")
                print(f"{'='*55}\n")

                retry = 0
                async for raw in ws:
                    _on_message(raw)

        except (ConnectionRefusedError, OSError,
                websockets.exceptions.InvalidProxyMessage,
                websockets.exceptions.InvalidHandshake) as e:
            log.warning(f"P2P failed ({type(e).__name__}) - retry {retry+1}/{P2P_MAX_RETRIES}")
        except websockets.exceptions.ConnectionClosed:
            log.info(f"P2P closed - retry {retry+1}/{P2P_MAX_RETRIES}")
        except Exception as e:
            log.warning(f"P2P unexpected error: {e} - retry {retry+1}/{P2P_MAX_RETRIES}")
        finally:
            # v0.6: unregister peer from registry
            _peer_link_key = f"acp://{host}:{ws_port}/{token}"
            for _pid, _pinfo in _peers.items():
                if _pinfo.get("link") == _peer_link_key:
                    _unregister_peer(_pid)
                    break
            _peer_ws = None
            _status["connected"] = False
            _status["peer_card"] = None
            _status["peer_card_verification"] = None   # v1.9: clear on disconnect
            _status["peer_count"] = sum(1 for p2 in _peers.values() if p2["connected"])
            _broadcast_sse_event("peer", {"event": "disconnected"})

        retry += 1
        if retry < P2P_MAX_RETRIES:
            await asyncio.sleep(min(2 ** retry, 8))

    # ── BUG-012 fix: mark all P2P peers as disconnected before relay fallback ──
    # P2P peers are tied to direct WebSocket connections; relay is a different
    # transport. Keeping connected=True would allow /peer/{id}/send to silently
    # send via relay while the actual peer may be offline → fake ok=true.
    for _pid2 in list(_peers.keys()):
        if _peers[_pid2].get("connected"):
            _unregister_peer(_pid2)
            log.info(f"Relay fallback: marked peer '{_pid2}' as disconnected (P2P lost)")
    _status["peer_count"] = 0

    # ── Level 2: DCUtR UDP hole punch (v1.4) ─────────────────────────────────
    # Before falling back to relay-as-transport, attempt UDP hole punching.
    # We establish a *signaling-only* relay WS, exchange addresses, punch holes,
    # then connect directly via the punched address. If punching fails (symmetric
    # NAT, CGNAT, ~25% of cases), we fall through to Level 3 relay as normal.
    DEFAULT_RELAY = "https://black-silence-11c4.yuranliu888.workers.dev"
    _dcutr_direct_addr = None

    print(f"\n{'='*55}")
    print(f"⚡ P2P direct connect failed. Trying NAT hole punch (Level 2)...")
    print(f"{'='*55}\n")
    log.info("[v1.4] Attempting DCUtR hole punch before relay fallback")

    try:
        relay_ws_url = DEFAULT_RELAY.replace("https://", "wss://") + f"/acp/{token}/ws"
        async with await asyncio.wait_for(
            _proxy_ws_connect(relay_ws_url, open_timeout=5),
            timeout=6.0,
        ) as _sig_ws:
            log.info(f"[DCUtR] signaling channel established via relay: {relay_ws_url}")
            _status["dcutr_state"] = "punching"
            _broadcast_sse_event("peer", {"event": "dcutr_started"})
            puncher = DCUtRPuncher()
            _dcutr_direct_addr = await asyncio.wait_for(
                puncher.attempt(_sig_ws, local_udp_port=0),
                timeout=12.0,
            )
    except asyncio.TimeoutError:
        log.debug("[DCUtR] hole punch timed out (12s) — falling through to relay")
    except Exception as e:
        log.debug(f"[DCUtR] hole punch error ({type(e).__name__}): {e} — falling through to relay")
    finally:
        _status.pop("dcutr_state", None)

    if _dcutr_direct_addr is not None:
        # ── Hole punch succeeded: connect directly ────────────────────────────
        direct_host, direct_port = _dcutr_direct_addr
        direct_uri = f"ws://{direct_host}:{direct_port}/{token}"
        log.info(f"[DCUtR] hole punch succeeded → direct connect: {direct_uri}")
        print(f"\n{'='*55}")
        print(f"✅ NAT hole punch SUCCESS — direct P2P connection established!")
        print(f"   Peer: {direct_host}:{direct_port} (punched)")
        print(f"{'='*55}\n")
        _status["connection_type"] = "dcutr_direct"
        _broadcast_sse_event("peer", {"event": "dcutr_connected",
                                       "peer_addr": f"{direct_host}:{direct_port}"})
        # Re-enter guest mode with the punched address (Level 1 will succeed this time)
        await guest_mode(direct_host, direct_port, token, http_port)
        return

    # ── Level 3: Relay fallback ───────────────────────────────────────────────
    log.warning(f"[v1.4] DCUtR hole punch failed. Falling back to relay (Level 3).")
    log.warning(f"P2P unreachable after {P2P_MAX_RETRIES} retries. Auto-fallback to relay.")
    _status["connection_type"] = "relay"
    _broadcast_sse_event("peer", {"event": "relay_fallback",
                                   "reason": "dcutr_failed"})
    print(f"\n{'='*55}")
    print(f"⚠️  NAT hole punch failed. Auto-fallback to relay (Level 3)...")
    print(f"{'='*55}\n")

    import subprocess as _sp

    # P2P token == relay token（同一标识符，传输层透明）
    # 发起方启动时已用此 token 在 relay 预注册，直接 join 即可
    relay_base  = DEFAULT_RELAY
    relay_token = token
    relay_link  = f"acp+wss://{DEFAULT_RELAY.replace('https://','')}/acp/{token}"
    log.info(f"Auto-fallback: joining relay session with same token: {token}")

    # Join relay session
    agent_name = _status.get("agent_name", "ACP-Agent")
    try:
        _sp.run(
            ["curl", "-s", "--max-time", "10", "-X", "POST",
             f"{relay_base}/acp/{relay_token}/join",
             "-H", "Content-Type: application/json",
             "-d", json.dumps({"name": agent_name})],
            capture_output=True
        )
    except Exception as e:
        log.warning(f"Relay join failed: {e}")

    _status["link"] = relay_link

    print(f"\n{'='*55}")
    print(f"✅ Relay session ready [AUTO-FALLBACK]")
    print(f"   Relay: {relay_link}")
    print(f"{'='*55}\n")

    await _http_relay_guest(relay_base, relay_token, http_port)


# ══════════════════════════════════════════════════════════════════════════════
# Local HTTP interface
# ══════════════════════════════════════════════════════════════════════════════

class _BodyReadError(BaseException):
    """Raised by LocalHTTP._read_body when it has already written a 400 response.
    Inherits BaseException (not Exception) so it bypasses all 'except Exception'
    handlers and propagates cleanly to the do_POST wrapper."""


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
        if not raw.strip():
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            # BUG-011 fix: invalid JSON should be 400 ERR_INVALID_REQUEST, not 500 ERR_INTERNAL
            e_body, e_code = _err(ERR_INVALID_REQUEST, f"Invalid JSON in request body: {e}", 400)
            self._json(e_body, e_code)
            raise _BodyReadError() from e  # signal caller to stop processing

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

        if p in ("/card", "/.well-known/acp.json"):  # [stable] AgentCard
            # Rebuild dynamically so capabilities like lan_discovery reflect runtime state
            skills = [s["id"] for s in (_status.get("agent_card") or {}).get("skills", [])]
            live_card = _make_agent_card(_status.get("agent_name", "ACP-Agent"), skills)
            # v1.8: attach Ed25519 self-signature when identity is enabled
            live_card = _sign_agent_card(live_card)
            self._json({"self": live_card, "peer": _status.get("peer_card")})

        # ── GET /.well-known/did.json — W3C DID Document (v1.3) ───────────────
        elif p == "/.well-known/did.json":
            """Return a W3C-compatible DID Document for this Agent's did:acp: identity.

            Requires --identity flag (Ed25519 keypair).  Returns 404 when
            identity is not enabled.

            The DID Document maps the did:acp: identifier to:
              - A verificationMethod (Ed25519VerificationKey2020)
              - A service endpoint pointing to the current ACP session link
            """
            if not _ed25519_private or not _did_acp:
                self._json({"error": "DID identity not enabled — start with --identity"}, 404)
                return

            link    = _status.get("link")
            did_doc = {
                "@context": [
                    "https://www.w3.org/ns/did/v1",
                    "https://w3id.org/security/suites/ed25519-2020/v1",
                ],
                "id": _did_acp,
                "verificationMethod": [{
                    "id":                f"{_did_acp}#key-1",
                    "type":              "Ed25519VerificationKey2020",
                    "controller":        _did_acp,
                    "publicKeyMultibase": f"z{_ed25519_public_b64}",  # 'z' = base64url multibase prefix
                }],
                "authentication":       [f"{_did_acp}#key-1"],
                "assertionMethod":      [f"{_did_acp}#key-1"],
                "service": ([{
                    "id":              f"{_did_acp}#acp",
                    "type":            "ACPRelay",
                    "serviceEndpoint": link,
                }] if link else []),
            }
            self._json(did_doc)

        elif p == "/status":  # [stable] relay status
            self._json(_status)

        elif p == "/link":
            self._json({"link": _status.get("link"), "session_id": _status.get("session_id")})

        # ── GET /peers — list all known peers (v0.6)  [stable] ─────────────────
        elif p == "/peers":
            peer_list = []
            for pid, info in _peers.items():
                peer_list.append({
                    "id":               info["id"],
                    "name":             info["name"],
                    "link":             info.get("link"),
                    "connected":        info["connected"],
                    "connected_at":     info.get("connected_at"),
                    "disconnected_at":  info.get("disconnected_at"),
                    "messages_sent":    info.get("messages_sent", 0),
                    "messages_received": info.get("messages_received", 0),
                    "agent_card":       info.get("agent_card"),
                })
            active = sum(1 for p2 in _peers.values() if p2["connected"])
            self._json({"peers": peer_list, "count": len(peer_list), "active": active})

        # ── GET /peers/discover — LAN port-scan discovery (v2.1) ─────────────
        elif p == "/peers/discover":
            """
            Scan the local /24 subnet for ACP relays via TCP port probe +
            /.well-known/acp.json fingerprinting.

            Does NOT require --advertise-mdns; works against any ACP relay
            on the same LAN regardless of whether it broadcasts mDNS.

            Optional query params:
              ?subnet=192.168.1   override the /24 prefix to scan
              ?ports=7901,7902    comma-separated list of HTTP ports to probe
              ?workers=32         thread pool size (default 64)

            Response:
              {
                "found": [
                  {
                    "host": "192.168.1.42",
                    "http_port": 7901,
                    "name": "Agent-Alice",
                    "link": "acp://192.168.1.42:7801/tok_xxx",
                    "agent_card": { ... },
                    "latency_ms": 3.2
                  }
                ],
                "scanned_hosts": 253,
                "scanned_ports": 1518,
                "subnet": "192.168.1",
                "duration_ms": 1240,
                "mdns_peers": [ ... ],   # mDNS cache merged in (deduped by host)
                "error": null
              }

            Typically completes in 1-3 seconds on a /24 LAN with default settings.
            """
            qs = parse_qs(urlparse(self.path).query)
            scan_subnet = qs.get("subnet", [None])[0]
            raw_ports   = qs.get("ports",  [None])[0]
            raw_workers = qs.get("workers",["64"])[0]
            scan_ports  = (
                [int(p.strip()) for p in raw_ports.split(",") if p.strip().isdigit()]
                if raw_ports else None
            )
            try:
                workers = max(1, min(256, int(raw_workers)))
            except ValueError:
                workers = 64

            my_http_port = _status.get("http_port")
            result = _lan_port_scan(
                subnet=scan_subnet,
                ports=scan_ports,
                max_workers=workers,
                skip_self_port=my_http_port,
            )

            # Merge mDNS cache — add entries not already found by port scan
            mdns_peers = _mdns_peer_list()
            scan_hosts = {r["host"] for r in result["found"]}
            for mp in mdns_peers:
                mp_host = mp.get("host") or mp.get("ip")
                if mp_host and mp_host not in scan_hosts:
                    result["found"].append({
                        "host": mp_host,
                        "http_port": mp.get("http_port"),
                        "name": mp.get("name"),
                        "link": mp.get("link"),
                        "agent_card": None,
                        "latency_ms": None,
                        "source": "mdns",
                    })

            result["mdns_peers"] = mdns_peers
            result["total_found"] = len(result["found"])
            self._json(result)

        # ── GET /discover — LAN peers via mDNS (v0.7)  [experimental] ──────────
        elif p == "/discover":
            discovered = _mdns_peer_list()
            self._json({
                "lan_peers":  discovered,
                "count":      len(discovered),
                "mdns_active": _mdns_running,
                "note": "Start with --advertise-mdns to enable LAN discovery" if not _mdns_running else None,
            })

        # ── GET /extensions — list declared extensions (v1.3) ────────────────
        elif p == "/extensions":
            self._json({
                "extensions": list(_extensions),
                "count":      len(_extensions),
            })

        # ── GET /offline-queue — inspect offline delivery buffer (v2.0) ─────────
        elif p == "/offline-queue":
            """
            Return a snapshot of the offline delivery queue.

            Messages are buffered here when POST /message:send (or /send) is called
            while no peer is connected. On peer reconnect, the queue is automatically
            flushed in FIFO order.

            Response fields:
              - total_queued (int): total messages across all peer buckets
              - queue (dict): {peer_id: {depth, messages: [{id, type, queued_at}]}}
              - max_per_peer (int): per-peer queue capacity (OFFLINE_QUEUE_MAXLEN)
            """
            snap = _offline_queue_snapshot()
            total = sum(v["depth"] for v in snap.values())
            self._json({
                "total_queued": total,
                "max_per_peer": OFFLINE_QUEUE_MAXLEN,
                "queue": snap,
            })

        # ── GET /peer/verify — peer AgentCard auto-verification result (v1.9) ──
        elif p == "/peer/verify":
            """
            Return the auto-verification result for the currently connected peer's AgentCard.

            Result is computed on receipt of acp.agent_card during handshake (v1.9).
            Returns 404 when no peer is connected.

            Fields:
              - verified (bool): True if peer's card_sig is cryptographically valid
              - valid (bool|None): raw result from _verify_agent_card
              - did (str|None): peer's did:acp: identifier
              - did_consistent (bool|None): did matches public_key
              - public_key (str|None): peer's Ed25519 public key (base64url)
              - scheme (str): peer's identity scheme
              - error (str|None): reason if invalid or unsigned
              - peer_name (str|None): peer's agent name
            """
            if not _status.get("connected") or _status.get("peer_card") is None:
                self._json({"error": "no peer connected"}, 404)
                return
            vr = _status.get("peer_card_verification") or {}
            peer_card = _status.get("peer_card") or {}
            self._json({
                "peer_name":    peer_card.get("name"),
                "peer_did":     vr.get("did"),
                "verified":     vr.get("valid") is True,
                "valid":        vr.get("valid"),
                "did_consistent": vr.get("did_consistent"),
                "public_key":   vr.get("public_key"),
                "scheme":       vr.get("scheme"),
                "error":        vr.get("error"),
            })

        # ── GET /verify/card — return self-verification result (v1.8) ─────────
        elif p == "/verify/card":
            skills = [s["id"] for s in (_status.get("agent_card") or {}).get("skills", [])]
            live_card = _make_agent_card(_status.get("agent_name", "ACP-Agent"), skills)
            signed_card = _sign_agent_card(live_card)
            result = _verify_agent_card(signed_card)
            self._json({"self_verification": result, "card_signed": bool(_ed25519_private)})

        # ── GET /peers/{id} — single peer info (v0.6) ─────────────────────────
        elif p.startswith("/peers/") and not p.endswith("/send"):
            peer_id = p[len("/peers/"):]
            info = _peers.get(peer_id)
            if not info:
                self._json({"error": f"peer '{peer_id}' not found"}, 404)
            else:
                self._json({k: v for k, v in info.items() if k != "ws"})

        elif p == "/connect" and self.command == "POST":
            # 对等连接：主动连接对方链接，无主从之分
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length) or b"{}")
            except Exception:
                body = {}
            peer_link = body.get("link", "")
            if not peer_link:
                self._json({"error": "missing link"}, 400)
                return
            def _do_connect():
                result = parse_link(peer_link)
                host, port, token, scheme = result
                http_port = _status.get("http_port", 7901)
                if scheme == "http_relay":
                    asyncio.run_coroutine_threadsafe(
                        _http_relay_guest(host, token, http_port), _loop)
                else:
                    asyncio.run_coroutine_threadsafe(
                        guest_mode(host, port, token, http_port), _loop)
            threading.Thread(target=_do_connect, daemon=True).start()
            self._json({"ok": True, "connecting_to": peer_link})

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

        elif p == "/recv":  # [stable] poll received messages
            limit = int(qs.get("limit", ["50"])[0])
            msgs  = [_recv_queue.popleft() for _ in range(min(limit, len(_recv_queue)))]
            self._json({"messages": msgs, "count": len(msgs), "remaining": len(_recv_queue)})

        elif p == "/tasks":  # [stable] task CRUD — supports pagination (v1.1)
            # Query params:
            #   state=<status>         filter by status
            #   limit=<n>              max tasks to return (default 50, max 200)
            #   cursor=<task_id>       exclusive cursor: return tasks after this id
            #   peer_id=<peer_id>      filter by originating peer
            #   sort=created_asc|created_desc  (default: created_desc, newest first)
            #   created_after=<iso>    filter tasks created after this ISO-8601 timestamp
            #   updated_after=<iso>    filter tasks updated after this ISO-8601 timestamp
            state_filter    = qs.get("state",          [None])[0]
            peer_filter     = qs.get("peer_id",        [None])[0]
            created_after   = qs.get("created_after",  [None])[0]
            updated_after   = qs.get("updated_after",  [None])[0]
            limit           = min(int(qs.get("limit",  ["50"])[0]),  200)
            cursor        = qs.get("cursor", [None])[0]
            sort_order    = qs.get("sort",   ["created_desc"])[0]

            tasks = list(_tasks.values())

            # Filter
            if state_filter:
                tasks = [t for t in tasks if t.get("status") == state_filter]
            if peer_filter:
                tasks = [t for t in tasks if
                         t.get("peer_id") == peer_filter or
                         t.get("payload", {}).get("peer_id") == peer_filter]
            if created_after:
                tasks = [t for t in tasks if t.get("created_at", "") > created_after]
            if updated_after:
                tasks = [t for t in tasks if t.get("updated_at", t.get("created_at", "")) > updated_after]

            # Sort by creation time (task_id contains timestamp prefix for natural sort)
            reverse = (sort_order != "created_asc")
            tasks.sort(key=lambda t: t.get("created_at", ""), reverse=reverse)

            # Cursor pagination (keyset-based, exclusive)
            if cursor and cursor in _tasks:
                try:
                    cursor_idx = next(i for i, t in enumerate(tasks) if t["id"] == cursor)
                    tasks = tasks[cursor_idx + 1:]
                except StopIteration:
                    tasks = []

            # Limit + next_cursor
            has_more    = len(tasks) > limit
            page        = tasks[:limit]
            next_cursor = page[-1]["id"] if has_more and page else None

            self._json({
                "tasks":       page,
                "count":       len(page),
                "total":       len(_tasks),
                "has_more":    has_more,
                "next_cursor": next_cursor,
            })

        # GET /tasks/{id}/wait?timeout=30 — 同步等待 task 进入 terminal 状态
        # BUG-008 fix: support both /wait and :wait styles
        elif p.startswith("/tasks/") and (p.endswith("/wait") or p.endswith(":wait")):
            sep_len = len("/wait") if p.endswith("/wait") else len(":wait")
            task_id = p[len("/tasks/"):-sep_len]
            timeout = float(qs.get("timeout", ["30"])[0])
            task = _tasks.get(task_id)
            if not task:
                self._json({"error": "task not found"}, 404)
                return
            if task["status"] in TERMINAL_STATES:
                self._json({"task": task, "waited": False})
                return
            deadline = time.time() + timeout
            while time.time() < deadline:
                task = _tasks.get(task_id)
                if task and task["status"] in TERMINAL_STATES:
                    self._json({"task": task, "waited": True})
                    return
                time.sleep(0.5)
            self._json({"task": _tasks.get(task_id), "waited": True, "timeout": True}, 202)

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
                self.close_connection = False
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("X-Accel-Buffering", "no")
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
                            _sse_notify.wait(timeout=30); _sse_notify.clear()
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

        elif p == "/stream":  # [stable] SSE event stream
            # BUG-001 additional fix: prevent BaseHTTP HTTP/1.0 from closing
            # the connection after headers. SSE requires a persistent connection.
            self.close_connection = False
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Accel-Buffering", "no")
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
                        _sse_notify.wait(timeout=30); _sse_notify.clear()
            except Exception:
                pass
            finally:
                if q in _sse_subscribers:
                    _sse_subscribers.remove(q)

        else:
            self._json({"error": "not found"}, 404)

    # ── POST ──────────────────────────────────────────────────────────────────

    def do_POST(self):
        global _extensions  # v1.3: may be mutated by /extensions/register and /extensions/unregister
        try:
            self._do_POST_inner()
        except _BodyReadError:
            pass  # Response already written by _read_body; just stop processing

    def _do_POST_inner(self):
        global _extensions
        parsed = urlparse(self.path)
        p = parsed.path

        # /message:send  — primary v0.5 endpoint (A2A-aligned)  [stable]
        # Accepts: {message_id?, role, parts|text, task_id?, context_id?, sync?, timeout?}
        # Required fields (server-side validated, v0.9):
        #   role    — must be present and one of: "user" | "agent"
        #   content — at least one of: parts (non-empty list) or text/content (non-empty string)
        if p == "/message:send":
            try:
                body = self._read_body()

                # ── v0.9: server-side required-field validation ───────────────
                # Pre-extract client-supplied message_id for failed_message_id in errors
                _client_msg_id = body.get("message_id")  # may be None; used in error envelopes
                _VALID_ROLES = {"user", "agent"}
                role_raw = body.get("role")
                if role_raw is None:
                    e_body, e_code = _err(ERR_INVALID_REQUEST,
                                          "missing required field: role (must be 'user' or 'agent')",
                                          failed_message_id=_client_msg_id)
                    self._json(e_body, e_code)
                    return
                if role_raw not in _VALID_ROLES:
                    e_body, e_code = _err(ERR_INVALID_REQUEST,
                                          f"invalid role '{role_raw}': must be 'user' or 'agent'",
                                          failed_message_id=_client_msg_id)
                    self._json(e_body, e_code)
                    return

                # ── BUG-007 fix: multi-peer ambiguity guard ────────────────────
                # When >1 peers are connected and no peer_id is supplied,
                # /message:send cannot unambiguously route the message.
                # Return ERR_AMBIGUOUS_PEER and guide the caller to use
                # POST /peer/{id}/send instead.
                _req_peer_id = body.get("peer_id")
                _connected_peers = [pid for pid, pinfo in _peers.items() if pinfo.get("connected")]
                if len(_connected_peers) > 1 and not _req_peer_id:
                    e_body, e_code = _err(
                        "ERR_AMBIGUOUS_PEER",
                        f"multiple peers connected ({len(_connected_peers)}); "
                        "specify 'peer_id' in the request body or use "
                        "POST /peer/{{id}}/send for directed delivery",
                        400,
                        failed_message_id=_client_msg_id,
                    )
                    e_body["connected_peers"] = _connected_peers
                    self._json(e_body, e_code)
                    return

                # ── Build structured message ───────────────────────────────────
                parts = body.get("parts")
                if parts:
                    ok, err = _validate_parts(parts)
                    if not ok:
                        e_body, e_code = _err(ERR_INVALID_REQUEST, err,
                                              failed_message_id=_client_msg_id)
                        self._json(e_body, e_code)
                        return
                else:
                    # Auto-wrap plain text in a text Part
                    text = body.get("text") or body.get("content") or ""
                    parts = [_make_text_part(str(text))] if text else []
                    if not parts:
                        e_body, e_code = _err(ERR_INVALID_REQUEST,
                                              "missing required field: provide 'parts' (list) or 'text' (string)",
                                              failed_message_id=_client_msg_id)
                        self._json(e_body, e_code)
                        return

                message_id = body.get("message_id") or _make_id("msg")
                msg = {
                    "type":       "acp.message",
                    "message_id": message_id,
                    "server_seq": _next_seq(),
                    "ts":         _now(),
                    "from":       _status.get("agent_name", "unknown"),
                    "role":       role_raw,
                    "parts":      parts,
                }
                if body.get("task_id"):
                    msg["task_id"] = body["task_id"]
                if body.get("context_id"):
                    msg["context_id"] = body["context_id"]

                serialized = json.dumps(msg, ensure_ascii=False)
                if len(serialized.encode()) > MAX_MSG_BYTES:
                    e_body, e_code = _err(ERR_MSG_TOO_LARGE,
                                          f"message too large (max {MAX_MSG_BYTES} bytes)", 413,
                                          failed_message_id=message_id)
                    self._json(e_body, e_code)
                    return

                want_sync = body.get("sync", False)
                timeout   = float(body.get("timeout", 30))

                # Create task if requested
                task = None
                if body.get("create_task", False):
                    task = _create_task({"parts": parts}, message_id=message_id,
                                        context_id=body.get("context_id"))  # v1.7: propagate context_id
                    msg["task_id"] = task["id"]
                    if task:
                        _update_task(task["id"], TASK_WORKING)

                if want_sync:
                    msg["correlation_id"] = message_id
                    future = _loop.create_future()
                    _sync_pending[message_id] = future
                    _ws_send_sync(msg, peer_id=_req_peer_id or None)
                    try:
                        reply = asyncio.run_coroutine_threadsafe(
                            asyncio.wait_for(asyncio.shield(future), timeout=timeout), _loop
                        ).result(timeout=timeout + 2)
                        _sync_pending.pop(message_id, None)
                        if task:
                            _update_task(task["id"], TASK_COMPLETED, artifact={"parts": reply.get("parts", [])})
                        self._json({"ok": True, "message_id": message_id,
                                    "server_seq": msg["server_seq"], "reply": reply, "task": task})
                    except asyncio.TimeoutError:
                        _sync_pending.pop(message_id, None)
                        if task:
                            _update_task(task["id"], TASK_FAILED, error="reply timeout")
                        e_body, e_code = _err(ERR_TIMEOUT, "reply timeout", 408,
                                              failed_message_id=message_id)
                        self._json(e_body, e_code)
                else:
                    seq = msg["server_seq"]
                    # BUG-007 fix (part 2): when peer_id supplied in body, route to that peer
                    _ws_send_sync(msg, peer_id=_req_peer_id or None)
                    # BUG-001 fix: broadcast SSE event for outbound messages so local stream
                    #              subscribers see all traffic (not just WS-received messages).
                    # BUG-004 fix: also persist to local recv_queue so /recv and /stream reflect send.
                    _broadcast_sse_event("message", {
                        "message_id": message_id,
                        "role":       role_raw,
                        "parts":      parts,
                        "task_id":    msg.get("task_id"),
                        "direction":  "outbound",
                    })
                    self._json({"ok": True, "message_id": message_id, "server_seq": seq, "task": task})

            except ConnectionError as e:
                # message_id may be defined if we got past body parsing
                _fmid = locals().get("message_id") or locals().get("_client_msg_id")
                e_body, e_code = _err(ERR_NOT_CONNECTED, str(e), 503,
                                     failed_message_id=_fmid)
                self._json(e_body, e_code)
            except Exception as e:
                _fmid = locals().get("message_id") or locals().get("_client_msg_id")
                e_body, e_code = _err(ERR_INTERNAL, str(e), 500,
                                     failed_message_id=_fmid)
                self._json(e_body, e_code)

        # /send  — legacy endpoint (backward-compat)
        elif p == "/send":  # [stable] legacy alias for /message:send
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

        # ── POST /peer/{id}/send — directed send to a specific peer (v0.6) ───
        # Allows one Agent to maintain multiple peer connections and send
        # messages to a specific peer by peer_id.
        elif p.startswith("/peer/") and p.endswith("/send"):
            peer_id = p[len("/peer/"):-len("/send")]
            try:
                body = self._read_body()
                peer_info = _peers.get(peer_id)
                if not peer_info:
                    self._json({"error": f"peer '{peer_id}' not found"}, 404)
                    return
                if not peer_info.get("connected"):
                    self._json({"error": f"peer '{peer_id}' is not connected"}, 503)
                    return
                if peer_info.get("ws") is None:
                    # Peer registered but WS handshake not yet complete (connecting race)
                    self._json({"ok": False, "error_code": "ERR_PEER_CONNECTING",
                                "error": f"peer '{peer_id}' is connecting, retry shortly"}, 503)
                    return

                parts = body.get("parts")
                if not parts:
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
                    "to_peer":    peer_id,
                    "role":       body.get("role", "user"),
                    "parts":      parts,
                }
                if body.get("task_id"):
                    msg["task_id"] = body["task_id"]

                serialized = json.dumps(msg, ensure_ascii=False)
                if len(serialized.encode()) > MAX_MSG_BYTES:
                    self._json({"ok": False, "error": f"message too large"}, 413)
                    return

                # Send via peer's WebSocket
                # BUG-012 fix: do NOT fallback to _ws_send_sync (relay) when peer ws is None.
                # If the peer's ws is gone, it means the P2P connection was lost.
                # Falling back to relay would send to a ghost session → fake ok=true.
                # Return 503 so the caller knows the peer is unreachable.
                ws = peer_info.get("ws")
                if ws:
                    # Wait for the send to complete and catch WebSocket errors.
                    # This ensures a closed-but-not-yet-unregistered ws returns
                    # 503 instead of silently succeeding (BUG-012).
                    try:
                        future = asyncio.run_coroutine_threadsafe(ws.send(serialized), _loop)
                        future.result(timeout=5)  # blocks up to 5s; raises on ws error
                    except Exception as ws_err:
                        # ws is closed or broken; unregister the peer
                        _unregister_peer(peer_id)
                        _status["peer_count"] = sum(1 for p2 in _peers.values() if p2["connected"])
                        self._json({"ok": False,
                                    "error_code": "ERR_NOT_CONNECTED",
                                    "error": f"peer '{peer_id}' connection lost: {ws_err}"}, 503)
                        return
                else:
                    self._json({"ok": False,
                                "error_code": "ERR_NOT_CONNECTED",
                                "error": f"peer '{peer_id}' WebSocket is not active; P2P connection lost"}, 503)
                    return

                peer_info["messages_sent"] = peer_info.get("messages_sent", 0) + 1
                _status["messages_sent"] += 1
                self._json({"ok": True, "message_id": message_id, "peer_id": peer_id})

            except ConnectionError as e:
                self._json({"ok": False, "error": str(e)}, 503)
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)

        # ── POST /peer/{id}/rename — rename a peer for readability (v0.6) ────
        elif p.startswith("/peer/") and p.endswith("/rename"):
            peer_id = p[len("/peer/"):-len("/rename")]
            try:
                body = self._read_body()
                new_name = body.get("name", "").strip()
                if not new_name:
                    self._json({"error": "name required"}, 400)
                    return
                peer_info = _peers.get(peer_id)
                if not peer_info:
                    self._json({"error": f"peer '{peer_id}' not found"}, 404)
                    return
                old_name = peer_info["name"]
                peer_info["name"] = new_name
                self._json({"ok": True, "peer_id": peer_id,
                            "old_name": old_name, "new_name": new_name})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)

        # ── POST /peers/connect — connect to a new peer, add to registry (v0.6) ─
        elif p == "/peers/connect":  # [stable] connect to peer via acp:// link
            try:
                body = self._read_body()
                peer_link = body.get("link", "").strip()
                peer_name = body.get("name", "").strip()
                if not peer_link:
                    self._json({"error": "link required"}, 400)
                    return
                # BUG-013 fix: validate link format before accepting the request
                try:
                    parse_link(peer_link)
                except ValueError as ve:
                    e_body, _ = _err(ERR_INVALID_REQUEST, str(ve))
                    self._json(e_body, 400)
                    return
                # BUG-003 / BUG-003b fix: idempotent connect — if a peer with the same link
                # already exists (regardless of connected state), return it instead of creating
                # a duplicate. Previously only checked connected=True, which caused duplicates
                # when the WS connection was still being established.
                existing_peer_id = None
                for pid, pinfo in _peers.items():
                    if pinfo.get("link") == peer_link:
                        existing_peer_id = pid
                        break
                if existing_peer_id:
                    self._json({"ok": True, "peer_id": existing_peer_id,
                                "connecting_to": peer_link,
                                "name": _peers[existing_peer_id].get("name", existing_peer_id),
                                "already_connected": True})
                    return
                # Generate peer_id before connecting
                peer_id = _make_peer_id()
                _register_peer(peer_id=peer_id, link=peer_link)
                if peer_name:
                    _peers[peer_id]["name"] = peer_name
                # Connect in background
                def _do_connect():
                    result = parse_link(peer_link)
                    host, port, token, scheme = result
                    http_port = _status.get("http_port", 7901)
                    if scheme == "http_relay":
                        asyncio.run_coroutine_threadsafe(
                            _http_relay_guest(host, token, http_port), _loop)
                    else:
                        asyncio.run_coroutine_threadsafe(
                            guest_mode(host, port, token, http_port), _loop)
                threading.Thread(target=_do_connect, daemon=True).start()
                self._json({"ok": True, "peer_id": peer_id,
                            "connecting_to": peer_link, "name": peer_name or peer_id})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)

        # /tasks/create — create a task (optionally delegate to peer)
        elif p == "/tasks/create" or p == "/tasks":
            try:
                body = self._read_body()
                # BUG-010 fix: validate required 'role' field
                payload = body.get("payload", body)
                role = payload.get("role") if isinstance(payload, dict) else body.get("role")
                if not role:
                    e_body, e_code = _err(ERR_INVALID_REQUEST,
                                          "missing required field: role (must be: agent, user, or system)")
                    self._json(e_body, e_code)
                    return
                task = _create_task(payload,
                                    message_id=body.get("message_id"),
                                    task_id=body.get("task_id"),       # BUG-006 fix: pass client task_id
                                    context_id=body.get("context_id")) # v1.7: propagate context_id to SSE events
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
        # BUG-008 fix: support both /update (slash) and :update (colon) styles
        elif p.startswith("/tasks/") and (p.endswith("/update") or p.endswith(":update")):
            sep_len = len("/update") if p.endswith("/update") else len(":update")
            task_id = p[len("/tasks/"):-sep_len]
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

        # /tasks/{id}/continue — resume input_required task  [stable]
        # BUG-008 fix: support both /continue and :continue styles
        elif p.startswith("/tasks/") and (p.endswith("/continue") or p.endswith(":continue")):
            sep_len = len("/continue") if p.endswith("/continue") else len(":continue")
            task_id = p[len("/tasks/"):-sep_len]
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

        # /tasks/{id}:cancel — A2A-aligned cancel endpoint  [stable]
        elif p.startswith("/tasks/") and p.endswith(":cancel"):
            task_id = p[len("/tasks/"):-len(":cancel")]
            task = _tasks.get(task_id)
            if not task:
                self._json({"error": "task not found"}, 404)
            elif task["status"] in TERMINAL_STATES:
                self._json({"error": f"task already in terminal state: {task['status']}"}, 409)
            else:
                _update_task(task_id, TASK_CANCELED)  # BUG-002 fix: use TASK_CANCELED, not TASK_FAILED
                self._json({"ok": True, "task_id": task_id, "status": TASK_CANCELED})

        # GET /tasks/{id}/wait?timeout=30 — 同步等待 task 进入 terminal 状态
        # 比 SSE subscribe 更简单，适合 Agent 调用
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
        elif p == "/skills/query":  # [stable] QuerySkill runtime capability discovery
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

        # ── POST /extensions/register — runtime extension registration (v1.3) ──
        elif p == "/extensions/register":
            """Register a new Extension in the AgentCard at runtime (v1.3).

            Body:
              {
                "uri":      "https://example.com/ext/billing",   // required
                "required": false,                               // optional, default false
                "params":   { "tier": "pro" }                   // optional
              }

            Returns the updated extensions list.
            Idempotent: re-registering the same URI updates the entry.
            """
            try:
                body = self._read_body()
            except Exception as e:
                self._json({"error": f"invalid JSON: {e}"}, 400)
                return

            uri = body.get("uri")
            if not uri or not isinstance(uri, str):
                self._json({"error": "'uri' is required and must be a string"}, 400)
                return
            if not uri.startswith("http://") and not uri.startswith("https://"):
                self._json({"error": "'uri' must be an http(s) URL"}, 400)
                return

            required = bool(body.get("required", False))
            params   = body.get("params", {})
            if not isinstance(params, dict):
                self._json({"error": "'params' must be a JSON object"}, 400)
                return

            # Upsert: remove existing entry with same URI, then append
            _extensions = [e for e in _extensions if e.get("uri") != uri]
            entry = {"uri": uri, "required": required}
            if params:
                entry["params"] = params
            _extensions.append(entry)
            log.info(f"🔌 Extension registered: {uri} (required={required})")
            self._json({"ok": True, "extensions": list(_extensions)})

        # ── POST /extensions/unregister — remove extension at runtime (v1.3) ─
        elif p == "/extensions/unregister":
            try:
                body = self._read_body()
            except Exception as e:
                self._json({"error": f"invalid JSON: {e}"}, 400)
                return

            uri = body.get("uri")
            if not uri:
                self._json({"error": "'uri' is required"}, 400)
                return

            before = len(_extensions)
            _extensions = [e for e in _extensions if e.get("uri") != uri]
            removed = before - len(_extensions)
            log.info(f"🔌 Extension unregistered: {uri} (found={removed > 0})")
            self._json({"ok": True, "removed": removed, "extensions": list(_extensions)})

        # ── POST /verify/card — verify any AgentCard's Ed25519 self-signature (v1.8) ──
        elif p == "/verify/card":
            """
            Verify an AgentCard's Ed25519 self-signature (v1.8).

            Body: any ACP AgentCard JSON (the 'self' field from /.well-known/acp.json).

            Returns:
              {
                "valid": true/false/null,   # null = cannot verify (lib missing)
                "did": "did:acp:...",       # signer's stable identifier
                "did_consistent": true,     # did:acp: matches public_key
                "public_key": "...",        # base64url Ed25519 public key
                "scheme": "ed25519",        # identity scheme
                "error": null              # human-readable reason if invalid
              }

            Works for any ACP relay's AgentCard — not just this agent's.
            Verifies that the card was signed by the private key matching
            the public_key in card.identity.public_key.
            """
            try:
                body = self._read_body()
            except Exception as e:
                self._json({"error": f"invalid JSON: {e}"}, 400)
                return

            # Accept either the raw card or the wrapped form {"self": card, ...}
            if "self" in body and isinstance(body["self"], dict):
                card = body["self"]
            elif "name" in body or "identity" in body:
                card = body
            else:
                self._json({"error": "expected AgentCard JSON or {\"self\": card}"}, 400)
                return

            result = _verify_agent_card(card)
            self._json(result)

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


    def do_PATCH(self):
        """PATCH /.well-known/acp.json — live-update AgentCard availability block (v1.2).

        Accepts a JSON body with any subset of availability fields:
          {
            "availability": {
              "mode":                    "heartbeat" | "cron" | "persistent" | "manual",
              "interval_seconds":        <int>,
              "next_active_at":          "<ISO-8601-UTC>",
              "last_active_at":          "<ISO-8601-UTC>",
              "task_latency_max_seconds": <int>
            }
          }

        Use-case: a heartbeat agent calls this endpoint on each wake to stamp
        next_active_at and last_active_at without restarting the relay.
        """
        global _availability
        p = urlparse(self.path).path
        if p not in ("/card", "/.well-known/acp.json"):
            self._json({"error": "PATCH only supported on /.well-known/acp.json"}, 404)
            return
        try:
            body = self._read_body()
        except Exception as e:
            self._json({"error": f"invalid JSON: {e}"}, 400)
            return

        patch = body.get("availability")
        if patch is None:
            self._json({"error": "request body must contain 'availability' key"}, 400)
            return
        if not isinstance(patch, dict):
            self._json({"error": "'availability' must be a JSON object"}, 400)
            return

        # Allowed fields for PATCH (whitelist to avoid injection)
        ALLOWED = {"mode", "interval_seconds", "next_active_at",
                   "last_active_at", "task_latency_max_seconds"}
        unknown = set(patch.keys()) - ALLOWED
        if unknown:
            self._json({"error": f"unknown availability fields: {sorted(unknown)}"}, 400)
            return

        # Validate mode if provided
        valid_modes = {"persistent", "heartbeat", "cron", "manual"}
        if "mode" in patch and patch["mode"] not in valid_modes:
            self._json({"error": f"mode must be one of {sorted(valid_modes)}"}, 400)
            return

        # Merge patch into _availability
        _availability = {**_availability, **patch}
        log.info(f"📅 AgentCard availability updated via PATCH: {_availability}")

        # Return the updated live card
        skills = [s["id"] for s in (_status.get("agent_card") or {}).get("skills", [])]
        live_card = _make_agent_card(_status.get("agent_name", "ACP-Agent"), skills)
        self._json({"ok": True, "availability": live_card.get("availability", {})})


def run_http(port, host="127.0.0.1", http2=False):
    # BUG-001 root-cause fix (2026-03-23): use ThreadingHTTPServer so that
    # /stream (blocking SSE loop) does not prevent /message:send from being served.
    # The original HTTPServer was single-threaded; any open /stream connection
    # would block ALL subsequent HTTP requests, making SSE effectively useless.
    # host defaults to 127.0.0.1 (local-only); pass "0.0.0.0" for Docker/container use.

    # v1.6: Optional HTTP/2 transport binding via hypercorn (graceful fallback to HTTP/1.1)
    if http2:
        if not _HTTP2_AVAILABLE:
            log.warning("⚠️  --http2 requested but hypercorn/h2 not installed; "
                        "falling back to HTTP/1.1 (pip install hypercorn h2)")
        else:
            log.info(f"🚀 HTTP/2 transport enabled via hypercorn on {host}:{port}")
            _run_http2_hypercorn(host, port)
            return  # hypercorn blocks until shutdown

    # Default: HTTP/1.1 via stdlib ThreadingHTTPServer
    ThreadingHTTPServer((host, port), LocalHTTP).serve_forever()


def _run_http2_hypercorn(host: str, port: int):
    """Run the HTTP server with HTTP/2 (h2c cleartext) support.

    Uses the `h2` state machine directly over a raw TCP socket server.
    This avoids hypercorn's signal handler registration issue in non-main
    threads, while still providing true HTTP/2 multiplexing via the h2 library.

    Architecture:
        ThreadingTCPServer → _H2Handler per connection
        → h2.Connection state machine processes frames
        → LocalHTTP dispatch logic called for each complete request
        → Response serialised back as DATA frames
    """
    import io
    import h2.connection
    import h2.config
    import h2.events
    import socketserver

    class _H2Handler(socketserver.BaseRequestHandler):
        """Handle a single TCP connection using HTTP/2 h2c (cleartext)."""

        MAX_BODY = 4 * 1024 * 1024  # 4 MB request body limit

        def handle(self):
            conn = h2.connection.H2Connection(
                config=h2.config.H2Configuration(client_side=False,
                                                  header_encoding="utf-8")
            )
            conn.initiate_connection()
            self.request.sendall(conn.data_to_send(65535))

            # Per-stream state: {stream_id: {"headers": [...], "body": bytes}}
            streams: dict = {}

            try:
                while True:
                    try:
                        data = self.request.recv(65535)
                    except Exception:
                        break
                    if not data:
                        break

                    events = conn.receive_data(data)
                    for event in events:
                        if isinstance(event, h2.events.RequestReceived):
                            streams[event.stream_id] = {
                                "headers": event.headers,
                                "body": b"",
                            }
                        elif isinstance(event, h2.events.DataReceived):
                            sid = event.stream_id
                            if sid in streams:
                                streams[sid]["body"] += event.data
                                if len(streams[sid]["body"]) > self.MAX_BODY:
                                    conn.reset_stream(sid, error_code=3)
                            conn.acknowledge_received_data(event.flow_controlled_length, sid)
                        elif isinstance(event, h2.events.StreamEnded):
                            sid = event.stream_id
                            if sid in streams:
                                self._dispatch(conn, sid, streams.pop(sid))
                        elif isinstance(event, h2.events.WindowUpdated):
                            pass  # flow control — nothing to do
                        elif isinstance(event, h2.events.ConnectionTerminated):
                            return

                    out = conn.data_to_send(65535)
                    if out:
                        self.request.sendall(out)
            except Exception as exc:
                log.debug(f"H2 connection error: {exc}")

        def _dispatch(self, conn, stream_id, stream_data):
            """Dispatch one HTTP/2 request to LocalHTTP and send h2 response."""
            import io
            import email

            headers_dict = {k: v for k, v in stream_data["headers"]}
            method  = headers_dict.get(":method", "GET")
            path    = headers_dict.get(":path", "/")
            body    = stream_data["body"]

            # Build the fake HTTP/1.1 request lines (header section only, no body).
            # content-length is set authoritatively to the actual body byte length.
            # h2 pseudo-headers (:method, :path, etc.) are stripped; duplicate
            # content-length headers from the client are also stripped to avoid
            # BaseHTTPRequestHandler reading the wrong byte count.
            header_lines = []
            for k, v in stream_data["headers"]:
                if k.startswith(":"):
                    continue
                if k.lower() == "content-length":
                    continue
                header_lines.append(f"{k}: {v}")
            header_lines.append(f"content-length: {len(body)}")

            # Full HTTP/1.1 wire bytes: request line + headers + blank line + body
            req_line    = f"{method} {path} HTTP/1.1\r\n".encode()
            header_blob = ("\r\n".join(header_lines) + "\r\n\r\n").encode()
            raw_req     = req_line + header_blob + body

            resp_buf = io.BytesIO()

            class _FakeSock:
                def makefile(self, mode, **kw):
                    # rfile (read) must start right after the request line
                    # so that parse_headers() finds the header section.
                    if "r" in mode:
                        f = io.BytesIO(header_blob + body)
                        return io.BufferedReader(f)
                    return resp_buf
                def sendall(self, d): resp_buf.write(d)
                def send(self, d, flags=0): resp_buf.write(d); return len(d)
                def close(self): pass
                def getpeername(self):
                    try: return self.client_address
                    except Exception: return ("127.0.0.1", 0)

            fake_sock = _FakeSock()
            fake_sock.client_address = self.client_address

            try:
                handler = LocalHTTP.__new__(LocalHTTP)
                handler.server = type("_S", (), {"server_address": (host, port)})()
                handler.client_address = self.client_address
                handler.request    = fake_sock
                handler.connection = fake_sock
                # rfile: after request line, pointing at headers+body
                handler.rfile  = fake_sock.makefile("rb")
                handler.wfile  = resp_buf
                handler.raw_requestline = req_line
                # parse_request reads the request line, then parse_headers reads rfile
                handler.parse_request()
                meth_fn = getattr(handler, f"do_{method}", None)
                if meth_fn:
                    meth_fn()
                else:
                    handler.send_error(405, f"Method {method} not allowed")
            except Exception as exc:
                log.debug(f"H2 dispatch error: {exc}")
                conn.send_headers(stream_id, [
                    (":status", "500"),
                    ("content-type", "text/plain"),
                ])
                conn.send_data(stream_id, b"Internal Server Error", end_stream=True)
                return

            # Parse HTTP/1.1 response from buffer → h2 frames
            resp_buf.seek(0)
            raw_resp = resp_buf.read()
            try:
                sep = raw_resp.index(b"\r\n\r\n")
                header_bytes = raw_resp[:sep]
                resp_body    = raw_resp[sep + 4:]
                lines = header_bytes.decode(errors="replace").split("\r\n")
                status_code  = int(lines[0].split()[1]) if lines else 200
                resp_headers = [(":status", str(status_code))]
                for line in lines[1:]:
                    if ":" in line:
                        k, _, v = line.partition(":")
                        resp_headers.append((k.strip().lower(), v.strip()))
            except Exception:
                status_code = 200
                resp_headers = [(":status", "200"), ("content-type", "text/plain")]
                resp_body = raw_resp

            try:
                conn.send_headers(stream_id, resp_headers)
                if resp_body:
                    conn.send_data(stream_id, resp_body, end_stream=True)
                else:
                    conn.send_data(stream_id, b"", end_stream=True)
            except Exception as exc:
                log.debug(f"H2 send_headers/data error: {exc}")

    class _ThreadingH2Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    server = _ThreadingH2Server((host, port), _H2Handler)
    log.info(f"HTTP/2 h2c server listening on {host}:{port}")
    server.serve_forever()


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
    """
    Returns (host, port, token, scheme)

    应用层链接格式（传输层无关）：
      acp://IP:PORT/TOKEN       → 标准链接，底层自动选 P2P 或中继
      acp+wss://relay.host/acp/TOKEN  → 直接指定中继（向后兼容）

    Raises ValueError for malformed links (BUG-013 fix).
    """
    if not link or not isinstance(link, str):
        raise ValueError("link must be a non-empty string")

    if link.startswith("acp+wss://") or link.startswith("acp+ws://"):
        scheme = "http_relay"
        parsed = urlparse(link.replace("acp+wss://", "https://", 1).replace("acp+ws://", "http://", 1))
        base_url = f"{'https' if link.startswith('acp+wss://') else 'http'}://{parsed.netloc}"
        token = parsed.path.strip("/").split("/")[-1]
        if not token:
            raise ValueError(f"acp+wss:// link missing token: {link!r}")
        return base_url, 0, token, scheme

    # BUG-013 fix: reject non-acp:// schemes
    if not link.startswith("acp://"):
        raise ValueError(f"invalid link scheme (expected acp:// or acp+wss://): {link!r}")

    # 标准 acp:// 链接
    parsed = urlparse(link.replace("acp://", "http://", 1))
    host  = parsed.hostname
    port  = parsed.port
    token = parsed.path.strip("/")

    if not host:
        raise ValueError(f"link missing host: {link!r}")
    if port is None:
        port = 7801
    elif not (1 <= port <= 65535):
        raise ValueError(f"link port out of range ({port}): {link!r}")
    if not token:
        raise ValueError(f"link missing token: {link!r}")

    return host, port, token, "ws"


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

def _load_config_file(path: str) -> dict:
    """
    Load a YAML or JSON config file and return a dict of option overrides.

    Supported keys match CLI long-option names (hyphens, not underscores):
      name, port, join, relay, relay-url, skills, inbox, max-msg-size,
      secret, hmac-window, advertise-mdns, identity, verbose

    YAML support uses stdlib only (no PyYAML required) — only the subset of
    YAML that is valid JSON is accepted. For true YAML, install PyYAML.

    Example config.json:
        {
          "name": "MyAgent",
          "port": 8000,
          "skills": "summarize,translate",
          "verbose": true
        }

    Example config.yaml (JSON-compatible subset):
        name: MyAgent
        port: 8000
        skills: summarize,translate
        verbose: true
    """
    if not os.path.exists(path):
        print(f"[acp] Error: config file not found: {path}", file=sys.stderr)
        sys.exit(1)

    with open(path, "r") as f:
        text = f.read()

    # Try JSON first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Minimal YAML parser (key: value lines, bool/int coercion, no nesting)
    try:
        result = {}
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                continue
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            # bool coercion
            if val.lower() in ("true", "yes"):
                val = True
            elif val.lower() in ("false", "no"):
                val = False
            else:
                # int coercion
                try:
                    val = int(val)
                except ValueError:
                    pass
            result[key] = val
        return result
    except Exception as e:
        print(f"[acp] Error parsing config file {path}: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    global _loop, _status, _inbox_path, MAX_MSG_BYTES

    parser = argparse.ArgumentParser(
        description=f"ACP P2P v{VERSION} — zero-server Agent communication",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Minimal P2P host
  python3 acp_relay.py --name AgentA

  # Join an existing session
  python3 acp_relay.py --name AgentB --join acp://1.2.3.4:7801/tok_xxx

  # Use public relay (firewall-friendly)
  python3 acp_relay.py --name AgentA --relay

  # Load config from file (JSON or YAML)
  python3 acp_relay.py --config agent.json

  # Show version and exit
  python3 acp_relay.py --version

  # Verbose debug logging
  python3 acp_relay.py --name AgentA --verbose
""",
    )

    # ── Meta ──────────────────────────────────────────────────────────────────
    parser.add_argument(
        "--version", action="version",
        version=f"acp_relay.py {VERSION}",
        help="Show version string and exit",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable DEBUG-level logging (default: INFO)",
    )
    parser.add_argument(
        "--config", default=None, metavar="FILE",
        help="Path to a JSON or YAML config file. CLI flags override file values.",
    )

    # ── Core ──────────────────────────────────────────────────────────────────
    parser.add_argument("--name",         default=None,  help="Agent name (default: ACP-Agent)")
    parser.add_argument("--join",         default=None,  help="acp:// link to connect to")
    parser.add_argument("--relay",        action="store_true", help="Use public HTTP relay instead of P2P")
    parser.add_argument("--relay-url",    default=None,
                        help="Relay endpoint URL (default: public Cloudflare Worker)")
    parser.add_argument("--port",         type=int, default=None,
                        help="WebSocket listen port (default: 7801; HTTP API = port+100)")
    parser.add_argument("--skills",       default=None,
                        help="Comma-separated skill ids to advertise in AgentCard")
    parser.add_argument("--inbox",        default=None,
                        help="Path to JSONL message persistence file")
    parser.add_argument("--max-msg-size", type=int, default=None,
                        help=f"Max inbound message size in bytes (default: {MAX_MSG_BYTES})")

    # ── Security (v0.7+) ──────────────────────────────────────────────────────
    parser.add_argument("--secret",       default=None,
                        help="(v0.7) HMAC-SHA256 shared secret for message signing. "
                             "Both peers must use the same value.")
    parser.add_argument("--hmac-window",  type=int, default=None, metavar="SECONDS",
                        help="(v1.1) Replay-window in seconds for HMAC-signed messages. "
                             "Inbound messages with ts outside ±WINDOW are dropped. "
                             "Default: 300 (5 minutes). Only active when --secret is set.")
    parser.add_argument("--advertise-mdns", action="store_true",
                        help="(v0.7) Advertise on LAN via UDP multicast. "
                             "Enables GET /discover. No extra packages required.")
    parser.add_argument("--ca-cert",      default=None, metavar="PATH_OR_PEM",
                        help="(v1.5) Path to a PEM-encoded CA-signed certificate file, or a raw PEM string. "
                             "When provided alongside --identity, adds a 'ca_cert' field to AgentCard "
                             "and sets identity.scheme='ed25519+ca' (hybrid self-sovereign + CA model). "
                             "Without --identity this flag is ignored.")
    parser.add_argument("--identity",     default=None,
                        help="(v0.8) Path to Ed25519 keypair JSON (auto-generated if absent). "
                             "Omit path to use ~/.acp/identity.json. "
                             "Requires: pip install cryptography.")
    parser.add_argument("--availability-mode", default=None,
                        choices=["persistent", "heartbeat", "cron", "manual"],
                        help="(v1.2) Agent availability mode. 'persistent' = always-on (default). "
                             "'heartbeat'/'cron' = wakes periodically; set --heartbeat-interval. "
                             "Populates the AgentCard 'availability' block.")
    parser.add_argument("--heartbeat-interval", type=int, default=None, metavar="SECONDS",
                        help="(v1.2) Heartbeat/cron wake interval in seconds. "
                             "Used with --availability-mode heartbeat|cron. "
                             "Sets availability.interval_seconds and task_latency_max_seconds.")
    parser.add_argument("--next-active-at", default=None, metavar="ISO8601",
                        help="(v1.2) ISO-8601 UTC timestamp of next scheduled wake "
                             "(e.g. 2026-03-22T07:00:00Z). Written into AgentCard availability block.")
    parser.add_argument("--extension", action="append", default=[], metavar="URI[,required=true][,key=val...]",
                        help="(v1.3) Declare an AgentCard extension. May be repeated. "
                             "Format: URI  or  URI,required=true,param_key=param_val. "
                             "Example: --extension https://acp.dev/ext/availability/v1,required=false "
                             "         --extension https://corp.example.com/ext/billing,tier=pro")
    parser.add_argument("--http-host", default="127.0.0.1", metavar="HOST",
                        help="Host/IP the HTTP interface binds to (default: 127.0.0.1). "
                             "Use 0.0.0.0 for Docker/container deployments so port mapping works.")
    parser.add_argument("--http2", action="store_true",
                        help="Enable HTTP/2 transport (h2c cleartext) via hypercorn. "
                             "Requires: pip install hypercorn h2. "
                             "Falls back to HTTP/1.1 if dependencies are missing. "
                             "Enables multiplexed streams and reduced head-of-line blocking.")

    args = parser.parse_args()

    # ── Apply config file (lowest precedence) ─────────────────────────────────
    cfg: dict = {}
    if args.config:
        cfg = _load_config_file(args.config)

    # Helpers: resolve with CLI > config > hardcoded default
    def _get(cli_val, cfg_key: str, default):
        if cli_val is not None:
            return cli_val
        if cfg_key in cfg:
            return cfg[cfg_key]
        return default

    def _get_bool(cli_flag: bool, cfg_key: str) -> bool:
        if cli_flag:
            return True
        return bool(cfg.get(cfg_key, False))

    # ── Resolve all values ────────────────────────────────────────────────────
    _DEFAULT_RELAY = "https://black-silence-11c4.yuranliu888.workers.dev"

    verbose        = _get_bool(args.verbose,        "verbose")
    agent_name     = _get(args.name,         "name",           "ACP-Agent")
    join_link      = _get(args.join,         "join",           None)
    use_relay      = _get_bool(args.relay,          "relay")
    relay_url      = _get(args.relay_url,    "relay-url",      _DEFAULT_RELAY)
    port           = _get(args.port,         "port",           7801)
    skills_str     = _get(args.skills,       "skills",         "")
    inbox_path     = _get(args.inbox,        "inbox",          None)
    max_msg_size   = _get(args.max_msg_size, "max-msg-size",   MAX_MSG_BYTES)
    secret_str     = _get(args.secret,       "secret",         None)
    advertise_mdns = _get_bool(args.advertise_mdns, "advertise-mdns")
    identity_path  = _get(args.identity,     "identity",       None)

    # ── Configure logging ─────────────────────────────────────────────────────
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        log.debug("Verbose/DEBUG logging enabled")
    else:
        logging.getLogger().setLevel(logging.INFO)

    # ── Apply resolved values ─────────────────────────────────────────────────
    MAX_MSG_BYTES = max_msg_size
    _status["max_msg_bytes"] = MAX_MSG_BYTES

    # HMAC optional signing (v0.7) + replay-window (v1.1)
    global _hmac_secret, _HMAC_REPLAY_WINDOW
    if secret_str:
        _hmac_secret = secret_str.encode()
        log.info("🔐 HMAC signing enabled (--secret configured)")
        if hasattr(args, "hmac_window") and args.hmac_window is not None:
            _HMAC_REPLAY_WINDOW = args.hmac_window
        log.info(f"🕐 HMAC replay-window: ±{_HMAC_REPLAY_WINDOW}s")
    else:
        _hmac_secret = None

    # Ed25519 optional identity (v0.8)
    if identity_path is not None:
        _ed25519_load_or_create(identity_path if identity_path else None)

    # v1.5: CA-signed certificate — hybrid identity model (self-sovereign + CA)
    global _ca_cert_pem
    ca_cert_arg = _get(getattr(args, "ca_cert", None), "ca-cert", None)
    if ca_cert_arg and _ed25519_private:
        import pathlib as _pl
        p = _pl.Path(ca_cert_arg)
        if p.exists():
            _ca_cert_pem = p.read_text().strip()
            log.info(f"📜 CA certificate loaded from {p} (hybrid identity: ed25519+ca)")
        elif ca_cert_arg.strip().startswith("-----BEGIN"):
            _ca_cert_pem = ca_cert_arg.strip()
            log.info("📜 CA certificate loaded from inline PEM (hybrid identity: ed25519+ca)")
        else:
            log.warning(f"--ca-cert: path '{ca_cert_arg}' not found and doesn't look like PEM; ignoring")
    elif ca_cert_arg and not _ed25519_private:
        log.warning("--ca-cert ignored: requires --identity to be set first")

    # Availability metadata (v1.2) — opt-in AgentCard block for heartbeat/cron agents
    global _availability
    avail_mode     = _get(getattr(args, "availability_mode",    None), "availability-mode",    None)
    hb_interval    = _get(getattr(args, "heartbeat_interval",   None), "heartbeat-interval",   None)
    next_active_at = _get(getattr(args, "next_active_at",       None), "next-active-at",       None)
    if avail_mode and avail_mode != "persistent":
        _availability = {"mode": avail_mode}
        if hb_interval is not None:
            _availability["interval_seconds"]        = int(hb_interval)
            _availability["task_latency_max_seconds"] = int(hb_interval)
        if next_active_at:
            _availability["next_active_at"] = next_active_at
        log.info(f"📅 Availability mode: {avail_mode}" +
                 (f" (interval={hb_interval}s)" if hb_interval else ""))
    elif avail_mode == "persistent":
        _availability = {"mode": "persistent"}

    # v1.3: parse --extension flags into _extensions list
    raw_extensions = _get(getattr(args, "extension", []) or [], "extensions", [])
    if isinstance(raw_extensions, str):
        raw_extensions = [raw_extensions]
    for raw_ext in raw_extensions:
        parts = [p.strip() for p in raw_ext.split(",")]
        if not parts:
            continue
        ext_uri = parts[0]
        if not ext_uri:
            continue
        ext_entry = {"uri": ext_uri, "required": False, "params": {}}
        for kv in parts[1:]:
            if "=" in kv:
                k, v = kv.split("=", 1)
                k = k.strip()
                v = v.strip()
                if k == "required":
                    ext_entry["required"] = v.lower() in ("true", "1", "yes")
                else:
                    ext_entry["params"][k] = v
        if ext_entry["params"] == {}:
            del ext_entry["params"]
        _extensions.append(ext_entry)
    if _extensions:
        log.info(f"🔌 Extensions declared: {[e['uri'] for e in _extensions]}")

    # Rebuild args-like namespace for the rest of main() to consume
    # (avoids rewriting all downstream args.xxx references)
    args.name          = agent_name
    args.join          = join_link
    args.relay         = use_relay
    args.relay_url     = relay_url
    args.port          = port
    args.skills        = skills_str
    args.inbox         = inbox_path
    args.advertise_mdns = advertise_mdns

    ws_port   = args.port
    http_port = args.port + 100
    skills    = [s.strip() for s in args.skills.split(",") if s.strip()] if args.skills else []

    _status["agent_name"] = args.name
    _status["ws_port"]    = ws_port
    _status["http_port"]  = http_port
    _status["agent_card"] = _make_agent_card(args.name, skills)

    _inbox_path = args.inbox or f"/tmp/acp_inbox_{args.name.replace(' ', '_')}.jsonl"
    log.info(f"Message persistence: {_inbox_path}")

    http_host = getattr(args, "http_host", "127.0.0.1")

    # v1.6: HTTP/2 transport binding
    global _http2_enabled
    _use_http2 = getattr(args, "http2", False)
    if _use_http2 and not _HTTP2_AVAILABLE:
        log.warning("⚠️  --http2 requested but hypercorn/h2 not installed — "
                    "falling back to HTTP/1.1 (pip install hypercorn h2)")
        _use_http2 = False
    _http2_enabled = _use_http2
    if _http2_enabled:
        # Rebuild agent card to reflect http2=True capability
        _status["agent_card"] = _make_agent_card(args.name, skills)
        log.info(f"🚀 HTTP/2 (h2c) transport enabled via hypercorn on {http_host}:{http_port}")

    threading.Thread(target=run_http, args=(http_port, http_host), kwargs={"http2": _http2_enabled}, daemon=True).start()
    log.info(f"HTTP interface: {'h2c' if _http2_enabled else 'http'}//{http_host}:{http_port}")

    # ── mDNS LAN discovery (v0.7) ─────────────────────────────────────────────
    if args.advertise_mdns:
        token_placeholder = _make_token()  # will be replaced after host_mode assigns real token
        _mdns_start(args.name, token_placeholder, ws_port, http_port)
        log.info(f"mDNS: advertising on LAN ({_MDNS_GROUP}:{_MDNS_PORT})")

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
            # ── 加入已有会话 ─────────────────────────────────────────────
            # 解析链接，自动选择传输方式，Agent 无需关心
            result = parse_link(args.join)
            host, port, token, scheme = result
            if scheme == "http_relay":
                log.info(f"Transport: HTTP relay -> {host}")
                _loop.run_until_complete(_http_relay_guest(host, token, http_port))
            else:
                _loop.run_until_complete(guest_mode(host, port, token, http_port))
        elif args.relay:
            # ── 通过公共中继创建新会话 ────────────────────────────────────
            import subprocess as _sp2
            relay_base = args.relay_url.rstrip("/")
            _status["relay_base_url"] = relay_base  # expose for DCUtR HTTP reflection (v1.4)
            r2 = _sp2.run(
                ["curl", "-s", "--max-time", "10", "-X", "POST", f"{relay_base}/acp/new",
                 "-H", "Content-Type: application/json", "-d", "{}"],
                capture_output=True, text=True
            )
            resp = json.loads(r2.stdout)
            token = resp["token"]
            link  = resp["link"]
            _status["link"] = link
            _status["session_id"] = token
            print(f"\n{'='*55}")
            print(f"ACP v{VERSION} — relay session ready")
            print(f"  Your link: {link}")
            print(f"  Share this with the other Agent to connect")
            print(f"{'='*55}\n")
            _loop.run_until_complete(_http_relay_guest(relay_base, token, http_port))
        else:
            # ── 默认：P2P 模式，监听并等待对方连接 ────────────────────────
            token = _make_token()
            # Update mDNS with real token now that we have it
            if args.advertise_mdns and _mdns_running:
                _mdns_send_announce(args.name, token, ws_port, http_port)
                log.info(f"mDNS: updated announce with real token {token[:12]}...")
            _loop.run_until_complete(host_mode(token, ws_port, http_port))
    except KeyboardInterrupt:
        pass

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

    # 注册到会话（用 curl 确保走代理）
    import subprocess as _subp
    def _curl_relay(url, data_str):
        r = _subp.run(
            ["curl", "-s", "--max-time", "10", "-X", "POST", url,
             "-H", "Content-Type: application/json", "-d", data_str],
            capture_output=True, text=True
        )
        if r.returncode != 0 or not r.stdout.strip():
            raise RuntimeError(f"curl failed: {r.stderr}")
        return json.loads(r.stdout)

    try:
        resp = _curl_relay(join_url, json.dumps(agent_card))
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


    # _http_send 用 asyncio curl
    async def _http_send(msg: dict):
        try:
            proc = await asyncio.create_subprocess_exec(
                "curl", "-s", "--max-time", "10", "-X", "POST", send_url,
                "-H", "Content-Type: application/json",
                "-d", json.dumps(msg),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await proc.communicate()
        except Exception as e:
            log.warning(f"HTTP send failed: {e}")

    global _http_relay_send
    _http_relay_send = _http_send

    # 轮询消息循环（用 asyncio subprocess 避免阻塞 event loop）
    since = 0.0
    POLL_INTERVAL = 1.5  # 秒

    while True:
        try:
            proc = await asyncio.create_subprocess_exec(
                "curl", "-s", "--max-time", "10",
                f"{poll_url}?since={since}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL
            )
            stdout, _ = await proc.communicate()
            if stdout.strip():
                data = json.loads(stdout)
                msgs = data.get("messages", [])
                for msg in msgs:
                    if msg.get("from") != _status["agent_name"]:
                        _on_message(json.dumps(msg))
                    if msg.get("ts", 0) > since:
                        since = float(msg["ts"])
        except Exception as e:
            log.warning(f"Poll exception: {e}")

        await asyncio.sleep(POLL_INTERVAL)

_http_relay_send = None  # 由 _http_relay_guest 设置


# ══════════════════════════════════════════════════════════════════════════════
# NAT Traversal — DCUtR-style UDP Hole Punching (v1.4 initial impl)
#
# Design: Three-level connection strategy, fully automatic, zero user config:
#   Level 1: Direct connect (existing, 3s timeout)
#   Level 2: UDP hole punching via Relay signaling (new, 5s timeout)
#   Level 3: Relay permanent relay (existing fallback)
#
# All code here is stdlib-only: asyncio, socket, struct, os, time, uuid
# No third-party deps. Any failure silently degrades to the next level.
#
# New ACP message types (transported over Relay WebSocket):
#   dcutr_connect  — initiator sends its addresses, requests hole punch
#   dcutr_sync     — responder sends its addresses + synchronized punch time
#   dcutr_result   — notify relay of outcome (informational)
# ══════════════════════════════════════════════════════════════════════════════

import struct as _struct


# ─────────────────────────────────────────────────────────────────────────────
# STUNClient — discover public UDP address via STUN Binding Request (stdlib)
# ─────────────────────────────────────────────────────────────────────────────

class STUNClient:
    """
    Minimal STUN Binding Request client (RFC 5389 / RFC 8489).
    Uses only stdlib: asyncio, socket, struct.
    Returns the public (NAT-mapped) UDP address observed by the STUN server.
    """

    MAGIC_COOKIE = 0x2112A442
    BINDING_REQUEST  = 0x0001
    BINDING_RESPONSE = 0x0101
    ATTR_MAPPED_ADDRESS     = 0x0001
    ATTR_XOR_MAPPED_ADDRESS = 0x0020

    @staticmethod
    async def get_public_address(
        stun_host: str = "stun.l.google.com",
        stun_port: int = 19302,
        timeout: float = 3.0,
    ):
        """
        Send a STUN Binding Request and parse the XOR-MAPPED-ADDRESS response.

        Returns:
            (ip: str, port: int) — the public UDP address as seen by STUN server
            None                 — on any failure / timeout
        """
        try:
            # Build 20-byte STUN Binding Request
            transaction_id = os.urandom(12)
            header = _struct.pack(
                "!HHI12s",
                STUNClient.BINDING_REQUEST,  # Message Type
                0,                           # Message Length (no attributes)
                STUNClient.MAGIC_COOKIE,     # Magic Cookie
                transaction_id,
            )

            loop = asyncio.get_event_loop()

            def _send_recv():
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.settimeout(timeout)
                try:
                    server_ip = socket.gethostbyname(stun_host)
                    sock.sendto(header, (server_ip, stun_port))
                    data, _ = sock.recvfrom(512)
                    return data
                finally:
                    sock.close()

            data = await asyncio.wait_for(
                loop.run_in_executor(None, _send_recv),
                timeout=timeout + 0.5,
            )

            return STUNClient._parse_response(data)

        except Exception as e:
            log.debug(f"[STUN] address discovery failed: {e}")
            return None

    @staticmethod
    def _parse_response(data: bytes):
        """
        Parse STUN Binding Response.
        Prefers XOR-MAPPED-ADDRESS (0x0020) over MAPPED-ADDRESS (0x0001).
        Returns (ip, port) or None.
        """
        if len(data) < 20:
            return None

        msg_type, msg_len, magic, txn_id = _struct.unpack_from("!HHI12s", data, 0)
        if msg_type != STUNClient.BINDING_RESPONSE:
            return None

        # Walk attributes
        offset = 20
        result_mapped = None
        result_xor    = None

        while offset + 4 <= len(data):
            attr_type, attr_len = _struct.unpack_from("!HH", data, offset)
            offset += 4
            attr_val = data[offset: offset + attr_len]
            # Pad to 4-byte boundary
            offset += (attr_len + 3) & ~3

            if attr_type == STUNClient.ATTR_MAPPED_ADDRESS and attr_len >= 8:
                # Format: 1-byte reserved, 1-byte family(0x01=IPv4), 2-byte port, 4-byte ip
                family = attr_val[1]
                if family == 0x01:  # IPv4
                    port = _struct.unpack_from("!H", attr_val, 2)[0]
                    ip   = socket.inet_ntoa(attr_val[4:8])
                    result_mapped = (ip, port)

            elif attr_type == STUNClient.ATTR_XOR_MAPPED_ADDRESS and attr_len >= 8:
                family = attr_val[1]
                if family == 0x01:  # IPv4
                    xport = _struct.unpack_from("!H", attr_val, 2)[0] ^ (STUNClient.MAGIC_COOKIE >> 16)
                    xip_raw = _struct.unpack_from("!I", attr_val, 4)[0] ^ STUNClient.MAGIC_COOKIE
                    xip = socket.inet_ntoa(_struct.pack("!I", xip_raw))
                    result_xor = (xip, xport)

        return result_xor or result_mapped


# ─────────────────────────────────────────────────────────────────────────────
# DCUtRPuncher — UDP hole punching state machine
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# Signaling helpers — HTTP Reflection via Cloudflare Worker (v2.1 / ACP v1.4)
#
# These complement STUNClient: when STUN fails (corporate firewall blocks UDP
# to external STUN servers), we fall back to HTTP reflection via the Worker.
#
# Endpoints (added in Worker v2.1):
#   GET  /acp/myip           → reflect public IP
#   POST /acp/announce       → register {token, ip, port} with 30s TTL
#   GET  /acp/peer?token=<t> → fetch + delete peer announce record (one-time)
# ─────────────────────────────────────────────────────────────────────────────

def _relay_get_public_ip(relay_base_url: str, timeout: float = 3.0) -> str | None:
    """
    Reflect public IP via Worker /acp/myip endpoint.
    Returns IP string or None on failure.
    stdlib-only: urllib.
    """
    import urllib.request
    try:
        url = relay_base_url.rstrip("/") + "/acp/myip"
        # Use no-proxy opener so localhost mock servers work in sandboxed envs.
        _opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with _opener.open(url, timeout=timeout) as r:
            data = json.loads(r.read())
            return data.get("ip")
    except Exception as e:
        log.debug(f"[NAT/HTTP] /acp/myip failed: {e}")
        return None


def _relay_announce(relay_base_url: str, token: str, ip: str, port: int,
                    nat_type: str = "unknown", timeout: float = 3.0) -> bool:
    """
    Register public address for a token via Worker /acp/announce.
    Record expires in 30s automatically.
    Returns True on success.
    """
    import urllib.request
    try:
        if not token:
            return False
        url = relay_base_url.rstrip("/") + "/acp/announce"
        body = json.dumps({"token": token, "ip": ip, "port": port,
                           "nat_type": nat_type}).encode()
        req = urllib.request.Request(url, body, {"Content-Type": "application/json"})
        # Use a no-proxy opener so localhost mock servers work in sandboxed envs.
        _opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with _opener.open(req, timeout=timeout) as r:
            data = json.loads(r.read())
            return bool(data.get("ok"))
    except Exception as e:
        log.debug(f"[NAT/HTTP] /acp/announce failed: {e}")
        return False


def _relay_get_peer_addr(relay_base_url: str, token: str,
                         timeout: float = 3.0) -> dict | None:
    """
    Fetch peer's announced address via Worker /acp/peer?token=<t>.
    One-time fetch: Worker deletes record after first read.
    Returns dict {ip, port, nat_type, ts} or None on failure/not-found.
    """
    import urllib.request
    import urllib.parse
    try:
        params = urllib.parse.urlencode({"token": token})
        url = relay_base_url.rstrip("/") + "/acp/peer?" + params
        # Use no-proxy opener so localhost mock servers work in sandboxed envs.
        _opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with _opener.open(url, timeout=timeout) as r:
            data = json.loads(r.read())
            if data.get("ok"):
                return {"ip": data["ip"], "port": data["port"],
                        "nat_type": data.get("nat_type", "unknown")}
            return None
    except Exception as e:
        log.debug(f"[NAT/HTTP] /acp/peer failed: {e}")
        return None


class DCUtRPuncher:
    """
    DCUtR-style UDP hole punching.

    State machine:
        IDLE → DISCOVERING → SIGNALING → PUNCHING → CONNECTED / FAILED

    The puncher requires an existing Relay WebSocket connection (relay_ws)
    which acts as the signaling channel for address exchange.
    Both sides must coordinate: one calls attempt(), the other calls listen_for_dcutr().
    """

    # Timing constants
    STUN_TIMEOUT      = 3.0   # seconds to wait for STUN response
    SIGNAL_TIMEOUT    = 5.0   # seconds to wait for dcutr_sync from peer
    PUNCH_AHEAD_MS    = 500   # ms ahead of t_punch to start listening
    PUNCH_PROBES      = 3     # number of UDP probe packets per target
    PUNCH_INTERVAL    = 0.10  # seconds between probe packets
    PUNCH_WAIT        = 3.0   # seconds to wait for incoming UDP reply
    UDP_PROBE_PAYLOAD = b"ACP-DCUtR-PROBE"

    # ── Initiator side ────────────────────────────────────────────────────────

    async def attempt(self, relay_ws, local_port: int):
        """
        Initiator: discover addresses → signal → punch → return direct addr or None.

        Args:
            relay_ws:   An active websockets connection to the Relay/peer.
                        Must support send(str) and recv().
            local_port: Local UDP port to use for hole punching.

        Returns:
            (ip: str, port: int) — direct peer address on success
            None                 — on any failure (caller falls back to relay)
        """
        session_id = str(uuid.uuid4())
        log.info(f"[DCUtR] initiating hole punch (session={session_id[:8]})")

        # ── Phase 1: STUN — discover public UDP address ───────────────────────
        stun_addr = await STUNClient.get_public_address(timeout=self.STUN_TIMEOUT)
        addresses = []
        if stun_addr:
            addresses.append(f"{stun_addr[0]}:{stun_addr[1]}")
            log.info(f"[DCUtR] public address via STUN: {stun_addr[0]}:{stun_addr[1]}")
        else:
            log.debug("[DCUtR] STUN failed; trying HTTP reflection fallback (v1.4)")
            # ── HTTP reflection fallback (v1.4) ─────────────────────────────
            # When STUN is blocked (corporate firewall / UDP filtered), fall back
            # to Cloudflare Worker GET /acp/myip which returns the public IP via
            # CF-Connecting-IP header.  Port is unknown from HTTP reflection
            # (TCP source port ≠ UDP hole-punch port), so we use local_port as
            # the candidate — good enough for Full Cone / Restricted Cone NAT.
            relay_base = _status.get("relay_base_url") or ""
            if relay_base:
                http_ip = _relay_get_public_ip(relay_base, timeout=3.0)
                if http_ip:
                    addresses.append(f"{http_ip}:{local_port}")
                    log.info(
                        f"[DCUtR] public address via HTTP reflection: "
                        f"{http_ip}:{local_port} (port is local estimate)"
                    )
                    _broadcast_sse_event("peer", {
                        "event": "dcutr_http_reflect",
                        "public_ip": http_ip,
                        "local_port": local_port,
                    })
                else:
                    log.debug("[DCUtR] HTTP reflection also failed; continuing with local only")
            else:
                log.debug("[DCUtR] no relay_base_url configured; skipping HTTP reflection")

        # Always include local address as fallback (same-LAN case)
        try:
            local_ip = socket.gethostbyname(socket.gethostname())
            addresses.append(f"{local_ip}:{local_port}")
        except Exception:
            pass

        if not addresses:
            log.debug("[DCUtR] no addresses discovered, aborting")
            return None

        # ── Phase 2: Signal — send dcutr_connect, wait for dcutr_sync ─────────
        connect_msg = json.dumps({
            "type":       "dcutr_connect",
            "addresses":  addresses,
            "session_id": session_id,
        })
        try:
            await relay_ws.send(connect_msg)
            log.debug(f"[DCUtR] sent dcutr_connect with {len(addresses)} address(es)")
        except Exception as e:
            log.debug(f"[DCUtR] failed to send dcutr_connect: {e}")
            return None

        # Wait for dcutr_sync from peer
        try:
            sync_data = await asyncio.wait_for(
                self._recv_dcutr_sync(relay_ws, session_id),
                timeout=self.SIGNAL_TIMEOUT,
            )
        except asyncio.TimeoutError:
            log.debug("[DCUtR] timeout waiting for dcutr_sync")
            return None
        except Exception as e:
            log.debug(f"[DCUtR] error receiving dcutr_sync: {e}")
            return None

        if sync_data is None:
            log.debug("[DCUtR] no dcutr_sync received")
            return None

        peer_addrs = sync_data.get("addresses", [])
        t_punch    = sync_data.get("t_punch", time.time())
        log.info(f"[DCUtR] peer addresses: {peer_addrs}, t_punch={t_punch}")

        # ── Phase 3: Punch — simultaneous UDP probes ───────────────────────────
        result = await self._do_punch(local_port, peer_addrs, t_punch)

        # Notify peer of result (best-effort, non-blocking)
        try:
            result_msg = json.dumps({
                "type":        "dcutr_result",
                "session_id":  session_id,
                "success":     result is not None,
                "direct_addr": f"{result[0]}:{result[1]}" if result else None,
            })
            await relay_ws.send(result_msg)
        except Exception:
            pass  # non-critical

        return result

    # ── Responder side ────────────────────────────────────────────────────────

    async def listen_for_dcutr(self, relay_ws, local_port: int):
        """
        Responder: wait for dcutr_connect, reply with dcutr_sync, punch.

        Args:
            relay_ws:   Active Relay WebSocket connection.
            local_port: Local UDP port for punching.

        Returns:
            (ip: str, port: int) — direct peer address on success
            None                 — on any failure
        """
        log.info("[DCUtR] listening for hole punch request")

        # Wait for dcutr_connect
        try:
            connect_data = await asyncio.wait_for(
                self._recv_dcutr_connect(relay_ws),
                timeout=self.SIGNAL_TIMEOUT,
            )
        except asyncio.TimeoutError:
            log.debug("[DCUtR] timeout waiting for dcutr_connect")
            return None
        except Exception as e:
            log.debug(f"[DCUtR] error receiving dcutr_connect: {e}")
            return None

        if connect_data is None:
            return None

        peer_addrs = connect_data.get("addresses", [])
        session_id = connect_data.get("session_id", str(uuid.uuid4()))
        log.info(f"[DCUtR] received dcutr_connect, peer addrs: {peer_addrs}")

        # Discover our own addresses
        stun_addr = await STUNClient.get_public_address(timeout=self.STUN_TIMEOUT)
        my_addrs = []
        if stun_addr:
            my_addrs.append(f"{stun_addr[0]}:{stun_addr[1]}")
        try:
            local_ip = socket.gethostbyname(socket.gethostname())
            my_addrs.append(f"{local_ip}:{local_port}")
        except Exception:
            pass

        # Schedule punch time: now + PUNCH_AHEAD_MS + signaling buffer
        t_punch = time.time() + (self.PUNCH_AHEAD_MS / 1000.0) + 0.2

        # Reply with dcutr_sync
        sync_msg = json.dumps({
            "type":       "dcutr_sync",
            "addresses":  my_addrs,
            "session_id": session_id,
            "t_punch":    t_punch,
        })
        try:
            await relay_ws.send(sync_msg)
            log.debug(f"[DCUtR] sent dcutr_sync, t_punch={t_punch:.3f}")
        except Exception as e:
            log.debug(f"[DCUtR] failed to send dcutr_sync: {e}")
            return None

        # Execute punch
        return await self._do_punch(local_port, peer_addrs, t_punch)

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _recv_dcutr_sync(self, relay_ws, session_id: str):
        """Receive messages from relay_ws until dcutr_sync for our session_id."""
        while True:
            try:
                raw = await relay_ws.recv()
                msg = json.loads(raw)
                if msg.get("type") == "dcutr_sync" and msg.get("session_id") == session_id:
                    return msg
                # Other messages are silently dropped in this phase
            except Exception:
                return None

    async def _recv_dcutr_connect(self, relay_ws):
        """Receive messages from relay_ws until dcutr_connect arrives."""
        while True:
            try:
                raw = await relay_ws.recv()
                msg = json.loads(raw)
                if msg.get("type") == "dcutr_connect":
                    return msg
                # Other messages dropped silently
            except Exception:
                return None

    async def _do_punch(self, local_port: int, peer_addrs: list, t_punch: float):
        """
        Core UDP hole punch: bind local socket, wait until t_punch,
        send probes to all peer addresses, wait for reply.

        Returns (ip, port) on success, None on failure.
        """
        if not peer_addrs:
            return None

        # Parse peer addresses
        targets = []
        for addr_str in peer_addrs:
            try:
                host, port_str = addr_str.rsplit(":", 1)
                targets.append((host, int(port_str)))
            except Exception:
                continue

        if not targets:
            return None

        loop = asyncio.get_event_loop()

        def _punch_sync():
            """Blocking punch (run in executor to not block event loop)."""
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.bind(("0.0.0.0", local_port))
                sock.settimeout(0.1)
            except Exception as e:
                log.debug(f"[DCUtR] socket bind failed (port={local_port}): {e}")
                # Try with a random port
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    sock.bind(("0.0.0.0", 0))
                    sock.settimeout(0.1)
                except Exception as e2:
                    log.debug(f"[DCUtR] fallback socket also failed: {e2}")
                    return None

            try:
                # Wait until t_punch (clock sync)
                delay = t_punch - time.time()
                if delay > 0:
                    time.sleep(delay)

                # Send probe packets to all targets
                deadline = time.time() + self.PUNCH_WAIT
                for _ in range(self.PUNCH_PROBES):
                    for target in targets:
                        try:
                            sock.sendto(self.UDP_PROBE_PAYLOAD, target)
                            log.debug(f"[DCUtR] probe → {target[0]}:{target[1]}")
                        except Exception:
                            pass
                    time.sleep(self.PUNCH_INTERVAL)

                # Listen for incoming probes
                while time.time() < deadline:
                    try:
                        data, addr = sock.recvfrom(256)
                        if data.startswith(b"ACP-DCUtR"):
                            log.info(f"[DCUtR] ✅ punch success! peer={addr[0]}:{addr[1]}")
                            # Send ack
                            try:
                                sock.sendto(b"ACP-DCUtR-ACK", addr)
                            except Exception:
                                pass
                            return addr  # (ip, port)
                    except socket.timeout:
                        pass
                    except Exception:
                        pass

                log.debug("[DCUtR] punch timeout — no reply received")
                return None
            finally:
                sock.close()

        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, _punch_sync),
                timeout=self.PUNCH_WAIT + self.PUNCH_PROBES * self.PUNCH_INTERVAL + 1.0,
            )
            return result
        except asyncio.TimeoutError:
            log.debug("[DCUtR] _do_punch executor timed out")
            return None
        except Exception as e:
            log.debug(f"[DCUtR] _do_punch error: {e}")
            return None


# ─────────────────────────────────────────────────────────────────────────────
# connect_with_holepunch — public three-level connection API
# ─────────────────────────────────────────────────────────────────────────────

async def connect_with_holepunch(ws_uri: str, relay_ws=None, local_udp_port: int = 0):
    """
    Three-level connection strategy for ACP (DCUtR-style NAT traversal).

    Levels:
        1. Direct WebSocket connect (3s timeout) — existing behavior
        2. UDP hole punch via relay signaling    — new in v1.4
        3. Relay permanent relay (ws_uri must be relay URI) — existing fallback

    Args:
        ws_uri:         The WebSocket URI to connect to (direct or relay).
        relay_ws:       An existing Relay WebSocket (for signaling in Level 2).
                        If None, Level 2 is skipped.
        local_udp_port: Local UDP port for hole punching.
                        0 = OS-assigned (may limit port-restricted NAT success).

    Returns:
        (websocket, is_direct: bool)
            websocket  — connected websockets.WebSocketClientProtocol
            is_direct  — True if direct/hole-punched, False if relay
        Raises ConnectionError if all three levels fail.

    Usage:
        ws, direct = await connect_with_holepunch("ws://1.2.3.4:7801/tok_xxx")
        ws, direct = await connect_with_holepunch(
            relay_uri, relay_ws=existing_relay_ws, local_udp_port=9001
        )
    """
    # ── Level 1: Direct connect ───────────────────────────────────────────────
    try:
        ws = await asyncio.wait_for(
            _proxy_ws_connect(ws_uri),
            timeout=3.0,
        )
        log.info(f"[connect] Level 1 direct connect succeeded: {ws_uri}")
        return (ws, True)
    except Exception as e:
        log.debug(f"[connect] Level 1 direct failed ({type(e).__name__}): {e}")

    # ── Level 2: UDP hole punch ───────────────────────────────────────────────
    if relay_ws is not None:
        try:
            puncher = DCUtRPuncher()
            direct_addr = await puncher.attempt(relay_ws, local_udp_port)

            if direct_addr is not None:
                # Build a direct WebSocket URI from the punched address
                # (reuse scheme/path from ws_uri, replace host:port)
                from urllib.parse import urlparse as _up2, urlunparse as _uu2
                parsed = _up2(ws_uri)
                direct_uri = _uu2((
                    parsed.scheme,
                    f"{direct_addr[0]}:{direct_addr[1]}",
                    parsed.path,
                    parsed.params,
                    parsed.query,
                    parsed.fragment,
                ))
                try:
                    ws = await asyncio.wait_for(
                        _proxy_ws_connect(direct_uri),
                        timeout=3.0,
                    )
                    log.info(
                        f"[connect] Level 2 hole punch succeeded: "
                        f"{direct_addr[0]}:{direct_addr[1]}"
                    )
                    # Close relay connection now that we have a direct path
                    try:
                        await relay_ws.close()
                    except Exception:
                        pass
                    return (ws, True)
                except Exception as e2:
                    log.debug(f"[connect] Level 2 WS upgrade failed after punch: {e2}")
        except Exception as e:
            log.debug(f"[connect] Level 2 hole punch error: {e}")

    # ── Level 3: Relay permanent relay ───────────────────────────────────────
    if relay_ws is not None:
        log.info("[connect] Level 3 relay fallback (permanent)")
        # relay_ws is already connected; return it as the communication channel
        return (relay_ws, False)

    # Last resort: try direct connect one more time (in case of transient failure)
    try:
        ws = await asyncio.wait_for(
            _proxy_ws_connect(ws_uri),
            timeout=5.0,
        )
        log.info(f"[connect] Level 3 direct retry succeeded")
        return (ws, True)
    except Exception as e:
        raise ConnectionError(
            f"All connection levels failed for {ws_uri}: {e}"
        ) from e


if __name__ == "__main__":
    main()



