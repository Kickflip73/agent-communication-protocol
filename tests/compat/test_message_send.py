"""
Suite: Message Send (ACP spec §4)
Tests /message:send endpoint behavior including idempotency.
"""
import time
import uuid
from compat_base import Compat


def _msg(text: str = "compat-test", message_id: str | None = None) -> dict:
    return {
        "type": "acp.message",
        "message_id": message_id or f"msg_{uuid.uuid4().hex[:16]}",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "from": "compat-runner",
        "role": "user",
        "parts": [{"type": "text", "content": text}],
    }


class MessageSendSuite(Compat):
    SUITE_NAME = "Message Send"

    def run(self) -> None:
        # ── Basic send ────────────────────────────────────────────────────────
        msg = _msg("hello from compat suite")
        status, resp = self.post("/message:send", msg)

        self.check("POST /message:send returns 200 or 202",
                   status in (200, 202), "MUST",
                   f"got {status}")

        self.check("response is a JSON object",
                   isinstance(resp, dict), "MUST")

        if isinstance(resp, dict):
            self.check("response has 'message_id' echo",
                       resp.get("message_id") == msg["message_id"],
                       "SHOULD",
                       "server should echo client's message_id")

            self.check("response has 'server_seq' integer",
                       isinstance(resp.get("server_seq"), int),
                       "SHOULD")

        # ── Required envelope fields validation ───────────────────────────────
        # Missing message_id → should get error
        bad = {"type": "acp.message", "parts": [{"type": "text", "content": "x"}]}
        s2, r2 = self.post("/message:send", bad)
        self.check("missing message_id returns 4xx",
                   400 <= s2 < 500, "SHOULD",
                   f"got {s2} — server should validate required fields")

        # ── Idempotency (message_id deduplication) ────────────────────────────
        dup_id = f"msg_{uuid.uuid4().hex[:16]}"
        m1 = _msg("first send", dup_id)
        m2 = _msg("second send (dup)", dup_id)  # same message_id, different content

        s_a, r_a = self.post("/message:send", m1)
        s_b, r_b = self.post("/message:send", m2)

        # Both should succeed (not error), but second should be deduplicated
        self.check("duplicate message_id: first send succeeds",
                   s_a in (200, 202), "MUST",
                   f"got {s_a}")

        self.check("duplicate message_id: second send does not return 5xx",
                   s_b < 500, "MUST",
                   f"got {s_b}")

        if isinstance(r_a, dict) and isinstance(r_b, dict):
            seq_a = r_a.get("server_seq")
            seq_b = r_b.get("server_seq")
            if seq_a is not None and seq_b is not None:
                self.check("duplicate message_id: server_seq unchanged on re-send",
                           seq_a == seq_b,
                           "SHOULD",
                           f"seq_a={seq_a}, seq_b={seq_b} — idempotent re-send should return same seq")

        # ── context_id (if declared) ──────────────────────────────────────────
        if self.has_capability("context_id"):
            ctx_id = f"ctx_{uuid.uuid4().hex[:8]}"
            cm = _msg("message with context_id")
            cm["context_id"] = ctx_id
            s_ctx, r_ctx = self.post("/message:send", cm)
            self.check("context_id accepted without error",
                       s_ctx in (200, 202), "MUST",
                       f"got {s_ctx}")
        else:
            self.skip("context_id field accepted", "context_id not in capabilities")
