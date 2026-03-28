/**
 * Tests for RelayClient — uses Node.js built-in test runner + mock HTTP server.
 * Run: node --test tests/relay_client.test.js
 *
 * No external dependencies required.
 */

'use strict';

const { test, describe, before, after } = require('node:test');
const assert = require('node:assert');
const http = require('node:http');
const { RelayClient, Extension } = require('../src/index');

// ─────────────────────────────────────────────
// Mock HTTP server
// ─────────────────────────────────────────────

let mockServer;
let mockPort;
let mockHandlers = {};

function setHandler(method, path, fn) {
  mockHandlers[`${method}:${path}`] = fn;
}

function jsonResponse(res, statusCode, body) {
  const payload = JSON.stringify(body);
  res.writeHead(statusCode, { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) });
  res.end(payload);
}

before(async () => {
  await new Promise((resolve) => {
    mockServer = http.createServer((req, res) => {
      let body = '';
      req.on('data', chunk => { body += chunk; });
      req.on('end', () => {
        const key = `${req.method}:${req.url.split('?')[0]}`;
        const handler = mockHandlers[key];
        if (handler) {
          handler(req, res, body ? JSON.parse(body) : undefined);
        } else {
          jsonResponse(res, 404, { error: `No handler for ${key}` });
        }
      });
    });
    mockServer.listen(0, '127.0.0.1', () => {
      mockPort = mockServer.address().port;
      resolve();
    });
  });
});

after(async () => {
  await new Promise(resolve => mockServer.close(resolve));
});

function makeClient() {
  return new RelayClient(`http://127.0.0.1:${mockPort}`, { timeout: 3000 });
}

// ─────────────────────────────────────────────
// Tests
// ─────────────────────────────────────────────

describe('RelayClient constructor', () => {
  test('stores baseUrl without trailing slash', () => {
    const c = new RelayClient('http://localhost:7901/');
    assert.strictEqual(c.baseUrl, 'http://localhost:7901');
  });

  test('default timeout is 10000', () => {
    const c = new RelayClient('http://localhost:7901');
    assert.strictEqual(c.timeout, 10000);
  });

  test('custom timeout is respected', () => {
    const c = new RelayClient('http://localhost:7901', { timeout: 5000 });
    assert.strictEqual(c.timeout, 5000);
  });
});

describe('status()', () => {
  test('returns status object', async () => {
    setHandler('GET', '/status', (req, res) => {
      jsonResponse(res, 200, { version: '0.7-dev', peer_count: 1, session_id: 'sess_abc' });
    });
    const c = makeClient();
    const s = await c.status();
    assert.strictEqual(s.version, '0.7-dev');
    assert.strictEqual(s.peer_count, 1);
    assert.strictEqual(s.session_id, 'sess_abc');
  });
});

describe('agentCard()', () => {
  test('fetches /.well-known/acp.json', async () => {
    setHandler('GET', '/.well-known/acp.json', (req, res) => {
      jsonResponse(res, 200, { name: 'TestAgent', version: '0.7', capabilities: { hmac_signing: true } });
    });
    const c = makeClient();
    const card = await c.agentCard();
    assert.strictEqual(card.name, 'TestAgent');
    assert.strictEqual(card.capabilities.hmac_signing, true);
  });
});

describe('send()', () => {
  test('sends text message and returns ok + message_id', async () => {
    let received;
    setHandler('POST', '/message:send', (req, res, body) => {
      received = body;
      jsonResponse(res, 200, { ok: true, message_id: 'msg_test001' });
    });
    const c = makeClient();
    const resp = await c.send('Hello, ACP!');
    assert.strictEqual(resp.ok, true);
    assert.strictEqual(resp.message_id, 'msg_test001');
    assert.strictEqual(received.parts[0].content, 'Hello, ACP!');
    assert.strictEqual(received.type, 'acp.message');
  });

  test('send() passes extra fields (context_id)', async () => {
    let received;
    setHandler('POST', '/message:send', (req, res, body) => {
      received = body;
      jsonResponse(res, 200, { ok: true, message_id: 'msg_ctx001' });
    });
    const c = makeClient();
    await c.send('Test', { context_id: 'ctx_xyz' });
    assert.strictEqual(received.context_id, 'ctx_xyz');
  });
});

