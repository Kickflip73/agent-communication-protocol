"""
Suite: Multi-Session Peers (ACP spec §7)
Tests /peers and /peer/{id}/send endpoints.
Only runs if capabilities.multi_session is declared.
"""
from compat_base import Compat


class PeersSuite(Compat):
    SUITE_NAME = "Multi-Session Peers"

    def run(self) -> None:
        if not self.has_capability("multi_session"):
            self.skip("GET /peers", "multi_session not declared in AgentCard")
            self.skip("/peers returns list", "multi_session not declared")
            self.skip("/peers items have required fields", "multi_session not declared")
            self.skip("/peer/{id}/send endpoint exists", "multi_session not declared")
            self.skip("unknown peer returns 404", "multi_session not declared")
            return

        # ── GET /peers ────────────────────────────────────────────────────────
        s_peers, r_peers = self.get("/peers")
        self.check("GET /peers returns 200",
                   s_peers == 200, "MUST",
                   f"got {s_peers}")

        self.check("/peers returns a list",
                   isinstance(r_peers, list), "MUST",
                   f"got {type(r_peers).__name__}")

        if isinstance(r_peers, list) and len(r_peers) > 0:
            peer = r_peers[0]
            self.check("/peers[0] has 'peer_id'",
                       isinstance(peer.get("peer_id"), str), "MUST")
            self.check("/peers[0] has 'name'",
                       isinstance(peer.get("name"), str), "SHOULD")
            self.check("/peers[0] has 'link'",
                       isinstance(peer.get("link"), str), "SHOULD")
        else:
            self.skip("/peers items have required fields",
                      "no peers connected (empty list is valid)")

        # ── GET /peer/{id} ────────────────────────────────────────────────────
        s_peer_404, _ = self.get("/peer/no_such_peer_xyz_compat")
        self.check("GET /peer/{unknown} returns 404",
                   s_peer_404 == 404, "MUST",
                   f"got {s_peer_404}")

        # ── POST /peer/{id}/send ──────────────────────────────────────────────
        # Just verify the endpoint exists (404 on unknown peer, not 405/404-on-route)
        import uuid, time
        msg = {
            "type": "acp.message",
            "message_id": f"msg_{uuid.uuid4().hex[:16]}",
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "from": "compat-runner",
            "role": "user",
            "parts": [{"type": "text", "content": "compat peer send test"}],
        }
        s_psend, r_psend = self.post("/peer/no_such_peer_xyz_compat/send", msg)
        self.check("/peer/{unknown}/send returns 404 (not 405 Method Not Allowed)",
                   s_psend == 404, "MUST",
                   f"got {s_psend} — 405 means endpoint exists but method wrong")
