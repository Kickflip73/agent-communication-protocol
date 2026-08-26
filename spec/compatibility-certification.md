# ACP Compatibility Certification Guide

> **Version**: 1.0  
> **Status**: Draft  
> **Last Updated**: 2026-03-24

This document defines how to certify that your implementation is ACP-compatible.
A "certified" implementation guarantees interoperability with any other certified ACP relay or client.

---

## Overview

ACP compatibility has two levels:

| Level | Name | Description |
|-------|------|-------------|
| **Level 1** | Core | Basic message send/recv, agent card, ping |
| **Level 2** | Full | All Level 1 + tasks, peers, SSE stream, availability |

Implementations may self-certify by running the official test suite against their relay.

---

## Level 1 — Core Certification

### Required Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/ping` | Health check — must return `{"status":"ok"}` |
| `GET` | `/.well-known/acp.json` | AgentCard discovery |
| `POST` | `/message:send` | Send a message |
| `GET` | `/recv` | Receive messages |

### AgentCard Requirements

The `GET /.well-known/acp.json` response **MUST** include:

```json
{
  "name": "<string>",
  "version": "<semver>",
  "acp_version": "1.x",
  "link": "acp://<host>:<port>/<session_id>",
  "capabilities": {
    "streaming": <bool>,
    "push_notifications": <bool>
  }
}
```

Optional fields (Level 2): `availability`, `identity`, `extensions`.

### Message Format

`POST /message:send` request body:

```json
{
  "role": "user" | "agent",
  "parts": [
    {"type": "text", "text": "<string>"}
  ]
}
```

Optional: `message_id` (string, client-generated idempotency key), `task_id`, `context_id`.

`GET /recv` response:

```json
{
  "messages": [
    {
      "type": "acp.message",
      "message_id": "<string>",
      "ts": <unix_ms>,
      "from": "<peer_id>",
      "role": "user" | "agent",
      "parts": [...]
    }
  ]
}
```

### Error Format

All error responses **MUST** use:

```json
{
  "error": "<ERROR_CODE>",
  "message": "<human readable>",
  "failed_message_id": "<string>" | null
}
```

Standard error codes: `ERR_INVALID_REQUEST`, `ERR_NOT_FOUND`, `ERR_NOT_CONNECTED`,
`ERR_RATE_LIMITED`, `ERR_INTERNAL`, `ERR_UNAUTHORIZED`.

---

## Level 2 — Full Certification

### Additional Required Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/status` | Relay status + uptime |
| `GET` | `/tasks` | List tasks with pagination |
| `POST` | `/message:cancel` | Cancel a pending task |
| `GET` | `/peers` | List connected peers |
| `POST` | `/peers/connect` | Connect to a remote peer |
| `POST` | `/peer/{id}/send` | Send message to specific peer |
| `GET` | `/stream` | SSE event stream |
| `PATCH` | `/.well-known/acp.json` | Update availability metadata |
| `POST` | `/skills/query` | QuerySkill — runtime capability introspection |

### Task State Machine

Implementations **MUST** support exactly 5 task states:

```
submitted → working → completed
                   → failed
                   → input_required → working (resume)
```

Terminal states: `completed`, `failed`.  
Non-terminal: `submitted`, `working`, `input_required`.

### SSE Stream Format

`GET /stream` **MUST** emit Server-Sent Events with `Content-Type: text/event-stream`.

Event types:

```
event: status
data: {"task_id":"...","state":"working","ts":...}

event: artifact  
data: {"task_id":"...","part":{...},"index":0,"append":false,"last_chunk":true}

event: message
data: {"message_id":"...","role":"agent","parts":[...]}
```

### Availability Metadata

`PATCH /.well-known/acp.json` body:

```json
{
  "availability": {
    "mode": "persistent" | "heartbeat" | "cron" | "manual",
    "interval_seconds": <int>,
    "last_active_at": "<ISO-8601>",
    "next_active_at": "<ISO-8601>",
    "task_latency_max_seconds": <int>
  }
}
```

---

## Running the Certification Test Suite

### Prerequisites

```bash
pip install websockets requests
git clone https://github.com/Kickflip73/agent-communication-protocol
cd agent-communication-protocol
```

### Level 1 Certification

```bash
# Point RELAY_URL at your implementation
export ACP_TARGET_URL="http://your-relay:7901"
python3 tests/cert/test_level1.py
```

### Level 2 Certification

```bash
export ACP_TARGET_URL="http://your-relay:7901"
python3 tests/cert/test_level2.py
```

### Expected Output

```
ACP Compatibility Certification — Level 1
==========================================
✅ C1-01  GET /ping → {"status":"ok"}
✅ C1-02  GET /.well-known/acp.json → valid AgentCard
✅ C1-03  AgentCard has required fields (name, version, acp_version, link, capabilities)
✅ C1-04  POST /message:send → 200 with message_id
✅ C1-05  GET /recv → 200 with messages array
✅ C1-06  Idempotent send (same message_id twice → same response)
✅ C1-07  Invalid JSON → 400 ERR_INVALID_REQUEST
✅ C1-08  Missing role field → 400 ERR_INVALID_REQUEST
✅ C1-09  Error response has required fields (error, message)
✅ C1-10  Content-Type: application/json on all responses

Level 1: 10/10 PASS — ✅ CERTIFIED
```

---

## Certification Badge

Once your implementation passes all tests, you may display:

```markdown
[![ACP Level 1 Compatible](https://img.shields.io/badge/ACP-Level%201%20Compatible-blue)](https://github.com/Kickflip73/agent-communication-protocol/blob/main/spec/compatibility-certification.md)

[![ACP Level 2 Compatible](https://img.shields.io/badge/ACP-Level%202%20Compatible-green)](https://github.com/Kickflip73/agent-communication-protocol/blob/main/spec/compatibility-certification.md)
```

---

## Known Certified Implementations

| Implementation | Level | Language | Link |
|---------------|-------|----------|------|
| `acp_relay.py` (reference) | **2** | Python | [relay/acp_relay.py](../relay/acp_relay.py) |

*To add your implementation, open a PR updating this table.*

---

## Versioning

This certification spec tracks ACP core spec versions.

| Cert Spec | ACP Version | Notes |
|-----------|-------------|-------|
| 1.0 | 1.x | Initial certification spec |

---

*ACP Compatibility Certification Guide v1.0 · 2026-03-24*