describe('sendParts()', () => {
  test('sends custom parts array', async () => {
    let received;
    setHandler('POST', '/message:send', (req, res, body) => {
      received = body;
      jsonResponse(res, 200, { ok: true, message_id: 'msg_parts001' });
    });
    const c = makeClient();
    await c.sendParts([{ type: 'text', content: 'Part A' }, { type: 'data', data: { x: 1 } }]);
    assert.strictEqual(received.parts.length, 2);
    assert.strictEqual(received.parts[0].content, 'Part A');
    assert.deepStrictEqual(received.parts[1].data, { x: 1 });
  });
});

describe('sendToPeer()', () => {
  test('sends to specific peer endpoint', async () => {
    let receivedPath;
    setHandler('POST', '/peer/peer_abc/send', (req, res, body) => {
      receivedPath = req.url;
      jsonResponse(res, 200, { ok: true, message_id: 'msg_peer001' });
    });
    const c = makeClient();
    const resp = await c.sendToPeer('peer_abc', 'Hi peer!');
    assert.strictEqual(resp.ok, true);
    assert.ok(receivedPath.includes('peer_abc'));
  });
});

describe('recv()', () => {
  test('returns messages array', async () => {
    setHandler('GET', '/recv', (req, res) => {
      jsonResponse(res, 200, { messages: [
        { message_id: 'msg_001', parts: [{ type: 'text', content: 'Hello back' }] }
      ]});
    });
    const c = makeClient();
    const msgs = await c.recv();
    assert.strictEqual(msgs.length, 1);
    assert.strictEqual(msgs[0].message_id, 'msg_001');
  });

  test('returns empty array when no messages', async () => {
    setHandler('GET', '/recv', (req, res) => {
      jsonResponse(res, 200, { messages: [] });
    });
    const c = makeClient();
    const msgs = await c.recv();
    assert.strictEqual(msgs.length, 0);
  });
});

describe('peers()', () => {
  test('returns peers array', async () => {
    setHandler('GET', '/peers', (req, res) => {
      jsonResponse(res, 200, { peers: [
        { peer_id: 'peer_001', name: 'Agent-B' },
        { peer_id: 'peer_002', name: 'Agent-C' },
      ]});
    });
    const c = makeClient();
    const peers = await c.peers();
    assert.strictEqual(peers.length, 2);
    assert.strictEqual(peers[0].name, 'Agent-B');
  });
});

describe('discover()', () => {
  test('returns LAN-discovered peers', async () => {
    setHandler('GET', '/discover', (req, res) => {
      jsonResponse(res, 200, { peers: [
        { peer_id: 'lan_001', name: 'LocalAgent', link: 'acp://192.168.1.5:7801/tok_abc' }
      ]});
    });
    const c = makeClient();
    const peers = await c.discover();
    assert.strictEqual(peers.length, 1);
    assert.ok(peers[0].link.startsWith('acp://'));
  });
});

describe('tasks()', () => {
  test('returns tasks array', async () => {
    setHandler('GET', '/tasks', (req, res) => {
      jsonResponse(res, 200, { tasks: [
        { task_id: 'task_001', state: 'working', description: 'Analyze data' }
      ]});
    });
    const c = makeClient();
    const tasks = await c.tasks();
    assert.strictEqual(tasks.length, 1);
    assert.strictEqual(tasks[0].state, 'working');
  });
});

describe('createTask()', () => {
  test('creates task and returns task object', async () => {
    setHandler('POST', '/tasks/create', (req, res, body) => {
      jsonResponse(res, 200, { task_id: 'task_new001', state: 'submitted', ...body });
    });
    const c = makeClient();
    const task = await c.createTask({ description: 'New task', type: 'analysis' });
    assert.strictEqual(task.task_id, 'task_new001');
    assert.strictEqual(task.state, 'submitted');
    assert.strictEqual(task.description, 'New task');
  });
});

describe('updateTask()', () => {
  test('updates task state', async () => {
    setHandler('POST', '/tasks/task_001:update', (req, res, body) => {
      jsonResponse(res, 200, { task_id: 'task_001', ...body });
    });
    const c = makeClient();
    const updated = await c.updateTask('task_001', { state: 'completed', result: { summary: 'Done' } });
    assert.strictEqual(updated.state, 'completed');
  });
});

