# ACP Core Specification — v0.1 (Draft)

**Status:** Draft  
**Authors:** ACP Community  
**Date:** 2026-03-18  
**License:** Apache 2.0

---

## 1. Introduction

The **Agent Communication Protocol (ACP)** defines a standard message format and interaction model for communication between autonomous AI agents in Multi-Agent Systems (MAS).

### 1.1 Scope

ACP covers:
- **Agent-to-Agent (A2A)** messaging
- **Task delegation and result reporting**
- **Event broadcasting**
- **Capability advertisement and discovery**
- **Error handling and escalation**

ACP does **not** cover:
- Agent-to-tool calls (see MCP)
- Internal agent reasoning
- LLM inference protocols
- Human-to-agent UX interfaces

### 1.2 Relationship to Existing Protocols

| Protocol | Layer | Relationship to ACP |
|----------|-------|---------------------|
| HTTP/WebSocket | Transport | ACP runs on top |
| MCP (Anthropic) | Tool integration | Complementary — MCP connects agents to tools; ACP connects agents to agents |
| FIPA-ACL (1990s) | Agent communication | ACP is the modern successor; JSON-native, async-first |
| Google A2A | Agent communication | Parallel effort; ACP is vendor-neutral |
| AMQP/MQTT | Message transport | ACP can use these as transport |

---

## 2. Core Concepts

### 2.1 Agent Identity

Every agent participating in ACP has a globally unique **Agent Identifier (AID)**:

```
did:acp:<namespace>:<agent-name>
```

Examples:
```
did:acp:local:summarizer-agent
did:acp:mycompany:customer-support-v2
did:acp:global:7f3a9b2c-1234-5678-abcd-ef0123456789
```

- **`local`** — single-machine, no verification required (development)
- **`<org>`** — organization-scoped, verified by org's registry
- **`global`** — public, globally unique, optionally DID-document backed

### 2.2 Message Envelope

Every ACP message MUST include a **standard envelope**:

```json
{
  "acp": "0.1",
  "id": "<message-id>",
  "type": "<message-type>",
  "from": "<sender-aid>",
  "to": "<recipient-aid> | <broadcast-topic>",
  "ts": "<ISO 8601 timestamp>",
  "correlation_id": "<optional: links messages in a conversation>",
  "reply_to": "<optional: id of message this replies to>",
  "ttl": "<optional: seconds until message expires>",
  "trace": {
    "trace_id": "<distributed tracing ID>",
    "span_id": "<span ID>",
    "parent_span_id": "<optional>"
  },
  "body": { ... }
}
```

**Field definitions:**

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `acp` | ✅ | string | Protocol version, e.g. `"0.1"` |
| `id` | ✅ | string | Unique message ID (UUID or `msg_<random>`) |
| `type` | ✅ | string | Message type (see §3) |
| `from` | ✅ | string | Sender's AID |
| `to` | ✅ | string | Recipient AID or broadcast topic |
| `ts` | ✅ | string | ISO 8601 UTC timestamp |
| `correlation_id` | ☑️ | string | Groups related messages (session/workflow) |
| `reply_to` | ☑️ | string | ID of the message being replied to |
| `ttl` | ☑️ | integer | Seconds before message is considered stale |
| `trace` | ☑️ | object | Distributed tracing (OpenTelemetry-compatible) |
| `body` | ✅ | object | Message-type-specific payload |

### 2.3 Transport Binding

ACP is transport-agnostic. The same envelope is used regardless of transport.

**Recommended transports:**

| Transport | Use Case |
|-----------|----------|
| HTTP POST | Request/response, simple deployments |
| WebSocket | Low-latency, streaming, long sessions |
| MQTT | IoT-style agent swarms, pub/sub |
| AMQP/Kafka | High-throughput pipelines, event-driven |
| In-process | Single-process multi-agent (testing, embedded) |

Transport-specific bindings are defined in [transports.md](transports.md).

---

## 3. Message Types

### 3.1 Task Messages

#### `task.delegate`
Sender asks recipient to perform a task.

