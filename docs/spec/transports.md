# ACP Transport Specification

**Status:** Draft  
**Version:** 0.3 (2026-03-20 — §3.6 transport-level HTTP headers clarification, Binding A)  
**Language:** **English** · [中文](transports.zh.md)

> **What changed in v0.3:**  
> Added §3.6 transport-level HTTP headers clarification for Binding A.  
> Explains the Binding-layer vs Extension-layer distinction for HTTP headers,  
> resolving the ambiguity raised in A2A #1653.
>
> **What changed in v0.2:**  
> Introduced the Protocol Binding / Extension distinction (inspired by A2A #1619).  
> Added Binding A (WebSocket P2P) and Binding C (HTTP Public Relay) which are the  
> two bindings implemented in `relay/acp_relay.py`.  
> Retained original Bindings B/D/E (stdio, HTTP/SSE, TCP) from v0.1.

---

## 1. Core Concept: Bindings vs Extensions

ACP separates two orthogonal concerns:

| Concept | Definition | Examples |
|---------|-----------|---------|
| **Protocol Binding** | A complete transport alternative. Replacing one binding with another changes how bits travel, but the message envelope stays identical. | WS P2P, HTTP Relay, stdio, TCP |
| **Extension** | Additional fields added to the message envelope. Extensions can be used with any binding. | `server_seq`, `message_id`, `task_id`, `context_id` |

**Rule:** An ACP implementation announces which bindings it supports in its AgentCard. A receiver that does not recognize an extension field MUST ignore it (forward-compatible).

```
┌─────────────────────────────────────────┐
│             ACP Message Envelope         │
│  (identical across all protocol bindings)│
│                                          │
│  type, message_id, ts, from, role, parts │
│  [+ optional extension fields]           │
└──────────────┬──────────────────────────┘
               │ delivered via
    ┌──────────┴──────────┐
    │  Protocol Binding   │
    │  A / B / C / D / E  │
    └─────────────────────┘
```

---

## 2. Protocol Bindings Summary

| ID | Name | Link Scheme | Latency | Network | Implemented |
|----|------|-------------|---------|---------|-------------|
| **A** | WebSocket P2P | `acp://` | <100ms | Direct IP | ✅ acp_relay.py |
| **B** | stdio | n/a | ~1ms | Subprocess | ✅ (planned SDK) |
| **C** | HTTP Public Relay | `acp+wss://` | 1–3s | HTTPS out | ✅ acp_relay.py |
| **D** | HTTP/SSE | `http(s)://` | ~10ms | Networked | ✅ (planned SDK) |
| **E** | TCP | `tcp://` | ~1ms | LAN | 📋 planned |

---

## 3. Binding A — WebSocket P2P (`acp://`)

### 3.1 Overview

The standard ACP transport. Two agents connect directly via WebSocket. No middleman stores or relays messages; the Relay helper only performs connection setup (token handshake), then steps aside.

**This is the preferred binding.** Use it whenever direct IP connectivity exists between agents.

### 3.2 Link Format

```
acp://<host>:<port>/<token>
```

- `host` — Public or LAN IP of the listening agent
- `port` — WebSocket port (default: 7801)
- `token` — Session token (`tok_` + 16 hex chars), generated at startup

**Example:**
```
acp://33.229.113.196:7801/tok_ba366fcab78d4d61
```

### 3.3 Connection Lifecycle

```
Host (listener)                   Guest (connector)
────────────────                  ─────────────────
listen(ws_port, token)
                     ←── WS connect /<token>
validate token
send AgentCard ──────────────────→
                     ←── send AgentCard
connected ✅                      connected ✅

# Either side can send messages now
send(msg) ──────────────────────→ recv(msg)
recv(msg) ←──────────────────────  send(msg)

# Disconnect
close() / network error ─────────→ ConnectionClosed
reconnect (up to MAX_RETRIES)
on exhaust → auto-fallback to Binding C
```

### 3.4 Message Framing

Each WebSocket frame carries one JSON message (text frame, UTF-8):

```json
{
  "type": "acp.message",
  "message_id": "msg_abc123def456",
  "server_seq": 42,
  "ts": "2026-03-20T02:51:00Z",
  "from": "Agent-A",
  "role": "user",
  "parts": [
    {"type": "text", "content": "Hello, Agent-B!"}
  ]
}
```

### 3.5 AgentCard Declaration

```json
{
  "capabilities": {
    "multi_session": true
  },
  "endpoints": {
    "send": "/message:send",
    "stream": "/stream",
    "peers": "/peers",
    "peer_send": "/peer/{id}/send"
  }
}
```

### 3.6 Transport-Level HTTP Headers (Binding A)

When the WebSocket upgrade request is made during connection setup, the connecting agent MAY include transport-level HTTP headers. These headers are a **Binding A concern** — they are not part of the ACP message envelope and are invisible to the application layer.

**Headers used by the reference implementation:**

| Header | Direction | Purpose |
|--------|-----------|---------|
| `X-ACP-Token` | Guest → Host | Alternative to token-in-URL; some reverse proxies strip path segments |
| `X-ACP-Agent` | Guest → Host | Agent display name (human-readable, not identity-verified) |
| `X-ACP-Version` | Both | Protocol version string (e.g. `"0.7"`) |

**Classification:**

```
Transport-level (Binding A only):     X-ACP-Token, X-ACP-Agent, X-ACP-Version
                                       ↑ Set during WS upgrade request
                                       ↑ Not visible in message envelope
                                       ↑ NOT carried over if agent switches to Binding C

Extension fields (all bindings):       message_id, server_seq, context_id, sig, task_id
                                       ↑ Part of the JSON message envelope
                                       ↑ Survive binding switches transparently
```

> **Why this matters (A2A #1653 context):** A2A has an unresolved debate about whether custom HTTP headers belong to the "Data" or "Profile Extension" layer. ACP resolves this cleanly: HTTP headers are **Binding-layer metadata** (§2 Protocol Bindings), not envelope Extensions (§2 Extensions). Any semantics that must survive a binding switch MUST be in the envelope, not in headers.

### 3.7 Limitations

- Requires both agents to have mutually reachable IPs
- Does not work in strict K8s / corporate NAT environments without port exposure
- Automatic fallback to Binding C handles these cases transparently
- Transport-level headers (§3.6) are lost when falling back to Binding C; use envelope fields for durable metadata

---

## 4. Binding B — stdio

### 4.1 Overview

The stdio binding enables two agents to communicate via standard input/output streams. It is the simplest transport: no network configuration, no ports, no TLS.

Modelled after MCP's stdio transport — the same approach that made MCP easy to adopt.

### 4.2 Message Framing

One JSON object per line (newline-delimited JSON / NDJSON):

```
{"type":"acp.message","message_id":"msg_001",...}\n
{"type":"acp.message","message_id":"msg_002",...}\n
```

### 4.3 Usage Patterns

**Pattern 1: Subprocess pipe**
```python
proc = subprocess.Popen(["python3", "agent_b.py"],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE)
# Write to proc.stdin, read from proc.stdout
```

**Pattern 2: Shell pipe**
```bash
agent_a | agent_b
```

### 4.4 Limitations

- Same-machine only (or via SSH tunnels)
- No reconnection — if the process dies, the session ends
- No AgentCard discovery (agent identity exchanged in-band via first message)

---

## 5. Binding C — HTTP Public Relay (`acp+wss://`)

### 5.1 Overview

A fallback transport for environments where direct IP connectivity is unavailable (K8s pods, corporate NAT, sandboxes). Messages are relayed through a shared HTTP endpoint. The relay holds messages briefly in KV storage for polling; it does **not** persist messages beyond TTL.

**Use only when Binding A fails.** The reference relay (`acp_relay.py`) auto-falls back to Binding C after 3 failed P2P attempts.

### 5.2 Link Format

```
acp+wss://<relay-host>/acp/<token>
```

**Example:**
```
acp+wss://black-silence-11c4.yuranliu888.workers.dev/acp/tok_ba366fcab78d4d61
```

> **Transparency principle:** The P2P token (`acp://`) and the relay token (`acp+wss://`) are the same value. When Binding A fails, the guest reuses the same token to join the relay session — no extra information exchange needed.

### 5.3 Relay Session Lifecycle

```
Host startup:
  POST /acp/new?token=<p2p_token>  →  relay pre-registers session

Guest (Binding A failed):
  POST /acp/<token>/join           →  join relay session
  GET  /acp/<token>/poll           →  long-poll for messages (1–3s)
  POST /acp/<token>/send           →  send message to relay
```

### 5.4 Self-Hosting

The relay is open-source (`relay/acp_worker.js`, Cloudflare Worker). Anyone can deploy their own:

```bash
wrangler deploy relay/acp_worker.js
```

The link naturally carries the relay host, so self-hosted relays work without any protocol changes:
```
acp+wss://my-relay.example.com/acp/tok_xyz
```

### 5.5 Limitations

- Higher latency (1–3s per message, HTTP polling)
- Relay is a third-party service (though self-hostable and open-source)
- Message TTL: 60s (configurable in acp_worker.js)
- **Not a protocol standard** — Binding C is an engineering convenience; Binding A is the ACP standard

---

## 6. Binding D — HTTP/SSE

### 6.1 Overview

The most interoperable binding for networked agents. Uses standard HTTP for sending (POST) and Server-Sent Events for receiving (streaming). Easy to debug with curl/browser.

### 6.2 Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/message:send` | Send a message |
| `GET` | `/stream` | Receive messages (SSE) |
| `GET` | `/.well-known/acp.json` | AgentCard discovery |

### 6.3 Message Framing

**Send (POST /message:send):**
```json
{
  "parts": [{"type": "text", "content": "Hello"}],
  "message_id": "msg_abc123"
}
```

**Receive (GET /stream):**
```
data: {"type":"acp.message","message_id":"msg_xyz",...}

data: {"type":"acp.message","message_id":"msg_abc",...}

: keepalive
```

### 6.4 Advantages

- Works anywhere HTTP is available
- Human-readable and curl-debuggable
- Native browser support (EventSource API)
- TLS via HTTPS — no extra work

---

## 7. Binding E — TCP (Planned)

### 7.1 Overview

Raw TCP with NDJSON framing. Intended for high-throughput, low-overhead pipelines within a datacenter or LAN.

### 7.2 Message Framing

Same as stdio: one JSON object per line, UTF-8, `\n` terminated.

### 7.3 Advantages

- Lowest overhead — no HTTP headers, no WebSocket framing
- Persistent connection — no per-message connection overhead
- TLS via TLS wrapping (e.g., stunnel, or Python `ssl.wrap_socket`)

---

## 8. Message Extensions

Extensions are optional fields added to the ACP message envelope. They work with **any** protocol binding.

| Extension Field | Type | Purpose | Spec Status |
|----------------|------|---------|-------------|
| `message_id` | string | Client-generated unique ID for deduplication | ✅ v0.5 |
| `server_seq` | integer | Server-assigned monotonic sequence number | ✅ v0.5 |
| `task_id` | string | Associates message with a Task | ✅ v0.5 |
| `context_id` | string | Groups multiple Tasks into a conversation | 📋 v0.7 |
| `correlation_id` | string | Links a reply to its original message | ✅ v0.5 |
| `to_peer` | string | Directed send target (multi-session) | ✅ v0.6 |

**Receiver MUST ignore unknown extension fields** (forward compatibility).

---

## 9. Transport Selection Guide

```
Is the peer a subprocess you control?
  YES → Binding B (stdio) — zero config, zero network

Is low-latency / high-throughput the priority (LAN/datacenter)?
  YES → Binding E (TCP, planned) or Binding A (WS P2P)

Do both agents have direct IP connectivity?
  YES → Binding A (WS P2P) ★ preferred
  NO  → Binding C (HTTP Relay) via auto-fallback

Do you need browser / curl interoperability?
  YES → Binding D (HTTP/SSE)
```

---

## 10. Multi-Binding Agents (v0.6+)

An agent MAY support multiple bindings simultaneously. The reference implementation (`acp_relay.py`) runs Binding A (WS P2P) and Binding C (HTTP Relay) concurrently:

```
acp_relay.py startup:
  1. Listen on ws_port (Binding A)
  2. POST /acp/new to pre-register relay session (Binding C fallback)
  3. Serve HTTP API on http_port (Binding D for local control)
```

AgentCard declares supported bindings:

```json
{
  "capabilities": {
    "multi_session": true,
    "bindings": ["ws-p2p", "http-relay", "http-sse"]
  }
}
```

---

## Appendix: Quick Comparison

| Feature | A: WS P2P | B: stdio | C: HTTP Relay | D: HTTP/SSE | E: TCP |
|---------|-----------|---------|--------------|-------------|--------|
| Requires network | Yes | No | Yes (HTTPS) | Yes | Yes |
| Requires open port | Yes | No | No | Yes | Yes |
| Works through NAT | No | N/A | **Yes** | No | No |
| Latency | <100ms | ~1ms | 1–3s | ~10ms | ~1ms |
| Human-readable (curl) | Partial | No | Yes | **Yes** | No |
| Streaming recv | SSE keepalive | stdin | Polling | SSE native | TCP stream |
| TLS support | wss:// | N/A | HTTPS native | HTTPS native | ssl wrap |
| Persistent conn | Yes | Process lifetime | Polling | Per-SSE | Yes |
| Recommended use | Cross-host P2P | Subprocess | NAT/sandbox | Browser/debug | LAN pipeline |
