# ACP Core Specification — v0.5

**Status:** Stable Draft  
**Authors:** ACP Community  
**Date:** 2026-03-19  
**License:** Apache 2.0  
**Previous:** [core-v0.1.md](core-v0.1.md)

---

## Overview

v0.5 introduces three foundational additions to the ACP core:

1. **Structured Part model** — typed message content (text / file / data)
2. **Task lifecycle** — 5-state machine with terminal guards and interruption support
3. **Message idempotency** — client-generated `message_id` with server-side deduplication

These additions bring ACP closer to A2A's data model while preserving our core design
principles: **zero-server, zero-config, curl-compatible**.

---

## 1. Part Model

A **Part** is the atomic unit of message content. Every message carries one or more Parts.

### 1.1 Part Types

#### Text Part
```json
{
  "type": "text",
  "content": "string content here"
}
```
- `content` MUST be a string.
- Use for natural language, instructions, and plain-text data.

#### File Part
```json
{
  "type": "file",
  "url": "https://example.com/report.pdf",
  "media_type": "application/pdf",
  "filename": "report.pdf"
}
```
- `url` REQUIRED. Must be an accessible HTTP/HTTPS URL.
- `media_type` RECOMMENDED. Standard MIME type.
- `filename` OPTIONAL. Display name hint.
- ACP does **not** inline raw bytes — use URL references only. This keeps messages lightweight and relay-friendly.

#### Data Part
```json
{
  "type": "data",
  "content": { "any": "json", "value": true }
}
```
- `content` can be any valid JSON value (object, array, number, string, boolean, null).
- Use for structured payloads, tool results, and machine-readable data.

### 1.2 Message Envelope

```json
{
  "type":       "acp.message",
  "message_id": "msg_a1b2c3d4e5f6",
  "ts":         "2026-03-19T04:00:00Z",
  "from":       "Agent-A",
  "role":       "user",
  "parts": [
    {"type": "text", "content": "Summarize this file."},
    {"type": "file", "url": "https://example.com/doc.pdf", "media_type": "application/pdf"}
  ],
  "task_id":    "task_optional",
  "context_id": "ctx_optional"
}
```

**Required fields:** `type`, `ts`, `parts`  
**Recommended:** `message_id`, `from`, `role`  
**Optional:** `task_id`, `context_id`

---

## 2. Task Lifecycle

### 2.1 States

```
submitted ──► working ──► completed   (terminal)
                     └──► failed      (terminal)
                     └──► input_required   (interrupted; resumes via /continue)
```

| State | Type | Description |
|-------|------|-------------|
| `submitted` | Active | Task received, not yet started |
| `working` | Active | Task is being processed |
| `completed` | **Terminal** | Task finished successfully |
| `failed` | **Terminal** | Task finished with error |
| `input_required` | Interrupted | Processing paused; awaiting additional input |

### 2.2 Transition Rules

- Terminal states (`completed`, `failed`) are **irreversible**. Implementations MUST reject state updates that attempt to re-activate a terminal task.
- `input_required` is not terminal — the task can resume to `working` via `/tasks/{id}/continue`.
- Direct `submitted → completed` is valid for synchronous tasks.

### 2.3 Task Object

```json
{
  "id":         "task_a1b2c3",
  "status":     "working",
  "created_at": "2026-03-19T04:00:00Z",
  "updated_at": "2026-03-19T04:00:05Z",
  "payload":    { ... },
  "artifacts":  [],
  "history":    [],
  "error":      null
}
```

### 2.4 Artifacts

When a task produces output, it is delivered as an **Artifact**:

```json
{
  "artifact_id": "art_xyz",
  "name":        "Analysis Report",
  "parts": [
    {"type": "text",  "content": "Summary: ..."},
    {"type": "file",  "url": "https://example.com/report.pdf", "media_type": "application/pdf"}
  ]
}
```

Artifacts are appended to `task.artifacts[]` and broadcast via a `type=artifact` SSE event.

---

## 3. Message Idempotency

### 3.1 Client-Generated `message_id`

- The sending agent SHOULD generate a unique `message_id` per message.
- Format: any opaque string ≤ 128 characters. Recommended: `msg_<12-char hex>`.
- The receiving implementation MUST deduplicate on `message_id` within a session.

### 3.2 Deduplication Semantics

- If a `message_id` has already been processed in the current session, the duplicate MUST be silently dropped (no error, no re-processing).
- Deduplication state is **session-scoped** — the same `message_id` on a new session is treated as a new message.
- Implementations should bound their deduplication cache (reference implementation: 2000 entries, LRU eviction).

### 3.3 Omitting `message_id`

If `message_id` is absent or empty, the message is processed without idempotency guarantees. This is allowed for fire-and-forget use cases.

---

## 4. SSE Event Types

The `/stream` endpoint emits structured events, each with a `type` field:

### `status` — Task state changed
```
data: {"type":"status","ts":"...","task_id":"task_x","state":"working","error":null}
```

### `artifact` — Task produced output
```
data: {"type":"artifact","ts":"...","task_id":"task_x","artifact":{...}}
```

### `message` — New inbound message
```
data: {"type":"message","ts":"...","message_id":"msg_x","role":"user","parts":[...],"task_id":"task_x"}
```

