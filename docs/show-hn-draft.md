# Show HN Draft — ACP (Agent Communication Protocol)

> **Status**: Draft, pending review  
> **Target**: Hacker News — Show HN  
> **Date**: 2026-03-24 (last updated: 2026-03-25)
> **Timing note**: A2A has been quiet for 10+ days post-v1.0 (last merge: 2026-03-16). Window is open.

---

## Title Options

1. `Show HN: ACP – P2P Agent Communication Protocol (like WhatsApp for AI agents)`
2. `Show HN: ACP – Open protocol for agent-to-agent messaging, no central server required`
3. `Show HN: I built an open agent communication protocol because A2A felt too enterprise`

**Recommended**: Option 1 (clearest analogy)

---

## Post Body

**Show HN: ACP – P2P Agent Communication Protocol (like WhatsApp for AI agents)**

---

Over the past month I built ACP — an open protocol for AI agents to talk to each other
directly, without a central server or a cloud dependency.

**The problem**: Every AI framework has tools (MCP standardized Agent↔Tool). But there's
no lightweight standard for Agent↔Agent communication. Google's A2A protocol exists but
it's enterprise-grade: OAuth 2.0, multi-tenant infrastructure, 8 task states, gRPC
bindings, central registry. Great for Google's use case. Overkill for individuals and
small teams.

**What ACP does**:

- Any agent sends `POST /message:send`. Any other agent polls `GET /recv`. That's it.
- Two agents connect by sharing an `acp://` link. No registration. No cloud account.
- Transport: P2P WebSocket → UDP hole-punching → HTTP relay fallback (automatic)
- AgentCard discovery at `GET /.well-known/acp.json` (similar to DNS for agents)
- Works with curl. Works with any HTTP client. Language-agnostic.

**Under the hood**:

```bash
# Start a relay (you get a shareable link)
python3 acp_relay.py --name Alice

# Output:
# acp://1.2.3.4:7801/tok_abc123
# POST http://localhost:7901/message:send
# GET  http://localhost:7901/recv

# The other agent connects by pasting the link
python3 acp_relay.py --connect acp://1.2.3.4:7801/tok_abc123 --name Bob
```

From there, any code that can make HTTP requests can participate:

```bash
curl -X POST http://localhost:7901/message:send \
  -d '{"role":"agent","parts":[{"type":"text","content":"Hello Bob"}]}'
```

**What's shipping**:

