/**
 * ACP Public Relay — Cloudflare Worker v2.0
 *
 * v2.0 changes (2026-03-20):
 *   - Multi-room list: GET /acp/rooms (active sessions index via KV meta key)
 *   - Sliding TTL refresh: every operation resets SESSION_TTL countdown
 *   - Message cursor: POST /acp/:token/poll supports ?after_id= for exact-once delivery
 *   - Session stats: last_active, agent_count, message_count in GET /status
 *   - DELETE /acp/:token: explicit session cleanup (removes from rooms index too)
 *   - Active rooms cap: max MAX_ROOMS concurrent sessions (evicts oldest by last_active)
 *   - Idempotent /acp/new: existing session reused, returns same token
 *
 * v1.0 (2026-03-19): initial HTTP relay, KV-backed message queue
 */

const MSG_LIMIT  = 200;      // max messages per session
const SESSION_TTL = 3600;    // seconds, sliding
const MAX_ROOMS   = 500;     // max concurrent active sessions
const ROOMS_KEY   = "__rooms_index__";  // KV key for rooms index

function jsonResp(data, status) {
  return new Response(JSON.stringify(data, null, 2), {
    status: status || 200,
    headers: {
      "Content-Type":                "application/json; charset=utf-8",
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    },
  });
}

function makeId() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

function nowMs() { return Date.now(); }

/** Load rooms index from KV. Returns { [token]: { last_active, created } }. */
async function loadRooms(kv) {
  const raw = await kv.get(ROOMS_KEY);
  if (!raw) return {};
  try { return JSON.parse(raw); } catch(e) { return {}; }
}

/** Persist rooms index to KV (no TTL — this is the index, not a session). */
async function saveRooms(kv, rooms) {
  await kv.put(ROOMS_KEY, JSON.stringify(rooms));
}

/** Register or update a session in the rooms index, evicting oldest if over cap. */
async function touchRoom(kv, token) {
  const rooms = await loadRooms(kv);
  rooms[token] = { last_active: nowMs(), created: rooms[token]?.created || nowMs() };
  const keys = Object.keys(rooms);
  if (keys.length > MAX_ROOMS) {
    // Evict oldest by last_active
    const sorted = keys.sort((a, b) => rooms[a].last_active - rooms[b].last_active);
    const evict = sorted.slice(0, keys.length - MAX_ROOMS);
    for (const k of evict) {
      delete rooms[k];
      await kv.delete(k);  // best-effort cleanup
    }
  }
  await saveRooms(kv, rooms);
}

/** Remove a session from the rooms index. */
async function removeRoom(kv, token) {
  const rooms = await loadRooms(kv);
  delete rooms[token];
  await saveRooms(kv, rooms);
}

export default {
  async fetch(request, env, ctx) {
    try {
      return await handleRequest(request, env, ctx);
    } catch (e) {
      return jsonResp({ error: "internal_error", detail: String(e) }, 500);
    }
  }
};

