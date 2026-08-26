"""
ACP Identity Extension v0.8 — Ed25519 optional message signing.

Design principles (ACP v0.8):
  - OPTIONAL: agents without identity configured are fully unaffected
  - LIGHTWEIGHT: Ed25519 self-sovereign keypair, zero PKI / CA overhead
  - TRANSPARENT: Relay handles verification; Agents don't need to know

Wire format (signature in /message:send body):
  {
    "parts": [...],
    "message_id": "msg_uuid",
    "signature": {
      "key_id":       "kid_xxxx",
      "value":        "base64url(ed25519_signature_64_bytes)",
      "payload_hash": "sha256hex(canonical_json(parts + message_id + timestamp))"
    },
    "timestamp": 1711598400   # Unix seconds, included in signed payload
  }

AgentCard identity field:
  {
    "identity": {
      "public_key": "base64url(ed25519_public_key_32_bytes)",
      "algorithm":  "Ed25519",
      "key_id":     "kid_xxxx"
    }
  }

Dependencies:
  - cryptography >= 2.6  (pip install cryptography)
  - Falls back gracefully when unavailable (verify returns None = skip)
"""

import base64
import hashlib
import json
import time

# ── Optional cryptography import ──────────────────────────────────────────────
try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        PublicFormat,
        PrivateFormat,
        NoEncryption,
    )
    from cryptography.exceptions import InvalidSignature as _InvalidSignature
    IDENTITY_AVAILABLE = True
except ImportError:
    IDENTITY_AVAILABLE = False

# ── Replay-window constant ─────────────────────────────────────────────────────
REPLAY_WINDOW_SECONDS = 300  # ±5 minutes


# ─────────────────────────────────────────────────────────────────────────────
# Key utilities
# ─────────────────────────────────────────────────────────────────────────────