describe('cancelTask()', () => {
  test('calls POST /tasks/{id}:cancel (not :update)', async () => {
    let calledPath;
    setHandler('POST', '/tasks/task_002:cancel', (req, res, body) => {
      calledPath = req.url;
      jsonResponse(res, 200, { task_id: 'task_002', state: 'canceled' });
    });
    const c = makeClient();
    const result = await c.cancelTask('task_002');
    assert.ok(calledPath, ':cancel endpoint should have been called');
    assert.strictEqual(result.state, 'canceled');
  });

  test('returns canceled state on success', async () => {
    setHandler('POST', '/tasks/task_003:cancel', (req, res) => {
      jsonResponse(res, 200, { task_id: 'task_003', state: 'canceled' });
    });
    const c = makeClient();
    const result = await c.cancelTask('task_003');
    assert.strictEqual(result.state, 'canceled');
    assert.strictEqual(result.task_id, 'task_003');
  });

  test('returns error body on 409 ERR_TASK_NOT_CANCELABLE', async () => {
    setHandler('POST', '/tasks/task_done:cancel', (req, res) => {
      const payload = JSON.stringify({ error: 'ERR_TASK_NOT_CANCELABLE', task_id: 'task_done' });
      res.writeHead(409, { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) });
      res.end(payload);
    });
    const c = makeClient();
    const result = await c.cancelTask('task_done');
    assert.strictEqual(result.error, 'ERR_TASK_NOT_CANCELABLE');
  });

  test('throws on 409 when raiseOnTerminal=true', async () => {
    setHandler('POST', '/tasks/task_done2:cancel', (req, res) => {
      const payload = JSON.stringify({ error: 'ERR_TASK_NOT_CANCELABLE', task_id: 'task_done2' });
      res.writeHead(409, { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) });
      res.end(payload);
    });
    const c = makeClient();
    await assert.rejects(
      () => c.cancelTask('task_done2', { raiseOnTerminal: true }),
      /terminal state/
    );
  });
});

describe('querySkills()', () => {
  test('returns skills array', async () => {
    setHandler('GET', '/skills/query', (req, res) => {
      jsonResponse(res, 200, { skills: [
        { name: 'code-review', category: 'development' },
        { name: 'summarize', category: 'text' },
      ]});
    });
    const c = makeClient();
    const skills = await c.querySkills();
    assert.strictEqual(skills.length, 2);
    assert.strictEqual(skills[0].name, 'code-review');
  });
});

describe('reply()', () => {
  test('sends message with reply_to field', async () => {
    let received;
    setHandler('POST', '/message:send', (req, res, body) => {
      received = body;
      jsonResponse(res, 200, { ok: true, message_id: 'msg_reply001' });
    });
    const c = makeClient();
    await c.reply('msg_original', 'Here is my reply');
    assert.strictEqual(received.reply_to, 'msg_original');
    assert.strictEqual(received.parts[0].content, 'Here is my reply');
  });
});

// ─── Extension Tests ───────────────────────────────
describe('Extension class', () => {
  test('constructor defaults', () => {
    const ext = new Extension('acp:ext:hmac-v1');
    assert.strictEqual(ext.uri, 'acp:ext:hmac-v1');
    assert.strictEqual(ext.required, false);
    assert.deepStrictEqual(ext.params, {});
  });

  test('constructor with params', () => {
    const ext = new Extension('acp:ext:hmac-v1', true, { scheme: 'hmac-sha256' });
    assert.strictEqual(ext.required, true);
    assert.deepStrictEqual(ext.params, { scheme: 'hmac-sha256' });
  });

  test('toDict round-trip', () => {
    const ext = new Extension('acp:ext:test-v1', false, { foo: 'bar' });
    const d = ext.toDict();
    assert.deepStrictEqual(d, { uri: 'acp:ext:test-v1', required: false, params: { foo: 'bar' } });
  });

  test('fromDict', () => {
    const ext = Extension.fromDict({ uri: 'acp:ext:mdns-v1', required: true, params: {} });
    assert.strictEqual(ext.uri, 'acp:ext:mdns-v1');
    assert.strictEqual(ext.required, true);
  });

  test('fromDict missing fields', () => {
    const ext = Extension.fromDict({});
    assert.strictEqual(ext.uri, '');
    assert.strictEqual(ext.required, false);
    assert.deepStrictEqual(ext.params, {});
  });

  test('toString', () => {
    const ext = new Extension('acp:ext:hmac-v1', false);
    assert.ok(ext.toString().includes('acp:ext:hmac-v1'));
  });
});

