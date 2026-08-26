"""
Suite: Error Codes (ACP spec §9 / spec/error-codes.md)
Tests that error responses use the standard ACP error envelope.
"""
import uuid
from compat_base import Compat


class ErrorCodesSuite(Compat):
    SUITE_NAME = "Error Codes"

    def _check_error_envelope(self, name: str, resp: dict, level: str = "MUST") -> None:
        """Verify a response follows ACP error format."""
        self.check(f"{name}: has 'error_code'",
                   isinstance(resp.get("error_code"), str),
                   level,
                   f"got keys: {list(resp.keys())}")
        self.check(f"{name}: has 'message'",
                   isinstance(resp.get("message"), str),
                   level)

    def run(self) -> None:
        # ── 404 on unknown task ───────────────────────────────────────────────
        _, r404 = self.get(f"/tasks/no_such_{uuid.uuid4().hex[:8]}")
        if isinstance(r404, dict) and r404:
            self._check_error_envelope("404 task", r404, "SHOULD")
        else:
            self.skip("404 error envelope", "empty or non-JSON 404 response")

        # ── 400 on malformed message:send ─────────────────────────────────────
        _, r400 = self.post("/message:send", {"bad": "payload"})
        if isinstance(r400, dict) and r400:
            self._check_error_envelope("400 bad message", r400, "SHOULD")
        else:
            self.skip("400 error envelope", "empty or non-JSON 400 response")

        # ── /status endpoint ──────────────────────────────────────────────────
        s_status, r_status = self.get("/status")
        self.check("GET /status returns 200",
                   s_status == 200, "MUST",
                   f"got {s_status}")

        if isinstance(r_status, dict):
            self.check("status has 'version' field",
                       "version" in r_status, "SHOULD")
            self.check("status has 'session_id' field",
                       "session_id" in r_status or "token" in r_status, "SHOULD")

        # ── ACP standard error codes spot check ───────────────────────────────
        # Try to send to a non-existent peer (if multi-session supported)
        if self.has_capability("multi_session"):
            _, r_peer = self.post(f"/peer/no_such_peer_{uuid.uuid4().hex[:8]}/send",
                                  {"parts": [{"type": "text", "content": "test"}]})
            if isinstance(r_peer, dict) and r_peer:
                self.check("unknown peer send: error_code is 'peer_not_found'",
                           r_peer.get("error_code") in ("peer_not_found", "not_found"),
                           "SHOULD",
                           f"got '{r_peer.get('error_code')}'")
        else:
            self.skip("unknown peer error_code", "multi_session not declared")
