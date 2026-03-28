/**
 * RelayClient — Node.js HTTP client for a running acp_relay.py instance.
 *
 * @version 2.4.0
 *
 * Zero external dependencies. Uses only Node.js built-in `http`/`https` modules.
 * Requires Node.js >= 18 (fetch API available built-in, or use http module).
 *
 * API surface mirrors the Python SDK (sdk/python/acp_sdk/relay_client.py):
 *   POST /message:send      — send a message to the connected peer
 *   POST /peer/{id}/send    — send to a specific peer (multi-session)
 *   GET  /recv              — poll pending received messages
 *   GET  /stream            — SSE event stream (AsyncGenerator)
 *   GET  /peers             — list connected peers
 *   GET  /peer/{id}         — get a single peer's info
 *   GET  /status            — relay status + AgentCard
 *   GET  /tasks             — list tasks
 *   POST /tasks/create      — create/delegate a task
 *   POST /tasks/{id}:update — update task state
 *   GET  /skills/query      — query peer capabilities (QuerySkill)
 *   GET  /discover          — list LAN-discovered peers (mDNS, v0.7)
 *
 * Usage:
 *   const { RelayClient } = require('acp-sdk');
 *   // or: import { RelayClient } from 'acp-sdk';
 *
 *   const client = new RelayClient('http://localhost:7901');
 *
 *   // Send a message
 *   const resp = await client.send('Hello from Node.js SDK!');
 *   console.log(resp); // { ok: true, message_id: 'msg_...' }
 *
 *   // Poll received messages
 *   const msgs = await client.recv();
 *   msgs.forEach(m => console.log(m.parts));
 *
 *   // List peers
 *   const peers = await client.peers();
 *
 *   // SSE stream (async generator)
 *   for await (const event of client.stream({ timeout: 30000 })) {
 *     console.log(event.type, event.data);
 *   }
 */

'use strict';

const http = require('http');
const https = require('https');
const { URL } = require('url');

// ─────────────────────────────────────────────
// Internal HTTP helpers (no external deps)
// ─────────────────────────────────────────────

/**
 * Make an HTTP GET request and return parsed JSON.
 * @param {string} url
 * @param {object} [options]
 * @param {number} [options.timeout=10000] - ms
 * @returns {Promise<any>}
 */
function httpGet(url, options = {}) {
  const timeout = options.timeout ?? 10000;
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    const mod = parsed.protocol === 'https:' ? https : http;
    const req = mod.request(
      { hostname: parsed.hostname, port: parsed.port, path: parsed.pathname + parsed.search,
        method: 'GET', headers: { Accept: 'application/json' } },
      (res) => {
        let raw = '';
        res.on('data', chunk => { raw += chunk; });
        res.on('end', () => {
          try { resolve(JSON.parse(raw)); }
          catch (e) { reject(new Error(`JSON parse error: ${e.message} — body: ${raw.slice(0, 200)}`)); }
        });
      }
    );
    req.setTimeout(timeout, () => { req.destroy(); reject(new Error(`GET ${url} timed out`)); });
    req.on('error', reject);
    req.end();
  });
}

/**
 * Make an HTTP POST request with a JSON body and return parsed JSON.
 * @param {string} url
 * @param {object} body
 * @param {object} [options]
 * @param {number} [options.timeout=10000] - ms
 * @returns {Promise<any>}
 */
function httpPost(url, body, options = {}) {
  const timeout = options.timeout ?? 10000;
  const payload = JSON.stringify(body);
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    const mod = parsed.protocol === 'https:' ? https : http;
    const req = mod.request(
      { hostname: parsed.hostname, port: parsed.port, path: parsed.pathname + parsed.search,
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json',
                   'Content-Length': Buffer.byteLength(payload) } },
      (res) => {
        let raw = '';
        res.on('data', chunk => { raw += chunk; });
        res.on('end', () => {
          try {
            const data = JSON.parse(raw);
            if (res.statusCode >= 400) {
              const err = new Error(`HTTP ${res.statusCode}: ${data.error || raw.slice(0, 200)}`);
              err.statusCode = res.statusCode;
              err.body = data;
              reject(err);
            } else {
              resolve(data);
            }
          } catch (e) {
            reject(new Error(`JSON parse error: ${e.message} — body: ${raw.slice(0, 200)}`));
          }
        });
      }
    );
    req.setTimeout(timeout, () => { req.destroy(); reject(new Error(`POST ${url} timed out`)); });
    req.on('error', reject);
    req.write(payload);
    req.end();
  });
}