describe('RelayClient.agentCard() extensions parsing', () => {
  test('parses extensions array into Extension instances', async () => {
    setHandler('GET', '/.well-known/acp.json', (req, res) => {
      jsonResponse(res, 200, {
        name: 'TestAgent',
        version: '2.1.0',
        capabilities: {},
        extensions: [
          { uri: 'acp:ext:hmac-v1', required: false, params: { scheme: 'hmac-sha256' } },
          { uri: 'acp:ext:mdns-v1', required: false, params: {} },
        ],
      });
    });
    const client = makeClient();
    const card = await client.agentCard();
    assert.strictEqual(card.extensions.length, 2);
    assert.ok(card.extensions[0] instanceof Extension);
    assert.strictEqual(card.extensions[0].uri, 'acp:ext:hmac-v1');
    assert.strictEqual(card.extensions[1].uri, 'acp:ext:mdns-v1');
  });

  test('handles empty extensions array', async () => {
    setHandler('GET', '/.well-known/acp.json', (req, res) => {
      jsonResponse(res, 200, { name: 'TestAgent', version: '2.1.0', extensions: [] });
    });
    const client = makeClient();
    const card = await client.agentCard();
    assert.deepStrictEqual(card.extensions, []);
  });

  test('handles missing extensions field (backward compat)', async () => {
    setHandler('GET', '/.well-known/acp.json', (req, res) => {
      jsonResponse(res, 200, { name: 'OldAgent', version: '1.0.0' });
    });
    const client = makeClient();
    const card = await client.agentCard();
    assert.deepStrictEqual(card.extensions, []);
  });
});

describe('RelayClient.hasExtension()', () => {
  test('returns true when extension present', async () => {
    setHandler('GET', '/.well-known/acp.json', (req, res) => {
      jsonResponse(res, 200, {
        name: 'Agent', version: '2.1.0',
        extensions: [{ uri: 'acp:ext:hmac-v1', required: false, params: {} }],
      });
    });
    const client = makeClient();
    assert.strictEqual(await client.hasExtension('acp:ext:hmac-v1'), true);
  });

  test('returns false when extension absent', async () => {
    setHandler('GET', '/.well-known/acp.json', (req, res) => {
      jsonResponse(res, 200, { name: 'Agent', version: '2.1.0', extensions: [] });
    });
    const client = makeClient();
    assert.strictEqual(await client.hasExtension('acp:ext:hmac-v1'), false);
  });
});

describe('RelayClient.requiredExtensions()', () => {
  test('returns only required extensions', async () => {
    setHandler('GET', '/.well-known/acp.json', (req, res) => {
      jsonResponse(res, 200, {
        name: 'Agent', version: '2.4.0',
        extensions: [
          { uri: 'acp:ext:hmac-v1', required: true, params: {} },
          { uri: 'acp:ext:mdns-v1', required: false, params: {} },
        ],
      });
    });
    const client = makeClient();
    const req = await client.requiredExtensions();
    assert.strictEqual(req.length, 1);
    assert.strictEqual(req[0].uri, 'acp:ext:hmac-v1');
  });

  test('returns empty array when none required', async () => {
    setHandler('GET', '/.well-known/acp.json', (req, res) => {
      jsonResponse(res, 200, {
        name: 'Agent', version: '2.4.0',
        extensions: [{ uri: 'acp:ext:mdns-v1', required: false, params: {} }],
      });
    });
    const client = makeClient();
    const req = await client.requiredExtensions();
    assert.deepStrictEqual(req, []);
  });
});

// ─── v2.4 New API Tests ────────────────────────────────────

