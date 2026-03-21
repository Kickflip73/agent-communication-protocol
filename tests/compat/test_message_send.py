"""
Suite: Message Send (ACP spec §4)
Tests /message:send endpoint behavior including idempotency.

v0.9 additions:
  - Server-side required-field validation: role + content (§4.1)
    Per ACP spec v0.9, servers MUST reject messages that are missing
    'role' or have an invalid role value, and MUST reject messages
    that have neither 'parts' nor 'text'/'content'.
"""
import time
import uuid
from compat_base import Compat


def _msg(text: str = "compat-test", message_id: str | None = None,
         role: str = "user") -> dict:
    return {
        "type": "acp.message",
        "message_id": message_id or f"msg_{uuid.uuid4().hex[:16]}",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "from": "compat-runner",
        "role": role,
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

        # ── Required-field validation (v0.9, server-side) ────────────────────
        # §4.1: role is REQUIRED; missing → 400
        no_role = {"type": "acp.message", "parts": [{"type": "text", "content": "x"}]}
        s_no_role, r_no_role = self.post("/message:send", no_role)
        self.check("missing 'role' returns 400",
                   s_no_role == 400, "MUST",
                   f"got {s_no_role} — server MUST reject requests without role")

        if isinstance(r_no_role, dict):
            self.check("missing 'role' error has error_code ERR_INVALID_REQUEST",
                       r_no_role.get("error_code") == "ERR_INVALID_REQUEST", "MUST",
                       f"got error_code={r_no_role.get('error_code')!r}")
            self.check("missing 'role' error has 'error' string",
                       isinstance(r_no_role.get("error"), str), "MUST")

        # §4.1: role must be 'user' or 'agent'
        bad_role = {"type": "acp.message", "role": "superagent",
                    "parts": [{"type": "text", "content": "x"}]}
        s_bad_role, r_bad_role = self.post("/message:send", bad_role)
        self.check("invalid role value returns 400",
                   s_bad_role == 400, "MUST",
                   f"got {s_bad_role} — role must be 'user' or 'agent'")

        if isinstance(r_bad_role, dict):
            self.check("invalid role error_code is ERR_INVALID_REQUEST",
                       r_bad_role.get("error_code") == "ERR_INVALID_REQUEST", "MUST",
                       f"got {r_bad_role.get('error_code')!r}")

        # §4.1: at least one of parts / text / content is REQUIRED
        no_content = {"type": "acp.message", "role": "user"}
        s_no_content, r_no_content = self.post("/message:send", no_content)
        self.check("missing content (no parts, no text) returns 400",
                   s_no_content == 400, "MUST",
                   f"got {s_no_content} — server MUST reject empty-content messages")

        if isinstance(r_no_content, dict):
            self.check("missing content error_code is ERR_INVALID_REQUEST",
                       r_no_content.get("error_code") == "ERR_INVALID_REQUEST", "MUST",
                       f"got {r_no_content.get('error_code')!r}")

        # role='agent' is valid
        s_agent, r_agent = self.post("/message:send", _msg("agent message", role="agent"))
        self.check("role='agent' is accepted",
                   s_agent in (200, 202), "MUST",
                   f"got {s_agent}")

        # Missing message_id is allowed (server auto-generates)
        no_mid = {"role": "user", "text": "no explicit message_id"}
        s_no_mid, r_no_mid = self.post("/message:send", no_mid)
        self.check("missing message_id is acceptable (server auto-assigns)",
                   s_no_mid in (200, 202), "SHOULD",
                   f"got {s_no_mid} — servers MAY auto-generate message_id")

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
