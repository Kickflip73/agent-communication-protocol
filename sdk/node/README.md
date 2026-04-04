# acp-relay-client (Node.js)

Node.js client for the [Agent Communication Protocol (ACP)](../../README.md) P2P relay.

**Version:** 2.47.0 | **Zero external dependencies** | **Node.js ≥ 18** | **ESM + CJS**

## Installation

```bash
# From npm (once published)
npm install acp-relay-client

# From GitHub (latest dev)
npm install github:Kickflip73/agent-communication-protocol#main --prefix . \
  && cp -r node_modules/acp-relay-client .

# Or copy the sdk/node/ directory directly
cp -r sdk/node/ my-project/acp-relay-client/
```

## Quick Start

```js
// CommonJS
const { RelayClient } = require('acp-relay-client');

// ESM
import { RelayClient } from 'acp-relay-client';

const client = new RelayClient('http://localhost:7901');

// Send a message
const resp = await client.send('Hello from Node.js!');
console.log(resp); // { ok: true, message_id: 'msg_...' }

// Poll received messages
const msgs = await client.recv();
msgs.forEach(m => console.log(m.parts[0].content));

// List connected peers
const peers = await client.peers();

// Discover LAN peers (mDNS, v0.7+)
const lanPeers = await client.discover();

// SSE stream
for await (const event of client.stream({ timeout: 30000 })) {
  console.log(event.type, JSON.parse(event.data));
}

// v2.47 — Trust signals
const signals = await client.trustSignals();
// [ { type: 'jwks', provider: 'self', uri: '/.well-known/jwks.json' },
//   { type: 'ed25519_identity', provider: 'self', did: 'did:acp:...' } ]

// v2.46 — Capability groups (structured)
const groups = await client.capabilityGroups();
if (groups.identity?.ed25519) {
  console.log('Peer supports Ed25519 identity');
}

// v2.47 — RFC 8615 well-known headers
const headers = await client.wellKnownHeaders();
console.log(headers['cache-control']); // "max-age=300, stale-while-revalidate=60"
```

## API Reference

### `new RelayClient(baseUrl, [options])`

| Option | Default | Description |
|--------|---------|-------------|
| `timeout` | `10000` | Request timeout (ms) |

### Methods

| Method | Since | Description |
|--------|-------|-------------|
| `status()` | v0.5 | Get relay status + AgentCard |
| `agentCard()` | v0.5 | Fetch `/.well-known/acp.json` |
| `send(text, [extra])` | v0.5 | Send text message to connected peer |
| `sendParts(parts, [extra])` | v0.6 | Send message with custom parts |
| `sendToPeer(peerId, text, [extra])` | v0.6 | Send to specific peer (multi-session) |
| `recv([options])` | v0.5 | Poll pending received messages |
| `peers()` | v0.6 | List connected peers |
| `peer(peerId)` | v0.6 | Get single peer info |
| `discover()` | v0.7 | List LAN-discovered peers (mDNS) |
| `stream([options])` | v0.6 | SSE event stream (async generator) |
| `link()` | v0.6 | Get this relay's shareable `acp://` link |
| `capabilities()` | v1.6 | Flat capabilities map from AgentCard |
| `identity()` | v1.3 | Identity block (`did`, `public_key_b64`, `scheme`) |
| `didDocument()` | v1.3 | Fetch `/.well-known/did.json` (W3C DID Document) |
| `supportedInterfaces()` | v2.5 | Declared interface groups (e.g. `["core","task","identity"]`) |
| `sseSeqEnabled()` | v2.5 | True if relay emits monotonic `seq` on SSE events |
| `tasks([options])` | v1.4 | List tasks with optional filters + pagination |
| `createTask(task)` | v1.4 | Create a new task |
| `updateTask(id, update)` | v1.4 | Update task state |
| `cancelTask(id, [options])` | v1.4 | Cancel a task (idempotent) |
| `querySkills([filter])` | v2.4 | Query peer capabilities / skills |
| `waitForPeer([options])` | v0.6 | Poll until a peer connects |
| `sendAndRecv(text, [options])` | v0.6 | Send + await first reply |
| `reply(messageId, text)` | v0.6 | Reply to a specific message |
| **`trustSignals()`** | **v2.47** | **Trust signals from AgentCard (`trust.signals[]`)** |
| **`capabilityGroups()`** | **v2.46** | **Structured capability groups (messaging/tasks/identity/transport/discovery)** |
| **`wellKnownHeaders()`** | **v2.47** | **RFC 8615 response headers (Cache-Control, Vary, X-Content-Type-Options)** |

## TypeScript

TypeScript definitions are included at `src/index.d.ts`.

```ts
import type { RelayClient, AcpMessage, AcpPeer } from 'acp-relay-client';
```

## Testing

```bash
node --test tests/relay_client.test.js
# 66 tests, 0 failures
```

## Links

- [Protocol spec](../../spec/core-v1.0.md) (Stable, v2.47)
- [Identity spec](../../spec/identity-v2.0.md) (Stable)
- [Compatibility Matrix](../../docs/compatibility-matrix.md)
- [Python SDK](../python/README-sdk.md)
- [Integration guide](../../docs/integration-guide.md)
- [CLI reference](../../docs/cli-reference.md)
- [CHANGELOG](../../CHANGELOG.md)
