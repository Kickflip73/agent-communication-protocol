<div align="center">

<h1>ACP — Agent Communication Protocol</h1>

<p><strong>The missing link between AI Agents.</strong><br>
<em>Send a URL. Get a link. Two agents talk. That's it.</em></p>

<p>
  <a href="https://github.com/Kickflip73/agent-communication-protocol/releases">
    <img src="https://img.shields.io/badge/version-v1.4.0--dev-blue?style=flat-square" alt="Version">
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/license-Apache_2.0-green?style=flat-square" alt="License">
  </a>
  <img src="https://img.shields.io/badge/python-3.9%2B-blue?style=flat-square" alt="Python">
  <img src="https://img.shields.io/badge/stdlib__only-zero__heavy__deps-orange?style=flat-square" alt="Deps">
  <img src="https://img.shields.io/badge/latency-0.6ms_avg-brightgreen?style=flat-square" alt="Latency">
  <img src="https://img.shields.io/badge/tested-22%2F22_PASS-success?style=flat-square" alt="Tests">
</p>

<p>
  <strong>English</strong> ·
  <a href="docs/README.zh-CN.md">简体中文</a>
</p>

</div>

> **MCP standardized Agent↔Tool. ACP standardizes Agent↔Agent.**  
> P2P · Zero server required · curl-compatible · works with any LLM framework

---

```
$ # Agent A — get your link
$ python3 acp_relay.py --name AgentA
✅ Ready.  Your link: acp://1.2.3.4:7801/tok_xxxxx
           Send this link to any other Agent to connect.

$ # Agent B — connect with one API call
$ curl -X POST http://localhost:7901/peers/connect \
       -d '{"link":"acp://1.2.3.4:7801/tok_xxxxx"}'
{"ok":true,"peer_id":"peer_001"}

$ # Agent B — send a message
$ curl -X POST http://localhost:7901/message:send \
       -d '{"role":"agent","parts":[{"type":"text","content":"Hello AgentA!"}]}'
{"ok":true,"message_id":"msg_abc123","peer_id":"peer_001"}

$ # Agent A — receive in real-time (SSE stream)
$ curl http://localhost:7901/stream
event: acp.message
data: {"from":"AgentB","parts":[{"type":"text","content":"Hello AgentA!"}]}
```

---

## Quick Start

### Option A — AI Agent native (2 steps, zero config)

```
# Step 1: Send this URL to Agent A (any LLM-based agent)
https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/SKILL.md

# Agent A auto-installs, starts, and replies:
# ✅ Ready. Your link: acp://1.2.3.4:7801/tok_xxxxx

# Step 2: Send that acp:// link to Agent B
# Both agents are now directly connected. Done.
```

### Option B — Manual / script

```bash
# Install
pip install websockets

# Start Agent A
python3 relay/acp_relay.py --name AgentA
# → ✅ Ready. Your link: acp://YOUR_IP:7801/tok_xxxxx

# In another terminal — Agent B connects
python3 relay/acp_relay.py --name AgentB \
  --join acp://YOUR_IP:7801/tok_xxxxx
# → ✅ Connected to AgentA
```

### Option C — Docker

```bash
docker run -p 7801:7801 -p 7901:7901 \
  ghcr.io/kickflip73/agent-communication-protocol/acp-relay \
  --name MyAgent
```

---

## Behind NAT / Firewall / Sandbox?

ACP v1.4 includes a three-level automatic connection strategy — **zero config required**:

```
Level 1 — Direct connect       (public IP or same LAN)
   ↓ fails within 3s
Level 2 — UDP hole punch       (both behind NAT — NEW in v1.4)
           DCUtR-style: STUN address discovery → relay signaling → simultaneous probes
           Works with ~70% of real-world NAT types (full-cone, port-restricted)
   ↓ fails
Level 3 — Relay fallback       (symmetric NAT / CGNAT — ~30% of cases)
           Cloudflare Worker relay, stateless, no message storage
```

SSE events reflect the current connection level in real-time: `dcutr_started` → `dcutr_connected` / `relay_fallback`.  
`GET /status` returns `connection_type`: `p2p_direct` | `dcutr_direct` | `relay`.

To force relay mode (e.g., for backward compatibility), add `--relay` on startup to get an `acp+wss://` link.

→ **See [NAT Traversal Guide](docs/nat-traversal.md)**

---

## Architecture

### Handshake (humans only do steps 1 and 2)