```json
{
  "type": "task.delegate",
  "body": {
    "task": "<human-readable task description>",
    "input": { ... },
    "constraints": {
      "deadline": "<ISO 8601>",
      "max_tokens": 1000,
      "priority": "high | normal | low",
      "budget": { "usd": 0.05 }
    },
    "context": [ ... ],
    "callback": "<optional AID to notify on completion>"
  }
}
```

#### `task.accept`
Recipient acknowledges it will perform the task.

```json
{
  "type": "task.accept",
  "body": {
    "estimated_completion": "<ISO 8601>",
    "task_handle": "<opaque ID for status queries>"
  }
}
```

#### `task.reject`
Recipient declines the task.

```json
{
  "type": "task.reject",
  "body": {
    "reason": "overloaded | unauthorized | capability_mismatch | deadline_infeasible",
    "message": "<human-readable explanation>"
  }
}
```

#### `task.result`
Recipient reports task completion.

```json
{
  "type": "task.result",
  "body": {
    "status": "success | partial | failed",
    "output": { ... },
    "artifacts": [
      { "type": "file | url | inline", "name": "report.pdf", "content": "..." }
    ],
    "usage": {
      "tokens_in": 234,
      "tokens_out": 512,
      "duration_ms": 1243
    },
    "error": { "code": "...", "message": "..." }
  }
}
```

#### `task.progress`
Recipient sends incremental progress for long-running tasks.

```json
{
  "type": "task.progress",
  "body": {
    "percent": 60,
    "message": "Processing page 3 of 5...",
    "partial_output": { ... }
  }
}
```

#### `task.cancel`
Sender cancels a previously delegated task.

```json
{
  "type": "task.cancel",
  "body": {
    "reason": "<optional>"
  }
}
```

### 3.2 Event Messages

#### `event.broadcast`
Agent broadcasts an event to a topic (pub/sub).

```json
{
  "type": "event.broadcast",
  "to": "topic:market-data-updates",
  "body": {
    "event_name": "price.updated",
    "payload": { "symbol": "AAPL", "price": 182.5 }
  }
}
```

#### `event.subscribe` / `event.unsubscribe`
Agent subscribes to a topic.

```json
{
  "type": "event.subscribe",
  "to": "did:acp:local:event-bus",
  "body": {
    "topic": "topic:market-data-updates",
    "filter": { "event_name": "price.updated" }
  }
}
```

### 3.3 Coordination Messages

#### `coord.propose`
Multi-agent coordination: propose an action (for consensus/voting scenarios).

```json
{
  "type": "coord.propose",
  "body": {
    "proposal_id": "prop_abc123",
    "action": { ... },
    "voting_deadline": "<ISO 8601>",
    "required_votes": 3
  }
}
```

#### `coord.vote`

```json
{
  "type": "coord.vote",
  "body": {
    "proposal_id": "prop_abc123",
    "vote": "approve | reject | abstain",
    "reason": "<optional>"
  }
}
```

### 3.4 Lifecycle Messages

#### `agent.hello`
Agent announces its presence and capabilities.

```json
{
  "type": "agent.hello",
  "to": "did:acp:local:registry",
  "body": {
    "name": "Summarizer Agent",
    "version": "1.0.0",
    "capabilities": ["summarize", "translate", "classify"],
    "input_schema": { ... },
    "output_schema": { ... },
    "max_concurrent_tasks": 5,
    "metadata": { "model": "gpt-4o", "owner": "team-nlp" }
  }
}
```

#### `agent.bye`
Agent announces graceful shutdown.

#### `agent.heartbeat`
Periodic liveness signal.

### 3.5 Human-in-the-Loop Messages

#### `hitl.escalate`
Agent escalates to a human for approval or input.

```json
{
  "type": "hitl.escalate",
  "to": "did:acp:human:alice",
  "body": {
    "reason": "approval_required | ambiguity | ethical_concern | budget_exceeded",
    "context": { ... },
    "options": [
      { "id": "approve", "label": "Approve and proceed" },
      { "id": "reject", "label": "Cancel task" },
      { "id": "modify", "label": "Modify parameters" }
    ],
    "deadline": "<ISO 8601>",
    "default_on_timeout": "reject"
  }
}
```

#### `hitl.response`
Human responds to escalation.