describe('capabilities() — v1.6+', () => {
  test('returns capabilities dict from AgentCard', async () => {
    setHandler('GET', '/.well-known/acp.json', (req, res) => {
      jsonResponse(res, 200, {
        name: 'Agent', version: '2.4.0',
        capabilities: { http2: true, hmac_signing: true, did_identity: false, mdns: true, sse_seq: true },
      });
    });
    const client = makeClient();
    const caps = await client.capabilities();
    assert.strictEqual(caps.http2, true);
    assert.strictEqual(caps.hmac_signing, true);
    assert.strictEqual(caps.did_identity, false);
    assert.strictEqual(caps.sse_seq, true);
  });

  test('returns empty object when capabilities field absent', async () => {
    setHandler('GET', '/.well-known/acp.json', (req, res) => {
      jsonResponse(res, 200, { name: 'OldAgent', version: '1.0.0' });
    });
    const client = makeClient();
    const caps = await client.capabilities();
    assert.deepStrictEqual(caps, {});
  });

  test('returns empty object on network error', async () => {
    // Use a client pointing to a non-existent port to simulate network error
    const badClient = new RelayClient('http://127.0.0.1:1', { timeout: 500 });
    const caps = await badClient.capabilities();
    assert.deepStrictEqual(caps, {});
  });
});

describe('link()', () => {
  test('returns link string', async () => {
    setHandler('GET', '/link', (req, res) => {
      jsonResponse(res, 200, { link: 'acp://127.0.0.1:7801/tok_abc123' });
    });
    const client = makeClient();
    const link = await client.link();
    assert.strictEqual(link, 'acp://127.0.0.1:7801/tok_abc123');
  });

  test('returns empty string when link field absent', async () => {
    setHandler('GET', '/link', (req, res) => {
      jsonResponse(res, 200, {});
    });
    const client = makeClient();
    const link = await client.link();
    assert.strictEqual(link, '');
  });
});

describe('identity() — v1.3+', () => {
  test('returns identity block from AgentCard', async () => {
    setHandler('GET', '/.well-known/acp.json', (req, res) => {
      jsonResponse(res, 200, {
        name: 'Agent', version: '2.4.0',
        identity: { did: 'did:acp:abc123', public_key_b64: 'AAAA...', scheme: 'ed25519' },
      });
    });
    const client = makeClient();
    const ident = await client.identity();
    assert.strictEqual(ident.did, 'did:acp:abc123');
    assert.strictEqual(ident.scheme, 'ed25519');
  });

  test('returns empty object when identity absent', async () => {
    setHandler('GET', '/.well-known/acp.json', (req, res) => {
      jsonResponse(res, 200, { name: 'Agent', version: '2.4.0' });
    });
    const client = makeClient();
    const ident = await client.identity();
    assert.deepStrictEqual(ident, {});
  });
});

describe('didDocument() — v1.3+', () => {
  test('fetches /.well-known/did.json', async () => {
    setHandler('GET', '/.well-known/did.json', (req, res) => {
      jsonResponse(res, 200, {
        '@context': 'https://www.w3.org/ns/did/v1',
        id: 'did:acp:abc123',
        verificationMethod: [],
      });
    });
    const client = makeClient();
    const doc = await client.didDocument();
    assert.strictEqual(doc.id, 'did:acp:abc123');
    assert.ok(Array.isArray(doc.verificationMethod));
  });
});

describe('supportedInterfaces() — v2.5+', () => {
  test('returns supported_interfaces list from AgentCard', async () => {
    setHandler('GET', '/.well-known/acp.json', (req, res) => {
      jsonResponse(res, 200, {
        name: 'Agent', version: '2.5.0',
        supported_interfaces: ['core', 'task', 'stream'],
      });
    });
    const client = makeClient();
    const ifaces = await client.supportedInterfaces();
    assert.deepStrictEqual(ifaces.sort(), ['core', 'stream', 'task']);
  });

  test('returns empty array when field absent (pre-v2.5 relay)', async () => {
    setHandler('GET', '/.well-known/acp.json', (req, res) => {
      jsonResponse(res, 200, { name: 'OldAgent', version: '1.0.0' });
    });
    const client = makeClient();
    const ifaces = await client.supportedInterfaces();
    assert.deepStrictEqual(ifaces, []);
  });

  test('returns empty array on network error', async () => {
    const badClient = new RelayClient('http://127.0.0.1:1', { timeout: 500 });
    const ifaces = await badClient.supportedInterfaces();
    assert.deepStrictEqual(ifaces, []);
  });
});