- Core protocol v1.3 with task state machine, structured messages, idempotency
- Multi-peer routing (`/peer/{id}/send`) for orchestrator patterns
- Identity: `did:acp:<base58(pubkey)>` — self-sovereign DID, zero external resolver
- HMAC-SHA256 message signing (optional)
- LAN peer discovery via mDNS
- Availability metadata for heartbeat/cron agents (A2A is still discussing this in issue #1667)
- SDKs: Python, Node.js, Go, Rust, Java
- Cloudflare Worker as public relay fallback (handles NAT traversal)
- Compatibility certification test suite (Level 1: 24/24 ✅)

**Why not just use A2A?**

A2A is great if you're building enterprise agent infrastructure. ACP is for:
- Personal AI assistants talking to each other
- Small team agent pipelines (3-10 agents)
- Experiments where you don't want to run an auth server
- Any scenario where `curl` should be enough

A few things I've noticed while tracking A2A closely:

**Identity & Verification**: A2A's Working Group is converging on `getagentid.dev` as a reference identity CA (issue #1672, 47 comments). That's a central registration service — an external dependency. ACP ships `did:acp:` today: self-generated from your Ed25519 pubkey, zero external resolver, zero registration, works offline. One flag: `--identity ~/.acp/identity.json`.

And as of v1.8 (today): ACP agents **sign their own AgentCard** with their Ed25519 key. Any peer can call `POST /verify/card` to cryptographically verify "this card was signed by the owner of this `did:acp:`" — no CA, no internet required. A2A issue #1672 has 62 comments and counting, with three competing implementations (AgentID, APS, qntm) proving interoperability in the issue thread — but nothing merged into spec yet.

Meanwhile, A2A PR#1079 proposes adding a random UUID as the agent's unique identifier. ACP uses `did:acp:<base58url(pubkey)>` — not a name tag, but a cryptographic fingerprint. You can't claim someone else's `did:acp:` without their private key.

And v1.9 (also today) closes the loop: **mutual identity verification at handshake**. When two ACP agents connect, each side automatically verifies the other's AgentCard signature. `GET /peer/verify` gives you the result — `verified: true/false`, the peer's `did:acp:`, and whether the DID is consistent with the public key. Zero extra API calls. The whole identity story is: connect → verify → done.

**Discovery**: How do two agents find each other on a LAN? A2A has no spec-level answer. ACP v2.1-alpha ships `GET /peers/discover`: hit that endpoint and it scans your entire /24 subnet in 1–3 seconds using a 64-thread TCP probe. Any host with an open ACP port gets a `GET /.well-known/acp.json` fingerprint check. You get back a list of `acp://` links ready to paste into `/peers/connect`. No mDNS setup on the other side. No configuration. Just: find → connect.

**Reliability**: What happens if you send a message while the peer agent is restarting? In A2A, it's just gone — there's no offline delivery in the spec. ACP v2.0-alpha adds an **offline delivery queue**: when your peer is offline, the message is buffered locally (up to 100 per peer). The moment they reconnect, the queue auto-flushes in FIFO order. The API is unchanged — you still get `503 ERR_NOT_CONNECTED` (so existing callers aren't surprised), but your message is queued, not dropped. `GET /offline-queue` lets you see what's waiting. Short disconnects become invisible to the application layer.

**Security**: A2A's `GetTaskPushNotificationConfig` API returns full credentials in the
response by default — a security vulnerability filed as issue #1681 (still open). ACP has no
Push Notification mechanism at all. Fewer features = smaller attack surface.

**Simplicity**: ACP's cancel is synchronous and unambiguous: call `:cancel`, get back
`{"status": "canceled"}`, done. A2A has had this open since issue #1680 (March 2026) —
and as of today, issue #1684 reveals they still haven't agreed on what `CancelTaskRequest`
even *looks like*. ACP spec §10 has had a complete, tested cancel contract for two weeks.

**Spec consistency**: A2A issue #1683 (March 2026): their spec says `contextId` is *mandatory* in SSE events (§4.2.2), but the SSE streaming example in §6.2 omits it entirely — the spec contradicts itself. ACP v1.7 explicitly propagates `context_id` through every SSE event; doc and code are identical.

**What I want feedback on**:

1. Is the `acp://` link-sharing UX intuitive? (inspired by how you share a Tailscale node)
2. Should I add a hosted public relay (like ngrok for agents)? Or does that defeat the P2P ethos?
3. Is there an existing standard I missed that already solves this well?

**Links**:
- GitHub: https://github.com/Kickflip73/agent-communication-protocol
- Spec: `/spec/core-v1.3.md`
- Quickstart: `/README.md`

---

## Key Talking Points (for comments)

- **vs MCP**: MCP = Agent↔Tool. ACP = Agent↔Agent. Different layers, complementary.
- **vs A2A**: A2A is enterprise. ACP is personal/small team. Like nginx vs Apache — both valid.
- **on identity**: A2A is heading toward `getagentid.dev` (external CA). ACP uses `did:acp:` (self-sovereign, zero external service). If A2A's CA goes down, their identity story breaks. ACP works offline. And v1.8 adds AgentCard self-signatures: `POST /verify/card` gives cryptographic proof of card authenticity — no CA involved.
- **on discovery**: A2A has no LAN discovery mechanism. ACP `GET /peers/discover` scans your /24 in 1–3s — TCP probe + AgentCard fingerprint, no mDNS opt-in required from the target.
- **on reliability**: A2A drops messages silently when peer is offline — no spec-level buffering. ACP v2.0-alpha offline queue: message survives the disconnect, auto-delivered on reconnect, zero caller changes required.
- **on security**: A2A issue #1681 (open): `PushNotificationConfig` leaks credentials by default. ACP doesn't have Push Notifications — that's a feature, not a limitation.
- **on cancel semantics**: A2A issue #1680 (open, no resolution): async cancel is complex. ACP cancel is synchronous and unambiguous.
- **vs MQTT/WebSockets**: Those are transports. ACP is a semantic protocol (tasks, agent cards, identity).
- **vs HTTP APIs**: Agents aren't servers. They come and go. ACP handles NAT, discovery, availability.
- **Zero-server claim**: The Cloudflare Worker relay is a fallback, not required. P2P works without it if agents are on same LAN or have public IPs.

## Anti-trolling prep

- "Why not just use REST?" → REST assumes servers. Agents are peers.
- "This is just WebSockets" → Transports are pluggable. The protocol is the semantic layer.
- "Security concerns?" → HMAC signing + `did:acp:` self-sovereign identity (v1.5, ships today). E2E encryption on roadmap. Compare: A2A #1681 leaks credentials by default; A2A #895 (SSRF + Context ID Injection, 2026-03-25) shows attack surface from complex AgentCard URL parsing. ACP P2P has no such surface.
- "Why not just use getagentid.dev?" → External CA = external dependency + registration + potential downtime. ACP `did:acp:` is derived from your key pair, works offline, no third party.
- "A2A already does this" → A2A requires OAuth 2.0 + cloud infra. ACP runs with curl + python. Also: A2A hasn't merged code in 10+ days post-v1.0.
- "What about cancel edge cases?" → ACP cancel is synchronous: you get `canceled` back immediately. A2A is still debating this in issue #1680.
- "Is this actively maintained?" → Yes. 3 commits this week alone. Check the GitHub pulse.
- "A2A spec is more thorough?" → A2A issue #1683: their spec contradicts itself on SSE contextId (mandatory per §4.2.2, absent in §6.2 example). ACP spec = code; we ship tests alongside every spec change.

---

*Draft by J.A.R.V.I.S. · 2026-03-24 · Awaiting Stark 先生 review before posting*
