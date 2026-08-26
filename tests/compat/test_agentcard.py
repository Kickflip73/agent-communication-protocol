"""
Suite: AgentCard (ACP spec §3)
Tests that /.well-known/acp.json returns a valid AgentCard.
"""
from compat_base import Compat


class AgentCardSuite(Compat):
    SUITE_NAME = "AgentCard"

    def run(self) -> None:
        status, card = self.get("/.well-known/acp.json")

        # ── Reachability ──────────────────────────────────────────────────────
        self.check("GET /.well-known/acp.json returns 200",
                   status == 200, "MUST",
                   f"got {status}")

        if status != 200:
            # Nothing else can pass — mark all remaining as failed
            for name in ["has 'name' field", "has 'version' field",
                         "has 'protocol' field", "protocol == 'acp'",
                         "has 'capabilities' object", "has 'endpoints' object",
                         "endpoints.send present"]:
                self.check(name, False, "MUST", "skipped: card unreachable")
            return

        # ── Required top-level fields ─────────────────────────────────────────
        self.check("has 'name' field",
                   isinstance(card.get("name"), str) and len(card["name"]) > 0,
                   "MUST")

        self.check("has 'version' field",
                   isinstance(card.get("version"), str),
                   "MUST")

        self.check("has 'protocol' field",
                   "protocol" in card,
                   "MUST")

        self.check("protocol == 'acp'",
                   card.get("protocol") == "acp",
                   "MUST",
                   f"got '{card.get('protocol')}'")

        # ── capabilities ──────────────────────────────────────────────────────
        caps = card.get("capabilities", None)
        self.check("has 'capabilities' object",
                   isinstance(caps, dict),
                   "MUST")

        # ── endpoints ─────────────────────────────────────────────────────────
        endpoints = card.get("endpoints", None)
        self.check("has 'endpoints' object",
                   isinstance(endpoints, dict),
                   "MUST")

        if isinstance(endpoints, dict):
            self.check("endpoints.send present",
                       "send" in endpoints,
                       "MUST",
                       "endpoint for POST /message:send must be declared")
        else:
            self.check("endpoints.send present", False, "MUST",
                       "endpoints object missing")

        # ── SHOULD fields ─────────────────────────────────────────────────────
        self.check("has 'description' field",
                   isinstance(card.get("description"), str),
                   "SHOULD")

        # ── Optional capability consistency ───────────────────────────────────
        if isinstance(caps, dict) and caps.get("hmac_signing"):
            trust = card.get("trust", {})
            self.check("trust.scheme declared when hmac_signing=true",
                       isinstance(trust.get("scheme"), str),
                       "MUST",
                       "when capabilities.hmac_signing=true, trust.scheme must be set")

        if isinstance(caps, dict) and caps.get("lan_discovery"):
            self.check("endpoints.discover present when lan_discovery=true",
                       isinstance(endpoints, dict) and "discover" in endpoints,
                       "SHOULD")
