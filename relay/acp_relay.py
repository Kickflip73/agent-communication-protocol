#!/usr/bin/env python3
"""
ACP P2P Relay v3.0.0
====================
Zero-server, zero-code-change P2P Agent communication.

v2.48 changes (2026-04-05):
  - GET /peers/<peer_id>/messages — per-peer message history query:
    * Filters: direction=inbound|outbound|all, since_seq=<N>, limit, offset, sort=asc|desc
    * Returns both inbound and outbound messages involving the target peer
    * Incremental polling via since_seq (same semantics as /stream?since=<seq>)
    * Clean response: message_id, direction, from/to, parts, context_id, task_id, priority, timestamps
    * capabilities.peer_message_history=true + endpoints.peer_messages declared
    * Inbound messages matched by peer agent_name or peer_id; outbound from _recv_queue direction field
    * Useful for: auditing conversation history, debugging orchestration, replaying context
    * 10/10 tests PASS (tests/test_peer_message_history.py)

v2.7 changes (2026-03-28):
  - AgentCard top-level `limitations: string[]` field (ACP-exclusive, ref A2A #1694):
    Declares what this agent cannot do (e.g. ["no_file_access", "no_internet"]).
    Completes the three-part capability boundary declaration alongside
    `capabilities` (what the agent CAN do) and `availability` (current state).
    --limitations flag: comma-separated string (e.g. --limitations "no_file_access,no_internet")
    Optional field; defaults to [] (empty array) when not specified.
    Fully backward-compatible: old clients that don't know this field simply ignore it.

v2.6 changes (2026-03-27):
  - Task `cancelling` intermediate state (ACP-unique, fills A2A #1684/#1680 semantic gap):
    * New constant TASK_CANCELLING = "cancelling"
    * :cancel endpoint: phase-1 → `cancelling` (SSE event pushed immediately),
      phase-2 → async `canceled` (worker thread, ~instant in ref impl)
    * Idempotent: already cancelling/canceled → 200 + current status
    * AgentCard capabilities.task_cancelling = true (negotiation flag)
    * spec/core-v1.0.md §3 updated: new state row + transition diagram
    * A2A comparison table updated (ACP leads A2A on cancel semantics)

v2.5 changes (2026-03-27):
  - SSE event sequence field (`seq`): every SSE event now carries a global monotonically-
    increasing `seq` integer.  Clients can detect dropped/out-of-order events without
    relying on wall-clock timestamps.
    capabilities.sse_seq=true declared in AgentCard.
  - Named SSE event types: task-related SSE events now emit a named `event:` line on the
    wire so EventSource consumers can filter by type:
      event: acp.task.status   (for type=status events)
      event: acp.task.artifact (for type=artifact events)
    All other event types (message, peer, mdns) remain as unnamed data-only events.
  - AgentCard top-level `supported_interfaces` field: declares which ACP interface groups
    this agent implements (core/task/stream/mdns/p2p/identity).  Inspired by A2A SDK
    v1.0.0-alpha `supported_interfaces` for lightweight capability negotiation.
    Auto-derived from runtime config; override with --supported-interfaces flag.

v2.4 changes (2026-03-27):
  - AgentCard top-level `transport_modes` field: declares routing modes ["p2p", "relay"] or subset
    Distinct from capabilities.supported_transports (protocol bindings): this declares *routing* topology
    --transport-modes p2p,relay  (default: both; pass subset to restrict)
    /.well-known/acp.json now includes "transport_modes": ["p2p", "relay"]

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

VERSION = "2.53.0"  # v2.53: skill.rate_limit — per-skill/per-peer invocation frequency limiting (requests_per_minute/requests_per_day/burst) → 429 ERR_RATE_LIMIT

# v2.38: valid priority levels and sort order (lower index = higher priority)
VALID_PRIORITIES  = {"critical", "high", "normal", "low"}
_PRIORITY_ORDER   = {"critical": 0, "high": 1, "normal": 2, "low": 3}

# ── ACP Identity Extension v0.8 (optional Ed25519 module) ────────────────────
# Import relay/identity.py for standalone verify helpers.
# Falls back silently if identity.py is not on sys.path.
try:
    import os as _os_id
    import sys as _sys_id
    _identity_dir = _os_id.path.dirname(_os_id.path.abspath(__file__))
    if _identity_dir not in _sys_id.path:
        _sys_id.path.insert(0, _identity_dir)
    import identity as _identity_ext
    _IDENTITY_EXT_AVAILABLE = True
except ImportError:
    _identity_ext = None  # type: ignore
    _IDENTITY_EXT_AVAILABLE = False


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
ERR_NOT_CONNECTED        = "ERR_NOT_CONNECTED"        # No peer connected
ERR_MSG_TOO_LARGE        = "ERR_MSG_TOO_LARGE"        # Message exceeds max_msg_bytes
ERR_NOT_FOUND            = "ERR_NOT_FOUND"            # Task/peer/resource not found
ERR_INVALID_REQUEST      = "ERR_INVALID_REQUEST"      # Bad input (missing fields, invalid parts)
ERR_TIMEOUT              = "ERR_TIMEOUT"              # Sync wait timed out
ERR_INTERNAL             = "ERR_INTERNAL"             # Unexpected server error
ERR_AUTHORIZATION_TIER   = "ERR_AUTHORIZATION_TIER"   # v2.49: caller does not meet skill tier requirement
ERR_PARAM_CONSTRAINT     = "ERR_PARAM_CONSTRAINT"     # v2.50: task params violate skill.param_constraints
ERR_CONFIRM_NOT_PENDING  = "ERR_CONFIRM_NOT_PENDING"  # v2.51: task not in input_required/confirmation_pending state
ERR_SKILL_DEPRECATED     = "ERR_SKILL_DEPRECATED"     # v2.52: informational — skill is deprecated (task still created, warning injected)
ERR_RATE_LIMIT           = "ERR_RATE_LIMIT"           # v2.53: caller has exceeded skill.rate_limit (429)

def _err(code: str, message: str, http_status: int = 400,
         failed_message_id: str = None) -> tuple:
    """Build a standardized ACP error response dict + HTTP status code."""
    body = {"ok": False, "error_code": code, "error": message}
    if failed_message_id:
        body["failed_message_id"] = failed_message_id
    return body, http_status

# ── Task states ────────────────────────────────────────────────────────────────
#
#  submitted -> working -> completed      (terminal)
#                       -> failed         (terminal)
#                       -> input_required (interrupted; resumes via /tasks/{id}/continue)
#                       -> cancelling     (v2.6: intermediate cancel state; ACP-unique)
#                            └──> canceled (terminal)
#
# BUG-002 fix (2026-03-23): added TASK_CANCELED — spec §3 defines 5 states including canceled.
# v2.6 (2026-03-27): added TASK_CANCELLING — intermediate state exposing cancel-in-progress
#   to observers via SSE.  Fills semantic gap identified in A2A issues #1684/#1680 (CancelTask
#   lacks a "being cancelled" intermediate state).  ACP leads A2A on this.
#
TASK_SUBMITTED      = "submitted"
TASK_WORKING        = "working"
TASK_COMPLETED      = "completed"
TASK_FAILED         = "failed"
TASK_CANCELED       = "canceled"
TASK_CANCELLING     = "cancelling"     # v2.6: intermediate cancel state (ACP-unique)
TASK_INPUT_REQUIRED       = "input_required"
TASK_CONFIRMATION_PENDING = "confirmation_pending"   # v2.51: T3 awaiting human sign-off

TERMINAL_STATES    = {TASK_COMPLETED, TASK_FAILED, TASK_CANCELED}
INTERRUPTED_STATES = {TASK_INPUT_REQUIRED}
CONFIRMATION_PENDING_STATES = {TASK_CONFIRMATION_PENDING}  # v2.51
# States that represent an in-progress cancel (not yet terminal)
CANCELLING_STATES  = {TASK_CANCELLING}

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

# v2.12: WebSocket /ws/stream native push clients
# Each entry is a socket-like object with a send_ws_text(data: str) method
_ws_stream_clients: set = set()
_ws_stream_lock = threading.Lock()

# v2.3: SSE event sequence counter — monotonically-increasing global seq for all SSE events.
# Clients use seq to detect out-of-order or dropped events without relying on wall-clock timestamps.
_sse_seq_lock = threading.Lock()
_sse_seq: int = 0

# v2.13: Event replay log — last _EVENT_LOG_MAX events kept in-memory for ?since= replay.
# Allows clients to recover missed events after reconnect without data loss.
_EVENT_LOG_MAX = 500                    # ring buffer capacity
_event_log: list = []                  # list of event dicts, ordered by seq
_event_log_lock = threading.Lock()

# BUG-045: global threading.Lock for legacy _peer_ws path.
# Using threading.Lock (not asyncio.Lock) because multiple HTTP threads call
# _ws_send_sync() concurrently and we need cross-thread serialisation.
_ws_send_global_lock = threading.Lock()

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

# ── Test mode (v2.48) ────────────────────────────────────────────────────────
# --test-mode enables POST /debug/inject for unit-test message + peer injection.
# NEVER enabled in production; gated behind explicit CLI flag.
_test_mode: bool = False

# --auto-confirm-t3: skip human_confirmation_required gate for T3 skills (test-only).
# When True, POST /tasks with T3 + human_confirmation_required proceeds directly to submitted.
_auto_confirm_t3: bool = False

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
        now_utc  = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
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
_did_key: str = None              # v0.8: did:key:z6Mk... W3C did:key identifier (base58btc multibase)
_ca_cert_pem: str = None          # v1.5: optional PEM-encoded CA-signed certificate (hybrid identity)
_delegation_chain: list = []      # v2.16: signed delegation entries [{delegator_did, scope, expires_at, sig}]


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


_BASE58_ALPHABET = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _base58_encode(data: bytes) -> str:
    """Pure-Python base58btc encoding (stdlib-only, no external deps)."""
    n = int.from_bytes(data, "big")
    result = bytearray()
    while n > 0:
        n, remainder = divmod(n, 58)
        result.append(_BASE58_ALPHABET[remainder])
    # leading zero bytes → '1' characters
    for byte in data:
        if byte != 0:
            break
        result.append(_BASE58_ALPHABET[0])
    return result[::-1].decode("ascii")


def _base58_decode(s: str) -> bytes:
    """Pure-Python base58btc decoding (stdlib-only, no external deps)."""
    alphabet = _BASE58_ALPHABET
    n = 0
    for char in s.encode("ascii"):
        n = n * 58 + alphabet.index(char)
    # Determine the number of leading zero bytes
    leading_zeros = 0
    for char in s.encode("ascii"):
        if char == alphabet[0]:
            leading_zeros += 1
        else:
            break
    result = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return bytes(leading_zeros) + result


def _resolve_did_to_pubkey(did: str) -> dict:
    """Resolve a DID to its Ed25519 public key (offline, no HTTP required).

    v2.33: Supports did:acp: and did:key: schemes.

    Returns:
      {
        "ok": True,
        "did": str,
        "scheme": "did:acp" | "did:key",
        "public_key_b64": str,        # base64url-encoded 32-byte Ed25519 public key
        "public_key_hex": str,        # hex-encoded
        "algorithm": "ed25519",
        "derived_did_acp": str,       # canonical did:acp: derived from pubkey
        "derived_did_key": str,       # canonical did:key: derived from pubkey
        "consistent": bool,           # True if input DID round-trips correctly
      }
    or {"ok": False, "error": str, "did": str}
    """
    if not did or not isinstance(did, str):
        return {"ok": False, "error": "did must be a non-empty string", "did": did}

    try:
        if did.startswith("did:acp:"):
            # did:acp:<base64url-no-padding(32-byte pubkey)>
            encoded = did[len("did:acp:"):]
            # Add padding back
            pub_raw = _base64.urlsafe_b64decode(encoded + "==")
            if len(pub_raw) != 32:
                return {"ok": False, "error": f"did:acp: pubkey must be 32 bytes, got {len(pub_raw)}", "did": did}

        elif did.startswith("did:key:z"):
            # did:key:z<base58btc(0xed01 + 32-byte pubkey)>
            # Multibase: leading 'z' = base58btc
            encoded = did[len("did:key:z"):]
            decoded = _base58_decode(encoded)
            # Expect 2-byte multicodec prefix [0xed, 0x01] + 32-byte pubkey
            if len(decoded) < 34:
                return {"ok": False, "error": f"did:key: decoded length {len(decoded)} < 34", "did": did}
            if decoded[0] != 0xed or decoded[1] != 0x01:
                return {"ok": False, "error": f"did:key: expected Ed25519 multicodec 0xed01, got {decoded[:2].hex()}", "did": did}
            pub_raw = decoded[2:34]

        else:
            return {"ok": False, "error": f"unsupported DID scheme (supported: did:acp:, did:key:z)", "did": did}

        # Validate it's a real Ed25519 public key
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        Ed25519PublicKey.from_public_bytes(pub_raw)

        pub_b64 = _base64.urlsafe_b64encode(pub_raw).rstrip(b"=").decode()
        pub_hex = pub_raw.hex()
        derived_acp = _pubkey_to_did_acp(pub_raw)
        derived_key = _pubkey_to_did_key(pub_raw)
        consistent  = (did == derived_acp) or (did == derived_key)

        return {
            "ok":              True,
            "did":             did,
            "scheme":          "did:acp" if did.startswith("did:acp:") else "did:key",
            "public_key_b64":  pub_b64,
            "public_key_hex":  pub_hex,
            "algorithm":       "ed25519",
            "derived_did_acp": derived_acp,
            "derived_did_key": derived_key,
            "consistent":      consistent,
        }

    except Exception as e:
        return {"ok": False, "error": str(e), "did": did}


def _pubkey_to_did_key(pubkey_bytes: bytes) -> str:
    """Derive a W3C did:key identifier from a raw 32-byte Ed25519 public key.

    Follows the did:key spec (https://w3c-ccg.github.io/did-key-spec/):
      - Prepend Ed25519 multicodec prefix 0xed 0x01
      - Encode with base58btc (pure Python, no external deps)
      - Prefix with 'z' (multibase base58btc indicator)

    Format: did:key:z6Mk<base58btc(0xed01 + pubkey)>
    Example: did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK
    """
    ED25519_MULTICODEC = bytes([0xed, 0x01])
    prefixed = ED25519_MULTICODEC + pubkey_bytes
    encoded = _base58_encode(prefixed)
    return f"did:key:z{encoded}"


def _ed25519_load_or_create(identity_path: str = None) -> bool:
    """Load existing Ed25519 keypair or generate a new one. Returns success."""
    global _ed25519_private, _ed25519_public_b64, _did_acp, _did_key
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
            _did_key = _pubkey_to_did_key(pub_raw)
            log.info(f"Ed25519 identity loaded from {path} | did={_did_key}")
            return True
        except Exception as e:
            log.warning(f"Failed to load identity from {path}: {e} — generating new keypair")

    _ed25519_private = Ed25519PrivateKey.generate()
    pub_raw = _ed25519_private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    priv_raw = _ed25519_private.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    _ed25519_public_b64 = _base64.urlsafe_b64encode(pub_raw).rstrip(b"=").decode()
    _did_acp = _pubkey_to_did_acp(pub_raw)
    _did_key = _pubkey_to_did_key(pub_raw)
    priv_b64 = _base64.urlsafe_b64encode(priv_raw).rstrip(b"=").decode()
    try:
        path.write_text(_json.dumps({
            "scheme":      "ed25519",
            "public_key":  _ed25519_public_b64,
            "did":         _did_key,
            "did_acp":     _did_acp,
            "private_key": priv_b64,
            "created_at":  _now(),
        }, indent=2))
        path.chmod(0o600)
        log.info(f"Ed25519 keypair generated and saved to {path} | did={_did_key}")
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
_broadcast_log: list = []                    # v2.23: broadcast history (ring buffer, max 200 entries)
_BROADCAST_LOG_MAX = 200
_pending_pongs: dict = {}  # v2.25: nonce -> asyncio.Future; resolved when acp.pong arrives
_vouch_chain: list  = []  # v2.27: list of vouch_chain entries [{voucher_did, vouched_did, vouched_at, sig, comment}]

def _make_peer_id():
    global _peer_id_counter
    _peer_id_counter += 1
    return f"peer_{_peer_id_counter:03d}"

def _register_peer(peer_id=None, link=None, ws=None, link_token=None, remote_address=None):
    """Register or update a peer connection. Returns peer_id."""
    pid = peer_id or _make_peer_id()
    existing = _peers.get(pid, {})
    _peers[pid] = {
        "id":               pid,
        "name":             existing.get("name", pid),
        "link":             link or existing.get("link"),
        "link_token":       link_token or existing.get("link_token"),
        "ws":               ws or existing.get("ws"),
        "connected":        True,
        "connected_at":     existing.get("connected_at") or _now(),
        "messages_sent":      existing.get("messages_sent", 0),
        "messages_received":  existing.get("messages_received", 0),
        "messages_delivered": existing.get("messages_delivered", 0),  # v2.35: ack count
        "messages_read":      existing.get("messages_read", 0),       # v2.36: read receipt count
        "typing":             existing.get("typing", False),           # v2.37: typing indicator state
        "typing_since":       existing.get("typing_since", None),      # v2.37: ISO ts when peer started typing
        "agent_card":         existing.get("agent_card"),
        "remote_address":     remote_address or existing.get("remote_address"),  # v2.16: for dedup
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
    "messages_sent":      0,
    "messages_received":  0,
    "messages_deduped":   0,
    "messages_delivered": 0,   # v2.35: count of acp.delivered ACKs received from peers
    "messages_read":      0,       # v2.36: count of acp.read ACKs received from peers
    "last_received_message_id": None,  # v2.36: track most-recent inbound msg_id for read receipt
    "peer_typing":       False,         # v2.37: True when peer sent acp.typing{typing:true}
    "peer_typing_since": None,          # v2.37: ISO timestamp when peer started typing
    "priority_counts": {               # v2.38: inbound message counts per priority level
        "critical": 0, "high": 0, "normal": 0, "low": 0
    },
    "reconnect_count":    0,
    "tasks_created":     0,
    "started_at":        None,
    "max_msg_bytes":     MAX_MSG_BYTES,
    "server_seq":        0,
    "peer_count":        0,    # v0.6: active peer count
    "p2p_enabled":       False, # v2.3: set True when P2P WebSocket listener is active
    "limitations":       [],    # v2.20: LimitationObject[] — what this agent CANNOT do (structured capability boundary)
    "agent_limitations": None,  # v2.40: structured constraint dict (populated after _LIMITATIONS is defined)
    "connection_type":   "host",  # v2.19: NAT traversal result — "host" (default) | "p2p_direct" | "dcutr_direct" | "relay"
}

def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

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
#   schedule:         str         # v2.17: CRON expression (e.g. "0 */4 * * *") — auto-computes next_active_at
#   next_active_at:   ISO-8601 Z  # next scheduled wake (agent-maintained or auto-computed from schedule)
#   last_active_at:   ISO-8601 Z  # last wake time (auto-set on startup / POST /availability/heartbeat)
#   task_latency_max_seconds: int # worst-case task processing latency
#   timezone:         str         # v2.17: IANA timezone for schedule interpretation (default "UTC")
_availability: dict  = {}         # empty = persistent (default behaviour)
_extensions:   list  = []         # v1.3: [{uri, required, params}] Extension list (opt-in)
_http2_enabled: bool = False      # v1.6: HTTP/2 transport binding (requires hypercorn+h2)
_transport_modes: list = ["p2p", "relay"]  # v2.4: top-level AgentCard field — routing modes supported by this node
_limitations: list = []  # v2.20: top-level AgentCard field — LimitationObject[] (structured) or string[] (legacy compat)
_skill_limitations_overrides: dict = {}  # v2.29: runtime per-skill limitations override {skill_id: LimitationObject[]}

# v2.40: AgentCard limitations — explicit constraint declarations (inspired by A2A IS#1694)
# Distinct from _limitations (LimitationObject[]) — this is a structured dict of hard numeric/enum limits.
# All fields are optional; agents may expose a subset.
_LIMITATIONS = {
    "max_message_size_bytes":  65536,                               # 64 KB per message
    "max_recv_queue_size":     1000,                                # recv queue hard cap
    "max_wait_seconds":        30,                                  # long-poll max wait (v2.39)
    "max_peers":               100,                                 # concurrent peer connections
    "supported_message_roles": ["user", "agent", "system"],        # valid role values
    "supported_priorities":    ["critical", "high", "normal", "low"],  # valid priority values
}
# Populate _status["agent_limitations"] now that _LIMITATIONS is defined (v2.40)
_status["agent_limitations"] = _LIMITATIONS

# LimitationObject schema (v2.20, ref A2A #1694):
#   kind:      str  — "capability" | "modality" | "scale" | "domain" | "access" | "other"
#   code:      str  — machine-readable code (e.g. "no_file_access", "image-input-unsupported")
#   message:   str  — human-readable description
#   permanent: bool — True = stable/static constraint; False = runtime/transient degradation

_VALID_LIMITATION_KINDS = {"capability", "modality", "scale", "domain", "access", "other"}

def _parse_limitation(raw) -> dict:
    """Normalize a limitation entry to LimitationObject.
    Accepts:
      - str  → {"kind": "capability", "code": raw, "message": raw, "permanent": True}
      - dict → validated/defaulted LimitationObject
    """
    if isinstance(raw, str):
        code = raw.strip()
        return {"kind": "capability", "code": code, "message": code, "permanent": True}
    if isinstance(raw, dict):
        kind = raw.get("kind", "other")
        if kind not in _VALID_LIMITATION_KINDS:
            kind = "other"
        code = str(raw.get("code", raw.get("message", "unknown"))).strip()
        message = str(raw.get("message", code)).strip()
        permanent = bool(raw.get("permanent", True))
        obj = {"kind": kind, "code": code, "message": message, "permanent": permanent}
        return obj
    # Fallback: coerce to string
    return _parse_limitation(str(raw))

# v2.3: supported_interfaces — top-level AgentCard field declaring which ACP interface groups
# this agent implements.  Values:
#   core     — base messaging endpoints (/message:send, /status, /stream, /.well-known/acp.json)
#   task     — task lifecycle endpoints (/tasks, /tasks/{id}, /tasks/{id}:cancel, /tasks/{id}:subscribe)
#   stream   — SSE event stream with seq + named event types (v2.3)
#   mdns     — mDNS LAN peer discovery (--advertise-mdns)
#   p2p      — direct P2P WebSocket transport (acp:// link)
#   identity — Ed25519/DID identity (--identity)
# Implementors may declare a subset; clients use this list for capability negotiation.
_VALID_INTERFACES = {"core", "task", "stream", "mdns", "p2p", "identity"}
_supported_interfaces_override: list | None = None  # None = auto-derive at runtime


def _make_supported_interfaces() -> list:
    """
    v2.3: Derive the supported_interfaces list from runtime configuration.
    Returns a sorted list of interface group identifiers.
    If overridden via --supported-interfaces CLI flag, returns that list verbatim.
    """
    if _supported_interfaces_override is not None:
        return list(_supported_interfaces_override)
    ifaces = {"core", "task", "stream"}          # always present
    if _mdns_running:
        ifaces.add("mdns")
    if _status.get("p2p_enabled", False):
        ifaces.add("p2p")
    if _ed25519_private:
        ifaces.add("identity")
    return sorted(ifaces)


def _parse_skill_obj(s):
    """Normalise a single skill entry to a structured dict.

    Accepts either a plain string ("summarize") or a dict with at least
    {"id": ..., "name": ...}.  Returns a canonical skill object:
    {id, name, description?, tags?, examples?, input_modes?, output_modes?,
     constraints?, limitations?}

    constraints (v2.26): per-skill runtime limits that QuerySkill can check:
      {
        "max_file_size_bytes":  <int|null>,   # max single-file payload
        "concurrent_tasks":     <int|null>,   # max parallel tasks this skill handles
        "context_window":       <int|null>,   # max context tokens (LLM skills)
      }
    Any null/absent field means "no declared limit" (treated as unlimited).

    limitations (v2.28): per-skill capability boundary declarations (ref A2A #1694).
      Each entry is a LimitationObject (same schema as top-level AgentCard.limitations):
        {
          "kind":      str,   # "capability"|"modality"|"scale"|"domain"|"access"|"other"
          "code":      str,   # machine-readable identifier (e.g. "no_audio_input")
          "message":   str,   # human-readable description
          "permanent": bool,  # true = always; false = transient/conditional
        }
      Accepts both string shorthand (promoted to LimitationObject) and full dicts.
      Interoperates with A2A IS#1694 limitations field at skill level.

    authorization_tier (v2.49): per-skill authorization tier (ref A2A #1716 / SINT Protocol).
      Declares the minimum trust level required to invoke this skill.
      Values: "T0" | "T1" | "T2" | "T3" | null
        T0 — observe/query only (zero-risk): auto-execute, no trust requirement
        T1 — read / non-destructive: auto-execute, no trust requirement
        T2 — consequential action (write, send, trigger): requires caller trust_score >= 0.7
        T3 — irreversible (delete, transfer, deploy): requires trust_score >= 0.9
             AND trust.signals must include a "verified_identity" signal
      null (default): no authorization tier enforcement (backward-compatible)
      Enforcement point: POST /tasks creation — returns 403 ERR_AUTHORIZATION_TIER if
        the calling peer does not satisfy the declared tier requirements.

    human_confirmation_required (v2.51): if True AND skill's authorization_tier == "T3", a POST /tasks
      targeting this skill enters "confirmation_pending" state instead of "submitted".
      The task MUST be explicitly approved via POST /tasks/{id}:confirm before execution proceeds.
      Rejection is done via POST /tasks/{id}:reject → task transitions to "failed".
      Bypassed when relay is started with --auto-confirm-t3 (test-only flag).
      null/false (default): T3 tasks proceed as submitted immediately (backward-compatible).

    param_constraints (v2.50): parameter-level invocation constraints (ref SINT Protocol / A2A #1716).
      Declares per-parameter rules applied when the skill is invoked via POST /tasks with a
      "params" dict in the request body.  Each key in param_constraints maps to a ConstraintRule:
        {
          "type":           "string"|"number"|"integer"|"boolean"|"array"  (optional, type check)
          "required":       true|false   (default false; if true, key must be present in params)
          "min":            <number>     (numeric: value >= min; string/array: length >= min)
          "max":            <number>     (numeric: value <= max; string/array: length <= max)
          "allowed_values": [...]        (enum check: value must be in this list)
          "pattern":        "<regex>"    (string only: value must match regex)
        }
      All rule fields are optional — only declared fields are checked.
      Enforcement point: POST /tasks — returns 400 ERR_PARAM_CONSTRAINT with violated_params list.
      null/absent param_constraints (default): no parameter validation (backward-compatible).

    deprecation_notice (v2.52): optional skill sunset declaration.
      {
        "deprecated":         bool,   # true = this skill is deprecated
        "deprecated_since":   str,    # ISO date string (e.g. "2026-04-01")
        "sunset_at":          str,    # ISO date string after which skill may be removed
        "replacement_skill":  str,    # id of the recommended replacement skill (optional)
        "message":            str,    # human-readable migration guidance (optional)
      }
      Behaviour: POST /tasks targeting a deprecated skill still succeeds (201) but the response
      includes a top-level "deprecation_warning" object with the notice fields.
      null/absent (default): skill is active, no warning injected (backward-compatible).
    """
    # v2.49: validate authorization_tier value
    _VALID_TIERS = {None, "T0", "T1", "T2", "T3"}

    if isinstance(s, dict):
        sid = str(s.get("id", s.get("name", "unknown"))).strip()
        # v2.26: parse per-skill constraints block
        raw_constraints = s.get("constraints") or {}
        # v2.28: parse per-skill limitations[] (ref A2A #1694)
        raw_limitations = s.get("limitations") or []
        # v2.49: parse authorization_tier
        raw_tier = s.get("authorization_tier")
        auth_tier = raw_tier if raw_tier in _VALID_TIERS else None
        # v2.50: parse param_constraints — dict of {param_name: ConstraintRule}
        raw_pc = s.get("param_constraints")
        param_constraints = _parse_param_constraints(raw_pc) if raw_pc else None
        # v2.51: parse human_confirmation_required
        human_conf = bool(s.get("human_confirmation_required", False))
        # v2.53: parse rate_limit
        rate_limit = _parse_rate_limit(s.get("rate_limit"))
        # v2.52: parse deprecation_notice
        raw_dep = s.get("deprecation_notice")
        if isinstance(raw_dep, dict) and raw_dep.get("deprecated"):
            dep_notice = {
                "deprecated":        True,
                "deprecated_since":  str(raw_dep.get("deprecated_since", "")),
                "sunset_at":         str(raw_dep.get("sunset_at", "")),
                "replacement_skill": str(raw_dep.get("replacement_skill", "")),
                "message":           str(raw_dep.get("message", "")),
            }
        else:
            dep_notice = None
        obj = {
            "id":                          sid,
            "name":                        str(s.get("name", sid)),
            "description":                 s.get("description", ""),
            "tags":                        list(s.get("tags") or []),
            "examples":                    list(s.get("examples") or []),
            "input_modes":                 list(s.get("input_modes") or []),
            "output_modes":                list(s.get("output_modes") or []),
            "constraints":                 {
                "max_file_size_bytes": raw_constraints.get("max_file_size_bytes"),
                "concurrent_tasks":   raw_constraints.get("concurrent_tasks"),
                "context_window":     raw_constraints.get("context_window"),
            },
            "limitations":                 [_parse_limitation(lim) for lim in raw_limitations],  # v2.28
            "authorization_tier":          auth_tier,        # v2.49: T0/T1/T2/T3/null
            "param_constraints":           param_constraints, # v2.50: parameter-level ConstraintRule dict
            "human_confirmation_required": human_conf,        # v2.51: T3 requires human sign-off
            "deprecation_notice":          dep_notice,        # v2.52: skill sunset declaration or None
            "rate_limit":                  rate_limit,        # v2.53: per-skill/per-peer rate limit or None
        }
    else:
        sid = str(s).strip()
        obj = {
            "id":                          sid,
            "name":                        sid,
            "description":                 "",
            "tags":                        [],
            "examples":                    [],
            "input_modes":                 [],
            "output_modes":                [],
            "constraints":                 {
                "max_file_size_bytes": None,
                "concurrent_tasks":   None,
                "context_window":     None,
            },
            "limitations":                 [],    # v2.28: empty by default
            "authorization_tier":          None,  # v2.49: no tier = unrestricted
            "param_constraints":           None,  # v2.50: no param constraints = unrestricted
            "human_confirmation_required": False, # v2.51: default no confirmation needed
            "deprecation_notice":          None,  # v2.52: no deprecation by default
        }
    return obj


# ── v2.16: Delegation Chain helpers ───────────────────────────────────────────

def _build_delegation_entry(delegator_did: str, scope: list, expires_at: float) -> dict:
    """Create a signed delegation entry for the local agent's identity.

    The local agent (delegatee) signs a canonical payload asserting that
    *delegator_did* has delegated *scope* to it, expiring at *expires_at*.

    Payload (JSON-canonical, sorted keys):
        {"delegatee_did": <our did>, "delegator_did": <their did>,
         "expires_at": <unix float>, "scope": <sorted list>}

    The signature covers the UTF-8 encoding of that canonical JSON.
    Returns a dict with: delegator_did, delegatee_did, scope, expires_at, sig, scheme.
    Raises RuntimeError if no Ed25519 identity is loaded.
    """
    import json as _json
    if not _ed25519_private or not _did_acp:
        raise RuntimeError("delegation_chain requires --identity (Ed25519 keypair)")
    payload = _json.dumps({
        "delegatee_did": _did_acp,
        "delegator_did": delegator_did,
        "expires_at":    expires_at,
        "scope":         sorted(scope),
    }, sort_keys=True, separators=(",", ":")).encode()
    sig_bytes = _ed25519_private.sign(payload)
    sig_b64   = _base64.urlsafe_b64encode(sig_bytes).rstrip(b"=").decode()
    return {
        "delegator_did": delegator_did,
        "delegatee_did": _did_acp,
        "scope":         sorted(scope),
        "expires_at":    expires_at,
        "sig":           sig_b64,
        "scheme":        "ed25519",
    }


def _verify_delegation_entry(entry: dict) -> bool:
    """Verify a delegation entry's signature.

    Verifies that the *delegatee* (identified by entry['delegatee_did']) signed
    the canonical payload using their Ed25519 key.  For local entries this
    re-derives the public key from the DID.  Returns True if valid, False otherwise.
    """
    import json as _json
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        payload = _json.dumps({
            "delegatee_did": entry["delegatee_did"],
            "delegator_did": entry["delegator_did"],
            "expires_at":    entry["expires_at"],
            "scope":         sorted(entry["scope"]),
        }, sort_keys=True, separators=(",", ":")).encode()
        sig_bytes = _base64.urlsafe_b64decode(entry["sig"] + "==")
        # Extract pubkey from did:acp:<base64url>
        did = entry["delegatee_did"]
        if not did.startswith("did:acp:"):
            return False
        pub_bytes = _base64.urlsafe_b64decode(did[len("did:acp:"):] + "==")
        pub_key   = Ed25519PublicKey.from_public_bytes(pub_bytes)
        pub_key.verify(sig_bytes, payload)
        return True
    except Exception:
        return False


def _delegation_chain_status() -> dict:
    """Return a summary of the current delegation chain for status/debug."""
    import time as _time
    now = _time.time()
    entries = []
    for e in _delegation_chain:
        expired = e.get("expires_at", 0) < now
        entries.append({**e, "expired": expired})
    return {
        "count":    len(_delegation_chain),
        "entries":  entries,
        "has_valid": any(not e["expired"] for e in entries),
    }


# ── v2.17: Availability Schedule (CRON) helpers ──────────────────────────────

def _parse_cron_field(field: str, lo: int, hi: int) -> list:
    """Parse a single cron field into a sorted list of integers.
    Supports: * / , -  (no names).  Returns sorted list of valid values in [lo, hi].
    """
    values = set()
    for part in field.split(","):
        part = part.strip()
        if "/" in part:
            rng, step_str = part.split("/", 1)
            step = int(step_str)
            if rng == "*":
                start, end = lo, hi
            elif "-" in rng:
                s, e = rng.split("-", 1)
                start, end = int(s), int(e)
            else:
                start = int(rng)
                end = hi
            values.update(range(start, end + 1, step))
        elif "-" in part:
            s, e = part.split("-", 1)
            values.update(range(int(s), int(e) + 1))
        elif part == "*":
            values.update(range(lo, hi + 1))
        else:
            values.add(int(part))
    return sorted(v for v in values if lo <= v <= hi)


def _next_cron_datetime(expr: str, after_dt=None) -> "datetime.datetime | None":
    """Compute the next UTC datetime matching the 5-field cron expression.
    Fields: minute hour dom month dow  (all 0-indexed except month/dom).
    Returns a UTC-aware datetime or None if parsing fails.
    """
    import datetime as _dt
    try:
        fields = expr.strip().split()
        if len(fields) != 5:
            return None
        minutes = _parse_cron_field(fields[0],  0, 59)
        hours   = _parse_cron_field(fields[1],  0, 23)
        days    = _parse_cron_field(fields[2],  1, 31)
        months  = _parse_cron_field(fields[3],  1, 12)
        dows    = _parse_cron_field(fields[4],  0,  6)  # 0=Sun
    except Exception:
        return None

    base = after_dt or _dt.datetime.now(_dt.timezone.utc)
    # Advance 1 minute so next > now
    candidate = (base + _dt.timedelta(minutes=1)).replace(second=0, microsecond=0)

    # Iterate up to 4 years to find a match
    limit = base + _dt.timedelta(days=4 * 366)
    while candidate < limit:
        if candidate.month not in months:
            # Jump to next valid month
            candidate = candidate.replace(day=1, hour=0, minute=0)
            candidate += _dt.timedelta(days=1)
            continue
        if candidate.day not in days or candidate.weekday() not in [d if d != 0 else 6 for d in dows]:
            # Weekday mapping: cron 0=Sun → Python 6=Sun
            # Check both dom and dow
            dom_ok  = candidate.day in days
            dow_val = (candidate.weekday() + 1) % 7  # Python Mon=0 → cron Mon=1; Sun: Python 6 → cron 0
            dow_ok  = dow_val in dows
            # Standard cron: if both dom and dow are restricted, either match suffices (OR)
            # If only one is restricted (not *), use that one
            dom_star = fields[2] == "*"
            dow_star = fields[4] == "*"
            if dom_star and not dow_ok:
                candidate = candidate.replace(hour=0, minute=0) + _dt.timedelta(days=1); continue
            if dow_star and not dom_ok:
                candidate = candidate.replace(hour=0, minute=0) + _dt.timedelta(days=1); continue
            if not dom_star and not dow_star and not (dom_ok or dow_ok):
                candidate = candidate.replace(hour=0, minute=0) + _dt.timedelta(days=1); continue
        if candidate.hour not in hours:
            next_h = next((h for h in hours if h > candidate.hour), None)
            if next_h is None:
                candidate = candidate.replace(hour=0, minute=0) + _dt.timedelta(days=1); continue
            candidate = candidate.replace(hour=next_h, minute=0); continue
        if candidate.minute not in minutes:
            next_m = next((m for m in minutes if m > candidate.minute), None)
            if next_m is None:
                candidate = candidate.replace(minute=0) + _dt.timedelta(hours=1); continue
            candidate = candidate.replace(minute=next_m); continue
        # All fields match
        return candidate
    return None


def _availability_with_schedule(avail: dict) -> dict:
    """Return a copy of the availability dict, auto-computing next_active_at
    from schedule if present and next_active_at is not already set.
    """
    import datetime as _dt
    result = dict(avail)
    schedule = result.get("schedule")
    if schedule and not result.get("next_active_at"):
        nxt = _next_cron_datetime(schedule)
        if nxt:
            result["next_active_at"] = nxt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return result


# ── end v2.17 helpers ─────────────────────────────────────────────────────────


def _make_agent_card(name, skills):
    """Build the AgentCard dict.

    *skills* may be:
      - a list of plain strings (legacy) → auto-converted to structured objects
      - a list of dicts (v2.10+ structured)
      - mixed list
    """
    structured_skills = [_parse_skill_obj(s) for s in skills]
    card = {
        "name":            name,
        "version":         VERSION,
        "acp_version":     VERSION,
        "description":     f"ACP P2P Agent: {name}",
        "http_port":       _status["http_port"],
        "timestamp":       _now(),
        "transport_modes": list(_transport_modes),          # v2.4: routing modes ["p2p", "relay"] or subset
        "supported_interfaces": _make_supported_interfaces(), # v2.3: declared interface groups
        "limitations": [_parse_limitation(lim) for lim in _limitations],  # v2.20: LimitationObject[] (structured, backward-compat)
        "agent_limitations": _LIMITATIONS,                   # v2.40: structured constraint dict (numeric/enum limits)
        "skills_schema_url": "/docs/openapi-skills.yaml",   # v2.41: skills OpenAPI spec
        "skills":      structured_skills,
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
            "supported_transports": (                          # v2.2: declare supported transport bindings (A2A-inspired)
                ["http", "ws", "h2c"] if _http2_enabled else ["http", "ws"]
            ),
            "sse_seq":            True,                         # v2.3: SSE events carry global seq + named event types
            "task_cancelling":    True,                         # v2.6: `cancelling` intermediate state before `canceled` (ACP-unique, fills A2A #1684/#1680 gap)
            "ws_stream":          True,                         # v2.12: GET /ws/stream WebSocket native push endpoint
            "event_replay":       True,                         # v2.13: ?since=<seq> replay on /stream and /ws/stream
            "trust_signals":      True,                         # v2.14: trust.signals[] structured evidence in AgentCard
            "context_query":      True,                         # v2.15: GET /context/<id>/messages multi-turn query
            "delegation_chain":   bool(_delegation_chain),      # v2.16: signed delegation chain in AgentCard identity
            "availability_schedule": bool(_availability.get("schedule")),  # v2.17: CRON-based scheduling
            "trust_jwks":         True,                                      # v2.18: JWKS compatibility layer — /.well-known/jwks.json
            "well_known_rfc8615":      True,                                  # v2.47: /.well-known/* endpoints return RFC 8615 headers (Cache-Control/Vary/X-Content-Type-Options)
            "limitations_structured":  True,                                  # v2.20: limitations[] uses LimitationObject format
            "limitations_patch":       True,                                  # v2.21: PATCH /.well-known/acp.json supports 'limitations' key
            "limitations_filter":      True,                                  # v2.21: GET /.well-known/acp.json?filter_limitations=<value> supported
            "peers_broadcast":         True,                                  # v2.22: POST /peers/broadcast — fanout to all connected peers
            "peers_broadcast_subset":  True,                                  # v2.23: target_peers[] subset broadcast
            "peers_broadcast_history": True,                                  # v2.23: GET /peers/broadcast/history
            "peer_card_query":         True,                                  # v2.24: GET /peers/<id>/card
            "peer_ping":               True,                                  # v2.25: POST /peers/<id>/ping — app-layer liveness probe + RTT
            "skills_query_constraints": True,                                 # v2.26: QuerySkill constraints (max_file_size_bytes/concurrent_tasks/context_window)
            "peers_pagination":         True,                                  # v2.27: GET /peers ?limit=&offset=&filter=
            "peers_vouch_chain":        True,                                  # v2.27: trust.signals vouch_chain type
            "skill_limitations":        True,                                  # v2.28: per-skill limitations[] field (ref A2A #1694)
            "skill_status_probe":       True,                                  # v2.29: GET /skills/<id>/status — per-skill availability probe
            "skill_limitations_patch":  True,                                  # v2.29: PATCH /skills/<id>/limitations — runtime per-skill limitations update
            "error_failed_msg_id":      True,                                  # v2.30: failed_message_id in error response (ref ANP failed_msg_id)
            "message_dedup":            True,                                  # v2.32: 30s TTL dedup window on /message:send and /peer/<id>/send
            "pubkey_discovery":         True,                                  # v2.33: GET|POST /identity/pubkey-discovery — resolve did:acp:/did:key: → Ed25519 pubkey (offline, no HTTP to peer)
            "peer_trust":               True,                                  # v2.34: GET /peers/<id>/trust — structured per-peer trust score
            "delivery_ack":             True,                                  # v2.35: acp.delivered ACK frame; sender knows when message was received
            "read_receipt":             True,                                  # v2.36: acp.read frame; sender knows when peer consumed the message
            "typing_indicator":         True,                                  # v2.37: acp.typing frame; POST /message:typing; peer typing status
            "message_priority":         True,                                  # v2.38: priority field in send; /recv sorted critical>high>normal>low
            "recv_long_poll":           True,                                  # v2.39: GET /recv?wait=<seconds> — long-poll support
            "agent_limitations":        True,                                  # v2.40: structured agent_limitations dict in AgentCard and /status
            "skills_openapi_spec":      True,                                  # v2.41: GET /docs/openapi-skills.yaml — OpenAPI 3.1 spec for /skills
            "tasks_pagination":         True,                                  # v0.9: GET /tasks supports page_size/after/multi-status params (A2A v1.0 aligned)
            "peer_message_history":         True,                              # v2.48: GET /peers/<id>/messages — per-peer message history with direction/seq/sort filters
            "skill_authorization_tiers":    True,                              # v2.49: skill.authorization_tier T0-T3 enforcement via POST /tasks (ref A2A #1716)
            "skill_param_constraints":      True,                              # v2.50: skill.param_constraints — parameter-level validation at POST /tasks (ref SINT Protocol)
            "t3_human_confirmation":        True,                              # v2.51: T3 skills with human_confirmation_required=true enter confirmation_pending; :confirm/:reject endpoints
            "task_audit_log":              True,                              # v2.52: GET /tasks/{id}/audit-log — immutable per-task audit trail
            "skill_deprecation_notice":    True,                              # v2.52: skill.deprecation_notice — POST /tasks on deprecated skill returns deprecation_warning
            "skill_rate_limit":            True,                              # v2.53: skill.rate_limit — per-skill/per-peer RPM/RPD/burst; POST /tasks returns 429 ERR_RATE_LIMIT when exceeded
        },

        "identity": ({
            "scheme":     "ed25519+ca" if _ca_cert_pem else "ed25519",
            "public_key": _ed25519_public_b64,
            "pubkey_b64": _ed25519_public_b64,   # v0.8: alias — base64url-encoded 32-byte Ed25519 public key
            "did":        _did_acp or _did_key,    # v1.3: primary DID — did:acp: preferred, fallback did:key:
            "did_key":    _did_key,              # v0.8: W3C did:key:z6Mk... identifier (base58btc multibase)
            "did_acp":    _did_acp,              # v1.3: did:acp:<base64url> — ACP-native identifier
            **( {"ca_cert": _ca_cert_pem} if _ca_cert_pem else {} ),  # v1.5: CA-signed cert (hybrid model)
            **( {"delegation": _delegation_chain} if _delegation_chain else {} ),  # v2.16: signed delegation chain
        } if _ed25519_private else None),
        "trust": {
            "scheme":  "hmac-sha256" if _hmac_secret else "none",
            "enabled": bool(_hmac_secret),
            "signals": _build_trust_signals(),   # v2.14: structured trust evidence (A2A #1628 compatible)
        },
        "auth":      {"schemes": ["none"]},
        "endpoints": {
            "send":         "/message:send",
            "stream":       "/stream",
            "tasks":        "/tasks",
            "agent_card":   "/.well-known/acp.json",
            "did_document": "/.well-known/did.json",   # v1.3: W3C DID Document (requires --identity)
            "skills_query": "/skills/query",
            "skills":       "/skills",                 # v2.10: structured skill list + filtering
            "skill_status": "/skills/{id}/status",     # v2.29: per-skill availability probe
            "peers":        "/peers",                  # v0.6
            "peer_send":    "/peer/{id}/send",         # v0.6
            "peers_connect": "/peers/connect",         # v0.6
            "discover":     "/discover",               # v0.7 mDNS LAN discovery
            "extensions":   "/extensions",             # v1.3: list/register extensions
            "verify_card":  "/verify/card",            # v1.8: verify any AgentCard self-signature
            "peer_verify":  "/peer/verify",            # v1.9: auto-verification result for connected peer
            "offline_queue": "/offline-queue",         # v2.0: inspect offline delivery queue
            "peers_discover": "/peers/discover",       # v2.1: TCP port-scan LAN discovery
            "peers_broadcast": "/peers/broadcast",              # v2.22: broadcast to all connected peers
            "peers_broadcast_history": "/peers/broadcast/history",  # v2.23: broadcast history
            "peer_card":               "/peers/{peer_id}/card",      # v2.24: GET cached AgentCard for peer
            "peer_ping":               "/peers/{peer_id}/ping",      # v2.25: POST liveness probe + RTT
            "peer_trust":              "/peers/{peer_id}/trust",     # v2.34: GET structured trust score for peer
            "peer_messages":           "/peers/{peer_id}/messages",  # v2.48: GET per-peer message history
            "peers_paginated":         "/peers?limit=&offset=&filter=",  # v2.27: paginated peer list
            "ws_stream":      "/ws/stream",            # v2.12: WebSocket native push stream
            "delegate":       "/identity/delegate",    # v2.16: POST — create signed delegation entry
            "delegation":        "/identity/delegation",          # v2.16: GET — query delegation chain
            "delegation_verify": "/identity/delegation/verify",  # v2.16: POST — verify a delegation entry
            "pubkey_discovery":  "/identity/pubkey-discovery",   # v2.33: GET|POST — resolve DID → Ed25519 pubkey (offline)
            "availability":   "/availability",          # v2.17: GET — full availability status
            "heartbeat":      "/availability/heartbeat", # v2.17: POST — stamp last_active_at + recompute next_active_at
            "jwks":           "/.well-known/jwks.json",  # v2.18: JWKS endpoint (RFC 7517) — public key set for Ed25519 identity
        },
    }
    # v0.9: inject capabilities.groups — structured grouping of flat capabilities (A2A v1.0 aligned)
    card["capabilities"]["groups"] = _build_capabilities_groups(card["capabilities"])

    # v1.2: attach availability block only when configured (opt-in)
    if _availability:
        card["availability"] = dict(_availability)  # shallow copy
        # auto-stamp last_active_at if not explicitly set
        if "last_active_at" not in card["availability"]:
            started = _status.get("started_at")
            if started and isinstance(started, (int, float)):
                card["availability"]["last_active_at"] = (
                    datetime.datetime.fromtimestamp(started, tz=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                )
            else:
                card["availability"]["last_active_at"] = _now()
        # v2.17: auto-compute next_active_at from CRON schedule if not explicitly set
        schedule = card["availability"].get("schedule")
        if schedule and not card["availability"].get("next_active_at"):
            nxt = _next_cron_datetime(schedule)
            if nxt:
                card["availability"]["next_active_at"] = nxt.strftime("%Y-%m-%dT%H:%M:%SZ")

    # v2.8: always include extensions field (empty list when none declared)
    # Auto-register built-in extensions based on runtime capabilities
    builtin_extensions = _make_builtin_extensions()
    # Merge: built-in first, then user-declared (deduplicate by URI)
    seen_uris = set()
    merged_extensions = []
    for ext in builtin_extensions + list(_extensions):
        uri = ext.get("uri", "")
        if uri and uri not in seen_uris:
            seen_uris.add(uri)
            merged_extensions.append(dict(ext))
    card["extensions"] = merged_extensions

    return card


def _build_capabilities_groups(caps: dict) -> dict:
    """
    v0.9: Build structured capabilities.groups from the flat capabilities dict.

    Groups map flat capabilities keys into named functional categories, aligned
    with A2A v1.0 AgentCapabilities structure.  The flat keys are preserved in
    the top-level capabilities dict for backward-compatibility; this adds an
    optional nested `groups` view.

    Group definitions:
      messaging  — message transport quality features
      tasks      — task lifecycle management features
      identity   — cryptographic identity & signing features
      transport  — protocol transport binding features
      discovery  — agent discovery & metadata features
    """
    groups: dict = {}

    # ── messaging ────────────────────────────────────────────────────────────
    groups["messaging"] = {
        "priority":      bool(caps.get("message_priority", False)),
        "long_poll":     bool(caps.get("recv_long_poll", False)),
        "history":       bool(caps.get("event_replay", False)),
        "broadcast":     bool(caps.get("peers_broadcast", False)),
        "delivery_ack":  bool(caps.get("delivery_ack", False)),
    }

    # ── tasks ─────────────────────────────────────────────────────────────────
    groups["tasks"] = {
        "pagination":    bool(caps.get("tasks_pagination", False)),
        "filtering":     bool(caps.get("tasks_pagination", False)),   # filtering ships with pagination
        "state_machine": bool(caps.get("task_cancelling", False)),    # cancelling state is part of state machine
    }

    # ── identity ──────────────────────────────────────────────────────────────
    identity_val = caps.get("identity", "none")
    groups["identity"] = {
        "hmac":           bool(caps.get("hmac_signing", False)),
        "ed25519":        identity_val in ("ed25519", "ed25519+ca"),
        "jwks":           bool(caps.get("trust_jwks", False)),
        "card_signature": bool(caps.get("card_sig", False)),
    }

    # ── transport ─────────────────────────────────────────────────────────────
    supported_transports = caps.get("supported_transports", [])
    groups["transport"] = {
        "sse":            bool(caps.get("sse_seq", False)),
        "http2":          bool(caps.get("http2", False)),
        "p2p_direct":     True,                                          # always true — ACP is P2P-first
        "dcutr":          "p2p" in caps.get("supported_transports", []) or bool(caps.get("lan_discovery", False)),
        "relay_fallback": True,                                          # relay fallback always supported
    }

    # ── discovery ─────────────────────────────────────────────────────────────
    groups["discovery"] = {
        "skills":                 bool(caps.get("query_skill", False)),
        "skills_openapi_spec":    bool(caps.get("skills_openapi_spec", False)),
        "limitations":            bool(caps.get("limitations_structured", False)),
        "availability_schedule":  bool(caps.get("availability_schedule", False)),
    }

    return groups


def _make_builtin_extensions() -> list:
    """
    v2.8: Auto-derive built-in extension declarations from runtime configuration.

    Returns a list of extension dicts for capabilities that are already active:
      - acp:ext:hmac-v1   — HMAC-SHA256 message signing (--secret)
      - acp:ext:mdns-v1   — mDNS LAN peer discovery (--advertise-mdns)
      - acp:ext:h2c-v1    — HTTP/2 cleartext transport (--http2)

    URI naming convention: acp:ext:<name>-v<version>
    External extensions use a full URL (https://…).
    """
    exts = []
    if _hmac_secret:
        exts.append({
            "uri":      "acp:ext:hmac-v1",
            "required": False,
            "params":   {"scheme": "hmac-sha256"},
        })
    if _mdns_running:
        exts.append({
            "uri":      "acp:ext:mdns-v1",
            "required": False,
            "params":   {},
        })
    if _http2_enabled:
        exts.append({
            "uri":      "acp:ext:h2c-v1",
            "required": False,
            "params":   {},
        })
    return exts


# ══════════════════════════════════════════════════════════════════════════════
# Trust Signals (v2.14) — A2A Issue #1628 compatible
# ══════════════════════════════════════════════════════════════════════════════

def _build_trust_signals() -> list:
    """
    Build trust.signals[] for the AgentCard (v2.14).

    Each signal is a dict:
      {
        "type":        str,   # signal category (see below)
        "enabled":     bool,  # whether this signal is currently active
        "description": str,   # human-readable explanation
        "details":     dict,  # optional type-specific metadata
      }

    Signal types:
      - "hmac_message_signing":   HMAC-SHA256 per-message signing (v0.7/v1.1)
      - "ed25519_identity":       Ed25519 keypair with DID (v0.8/v1.3)
      - "agent_card_signature":   AgentCard self-signed with Ed25519 key (v1.8)
      - "peer_card_verification": Auto-verify peer AgentCard on connect (v1.9)
      - "replay_window":          HMAC replay-window protection (v1.1)
      - "did_document":           W3C DID Document published (v1.3)

    Rationale (A2A #1628):
      A2A's trust.signals[] proposal aims to enumerate verifiable trust evidence in the
      AgentCard. ACP already implements most of these as concrete features; this field
      makes them discoverable in a structured, interoperable way.
    """
    signals = []

    # 1. HMAC-SHA256 per-message signing
    signals.append({
        "type":        "hmac_message_signing",
        "enabled":     bool(_hmac_secret),
        "description": "HMAC-SHA256 message signing (v0.7). Each message carries an `identity.sig` field signed with a shared secret.",
        "details":     {"algorithm": "hmac-sha256"} if _hmac_secret else {},
    })

    # 2. Ed25519 self-sovereign identity
    signals.append({
        "type":        "ed25519_identity",
        "enabled":     bool(_ed25519_private),
        "description": "Ed25519 keypair with self-sovereign DID (v0.8/v1.3). Identity is generated locally, never shared with a central authority.",
        "details": ({
            "scheme":  "ed25519+ca" if _ca_cert_pem else "ed25519",
            "did_acp": _did_acp,
            "did":     _did_key,
        } if _ed25519_private else {}),
    })

    # 3. AgentCard self-signature
    signals.append({
        "type":        "agent_card_signature",
        "enabled":     bool(_ed25519_private),
        "description": "AgentCard is self-signed with Ed25519 private key (v1.8). Receivers can verify card authenticity without a CA.",
        "details":     {"algorithm": "ed25519", "field": "identity.card_sig"} if _ed25519_private else {},
    })

    # 4. Auto peer AgentCard verification on connect
    signals.append({
        "type":        "peer_card_verification",
        "enabled":     True,   # always active (v1.9); verification result in /peer/verify
        "description": "Peer's AgentCard is automatically verified on connection (v1.9). Result available at GET /peer/verify.",
        "details":     {"endpoint": "/peer/verify"},
    })

    # 5. HMAC replay-window protection
    signals.append({
        "type":        "replay_window",
        "enabled":     bool(_hmac_secret),
        "description": "HMAC replay-window: messages with duplicate nonces within 60s window are dropped (v1.1).",
        "details":     {"window_seconds": 60} if _hmac_secret else {},
    })

    # 6. W3C DID Document
    signals.append({
        "type":        "did_document",
        "enabled":     bool(_did_acp),
        "description": "W3C DID Document published at /.well-known/did.json (v1.3). Contains Ed25519VerificationKey2020 and ACPRelay service endpoint.",
        "details":     {"endpoint": "/.well-known/did.json", "did": _did_acp} if _did_acp else {},
    })

    # 7. JWKS compatibility layer (v2.18)
    signals.append({
        "type":        "jwks",
        "enabled":     bool(_ed25519_private),
        "description": "Ed25519 public key published as JWK Set at /.well-known/jwks.json (v2.18, RFC 7517). Enables JWKS-based key discovery compatible with A2A IS#1628.",
        "jwks_uri":    "/.well-known/jwks.json",
        "alg":         "EdDSA",
        "details":     {"endpoint": "/.well-known/jwks.json", "alg": "EdDSA", "kty": "OKP", "crv": "Ed25519"} if _ed25519_private else {},
    })

    # 8. Vouch chain (v2.27) — structured trust endorsements from other agents (A2A IS#1628 compatible)
    signals.append({
        "type":        "vouch_chain",
        "enabled":     len(_vouch_chain) > 0,
        "description": "Vouch chain: structured endorsements from other agents (v2.27). Compatible with A2A IS#1628 trust.signals specification.",
        "details":     {
            "count":   len(_vouch_chain),
            "endpoint": "/trust/vouch",
            "vouches":  _vouch_chain[-5:],  # expose last 5 for compactness in AgentCard
        },
    })

    return signals


# ── v2.18: JWKS helpers ────────────────────────────────────────────────────────

def _build_jwks(agent_name: str = "ACP-Agent") -> dict:
    """
    Build a JWK Set (RFC 7517) from the ACP Ed25519 identity (v2.18).

    Returns a standard JWKS dict:
      {
        "keys": [
          {
            "kty": "OKP",
            "crv": "Ed25519",
            "x":   "<base64url-encoded 32-byte public key>",
            "use": "sig",
            "alg": "EdDSA",
            "kid": "<agent_name>:<pubkey_prefix_8chars>"
          }
        ]
      }

    If no Ed25519 identity is loaded (--identity not provided), returns {"keys": []}.

    Notes:
      - Only the public key is included; the private key is NEVER exported.
      - 'x' is the raw 32-byte Ed25519 public key encoded as base64url (no padding).
      - 'kid' is derived from agent_name and first 8 chars of the base64url pubkey.
      - The endpoint is unauthenticated (well-known public key discovery).

    Test IDs: JW1 ~ JW6
    """
    if not _ed25519_private or not _ed25519_public_b64:
        return {"keys": []}

    # kid = "<agent_name>:<pubkey_prefix>" — first 8 chars of base64url pubkey
    kid = f"{agent_name}:{_ed25519_public_b64[:8]}"

    jwk = {
        "kty": "OKP",
        "crv": "Ed25519",
        "x":   _ed25519_public_b64,   # raw 32-byte pubkey, base64url no-padding
        "use": "sig",
        "alg": "EdDSA",
        "kid": kid,
    }
    return {"keys": [jwk]}


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

        # Optionally verify did:key: or did:acp: matches public_key
        did_consistent = None
        if did and did.startswith("did:key:"):
            expected_did = _pubkey_to_did_key(pub_raw)
            did_consistent = (did == expected_did)
        elif did and did.startswith("did:acp:"):
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

_DEDUP_WINDOW_SECONDS = 30  # v2.32: 30s TTL dedup window for HTTP send endpoints

def _check_and_record_message_id(message_id):
    """Returns True if new (process), False if duplicate (skip). Used for WS inbound messages."""
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


def _http_dedup_check(message_id):
    """
    v2.32 — HTTP send endpoint idempotency check with 30s TTL window.

    Returns (is_duplicate: bool, cached_server_seq: int | None).
    - If message_id already seen within _DEDUP_WINDOW_SECONDS: (True, server_seq)
    - Otherwise records and returns (False, None).
    - message_id=None always returns (False, None) — no-id sends are never deduped.

    Thread-safe: uses _seen_message_ids dict (GIL-protected for CPython).
    Expired entries are evicted lazily during check.
    """
    if not message_id:
        return False, None

    now = time.time()
    entry = _seen_message_ids.get(message_id)
    if entry:
        age = now - entry.get("wall_ts", 0)
        if age <= _DEDUP_WINDOW_SECONDS:
            _status["messages_deduped"] += 1
            log.info(f"[dedup] Duplicate HTTP message_id={message_id} (age={age:.1f}s), returning cached response")
            return True, entry.get("server_seq")
        # Expired — fall through to record fresh

    # Evict expired entries lazily (keep dict bounded)
    expired = [mid for mid, e in _seen_message_ids.items()
               if now - e.get("wall_ts", 0) > _DEDUP_WINDOW_SECONDS]
    for mid in expired:
        del _seen_message_ids[mid]
    # Hard cap fallback
    if len(_seen_message_ids) > _SEEN_MAX:
        oldest = next(iter(_seen_message_ids))
        del _seen_message_ids[oldest]

    _seen_message_ids[message_id] = {"ts": _now(), "wall_ts": now, "server_seq": None}
    return False, None


def _http_dedup_record_seq(message_id, server_seq):
    """After assigning server_seq, store it in the dedup cache for replay responses."""
    if message_id and message_id in _seen_message_ids:
        _seen_message_ids[message_id]["server_seq"] = server_seq


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

    v2.3: every event carries a monotonically-increasing `seq` field so that
    consumers can detect out-of-order or missed events without relying on
    wall-clock timestamps.  The SSE wire format also uses a named event line:
      event: acp.task.status   (for type=status)
      event: acp.task.artifact (for type=artifact)
    All other types continue to arrive as unnamed data-only events.
    """
    global _sse_seq
    with _sse_seq_lock:
        _sse_seq += 1
        seq = _sse_seq
    event = {"type": event_type, "ts": _now(), "seq": seq, **payload}
    # v2.13: append to replay log (ring buffer)
    with _event_log_lock:
        _event_log.append(event)
        if len(_event_log) > _EVENT_LOG_MAX:
            del _event_log[0]
    for q in _sse_subscribers:
        q.append(event)
    _sse_notify.set()   # BUG-009 fix: wake up SSE polling handlers immediately
    # v2.12: also broadcast to WebSocket /ws/stream clients
    _broadcast_ws_stream_event(event_type, event)


# v2.3: SSE event type → named SSE event field mapping.
# Consumers can filter by event name using EventSource.addEventListener('acp.task.status', ...).
_SSE_EVENT_NAMES = {
    "status":   "acp.task.status",
    "artifact": "acp.task.artifact",
}


def _sse_format(evt: dict) -> bytes:
    """
    Serialize a single SSE event dict to wire bytes (v2.3).

    For task status/artifact events, emits a named `event:` line:
      event: acp.task.status\ndata: {...}\n\n
      event: acp.task.artifact\ndata: {...}\n\n
    All other event types (message, peer, mdns...) use the plain data-only form:
      data: {...}\n\n
    """
    event_name = _SSE_EVENT_NAMES.get(evt.get("type", ""))
    data_line = f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
    if event_name:
        return f"event: {event_name}\n{data_line}".encode()
    return data_line.encode()
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
# WebSocket /ws/stream native push (v2.12)
# ══════════════════════════════════════════════════════════════════════════════

def _ws_handshake(handler):
    """
    Perform a RFC 6455 WebSocket upgrade handshake on an HTTP handler.
    Returns the raw socket on success, raises on failure.

    Steps:
      1. Read Sec-WebSocket-Key from headers
      2. Compute accept key = base64(SHA1(key + magic))
      3. Send 101 Switching Protocols response (MUST be HTTP/1.1)

    Note: BaseHTTPRequestHandler.send_response() uses HTTP/1.0 by default.
    We write the 101 response directly as raw bytes to ensure HTTP/1.1.
    """
    import hashlib as _hashlib
    import base64 as _base64_mod

    key = handler.headers.get("Sec-WebSocket-Key", "").strip()
    if not key:
        handler.send_response(400)
        handler.end_headers()
        raise ValueError("Missing Sec-WebSocket-Key")

    magic = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
    accept = _base64_mod.b64encode(
        _hashlib.sha1((key + magic).encode()).digest()
    ).decode()

    # Write HTTP/1.1 101 response directly (bypass BaseHTTPRequestHandler
    # which defaults to HTTP/1.0; websockets library requires HTTP/1.1)
    response = (
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {accept}\r\n"
        "\r\n"
    )
    handler.wfile.write(response.encode())
    handler.wfile.flush()
    return handler.connection


def _ws_send_frame(sock, data: str):
    """
    Send a WebSocket text frame (opcode 0x1) over a raw socket.
    Uses a simple unmasked frame (server→client frames are unmasked per RFC 6455).
    """
    payload = data.encode("utf-8")
    length = len(payload)
    header = bytearray()
    header.append(0x81)  # FIN=1, opcode=text(1)
    if length < 126:
        header.append(length)
    elif length < 65536:
        header.append(126)
        header += length.to_bytes(2, "big")
    else:
        header.append(127)
        header += length.to_bytes(8, "big")
    sock.sendall(bytes(header) + payload)


def _ws_recv_frame(sock):
    """
    Receive a single WebSocket frame from client.
    Returns (opcode, payload_bytes) or raises on close/error.
    Handles masking (client→server frames are always masked per RFC 6455).
    """
    # Read first 2 bytes
    header = b""
    while len(header) < 2:
        chunk = sock.recv(2 - len(header))
        if not chunk:
            raise ConnectionResetError("WS connection closed")
        header += chunk

    fin   = (header[0] & 0x80) != 0
    opcode = header[0] & 0x0F
    masked = (header[1] & 0x80) != 0
    length = header[1] & 0x7F

    if length == 126:
        lb = b""
        while len(lb) < 2:
            lb += sock.recv(2 - len(lb))
        length = int.from_bytes(lb, "big")
    elif length == 127:
        lb = b""
        while len(lb) < 8:
            lb += sock.recv(8 - len(lb))
        length = int.from_bytes(lb, "big")

    mask_key = b""
    if masked:
        while len(mask_key) < 4:
            mask_key += sock.recv(4 - len(mask_key))

    payload = b""
    while len(payload) < length:
        chunk = sock.recv(length - len(payload))
        if not chunk:
            raise ConnectionResetError("WS connection closed during payload")
        payload += chunk

    if masked:
        payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))

    return opcode, payload


class _WsStreamClient:
    """Wrapper around a raw socket for a /ws/stream subscriber."""
    def __init__(self, sock):
        self._sock = sock
        self._lock = threading.Lock()
        self.closed = False

    def send(self, data: str):
        if self.closed:
            return
        try:
            with self._lock:
                _ws_send_frame(self._sock, data)
        except Exception:
            self.closed = True

    def close(self):
        self.closed = True
        try:
            self._sock.close()
        except Exception:
            pass


def _broadcast_ws_stream_event(event_type: str, event: dict):
    """
    v2.12: Broadcast a typed event to all /ws/stream WebSocket subscribers.

    Maps ACP event types to WS event names:
      message → acp.message
      peer    → acp.peer
      status  → acp.task.status
      artifact→ acp.task.artifact
      *       → acp.<type>
    """
    _WS_EVENT_NAMES = {
        "message":  "acp.message",
        "peer":     "acp.peer",
        "status":   "acp.task.status",
        "artifact": "acp.task.artifact",
    }
    ws_event_name = _WS_EVENT_NAMES.get(event_type, f"acp.{event_type}")

    # Build the WS push payload
    # For message events, reshape data to match spec:
    # { event, data: { message_id, from, parts, timestamp, server_seq } }
    if event_type == "message":
        ws_payload = json.dumps({
            "event": ws_event_name,
            "data": {
                "message_id": event.get("message_id"),
                "from":       event.get("role", "agent"),
                "parts":      event.get("parts", []),
                "timestamp":  event.get("ts"),
                "server_seq": event.get("seq"),
            }
        }, ensure_ascii=False)
    else:
        ws_payload = json.dumps({
            "event": ws_event_name,
            "data":  event,
        }, ensure_ascii=False)

    dead = set()
    with _ws_stream_lock:
        clients = set(_ws_stream_clients)

    for client in clients:
        client.send(ws_payload)
        if client.closed:
            dead.add(client)

    if dead:
        with _ws_stream_lock:
            _ws_stream_clients.difference_update(dead)


def _handle_ws_stream(handler):
    """
    v2.12/v2.13: Handle a /ws/stream WebSocket connection lifecycle.
    Called from do_GET when path == /ws/stream and Upgrade: websocket.
    Runs in the ThreadingHTTPServer worker thread for this connection.

    v2.13: supports ?since=<seq> for missed-event replay on reconnect.
    """
    try:
        sock = _ws_handshake(handler)
    except Exception as e:
        log.warning(f"/ws/stream handshake failed: {e}")
        return

    # v2.13: parse ?since=<seq> from request path before completing handshake
    since_seq = None
    try:
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(handler.path).query)
        since_seq = int(qs.get("since", [None])[0])
    except (TypeError, ValueError):
        pass

    client = _WsStreamClient(sock)
    with _ws_stream_lock:
        _ws_stream_clients.add(client)

    # v2.13: replay missed events before joining live stream
    if since_seq is not None:
        with _event_log_lock:
            replay = [e for e in _event_log if e.get("seq", 0) > since_seq]
        for evt in replay:
            event_type = evt.get("type", "message")
            ws_evt = {"event": f"acp.{event_type}", "data": evt}
            try:
                client.send(json.dumps(ws_evt, ensure_ascii=False))
            except Exception:
                break

    log.info(f"/ws/stream client connected (total={len(_ws_stream_clients)})")

    try:
        # Keep-alive loop: read frames from client (handle ping/close)
        # We don't need to process client→server data, just detect disconnects
        sock.settimeout(60.0)
        while not client.closed:
            try:
                opcode, payload = _ws_recv_frame(sock)
                if opcode == 0x8:  # close frame
                    break
                elif opcode == 0x9:  # ping → pong
                    _ws_send_frame(sock, "")  # minimal pong (opcode 0xA)
                    # Actually send proper pong
                    pong = bytearray([0x8A, len(payload)]) + payload
                    sock.sendall(bytes(pong))
                # ignore text/binary frames from client
            except OSError:
                break
    except Exception:
        pass
    finally:
        client.close()
        with _ws_stream_lock:
            _ws_stream_clients.discard(client)
        log.info(f"/ws/stream client disconnected (total={len(_ws_stream_clients)})")


# ══════════════════════════════════════════════════════════════════════════════
# Task helpers
# ══════════════════════════════════════════════════════════════════════════════

# ── v2.50: param_constraints helpers ─────────────────────────────────────────

_VALID_CONSTRAINT_TYPES = {"string", "number", "integer", "boolean", "array"}

def _parse_param_constraints(raw: dict) -> dict:
    """Normalise a param_constraints dict.

    Input: {param_name: rule_dict, ...}
    Each rule_dict may contain: type, required, min, max, allowed_values, pattern.
    Unknown rule fields are silently dropped (forward-compat).
    Returns the normalised dict; invalid top-level (non-dict) returns {}.
    """
    import re as _re
    if not isinstance(raw, dict):
        return {}
    result = {}
    for param, rule in raw.items():
        if not isinstance(rule, dict):
            continue
        norm: dict = {}
        if "type" in rule and rule["type"] in _VALID_CONSTRAINT_TYPES:
            norm["type"] = rule["type"]
        if "required" in rule:
            norm["required"] = bool(rule["required"])
        if "min" in rule and isinstance(rule["min"], (int, float)):
            norm["min"] = rule["min"]
        if "max" in rule and isinstance(rule["max"], (int, float)):
            norm["max"] = rule["max"]
        if "allowed_values" in rule and isinstance(rule["allowed_values"], list):
            norm["allowed_values"] = list(rule["allowed_values"])
        if "pattern" in rule and isinstance(rule["pattern"], str):
            # Pre-validate regex
            try:
                _re.compile(rule["pattern"])
                norm["pattern"] = rule["pattern"]
            except _re.error:
                pass  # invalid pattern silently dropped
        if norm:
            result[param] = norm
    return result or None


def _check_param_constraints(skill_id: str | None, params: dict | None) -> tuple[bool, list]:
    """v2.50: Validate task params against skill.param_constraints.

    Returns (ok: bool, violations: list[str]).
    ok=True means params satisfy all declared constraints (or no constraints declared).
    violations is populated only when ok=False; each entry is a human-readable description.
    """
    import re as _re
    if not skill_id or not params:
        # No skill_id or no params → nothing to validate
        # (required fields checked separately below if skill known)
        pass

    # Look up skill
    skills = (_status.get("agent_card") or {}).get("skills", [])
    skill_obj = next((s for s in skills if isinstance(s, dict) and s.get("id") == skill_id), None)
    if not skill_obj:
        return True, []  # Unknown skill → no constraints to enforce

    pc = skill_obj.get("param_constraints")
    if not pc:
        return True, []  # No param_constraints declared → always allowed

    params = params or {}
    violations = []

    for param_name, rule in pc.items():
        value = params.get(param_name)
        present = param_name in params

        # required check
        if rule.get("required") and not present:
            violations.append(f"param '{param_name}' is required but missing")
            continue

        if not present:
            continue  # optional and absent — skip remaining checks

        # type check
        expected_type = rule.get("type")
        if expected_type:
            type_ok = True
            if expected_type == "string":
                type_ok = isinstance(value, str)
            elif expected_type == "number":
                type_ok = isinstance(value, (int, float)) and not isinstance(value, bool)
            elif expected_type == "integer":
                type_ok = isinstance(value, int) and not isinstance(value, bool)
            elif expected_type == "boolean":
                type_ok = isinstance(value, bool)
            elif expected_type == "array":
                type_ok = isinstance(value, list)
            if not type_ok:
                violations.append(
                    f"param '{param_name}': expected type {expected_type}, "
                    f"got {type(value).__name__}"
                )
                continue  # skip further checks for wrong-typed value

        # min / max
        if "min" in rule or "max" in rule:
            # numeric: compare value; string/array: compare length
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                comparable = value
            elif isinstance(value, (str, list)):
                comparable = len(value)
            else:
                comparable = None

            if comparable is not None:
                if "min" in rule and comparable < rule["min"]:
                    violations.append(
                        f"param '{param_name}': value {comparable} < min {rule['min']}"
                    )
                if "max" in rule and comparable > rule["max"]:
                    violations.append(
                        f"param '{param_name}': value {comparable} > max {rule['max']}"
                    )

        # allowed_values (enum check)
        if "allowed_values" in rule and value not in rule["allowed_values"]:
            violations.append(
                f"param '{param_name}': value {value!r} not in allowed_values "
                f"{rule['allowed_values']}"
            )

        # pattern (string only)
        if "pattern" in rule and isinstance(value, str):
            if not _re.fullmatch(rule["pattern"], value):
                violations.append(
                    f"param '{param_name}': value {value!r} does not match "
                    f"pattern {rule['pattern']!r}"
                )

    ok = len(violations) == 0
    return ok, violations


# ---------------------------------------------------------------------------
# v2.53: skill.rate_limit — per-skill / per-peer in-memory rate-limit buckets
# ---------------------------------------------------------------------------
# Bucket key: (skill_id, peer_id)  (peer_id may be None → treat as "anonymous")
# Each bucket stores:
#   {
#     "min_count":   int,   # requests in current 1-minute window
#     "day_count":   int,   # requests in current 1-day window
#     "min_start":   float, # epoch seconds of current minute window start
#     "day_start":   float, # epoch seconds of current day window start
#     "burst_queue": int,   # tokens consumed out of burst allowance this window
#   }
_rl_buckets: dict[tuple, dict] = {}


def _parse_rate_limit(raw: object) -> dict | None:
    """v2.53: Parse and normalise a raw rate_limit field from an AgentCard skill object.

    Accepts a dict with any subset of:
      requests_per_minute (int, ≥1)
      requests_per_day    (int, ≥1)
      burst               (int, ≥0) — extra requests allowed to absorb short spikes;
                                       burst tokens refill every minute alongside the normal window

    All fields are optional.  Returns None if raw is falsy or contains no valid limits.
    Invalid values (non-int, ≤0) are silently clamped / dropped (forward-compat).
    """
    if not isinstance(raw, dict):
        return None
    rpm = raw.get("requests_per_minute")
    rpd = raw.get("requests_per_day")
    burst = raw.get("burst")
    result: dict = {}
    if isinstance(rpm, (int, float)) and int(rpm) >= 1:
        result["requests_per_minute"] = int(rpm)
    if isinstance(rpd, (int, float)) and int(rpd) >= 1:
        result["requests_per_day"] = int(rpd)
    if isinstance(burst, (int, float)) and int(burst) >= 0:
        result["burst"] = int(burst)
    return result if result else None


def _check_rate_limit(skill_id: str | None, peer_id: str | None) -> tuple[bool, dict]:
    """v2.53: Check and update rate-limit counters for (skill_id, peer_id).

    Returns (allowed: bool, detail: dict).
      allowed=True  → request is within rate limits; counters have been incremented.
      allowed=False → request exceeds a configured limit; detail contains limit/reset info.

    Looks up the skill's rate_limit config from _status["agent_card"].skills[].
    No skill / no rate_limit config → always allowed (backward-compatible).

    Limits are enforced in order: requests_per_minute → requests_per_day.
    burst tokens extend requests_per_minute only (not requests_per_day).
    """
    if not skill_id:
        return True, {}
    # Look up skill's rate_limit config
    card_skills = (_status.get("agent_card") or {}).get("skills", [])
    skill_obj   = next((s for s in card_skills if isinstance(s, dict) and s.get("id") == skill_id), {})
    rl = skill_obj.get("rate_limit")  # already parsed by _parse_skill_obj → dict or None
    if not rl:
        return True, {}

    now = time.time()
    key = (skill_id, peer_id)
    if key not in _rl_buckets:
        _rl_buckets[key] = {
            "min_count":   0,
            "day_count":   0,
            "min_start":   now,
            "day_start":   now,
            "burst_used":  0,
        }
    bkt = _rl_buckets[key]

    # --- reset windows if expired ---
    if now - bkt["min_start"] >= 60:
        bkt["min_count"]  = 0
        bkt["min_start"]  = now
        bkt["burst_used"] = 0
    if now - bkt["day_start"] >= 86400:
        bkt["day_count"] = 0
        bkt["day_start"] = now

    rpm   = rl.get("requests_per_minute")
    rpd   = rl.get("requests_per_day")
    burst = rl.get("burst", 0)

    # --- check requests_per_minute (with burst) ---
    if rpm is not None:
        effective_limit = rpm + burst
        if bkt["min_count"] >= effective_limit:
            reset_in = max(0, int(60 - (now - bkt["min_start"])))
            return False, {
                "limit_type":        "requests_per_minute",
                "limit":             rpm,
                "burst":             burst,
                "effective_limit":   effective_limit,
                "current_count":     bkt["min_count"],
                "reset_in_seconds":  reset_in,
                "skill_id":          skill_id,
                "peer_id":           peer_id,
            }

    # --- check requests_per_day ---
    if rpd is not None:
        if bkt["day_count"] >= rpd:
            reset_in = max(0, int(86400 - (now - bkt["day_start"])))
            return False, {
                "limit_type":       "requests_per_day",
                "limit":            rpd,
                "current_count":    bkt["day_count"],
                "reset_in_seconds": reset_in,
                "skill_id":         skill_id,
                "peer_id":          peer_id,
            }

    # --- within limits: increment counters ---
    bkt["min_count"] += 1
    bkt["day_count"] += 1
    # track burst usage if we exceeded base rpm but had burst tokens
    if rpm is not None and bkt["min_count"] > rpm:
        bkt["burst_used"] += 1

    return True, {}


def _check_authorization_tier(skill_id: str | None, peer_id: str | None) -> tuple[bool, str]:
    """v2.49: Check whether the calling peer satisfies the skill's authorization_tier requirement.

    Returns (allowed: bool, reason: str).
    - allowed=True  → proceed with task creation
    - allowed=False → caller does not meet tier requirements; include reason in 403 response

    Tier requirements:
      T0 / T1 / None  — always allowed (auto-execute, low-risk)
      T2              — requires caller trust_score >= 0.7
      T3              — requires caller trust_score >= 0.9 AND trust.signals contains
                        at least one signal of type "verified_identity"

    Graceful degradation:
      - If skill_id is None or skill not found: allowed (unknown skill → no tier enforcement)
      - If peer_id is None or peer not found: allowed for T0/T1, denied for T2/T3
        (unknown caller cannot meet elevated tier requirements by definition)
    """
    if not skill_id:
        return True, "no skill_id specified"

    # look up skill in AgentCard
    agent_card = _status.get("agent_card") or {}
    all_skills = agent_card.get("skills", [])
    skill_obj = None
    for s in all_skills:
        if isinstance(s, dict) and s.get("id") == skill_id:
            skill_obj = s
            break

    if skill_obj is None:
        return True, f"skill '{skill_id}' not found in agent card"

    tier = skill_obj.get("authorization_tier")
    if tier is None or tier in ("T0", "T1"):
        return True, f"tier {tier!r} — auto-execute"

    # T2 or T3 — need peer trust score
    if not peer_id or peer_id not in _peers:
        return False, (f"skill '{skill_id}' requires tier {tier} but caller peer is unknown; "
                       f"connect via /peers/connect first")

    pinfo = _peers[peer_id]

    # --- compute trust score (mirrors GET /peers/<id>/trust logic) ---
    vr = pinfo.get("card_verification") or {}
    card_sig_score       = 1.0 if vr.get("valid") else 0.0
    did_consistent_score = 1.0 if vr.get("did_consistent") else (0.5 if vr.get("valid") else 0.0)

    msgs = pinfo.get("messages_sent", 0) + pinfo.get("messages_received", 0)
    msg_score = (1.0 if msgs > 100 else 0.7 if msgs > 20 else 0.4 if msgs > 5 else 0.2 if msgs > 0 else 0.0)

    rtt = pinfo.get("last_ping_rtt_ms")
    ping_score = (1.0 if rtt is not None and rtt < 50 else
                  0.7 if rtt is not None and rtt < 200 else
                  0.4 if rtt is not None and rtt < 500 else
                  0.1 if rtt is not None else 0.0)

    peer_did = (pinfo.get("agent_card") or {}).get("did") or ""
    # _vouch_chain is a list of {voucher_did, vouched_did, vouched_at, sig, comment}
    vouch_score = 0.0
    if peer_did and _vouch_chain:
        for v in _vouch_chain:
            if v.get("vouched_did") == peer_did:
                vouch_score = 1.0
                break

    weights = {"card_sig": 0.35, "did_consistent": 0.20,
               "ping_rtt": 0.20, "message_hist": 0.15, "vouch": 0.10}
    raw = {"card_sig": card_sig_score, "did_consistent": did_consistent_score,
           "ping_rtt": ping_score, "message_hist": msg_score, "vouch": vouch_score}
    trust_score = round(sum(raw[k] * weights[k] for k in weights), 4)

    if tier == "T2":
        if trust_score >= 0.7:
            return True, f"T2 satisfied: trust_score={trust_score:.3f} >= 0.7"
        return False, (f"skill '{skill_id}' requires tier T2 (trust_score >= 0.7); "
                       f"caller trust_score={trust_score:.3f}")

    if tier == "T3":
        if trust_score < 0.9:
            return False, (f"skill '{skill_id}' requires tier T3 (trust_score >= 0.9); "
                           f"caller trust_score={trust_score:.3f}")
        # also check for verified_identity signal in peer's AgentCard
        peer_card  = pinfo.get("agent_card") or {}
        peer_trust = peer_card.get("trust") or {}
        peer_sigs  = peer_trust.get("signals") or []
        has_verified_identity = any(
            (sig.get("type") == "verified_identity" or sig.get("kind") == "verified_identity")
            for sig in peer_sigs
        )
        if not has_verified_identity:
            return False, (f"skill '{skill_id}' requires tier T3: caller lacks "
                           f"'verified_identity' trust signal (trust_score={trust_score:.3f})")
        return True, f"T3 satisfied: trust_score={trust_score:.3f}, verified_identity signal present"

    return True, f"unknown tier {tier!r} — defaulting to allow"


def _needs_human_confirmation(skill_id: str | None) -> bool:
    """v2.51: Return True if this skill requires human confirmation before execution.

    Conditions (all must hold):
      1. skill.human_confirmation_required == True
      2. skill.authorization_tier == "T3"
      3. --auto-confirm-t3 flag is NOT set
    """
    if _auto_confirm_t3:
        return False
    if not skill_id:
        return False
    skills = (_status.get("agent_card") or {}).get("skills", [])
    skill_obj = next((s for s in skills if isinstance(s, dict) and s.get("id") == skill_id), None)
    if not skill_obj:
        return False
    return (
        bool(skill_obj.get("human_confirmation_required"))
        and skill_obj.get("authorization_tier") == "T3"
    )


def _append_audit(task: dict, event_type: str, detail: dict | None = None):
    """v2.52: Append an immutable audit entry to task['audit_log'].

    Each entry: {"event": str, "ts": ISO-8601, "seq": int, "detail": dict}
    The audit_log is append-only — entries are never removed or modified.
    """
    log_list = task.setdefault("audit_log", [])
    entry = {
        "event": event_type,
        "ts":    _now(),
        "seq":   len(log_list),
    }
    if detail:
        entry["detail"] = detail
    log_list.append(entry)


def _create_task(payload, message_id=None, task_id=None, context_id=None, initial_state=None):
    # BUG-006 fix: honour client-supplied task_id (idempotent — return existing if already known)
    if task_id and task_id in _tasks:
        return _tasks[task_id]
    task_id = task_id or _make_id("task")
    # v2.51: allow initial_state override (e.g. confirmation_pending for T3 human-confirmation)
    state = initial_state if initial_state in (
        TASK_SUBMITTED, TASK_CONFIRMATION_PENDING
    ) else TASK_SUBMITTED
    now_ts = _now()
    task = {
        "id":         task_id,
        "status":     state,
        "created_at": now_ts,
        "updated_at": now_ts,
        "payload":    payload,
        "artifacts":  [],
        "history":    [],
        "audit_log":  [],          # v2.52: immutable audit trail — append-only
    }
    if message_id:
        task["origin_message_id"] = message_id
    if context_id:
        task["context_id"] = context_id
    if state == TASK_CONFIRMATION_PENDING:
        task["confirmation_required"] = True  # v2.51: flag for callers
    # v2.52: seed audit_log with creation event
    _append_audit(task, "created", {"initial_status": state})
    _tasks[task_id] = task
    _status["tasks_created"] += 1
    evt: dict = {"task_id": task_id, "state": state}
    if context_id:
        evt["context_id"] = context_id
    if state == TASK_CONFIRMATION_PENDING:
        evt["confirmation_required"] = True
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

    # v2.52: record state transition in audit_log
    if state != old_state:
        audit_detail: dict = {"from": old_state, "to": state}
        if error:
            audit_detail["error"] = error
        _append_audit(task, "status_changed", audit_detail)

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
        # BUG-037 fix: store remote agent_name in peer registry so that
        # messages_received counter can match by agent_name (not peer_id).
        # Find the most-recently connected peer that has no agent_name yet,
        # or update an existing peer whose agent_name matches peer_name.
        if peer_name and peer_name != "?":
            matched = False
            for pinfo in _peers.values():
                if pinfo.get("agent_name") == peer_name:
                    matched = True
                    pinfo["agent_card"] = card      # v2.24: cache card in peer registry
                    break
            if not matched:
                # Assign to the newest connected peer without an agent_name
                candidates = [p for p in _peers.values()
                              if p.get("connected") and not p.get("agent_name")]
                if candidates:
                    newest = max(candidates, key=lambda p: p.get("connected_at") or 0)
                    newest["agent_name"] = peer_name
                    newest["agent_card"] = card     # v2.24: cache card in peer registry
        else:
            # peer_name unknown — cache card on newest connected peer without a card
            candidates = [p for p in _peers.values()
                          if p.get("connected") and p.get("agent_card") is None]
            if candidates:
                newest = max(candidates, key=lambda p: p.get("connected_at") or 0)
                newest["agent_card"] = card         # v2.24: best-effort cache
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

    # v2.25: acp.ping — remote peer is probing us; respond with acp.pong
    if msg_type == "acp.ping":
        nonce = msg.get("nonce", "")
        pong_msg = json.dumps({
            "type":       "acp.pong",
            "nonce":      nonce,
            "from":       _status.get("agent_name", "ACP-Agent"),
            "ts":         _now(),
        }, ensure_ascii=False)
        # Send pong back on the same WS channel (find the ws for the sender)
        _from = msg.get("from", "")
        sender_ws = None
        for pinfo in _peers.values():
            if pinfo.get("connected") and (
                pinfo.get("agent_name") == _from or pinfo.get("name") == _from
            ):
                sender_ws = pinfo.get("ws")
                break
        if sender_ws is None:
            # Fallback: try the global _ws_ctx (single-peer scenario)
            sender_ws = _ws_ctx
        if sender_ws:
            try:
                asyncio.ensure_future(sender_ws.send(pong_msg))
            except Exception as ping_err:
                log.warning(f"[ping] Failed to send pong to {_from}: {ping_err}")
        log.debug(f"[ping] Received acp.ping from {_from}, nonce={nonce} — pong sent")
        return

    # v2.25: acp.pong — we sent a ping, peer is responding; resolve the pending Future
    if msg_type == "acp.pong":
        nonce = msg.get("nonce", "")
        fut = _pending_pongs.get(nonce)
        if fut and not fut.done():
            _loop.call_soon_threadsafe(fut.set_result, msg)
        log.debug(f"[ping] Received acp.pong nonce={nonce}")
        return

    if msg_type == "task.updated":
        task_id = msg.get("task_id")
        if task_id and task_id in _tasks:
            _update_task(task_id, msg.get("status", TASK_WORKING), artifact=msg.get("artifact"))
        return

    # v2.35: acp.delivered — peer ACK: they received our message; update delivery counters
    if msg_type == "acp.delivered":
        acked_id = msg.get("message_id")
        _from_ack = msg.get("from", "")
        _status["messages_delivered"] = _status.get("messages_delivered", 0) + 1
        # Credit the sending peer's delivery counter
        credited_ack = False
        for pinfo in _peers.values():
            if (pinfo.get("agent_name") == _from_ack
                    or pinfo.get("name") == _from_ack
                    or pinfo.get("id") == _from_ack):
                pinfo["messages_delivered"] = pinfo.get("messages_delivered", 0) + 1
                credited_ack = True
                break
        if not credited_ack:
            connected_ack = [p for p in _peers.values() if p.get("connected")]
            if len(connected_ack) == 1:
                connected_ack[0]["messages_delivered"] = connected_ack[0].get("messages_delivered", 0) + 1
        log.debug(f"[delivery_ack] Received acp.delivered from={_from_ack} acked_id={acked_id}")
        return

    # v2.36: acp.read — peer ACK: they have read/consumed our message; update read counters
    if msg_type == "acp.read":
        read_id = msg.get("message_id")
        _from_read = msg.get("from", "")
        _status["messages_read"] = _status.get("messages_read", 0) + 1
        # Credit the sending peer's read counter
        credited_read = False
        for pinfo in _peers.values():
            if (pinfo.get("agent_name") == _from_read
                    or pinfo.get("name") == _from_read
                    or pinfo.get("id") == _from_read):
                pinfo["messages_read"] = pinfo.get("messages_read", 0) + 1
                credited_read = True
                break
        if not credited_read:
            connected_read = [p for p in _peers.values() if p.get("connected")]
            if len(connected_read) == 1:
                connected_read[0]["messages_read"] = connected_read[0].get("messages_read", 0) + 1
        log.debug(f"[read_receipt] Received acp.read from={_from_read} read_id={read_id}")
        return

    # v2.37: acp.typing — peer is typing (or stopped typing); update state + broadcast SSE
    if msg_type == "acp.typing":
        _typing_val  = msg.get("typing", True)   # True = started, False = stopped
        _from_typing = msg.get("from", "")
        _ts_typing   = msg.get("ts") or _now()
        # Update global peer_typing state
        _status["peer_typing"]       = bool(_typing_val)
        _status["peer_typing_since"] = _ts_typing if _typing_val else None
        # Update per-peer typing field
        for pinfo in _peers.values():
            if (pinfo.get("agent_name") == _from_typing
                    or pinfo.get("name") == _from_typing
                    or pinfo.get("id") == _from_typing):
                pinfo["typing"]       = bool(_typing_val)
                pinfo["typing_since"] = _ts_typing if _typing_val else None
                break
        else:
            _conn_typing = [p for p in _peers.values() if p.get("connected")]
            if len(_conn_typing) == 1:
                _conn_typing[0]["typing"]       = bool(_typing_val)
                _conn_typing[0]["typing_since"] = _ts_typing if _typing_val else None
        # Broadcast SSE so local subscribers can show "peer is typing…"
        _broadcast_sse_event("typing", {
            "from":         _from_typing,
            "typing":       bool(_typing_val),
            "typing_since": _ts_typing if _typing_val else None,
        })
        log.debug(f"[typing] peer={_from_typing} typing={_typing_val}")
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
        # BUG-037 fix: match by agent_name (stored at acp.agent_card handshake).
        # Lazy-bind: if no peer has agent_name yet (timing race between HTTP relay
        # and P2P channel — acp.agent_card may arrive before peer is registered),
        # bind _from to the newest connected peer without an agent_name, then credit it.
        _from = msg.get("from", "")
        credited = False
        for pid, pinfo in _peers.items():
            if (pinfo.get("agent_name") == _from
                    or pinfo.get("name") == _from
                    or pinfo.get("id") == _from):
                pinfo["messages_received"] = pinfo.get("messages_received", 0) + 1
                credited = True
                break
        if not credited and _from:
            # Lazy-bind: assign agent_name to the newest unbound connected peer
            unbound = [p for p in _peers.values()
                       if p.get("connected") and not p.get("agent_name")]
            if unbound:
                target = max(unbound, key=lambda p: p.get("connected_at") or 0)
                target["agent_name"] = _from
                target["messages_received"] = target.get("messages_received", 0) + 1
                credited = True
        if not credited:
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
        # v2.36: track last received message_id for read receipt (sent on next outbound message)
        if message_id:
            _status["last_received_message_id"] = message_id

        # v2.35: send acp.delivered ACK back to sender via WebSocket
        if message_id:
            _ack_frame = json.dumps({
                "type":       "acp.delivered",
                "message_id": message_id,
                "from":       _status.get("agent_name", "ACP-Agent"),
                "ts":         _now(),
            }, ensure_ascii=False)
            # Find the WS of the sender and send ack
            _sender_ws = None
            for pinfo in _peers.values():
                if pinfo.get("connected") and (
                    pinfo.get("agent_name") == _from or pinfo.get("name") == _from
                ):
                    _sender_ws = pinfo.get("ws")
                    break
            if _sender_ws is None:
                _sender_ws = _ws_ctx  # fallback: single-peer scenario
            if _sender_ws:
                try:
                    asyncio.ensure_future(_sender_ws.send(_ack_frame))
                except Exception as _ack_err:
                    log.debug(f"[delivery_ack] Failed to send ack for {message_id}: {_ack_err}")
            log.debug(f"[delivery_ack] Sent acp.delivered for {message_id} to {_from}")
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
            "pubkey_b64": _ed25519_public_b64,  # v0.8: explicit alias
            "did":        _did_key or _did_acp,  # v0.8: prefer did:key; fall back to did:acp
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

    v2.14 fix (BUG-045): serialise concurrent writes per-peer with an asyncio.Lock
    to prevent websockets protocol violations (code 1011) under concurrent _ws_send.
    """
    ws = None
    send_lock = None
    if peer_id and peer_id in _peers:
        ws = _peers[peer_id].get("ws")
        if ws is None:
            # v2.0: peer known but offline — buffer for later delivery
            _offline_enqueue(msg, peer_id=peer_id)
            raise ConnectionError(f"Peer '{peer_id}' offline — message queued for delivery on reconnect")
        # Update per-peer counter
        _peers[peer_id]["messages_sent"] = _peers[peer_id].get("messages_sent", 0) + 1
        # BUG-045: per-peer asyncio.Lock to serialise WS writes.
        # Use setdefault for atomic creation — all callers in the same event loop
        # thread, so dict.setdefault is effectively atomic (no threading.Lock needed).
        lock = _peers[peer_id].setdefault("_send_lock", asyncio.Lock())
        send_lock = lock
    else:
        ws = _peer_ws
    if ws is None:
        # v2.0: no peer at all — buffer under "default" key
        _offline_enqueue(msg, peer_id=peer_id or "default")
        raise ConnectionError("No P2P connection — message queued for delivery on reconnect")
    payload = json.dumps(_attach_sig(msg), ensure_ascii=False)
    if send_lock:
        # Per-peer asyncio.Lock: all callers are in the same event loop thread, safe.
        async with send_lock:
            await ws.send(payload)
    else:
        # Legacy path (_peer_ws): serialise across HTTP threads using threading.Lock.
        # _ws_send runs in the event loop thread, but _ws_send_sync is called from
        # multiple HTTP handler threads → the loop thread sends one message at a time,
        # but the threading.Lock prevents concurrent *scheduling* of ws.send coroutines.
        # BUG-045: acquire the thread lock synchronously before awaiting ws.send.
        _ws_send_global_lock.acquire()
        try:
            await ws.send(payload)
        finally:
            _ws_send_global_lock.release()
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
        # BUG-041 fix (enhanced, v2.16 revision): deduplicate peers by incoming token + remote addr.
        # Original: token-only dedup — prevented ghost peers from NAT traversal racing Level1/2/3
        # paths simultaneously (all use same token but may have different remote addrs).
        # Problem: token-only dedup incorrectly rejects DIFFERENT legitimate agents that happen
        # to connect to the same link/token (e.g. Worker1 and Worker2 both connect to Orch link).
        # Fix: dedup only when BOTH token AND remote address match — same NAT-racing path.
        incoming_token  = token  # token is in closure scope from host_mode()
        incoming_remote = websocket.remote_address  # (host, port) tuple or None
        existing_pid = next(
            (pid for pid, pinfo in _peers.items()
             if pinfo.get("link_token") == incoming_token
             and pinfo.get("connected")
             and pinfo.get("remote_address") == str(incoming_remote)),
            None
        )
        if existing_pid:
            # Same token AND same remote address — NAT duplicate path, close it.
            log.info(f"[host_mode] Duplicate WS for token {incoming_token[:8]}… "
                     f"already have peer {existing_pid} (connected=True, same remote {incoming_remote}). "
                     f"Closing duplicate.")
            try:
                await websocket.close(1000, "duplicate_connection")
            except Exception:
                pass
            return
        # No existing connected peer for this token — register new peer
        peer_id = _register_peer(ws=websocket, link_token=incoming_token,
                                 remote_address=str(incoming_remote))
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
            _status["connection_type"] = "host"        # BUG-047: reset to "host" on disconnect
            _broadcast_sse_event("peer", {"event": "disconnected", "peer_id": peer_id})

    # v2.35: --local-only mode — skip public-IP detection and relay registration
    # (for CI, local tests, sandboxed environments where network is restricted)
    _local_only_mode = _status.get("local_only", False)

    if _local_only_mode:
        log.info("--local-only: skipping public IP detection and relay registration")
        display_ip = "127.0.0.1"
        public_ip = None
        relay_link = None
        relay_token = token
    else:
        log.info("Detecting public IP...")
        public_ip = await asyncio.get_event_loop().run_in_executor(None, lambda: get_public_ip(4.0))
        display_ip = public_ip or get_local_ip()

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

    p2p_link = f"acp://{display_ip}:{ws_port}/{token}"

    # 链接格式：acp://IP:PORT/TOKEN（应用层标识，不含传输层细节）
    link = p2p_link
    _status["link"] = link
    _status["relay_token"] = relay_token if relay_link else None

    # 同时在后台持续监听 relay（对方走中继时能收到消息）
    if relay_link:
        DEFAULT_RELAY = "https://black-silence-11c4.yuranliu888.workers.dev"
        relay_base = DEFAULT_RELAY
        _status["relay_base_url"] = relay_base  # expose for DCUtR HTTP reflection (v1.4)
        asyncio.ensure_future(_http_relay_guest(relay_base, relay_token, http_port))

    async with websockets.serve(on_guest, "0.0.0.0", ws_port):
        _status["p2p_enabled"] = True   # v2.3: flag for supported_interfaces auto-derivation
        print(f"\n{'='*60}")
        print(f"ACP P2P v{VERSION} - service started")
        if _local_only_mode:
            print(f"  Mode: LOCAL-ONLY (no relay, no public IP)")
        else:
            print(f"  IP: {'public' if public_ip else 'LAN'} {display_ip}")
        print(f"\n  Your link (send this to peer):")
        print(f"  {link}")
        if not _local_only_mode:
            print(f"\n  Transport: P2P ready | Relay pre-registered (auto-fallback)")
        print(f"  Waiting for peer...")
        print(f"{'='*60}\n")
        await asyncio.Future()


# ══════════════════════════════════════════════════════════════════════════════
# GUEST mode
# ══════════════════════════════════════════════════════════════════════════════

async def guest_mode(host, ws_port, token, http_port, embedded_relay=None, _existing_ws=None):
    """
    P2P 直连模式。连接失败超过 P2P_MAX_RETRIES 次后，
    自动降级到中继。传输层选择对应用层透明。
    token 同时是 P2P token 和 relay session token（同一标识符）。
    embedded_relay: 保留参数（兼容旧调用），实际不再需要
    _existing_ws: 已建立的 WS 对象（BUG-042 修复：由 _connect_with_nat_traversal Level 1 传入，
                  避免重新握手触发 BUG-041 dedup 关闭连接）
    """
    global _peer_ws
    _embedded_relay = embedded_relay  # 保留兼容性
    uri = f"ws://{host}:{ws_port}/{token}"
    P2P_MAX_RETRIES = 3   # P2P 最多尝试 3 次，失败后自动降级
    retry = 0

    while retry < P2P_MAX_RETRIES:
        try:
            # BUG-042 fix: if an existing WS is provided (from _connect_with_nat_traversal
            # Level 1), reuse it directly for the first iteration to avoid opening a second
            # WS connection that would be rejected by BUG-041 dedup logic on the host side.
            if _existing_ws is not None:
                log.info(f"[guest_mode] BUG-042: reusing Level-1 WS (no reconnect): {uri}")
                _ws_ctx = _existing_ws
                _existing_ws = None  # consume once
            else:
                log.info(f"{'Reconnecting #' + str(retry) if retry else 'Connecting to (P2P)'}: {uri}")
                _ws_ctx = await _proxy_ws_connect(uri, ping_interval=20, ping_timeout=10)
            async with _ws_ctx as ws:
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
            _status["connection_type"] = "host"        # BUG-047: reset to "host" on disconnect
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
# _connect_with_nat_traversal — v1.4 three-level automatic connection strategy
# ══════════════════════════════════════════════════════════════════════════════

async def _connect_with_nat_traversal(link: str, name: str, role: str) -> tuple:
    """
    三级连接策略（自动选择）：
      Level 1: 直连 ws://IP:port/token（3s 超时）
      Level 2: DCUtR TCP 打洞（交换 signaling → SYN 打洞）
      Level 3: HTTP Relay 降级（Cloudflare Worker 转发，兜底）

    返回：(peer_id, transport_level_used)
      transport_level_used: "direct" | "dcutr" | "relay"

    调用方负责将 transport_level_used 写入 _peers[peer_id]["transport_level"]。

    参数:
      link  — acp:// 格式链接（parse_link 负责解析）
      name  — 本地 agent 名（用于 relay join 请求体）
      role  — 保留参数，供上层标注 peer 角色
    """
    global _peers, _status, _loop

    _DEFAULT_RELAY = "https://black-silence-11c4.yuranliu888.workers.dev"
    DIRECT_TIMEOUT = 3.0   # Level 1: 3s 直连超时
    DCUTR_TIMEOUT  = 12.0  # Level 2: 打洞超时

    result = parse_link(link)
    host, port, token, scheme = result
    http_port = _status.get("http_port", 7901)

    # ── If link is already an HTTP relay link, skip to Level 3 directly ──────
    if scheme == "http_relay":
        log.info("[NAT] link is http_relay scheme → Level 3 directly")
        asyncio.ensure_future(_http_relay_guest(host, token, http_port))
        return (token, "relay")

    # ── Check --relay flag: force Level 3 (v1.4 semantic change) ─────────────
    # Prior to v1.4, --relay meant "user explicitly chose relay".
    # From v1.4 onward, --relay means "force Level 3 (skip L1+L2)".
    _force_relay = _status.get("force_relay", False)
    if _force_relay:
        log.info("[NAT] --relay flag set → forcing Level 3 relay (skip L1+L2)")
        relay_base = _status.get("relay_base_url") or _DEFAULT_RELAY
        asyncio.ensure_future(_http_relay_guest(relay_base, token, http_port))
        return (token, "relay")

    uri = f"ws://{host}:{port}/{token}"

    # ── Level 1: Direct WebSocket connection (3s timeout) ─────────────────────
    log.info(f"[NAT L1] Attempting direct connect: {uri}")
    try:
        ws = await asyncio.wait_for(
            _proxy_ws_connect(uri, ping_interval=20, ping_timeout=10),
            timeout=DIRECT_TIMEOUT,
        )
        # BUG-042 fix: pass the already-established WS to guest_mode so it reuses
        # this connection directly instead of opening a second WS.  The old code did
        # asyncio.ensure_future(guest_mode(...)) which opened a NEW WS, triggering
        # BUG-041 dedup on the host side and immediately closing the second connection.
        log.info(f"[NAT L1] Direct connect succeeded: {uri} — handing off to guest_mode")
        _status["connection_type"] = "p2p_direct"
        asyncio.ensure_future(guest_mode(host, port, token, http_port, _existing_ws=ws))
        return (token, "direct")
    except (asyncio.TimeoutError, ConnectionRefusedError, OSError,
            Exception) as e:
        log.info(f"[NAT L1] Direct connect failed ({type(e).__name__}): {e} → trying Level 2")

    # ── Level 2: DCUtR TCP/UDP hole punch ─────────────────────────────────────
    log.info("[NAT L2] Attempting DCUtR hole punch...")
    _broadcast_sse_event("peer", {"event": "dcutr_started"})
    relay_base_url = _status.get("relay_base_url") or _DEFAULT_RELAY
    _dcutr_direct_addr = None

    try:
        relay_ws_url = relay_base_url.replace("https://", "wss://") + f"/acp/{token}/ws"
        async with await asyncio.wait_for(
            _proxy_ws_connect(relay_ws_url, open_timeout=5),
            timeout=6.0,
        ) as _sig_ws:
            log.info(f"[NAT L2] signaling WS established: {relay_ws_url}")
            _status["dcutr_state"] = "punching"
            puncher = DCUtRPuncher()
            _dcutr_direct_addr = await asyncio.wait_for(
                puncher.attempt(_sig_ws, local_udp_port=0),
                timeout=DCUTR_TIMEOUT,
            )
    except asyncio.TimeoutError:
        log.info("[NAT L2] hole punch timed out → falling back to Level 3")
    except Exception as e:
        log.info(f"[NAT L2] hole punch error ({type(e).__name__}): {e} → falling back to Level 3")
    finally:
        _status.pop("dcutr_state", None)

    if _dcutr_direct_addr is not None:
        direct_host, direct_port = _dcutr_direct_addr
        log.info(f"[NAT L2] hole punch succeeded → {direct_host}:{direct_port}")
        _status["connection_type"] = "dcutr_direct"
        _broadcast_sse_event("peer", {"event": "dcutr_connected",
                                       "peer_addr": f"{direct_host}:{direct_port}"})
        asyncio.ensure_future(guest_mode(direct_host, direct_port, token, http_port))
        return (token, "dcutr")

    # ── Level 3: Relay fallback (Cloudflare Worker) ───────────────────────────
    log.warning("[NAT L3] Both L1 and L2 failed. Falling back to HTTP relay (Level 3).")
    _broadcast_sse_event("peer", {"event": "relay_fallback", "reason": "l1_l2_failed"})
    _status["connection_type"] = "relay"

    relay_base = relay_base_url
    # Join relay session so messages can flow
    import subprocess as _sp_nat
    try:
        _sp_nat.run(
            ["curl", "-s", "--max-time", "10", "-X", "POST",
             f"{relay_base}/acp/{token}/join",
             "-H", "Content-Type: application/json",
             "-d", json.dumps({"name": name or _status.get("agent_name", "ACP-Agent")})],
            capture_output=True,
        )
    except Exception as _e:
        log.warning(f"[NAT L3] relay join failed: {_e}")

    asyncio.ensure_future(_http_relay_guest(relay_base, token, http_port))
    return (token, "relay")


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

    def _json_well_known(self, data, code=200):
        """RFC 8615-compliant response for /.well-known/* endpoints.

        Adds required headers beyond the base _json():
          - Cache-Control: no-cache, no-store  (AgentCard is dynamic; must not be stale)
          - Vary: Accept                        (content negotiation hint for proxies)
          - Access-Control-Allow-Methods: GET, OPTIONS  (CORS preflight clarity)
          - Access-Control-Allow-Headers: Content-Type  (standard CORS header)
          - X-Content-Type-Options: nosniff    (security hardening per RFC 8615 §4)

        v2.47: introduced for /.well-known/acp.json, /.well-known/did.json,
               /.well-known/jwks.json to align with RFC 8615 production requirements.
        """
        body = json.dumps(data, ensure_ascii=False, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache, no-store")
        self.send_header("Vary", "Accept")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        n = int(self.headers.get("Content-Length", 0))
        # BUG-051 fix: enforce MAX_MSG_BYTES on HTTP request bodies (same limit as WebSocket)
        if n > MAX_MSG_BYTES:
            e_body, e_code = _err(ERR_MSG_TOO_LARGE,
                                  f"Request body too large: {n} bytes (max {MAX_MSG_BYTES})", 413)
            self._json(e_body, e_code)
            # Drain remaining bytes to keep connection clean
            try:
                self.rfile.read(min(n, 4096))
            except Exception:
                pass
            raise _BodyReadError()
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
            # v2.10: pass full structured skill objects (preserve description/tags/examples)
            skills = list((_status.get("agent_card") or {}).get("skills", []))
            live_card = _make_agent_card(_status.get("agent_name", "ACP-Agent"), skills)
            # v1.8: attach Ed25519 self-signature when identity is enabled
            live_card = _sign_agent_card(live_card)
            # v2.21: ?filter_limitations=permanent|transient|<kind> — filter limitations[] by permanence or kind
            fl = qs.get("filter_limitations", [None])[0]
            if fl and "limitations" in live_card:
                lims = live_card["limitations"]
                if fl == "permanent":
                    lims = [lim for lim in lims if lim.get("permanent") is True]
                elif fl == "transient":
                    lims = [lim for lim in lims if lim.get("permanent") is not True]
                elif fl in _VALID_LIMITATION_KINDS:
                    lims = [lim for lim in lims if lim.get("kind") == fl]
                else:
                    self._json({"error": f"invalid filter_limitations value '{fl}'; "
                                         f"use 'permanent', 'transient', or one of {sorted(_VALID_LIMITATION_KINDS)}"}, 400)
                    return
                live_card = {**live_card, "limitations": lims}
            self._json_well_known({"self": live_card, "peer": _status.get("peer_card")})

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
            # Prefer did:key (W3C standard) when available; fall back to did:acp
            primary_did = _did_key or _did_acp
            did_doc = {
                "@context": [
                    "https://www.w3.org/ns/did/v1",
                    "https://w3id.org/security/suites/ed25519-2020/v1",
                ],
                "id": primary_did,
                "alsoKnownAs": ([_did_acp] if _did_key and _did_acp else []),  # v0.8: cross-reference did:acp
                "verificationMethod": [{
                    "id":                f"{primary_did}#key-1",
                    "type":              "Ed25519VerificationKey2020",
                    "controller":        primary_did,
                    "publicKeyMultibase": f"z{_base58_encode(bytes([0xed, 0x01]) + _base64.urlsafe_b64decode(_ed25519_public_b64 + '=='))}",  # multibase base58btc
                }],
                "authentication":       [f"{primary_did}#key-1"],
                "assertionMethod":      [f"{primary_did}#key-1"],
                "service": ([{
                    "id":              f"{primary_did}#acp",
                    "type":            "ACPRelay",
                    "serviceEndpoint": link,
                }] if link else []),
            }
            self._json_well_known(did_doc)

        # ── GET /.well-known/jwks.json — JWKS endpoint (v2.18) ────────────────
        elif p == "/.well-known/jwks.json":
            """Return a JWK Set (RFC 7517) containing this Agent's Ed25519 public key.

            v2.18: JWKS compatibility layer for A2A IS#1628 interoperability.

            Returns:
              200 + {"keys": [<JWK>]}   when --identity is enabled (Ed25519 keypair loaded)
              200 + {"keys": []}         when --identity is NOT provided

            This endpoint is unauthenticated (public well-known key discovery).
            The JWK contains only the public key; the private key is never exported.

            JWK format:
              {
                "kty": "OKP",
                "crv": "Ed25519",
                "x":   "<base64url 32-byte pubkey>",
                "use": "sig",
                "alg": "EdDSA",
                "kid": "<agent_name>:<pubkey_prefix>"
              }

            Test IDs: JW1 ~ JW6
            """
            agent_name = _status.get("agent_name", "ACP-Agent")
            jwks = _build_jwks(agent_name)
            self._json_well_known(jwks)

        elif p == "/status":  # [stable] relay status
            self._json(_status)

        elif p == "/link":
            self._json({"link": _status.get("link"), "session_id": _status.get("session_id")})

        # ── GET /peers — list all known peers with pagination (v0.6, v2.27) ────
        elif p == "/peers":
            # v2.27: pagination + filter params
            try:
                limit_raw  = qs.get("limit",  ["50"])[0]
                offset_raw = qs.get("offset", ["0"])[0]
                filter_val = qs.get("filter", ["all"])[0].lower()  # all|connected|disconnected
                try:
                    limit = max(1, min(int(limit_raw), 200))
                except ValueError:
                    limit = 50
                try:
                    offset = max(0, int(offset_raw))
                except ValueError:
                    offset = 0
            except Exception:
                limit, offset, filter_val = 50, 0, "all"

            # build full list
            peer_list_all = []
            for pid, info in _peers.items():
                peer_list_all.append({
                    "id":               info["id"],
                    "name":             info["name"],
                    "link":             info.get("link"),
                    "connected":        info["connected"],
                    "ws_ready":         info["connected"] and info.get("ws") is not None,  # v2.16: true only after WS handshake
                    "connected_at":     info.get("connected_at"),
                    "disconnected_at":  info.get("disconnected_at"),
                    "messages_sent":      info.get("messages_sent", 0),
                    "messages_received":  info.get("messages_received", 0),
                    "messages_delivered": info.get("messages_delivered", 0),  # v2.35: delivery ACK count
                    "messages_read":      info.get("messages_read", 0),       # v2.36: read receipt count
                    "typing":             info.get("typing", False),           # v2.37: peer typing indicator
                    "typing_since":       info.get("typing_since"),            # v2.37: ISO ts when started
                    "agent_card":         info.get("agent_card"),
                    "last_ping_rtt_ms":   info.get("last_ping_rtt_ms"),   # v2.25: RTT from last /ping
                    "last_ping_at":     info.get("last_ping_at"),        # v2.25: ISO timestamp of last ping
                    "ping_count":       info.get("ping_count", 0),       # v2.25: total pings sent to this peer
                })

            # v2.27: apply filter
            if filter_val == "connected":
                filtered = [p2 for p2 in peer_list_all if p2["connected"]]
            elif filter_val == "disconnected":
                filtered = [p2 for p2 in peer_list_all if not p2["connected"]]
            elif filter_val == "all":
                filtered = peer_list_all
            else:
                self._json({"ok": False, "error_code": "ERR_INVALID_FILTER",
                            "error": f"filter must be one of: all, connected, disconnected"}, 400)
                return

            total_filtered = len(filtered)
            page_items     = filtered[offset: offset + limit]
            active         = sum(1 for p2 in _peers.values() if p2["connected"])

            self._json({
                "peers":         page_items,
                "count":         len(page_items),       # items in this page
                "total":         len(peer_list_all),    # total known peers (unfiltered)
                "total_filtered": total_filtered,       # total after filter
                "active":        active,                # connected peers (always)
                "pagination": {                         # v2.27: pagination metadata
                    "limit":    limit,
                    "offset":   offset,
                    "filter":   filter_val,
                    "has_more": (offset + limit) < total_filtered,
                    "next_offset": (offset + limit) if (offset + limit) < total_filtered else None,
                },
            })

        # ── GET /peers/broadcast/history — broadcast history log (v2.23) ──────
        elif p == "/peers/broadcast/history":
            try:
                limit_raw = qs.get("limit", ["20"])[0]
                try:
                    limit = max(1, min(int(limit_raw), 200))
                except ValueError:
                    limit = 20
                history = list(reversed(_broadcast_log))[:limit]
                self._json({
                    "ok": True,
                    "count": len(history),
                    "total": len(_broadcast_log),
                    "history": history,
                })
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)

        # ── GET /peers/<peer_id>/card — fetch cached AgentCard for a peer (v2.24) ──
        elif p.startswith("/peers/") and p.endswith("/card") and p.count("/") == 3:
            try:
                peer_id = p.split("/")[2]
                if peer_id not in _peers:
                    self._json({"ok": False, "error_code": "ERR_PEER_NOT_FOUND",
                                "error": f"peer '{peer_id}' not found"}, 404)
                    return
                info = _peers[peer_id]
                card = info.get("agent_card")
                self._json({
                    "ok": True,
                    "peer_id": peer_id,
                    "name": info.get("name"),
                    "connected": info.get("connected", False),
                    "agent_card": card,
                    "card_available": card is not None,
                })
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)

        # ── GET /peers/{peer_id}/trust — structured per-peer trust score (v2.34) ──
        elif p.startswith("/peers/") and p.endswith("/trust") and p.count("/") == 3:
            """
            Return a structured trust assessment for the specified peer.

            Score dimensions (each 0.0–1.0):
              card_sig      — peer AgentCard signature verified (Ed25519)
              did_consistent — DID in card is consistent with public key
              ping_rtt      — liveness: <50ms→1.0, <200ms→0.7, <500ms→0.4, else→0.1 (None→0.0)
              message_hist  — message volume: >100→1.0, >20→0.7, >5→0.4, >0→0.2, 0→0.0
              vouch         — at least one vouch for peer's DID in _vouch_chain

            overall = weighted mean of dimensions with weights:
              card_sig×0.35, did_consistent×0.20, ping_rtt×0.20, message_hist×0.15, vouch×0.10

            Response 200: {ok, peer_id, name, connected, trust_score, dimensions, evaluated_at}
            Response 404: peer not found
            """
            try:
                peer_id = p.split("/")[2]
                if peer_id not in _peers:
                    self._json({"ok": False, "error_code": "ERR_PEER_NOT_FOUND",
                                "error": f"peer '{peer_id}' not found"}, 404)
                    return

                info = _peers[peer_id]

                # ── Dimension 1: card_sig ─────────────────────────────────────
                vr = info.get("card_verification") or {}
                if not vr and peer_id in _peers:
                    # fallback: re-run if AgentCard available
                    card_obj = info.get("agent_card")
                    if card_obj and _ed25519_private:
                        vr = _verify_agent_card(card_obj) if callable(globals().get("_verify_agent_card")) else {}
                card_sig_score      = 1.0 if vr.get("valid") else 0.0
                did_consistent_score= 1.0 if vr.get("did_consistent") else (0.5 if vr.get("valid") else 0.0)

                # ── Dimension 2: ping RTT ─────────────────────────────────────
                rtt = info.get("last_ping_rtt_ms")
                if rtt is None:
                    ping_score = 0.0
                elif rtt < 50:
                    ping_score = 1.0
                elif rtt < 200:
                    ping_score = 0.7
                elif rtt < 500:
                    ping_score = 0.4
                else:
                    ping_score = 0.1

                # ── Dimension 3: message history ─────────────────────────────
                msgs = info.get("messages_sent", 0)
                if msgs >= 100:
                    msg_score = 1.0
                elif msgs >= 20:
                    msg_score = 0.7
                elif msgs >= 5:
                    msg_score = 0.4
                elif msgs > 0:
                    msg_score = 0.2
                else:
                    msg_score = 0.0

                # ── Dimension 4: vouch chain ──────────────────────────────────
                peer_did = None
                card_obj2 = info.get("agent_card")
                if isinstance(card_obj2, dict):
                    peer_did = (card_obj2.get("identity") or {}).get("did")
                vouch_score = 0.0
                if peer_did and _vouch_chain:
                    for v in _vouch_chain:
                        if isinstance(v, dict) and v.get("vouched_did") == peer_did:
                            vouch_score = 1.0
                            break

                # ── Weighted overall score ────────────────────────────────────
                weights = {"card_sig": 0.35, "did_consistent": 0.20,
                           "ping_rtt": 0.20, "message_hist": 0.15, "vouch": 0.10}
                raw_scores = {"card_sig": card_sig_score, "did_consistent": did_consistent_score,
                              "ping_rtt": ping_score, "message_hist": msg_score, "vouch": vouch_score}
                overall = sum(raw_scores[k] * weights[k] for k in weights)

                dimensions = {
                    "card_sig": {
                        "score": round(card_sig_score, 3),
                        "weight": weights["card_sig"],
                        "detail": vr.get("error") or ("verified" if card_sig_score == 1.0 else "not verified"),
                    },
                    "did_consistent": {
                        "score": round(did_consistent_score, 3),
                        "weight": weights["did_consistent"],
                        "detail": "DID matches public key" if did_consistent_score == 1.0 else "DID mismatch or unavailable",
                    },
                    "ping_rtt": {
                        "score": round(ping_score, 3),
                        "weight": weights["ping_rtt"],
                        "detail": f"{rtt:.1f}ms" if rtt is not None else "no ping data",
                        "last_ping_rtt_ms": rtt,
                        "ping_count": info.get("ping_count", 0),
                    },
                    "message_hist": {
                        "score": round(msg_score, 3),
                        "weight": weights["message_hist"],
                        "detail": f"{msgs} messages sent",
                        "messages_sent": msgs,
                    },
                    "vouch": {
                        "score": round(vouch_score, 3),
                        "weight": weights["vouch"],
                        "detail": f"vouched by {peer_did}" if vouch_score == 1.0 else "no vouch found",
                        "peer_did": peer_did,
                    },
                }

                self._json({
                    "ok":           True,
                    "peer_id":      peer_id,
                    "name":         info.get("name"),
                    "connected":    info.get("connected", False),
                    "trust_score":  round(overall, 4),
                    "trust_level":  ("high" if overall >= 0.75 else
                                     "medium" if overall >= 0.45 else
                                     "low"),
                    "dimensions":   dimensions,
                    "evaluated_at": _now(),
                })
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)

        # ── GET /peers/<peer_id>/messages — per-peer message history (v2.48) ──
        elif p.startswith("/peers/") and p.endswith("/messages") and p.count("/") == 3:
            """
            Return message history for a specific peer (both inbound and outbound).

            Query params:
              limit      — max messages to return (default 50, max 500)
              offset     — skip N messages from the start (default 0)
              direction  — "inbound"|"outbound"|"all" (default "all")
              since_seq  — only messages with server_seq > N (for incremental polling)
              sort       — "asc"|"desc" (default "desc" — newest first)

            Response 200:
              {ok, peer_id, name, messages[], count, total, has_more, next_offset}
            Response 404: peer not found (ERR_PEER_NOT_FOUND)
            Response 400: invalid params (ERR_INVALID_REQUEST)
            """
            try:
                peer_id = p.split("/")[2]
                if peer_id not in _peers:
                    self._json({"ok": False, "error_code": "ERR_PEER_NOT_FOUND",
                                "error": f"peer '{peer_id}' not found"}, 404)
                    return

                pinfo = _peers[peer_id]
                peer_name = pinfo.get("agent_name") or pinfo.get("name") or peer_id

                # ── Parse query params ─────────────────────────────────────────
                qs = parse_qs(urlparse(self.path).query)

                try:
                    limit = min(int(qs.get("limit", ["50"])[0]), 500)
                except ValueError:
                    self._json({"ok": False, "error_code": "ERR_INVALID_REQUEST",
                                "error": "limit must be an integer"}, 400)
                    return
                try:
                    offset = max(0, int(qs.get("offset", ["0"])[0]))
                except ValueError:
                    self._json({"ok": False, "error_code": "ERR_INVALID_REQUEST",
                                "error": "offset must be an integer"}, 400)
                    return

                direction = qs.get("direction", ["all"])[0]
                if direction not in ("inbound", "outbound", "all"):
                    self._json({"ok": False, "error_code": "ERR_INVALID_REQUEST",
                                "error": "direction must be 'inbound', 'outbound', or 'all'"}, 400)
                    return

                since_seq_raw = qs.get("since_seq", [None])[0]
                since_seq = None
                if since_seq_raw is not None:
                    try:
                        since_seq = int(since_seq_raw)
                    except ValueError:
                        self._json({"ok": False, "error_code": "ERR_INVALID_REQUEST",
                                    "error": "since_seq must be an integer"}, 400)
                        return

                sort_order = qs.get("sort", ["desc"])[0]
                if sort_order not in ("asc", "desc"):
                    self._json({"ok": False, "error_code": "ERR_INVALID_REQUEST",
                                "error": "sort must be 'asc' or 'desc'"}, 400)
                    return

                # ── Filter _recv_queue for messages involving this peer ─────────
                # Identify all names/ids that could refer to this peer
                peer_identifiers = set()
                peer_identifiers.add(peer_id)
                if pinfo.get("agent_name"):
                    peer_identifiers.add(pinfo["agent_name"])
                if pinfo.get("name"):
                    peer_identifiers.add(pinfo["name"])

                all_msgs = list(_recv_queue)  # non-destructive snapshot

                filtered = []
                for msg in all_msgs:
                    raw = msg.get("raw", {})
                    msg_from = raw.get("from") or msg.get("from", "")
                    msg_to = raw.get("to") or msg.get("to", "")
                    msg_dir = msg.get("direction", "inbound")  # outbound entries set by _outbound_entry

                    # Determine if this message involves our target peer
                    involves_peer = (
                        msg_from in peer_identifiers or
                        msg_to in peer_identifiers or
                        msg.get("peer_id") == peer_id
                    )
                    if not involves_peer:
                        continue

                    # Direction filter
                    if direction == "inbound" and msg_dir != "inbound":
                        continue
                    if direction == "outbound" and msg_dir != "outbound":
                        continue

                    # since_seq filter
                    if since_seq is not None:
                        msg_seq = msg.get("server_seq") or raw.get("server_seq")
                        if msg_seq is None or msg_seq <= since_seq:
                            continue

                    filtered.append(msg)

                # Sort
                filtered.sort(
                    key=lambda m: m.get("received_at") or m.get("sent_at") or 0,
                    reverse=(sort_order == "desc")
                )

                total = len(filtered)
                page = filtered[offset: offset + limit]
                has_more = (offset + limit) < total
                next_offset = (offset + limit) if has_more else None

                # Build clean response objects
                result_msgs = []
                for m in page:
                    raw = m.get("raw", {})
                    result_msgs.append({
                        "message_id":   m.get("message_id") or raw.get("message_id"),
                        "server_seq":   m.get("server_seq") or raw.get("server_seq"),
                        "direction":    m.get("direction", "inbound"),
                        "from":         raw.get("from") or m.get("from"),
                        "to":           raw.get("to") or m.get("to"),
                        "parts":        m.get("parts") or raw.get("parts", []),
                        "context_id":   m.get("context_id") or raw.get("context_id"),
                        "task_id":      m.get("task_id") or raw.get("task_id"),
                        "priority":     raw.get("priority", "normal"),
                        "received_at":  m.get("received_at"),
                        "sent_at":      m.get("sent_at"),
                    })

                self._json({
                    "ok":          True,
                    "peer_id":     peer_id,
                    "name":        peer_name,
                    "connected":   pinfo.get("connected", False),
                    "messages":    result_msgs,
                    "count":       len(result_msgs),
                    "total":       total,
                    "has_more":    has_more,
                    "next_offset": next_offset,
                    "direction_filter": direction,
                    "sort":        sort_order,
                })
            except Exception as e:
                log.exception(f"[peer_messages] {e}")
                self._json({"ok": False, "error": str(e)}, 500)

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

        # ── v2.17: GET /availability — dedicated availability status endpoint ──
        elif p == "/availability":
            avail = _availability_with_schedule(dict(_availability)) if _availability else {}
            # Always include last_active_at
            if avail and "last_active_at" not in avail:
                started = _status.get("started_at")
                if started and isinstance(started, (int, float)):
                    avail["last_active_at"] = (
                        datetime.datetime.fromtimestamp(started, tz=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    )
                else:
                    avail["last_active_at"] = _now()
            self._json({
                "ok":           True,
                "availability": avail,
                "mode":         avail.get("mode", "persistent"),
                "has_schedule": bool(avail.get("schedule")),
            })

        # ── GET /skills — Skills-lite structured skill list (v2.10) ──────────
        elif p == "/skills":  # [stable] structured skill discovery + filtering (v2.10)
            # Query parameters:
            #   tag=<tag>              filter by tag (exact match)
            #   q=<keyword>            keyword search in id/name/description (case-insensitive)
            #   limit=<n>              page size (default 50, max 200)
            #   offset=<n>             offset-based pagination (default 0)
            #   has_limitation=<val>   v2.28: filter skills that declare a limitation with matching kind or code
            # Response: {skills, total, has_more, next_offset}
            # Errors: 400 ERR_INVALID_REQUEST for non-integer limit/offset

            # ── Parameter parsing ─────────────────────────────────────────
            try:
                raw_limit = qs.get("limit", ["50"])[0]
                if not raw_limit.lstrip("-").isdigit():
                    raise ValueError("non-integer limit")
                limit = int(raw_limit)
            except (ValueError, TypeError):
                body, sc = _err(ERR_INVALID_REQUEST, "limit must be a non-negative integer", 400)
                self._json(body, sc)
                return
            try:
                raw_offset = qs.get("offset", ["0"])[0]
                if not raw_offset.lstrip("-").isdigit():
                    raise ValueError("non-integer offset")
                offset = int(raw_offset)
            except (ValueError, TypeError):
                body, sc = _err(ERR_INVALID_REQUEST, "offset must be a non-negative integer", 400)
                self._json(body, sc)
                return

            if limit < 0 or offset < 0:
                body, sc = _err(ERR_INVALID_REQUEST, "limit and offset must be non-negative integers", 400)
                self._json(body, sc)
                return

            # Clamp limit to max 200; default when 0 is 50
            limit = min(limit, 200)
            if limit == 0:
                limit = 50

            tag_filter           = qs.get("tag",             [None])[0]
            q_filter             = (qs.get("q", [None])[0] or "").strip().lower()
            has_limitation_filter = (qs.get("has_limitation", [None])[0] or "").strip().lower()  # v2.28

            # ── Fetch skill list from agent card ──────────────────────────
            agent_card = _status.get("agent_card") or {}
            all_skills = list(agent_card.get("skills", []))

            # ── Apply filters ─────────────────────────────────────────────
            if tag_filter:
                all_skills = [s for s in all_skills if tag_filter in s.get("tags", [])]

            if q_filter:
                def _skill_matches(s):
                    return (
                        q_filter in (s.get("id",          "") or "").lower() or
                        q_filter in (s.get("name",        "") or "").lower() or
                        q_filter in (s.get("description", "") or "").lower()
                    )
                all_skills = [s for s in all_skills if _skill_matches(s)]

            # v2.28: filter by limitation kind or code
            if has_limitation_filter:
                def _has_matching_limitation(s):
                    for lim in s.get("limitations") or []:
                        if (
                            (lim.get("kind",    "") or "").lower() == has_limitation_filter or
                            (lim.get("code",    "") or "").lower() == has_limitation_filter
                        ):
                            return True
                    return False
                all_skills = [s for s in all_skills if _has_matching_limitation(s)]

            # ── Pagination ────────────────────────────────────────────────
            total    = len(all_skills)
            sliced   = all_skills[offset:]
            has_more = len(sliced) > limit
            page     = sliced[:limit]
            next_offset = (offset + limit) if has_more else None

            # v2.29: apply per-skill limitations overrides before returning
            if _skill_limitations_overrides:
                merged_page = []
                for s in page:
                    sid = s.get("id", "") if isinstance(s, dict) else str(s)
                    if sid in _skill_limitations_overrides:
                        s = {**s, "limitations": _skill_limitations_overrides[sid]}
                    merged_page.append(s)
                page = merged_page

            self._json({
                "skills":      page,
                "total":       total,
                "has_more":    has_more,
                "next_offset": next_offset,
            })

        # ── GET /docs/openapi-skills.yaml — OpenAPI 3.1 spec for /skills (v2.41) ──
        elif p == "/docs/openapi-skills.yaml":
            spec_path = os.path.join(os.path.dirname(__file__), "..", "docs", "openapi-skills.yaml")
            if os.path.exists(spec_path):
                with open(spec_path, "r") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/yaml")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(content.encode())
            else:
                self._error(404, "openapi-skills.yaml not found")

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
            # v2.10: pass full structured skill objects
            skills = list((_status.get("agent_card") or {}).get("skills", []))
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
            # v2.39: long poll support — wait=<seconds> blocks until message arrives or timeout
            try:
                wait_sec = float(qs.get("wait", ["0"])[0])
                wait_sec = max(0.0, min(30.0, wait_sec))  # clamp to [0, 30]
            except (ValueError, TypeError):
                wait_sec = 0.0

            timed_out = False
            if wait_sec > 0 and len(_recv_queue) == 0:
                # hang until a message arrives or timeout expires
                # Use a deadline loop to handle spurious wakeups from pre-set events:
                #   1. clear the event first to avoid acting on stale set state
                #   2. re-check queue after clear (message may have arrived in the gap)
                #   3. loop until queue is non-empty or deadline passes
                _deadline = time.time() + wait_sec
                while len(_recv_queue) == 0:
                    _remaining = _deadline - time.time()
                    if _remaining <= 0:
                        timed_out = True
                        break
                    _sse_notify.clear()
                    if len(_recv_queue) > 0:  # re-check after clear (race window)
                        break
                    _sse_notify.wait(timeout=min(_remaining, 1.0))

            # v2.38: sort by priority before returning (critical > high > normal > low)
            _recv_snapshot = [_recv_queue.popleft() for _ in range(min(limit, len(_recv_queue)))]
            _recv_snapshot.sort(
                key=lambda m: _PRIORITY_ORDER.get(
                    (m.get("raw") or m).get("priority", "normal") if isinstance(m, dict) else "normal",
                    2  # default "normal" order
                )
            )
            self._json({"messages": _recv_snapshot, "count": len(_recv_snapshot), "remaining": len(_recv_queue), "timed_out": timed_out})

        elif p == "/messages":  # [stable] history message list — filtering + pagination (v2.9)
            # Query params:
            #   limit=<n>              page size (default 20, max 100)
            #   offset=<n>             offset-based page start (default 0)
            #   peer_id=<id>           filter by source peer (matches raw.from or _peers lookup)
            #   role=<agent|user>      filter by role
            #   sort=asc|desc          sort direction: asc=oldest first, desc=newest first (default desc)
            #   received_after=<ts>    filter messages received after this Unix timestamp

            # ── Parameter parsing ──────────────────────────────────────────────
            try:
                raw_limit = qs.get("limit", ["20"])[0]
                limit = int(raw_limit)
                if not raw_limit.lstrip("-").isdigit():
                    raise ValueError("non-integer")
            except (ValueError, TypeError):
                body, sc = _err(ERR_INVALID_REQUEST, "limit must be a non-negative integer", 400)
                self._json(body, sc)
                return
            try:
                raw_offset = qs.get("offset", ["0"])[0]
                offset = int(raw_offset)
                if not raw_offset.lstrip("-").isdigit():
                    raise ValueError("non-integer")
            except (ValueError, TypeError):
                body, sc = _err(ERR_INVALID_REQUEST, "offset must be a non-negative integer", 400)
                self._json(body, sc)
                return

            if limit < 0 or offset < 0:
                body, sc = _err(ERR_INVALID_REQUEST, "limit and offset must be non-negative integers", 400)
                self._json(body, sc)
                return

            # Clamp limit to max 100
            limit = min(limit, 100)
            # Default when 0: treat as 20 (caller should pass explicit limit)
            if limit == 0:
                limit = 20

            peer_filter     = qs.get("peer_id",        [None])[0]
            role_filter     = qs.get("role",            [None])[0]
            sort_raw        = qs.get("sort",            ["desc"])[0]
            received_after  = qs.get("received_after",  [None])[0]

            sort_asc = (sort_raw == "asc")

            # ── Build snapshot from _recv_queue (non-destructive) ──────────────
            msgs = list(_recv_queue)

            # ── Apply filters ──────────────────────────────────────────────────
            if role_filter:
                msgs = [m for m in msgs if m.get("role") == role_filter]

            if peer_filter:
                # Match by raw.from field (direct name) OR via _peers registry
                # Build a set of matching peer names/ids
                def _msg_matches_peer(m):
                    raw_from = (m.get("raw") or {}).get("from", "")
                    if raw_from == peer_filter:
                        return True
                    # Also check if peer_filter is a peer_id in _peers that maps to this agent_name
                    pinfo = _peers.get(peer_filter)
                    if pinfo:
                        aname = pinfo.get("agent_name") or pinfo.get("name") or ""
                        if raw_from == aname:
                            return True
                    return False
                msgs = [m for m in msgs if _msg_matches_peer(m)]

            if received_after is not None:
                try:
                    ra_ts = float(received_after)
                    msgs = [m for m in msgs if m.get("received_at", 0) > ra_ts]
                except (ValueError, TypeError):
                    pass  # ignore unparseable received_after

            # ── Sort ──────────────────────────────────────────────────────────
            msgs.sort(key=lambda m: m.get("received_at", 0), reverse=not sort_asc)

            # ── Pagination ────────────────────────────────────────────────────
            total = len(msgs)
            sliced   = msgs[offset:]
            has_more = len(sliced) > limit
            page     = sliced[:limit]
            next_offset = offset + limit if has_more else None

            resp = {
                "messages":    page,
                "total":       total,
                "has_more":    has_more,
                "next_offset": next_offset if next_offset is not None else offset + len(page),
            }
            self._json(resp)


        # ── GET /trust/vouch — list vouch_chain entries (v2.27) ─────────────
        elif p == "/trust/vouch":
            try:
                limit_raw  = qs.get("limit",  ["50"])[0]
                offset_raw = qs.get("offset", ["0"])[0]
                try:
                    limit = max(1, min(int(limit_raw), 200))
                except ValueError:
                    limit = 50
                try:
                    offset = max(0, int(offset_raw))
                except ValueError:
                    offset = 0
            except Exception:
                limit, offset = 50, 0

            total   = len(_vouch_chain)
            page    = _vouch_chain[offset: offset + limit]
            self._json({
                "ok":     True,
                "vouches": page,
                "count":   len(page),
                "total":   total,
                "pagination": {
                    "limit":   limit,
                    "offset":  offset,
                    "has_more": (offset + limit) < total,
                    "next_offset": (offset + limit) if (offset + limit) < total else None,
                },
            })

        # ── v2.33: GET /identity/pubkey-discovery — resolve DID → pubkey (offline) ──
        elif p == "/identity/pubkey-discovery":
            """Resolve a DID string to its Ed25519 public key without any network call.

            v2.33: Supports did:acp: and did:key: schemes. Fully offline.

            Query param:  ?did=<did_string>
            Response:     {ok, did, scheme, public_key_b64, public_key_hex,
                           algorithm, derived_did_acp, derived_did_key, consistent}
            Error:        {ok:false, error, did}
            """
            qs = parse_qs(urlparse(self.path).query)
            did_param = (qs.get("did") or [None])[0]
            if not did_param:
                self._json({"ok": False, "error": "query param 'did' required"}, 400)
                return
            result = _resolve_did_to_pubkey(did_param)
            self._json(result, 200 if result.get("ok") else 400)

        # ── v2.16: GET /identity/delegation ──────────────────────────────────
        elif p == "/identity/delegation":
            # GET /identity/delegation
            # Returns current delegation chain status + entries.
            self._json({
                "ok":     True,
                "did":    _did_acp,
                "chain":  _delegation_chain_status(),
            })

        elif p.startswith("/context/") and p.endswith("/messages"):  # [stable] context message query (v2.15)
            # GET /context/<context_id>/messages
            # Query params:
            #   limit=<n>          max messages to return (default 50, max 200)
            #   since_seq=<n>      only return messages with server_seq > n (incremental fetch)
            #   sort=asc|desc      asc=oldest first (default), desc=newest first
            _ctx_parts = p.split("/")
            # Expect exactly: ['', 'context', '<ctx_id>', 'messages']
            if len(_ctx_parts) != 4:
                self._json({"error": "not found"}, 404)
            else:
                ctx_id = _ctx_parts[2]
                if not ctx_id:
                    body, sc = _err(ERR_INVALID_REQUEST, "context_id must not be empty", 400)
                    self._json(body, sc)
                else:
                    # Parse query params
                    try:
                        _ctx_lim = int(qs.get("limit", ["50"])[0])
                        if _ctx_lim <= 0:
                            raise ValueError
                        _ctx_lim = min(_ctx_lim, 200)
                    except (ValueError, TypeError):
                        self._json(_err(ERR_INVALID_REQUEST, "limit must be a positive integer", 400)[0], 400)
                        return
                    try:
                        ctx_since = int(qs.get("since_seq", ["0"])[0])
                        if ctx_since < 0:
                            raise ValueError
                    except (ValueError, TypeError):
                        self._json(_err(ERR_INVALID_REQUEST, "since_seq must be non-negative", 400)[0], 400)
                        return
                    ctx_sort = qs.get("sort", ["asc"])[0]
                    if ctx_sort not in ("asc", "desc"):
                        self._json(_err(ERR_INVALID_REQUEST, "sort must be asc or desc", 400)[0], 400)
                        return
                    # Filter _recv_queue by context_id (non-destructive snapshot)
                    _snap = list(_recv_queue)
                    matched = []
                    for _m in _snap:
                        _raw = _m.get("raw", _m)
                        _m_ctx = _raw.get("context_id") or _m.get("context_id")
                        if _m_ctx != ctx_id:
                            continue
                        _m_seq = int(_raw.get("server_seq") or _m.get("server_seq") or 0)
                        if _m_seq <= ctx_since:
                            continue
                        matched.append({
                            "message_id": _raw.get("message_id") or _m.get("message_id"),
                            "server_seq": _m_seq,
                            "ts":         _raw.get("ts") or _m.get("ts") or _m.get("received_at"),
                            "from":       _raw.get("from") or _m.get("peer_id"),
                            "role":       _raw.get("role"),
                            "parts":      _raw.get("parts", []),
                            "task_id":    _raw.get("task_id") or _m.get("task_id"),
                            "context_id": _m_ctx,
                        })
                    matched.sort(key=lambda x: x.get("server_seq") or 0,
                                 reverse=(ctx_sort == "desc"))
                    _ctx_page = matched[:_ctx_lim]
                    self._json({
                        "context_id": ctx_id,
                        "messages":   _ctx_page,
                        "count":      len(_ctx_page),
                        "total":      len(matched),
                        "has_more":   len(matched) > _ctx_lim,
                    })

        elif p == "/tasks":  # [stable] task list — filtering + dual pagination (v2.2/v0.9)
            # Query params:
            #   status=<status>        filter by status; comma-separated multi-value (v0.9)
            #                          e.g. status=submitted,working
            #   state=<status>         legacy alias for status
            #   page_size=<n>          A2A-aligned alias for limit (v0.9, default 20, max 100)
            #   limit=<n>              page size (default 20, max 100; legacy default 50, max 200)
            #   after=<task_id>        A2A-aligned alias for cursor (v0.9 keyset cursor)
            #   offset=<n>             offset-based page start (v2.2, default 0)
            #   cursor=<task_id>       legacy keyset cursor (exclusive; used when offset absent)
            #   peer_id=<peer_id>      filter by originating peer
            #   sort=asc|desc          sort order shorthand (v2.2); created_asc/created_desc also accepted
            #   created_after=<iso>    filter tasks created after this ISO-8601 timestamp
            #   updated_after=<iso>    filter tasks updated after this ISO-8601 timestamp

            VALID_STATUSES = {
                TASK_SUBMITTED, TASK_WORKING, TASK_COMPLETED,
                TASK_FAILED, TASK_CANCELED, TASK_INPUT_REQUIRED,
            }

            # ── Parameter parsing ──────────────────────────────────────────────
            # status= takes precedence over legacy state=
            # v0.9: supports comma-separated multi-value e.g. status=submitted,working
            status_raw   = qs.get("status", qs.get("state", [None]))[0]
            peer_filter  = qs.get("peer_id",       [None])[0]
            created_after = qs.get("created_after", [None])[0]
            updated_after = qs.get("updated_after", [None])[0]
            # v0.9: `after` is the A2A-aligned alias for `cursor`
            cursor        = qs.get("after", qs.get("cursor", [None]))[0]

            # sort: accept "asc"/"desc" (v2.2) and "created_asc"/"created_desc" (legacy)
            sort_raw   = qs.get("sort", ["desc"])[0]
            sort_order = "created_asc" if sort_raw in ("asc", "created_asc") else "created_desc"

            # offset-based pagination (v2.2): limit/page_size default 20, max 100
            # legacy cursor/after mode: limit/page_size default 20, max 100
            # v0.9: page_size is the A2A-aligned alias for limit (default 20, max 100 in all modes)
            use_offset = "offset" in qs
            if use_offset:
                try:
                    offset = max(0, int(qs.get("offset", ["0"])[0]))
                except ValueError:
                    offset = 0
                # page_size takes precedence over limit (v0.9 A2A alignment)
                _limit_raw = qs.get("page_size", qs.get("limit", ["20"]))[0]
                try:
                    limit = min(max(1, int(_limit_raw)), 100)
                except ValueError:
                    limit = 20
            else:
                offset = 0
                # v0.9: page_size takes precedence over limit; both default 20, max 100
                # (legacy cursor mode previously used default 50/max 200; unified to 20/100)
                _limit_raw = qs.get("page_size", qs.get("limit", ["20"]))[0]
                try:
                    limit = min(max(1, int(_limit_raw)), 100)
                except ValueError:
                    limit = 20

            # v0.9: parse comma-separated multi-value status filter
            status_set = set()
            if status_raw:
                for s in status_raw.split(","):
                    s = s.strip()
                    if s:
                        status_set.add(s)

            # Validate all status values
            invalid_statuses = status_set - VALID_STATUSES
            if invalid_statuses:
                body, status_code = _err(
                    ERR_INVALID_REQUEST,
                    f"Invalid status value(s): {', '.join(sorted(invalid_statuses))}. "
                    f"Valid values: {', '.join(sorted(VALID_STATUSES))}",
                    400,
                )
                self._json(body, status_code)
                return

            # ── Build + filter task list ───────────────────────────────────────
            tasks = list(_tasks.values())

            if status_set:
                tasks = [t for t in tasks if t.get("status") in status_set]
            if peer_filter:
                # BUG-014: peer_id may live at top-level or inside payload
                tasks = [t for t in tasks if
                         t.get("peer_id") == peer_filter or
                         t.get("payload", {}).get("peer_id") == peer_filter]
            if created_after:
                tasks = [t for t in tasks if t.get("created_at", "") > created_after]
            if updated_after:
                tasks = [t for t in tasks if
                         t.get("updated_at", t.get("created_at", "")) > updated_after]

            # ── Sort ──────────────────────────────────────────────────────────
            reverse = (sort_order != "created_asc")
            tasks.sort(key=lambda t: t.get("created_at", ""), reverse=reverse)

            # ── Pagination ────────────────────────────────────────────────────
            total = len(tasks)   # total matching (pre-page)

            if use_offset:
                # Offset-based (v2.2)
                sliced   = tasks[offset:]
                has_more = len(sliced) > limit
                page     = sliced[:limit]
                next_offset = offset + limit if has_more else None

                resp = {
                    "tasks":       page,
                    "total":       total,
                    "has_more":    has_more,
                }
                if next_offset is not None:
                    resp["next_offset"] = next_offset
            else:
                # Cursor/after-based pagination (v0.9 A2A-aligned: `after` param + `next_cursor` response)
                if cursor and cursor in _tasks:
                    try:
                        cursor_idx = next(i for i, t in enumerate(tasks) if t["id"] == cursor)
                        tasks = tasks[cursor_idx + 1:]
                    except StopIteration:
                        tasks = []
                has_more    = len(tasks) > limit
                page        = tasks[:limit]
                # v0.9: next_cursor is always present (null when no more pages)
                next_cursor = page[-1]["id"] if has_more and page else None

                resp = {
                    "tasks":       page,
                    "count":       len(page),
                    "total":       total,
                    "has_more":    has_more,
                    "next_cursor": next_cursor,
                }

            self._json(resp)

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
                                self.wfile.write(_sse_format(evt))  # v2.3: named event type
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
            elif rest.endswith("/audit-log"):
                # v2.52: GET /tasks/{id}/audit-log — immutable per-task audit trail
                task_id = rest[:-len("/audit-log")]
                task = _tasks.get(task_id)
                if not task:
                    self._json({"error": "task not found"}, 404)
                else:
                    audit = task.get("audit_log", [])
                    # Support ?since_seq=<N> for incremental polling
                    try:
                        since_seq = int(qs.get("since_seq", ["-1"])[0])
                    except (ValueError, KeyError):
                        since_seq = -1
                    if since_seq >= 0:
                        audit = [e for e in audit if e.get("seq", 0) > since_seq]
                    limit = int(qs.get("limit", ["200"])[0])
                    audit = audit[:limit]
                    self._json({
                        "task_id":   task_id,
                        "status":    task["status"],
                        "audit_log": audit,
                        "total":     len(task.get("audit_log", [])),
                    })
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

        elif p == "/ws/stream":  # v2.12: WebSocket native push stream
            upgrade = self.headers.get("Upgrade", "").lower()
            if upgrade != "websocket":
                self._json({"error": "WebSocket upgrade required", "hint": "Set 'Upgrade: websocket' header"}, 426)
                return
            # Delegate to WS handler (runs in this thread — blocking)
            self.close_connection = True
            _handle_ws_stream(self)

        # ── GET /skills/<id>/status — per-skill availability probe (v2.29) ──────
        elif p.startswith("/skills/") and p.endswith("/status"):
            skill_id_req = p[len("/skills/"):-len("/status")]
            if not skill_id_req:
                self._json(_err(ERR_INVALID_REQUEST, "skill id must not be empty", 400)[0], 400)
                return
            agent_card  = _status.get("agent_card") or {}
            all_skills  = list(agent_card.get("skills", []))
            matched     = None
            for s in all_skills:
                sid = s.get("id", "") if isinstance(s, dict) else str(s)
                if sid == skill_id_req:
                    matched = s
                    break
            if matched is None:
                self._json(
                    _err(ERR_NOT_FOUND, f"skill '{skill_id_req}' not found in agent card", 404)[0],
                    404,
                )
                return
            # Determine availability: runtime (permanent=False) cap/access limitation → unavailable
            # v2.29: merge runtime overrides from PATCH /skills/<id>/limitations
            reason    = None
            available = True
            base_lims = matched.get("limitations", []) if isinstance(matched, dict) else []
            override_lims = _skill_limitations_overrides.get(skill_id_req)
            if override_lims is not None:
                # Override replaces the declared limitations entirely
                lims = override_lims
            else:
                lims = base_lims
            for lim in lims:
                if isinstance(lim, str):
                    continue
                if lim.get("permanent") is False and lim.get("kind") in ("capability", "access"):
                    available = False
                    reason    = lim.get("message") or lim.get("code") or "runtime limitation active"
                    break
            self._json({
                "skill_id":     skill_id_req,
                "available":    available,
                "reason":       reason,
                "limitations":  lims,              # v2.29: include resolved limitations in response
                "last_checked": _now(),
            })

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
            # v2.13: ?since=<seq> replay — send missed events before joining live stream
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            since_seq = None
            try:
                since_seq = int(qs.get("since", [None])[0])
            except (TypeError, ValueError):
                pass
            q = deque()
            if since_seq is not None:
                with _event_log_lock:
                    replay = [e for e in _event_log if e.get("seq", 0) > since_seq]
                for evt in replay:
                    try:
                        self.wfile.write(_sse_format(evt))
                    except Exception:
                        break
                try:
                    self.wfile.flush()
                except Exception:
                    return
            _sse_subscribers.append(q)
            try:
                while True:
                    if q:
                        evt = q.popleft()
                        self.wfile.write(_sse_format(evt))  # v2.3: named event type
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

        # ── v2.16: Delegation Chain POST endpoints ────────────────────────────
        if p == "/identity/delegate":
            # POST /identity/delegate
            # Body: {"delegator_did": "did:acp:...", "scope": [...], "expires_at": <unix>}
            import time as _time2
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            except Exception:
                body = {}
            delegator_did = body.get("delegator_did", "")
            scope         = body.get("scope", ["send", "receive"])
            expires_at    = float(body.get("expires_at", _time2.time() + 86400))
            if not delegator_did.startswith("did:"):
                self._json({"ok": False, "error": "delegator_did must be a valid DID"}, 400)
            elif not _ed25519_private:
                self._json({"ok": False, "error": "identity not loaded; start with --identity"}, 400)
            else:
                try:
                    entry = _build_delegation_entry(delegator_did, scope, expires_at)
                    global _delegation_chain
                    _delegation_chain = [e for e in _delegation_chain
                                         if e.get("delegator_did") != delegator_did]
                    _delegation_chain.append(entry)
                    log.info(f"[v2.16] delegation added: delegator={delegator_did} scope={scope}")
                    self._json({"ok": True, "entry": entry,
                                "delegation_chain_size": len(_delegation_chain)})
                except Exception as exc:
                    self._json({"ok": False, "error": str(exc)}, 500)
            return

        elif p == "/identity/pubkey-discovery":
            # POST /identity/pubkey-discovery — resolve DID → pubkey (v2.33)
            # Body: {"did": "<did_string>"} or {"dids": ["<did1>", "<did2>", ...]} (batch)
            try:
                body = self._read_body()
            except Exception as e:
                self._json({"error": f"invalid JSON: {e}"}, 400)
                return

            # Batch mode: {"dids": [...]}
            if "dids" in body:
                dids = body["dids"]
                if not isinstance(dids, list) or len(dids) > 50:
                    self._json({"ok": False, "error": "'dids' must be a list (max 50)"}, 400)
                    return
                results = [_resolve_did_to_pubkey(d) for d in dids]
                self._json({"ok": True, "results": results, "count": len(results)})
                return

            # Single mode: {"did": "..."}
            did_param = body.get("did")
            if not did_param:
                self._json({"ok": False, "error": "'did' field required"}, 400)
                return
            result = _resolve_did_to_pubkey(did_param)
            self._json(result, 200 if result.get("ok") else 400)

        elif p == "/identity/delegation/verify":
            # POST /identity/delegation/verify
            # Body: {"entry": {...}} — verify a single delegation entry's Ed25519 signature.
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            except Exception:
                body = {}
            entry = body.get("entry", {})
            if not entry:
                self._json({"ok": False, "error": "entry required"}, 400)
            else:
                valid = _verify_delegation_entry(entry)
                self._json({"ok": True, "valid": valid, "entry": entry})
            return
        # ── end v2.16 ─────────────────────────────────────────────────────────

        # ── v2.17: POST /availability/heartbeat ───────────────────────────────
        if p == "/availability/heartbeat":
            global _availability
            # Stamp last_active_at = now; recompute next_active_at from schedule if present
            now_str = _now()
            _availability = {**_availability, "last_active_at": now_str}
            # If caller provided a body, merge allowed fields
            try:
                body = self._read_body()
                allowed_fields = {"mode", "interval_seconds", "schedule",
                                  "next_active_at", "task_latency_max_seconds", "timezone"}
                for k, v in body.items():
                    if k in allowed_fields:
                        _availability[k] = v
            except Exception:
                pass  # No body or invalid JSON — just stamp last_active_at
            # Auto-compute next_active_at from schedule
            schedule = _availability.get("schedule")
            if schedule and not _availability.get("next_active_at"):
                nxt = _next_cron_datetime(schedule)
                if nxt:
                    _availability["next_active_at"] = nxt.strftime("%Y-%m-%dT%H:%M:%SZ")
            elif schedule:
                # Recompute next even if previously set (heartbeat = new cycle starts)
                nxt = _next_cron_datetime(schedule)
                if nxt:
                    _availability["next_active_at"] = nxt.strftime("%Y-%m-%dT%H:%M:%SZ")
            log.info(f"[v2.17] heartbeat stamped: last_active_at={now_str} "
                     f"next_active_at={_availability.get('next_active_at')}")
            self._json({
                "ok":            True,
                "last_active_at": now_str,
                "next_active_at": _availability.get("next_active_at"),
                "availability":   dict(_availability),
            })
            return
        # ── end v2.17 ─────────────────────────────────────────────────────────

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

                # ── v2.32: HTTP-level message idempotency (30s TTL dedup) ────
                # Only applies when the client supplies their own message_id.
                # Auto-generated IDs are never duplicates.
                if body.get("message_id"):
                    _is_dup, _cached_seq = _http_dedup_check(message_id)
                    if _is_dup:
                        self._json({
                            "ok":           True,
                            "deduplicated": True,
                            "message_id":   message_id,
                            "server_seq":   _cached_seq,
                        })
                        return

                # ── Ed25519 optional signature verification (v0.8) ───────────
                # If the caller supplies a `signature` block and the relay has a
                # peer_card with identity.public_key, verify the Ed25519 signature.
                # * No signature → pass through (backward compatible).
                # * Signature + known public_key → verify; 400 on failure/replay.
                # * Signature + no known public_key → skip (can't verify).
                _sig_obj = body.get("signature")
                if _sig_obj and _IDENTITY_EXT_AVAILABLE:
                    # Try to resolve the sender's public key from peer_card
                    _peer_card_id = (_status.get("peer_card") or {}).get("identity", {})
                    _sender_pubkey = _peer_card_id.get("public_key") if _peer_card_id else None
                    if _sender_pubkey:
                        import time as _t_sig
                        _ts_val = body.get("timestamp")
                        # Replay-window check (strict: timestamp must be present)
                        if _ts_val is not None:
                            _delta = abs(_t_sig.time() - float(_ts_val))
                            if _delta > _identity_ext.REPLAY_WINDOW_SECONDS:
                                e_body, e_code = _err(
                                    "ERR_REPLAY_DETECTED",
                                    "replay detected: timestamp outside ±300s window",
                                    400,
                                    failed_message_id=_client_msg_id,
                                )
                                self._json(e_body, e_code)
                                return
                        # Cryptographic verification
                        _aug_sig = dict(_sig_obj)
                        if _ts_val is not None:
                            _aug_sig["_timestamp"] = _ts_val
                        _v = _identity_ext.verify_signature(
                            _sender_pubkey, _aug_sig, parts, message_id
                        )
                        if _v is False:
                            e_body, e_code = _err(
                                "ERR_INVALID_SIGNATURE",
                                "invalid_signature: Ed25519 signature verification failed",
                                400,
                                failed_message_id=_client_msg_id,
                            )
                            self._json(e_body, e_code)
                            return
                        elif _v is True:
                            log.debug(f"✅ Ed25519 signature verified on {message_id}")
                        # _v is None → library unavailable → pass through

                # v2.38: message priority — validate and default to "normal"
                _priority_raw = body.get("priority", "normal")
                if _priority_raw not in VALID_PRIORITIES:
                    e_body, e_code = _err(
                        ERR_INVALID_REQUEST,
                        f"invalid priority '{_priority_raw}': must be one of {sorted(VALID_PRIORITIES)}",
                        400,
                        failed_message_id=_client_msg_id,
                    )
                    self._json(e_body, e_code)
                    return
                # Update priority counters (sent messages)
                _status["priority_counts"][_priority_raw] = (
                    _status["priority_counts"].get(_priority_raw, 0) + 1
                )

                msg = {
                    "type":       "acp.message",
                    "message_id": message_id,
                    "server_seq": _next_seq(),
                    "ts":         _now(),
                    "from":       _status.get("agent_name", "unknown"),
                    "role":       role_raw,
                    "priority":   _priority_raw,                           # v2.38
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
                        "context_id": msg.get("context_id"),   # v2.15: include context_id for context query
                        "direction":  "outbound",
                    })
                    # v2.15: persist outbound message to _recv_queue so /context/<id>/messages
                    # and /messages can surface sent messages (enables full conversation history).
                    _outbound_entry = {
                        "peer_id":    "local",
                        "direction":  "outbound",
                        "received_at": _now(),
                        "raw": {
                            "message_id":  message_id,
                            "server_seq":  seq,
                            "ts":          _now(),
                            "from":        _status.get("agent_name", "local"),
                            "role":        role_raw,
                            "parts":       parts,
                            "task_id":     msg.get("task_id"),
                            "context_id":  msg.get("context_id"),
                        },
                    }
                    _recv_queue.append(_outbound_entry)
                    # v2.32: store server_seq in dedup cache so replay returns it
                    if body.get("message_id"):
                        _http_dedup_record_seq(message_id, seq)

                    # v2.36: send acp.read receipt — signal to peer that we consumed their last message
                    _last_recv_id = _status.get("last_received_message_id")
                    if _last_recv_id:
                        _read_frame = json.dumps({
                            "type":       "acp.read",
                            "message_id": _last_recv_id,
                            "from":       _status.get("agent_name", "ACP-Agent"),
                            "ts":         _now(),
                        }, ensure_ascii=False)
                        _read_ws = None
                        _target_pid = _req_peer_id
                        if _target_pid and _target_pid in _peers:
                            _read_ws = _peers[_target_pid].get("ws")
                        if _read_ws is None:
                            _conn_peers = [p for p in _peers.values() if p.get("connected") and p.get("ws")]
                            if _conn_peers:
                                _read_ws = _conn_peers[0]["ws"]
                        if _read_ws and _loop:
                            try:
                                asyncio.run_coroutine_threadsafe(
                                    _read_ws.send(_read_frame), _loop
                                ).result(timeout=3)
                                # Clear after sending so we don't repeat the same read receipt
                                _status["last_received_message_id"] = None
                                log.debug(f"[read_receipt] Sent acp.read for {_last_recv_id}")
                            except Exception as _re:
                                log.debug(f"[read_receipt] Failed to send acp.read: {_re}")

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

        # /message:typing — v2.37: send typing indicator to peer
        elif p == "/message:typing":
            try:
                body = self._read_body()
                _typing_state = body.get("typing", True)   # True = started, False = stopped
                _req_peer_id_t = body.get("peer_id")
                _frame = json.dumps({
                    "type":   "acp.typing",
                    "from":   _status.get("agent_name", "ACP-Agent"),
                    "typing": bool(_typing_state),
                    "ts":     _now(),
                }, ensure_ascii=False)
                # Resolve target WS
                _typing_ws = None
                if _req_peer_id_t and _req_peer_id_t in _peers:
                    _typing_ws = _peers[_req_peer_id_t].get("ws")
                if _typing_ws is None:
                    _conn_t = [p for p in _peers.values() if p.get("connected") and p.get("ws")]
                    if _conn_t:
                        _typing_ws = _conn_t[0]["ws"]
                if _typing_ws is None:
                    e_body, e_code = _err(ERR_NOT_CONNECTED, "no connected peer", 503)
                    self._json(e_body, e_code)
                    return
                asyncio.run_coroutine_threadsafe(
                    _typing_ws.send(_frame), _loop
                ).result(timeout=3)
                log.debug(f"[typing] Sent acp.typing typing={_typing_state}")
                self._json({"ok": True, "typing": bool(_typing_state), "ts": _now()})
            except Exception as e:
                e_body, e_code = _err(ERR_INTERNAL, str(e), 500)
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
                # Pre-extract client-supplied message_id for failed_message_id in errors
                _client_msg_id = body.get("message_id")  # may be None; used in error envelopes
                peer_info = _peers.get(peer_id)
                if not peer_info:
                    e_body, e_code = _err("ERR_NOT_FOUND",
                                          f"peer '{peer_id}' not found", 404,
                                          failed_message_id=_client_msg_id)
                    self._json(e_body, e_code)
                    return
                if not peer_info.get("connected"):
                    e_body, e_code = _err(ERR_NOT_CONNECTED,
                                          f"peer '{peer_id}' is not connected", 503,
                                          failed_message_id=_client_msg_id)
                    self._json(e_body, e_code)
                    return
                if peer_info.get("ws") is None:
                    # Peer registered but WS handshake not yet complete (connecting race)
                    e_body, e_code = _err("ERR_PEER_CONNECTING",
                                          f"peer '{peer_id}' is connecting, retry shortly", 503,
                                          failed_message_id=_client_msg_id)
                    self._json(e_body, e_code)
                    return

                parts = body.get("parts")
                if not parts:
                    text = body.get("text") or body.get("content") or ""
                    parts = [_make_text_part(str(text))] if text else []
                    if not parts:
                        e_body, e_code = _err(ERR_INVALID_REQUEST,
                                              "provide 'parts' or 'text'", 400,
                                              failed_message_id=_client_msg_id)
                        self._json(e_body, e_code)
                        return

                message_id = body.get("message_id") or _make_id("msg")

                # ── v2.32: HTTP-level message idempotency (30s TTL dedup) ────
                if body.get("message_id"):
                    _is_dup, _cached_seq = _http_dedup_check(message_id)
                    if _is_dup:
                        self._json({
                            "ok":           True,
                            "deduplicated": True,
                            "message_id":   message_id,
                            "peer_id":      peer_id,
                            "server_seq":   _cached_seq,
                        })
                        return

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
                    e_body, e_code = _err(ERR_MSG_TOO_LARGE,
                                          f"message too large (max {MAX_MSG_BYTES} bytes)", 413,
                                          failed_message_id=message_id)
                    self._json(e_body, e_code)
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
                        e_body, e_code = _err(ERR_NOT_CONNECTED,
                                              f"peer '{peer_id}' connection lost: {ws_err}", 503,
                                              failed_message_id=message_id)
                        self._json(e_body, e_code)
                        return
                else:
                    e_body, e_code = _err(ERR_NOT_CONNECTED,
                                          f"peer '{peer_id}' WebSocket is not active; P2P connection lost", 503,
                                          failed_message_id=message_id)
                    self._json(e_body, e_code)
                    return

                peer_info["messages_sent"] = peer_info.get("messages_sent", 0) + 1
                _status["messages_sent"] += 1
                # v2.32: store server_seq in dedup cache so replay returns it
                if body.get("message_id"):
                    _http_dedup_record_seq(message_id, msg["server_seq"])
                self._json({"ok": True, "message_id": message_id, "peer_id": peer_id,
                            "server_seq": msg["server_seq"]})

            except ConnectionError as e:
                _fmid = locals().get("message_id") or locals().get("_client_msg_id")
                e_body, e_code = _err(ERR_NOT_CONNECTED, str(e), 503,
                                      failed_message_id=_fmid)
                self._json(e_body, e_code)
            except Exception as e:
                _fmid = locals().get("message_id") or locals().get("_client_msg_id")
                e_body, e_code = _err(ERR_INTERNAL, str(e), 500,
                                      failed_message_id=_fmid)
                self._json(e_body, e_code)

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

        # ── POST /peers/{id}/ping — application-layer liveness probe (v2.25) ─
        # Sends an ACP ping message over the peer's WebSocket and measures RTT.
        # Unlike WebSocket-level ping/pong (transport layer), this verifies that
        # the remote relay's message loop is alive and responding at the ACP level.
        #
        # Request body (optional JSON):
        #   {"timeout": 10.0}  — max seconds to wait for pong (default 10, max 30)
        #
        # Response:
        #   200 {"ok": true,  "peer_id": "peer_001", "rtt_ms": 42.3, "status": "alive", "nonce": "ping_xxx"}
        #   503 {"ok": false, "peer_id": "peer_001", "error_code": "ERR_NOT_CONNECTED", ...}
        #   404 {"ok": false, "error_code": "ERR_PEER_NOT_FOUND", ...}
        #   408 {"ok": false, "error_code": "ERR_PING_TIMEOUT",   "rtt_ms": null, "status": "timeout"}
        #
        # The peer must support ACP ping response (capabilities.peer_ping=true) for
        # measured RTT to be meaningful; otherwise the endpoint acts as a connection-check only.
        elif p.startswith("/peers/") and p.endswith("/ping") and p.count("/") == 3:
            peer_id = p[len("/peers/"):-len("/ping")]
            try:
                # Parse optional request body (timeout override)
                try:
                    body = self._read_body()
                    requested_timeout = float(body.get("timeout", 10.0))
                    requested_timeout = max(1.0, min(requested_timeout, 30.0))
                except Exception:
                    requested_timeout = 10.0

                # Validate peer exists
                peer_info = _peers.get(peer_id)
                if not peer_info:
                    e_body, e_code = _err("ERR_PEER_NOT_FOUND",
                                          f"peer '{peer_id}' not found", 404)
                    self._json(e_body, e_code)
                    return

                # Validate peer is connected and WS is ready
                if not peer_info.get("connected"):
                    e_body, e_code = _err(ERR_NOT_CONNECTED,
                                          f"peer '{peer_id}' is not connected", 503)
                    self._json(e_body, e_code)
                    return

                ws = peer_info.get("ws")
                if ws is None:
                    e_body, e_code = _err("ERR_PEER_CONNECTING",
                                          f"peer '{peer_id}' is connecting, retry shortly", 503)
                    self._json(e_body, e_code)
                    return

                # Build ping message
                nonce = _make_id("ping")
                ping_ts = time.time()
                ping_msg = json.dumps({
                    "type":    "acp.ping",
                    "nonce":   nonce,
                    "from":    _status.get("agent_name", "ACP-Agent"),
                    "ts":      _now(),
                }, ensure_ascii=False)

                # Register a pending pong Future keyed by nonce
                pong_future = _loop.create_future()
                _pending_pongs[nonce] = pong_future

                # Send ping over peer WS
                try:
                    send_fut = asyncio.run_coroutine_threadsafe(ws.send(ping_msg), _loop)
                    send_fut.result(timeout=5)
                except Exception as send_err:
                    _pending_pongs.pop(nonce, None)
                    _unregister_peer(peer_id)
                    _status["peer_count"] = sum(1 for p2 in _peers.values() if p2["connected"])
                    e_body, e_code = _err(ERR_NOT_CONNECTED,
                                          f"peer '{peer_id}' send failed: {send_err}", 503)
                    self._json(e_body, e_code)
                    return

                # Wait for pong (with timeout)
                try:
                    asyncio.run_coroutine_threadsafe(
                        asyncio.wait_for(asyncio.shield(pong_future), timeout=requested_timeout),
                        _loop
                    ).result(timeout=requested_timeout + 2)
                    rtt_ms = round((time.time() - ping_ts) * 1000, 2)
                    _pending_pongs.pop(nonce, None)

                    # Update peer last_ping stats
                    peer_info["last_ping_rtt_ms"] = rtt_ms
                    peer_info["last_ping_at"]     = _now()
                    peer_info["ping_count"]        = peer_info.get("ping_count", 0) + 1

                    self._json({
                        "ok":      True,
                        "peer_id": peer_id,
                        "nonce":   nonce,
                        "rtt_ms":  rtt_ms,
                        "status":  "alive",
                    })

                except (asyncio.TimeoutError, concurrent.futures.TimeoutError):
                    _pending_pongs.pop(nonce, None)
                    self._json({
                        "ok":         False,
                        "peer_id":    peer_id,
                        "nonce":      nonce,
                        "rtt_ms":     None,
                        "status":     "timeout",
                        "error_code": "ERR_PING_TIMEOUT",
                        "error":      f"no pong received within {requested_timeout}s",
                    }, 408)

            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)

        # ── POST /debug/inject-peer-card — test helper: inject peer_card directly ─
        elif p == "/debug/inject-peer-card":
            # Test-only endpoint: directly set _status["peer_card"] without a WS connection.
            # Allows identity integration tests to inject a peer AgentCard via HTTP.
            try:
                body = self._read_body()
                card = body.get("card")
                if not card or not isinstance(card, dict):
                    self._json({"ok": False, "error": "card field required"}, 400)
                    return
                _status["peer_card"] = card
                log.info(f"[debug] peer_card injected via /debug/inject-peer-card: "
                         f"name={card.get('name')} identity={bool(card.get('identity'))}")
                self._json({"ok": True, "peer_card": card})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)

        # ── POST /debug/inject — test-mode: inject message + auto-register peer (v2.48) ─
        elif p == "/debug/inject":
            """
            Test-only endpoint (--test-mode required).
            Injects a message into _recv_queue AND auto-registers the sender as a peer.

            Body:
              from          — sender agent name (required)
              parts         — list of part objects (required)
              message_id    — optional, generated if absent
              context_id    — optional
              task_id       — optional
              priority      — optional (default: normal)
              direction     — optional (default: inbound)
              server_seq    — optional, auto-assigned if absent

            Response 200: {ok, message_id, peer_id, server_seq}
            Response 403: test-mode not enabled
            Response 400: missing required fields
            """
            if not _test_mode:
                self._json({"ok": False, "error": "POST /debug/inject requires --test-mode",
                            "error_code": "ERR_TEST_MODE_REQUIRED"}, 403)
                return
            try:
                body = self._read_body()
                from_name = (body.get("from") or "").strip()
                parts = body.get("parts")
                if not from_name:
                    self._json({"ok": False, "error": "from field required",
                                "error_code": "ERR_INVALID_REQUEST"}, 400)
                    return
                if not parts or not isinstance(parts, list):
                    self._json({"ok": False, "error": "parts field required (list)",
                                "error_code": "ERR_INVALID_REQUEST"}, 400)
                    return

                # Auto-register the sender as a peer if not already registered
                peer_id = None
                for pid, pinfo in _peers.items():
                    if pinfo.get("agent_name") == from_name or pinfo.get("name") == from_name:
                        peer_id = pid
                        break
                if peer_id is None:
                    peer_id = _make_peer_id()
                    _register_peer(peer_id=peer_id, link=f"acp://debug/{peer_id}")
                    _peers[peer_id]["agent_name"] = from_name
                    _peers[peer_id]["name"] = from_name
                    _peers[peer_id]["connected"] = False  # not a real WS connection
                    _peers[peer_id]["debug_injected"] = True
                    log.info(f"[debug/inject] auto-registered peer: {from_name} → {peer_id}")

                # v2.51: trust_override — set peer trust fields for tier-based testing
                # Accepts: {score_override, verified_identity, card_sig_valid, did_consistent, ping_rtt_ms, vouch}
                trust_override = body.get("trust_override") if isinstance(body, dict) else None
                if trust_override and isinstance(trust_override, dict):
                    # card_sig / did_consistent
                    if trust_override.get("card_sig_valid"):
                        _peers[peer_id]["card_verification"] = {"valid": True, "did_consistent": bool(trust_override.get("did_consistent", True))}
                    # ping RTT
                    if "ping_rtt_ms" in trust_override:
                        _peers[peer_id]["last_ping_rtt_ms"] = trust_override["ping_rtt_ms"]
                    # message history count
                    if "message_count" in trust_override:
                        _peers[peer_id]["messages_sent"] = trust_override["message_count"]
                    # verified_identity signal: inject into peer's AgentCard trust.signals
                    if trust_override.get("verified_identity"):
                        existing_card = _peers[peer_id].get("agent_card") or {}
                        existing_trust = existing_card.get("trust") or {}
                        existing_sigs  = list(existing_trust.get("signals") or [])
                        # Add verified_identity signal if not already present
                        if not any(s.get("type") == "verified_identity" or s.get("kind") == "verified_identity" for s in existing_sigs):
                            existing_sigs.append({"type": "verified_identity", "kind": "verified_identity"})
                        existing_trust["signals"] = existing_sigs
                        existing_card["trust"] = existing_trust
                        _peers[peer_id]["agent_card"] = existing_card

                # Build message entry
                import time as _time_
                msg_id = body.get("message_id") or f"dbg_{int(_time_.time()*1000):x}"
                direction = body.get("direction", "inbound")
                priority = body.get("priority", "normal")
                context_id = body.get("context_id")
                task_id = body.get("task_id")

                # Assign server_seq
                import time as _time
                seq = body.get("server_seq") or int(_time.time() * 1000)
                ts_now = _now()
                entry = {
                    "message_id":  msg_id,
                    "server_seq":  seq,
                    "direction":   direction,
                    "from":        from_name,
                    "to":          _status.get("agent_name", "ACP-Agent"),
                    "parts":       parts,
                    "context_id":  context_id,
                    "task_id":     task_id,
                    "priority":    priority,
                    "peer_id":     peer_id,
                    "received_at": ts_now,
                    "sent_at":     ts_now if direction == "outbound" else None,
                    "raw": {
                        "from":       from_name,
                        "parts":      parts,
                        "message_id": msg_id,
                        "server_seq": seq,
                        "context_id": context_id,
                        "task_id":    task_id,
                        "priority":   priority,
                    },
                }

                _recv_queue.append(entry)
                _persist(entry)

                log.info(f"[debug/inject] injected msg {msg_id} from={from_name} peer={peer_id}")
                self._json({
                    "ok":         True,
                    "message_id": msg_id,
                    "peer_id":    peer_id,
                    "server_seq": entry["server_seq"],
                })
            except Exception as e:
                log.exception(f"[debug/inject] {e}")
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
                # v1.4: connect via automatic 3-level NAT traversal strategy
                # Level 1 (direct) → Level 2 (DCUtR hole punch) → Level 3 (relay)
                # transport_level field is written to peer info after resolution.
                agent_name = _status.get("agent_name", "ACP-Agent")
                def _do_connect_nat():
                    async def _run():
                        _pid, transport_level = await _connect_with_nat_traversal(
                            peer_link, agent_name, role="guest"
                        )
                        # Write transport_level into the pre-registered peer entry
                        if peer_id in _peers:
                            _peers[peer_id]["transport_level"] = transport_level
                        log.info(f"[NAT] peer {peer_id} connected via transport_level={transport_level}")
                    asyncio.run_coroutine_threadsafe(_run(), _loop)
                threading.Thread(target=_do_connect_nat, daemon=True).start()
                self._json({"ok": True, "peer_id": peer_id,
                            "connecting_to": peer_link, "name": peer_name or peer_id})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)

        # ── POST /peers/broadcast — send a message to ALL connected peers (v2.22) ─
        elif p == "/peers/broadcast":  # [stable] broadcast to all active peers
            try:
                body = self._read_body()

                # Validate role
                _VALID_ROLES = {"user", "agent"}
                role_raw = body.get("role")
                if role_raw not in _VALID_ROLES:
                    e_body, e_code = _err(
                        ERR_INVALID_REQUEST,
                        "missing or invalid 'role' field (must be 'user' or 'agent')",
                    )
                    self._json(e_body, e_code)
                    return

                # Build parts
                parts = body.get("parts")
                if parts:
                    ok, err = _validate_parts(parts)
                    if not ok:
                        e_body, e_code = _err(ERR_INVALID_REQUEST, err)
                        self._json(e_body, e_code)
                        return
                else:
                    text = body.get("text") or body.get("content") or ""
                    parts = [_make_text_part(str(text))] if text else []
                    if not parts:
                        e_body, e_code = _err(
                            ERR_INVALID_REQUEST,
                            "missing required field: provide 'parts' (list) or 'text' (string)",
                        )
                        self._json(e_body, e_code)
                        return

                context_id = body.get("context_id") or _make_id()

                # v2.23: optional target_peers[] for subset broadcast
                target_peers_filter = body.get("target_peers")
                if target_peers_filter is not None:
                    if not isinstance(target_peers_filter, list):
                        e_body, e_code = _err(ERR_INVALID_REQUEST, "'target_peers' must be a list of peer_id strings")
                        self._json(e_body, e_code)
                        return
                    # Validate all requested peer ids exist
                    unknown = [pid for pid in target_peers_filter if pid not in _peers]
                    if unknown:
                        e_body, e_code = _err(ERR_INVALID_REQUEST, f"unknown peer_id(s) in target_peers: {unknown}")
                        self._json(e_body, e_code)
                        return
                    active_peers = [
                        pid for pid in target_peers_filter if _peers[pid].get("connected")
                    ]
                else:
                    active_peers = [
                        pid for pid, pinfo in _peers.items() if pinfo.get("connected")
                    ]

                if not active_peers:
                    self._json(
                        {"ok": False, "error_code": "ERR_NO_PEERS",
                         "error": "no connected peers to broadcast to",
                         "delivered": 0, "failed": 0, "results": []},
                        503,
                    )
                    return

                results = []
                delivered = 0
                failed = 0

                for pid in active_peers:
                    msg_id = _make_id()
                    # Use the same wire format as /message:send
                    wire_msg = {
                        "type":       "acp.message",
                        "message_id": msg_id,
                        "server_seq": _next_seq(),
                        "ts":         _now(),
                        "from":       _status.get("agent_name", "unknown"),
                        "role":       role_raw,
                        "parts":      parts,
                        "broadcast":  True,
                    }
                    if body.get("task_id"):
                        wire_msg["task_id"] = body["task_id"]
                    if context_id:
                        wire_msg["context_id"] = context_id

                    ok_send = False
                    err_send = None
                    try:
                        # Reuse _ws_send_sync: handles lock, signature, offline queue
                        _ws_send_sync(wire_msg, peer_id=pid)
                        ok_send = True
                        delivered += 1
                    except Exception as ex:
                        err_send = str(ex)
                        failed += 1

                    results.append({
                        "peer_id": pid,
                        "message_id": msg_id,
                        "ok": ok_send,
                        "error": err_send,
                    })

                _broadcast_sse_event("message", {
                    "message_id": _make_id(),
                    "role": role_raw,
                    "parts": parts,
                    "broadcast": True,
                    "delivered": delivered,
                    "failed": failed,
                })

                # v2.23: record broadcast in history log
                broadcast_record = {
                    "broadcast_id": context_id,
                    "ts": _now(),
                    "role": role_raw,
                    "parts": parts,
                    "target_peers": target_peers_filter,   # None = all peers
                    "total_peers": len(active_peers),
                    "delivered": delivered,
                    "failed": failed,
                    "results": results,
                }
                _broadcast_log.append(broadcast_record)
                if len(_broadcast_log) > _BROADCAST_LOG_MAX:
                    _broadcast_log.pop(0)

                self._json({
                    "ok": True,
                    "broadcast": True,
                    "delivered": delivered,
                    "failed": failed,
                    "total_peers": len(active_peers),
                    "results": results,
                    "broadcast_id": context_id,
                }, 200)
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
                # v2.49: authorization tier enforcement
                skill_id_for_tier = body.get("skill_id") or (payload.get("skill_id") if isinstance(payload, dict) else None)
                caller_peer_id    = body.get("peer_id") or body.get("from_peer_id")
                tier_ok, tier_reason = _check_authorization_tier(skill_id_for_tier, caller_peer_id)
                if not tier_ok:
                    self._json({
                        "ok":         False,
                        "error_code": ERR_AUTHORIZATION_TIER,
                        "error":      tier_reason,
                        "skill_id":   skill_id_for_tier,
                        "peer_id":    caller_peer_id,
                    }, 403)
                    return
                # v2.50: param_constraints enforcement
                # (tier passed — audit entry recorded after task creation in skill_invoked)
                task_params = body.get("params") or (payload.get("params") if isinstance(payload, dict) else None)
                pc_ok, pc_violations = _check_param_constraints(skill_id_for_tier, task_params)
                if not pc_ok:
                    self._json({
                        "ok":             False,
                        "error_code":     ERR_PARAM_CONSTRAINT,
                        "error":          f"task params violate skill '{skill_id_for_tier}' constraints",
                        "skill_id":       skill_id_for_tier,
                        "violated_params": pc_violations,
                    }, 400)
                    return
                # v2.53: rate_limit enforcement
                rl_ok, rl_detail = _check_rate_limit(skill_id_for_tier, caller_peer_id)
                if not rl_ok:
                    self._json({
                        "ok":         False,
                        "error_code": ERR_RATE_LIMIT,
                        "error":      f"rate limit exceeded for skill '{skill_id_for_tier}'",
                        **rl_detail,
                    }, 429)
                    return
                # v2.51: T3 human_confirmation_required gate
                t3_confirm = _needs_human_confirmation(skill_id_for_tier)
                task = _create_task(payload,
                                    message_id=body.get("message_id"),
                                    task_id=body.get("task_id"),       # BUG-006 fix: pass client task_id
                                    context_id=body.get("context_id"), # v1.7: propagate context_id to SSE events
                                    initial_state=TASK_CONFIRMATION_PENDING if t3_confirm else None)
                # v2.52: audit skill_id + peer_id at task creation
                if skill_id_for_tier:
                    _audit_card_skills = (_status.get("agent_card") or {}).get("skills", [])
                    _audit_skill_obj   = next((s for s in _audit_card_skills if isinstance(s, dict) and s.get("id") == skill_id_for_tier), {})
                    _append_audit(task, "skill_invoked", {
                        "skill_id": skill_id_for_tier,
                        "peer_id":  caller_peer_id,
                        "tier":     _audit_skill_obj.get("authorization_tier"),
                    })
                if body.get("delegate", False):
                    _ws_send_sync({"type": "task.delegate", "message_id": _make_id(), "ts": _now(),
                                   "from": _status.get("agent_name"), "task_id": task["id"],
                                   "payload": task["payload"]})
                # v2.52: deprecation_warning — inject into response if skill is deprecated
                resp: dict = {"ok": True, "task": task}
                if skill_id_for_tier:
                    _card_skills = (_status.get("agent_card") or {}).get("skills", [])
                    skill_obj = next((s for s in _card_skills if isinstance(s, dict) and s.get("id") == skill_id_for_tier), {})
                    dep = skill_obj.get("deprecation_notice")
                    if dep:
                        resp["deprecation_warning"] = dep
                self._json(resp, 201)
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
        # v2.6: Two-phase cancel — first transitions to `cancelling` (SSE observable),
        #        then asynchronously completes to `canceled` (terminal).
        #        Idempotent: already cancelling/canceled → 200 immediately.
        #        Fills the semantic gap in A2A issues #1684/#1680 (no "being cancelled" state).
        elif p.startswith("/tasks/") and p.endswith(":cancel"):
            task_id = p[len("/tasks/"):-len(":cancel")]
            task = _tasks.get(task_id)
            if not task:
                self._json({"error": "task not found"}, 404)
            elif task["status"] in TERMINAL_STATES:
                # Already terminal (including canceled) — idempotent 200
                self._json({"ok": True, "task_id": task_id, "status": task["status"],
                            "note": "task already in terminal state"})
            elif task["status"] in CANCELLING_STATES:
                # Already mid-cancel — idempotent 200
                self._json({"ok": True, "task_id": task_id, "status": TASK_CANCELLING,
                            "note": "cancel already in progress"})
            else:
                # Phase 1: transition to `cancelling`, push SSE event immediately
                _update_task(task_id, TASK_CANCELLING)
                # Phase 2: asynchronously complete the cancel → `canceled`
                # For the reference implementation, cancellation is instantaneous;
                # real agents may need to signal their worker and await acknowledgment.
                def _do_cancel(tid):
                    import time as _time
                    _time.sleep(0.05)   # brief yield — allows SSE clients to observe `cancelling` before canceled
                    _update_task(tid, TASK_CANCELED)
                threading.Thread(target=_do_cancel, args=(task_id,), daemon=True).start()
                self._json({"ok": True, "task_id": task_id, "status": TASK_CANCELLING})

        # /tasks/{id}:confirm — v2.51: approve a confirmation_pending T3 task  [stable]
        # Transitions task from confirmation_pending → submitted, broadcasts SSE status event.
        # Idempotent: already submitted/terminal → 200 with note.
        elif p.startswith("/tasks/") and p.endswith(":confirm"):
            task_id = p[len("/tasks/"):-len(":confirm")]
            task = _tasks.get(task_id)
            if not task:
                self._json({"error": "task not found"}, 404)
            elif task["status"] in TERMINAL_STATES:
                self._json({"ok": True, "task_id": task_id, "status": task["status"],
                            "note": "task already in terminal state"})
            elif task["status"] == TASK_SUBMITTED:
                self._json({"ok": True, "task_id": task_id, "status": TASK_SUBMITTED,
                            "note": "task already confirmed/submitted"})
            elif task["status"] not in CONFIRMATION_PENDING_STATES:
                self._json({"ok": False,
                            "error_code": ERR_CONFIRM_NOT_PENDING,
                            "error": f"task '{task_id}' is not awaiting confirmation (status: {task['status']})"}, 409)
            else:
                # Approve: transition to submitted
                task.pop("confirmation_required", None)
                _append_audit(task, "confirmed", {"by": "human"})      # v2.52
                _update_task(task_id, TASK_SUBMITTED)
                self._json({"ok": True, "task_id": task_id, "status": TASK_SUBMITTED})

        # /tasks/{id}:reject — v2.51: reject a confirmation_pending T3 task  [stable]
        # Transitions task from confirmation_pending → failed, broadcasts SSE status event.
        elif p.startswith("/tasks/") and p.endswith(":reject"):
            task_id = p[len("/tasks/"):-len(":reject")]
            task = _tasks.get(task_id)
            if not task:
                self._json({"error": "task not found"}, 404)
            elif task["status"] in TERMINAL_STATES:
                self._json({"ok": True, "task_id": task_id, "status": task["status"],
                            "note": "task already in terminal state"})
            elif task["status"] not in CONFIRMATION_PENDING_STATES:
                self._json({"ok": False,
                            "error_code": ERR_CONFIRM_NOT_PENDING,
                            "error": f"task '{task_id}' is not awaiting confirmation (status: {task['status']})"}, 409)
            else:
                try:
                    body = self._read_body()
                except Exception:
                    body = {}
                reason = body.get("reason", "human rejected T3 task") if isinstance(body, dict) else "human rejected T3 task"
                task.pop("confirmation_required", None)
                _append_audit(task, "rejected", {"by": "human", "reason": reason})  # v2.52
                _update_task(task_id, TASK_FAILED, error=reason)
                self._json({"ok": True, "task_id": task_id, "status": TASK_FAILED, "reason": reason})

        # GET /tasks/{id}/wait?timeout=30 — 同步等待 task 进入 terminal 状态
        # 比 SSE subscribe 更简单，适合 Agent 调用
        elif p == "/webhooks/register":
            # BUG-039 fix: restrict webhook registration to localhost only
            # Webhook URLs receive all SSE events — must not allow remote registration
            client_ip = (self.client_address or ("", 0))[0]
            if client_ip not in ("127.0.0.1", "::1", "localhost"):
                self._json({"error": "webhook registration restricted to localhost"}, 403)
                return
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
            # BUG-039 fix: same localhost restriction for deregister
            client_ip = (self.client_address or ("", 0))[0]
            if client_ip not in ("127.0.0.1", "::1", "localhost"):
                self._json({"error": "webhook deregistration restricted to localhost"}, 403)
                return
            try:
                body = self._read_body()
                url  = body.get("url", "").strip()
                if url in _push_webhooks:
                    _push_webhooks.remove(url)
                self._json({"ok": True, "remaining": len(_push_webhooks)})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)

        # /skills/query — QuerySkill: runtime capability introspection (v0.6, enhanced v2.10)
        # Request:  {"skill_id": "summarize", "constraints": {"file_size_bytes": 52428800}}
        # Response: {"skill_id": "...", "support_level": "supported|partial|unsupported",
        #            "reason": "...", "constraints_applied": {...}, "agent": {...}}
        # v2.10: when skills are structured objects, uses id/name/description for keyword matching
        elif p == "/skills/query":  # [stable] QuerySkill runtime capability discovery
            try:
                body = self._read_body()
                skill_id    = (body.get("skill_id") or "").strip()
                constraints = body.get("constraints") or {}

                agent_card  = _status.get("agent_card") or {}
                raw_skills  = agent_card.get("skills", [])
                capabilities = agent_card.get("capabilities", {})

                # v2.10: structured matching — skills are dicts with id/name/description
                # Fallback: if skills are plain strings (legacy), use original logic
                _is_structured = raw_skills and isinstance(raw_skills[0], dict)

                if _is_structured:
                    known_skill_ids  = {s["id"] for s in raw_skills}
                    known_skills_str = sorted(known_skill_ids)
                else:
                    # Legacy: list of plain strings
                    known_skill_ids  = set(raw_skills)
                    known_skills_str = sorted(known_skill_ids)

                # v2.11: extract input_mode constraint before branching
                req_input_mode = constraints.get("input_mode", "").strip()

                # Determine support level
                if not skill_id:
                    # No skill_id: check for input_mode filter (v2.11), else return full list
                    if req_input_mode:
                        # Filter skills by input_mode support
                        if _is_structured:
                            matched_skills = [
                                s for s in raw_skills
                                if req_input_mode in (s.get("input_modes") or [])
                            ]
                        else:
                            matched_skills = []
                        if matched_skills:
                            self._json({
                                "skills":       matched_skills,
                                "capabilities": capabilities,
                                "agent": {"name": agent_card.get("name"), "acp_version": VERSION},
                            })
                        else:
                            self._json({
                                "support_level": "unsupported",
                                "reason": f"No skill supports input_mode='{req_input_mode}'",
                                "skills": [],
                                "capabilities": capabilities,
                                "agent": {"name": agent_card.get("name"), "acp_version": VERSION},
                            })
                        return
                    # No skill_id and no input_mode filter: return full skill list
                    if _is_structured:
                        self._json({
                            "skills":       raw_skills,
                            "capabilities": capabilities,
                            "agent": {"name": agent_card.get("name"), "acp_version": VERSION},
                        })
                    else:
                        self._json({
                            "skills":       list(known_skill_ids),
                            "capabilities": capabilities,
                            "agent": {"name": agent_card.get("name"), "acp_version": VERSION},
                        })
                    return

                if skill_id in known_skill_ids:
                    # Check constraints against known capabilities + per-skill limits
                    violations = []
                    constraints_applied = {}

                    # Legacy: file_size_bytes (v0.6) — check against max_msg_bytes
                    if "file_size_bytes" in constraints:
                        max_bytes = capabilities.get("max_msg_bytes", MAX_MSG_BYTES)
                        if constraints["file_size_bytes"] > max_bytes:
                            violations.append(f"file_size_bytes {constraints['file_size_bytes']} exceeds max {max_bytes}")
                        constraints_applied["max_msg_bytes"] = max_bytes

                    # v2.26: max_file_size_bytes — alias for file_size_bytes, also checks skill-level limit
                    if "max_file_size_bytes" in constraints:
                        req_fsz = constraints["max_file_size_bytes"]
                        # Check against relay-level max_msg_bytes first
                        relay_max = capabilities.get("max_msg_bytes", MAX_MSG_BYTES)
                        if req_fsz > relay_max:
                            violations.append(f"max_file_size_bytes {req_fsz} exceeds relay limit {relay_max}")
                            constraints_applied["relay_max_msg_bytes"] = relay_max
                        # Check against skill-level constraint (if declared)
                        if _is_structured:
                            skill_obj_fsz = next((s for s in raw_skills if s["id"] == skill_id), None)
                            if skill_obj_fsz:
                                skill_max_fsz = (skill_obj_fsz.get("constraints") or {}).get("max_file_size_bytes")
                                if skill_max_fsz is not None:
                                    constraints_applied["skill_max_file_size_bytes"] = skill_max_fsz
                                    if req_fsz > skill_max_fsz:
                                        violations.append(
                                            f"max_file_size_bytes {req_fsz} exceeds skill '{skill_id}' limit {skill_max_fsz}"
                                        )

                    # v2.26: concurrent_tasks — check against skill-level limit
                    if "concurrent_tasks" in constraints:
                        req_ct = constraints["concurrent_tasks"]
                        if _is_structured:
                            skill_obj_ct = next((s for s in raw_skills if s["id"] == skill_id), None)
                            if skill_obj_ct:
                                skill_max_ct = (skill_obj_ct.get("constraints") or {}).get("concurrent_tasks")
                                if skill_max_ct is not None:
                                    constraints_applied["skill_concurrent_tasks"] = skill_max_ct
                                    if req_ct > skill_max_ct:
                                        violations.append(
                                            f"concurrent_tasks {req_ct} exceeds skill '{skill_id}' limit {skill_max_ct}"
                                        )

                    # v2.26: context_window — check against skill-level limit
                    if "context_window" in constraints:
                        req_cw = constraints["context_window"]
                        if _is_structured:
                            skill_obj_cw = next((s for s in raw_skills if s["id"] == skill_id), None)
                            if skill_obj_cw:
                                skill_max_cw = (skill_obj_cw.get("constraints") or {}).get("context_window")
                                if skill_max_cw is not None:
                                    constraints_applied["skill_context_window"] = skill_max_cw
                                    if req_cw > skill_max_cw:
                                        violations.append(
                                            f"context_window {req_cw} exceeds skill '{skill_id}' limit {skill_max_cw}"
                                        )

                    # v2.11: check input_mode constraint against skill's input_modes
                    if req_input_mode and _is_structured:
                        skill_obj = next((s for s in raw_skills if s["id"] == skill_id), None)
                        if skill_obj:
                            skill_input_modes = skill_obj.get("input_modes") or []
                            if skill_input_modes and req_input_mode not in skill_input_modes:
                                violations.append(
                                    f"input_mode='{req_input_mode}' not supported by skill "
                                    f"'{skill_id}' (supports: {skill_input_modes})"
                                )

                    if violations:
                        support_level = "partial"
                        reason = "; ".join(violations)
                    else:
                        support_level = "supported"
                        reason = f"Skill '{skill_id}' is available"
                else:
                    # v2.10: try keyword match in id/name/description for fuzzy discovery
                    matched = []
                    if _is_structured:
                        _kw = skill_id.lower()
                        matched = [
                            s for s in raw_skills
                            if (_kw in (s.get("id", "") or "").lower() or
                                _kw in (s.get("name", "") or "").lower() or
                                _kw in (s.get("description", "") or "").lower())
                        ]
                    support_level = "unsupported"
                    reason = f"Skill '{skill_id}' not registered on this agent"
                    if matched:
                        reason += f"; similar skills found: {[s['id'] for s in matched]}"
                    constraints_applied = {}

                # v2.26: attach queried skill's declared constraints to response
                # v2.28: attach queried skill's declared limitations to response
                queried_skill_obj = None
                if _is_structured and skill_id in known_skill_ids:
                    queried_skill_obj = next((s for s in raw_skills if s["id"] == skill_id), None)
                skill_constraints_declared = (
                    queried_skill_obj.get("constraints") if queried_skill_obj else None
                ) or {}
                skill_limitations_declared = (
                    queried_skill_obj.get("limitations") if queried_skill_obj else None
                ) or []   # v2.28: per-skill limitations[] in QuerySkill response

                self._json({
                    "skill_id":                   skill_id,
                    "support_level":              support_level,
                    "reason":                     reason,
                    "constraints_applied":        constraints_applied,
                    "skill_constraints_declared": skill_constraints_declared,   # v2.26
                    "skill_limitations_declared": skill_limitations_declared,   # v2.28
                    "known_skills":               known_skills_str,
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

        # ── POST /trust/vouch — add a vouch_chain entry (v2.27) ──────────────
        elif p == "/trust/vouch":
            """
            Add a vouch_chain entry to this agent's trust signals (v2.27).
            Compatible with A2A IS#1628 trust.signals specification.

            Body:
              {
                "voucher_did":  "did:acp:...",   # required — DID of vouching agent
                "comment":      "...",           # optional — free text
                "sig":          "...",           # optional — base64 Ed25519 sig of vouched_did+vouched_at
              }

            Returns:
              {
                "ok":        true,
                "vouch_id":  "<int>",            # index in vouch_chain
                "total":     <int>,              # total vouches so far
                "entry":     { ... },            # the stored entry
              }
            """
            try:
                body = self._read_body()
            except Exception as e:
                self._json({"ok": False, "error": f"invalid JSON: {e}"}, 400)
                return

            voucher_did = body.get("voucher_did", "").strip()
            if not voucher_did:
                self._json({"ok": False, "error_code": "ERR_MISSING_FIELD",
                            "error": "'voucher_did' is required"}, 400)
                return

            import time as _time_vouch
            entry = {
                "vouch_id":   len(_vouch_chain),
                "voucher_did": voucher_did,
                "vouched_did": _did_acp or _did_key or "unknown",   # this agent's DID
                "vouched_at":  _time_vouch.strftime("%Y-%m-%dT%H:%M:%SZ", _time_vouch.gmtime()),
                "sig":        body.get("sig"),      # optional; None if not provided
                "comment":    body.get("comment"),  # optional free text
            }
            _vouch_chain.append(entry)
            self._json({
                "ok":      True,
                "vouch_id": entry["vouch_id"],
                "total":    len(_vouch_chain),
                "entry":    entry,
            })

        # ── GET /trust/vouch — list vouch_chain entries (v2.27) ──────────────
        elif p == "/trust/vouch" and self.command == "GET":
            # This branch is unreachable from do_POST, but kept for clarity;
            # actual GET handling is in do_GET below. See GET /trust/vouch.
            pass

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
        """PATCH handler — routes to per-skill or global card updates.

        Routes:
          PATCH /skills/<id>/limitations   (v2.29) — runtime per-skill limitations update
          PATCH /.well-known/acp.json      (v1.2/v2.21) — global AgentCard availability/limitations
          PATCH /card                      (alias for above)

        PATCH /skills/<id>/limitations body:
          {
            "limitations": [                 # required: new limitations list (replaces existing)
              {"kind": "capability", "code": "no_audio", "message": "...", "permanent": false},
              "string_shorthand"             # auto-promoted to LimitationObject
            ],
            "limitations_merge": false       # optional: if true, merge into existing (default: replace)
          }
        Send empty array [] to clear all runtime limitations (restores declared defaults).

        PATCH /.well-known/acp.json body (v1.2/v2.21):
          {
            "availability": { ... },
            "limitations": [ ... ],
            "limitations_merge": false
          }

        Use-case: runtime degradation/recovery — an agent (or its owner) can update its
        limitations dynamically without restarting the relay.
        """
        global _availability, _limitations, _skill_limitations_overrides
        p = urlparse(self.path).path

        # ── Route: PATCH /skills/<id>/limitations (v2.29) ────────────────────
        if p.startswith("/skills/") and p.endswith("/limitations"):
            skill_id_req = p[len("/skills/"):-len("/limitations")]
            if not skill_id_req:
                self._json({"error": "skill id must not be empty"}, 400)
                return
            # Verify skill exists in agent card
            agent_card = _status.get("agent_card") or {}
            all_skills = list(agent_card.get("skills", []))
            matched = None
            for s in all_skills:
                sid = s.get("id", "") if isinstance(s, dict) else str(s)
                if sid == skill_id_req:
                    matched = s
                    break
            if matched is None:
                self._json(
                    {"error": f"skill '{skill_id_req}' not found"},
                    404,
                )
                return
            try:
                body = self._read_body()
            except Exception as e:
                self._json({"error": f"invalid JSON: {e}"}, 400)
                return
            lims_raw = body.get("limitations")
            if lims_raw is None:
                self._json({"error": "request body must contain 'limitations' key"}, 400)
                return
            if not isinstance(lims_raw, list):
                self._json({"error": "'limitations' must be a JSON array"}, 400)
                return
            # Validate kinds
            for item in lims_raw:
                if isinstance(item, dict) and "kind" in item:
                    if item["kind"] not in _VALID_LIMITATION_KINDS:
                        self._json({"error": f"invalid limitation kind '{item['kind']}'; "
                                             f"must be one of {sorted(_VALID_LIMITATION_KINDS)}"}, 400)
                        return
            try:
                new_lims = [_parse_limitation(item) for item in lims_raw]
            except Exception as e:
                self._json({"error": f"invalid limitation entry: {e}"}, 400)
                return

            lims_merge = bool(body.get("limitations_merge", False))
            if lims_merge and skill_id_req in _skill_limitations_overrides:
                existing = {(lim.get("kind"), lim.get("code")): lim
                            for lim in _skill_limitations_overrides[skill_id_req]}
                for lim in new_lims:
                    existing[(lim.get("kind"), lim.get("code"))] = lim
                resolved = list(existing.values())
            else:
                resolved = new_lims

            if resolved:
                _skill_limitations_overrides[skill_id_req] = resolved
            else:
                # Empty list = clear override (restore declared defaults)
                _skill_limitations_overrides.pop(skill_id_req, None)

            log.info(f"🚫 Skill '{skill_id_req}' limitations updated via PATCH: "
                     f"{len(resolved)} entries (merge={lims_merge})")
            self._json({
                "ok":         True,
                "skill_id":   skill_id_req,
                "limitations": resolved,
            })
            return

        if p not in ("/card", "/.well-known/acp.json"):
            self._json({"error": "PATCH only supported on /.well-known/acp.json or /skills/<id>/limitations"}, 404)
            return
        try:
            body = self._read_body()
        except Exception as e:
            self._json({"error": f"invalid JSON: {e}"}, 400)
            return

        # v2.21: body may contain "availability" and/or "limitations" (either or both)
        avail_patch = body.get("availability")
        lims_patch   = body.get("limitations")
        lims_merge   = bool(body.get("limitations_merge", False))

        if avail_patch is None and lims_patch is None:
            self._json({"error": "request body must contain 'availability' and/or 'limitations' key"}, 400)
            return

        updated_keys = []

        # ── availability block ────────────────────────────────────────────────
        if avail_patch is not None:
            if not isinstance(avail_patch, dict):
                self._json({"error": "'availability' must be a JSON object"}, 400)
                return

            # Allowed fields for PATCH (whitelist to avoid injection)
            ALLOWED = {"mode", "interval_seconds", "next_active_at",
                       "last_active_at", "task_latency_max_seconds",
                       "schedule", "timezone"}   # v2.17: added schedule + timezone
            unknown = set(avail_patch.keys()) - ALLOWED
            if unknown:
                self._json({"error": f"unknown availability fields: {sorted(unknown)}"}, 400)
                return

            # Validate mode if provided
            valid_modes = {"persistent", "heartbeat", "cron", "manual"}
            if "mode" in avail_patch and avail_patch["mode"] not in valid_modes:
                self._json({"error": f"mode must be one of {sorted(valid_modes)}"}, 400)
                return

            # Merge patch into _availability
            _availability = {**_availability, **avail_patch}
            log.info(f"📅 AgentCard availability updated via PATCH: {_availability}")
            updated_keys.append("availability")

        # ── limitations block (v2.21) ─────────────────────────────────────────
        if lims_patch is not None:
            if not isinstance(lims_patch, list):
                self._json({"error": "'limitations' must be a JSON array"}, 400)
                return
            # v2.21: strict validation for dict entries in PATCH (kind must be valid or absent)
            for item in lims_patch:
                if isinstance(item, dict) and "kind" in item:
                    if item["kind"] not in _VALID_LIMITATION_KINDS:
                        self._json({"error": f"invalid limitation kind '{item['kind']}'; "
                                             f"must be one of {sorted(_VALID_LIMITATION_KINDS)}"}, 400)
                        return
            try:
                new_lims = [_parse_limitation(item) for item in lims_patch]
            except Exception as e:
                self._json({"error": f"invalid limitation entry: {e}"}, 400)
                return

            if lims_merge:
                # Merge: append new limitations, de-duplicate by (kind, code)
                existing = {(lim.get("kind"), lim.get("code")): lim for lim in _limitations}
                for lim in new_lims:
                    existing[(lim.get("kind"), lim.get("code"))] = lim
                _limitations = list(existing.values())
            else:
                # Replace (default): overwrite the entire limitations list
                _limitations = new_lims

            log.info(f"🚫 AgentCard limitations updated via PATCH: {len(_limitations)} entries (merge={lims_merge})")
            updated_keys.append("limitations")

        # Return the updated live card
        # v2.10: pass full structured skill objects
        skills = list((_status.get("agent_card") or {}).get("skills", []))
        live_card = _make_agent_card(_status.get("agent_name", "ACP-Agent"), skills)
        response = {"ok": True, "updated": updated_keys}
        if "availability" in updated_keys:
            response["availability"] = live_card.get("availability", {})
        if "limitations" in updated_keys:
            response["limitations"] = live_card.get("limitations", [])
        self._json(response)


class _ACPHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer subclass with BUG-030/BUG-049 concurrent-load fixes.

    Changes vs stock ThreadingHTTPServer:
    - allow_reuse_address = True  — prevents TIME_WAIT port conflicts on rapid restart
    - request_queue_size = 64     — default 5 causes ECONNREFUSED / RemoteDisconnected
                                    under concurrent-relay test scenarios (3+ relays)
    - daemon_threads = True       — worker threads don't block process exit
    """
    allow_reuse_address = True
    request_queue_size  = 64
    daemon_threads      = True


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

    # Default: HTTP/1.1 via _ACPHTTPServer (BUG-030/BUG-049: larger queue + reuse_addr)
    _ACPHTTPServer((host, port), LocalHTTP).serve_forever()


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
    parser.add_argument("--local-only",   action="store_true",
                        help="(v2.35) Skip public-IP detection and relay pre-registration; "
                             "generate acp://127.0.0.1:PORT/TOKEN link immediately. "
                             "Useful for local tests, CI, and sandboxed environments.")
    parser.add_argument("--test-mode",       action="store_true",
                        help="(v2.48) Enable POST /debug/inject for unit-test message+peer "
                             "injection. NEVER use in production.")
    parser.add_argument("--auto-confirm-t3", action="store_true",
                        help="(v2.51) Bypass human_confirmation_required gate for T3 skills. "
                             "Test-only: T3 tasks proceed directly to submitted. NEVER use in production.")
    parser.add_argument("--relay",        action="store_true", help="(v1.4) Force Level 3 relay transport (skip L1 direct + L2 hole punch). Previously 'use relay instead of P2P'; now means auto-degradation last resort.")
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
    parser.add_argument("--identity-file", default=None, metavar="PATH",
                        help="(v0.8) Alias for --identity. Path to Ed25519 keypair JSON file.")
    parser.add_argument("--gen-identity", action="store_true",
                        help="(v0.8) Generate a new Ed25519 keypair, save to --identity-file path "
                             "(default: ~/.acp/identity.key), print the did:key identifier, "
                             "then exit. Use with --identity-file to set a custom output path. "
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
    parser.add_argument("--availability-cron", default=None, metavar="CRON_EXPR",
                        help="(v2.19) CRON expression for scheduled availability. Sets availability.scheduleType='cron', "
                             "availability.cron=<expr>, and auto-computes nextActiveAt. "
                             "Implies --availability-mode cron. "
                             "Example: --availability-cron '*/30 * * * *' (every 30 minutes). "
                             "Populates AgentCard 'availability' block with scheduleType/cron/nextActiveAt/taskLatencyMaxSeconds.")
    parser.add_argument("--extension", action="append", default=[], metavar="URI[,required=true][,key=val...]",
                        help="(v1.3) Declare an AgentCard extension. May be repeated. "
                             "Format: URI  or  URI,required=true,param_key=param_val. "
                             "Example: --extension https://acp.dev/ext/availability/v1,required=false "
                             "         --extension https://corp.example.com/ext/billing,tier=pro")
    parser.add_argument("--extensions", default=None, metavar="URI[,URI...]",
                        help="(v2.8) Comma-separated list of extension URIs to declare in AgentCard. "
                             "Shorthand for --extension when no per-extension params are needed. "
                             "Built-in extensions (hmac, mdns, h2c) are auto-registered based on "
                             "runtime config; this flag appends custom/external extensions. "
                             "URI format: acp:ext:<name>-v<version> or https://... "
                             "Example: --extensions acp:ext:custom-v1,https://corp.example.com/ext/billing")
    parser.add_argument("--http-host", default="127.0.0.1", metavar="HOST",
                        help="Host/IP the HTTP interface binds to (default: 127.0.0.1). "
                             "Use 0.0.0.0 for Docker/container deployments so port mapping works.")
    parser.add_argument("--http2", action="store_true",
                        help="Enable HTTP/2 transport (h2c cleartext) via hypercorn. "
                             "Requires: pip install hypercorn h2. "
                             "Falls back to HTTP/1.1 if dependencies are missing. "
                             "Enables multiplexed streams and reduced head-of-line blocking.")
    parser.add_argument("--transport-modes", default=None, metavar="MODES",
                        help="(v2.4) Comma-separated routing modes this node supports. "
                             "Values: p2p, relay. Default: 'p2p,relay' (both). "
                             "Example: --transport-modes p2p  (P2P only, no relay fallback). "
                             "Advertised as top-level 'transport_modes' in AgentCard / /.well-known/acp.json.")
    parser.add_argument("--supported-interfaces", default=None, metavar="IFACES",
                        help="(v2.3) Comma-separated interface groups this agent supports. "
                             "Values: core, task, stream, mdns, p2p, identity. "
                             "Default: auto-derived from runtime configuration. "
                             "Example: --supported-interfaces core,task,stream. "
                             "Advertised as top-level 'supported_interfaces' in AgentCard.")
    parser.add_argument("--limitations", default=None, metavar="LIMITATIONS",
                        help="(v2.7/v2.20) Comma-separated list of things this agent CANNOT do. "
                             "Completes the 3-part capability boundary: capabilities (can-do) + "
                             "availability (current state) + limitations (cannot-do). "
                             "Example: --limitations no_file_access,no_internet. "
                             "Each string is auto-promoted to LimitationObject{kind=capability, permanent=True}. "
                             "Advertised as structured LimitationObject[] in AgentCard. "
                             "Defaults to [] (empty) when not specified. Ref: A2A #1694.")
    parser.add_argument("--limitations-json", default=None, metavar="LIMITATIONS_JSON",
                        help="(v2.20) JSON array of LimitationObject entries. Takes precedence over --limitations. "
                             "Each object: {\"kind\": \"modality\", \"code\": \"image-input-unsupported\", "
                             "\"message\": \"Cannot process images\", \"permanent\": true}. "
                             "Valid kinds: capability|modality|scale|domain|access|other. "
                             "Example: --limitations-json '[{\"kind\":\"scale\",\"code\":\"max-10mb\","
                             "\"message\":\"Max 10MB files\",\"permanent\":true}]'. "
                             "Ref: A2A IS#1694 stable/runtime split.")

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
    # --identity-file is an alias for --identity; CLI > config > None
    if identity_path is None and getattr(args, "identity_file", None):
        identity_path = args.identity_file

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

    # Ed25519 optional identity (v0.8) — --gen-identity: generate keypair and exit
    if getattr(args, "gen_identity", False):
        gen_path = identity_path or os.path.expanduser("~/.acp/identity.key")
        ok = _ed25519_load_or_create(gen_path)
        if ok and _did_key:
            print(f"✅ Ed25519 keypair generated")
            print(f"   File:     {gen_path}")
            print(f"   did:key:  {_did_key}")
            print(f"   did:acp:  {_did_acp}")
            print(f"   pubkey:   {_ed25519_public_b64}")
        else:
            print("❌ Failed to generate Ed25519 keypair (missing cryptography library?)")
            print("   Try: pip install cryptography")
            sys.exit(1)
        sys.exit(0)

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
    avail_mode        = _get(getattr(args, "availability_mode",  None), "availability-mode",    None)
    hb_interval       = _get(getattr(args, "heartbeat_interval", None), "heartbeat-interval",   None)
    next_active_at    = _get(getattr(args, "next_active_at",     None), "next-active-at",       None)
    # v2.19: --availability-cron shorthand — sets scheduleType=cron + CRON expression + auto-computes nextActiveAt
    avail_cron_expr   = _get(getattr(args, "availability_cron",  None), "availability-cron",    None)
    if avail_cron_expr:
        # --availability-cron implies mode=cron; compute next_active_at from expression
        avail_mode = "cron"
        nxt_from_cron = None
        try:
            nxt_from_cron = _next_cron_datetime(avail_cron_expr)
        except Exception:
            pass
        _availability = {
            "mode":                    "cron",
            "scheduleType":            "cron",
            "cron":                    avail_cron_expr,
            "schedule":                avail_cron_expr,   # alias used by _availability_with_schedule
            "taskLatencyMaxSeconds":   60,
            "task_latency_max_seconds": 60,
        }
        if nxt_from_cron:
            _availability["nextActiveAt"]   = nxt_from_cron.strftime("%Y-%m-%dT%H:%M:%SZ")
            _availability["next_active_at"] = _availability["nextActiveAt"]
        log.info(f"📅 Availability mode: cron (expr={avail_cron_expr!r}, "
                 f"nextActiveAt={_availability.get('nextActiveAt')})")
    elif avail_mode and avail_mode != "persistent":
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

    # v1.3 / v2.8: parse --extension and --extensions flags into _extensions list
    raw_extensions = _get(getattr(args, "extension", []) or [], "extension", [])
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

    # v2.8: --extensions shorthand (comma-separated URIs, no per-extension params)
    raw_extensions_bulk = _get(getattr(args, "extensions", None), "extensions", None)
    if raw_extensions_bulk:
        if isinstance(raw_extensions_bulk, str):
            uris = [u.strip() for u in raw_extensions_bulk.split(",") if u.strip()]
            for uri in uris:
                # Avoid duplicating URIs already added via --extension
                if not any(e["uri"] == uri for e in _extensions):
                    _extensions.append({"uri": uri, "required": False, "params": {}})

    if _extensions:
        log.info(f"🔌 User-declared extensions: {[e['uri'] for e in _extensions]}")
    log.info("🔌 Built-in extensions will be auto-registered from runtime capabilities")

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
    # v2.10: Skills-lite — support both plain CSV ("summarize,translate") and
    # JSON array ('[{"id":"summarize","name":"Text Summarization","tags":["nlp"]}]').
    if args.skills:
        _raw_skills = args.skills.strip()
        if _raw_skills.startswith("["):
            # JSON array of structured skill objects
            try:
                import json as _json
                _parsed = _json.loads(_raw_skills)
                if isinstance(_parsed, list):
                    skills = [_parse_skill_obj(s) for s in _parsed]
                else:
                    skills = [_parse_skill_obj(_raw_skills)]
            except Exception:
                # Fallback: treat as plain CSV
                skills = [_parse_skill_obj(s.strip()) for s in _raw_skills.split(",") if s.strip()]
        else:
            # Plain comma-separated strings → structured objects (backward compat)
            skills = [_parse_skill_obj(s.strip()) for s in _raw_skills.split(",") if s.strip()]
    else:
        skills = []

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

    # v2.4: transport_modes — top-level AgentCard routing modes
    global _transport_modes
    _VALID_TRANSPORT_MODES = {"p2p", "relay"}
    raw_modes = _get(getattr(args, "transport_modes", None), "transport-modes", None)
    if raw_modes is not None:
        parsed_modes = [m.strip() for m in raw_modes.split(",") if m.strip()]
        invalid = [m for m in parsed_modes if m not in _VALID_TRANSPORT_MODES]
        if invalid:
            log.warning(f"⚠️  Unknown transport_modes ignored: {invalid} — valid: {sorted(_VALID_TRANSPORT_MODES)}")
            parsed_modes = [m for m in parsed_modes if m in _VALID_TRANSPORT_MODES]
        if parsed_modes:
            _transport_modes = parsed_modes
        else:
            log.warning("⚠️  --transport-modes resulted in empty list; keeping default ['p2p', 'relay']")
    # v2.3: supported_interfaces — parse CLI override
    global _supported_interfaces_override
    raw_ifaces = _get(getattr(args, "supported_interfaces", None), "supported-interfaces", None)
    if raw_ifaces is not None:
        parsed_ifaces = [i.strip() for i in raw_ifaces.split(",") if i.strip()]
        invalid_ifaces = [i for i in parsed_ifaces if i not in _VALID_INTERFACES]
        if invalid_ifaces:
            log.warning(f"⚠️  Unknown supported_interfaces ignored: {invalid_ifaces} — valid: {sorted(_VALID_INTERFACES)}")
            parsed_ifaces = [i for i in parsed_ifaces if i in _VALID_INTERFACES]
        if parsed_ifaces:
            _supported_interfaces_override = sorted(parsed_ifaces)
        else:
            log.warning("⚠️  --supported-interfaces resulted in empty list; using auto-derived value")

    # v2.20: limitations — structured LimitationObject[] (what this agent CANNOT do)
    global _limitations
    raw_limitations_json = _get(getattr(args, "limitations_json", None), "limitations_json", None)
    raw_limitations_csv  = _get(getattr(args, "limitations", None), "limitations", None)
    if raw_limitations_json is not None:
        # --limitations-json takes precedence: parse JSON array of LimitationObject
        try:
            parsed_raw = json.loads(raw_limitations_json)
            if not isinstance(parsed_raw, list):
                log.warning("⚠️  --limitations-json must be a JSON array; ignoring")
                parsed_raw = []
            _limitations = [_parse_limitation(item) for item in parsed_raw]
            log.info(f"🚫 Limitations (structured JSON): {len(_limitations)} entries")
        except json.JSONDecodeError as e:
            log.warning(f"⚠️  --limitations-json invalid JSON ({e}); ignoring")
            _limitations = []
    elif raw_limitations_csv is not None:
        # --limitations: comma-separated strings → auto-promote to LimitationObject
        raw_strings = [lim.strip() for lim in raw_limitations_csv.split(",") if lim.strip()]
        _limitations = [_parse_limitation(s) for s in raw_strings]
        if _limitations:
            log.info(f"🚫 Limitations (csv→structured): {[l['code'] for l in _limitations]}")
    else:
        _limitations = []
    _status["limitations"] = list(_limitations)  # already normalized LimitationObject[]

    # v1.4: --relay flag now means "force Level 3" (skip L1+L2 NAT traversal)
    # Previously: "use relay instead of P2P"
    # Now: _connect_with_nat_traversal() reads this flag to skip directly to L3
    _status["force_relay"] = bool(use_relay)
    if use_relay:
        log.info("⚡ --relay flag: Level 3 relay forced (L1+L2 NAT traversal skipped)")

    # v2.35: --local-only flag — store in _status so host_mode() can read it
    _status["local_only"] = bool(getattr(args, "local_only", False))
    if _status["local_only"]:
        log.info("🏠 --local-only: public IP detection and relay registration disabled")

    # v2.48: --test-mode
    global _test_mode
    _test_mode = bool(getattr(args, "test_mode", False))
    if _test_mode:
        log.warning("⚠️  --test-mode ENABLED: POST /debug/inject active (DO NOT use in production)")

    # v2.51: --auto-confirm-t3
    global _auto_confirm_t3
    _auto_confirm_t3 = bool(getattr(args, "auto_confirm_t3", False))
    if _auto_confirm_t3:
        log.warning("⚠️  --auto-confirm-t3 ENABLED: T3 human_confirmation_required bypassed (DO NOT use in production)")

    # Rebuild card to reflect transport_modes + supported_interfaces + limitations
    _status["agent_card"] = _make_agent_card(args.name, skills)
    log.info(f"🚌 Transport modes: {_transport_modes}")
    log.info(f"🔌 Supported interfaces: {_make_supported_interfaces()}")

    threading.Thread(target=run_http, args=(http_port, http_host), kwargs={"http2": _http2_enabled}, daemon=True).start()
    log.info(f"HTTP interface: {'h2c' if _http2_enabled else 'http'}//{http_host}:{http_port}")

    # ── mDNS LAN discovery (v0.7) ─────────────────────────────────────────────
    if args.advertise_mdns:
        token_placeholder = _make_token()  # will be replaced after host_mode assigns real token
        _mdns_start(args.name, token_placeholder, ws_port, http_port)
        log.info(f"mDNS: advertising on LAN ({_MDNS_GROUP}:{_MDNS_PORT})")

    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)

    # BUG-045: _ws_send_global_lock is initialised lazily inside _ws_send (first async call)

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