```json
{
  "type": "hitl.response",
  "body": {
    "choice": "approve",
    "modifications": { ... }
  }
}
```

---

## 4. Error Handling

### 4.1 Error Message

```json
{
  "type": "error",
  "body": {
    "code": "<error-code>",
    "message": "<human-readable message>",
    "details": { ... },
    "retry_after": "<ISO 8601 | null>"
  }
}
```

### 4.2 Standard Error Codes

| Code | Meaning |
|------|---------|
| `acp.unknown_agent` | Recipient AID not found |
| `acp.unauthorized` | Sender not allowed to contact recipient |
| `acp.invalid_message` | Malformed envelope or body |
| `acp.unsupported_type` | Message type not supported |
| `acp.task_not_found` | Referenced task_handle unknown |
| `acp.overloaded` | Agent at capacity, retry later |
| `acp.deadline_exceeded` | Task deadline has passed |
| `acp.capability_missing` | Required capability not available |

---

## 5. Capability Discovery

Agents SHOULD advertise capabilities via `agent.hello`. Orchestrators MAY query a registry:

```
GET /acp/v1/agents?capability=summarize&language=zh
```

Response:
```json
{
  "agents": [
    {
      "aid": "did:acp:local:summarizer-v2",
      "capabilities": ["summarize", "translate"],
      "status": "available",
      "load": 0.3
    }
  ]
}
```

Full discovery spec: [discovery.md](discovery.md)

---

## 6. Security Considerations (v0.1 Baseline)

v0.1 defines baseline security requirements. Full security spec in [identity.md](identity.md).

- Messages SHOULD be transmitted over TLS
- Agents SHOULD verify `from` field against the connection credential
- `did:acp:local` agents are trusted within the same process/machine
- Production deployments MUST use signed messages (v0.4+)

---

## 7. Versioning

- The `acp` field indicates the spec version
- Agents MUST reject messages with a major version they do not support
- Agents SHOULD ignore unknown fields (forward compatibility)
- Breaking changes increment the major version

---

## 8. Conformance

A conformant ACP implementation MUST:
1. Produce valid message envelopes (§2.2) for all outgoing messages
2. Accept and process all Core message types (§3)
3. Respond to unrecognized message types with `acp.unsupported_type`
4. Implement at least one transport binding (§2.3)

---

## Appendix A: Full Message Examples

### A.1 Orchestrator delegating to two parallel workers

```json
// Orchestrator → Worker-1
{
  "acp": "0.1",
  "id": "msg_001",
  "type": "task.delegate",
  "from": "did:acp:local:orchestrator",
  "to": "did:acp:local:worker-search",
  "ts": "2026-03-18T10:00:00Z",
  "correlation_id": "workflow_xyz",
  "body": {
    "task": "Search for recent AI papers on memory mechanisms",
    "input": { "query": "AI agent memory 2025", "max_results": 10 },
    "constraints": { "deadline": "2026-03-18T10:02:00Z" }
  }
}

// Orchestrator → Worker-2 (parallel)
{
  "acp": "0.1",
  "id": "msg_002",
  "type": "task.delegate",
  "from": "did:acp:local:orchestrator",
  "to": "did:acp:local:worker-summarizer",
  "ts": "2026-03-18T10:00:00Z",
  "correlation_id": "workflow_xyz",
  "body": {
    "task": "Prepare summary template",
    "input": { "format": "academic", "max_length": 500 }
  }
}
```

### A.2 Long-running task with progress

```json
// Progress update
{ "acp":"0.1","id":"msg_010","type":"task.progress",
  "from":"did:acp:local:analyzer","to":"did:acp:local:orchestrator",
  "ts":"2026-03-18T10:01:15Z","reply_to":"msg_001","correlation_id":"workflow_xyz",
  "body":{"percent":45,"message":"Analyzed 45 of 100 documents"} }

// Final result
{ "acp":"0.1","id":"msg_020","type":"task.result",
  "from":"did:acp:local:analyzer","to":"did:acp:local:orchestrator",
  "ts":"2026-03-18T10:03:42Z","reply_to":"msg_001","correlation_id":"workflow_xyz",
  "body":{"status":"success","output":{"findings":[...]},"usage":{"duration_ms":222000}} }
```
