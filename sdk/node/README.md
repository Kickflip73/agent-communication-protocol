# acp-sdk (Node.js)

Node.js SDK for the [Agent Communication Protocol (ACP)](../../README.md) relay client.

**Version:** 0.8.0 | **Zero external dependencies** | **Node.js ≥ 18**

## Installation

```bash
# Copy to your project (no npm registry yet)
cp -r sdk/node/ my-project/acp-sdk/
```

## Quick Start

```js
const { RelayClient } = require('./acp-sdk/src');

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

## Testing

```bash
node --test tests/relay_client.test.js
# 19 tests, 0 failures
```

## TypeScript

TypeScript definitions are included at `src/index.d.ts`.

```ts
import { RelayClient, AcpMessage, AcpPeer } from './acp-sdk/src';
```