### `peer` — Connection state changed
```
data: {"type":"peer","ts":"...","event":"connected","session_id":"sess_x"}
data: {"type":"peer","ts":"...","event":"disconnected"}
```

Consumers SHOULD handle unknown `type` values gracefully (ignore and continue).

---

## 5. AgentCard v2

Every ACP node exposes its identity and capabilities at `GET /.well-known/acp.json`.

```json
{
  "name":        "Summarizer-Agent",
  "version":     "1.0.0",
  "acp_version": "0.5",
  "description": "Summarizes documents and web pages",
  "http_port":   7901,
  "timestamp":   "2026-03-19T04:00:00Z",
  "skills": [
    {"id": "summarize", "name": "summarize"},
    {"id": "translate", "name": "translate"}
  ],
  "capabilities": {
    "streaming":          true,
    "push_notifications": true,
    "input_required":     true,
    "part_types":         ["text", "file", "data"],
    "max_msg_bytes":      1048576
  },
  "auth": {
    "schemes": ["none"]
  },
  "endpoints": {
    "send":       "/message:send",
    "stream":     "/stream",
    "tasks":      "/tasks",
    "agent_card": "/.well-known/acp.json"
  }
}
```

The `/.well-known/acp.json` response returns both `self` (this agent) and `peer` (connected remote agent, or `null`).

---

## 5b. Bilateral Task Synchronization

A key design principle in ACP v0.5: **both sides share the same task_id**.

### Flow

```
Peer (initiator)                    JARVIS (executor)
─────────────────                   ─────────────────
POST /message:send                  receives message
  create_task: true          ──►    auto-registers task_id
  → task_id: "task_abc"             (from_peer: true, status: working)
     status: working

                                    processes...

                             ◄──    POST /tasks/task_abc/update
                                      status: completed
                                      artifact: {type: text, content: ...}

task synced to: completed ✅
```

### Rules

1. Initiator sends `create_task: true` → task_id embedded in outgoing message
2. Executor receives message with `task_id` not locally known → **auto-registers** it (`from_peer: true`)
3. Executor calls `/tasks/{id}/update` → state change propagated back via `task.updated` message
4. Initiator's task entry updates automatically; artifacts stored in `task.artifacts[]`

### Why shared task_id?

- **Zero coordination**: both sides use the same ID without a handshake
- **Debuggable**: logs reference the same ID on both ends  
- **Cancellable from either side**: initiator can call `:cancel` at any time

### `from_peer` flag

| Value | Meaning |
|-------|---------|
| absent / `false` | Task created by this agent |
| `true` | Task auto-registered from incoming peer message |


## 6. HTTP Endpoints

### Primary Send — `POST /message:send`

```
POST /message:send
Content-Type: application/json

{
  "parts":      [...],          // Required. Array of Part objects.
  "role":       "user",         // Optional. Default: "user"
  "message_id": "msg_xxx",      // Optional. For idempotency.
  "task_id":    "task_xxx",     // Optional. Associate with task.
  "context_id": "ctx_xxx",      // Optional. Multi-turn context.
  "sync":       false,          // Optional. If true, wait for reply.
  "timeout":    30,             // Optional. Sync reply timeout (seconds).
  "create_task": false          // Optional. Auto-create a task for this message.
}
```

**Response:**
```json
{"ok": true, "message_id": "msg_xxx", "task": null}
```

### Task Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/tasks` | List tasks (optional `?state=working`) |
| POST | `/tasks` | Create task |
| GET | `/tasks/{id}` | Get task |
| POST | `/tasks/{id}/update` | Update task state + artifact |
| POST | `/tasks/{id}/continue` | Resume `input_required` task |
| POST | `/tasks/{id}:cancel` | Cancel active task (sets state=failed) |
| GET | `/tasks/{id}/wait` | Sync-wait for terminal state (`?timeout=N`, default 30s) |
| GET | `/tasks/{id}:subscribe` | SSE stream for single task (closes on terminal) |

---

## 7. Compatibility Notes

### v0.4 → v0.5 Migration

- `/send` endpoint is **preserved** for backward compatibility. Prefer `/message:send`.
- Unstructured messages (without `parts`) are **still accepted** and auto-wrapped in a text Part internally.
- All v0.4 clients work without changes.

---

## 8. Design Decisions

### Why 5 task states (not 8)?

A2A defines 8 states including `canceled`, `rejected`, `auth_required`, `unknown`. For personal/small-team use:
- `canceled` → just disconnect; no state management needed
- `rejected` → use `failed` with an error message
- `auth_required` → handle at connection time, not task time
- `unknown` → an implementation detail, not a protocol state

5 states cover all meaningful lifecycle transitions with zero overhead.

### Why URL-only file parts (no raw bytes)?

Inlining raw bytes in JSON:
1. Bloats the WebSocket frame, hitting `max_msg_bytes` limits
2. Forces base64 encoding (33% size overhead)
3. Makes messages non-human-readable in logs

URL references keep messages lightweight and debuggable. Agents that need to transfer files can use any HTTP file server (including temporary ones).

### Why client-generated `message_id`?

Server-generated IDs require a round-trip before the client knows the ID. Client-generated IDs allow:
- Idempotent retries without coordination
- Pre-correlating messages with local task state
- Zero round-trip overhead

---

*ACP v0.5 · https://github.com/Kickflip73/agent-communication-protocol*

