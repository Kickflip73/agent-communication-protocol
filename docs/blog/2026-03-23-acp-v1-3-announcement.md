# ACP v1.3: Extensions, DID Identity, and a Complete SDK Matrix

*Published: 2026-03-23 · [GitHub](https://github.com/Kickflip73/agent-communication-protocol)*

---

We've been quietly building **ACP (Agent Communication Protocol)** for the past few weeks —
a zero-server, P2P protocol that lets two AI agents talk directly to each other.
No infrastructure. No code changes. Two steps for humans, everything else automatic.

Today we're tagging **v1.3** and sharing what's in it.

---

## What is ACP?

The problem: if you have two AI agents — say, one on OpenAI's API and one running locally on LM Studio — there's no standard way for them to exchange messages. You either route everything through a central server, or you build bespoke integrations.

ACP's answer: **the human acts as the messenger, once**.

```
Step 1: Send the ACP Skill URL to Agent A
Step 2: Send the acp:// link Agent A returns to Agent B
Done — the agents connect directly and communicate forever
```

The relay is a single Python file. No database. No config. No cloud account.
`websockets` is the only dependency for the P2P path. `cryptography` is optional, for identity.

---

## What's new in v1.3

### Extension mechanism

Agents can now declare arbitrary capability extensions via URI:

```json
{
  "name": "my-agent",
  "acp_version": "1.3",
  "extensions": [
    {
      "uri": "https://example.com/ext/code-execution/v1",
      "required": false,
      "params": { "languages": ["python", "bash"] }
    }
  ]
}
```

Extensions are opt-in and zero-config when unused. Register or remove them at runtime:

```bash
curl -X POST http://localhost:8100/extensions/register \
  -d '{"uri": "https://example.com/ext/my-cap/v1", "required": false}'
```

This aligns with A2A's extension model while staying lightweight.

### `did:acp:` — self-sovereign agent identity

An agent can now have a stable, cryptographic identity without any external registry:

```
did:acp:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK
```

The DID is derived directly from the Ed25519 public key. Start with `--identity` and
your DID stays the same across restarts, as long as you keep the keypair:

```bash
docker run --rm -p 8000:8000 -p 8100:8100 \
  -v acp-identity:/root/.acp \
  ghcr.io/kickflip73/agent-communication-protocol/acp-relay:full \
  --name MyAgent --identity
```

A W3C-compatible DID Document is served at `/.well-known/did.json`.

### Complete SDK matrix

ACP now has reference SDKs in four languages:

| Language | Location | Dependencies |
|----------|----------|-------------|
| Python | `sdk/python/` | stdlib only |
| Node.js | `sdk/node/` | zero npm deps |
| Go | `sdk/go/` | stdlib only |
| Rust | `sdk/rust/` | `tokio`, `reqwest` |

All SDKs cover: send message, get AgentCard, live-update (`PATCH`), task status, error handling.

### Official Docker image + GHCR CI

```bash
docker pull ghcr.io/kickflip73/agent-communication-protocol/acp-relay:latest
docker pull ghcr.io/kickflip73/agent-communication-protocol/acp-relay:full
```

Images are published automatically to GHCR on every push to `main` and every semver tag.
Multi-arch: `linux/amd64` + `linux/arm64`.

### Conformance guide

We added [`docs/conformance.md`](../conformance.md) — a guide for third-party implementors.
It defines three levels: **Core** (MUST), **Recommended** (SHOULD), **Full** (MAY).
Run the compat suite and self-certify with a badge:

```bash
python3 tests/compat/run.py --url http://your-agent:8100 --json > conformance.json
```

---

## How does ACP compare to A2A and MCP?

| | MCP | A2A (Google) | **ACP** |
|---|---|---|---|
| Purpose | Agent ↔ Tool | Agent ↔ Agent (enterprise) | Agent ↔ Agent (personal/team) |
| Server required | No | Yes | **No** |
| Code changes | Yes | Yes | **No** |
| Auth | None | OAuth 2.0 (mandatory) | HMAC or Ed25519 (optional) |
| Setup time | Minutes | Hours | **Seconds** |
| Analogy | USB cable | Enterprise ESB | WhatsApp |

We think of it this way: **MCP standardized Agent↔Tool. ACP standardizes Agent↔Agent.**
P2P, lightweight, open, works with any framework.

A2A is an excellent standard for enterprise-scale orchestration. ACP is for the person
who just wants two agents to talk.

---

## What's next

The v1.1 backlog is fully closed. v2.0 targets: public launch and broader ecosystem integration.

The only remaining open item is **HTTP/2 transport binding** — optional, long-term.

---

## Try it

```bash
# Start two agents and connect them
python3 relay/acp_relay.py --name Alice --port 8000 &
python3 relay/acp_relay.py --name Bob --port 8001 --join acp://localhost:8000

# Or with Docker
docker-compose up
```

GitHub: [Kickflip73/agent-communication-protocol](https://github.com/Kickflip73/agent-communication-protocol)

Feedback welcome — open an issue or start a discussion.

---

*ACP is Apache 2.0 licensed.*
