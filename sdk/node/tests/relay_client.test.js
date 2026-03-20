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
const { RelayClient } = require('../src/index');

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
  test('sends state=canceled', async () => {
    let received;
    setHandler('POST', '/tasks/task_002:update', (req, res, body) => {
      received = body;
      jsonResponse(res, 200, { task_id: 'task_002', state: 'canceled' });
    });
    const c = makeClient();
    await c.cancelTask('task_002');
    assert.strictEqual(received.state, 'canceled');
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