/**
 * Async generator that streams SSE events from a URL.
 * Yields plain objects: { type, data, id, retry }.
 * @param {string} url
 * @param {object} [options]
 * @param {number} [options.timeout=30000] - total stream timeout ms (0 = no timeout)
 * @param {AbortSignal} [options.signal] - abort signal
 */
async function* sseStream(url, options = {}) {
  const timeout = options.timeout ?? 30000;
  const parsed = new URL(url);
  const mod = parsed.protocol === 'https:' ? https : http;

  const lines = [];
  let currentEvent = {};

  yield* await new Promise((resolve, reject) => {
    const gen = (async function* () {
      const chunks = [];
      let done = false;
      let error = null;
      let notify = null;

      const req = mod.request(
        { hostname: parsed.hostname, port: parsed.port,
          path: parsed.pathname + parsed.search, method: 'GET',
          headers: { Accept: 'text/event-stream', 'Cache-Control': 'no-cache' } },
        (res) => {
          let buf = '';
          res.on('data', chunk => {
            buf += chunk.toString();
            const parts = buf.split('\n');
            buf = parts.pop(); // last partial line
            for (const line of parts) {
              chunks.push(line);
              if (notify) { const n = notify; notify = null; n(); }
            }
          });
          res.on('end', () => { done = true; if (notify) { const n = notify; notify = null; n(); } });
          res.on('error', err => { error = err; if (notify) { const n = notify; notify = null; n(); } });
        }
      );
      if (timeout > 0) req.setTimeout(timeout, () => { req.destroy(); done = true; if (notify) { const n = notify; notify = null; n(); } });
      req.on('error', err => { error = err; if (notify) { const n = notify; notify = null; n(); } });
      req.end();

      // Parse SSE lines
      let ev = { type: 'message', data: '', id: null, retry: null };
      while (true) {
        while (chunks.length > 0) {
          const line = chunks.shift();
          if (line === '') {
            // dispatch event
            if (ev.data !== '') {
              yield { type: ev.type, data: ev.data, id: ev.id, retry: ev.retry };
            }
            ev = { type: 'message', data: '', id: null, retry: null };
          } else if (line.startsWith('data:')) {
            ev.data += (ev.data ? '\n' : '') + line.slice(5).trimStart();
          } else if (line.startsWith('event:')) {
            ev.type = line.slice(6).trim();
          } else if (line.startsWith('id:')) {
            ev.id = line.slice(3).trim();
          } else if (line.startsWith('retry:')) {
            ev.retry = parseInt(line.slice(6).trim(), 10);
          }
        }
        if (done || error) break;
        await new Promise(res => { notify = res; });
      }
      if (error) throw error;
    })();
    resolve(gen);
  });
}


// ─────────────────────────────────────────────
// Extension class
// ─────────────────────────────────────────────

/**
 * Extension — represents a single ACP extension declaration in AgentCard.
 * Mirrors Python acp_client.models.Extension
 */
class Extension {
  /**
   * @param {string} uri - Extension URI (e.g. "acp:ext:hmac-v1")
   * @param {boolean} [required=false]
   * @param {object} [params={}]
   */
  constructor(uri, required = false, params = {}) {
    this.uri = uri;
    this.required = required;
    this.params = params;
  }

  /** @returns {object} */
  toDict() {
    return { uri: this.uri, required: this.required, params: this.params };
  }

  /**
   * @param {object} data
   * @returns {Extension}
   */
  static fromDict(data) {
    return new Extension(data.uri ?? '', data.required ?? false, data.params ?? {});
  }