describe('sseSeqEnabled() — v2.5+', () => {
  test('returns true when sse_seq capability is true', async () => {
    setHandler('GET', '/.well-known/acp.json', (req, res) => {
      jsonResponse(res, 200, {
        name: 'Agent', version: '2.5.0',
        capabilities: { sse_seq: true },
      });
    });
    const client = makeClient();
    assert.strictEqual(await client.sseSeqEnabled(), true);
  });

  test('returns false when sse_seq capability is false', async () => {
    setHandler('GET', '/.well-known/acp.json', (req, res) => {
      jsonResponse(res, 200, {
        name: 'Agent', version: '2.5.0',
        capabilities: { sse_seq: false },
      });
    });
    const client = makeClient();
    assert.strictEqual(await client.sseSeqEnabled(), false);
  });

  test('returns false when capabilities absent', async () => {
    setHandler('GET', '/.well-known/acp.json', (req, res) => {
      jsonResponse(res, 200, { name: 'OldAgent', version: '1.0.0' });
    });
    const client = makeClient();
    assert.strictEqual(await client.sseSeqEnabled(), false);
  });
});

describe('tasks() with filters — v1.4+', () => {
  test('passes status filter as query param', async () => {
    let receivedUrl;
    setHandler('GET', '/tasks', (req, res) => {
      receivedUrl = req.url;
      jsonResponse(res, 200, { tasks: [] });
    });
    const client = makeClient();
    await client.tasks({ status: 'working' });
    assert.ok(receivedUrl.includes('status=working'), `Expected status=working in ${receivedUrl}`);
  });

  test('passes multiple filters as query params', async () => {
    let receivedUrl;
    setHandler('GET', '/tasks', (req, res) => {
      receivedUrl = req.url;
      jsonResponse(res, 200, { tasks: [] });
    });
    const client = makeClient();
    await client.tasks({ status: 'completed', limit: 10, sort: 'desc' });
    assert.ok(receivedUrl.includes('status=completed'), `URL should contain status=completed: ${receivedUrl}`);
    assert.ok(receivedUrl.includes('limit=10'), `URL should contain limit=10: ${receivedUrl}`);
    assert.ok(receivedUrl.includes('sort=desc'), `URL should contain sort=desc: ${receivedUrl}`);
  });

  test('passes cursor for pagination', async () => {
    let receivedUrl;
    setHandler('GET', '/tasks', (req, res) => {
      receivedUrl = req.url;
      jsonResponse(res, 200, { tasks: [], next_cursor: null });
    });
    const client = makeClient();
    await client.tasks({ cursor: 'cursor_xyz_001' });
    assert.ok(receivedUrl.includes('cursor=cursor_xyz_001'), `URL should contain cursor: ${receivedUrl}`);
  });

  test('passes peer_id filter', async () => {
    let receivedUrl;
    setHandler('GET', '/tasks', (req, res) => {
      receivedUrl = req.url;
      jsonResponse(res, 200, { tasks: [] });
    });
    const client = makeClient();
    await client.tasks({ peer_id: 'peer_abc' });
    assert.ok(receivedUrl.includes('peer_id=peer_abc'), `URL should contain peer_id: ${receivedUrl}`);
  });

  test('passes created_after and updated_after timestamps', async () => {
    let receivedUrl;
    setHandler('GET', '/tasks', (req, res) => {
      receivedUrl = req.url;
      jsonResponse(res, 200, { tasks: [] });
    });
    const client = makeClient();
    await client.tasks({ created_after: '2026-01-01T00:00:00Z', updated_after: '2026-01-02T00:00:00Z' });
    assert.ok(receivedUrl.includes('created_after='), `URL should contain created_after: ${receivedUrl}`);
    assert.ok(receivedUrl.includes('updated_after='), `URL should contain updated_after: ${receivedUrl}`);
  });

  test('no query params when called with empty options', async () => {
    let receivedUrl;
    setHandler('GET', '/tasks', (req, res) => {
      receivedUrl = req.url;
      jsonResponse(res, 200, { tasks: [{ task_id: 'task_001', state: 'working' }] });
    });
    const client = makeClient();
    const tasks = await client.tasks({});
    assert.strictEqual(receivedUrl, '/tasks');
    assert.strictEqual(tasks.length, 1);
  });

  test('no query params when called with no arguments (backward compat)', async () => {
    let receivedUrl;
    setHandler('GET', '/tasks', (req, res) => {
      receivedUrl = req.url;
      jsonResponse(res, 200, { tasks: [] });
    });
    const client = makeClient();
    await client.tasks();
    assert.strictEqual(receivedUrl, '/tasks');
  });
});
