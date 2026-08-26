# Show HN Draft — ACP (Agent Communication Protocol)

> **Status**: Draft v2.86 — pending Stark 先生 review before posting  
> **Target**: Hacker News — Show HN  
> **Last updated**: 2026-04-09 (v2.87 features incorporated)  
> **Timing note**: A2A v1.0.1 just dropped (bugfix only). Identity issue #1672 still has 403 comments, no implementation. Our window is wide open.

---

## Title Options

1. `Show HN: ACP – P2P Agent Communication Protocol (like WhatsApp for AI agents)`
2. `Show HN: ACP – Open protocol for agent-to-agent messaging, zero central server`
3. `Show HN: I built a P2P agent comm protocol because A2A felt too enterprise`

**Recommended**: Option 1 (clearest analogy)

---

## Post Body

---

**Show HN: ACP – P2P Agent Communication Protocol (like WhatsApp for AI agents)**

Over the past month I built ACP — an open protocol for AI agents to talk to each other directly, without a central server or cloud dependency.

**The problem**: MCP standardized Agent↔Tool. Nobody standardized Agent↔Agent. Google's A2A exists but it's enterprise-grade: OAuth 2.0, multi-tenant infra, 8 task states, central registry. Great for Google's use case. Overkill for individuals and small teams.

**What ACP does in two steps**:

```bash
# Agent A — start, get a shareable link
$ python3 acp_relay.py --name AgentA
✅ Ed25519 identity loaded  did:acp:z6Mkv...
✅ Ready.  Your link: acp://1.2.3.4:7801/tok_xxxxx
           Send this link to any other Agent to connect.

# Agent B — connect with one HTTP call
$ curl -X POST http://localhost:7901/peers/connect \
       -d '{"link":"acp://1.2.3.4:7801/tok_xxxxx"}'
{"ok":true,"peer_id":"peer_001"}

# Send a message — any HTTP client works
$ curl -X POST http://localhost:7901/message:send \
       -d '{"role":"agent","parts":[{"type":"text","content":"Hello AgentA!"}]}'
{"ok":true,"message_id":"msg_abc123"}

# Receive in real-time
$ curl http://localhost:7901/stream
event: acp.message
data: {"from":"AgentB","parts":[{"type":"text","content":"Hello AgentA!"}]}
```

That's the whole API surface for a working chat. Three endpoints. No auth server. No registration.

---

**What's shipping (v2.87.0, 1100+ tests passing)**:

- **Ed25519 identity — default on**: Every agent gets a self-sovereign `did:acp:` keypair on first run. No flag needed. `--no-identity` is the escape hatch for testing.
- **AgentCard self-signatures + mutual verification**: Agents sign their own cards at connect-time. `POST /verify/card` gives cryptographic proof of card authenticity — no CA, works offline.
- **Governance/compliance standards declaration**: `--policy-compliance OWASP-ASVS,NIST-AIRMF` publishes which standards your agent conforms to, queryable via `GET /policy-compliance` and runtime-updatable via `PATCH`. (A2A #1717 still in proposal stage — ACP ships it.)
- **Automatic NAT traversal** — 3 levels: P2P direct → UDP hole-punch → Relay fallback. Zero user config.
- **Task state machine**: 5 states (submitted/working/completed/failed/input_required), SSE events for each transition.
- **Multi-peer routing** (`/peers/broadcast`, `/peer/{id}/send`) for orchestrator patterns.
- **Offline delivery queue**: messages buffered when peer is offline, auto-flushed on reconnect.
- **AgentCard `limitations` field**: machine-readable capability constraints (rate limits, unsupported inputs). Filterable at discovery time.
- **LAN peer discovery**: `GET /peers/discover` — 64-thread TCP subnet scan, no mDNS required.
- **`GET /protocol-binding/compatibility`**: structured JSON declaring protocol support levels (websocket=native, http/sse=native, a2a=partial, anp=partial).
- **Persistent message history**: `GET /messages` + `GET /peers/{id}/messages` with cursor pagination.
- Zero heavy dependencies — stdlib only (`websockets` is the only install).

---

**Why not just use A2A?**

A2A is great if you're building enterprise agent infrastructure. ACP is for:
- Personal AI assistants that need to coordinate
- Small team agent pipelines (2–10 agents)
- Experiments where you don't want to run an auth server
- Any scenario where `curl` should be enough to participate

Here's where I think ACP makes different choices worth discussing:

**Identity**: A2A's Working Group has been converging on `getagentid.dev` as a reference identity CA (issue #1672, **403 comments**, still open). That's an external CA — registration required, potential downtime. ACP ships `did:acp:` today: derived from your Ed25519 pubkey, zero external resolver, zero registration, works offline. As of v2.85, it's **default-on** — you don't opt in, you opt out. Two agents connecting automatically exchange and verify each other's identities at handshake.

**Simplicity**: ACP's entire protocol surface is: connect (one POST) + send (one POST) + receive (one GET stream). The `acp://` link is like a Tailscale invite link — opaque, self-contained, works across NAT. You paste it, you're connected.

**Zero-server P2P**: The Cloudflare Worker relay is a Level-3 fallback, not required. Same-LAN agents connect in 0.6ms (measured). The relay is just for when both sides are behind strict NAT.

**Discovery**: A2A has no spec-level LAN discovery. ACP `GET /peers/discover` scans your /24 in 1–3s, returns ready-to-use `acp://` links for every ACP-speaking host on the network.

**`curl` is a first-class citizen**: Every endpoint in ACP is plain HTTP. No SDK required. A bash script is a valid ACP agent.

---

**What I want feedback on**:

1. Is the `acp://` link-sharing UX intuitive? (inspired by how you share a Tailscale invite)
2. Should there be a hosted public relay? Or does that defeat the P2P ethos?
3. Is there an existing standard I missed that solves this well?
4. The identity story — self-sovereign Ed25519 vs CA-based. Is the tradeoff right?

**Links**:
- GitHub: https://github.com/Kickflip73/agent-communication-protocol
- Spec: `spec/core-v1.3.md`
- Quickstart: `README.md`
- Protocol compatibility: `GET /protocol-binding/compatibility`

---

## Key Talking Points (for comments)

- **vs MCP**: MCP = Agent↔Tool. ACP = Agent↔Agent. Different layers, complementary.
- **vs A2A**: A2A is enterprise. ACP is personal/small team. Like nginx vs Kubernetes — both valid, different scale.
- **on identity**: A2A issue #1672 (403 comments, open since March): still no merged implementation. ACP v2.85 ships Ed25519 identity default-on — self-sovereign, zero CA, works offline.
- **on discovery**: A2A has no LAN discovery spec. ACP `GET /peers/discover` scans /24 in <3s — TCP probe + AgentCard fingerprint, zero config.
- **on reliability**: ACP offline queue: messages survive peer restarts, auto-delivered on reconnect, zero caller changes needed.
- **on cancel semantics**: A2A issue #1680 (open, no resolution). ACP cancel is synchronous — you get `{"status":"canceled"}` immediately.
- **on limitations metadata**: ACP v2.7 `limitations` in AgentCard. A2A issue #1694 proposed same thing same week — still unimplemented.
- **vs MQTT/WebSockets**: Those are transports. ACP is a semantic protocol (tasks, identity, discovery, routing).
- **vs HTTP APIs**: Agents aren't servers. They come and go, live behind NAT, restart mid-conversation. ACP handles all of that.

## Anti-troll prep

- "Why not just use REST?" → REST assumes servers. Agents are ephemeral peers behind NAT.
- "This is just WebSockets" → WebSocket is the transport. The protocol is the semantic layer above it.
- "Security?" → Ed25519 identity default-on (v2.85). AgentCard self-signatures. Mutual verification at handshake. No push notification credential leak (compare: A2A #1681, still open).
- "Why not just use getagentid.dev?" → External CA = external dependency. ACP `did:acp:` is derived from your key pair, works offline, no third party ever involved.
- "A2A already does this" → A2A requires OAuth + cloud infra. ACP runs with `curl` + Python stdlib. ACP v1.0.1 shipped bugfixes; ACP v2.85 shipped default-on identity this week.
- "Is it maintained?" → 1092 tests, commits this week. Check the GitHub pulse.

---

## Posting Checklist

- [ ] Stark 先生 review + approve
- [ ] Record 2-agent demo (Alpha ↔ Beta, curl interaction, real terminal)
- [ ] Verify all GitHub links are public
- [ ] Best time: Monday or Tuesday, 9–10 AM ET (US East)
- [ ] Post from personal HN account (not bot/org)

---

## Version History

| Date | Change |
|------|--------|
| 2026-04-09 | v2.87 update: policy_compliance[] governance standards (A2A #1717 抢先落地), test count 1100+, last-updated bump |
| 2026-04-08 | v2.86 update: Ed25519 default-on, compatibility endpoint, A2A #1672 updated (403 comments), v2.85 test count (1092), SLIMRPC mention removed (too early) |
| 2026-03-28 | v1.5 update: DID, Docker, conformance, A2A #1680/#1684 compare |
| 2026-03-24 | Initial draft |
