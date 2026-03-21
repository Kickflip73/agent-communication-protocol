# acp-relay-client (Node.js)

Node.js client for the [Agent Communication Protocol (ACP)](../../README.md) P2P relay.

**Version:** 0.9.0-dev | **Zero external dependencies** | **Node.js ≥ 18** | **ESM + CJS**

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
```

## API Reference

### `new RelayClient(baseUrl, [options])`

| Option | Default | Description |
|--------|---------|-------------|
| `timeout` | `10000` | Request timeout (ms) |

### Methods

| Method | Description |
|--------|-------------|
| `status()` | Get relay status + AgentCard |
| `agentCard()` | Fetch `/.well-known/acp.json` |
| `send(text, [extra])` | Send text message to connected peer |
| `sendParts(parts, [extra])` | Send message with custom parts |
| `sendToPeer(peerId, text, [extra])` | Send to specific peer (multi-session) |
| `recv([options])` | Poll pending received messages |
| `peers()` | List connected peers |
| `peer(peerId)` | Get single peer info |
| `discover()` | List LAN-discovered peers (mDNS) |
| `stream([options])` | SSE event stream (async generator) |
| `tasks()` | List all tasks |
| `createTask(task)` | Create a new task |
| `updateTask(id, update)` | Update task state |
| `cancelTask(id)` | Cancel a task |
| `querySkills([filter])` | Query peer capabilities |
| `waitForPeer([options])` | Wait until a peer connects |
| `sendAndRecv(text, [options])` | Send + wait for first reply |
| `reply(messageId, text)` | Reply to a specific message |

## TypeScript

TypeScript definitions are included at `src/index.d.ts`.

```ts
import type { RelayClient, AcpMessage, AcpPeer } from 'acp-relay-client';
```

## Testing

```bash
node --test tests/relay_client.test.js
# 19 tests, 0 failures
```

## Links

- [Protocol spec](../../spec/core-v0.8.md)
- [Integration guide](../../docs/integration-guide.md)
- [CLI reference](../../docs/cli-reference.md)
- [CHANGELOG](../../CHANGELOG.md)
