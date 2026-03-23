# ACP vs. Existing Protocols

## Competitive Landscape (2026)

| Protocol | Creator | Scope | Open? | A2A? | Async? | Transport Agnostic? |
|----------|---------|-------|-------|------|--------|---------------------|
| **ACP** | Community | Agent↔Agent | ✅ Apache 2.0 | ✅ | ✅ | ✅ |
| MCP | Anthropic | Agent↔Tool | ✅ MIT | ❌ | ❌ | ⚠️ Mainly stdio/HTTP |
| A2A | Google | Agent↔Agent | ⚠️ Google-led | ✅ | ✅ | ⚠️ HTTP/gRPC |
| FIPA-ACL | FIPA (1997) | Agent↔Agent | ✅ | ✅ | ✅ | ⚠️ Dated |
| AutoGen wire | Microsoft | Agent↔Agent | ✅ | ✅ | ✅ | ❌ Framework-coupled |
| LangGraph | LangChain | Agent↔Agent | ✅ | ✅ | ✅ | ❌ Python-only |

## Why Not Use MCP?

MCP (Model Context Protocol) solves **Agent ↔ Tool** integration — connecting an LLM to databases, APIs, files. It's excellent for that purpose.

ACP solves **Agent ↔ Agent** communication — how an orchestrator delegates tasks to workers, how agents coordinate, discover each other, and report results. These are different layers.

**ACP + MCP together** = full-stack MAS:
```
Orchestrator
  │  (ACP)
  ├── Worker Agent A ──(MCP)──► Database Tool
  ├── Worker Agent B ──(MCP)──► Web Search Tool
  └── Worker Agent C ──(MCP)──► Code Execution Tool
```

## Why Not Use Google A2A?

A2A is a good protocol but is **vendor-driven** (Google). ACP is:
- Community-governed (no single company controls it)
- More minimal (A2A includes agent card, task manager, streaming as mandatory)
- More transport-agnostic (A2A strongly prefers HTTP/SSE)

ACP aims to be the **neutral ground** that any MAS framework can adopt.

## Why Not Use FIPA-ACL?

FIPA-ACL (1997) was ahead of its time but:
- XML-based, verbose
- No JSON support
- No async model
- Outdated infrastructure assumptions
- Very complex (hundreds of pages of spec)

ACP learns from FIPA's concepts (speech acts, performatives) but is JSON-native, minimal, and modern.

## Feature Comparison: ACP v1.2 vs A2A v1.0 vs MCP

| Feature | ACP v1.3 | A2A v1.0 | MCP |
|---------|----------|----------|-----|
| **P2P / zero-server** | ✅ Built-in | ❌ Server required | ❌ Server required |
| **Single-file deploy** | ✅ One `.py` file | ❌ Full service stack | ❌ Server + client SDK |
| **Docker image** | ✅ Official `Dockerfile` | ❌ | ❌ |
| **Scheduling metadata** | ✅ `availability` block (v1.2) | ❌ No native support (issue #1667) | ❌ |
| **Live availability update** | ✅ `PATCH /.well-known/acp.json` | ❌ | ❌ |
| **Extension mechanism** | ✅ URI-identified, runtime register/unregister (v1.3) | ⚠️ Proposed (no impl yet) | ❌ |
| **HMAC replay-window** | ✅ `--hmac-window` (v1.1) | ⚠️ OAuth only | ⚠️ OAuth only |
| **Task state machine** | ✅ 5 states (v0.5+) | ✅ 8 states | ❌ |
| **Agent Card identity verify** | ✅ `did:acp:` cryptographic self-cert (v1.3) | ❌ Open issue #1672, no impl yet | ❌ |
| **Ed25519 identity** | ✅ `--identity` flag | ✅ DID-based | ❌ |
| **DID identifier** | ✅ `did:acp:` key-based (v1.3) — no registry | ✅ `did:wba:` domain-based — requires DNS | ❌ |
| **DID Document** | ✅ `GET /.well-known/did.json` (W3C compatible) | ✅ via well-known URL | ❌ |
| **LAN discovery (mDNS)** | ✅ `--advertise-mdns` | ❌ | ❌ |
| **Multi-language SDKs** | ✅ Python / Go / Node.js / Rust | ✅ Python / JS / Java | ⚠️ Python / JS only |
| **Setup complexity** | `pip install websockets` | OAuth + agent registry | MCP server + config |
| **Target audience** | Personal/small team | Enterprise | Tool integration |

## ACP v1.2 Unique Differentiators

### 1. Scheduling Metadata (Heartbeat/Cron Agents)

ACP v1.2 is the **first Agent communication protocol** to support scheduling metadata natively in the AgentCard. An agent that wakes on a schedule can advertise:

```json
"availability": {
  "mode": "cron",
  "interval_seconds": 3600,
  "next_active_at": "2026-03-22T10:00:00Z",
  "last_active_at": "2026-03-22T09:00:00Z",
  "task_latency_max_seconds": 3600
}
```

A2A issue #1667 (filed 2026-03-21) confirms A2A has no plan for this. Callers of a cron agent can read `next_active_at` to avoid timeout storms.

### 2. Live Availability Update (PATCH)

Running heartbeat agents update their `next_active_at` / `last_active_at` on each wake without restarting:

```bash
curl -X PATCH http://localhost:8100/.well-known/acp.json \
  -H 'Content-Type: application/json' \
  -d '{"availability":{"last_active_at":"2026-03-22T09:00:00Z","next_active_at":"2026-03-22T10:00:00Z"}}'
```

### 3. Extension Mechanism (v1.3)

ACP v1.3 implements URI-identified extensions in the AgentCard — mirroring the direction A2A is proposing in issue #1667, but already shipping:

```json
"extensions": [
  { "uri": "https://acp.dev/ext/availability/v1", "required": false },
  { "uri": "https://corp.example.com/ext/billing", "required": true, "params": { "tier": "pro" } }
]
```

Unlike A2A's proposed Extension spec (which has no reference implementation), ACP ships with:
- `--extension URI[,required=true][,key=val]` CLI flag
- `POST /extensions/register` — upsert at runtime (no restart needed)
- `POST /extensions/unregister` — remove at runtime
- `GET /extensions` — list current extensions

**Cross-protocol note**: ACP extension URIs use the same `https://` URI format A2A plans to use — so an agent advertising `https://acp.dev/ext/availability/v1` is readable by any A2A-compatible client that understands that URI.

### 4. P2P with Zero Infrastructure

No central registry, no OAuth dance, no gRPC service. Two agents connect in two steps:

```
Agent A:  python3 acp_relay.py --name Alice
          → prints acp://relay.acp.dev/<id>

Agent B:  python3 acp_relay.py --name Bob --join acp://relay.acp.dev/<id>
          → connected
```

This is intentionally designed as **"WhatsApp for Agents"** — simple enough for individuals, powerful enough for teams.
