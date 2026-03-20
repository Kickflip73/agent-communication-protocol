"""
Suite: HMAC Signing (ACP spec §10, optional)
Only runs if capabilities.hmac_signing is declared in AgentCard.
"""
import hashlib
import hmac as _hmac
import uuid
import time
from compat_base import Compat


def _compute_sig(secret: str, message_id: str, ts: str) -> str:
    key = secret.encode()
    msg = f"{message_id}:{ts}".encode()
    return _hmac.new(key, msg, hashlib.sha256).hexdigest()


class HMACSigningSuite(Compat):
    SUITE_NAME = "HMAC Signing"

    def __init__(self, *args, secret: str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.secret = secret

    def run(self) -> None:
        if not self.has_capability("hmac_signing"):
            self.skip("HMAC signing tests", "hmac_signing not declared in capabilities")
            return

        trust = self.agent_card.get("trust", {})
        self.check("trust.scheme is 'hmac'",
                   trust.get("scheme") == "hmac",
                   "MUST",
                   f"got '{trust.get('scheme')}'")

        if not self.secret:
            self.skip("signed message accepted", "no --secret provided to compat runner")
            self.skip("unsigned message behavior", "no --secret provided")
            return

        # ── Send correctly signed message ─────────────────────────────────────
        msg_id = f"msg_{uuid.uuid4().hex[:16]}"
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        sig = _compute_sig(self.secret, msg_id, ts)

        msg = {
            "type": "acp.message",
            "message_id": msg_id,
            "ts": ts,
            "from": "compat-runner",
            "role": "user",
            "parts": [{"type": "text", "content": "signed compat test"}],
            "sig": sig,
        }
        s_ok, r_ok = self.post("/message:send", msg)
        self.check("correctly signed message accepted (200/202)",
                   s_ok in (200, 202), "MUST",
                   f"got {s_ok}")

        # ── Send message with wrong signature ──────────────────────────────────
        bad_msg_id = f"msg_{uuid.uuid4().hex[:16]}"
        bad_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        bad_msg = {
            "type": "acp.message",
            "message_id": bad_msg_id,
            "ts": bad_ts,
            "from": "compat-runner",
            "role": "user",
            "parts": [{"type": "text", "content": "bad sig test"}],
            "sig": "deadbeef" * 8,  # wrong signature
        }
        s_bad, r_bad = self.post("/message:send", bad_msg)
        # ACP spec: bad sig should warn but not drop (SHOULD warn, MAY reject)
        self.check("wrong sig: server does not crash (returns any response)",
                   s_bad != 0, "MUST",
                   f"got {s_bad}")
        self.check("wrong sig: server returns 4xx or 2xx (not 5xx)",
                   s_bad < 500, "SHOULD",
                   f"got {s_bad}")