  toString() {
    return `Extension(uri=${this.uri}, required=${this.required})`;
  }
}

// ─────────────────────────────────────────────
// RelayClient class
// ─────────────────────────────────────────────

class RelayClient {
  /**
   * @param {string} baseUrl - Base URL of the running acp_relay.py, e.g. 'http://localhost:7901'
   * @param {object} [options]
   * @param {number} [options.timeout=10000] - Default request timeout ms
   */
  constructor(baseUrl, options = {}) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
    this.timeout = options.timeout ?? 10000;
  }

  _url(path) {
    return `${this.baseUrl}${path}`;
  }

  _get(path, opts = {}) {
    return httpGet(this._url(path), { timeout: this.timeout, ...opts });
  }

  _post(path, body, opts = {}) {
    return httpPost(this._url(path), body, { timeout: this.timeout, ...opts });
  }

  // ── Status & discovery ──────────────────────

  /** Get relay status and AgentCard. */
  status() { return this._get('/status'); }

  /** Get the AgentCard (/.well-known/acp.json). Parses extensions[] into Extension instances. */
  async agentCard() {
    const data = await httpGet(`${this.baseUrl}/.well-known/acp.json`, { timeout: this.timeout });
    // Parse extensions
    data.extensions = (data.extensions ?? []).map(e => Extension.fromDict(e));
    return data;
  }

  /**
   * Check if the agent declares a specific extension.
   * @param {string} uri - Extension URI to look up
   * @returns {Promise<boolean>}
   */
  async hasExtension(uri) {
    const card = await this.agentCard();
    return card.extensions.some(e => e.uri === uri);
  }

  /**
   * Get all required extensions from the AgentCard.
   * @returns {Promise<Extension[]>}
   */
  async requiredExtensions() {
    const card = await this.agentCard();
    return card.extensions.filter(e => e.required);
  }

  // ── Messaging ──────────────────────────────

  /**
   * Send a text message to the connected peer.
   * @param {string} text
   * @param {object} [extra] - Additional fields: context_id, task_id, etc.
   */
  send(text, extra = {}) {
    return this._post('/message:send', {
      type: 'acp.message',
      parts: [{ type: 'text', content: text }],
      ...extra,
    });
  }

  /**
   * Send a message with custom parts.
   * @param {Array<{type: string, content?: string, url?: string, data?: any}>} parts
   * @param {object} [extra]
   */
  sendParts(parts, extra = {}) {
    return this._post('/message:send', {
      type: 'acp.message',
      parts,
      ...extra,
    });
  }

  /**
   * Send a message to a specific peer (multi-session, v0.6+).
   * @param {string} peerId
   * @param {string} text
   * @param {object} [extra]
   */
  sendToPeer(peerId, text, extra = {}) {
    return this._post(`/peer/${encodeURIComponent(peerId)}/send`, {
      type: 'acp.message',
      parts: [{ type: 'text', content: text }],
      ...extra,
    });
  }

  /**
   * Poll pending received messages.
   * @param {object} [options]
   * @param {string} [options.after_id] - cursor for incremental polling
   * @returns {Promise<Array>}
   */
  async recv(options = {}) {
    let path = '/recv';
    if (options.after_id) path += `?after_id=${encodeURIComponent(options.after_id)}`;
    const result = await this._get(path);
    return result.messages ?? result ?? [];
  }

  // ── Peer management ────────────────────────

  /** List all connected peers. */
  async peers() {
    const result = await this._get('/peers');
    return result.peers ?? result ?? [];
  }

  /** Get info about a specific peer. */
  peer(peerId) {
    return this._get(`/peer/${encodeURIComponent(peerId)}`);
  }

  /** List LAN-discovered peers (mDNS, v0.7+). */
  async discover() {
    const result = await this._get('/discover');
    return result.peers ?? result ?? [];
  }

  // ── SSE streaming ──────────────────────────

  /**
   * Subscribe to the SSE event stream.
   * Returns an async generator yielding { type, data, id, retry }.
   * @param {object} [options]
   * @param {number} [options.timeout=30000] - stream timeout ms
   */
  stream(options = {}) {
    return sseStream(this._url('/stream'), options);
  }

  // ── Status & capability helpers ────────────

  /**
   * Get the ACP link for this node (share with peers).
   * @returns {Promise<string>}
   */
  async link() {
    const data = await this._get('/link');
    return data.link ?? '';
  }

  /**
   * Return the relay's declared capabilities block from AgentCard (v1.6+).
   *
   * Includes fields such as:
   *   - http2 (bool): HTTP/2 h2c transport enabled
   *   - did_identity (bool): DID self-sovereign identity enabled
   *   - hmac_signing (bool): HMAC-SHA256 message signing enabled
   *   - mdns (bool): mDNS LAN discovery enabled
   *   - sse_seq (bool): SSE event sequencing enabled (v2.5+)
   *
   * @returns {Promise<Record<string, boolean>>}
   */
  async capabilities() {
    try {
      const card = await this._get('/.well-known/acp.json');
      return card.capabilities ?? {};
    } catch (_) {
      return {};
    }
  }

  /**
   * Return this node's identity block (v1.3+, did:acp:).
   *
   * @returns {Promise<{did?: string, public_key_b64?: string, scheme?: string}>}
   */
  async identity() {
    const card = await this._get('/.well-known/acp.json');
    return card.identity ?? {};
  }

  /**
   * Fetch the W3C DID Document for this node (v1.3+).
   * Endpoint: GET /.well-known/did.json
   *
   * @returns {Promise<object>}
   */
  didDocument() {
    return this._get('/.well-known/did.json');
  }

  /**
   * Return the relay's declared supported interface groups (v2.5+).
   *
   * Values include: core, task, stream, mdns, p2p, identity.
   * Consumers use this list for lightweight capability negotiation before
   * attempting optional endpoints (e.g. check 'mdns' before /discover).
   *
   * @returns {Promise<string[]>}
   */
  async supportedInterfaces() {
    try {
      const card = await this._get('/.well-known/acp.json');
      return Array.from(card.supported_interfaces ?? []);
    } catch (_) {
      return [];
    }
  }

  /**
   * Return true if the relay supports SSE event sequencing (v2.5+).
   *
   * When true, all events from /stream carry a monotonically-increasing
   * `seq` field and task status/artifact events use named SSE event types.
   *
   * @returns {Promise<boolean>}
   */
  async sseSeqEnabled() {
    const caps = await this.capabilities();
    return Boolean(caps.sse_seq);
  }

  // ── Task management ────────────────────────

  /**
   * List tasks with optional filters (v1.4+).
   *
   * @param {object} [options]
   * @param {string} [options.status]        - Filter by task state (submitted/working/completed/failed/input_required/canceled)
   * @param {string} [options.peer_id]       - Filter by peer agent id
   * @param {string} [options.created_after] - ISO-8601 timestamp; return only tasks created after this time
   * @param {string} [options.updated_after] - ISO-8601 timestamp; return only tasks updated after this time
   * @param {string} [options.sort]          - Sort order: "asc" or "desc" (default "desc")
   * @param {string} [options.cursor]        - Pagination cursor from previous response
   * @param {number} [options.limit]         - Max number of tasks to return
   * @returns {Promise<Array>}
   */
  async tasks(options = {}) {
    const params = [];
    if (options.status)        params.push(`status=${encodeURIComponent(options.status)}`);
    if (options.peer_id)       params.push(`peer_id=${encodeURIComponent(options.peer_id)}`);
    if (options.created_after) params.push(`created_after=${encodeURIComponent(options.created_after)}`);
    if (options.updated_after) params.push(`updated_after=${encodeURIComponent(options.updated_after)}`);
    if (options.sort)          params.push(`sort=${encodeURIComponent(options.sort)}`);
    if (options.cursor)        params.push(`cursor=${encodeURIComponent(options.cursor)}`);
    if (options.limit != null) params.push(`limit=${options.limit}`);
    const path = params.length ? `/tasks?${params.join('&')}` : '/tasks';
    const result = await this._get(path);
    return result.tasks ?? result ?? [];
  }

  /**
   * Create a new task.
   * @param {object} task
   * @param {string} task.description
   * @param {string} [task.type='generic']
   * @param {object} [task.metadata]
   */
  createTask(task) {
    return this._post('/tasks/create', task);
  }

  /**
   * Update task state.
   * @param {string} taskId
   * @param {object} update - { state, result, error, ... }
   */
  updateTask(taskId, update) {
    return this._post(`/tasks/${encodeURIComponent(taskId)}:update`, update);
  }

  /**
   * Cancel a task (v1.5.2, spec §10).
   *
   * Cancel semantics are synchronous and idempotent:
   *   - Canceling an active task returns {"state": "canceled"}.
   *   - Canceling an already-canceled task returns 200 (idempotent).
   *   - Canceling a completed/failed task returns ERR_TASK_NOT_CANCELABLE (409).
   *
   * @param {string} taskId
   * @param {object} [options]
   * @param {boolean} [options.raiseOnTerminal=false] - If true, throw on 409 terminal state
   * @returns {Promise<object>}
   */
  async cancelTask(taskId, options = {}) {
    try {
      return await this._post(`/tasks/${encodeURIComponent(taskId)}:cancel`, {});
    } catch (err) {
      // Handle 409 ERR_TASK_NOT_CANCELABLE
      if (err && err.statusCode === 409) {
        if (options.raiseOnTerminal) {
          throw new Error(
            `Task ${taskId} is in a terminal state and cannot be canceled. ` +
            `Server: ${JSON.stringify(err.body ?? {})}`
          );
        }
        return err.body ?? { error: 'ERR_TASK_NOT_CANCELABLE', task_id: taskId };
      }
      throw err;
    }
  }

  // ── Skill discovery ────────────────────────

  /**
   * Query peer's capabilities (QuerySkill, v0.5+).
   * @param {object} [filter] - Optional filter: { category, name }
   */
  async querySkills(filter = {}) {
    let path = '/skills/query';
    const params = new URLSearchParams(filter);
    const qs = params.toString();
    if (qs) path += `?${qs}`;
    const result = await this._get(path);
    return result.skills ?? result ?? [];
  }

  // ── Convenience helpers ────────────────────

  /**
   * Wait for a peer to connect (poll /status until peer_count > 0).
   * @param {object} [options]
   * @param {number} [options.timeout=60000] - max wait ms
   * @param {number} [options.interval=2000] - poll interval ms
   */
  async waitForPeer(options = {}) {
    const timeout = options.timeout ?? 60000;
    const interval = options.interval ?? 2000;
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) {
      const status = await this.status();
      const peerCount = status.peer_count ?? status.peers?.length ?? 0;
      if (peerCount > 0) return status;
      await new Promise(r => setTimeout(r, interval));
    }
    throw new Error(`waitForPeer: no peer connected after ${timeout}ms`);
  }

  /**
   * Send a message and wait for the first reply.
   * @param {string} text
   * @param {object} [options]
   * @param {number} [options.timeout=30000]
   */
  async sendAndRecv(text, options = {}) {
    const timeout = options.timeout ?? 30000;
    await this.send(text);
    const deadline = Date.now() + timeout;
    let lastId = null;
    while (Date.now() < deadline) {
      const msgs = await this.recv(lastId ? { after_id: lastId } : {});
      if (msgs.length > 0) return msgs[0];
      lastId = msgs.length > 0 ? msgs[msgs.length - 1].message_id : lastId;
      await new Promise(r => setTimeout(r, 500));
    }
    throw new Error(`sendAndRecv: no reply within ${timeout}ms`);
  }

  /**
   * Reply to a message (sets reply_to field).
   * @param {string} messageId - The message_id to reply to
   * @param {string} text
   */
  reply(messageId, text) {
    return this.send(text, { reply_to: messageId });
  }
}

module.exports = { RelayClient, Extension, httpGet, httpPost, sseStream };