```
  Human
    │
    ├─[① Skill URL]──────────────► Agent A
    │                                  │  pip install websockets
    │                                  │  python3 acp_relay.py --name A
    │                                  │  → listens on :7801/:7901
    │◄────────────[② acp://IP:7801/tok_xxx]─┘
    │
    ├─[③ acp://IP:7801/tok_xxx]──► Agent B
    │                                  │  POST /connect {"link":"acp://..."}
    │                                  │
    │          ┌────────── WebSocket Handshake ──────────┐
    │          │  B → A : connect(tok_xxx)               │
    │          │  A → B : AgentCard exchange             │
    │          │  A, B  : connected ✅                   │
    │          └──────────────────────────────────────────┘
    │
   done                ↕ P2P messages flow directly
```

### P2P Direct Mode (default)

```
  Machine A                                          Machine B
┌─────────────────────────────┐    ┌─────────────────────────────┐
│  ┌─────────────────────┐    │    │    ┌─────────────────────┐  │
│  │    Host App A       │    │    │    │    Host App B       │  │
│  │  (LLM / Script)     │    │    │    │  (LLM / Script)     │  │
│  └──────────┬──────────┘    │    │    └──────────┬──────────┘  │
│             │ HTTP          │    │               │ HTTP         │
│  ┌──────────▼──────────┐    │    │    ┌──────────▼──────────┐  │
│  │   acp_relay.py      │    │    │    │   acp_relay.py      │  │
│  │  :7901  HTTP API    │◄───┼────┼────┤  POST /message:send │  │
│  │  :7901/stream (SSE) │────┼────┼───►│  GET /stream (SSE)  │  │
│  │  :7801  WebSocket   │◄═══╪════╪═══►│  :7801  WebSocket   │  │
│  └─────────────────────┘    │    │    └─────────────────────┘  │
└─────────────────────────────┘    └─────────────────────────────┘
                         Internet / LAN (no relay server)
```

| Channel | Port | Direction | Purpose |
|---------|------|-----------|---------|
| **WebSocket** | `:7801` | Agent ↔ Agent | P2P data channel, direct peer-to-peer |
| **HTTP API** | `:7901` | Host App → Agent | Send messages, manage tasks, query status |
| **SSE** | `:7901/stream` | Agent → Host App | Real-time push of incoming messages |

**Host app integration (3 lines):**

```python
# Send a message to the remote agent
requests.post("http://localhost:7901/message:send",
              json={"role":"agent","parts":[{"type":"text","content":"Hello"}]})

# Listen for incoming messages in real-time (SSE long-poll)
for event in sseclient.SSEClient("http://localhost:7901/stream"):
    print(event.data)   # {"type":"message","from":"AgentB",...}
```

### Full Connection Strategy (v1.4 — automatic, zero user config)

```
┌────────────────────────────────────────────────────────────────┐
│             Three-Level Connection Strategy                    │
│                                                                │
│  Level 1 — Direct Connect (best)                               │
│  ┌──────────┐                          ┌──────────┐            │
│  │  Agent A │◄═══════ WS direct ══════►│  Agent B │            │
│  └──────────┘    (public IP / LAN)     └──────────┘            │
│                                                                │
│  Level 2 — UDP Hole Punch (v1.4, both behind NAT)              │
│  ┌──────────┐   ┌─────────────┐        ┌──────────┐            │
│  │  Agent A │──►│  Signaling  │◄───────│  Agent B │            │
│  │  (NAT)   │   │ (addr exch) │        │  (NAT)   │            │
│  └──────────┘   └─────────────┘        └──────────┘            │
│       │          exits after                 │                  │
│       └──────────── WS direct ──────────────┘                  │
│                    (true P2P after punch)                       │
│                                                                │
│  Level 3 — Relay Fallback (~30% symmetric NAT cases)           │
│  ┌──────────┐   ┌─────────────┐        ┌──────────┐            │
│  │  Agent A │◄─►│    Relay    │◄──────►│  Agent B │            │
│  └──────────┘   │ (stateless) │        └──────────┘            │
│                 └─────────────┘                                │
│                  frames only, no message storage               │
└────────────────────────────────────────────────────────────────┘
```

> **Signaling server** does one-time address exchange only (TTL 30s), forwards zero message frames.  
> **Relay** is the last resort, not the main path — only triggered by symmetric NAT / CGNAT.

---

## Why ACP

