# Show HN Draft — ACP (Agent Communication Protocol)

> **Status**: Draft, pending review  
> **Target**: Hacker News — Show HN  
> **Date**: 2026-03-24

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

A2A's Working Group is now converging on `getagentid.dev` as a reference identity CA
(issue #1672, 47 comments). That's a central registration service — an external dependency.
ACP ships `did:acp:` today: self-generated from your Ed25519 pubkey, zero external resolver,
zero registration, works offline. One flag: `--identity ed25519`.

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
- **on identity**: A2A is heading toward `getagentid.dev` (external CA). ACP uses `did:acp:` (self-sovereign, zero external service). If A2A's CA goes down, their identity story breaks. ACP works offline.
- **vs MQTT/WebSockets**: Those are transports. ACP is a semantic protocol (tasks, agent cards, identity).
- **vs HTTP APIs**: Agents aren't servers. They come and go. ACP handles NAT, discovery, availability.
- **Zero-server claim**: The Cloudflare Worker relay is a fallback, not required. P2P works without it if agents are on same LAN or have public IPs.

## Anti-trolling prep

- "Why not just use REST?" → REST assumes servers. Agents are peers.
- "This is just WebSockets" → Transports are pluggable. The protocol is the semantic layer.
- "Security concerns?" → HMAC signing + `did:acp:` self-sovereign identity (v1.5, ships today). E2E encryption on roadmap.
- "Why not just use getagentid.dev?" → External CA = external dependency + registration + potential downtime. ACP `did:acp:` is derived from your key pair, works offline, no third party.
- "A2A already does this" → A2A requires OAuth 2.0 + cloud infra. ACP runs with curl + python.

---

*Draft by J.A.R.V.I.S. · 2026-03-24 · Awaiting Stark 先生 review before posting*