def _b64url_encode(data: bytes) -> str:
    """URL-safe base64 encode without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    """URL-safe base64 decode, tolerating missing padding."""
    return base64.urlsafe_b64decode(s + "==")


def make_key_id(public_key_b64url: str) -> str:
    """Derive a short key_id from the public key bytes.

    Format: "kid_" + first 12 hex chars of SHA-256(pubkey).
    Deterministic and collision-resistant for normal usage.

    Args:
        public_key_b64url: Base64url-encoded Ed25519 public key (32 bytes).

    Returns:
        String like "kid_3f5a2b7c9d1e".
    """
    pub_bytes = _b64url_decode(public_key_b64url)
    digest = hashlib.sha256(pub_bytes).hexdigest()
    return f"kid_{digest[:12]}"


# ─────────────────────────────────────────────────────────────────────────────
# Canonical payload construction
# ─────────────────────────────────────────────────────────────────────────────

def _canonical_payload(parts: list, message_id: str, timestamp: int) -> bytes:
    """Build the canonical signing payload.

    Canonical form: sorted-keys JSON of {"message_id", "parts", "timestamp"}.
    This is deterministic across Python versions for JSON-safe values.

    Args:
        parts:      List of Part objects (must be JSON-serializable).
        message_id: Client-generated UUID string.
        timestamp:  Unix seconds (int).

    Returns:
        UTF-8 bytes of canonical JSON string.
    """
    obj = {
        "message_id": message_id,
        "parts":      parts,
        "timestamp":  timestamp,
    }
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _payload_hash(parts: list, message_id: str, timestamp: int) -> str:
    """Compute sha256hex of the canonical signing payload.

    Returns:
        Lowercase hex string (64 chars).
    """
    payload = _canonical_payload(parts, message_id, timestamp)
    return hashlib.sha256(payload).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# Signature verification
# ─────────────────────────────────────────────────────────────────────────────

def verify_signature(
    public_key_b64url: str,
    signature_obj: dict,
    parts: list,
    message_id: str,
) -> "bool | None":
    """Verify an Ed25519 message signature.

    Checks:
      1. Timestamp freshness: timestamp in signature_obj must be within
         ±REPLAY_WINDOW_SECONDS of current time.
      2. Payload hash: recomputed hash must match signature_obj["payload_hash"].
      3. Ed25519 signature: cryptographic verification against public_key_b64url.

    Args:
        public_key_b64url: Base64url-encoded Ed25519 public key (32 bytes).
        signature_obj:     Dict with keys: key_id, value, payload_hash.
                           Also requires a "timestamp" at the message level,
                           passed via the `timestamp` parameter (see note below).
                           Actually the timestamp comes from the outer message —
                           callers should pass it via the signature_obj or we read
                           it from signature_obj["timestamp"] if present.
        parts:             List of Part objects from the message.
        message_id:        Message UUID string.

    Note on timestamp:
        The timestamp is part of the outer message body, not the signature_obj.
        Callers should pass it as signature_obj["_timestamp"] or include it
        as a top-level "timestamp" in the message and pass the full message.
        For this function, if signature_obj contains "_timestamp", it is used;
        otherwise the current time is used (skipping replay check).

    Returns:
        True  — signature is valid and fresh
        False — signature is invalid or replay detected
        None  — cryptography library not available (graceful skip)

    Raises:
        Nothing — all errors return False or None.
    """
    if not IDENTITY_AVAILABLE:
        return None  # graceful degradation — skip verification

    try:
        # ── 1. Replay-window check ──────────────────────────────────────────
        timestamp = signature_obj.get("_timestamp")
        if timestamp is not None:
            now = time.time()
            delta = abs(now - float(timestamp))
            if delta > REPLAY_WINDOW_SECONDS:
                return False  # replay detected

        # ── 2. Payload hash check ───────────────────────────────────────────
        sig_ts = int(timestamp) if timestamp is not None else 0
        expected_hash = _payload_hash(parts, message_id, sig_ts)
        claimed_hash  = signature_obj.get("payload_hash", "")
        if expected_hash != claimed_hash:
            return False  # payload hash mismatch

        # ── 3. Ed25519 cryptographic verification ───────────────────────────
        pub_bytes   = _b64url_decode(public_key_b64url)
        pub_key     = Ed25519PublicKey.from_public_bytes(pub_bytes)
        sig_bytes   = _b64url_decode(signature_obj.get("value", ""))
        payload     = _canonical_payload(parts, message_id, sig_ts)
        pub_key.verify(sig_bytes, payload)
        return True

    except (_InvalidSignature, Exception):
        return False


def verify_message(public_key_b64url: str, message: dict) -> "bool | None":
    """Convenience wrapper: verify a full message dict.

    Extracts parts, message_id, timestamp and signature_obj from the message,
    then calls verify_signature().

    Args:
        public_key_b64url: Base64url-encoded Ed25519 public key.
        message:           Full message dict (from /message:send body).
                           Must have: parts, message_id, timestamp, signature.

    Returns:
        True / False / None (same semantics as verify_signature).
    """
    sig_obj = message.get("signature")
    if not sig_obj:
        return None  # no signature present — nothing to verify

    parts      = message.get("parts", [])
    message_id = message.get("message_id", "")
    timestamp  = message.get("timestamp")

    # Inject timestamp into sig_obj for the downstream check
    aug_sig = dict(sig_obj)
    if timestamp is not None:
        aug_sig["_timestamp"] = timestamp

    return verify_signature(public_key_b64url, aug_sig, parts, message_id)


# ─────────────────────────────────────────────────────────────────────────────
# Keypair generation (for testing and relay setup)
# ─────────────────────────────────────────────────────────────────────────────

def generate_keypair() -> dict:
    """Generate a fresh Ed25519 keypair for testing or agent initialization.

    Returns:
        {
          "private_key_b64url": "...",   # 32-byte private key, base64url
          "public_key_b64url":  "...",   # 32-byte public key, base64url
          "key_id":             "kid_xxxx",
        }

    Raises:
        RuntimeError: if cryptography library is not available.
    """
    if not IDENTITY_AVAILABLE:
        raise RuntimeError(
            "Ed25519 identity requires: pip install cryptography"
        )
    private_key = Ed25519PrivateKey.generate()
    pub_raw  = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    priv_raw = private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    pub_b64  = _b64url_encode(pub_raw)
    priv_b64 = _b64url_encode(priv_raw)
    return {
        "private_key_b64url": priv_b64,
        "public_key_b64url":  pub_b64,
        "key_id":             make_key_id(pub_b64),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Signing helpers (for SDK / test use)
# ─────────────────────────────────────────────────────────────────────────────

def sign_message(private_key_b64url: str, parts: list, message_id: str, timestamp: int = None) -> dict:
    """Sign a message and return a signature object.

    Args:
        private_key_b64url: Base64url-encoded Ed25519 private key (32 bytes).
        parts:              List of Part objects.
        message_id:         UUID string for the message.
        timestamp:          Unix seconds. Defaults to current time.

    Returns:
        signature dict:
        {
          "key_id":       "kid_xxxx",
          "value":        "base64url(sig)",
          "payload_hash": "sha256hex(...)",
        }

    Also returns the timestamp used (as part of the message body, not inside signature).

    Actually returns: (signature_dict, timestamp_int)
    """
    if not IDENTITY_AVAILABLE:
        raise RuntimeError("Ed25519 identity requires: pip install cryptography")

    if timestamp is None:
        timestamp = int(time.time())

    priv_raw    = _b64url_decode(private_key_b64url)
    private_key = Ed25519PrivateKey.from_private_bytes(priv_raw)
    pub_raw     = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    pub_b64     = _b64url_encode(pub_raw)

    payload  = _canonical_payload(parts, message_id, timestamp)
    sig_raw  = private_key.sign(payload)
    sig_b64  = _b64url_encode(sig_raw)
    ph       = _payload_hash(parts, message_id, timestamp)

    signature = {
        "key_id":       make_key_id(pub_b64),
        "value":        sig_b64,
        "payload_hash": ph,
    }
    return signature, timestamp