async function handleRequest(request, env, ctx) {
  const kv  = env.ACP_KV;
  const url  = new URL(request.url);
  const path = url.pathname;
  const method = request.method;

  // CORS preflight
  if (method === "OPTIONS") {
    return new Response(null, {
      headers: {
        "Access-Control-Allow-Origin":  "*",
        "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
      },
    });
  }

  // ── GET /acp/rooms — list active sessions (v2.0) ────────────────────────
  if (method === "GET" && path === "/acp/rooms") {
    const rooms = await loadRooms(kv);
    const list = Object.entries(rooms)
      .sort((a, b) => b[1].last_active - a[1].last_active)
      .map(([token, meta]) => ({
        token,
        last_active: meta.last_active,
        created: meta.created,
        age_s: Math.round((nowMs() - meta.created) / 1000),
        idle_s: Math.round((nowMs() - meta.last_active) / 1000),
      }));
    return jsonResp({ rooms: list, count: list.length, max: MAX_ROOMS });
  }

  // ── POST /acp/new ─────────────────────────────────────────────────────────
  if (method === "POST" && path === "/acp/new") {
    const reqToken = url.searchParams.get("token");
    const token = (reqToken && /^[a-zA-Z0-9_-]{6,64}$/.test(reqToken))
      ? reqToken
      : "tok_" + makeId();
    const existing = await kv.get(token);
    const session = existing
      ? JSON.parse(existing)
      : { messages: [], agents: {}, created: nowMs(), last_active: nowMs(), seq: 0 };
    const existed = !!existing;
    // Slide TTL
    await kv.put(token, JSON.stringify(session), { expirationTtl: SESSION_TTL });
    ctx.waitUntil(touchRoom(kv, token));
    const link = "acp+wss://" + url.host + "/acp/" + token;
    return jsonResp({ token, link, existed });
  }

  // ── Parse /acp/:token[/:action] ───────────────────────────────────────────
  const parts = path.split("/").filter(p => p.length > 0);
  // parts[0]="acp", parts[1]=token, parts[2]=action
  if (parts[0] !== "acp" || !parts[1]) {
    return jsonResp({ error: "not_found", hint: "Use /acp/new to create a session" }, 404);
  }
  const token  = parts[1];
  const action = parts[2] || "status";

  // ── DELETE /acp/:token — explicit cleanup (v2.0) ──────────────────────────
  if (method === "DELETE" && !parts[2]) {
    await kv.delete(token);
    ctx.waitUntil(removeRoom(kv, token));
    return jsonResp({ ok: true, deleted: token });
  }

  // Load session (required for all remaining actions)
  const raw = await kv.get(token);
  if (!raw) return jsonResp({ error: "invalid_token", hint: "Session not found or expired" }, 403);
  const session = JSON.parse(raw);

  // Helper: save session with sliding TTL + update rooms index
  async function save() {
    session.last_active = nowMs();
    await kv.put(token, JSON.stringify(session), { expirationTtl: SESSION_TTL });
    ctx.waitUntil(touchRoom(kv, token));
  }

  // ── POST /acp/:token/join ─────────────────────────────────────────────────
  if (method === "POST" && action === "join") {
    let data = {};
    try { data = await request.json(); } catch(e) {}
    const name = (data && data.name) ? String(data.name).slice(0, 64) : "agent_" + makeId().slice(0, 6);
    session.agents[name] = { joined: nowMs(), card: data.card || null };
    const joinMsg = {
      type: "acp.agent_joined",
      id: makeId(),
      seq: ++session.seq,
      from: name,
      ts: nowMs(),
      card: data.card || null,
    };
    session.messages.push(joinMsg);
    if (session.messages.length > MSG_LIMIT) {
      session.messages = session.messages.slice(-MSG_LIMIT);
    }
    await save();
    return jsonResp({ ok: true, session_id: token, seq: session.seq, agent_name: name });
  }

  // ── POST /acp/:token/send ─────────────────────────────────────────────────
  if (method === "POST" && action === "send") {
    let data = {};
    try { data = await request.json(); } catch(e) {}
    const msg = {
      ...data,
      id:  data.id || makeId(),
      seq: ++session.seq,
      ts:  nowMs(),
    };
    // Message deduplication by id (last MSG_LIMIT messages)
    const existingIds = new Set(session.messages.map(m => m.id));
    if (existingIds.has(msg.id)) {
      // Idempotent: already received
      return jsonResp({ ok: true, deduped: true, id: msg.id });
    }
    session.messages.push(msg);
    if (session.messages.length > MSG_LIMIT) {
      session.messages = session.messages.slice(-MSG_LIMIT);
    }
    await save();
    return jsonResp({ ok: true, id: msg.id, seq: msg.seq });
  }

  // ── GET /acp/:token/poll?since=<ts>&after_id=<id>&limit=<n> ──────────────
  if (method === "GET" && action === "poll") {
    const sinceStr  = url.searchParams.get("since") || "0";
    const afterId   = url.searchParams.get("after_id") || null;
    const limitStr  = url.searchParams.get("limit") || "50";
    const since     = Number(sinceStr);
    const limit     = Math.min(Number(limitStr) || 50, MSG_LIMIT);

    let msgs = session.messages;

    if (afterId) {
      // Cursor-based: return messages after the given id (exact-once semantics)
      const idx = msgs.findIndex(m => m.id === afterId);
      msgs = idx >= 0 ? msgs.slice(idx + 1) : msgs;
    } else {
      // Timestamp-based (legacy compat)
      msgs = msgs.filter(m => Number(m.ts) > since);
    }

    msgs = msgs.slice(0, limit);
    const lastId = msgs.length ? msgs[msgs.length - 1].id : afterId;
    return jsonResp({
      messages: msgs,
      count: msgs.length,
      last_id: lastId,
      server_seq: session.seq,
    });
  }

  // ── GET /acp/:token/status ─────────────────────────────────────────────────
  if (method === "GET" && (action === "status" || action === "")) {
    return jsonResp({
      token,
      agents: Object.keys(session.agents),
      agent_count: Object.keys(session.agents).length,
      message_count: session.messages.length,
      server_seq: session.seq || 0,
      created: session.created,
      last_active: session.last_active,
      idle_s: Math.round((nowMs() - (session.last_active || session.created)) / 1000),
      ttl_s: SESSION_TTL,
    });
  }

  return jsonResp({ error: "unknown_action", action }, 400);
}