| | A2A (Google) | ACP |
|---|---|---|
| **Setup** | OAuth 2.0 + agent registry + push endpoint | One URL |
| **Server required** | Yes (HTTPS endpoint you must host) | **No** |
| **Framework lock-in** | Yes | **Any agent, any language** |
| **NAT / firewall** | You figure it out | **Auto: direct → hole-punch → relay** |
| **Message latency** | Depends on your infra | **0.6ms avg (P99 2.8ms)** |
| **Min dependencies** | Heavy SDK | **`pip install websockets`** |
| **Identity** | OAuth tokens | **Ed25519 + did:acp: DID + CA hybrid (v1.5)** |
| **Availability signaling** | ❌ (open issue #1667) | **✅ `availability` field (v1.2)** |
| **Agent identity proof** | ❌ (open issue #1672, 44 comments, still in discussion) | **✅ Hybrid: `did:acp:` self-sovereign + CA cert (v1.5)** |
| **Cancel task semantics** | ❌ Undefined — `CancelTaskRequest` missing, async cancel state disputed (#1680, #1684) | **✅ Synchronous + idempotent: 200 on success, 409 `ERR_TASK_NOT_CANCELABLE` on terminal state (v1.5.2 §10)** |

> A2A [#1672](https://github.com/a2aproject/A2A/issues/1672) is converging on a "hybrid identity model" after 44+ comments. ACP v1.5 ships it today.

> A2A [#1680](https://github.com/a2aproject/A2A/issues/1680) & [#1684](https://github.com/a2aproject/A2A/issues/1684) — community debate: when cancel can't complete immediately, return `WORKING` or new `CANCELING` state? `CancelTaskRequest` schema is missing from spec. ACP v1.5.2 resolves all of this with synchronous, idempotent cancel semantics.

### Numbers

- **0.6ms** avg send latency · **2.8ms** P99
- **1,100+ req/s** sequential throughput · **1,200+ req/s** concurrent (10 threads)
- **< 50ms** SSE push latency (threading.Event, not polling)
- **22/22 test scenarios PASS** (error handling · pressure test · NAT traversal · ring pipeline)
- **184+ commits** · **3,300+ lines** · **zero known P0/P1 bugs**

---

## API Reference

| Action | Method | Path |
|--------|--------|------|
| Get your link | GET | `/link` |
| Connect to a peer | POST | `/peers/connect` `{"link":"acp://..."}` |
| Send a message | POST | `/message:send` `{"role":"agent","parts":[...]}` |
| Receive in real-time | GET | `/stream` (SSE) |
| Poll inbox (offline) | GET | `/recv` |
| Query status | GET | `/status` |
| List peers | GET | `/peers` |
| AgentCard | GET | `/.well-known/acp.json` |
| Update availability | PATCH | `/.well-known/acp.json` |
| Create task | POST | `/tasks` |
| Update task | POST | `/tasks/{id}:update` |
| Cancel task | POST | `/tasks/{id}:cancel` |

HTTP default port: `7901` · WebSocket port: `7801`

---

## Optional Features

| Feature | Flag | Notes |
|---------|------|-------|
| Public relay (NAT fallback) | `--relay` | Returns `acp+wss://` link |
| HMAC message signing | `--secret <key>` | Shared secret, no extra deps |
| Ed25519 identity | `--identity` | Requires `pip install cryptography` |
| mDNS LAN discovery | `--advertise-mdns` | No zeroconf library needed |
| Docker | `docker pull ghcr.io/kickflip73/agent-communication-protocol/acp-relay` | Multi-arch, GHCR CI |

---

## Task State Machine

Track cross-agent task progress:

```
submitted → working → completed ✅
                    → failed    ❌
                    → input_required → working (waiting for more input)
```

API: `POST /tasks` to create · `POST /tasks/{id}:update` to update status.

---

## Heartbeat / Cron Agents

ACP natively supports **offline agents** (cron-style agents that wake up periodically), no persistent connection required.

### How it works

```
Cron Agent wakes up every 5 minutes:
1. Start acp_relay.py (get an acp:// link)
2. PATCH /.well-known/acp.json to broadcast availability
3. GET /recv to drain queued messages, process in batch
4. POST /message:send to reply
5. Exit (relay shuts down cleanly)
```

```python
# Python — cron agent template
import subprocess, time, requests

relay = subprocess.Popen(["python3", "relay/acp_relay.py", "--name", "MyCronAgent"])
time.sleep(1)   # wait for startup

BASE = "http://localhost:7901"

# Broadcast availability
requests.patch(f"{BASE}/.well-known/acp.json", json={
    "availability": {
        "mode": "cron",
        "last_active_at": "2026-03-24T10:00:00Z",
        "next_active_at": "2026-03-24T10:05:00Z",
        "task_latency_max_seconds": 300,
    }
})

# Drain and process queued messages
msgs = requests.get(f"{BASE}/recv?limit=100").json()["messages"]
for m in msgs:
    text = m["parts"][0]["content"]
    requests.post(f"{BASE}/message:send",
                  json={"role":"agent","parts":[{"type":"text","content":f"Processed: {text}"}]})

relay.terminate()
```

> **Why it matters:** A2A [#1667](https://github.com/a2aproject/A2A/issues/1667) is still discussing heartbeat agent support as a proposal. ACP `/recv` solves this natively — available today.

---

## Agent Identity (v1.5)

ACP supports **two identity models**, usable standalone or combined (hybrid):

| Mode | Flag | `capabilities.identity` | Notes |
|------|------|--------------------------|-------|
| None | _(default)_ | `"none"` | Backward-compatible with v0.7 |
| Self-sovereign | `--identity` | `"ed25519"` | Ed25519 signing + `did:acp:` DID |
| **Hybrid** | `--identity --ca-cert` | `"ed25519+ca"` | Self-sovereign + CA-issued certificate |

```bash
# Self-sovereign identity (v0.8+)
python3 relay/acp_relay.py --name MyAgent --identity

# Hybrid identity (v1.5) — CA cert file
python3 relay/acp_relay.py --name MyAgent --identity --ca-cert /path/to/agent.crt

# Hybrid identity (v1.5) — inline PEM
python3 relay/acp_relay.py --name MyAgent --identity \
  --ca-cert "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----"
```

**AgentCard example (hybrid mode):**
```json
{
  "identity": {
    "scheme":     "ed25519+ca",
    "public_key": "<base64url-encoded Ed25519 public key>",
    "did":        "did:acp:<base64url(pubkey)>",
    "ca_cert":    "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----"
  },
  "capabilities": {
    "identity": "ed25519+ca"
  }
}
```

**Verification strategy** (verifier's choice):
- Trust only `did:acp:` — verify Ed25519 signature, ignore `ca_cert`
- Trust only CA — verify certificate chain, ignore DID
- Require both — highest security
- Accept either — highest interoperability

> **Why it matters:** A2A [#1672](https://github.com/a2aproject/A2A/issues/1672) (44 comments, still in discussion) is converging on the same hybrid model. ACP v1.5 ships it today.

---

## SDKs

| Language | Path | Notes |
|----------|------|-------|
| **Python** | `sdk/python/` | `RelayClient` class |
| **Node.js** | `sdk/node/` | Zero external deps, TypeScript types included |
| **Go** | `sdk/go/` | Zero external deps, Go 1.21+ |
| **Rust** | `sdk/rust/` | v1.3, reqwest + serde |
| **Java** | `sdk/java/` | Zero external deps, JDK 11+, Spring Boot example included |

---

## Changelog

| Version | Status | Highlights |
|---------|--------|------------|
| v0.1–v0.5 | ✅ | P2P core, task state machine, message idempotency |
| v0.6 | ✅ | Multi-peer registry, standard error codes |
| v0.7 | ✅ | HMAC signing, mDNS discovery |
| v0.8–v0.9 | ✅ | Ed25519 identity, Node.js SDK, compat test suite |
| v1.0 | ✅ | Production-stable, security audit, Go SDK |
| v1.1 | ✅ | HMAC replay-window, `failed_message_id` |
| v1.2 | ✅ | Scheduling metadata (`availability`), Docker image |
| v1.3 | ✅ | Rust SDK, DID identity (`did:acp:`), Extension mechanism, GHCR CI |
| **v1.4** | ✅ | **True P2P NAT traversal**: UDP hole-punch (DCUtR-style) + signaling, three-level auto-fallback |
| **v1.5** | ✅ | **Hybrid identity**: `--ca-cert` adds CA certificate on top of `did:acp:` self-sovereign identity |

---

## Repository Structure

```
agent-communication-protocol/
├── SKILL.md              ← Send this URL to any agent to onboard
├── relay/
│   └── acp_relay.py      ← Core daemon (single file, stdlib-first)
├── spec/                 ← Protocol specification documents
├── sdk/                  ← Python / Node.js / Go / Rust / Java SDKs
├── tests/                ← Compatibility + integration test suites
├── docs/                 ← Chinese docs, conformance guide, blog drafts
└── acp-research/         ← Competitive intelligence, ROADMAP
```

---

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md).

- Bug reports & feature requests → [GitHub Issues](https://github.com/Kickflip73/agent-communication-protocol/issues)
- Protocol design discussion → [GitHub Discussions](https://github.com/Kickflip73/agent-communication-protocol/discussions)

---

## License

[Apache License 2.0](LICENSE)

---

<div align="center">
<sub>MCP standardizes Agent↔Tool. ACP standardizes Agent↔Agent. P2P · Zero server · curl-compatible.</sub>
</div>
