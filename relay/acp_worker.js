/**
 * ACP Public Relay — Cloudflare Worker
 * 零注册、零 token，任意 Agent 接入
 *
 * POST /acp/new                     -> { token, link }
 * POST /acp/:token/join             -> { ok }
 * POST /acp/:token/send             -> { ok }
 * GET  /acp/:token/poll?since=<ts>  -> { messages }
 * GET  /acp/:token/status           -> { agents, message_count }
 */

const MSG_LIMIT = 100;
const SESSION_TTL = 3600;

function jsonResp(data, status) {
  return new Response(JSON.stringify(data), {
    status: status || 200,
    headers: {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    },
  });
}

export default {
  async fetch(request, env, ctx) {
    return handleRequest(request, env);
  }
};

async function handleRequest(request, env) {
  const kv = env.ACP_KV;
  const url = new URL(request.url);
  const path = url.pathname;
  const method = request.method;

  if (method === "OPTIONS") {
    return new Response(null, {
      headers: {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
      },
    });
  }

  // POST /acp/new
  if (method === "POST" && path === "/acp/new") {
    const token = "tok_" + Math.random().toString(36).slice(2, 10) + Math.random().toString(36).slice(2, 10);
    const session = { messages: [], agents: {}, created: Date.now() };
    await kv.put(token, JSON.stringify(session), { expirationTtl: SESSION_TTL });
    const link = "acp+wss://" + url.host + "/acp/" + token;
    return jsonResp({ token: token, link: link });
  }

  // /acp/:token/...
  const m = path.match(/^\/acp\/([^\/]+)\/?(.*)$/);
  if (!m) return jsonResp({ error: "not_found" }, 404);
  const token = m[1];
  const action = m[2] || "status";

  const raw = await kv.get(token);
  if (!raw) return jsonResp({ error: "invalid_token" }, 403);
  const session = JSON.parse(raw);

  // POST /acp/:token/join
  if (method === "POST" && action === "join") {
    let data = {};
    try { data = await request.json(); } catch(e) {}
    const name = data.name || "unknown";
    session.agents[name] = { joined: Date.now() };
    session.messages.push({ type: "acp.agent_card", from: name, ts: Date.now(), data: data, id: Math.random().toString(36).slice(2,10) });
    if (session.messages.length > MSG_LIMIT) session.messages = session.messages.slice(-MSG_LIMIT);
    await kv.put(token, JSON.stringify(session), { expirationTtl: SESSION_TTL });
    return jsonResp({ ok: true, session_id: token });
  }

  // POST /acp/:token/send
  if (method === "POST" && action === "send") {
    let data = {};
    try { data = await request.json(); } catch(e) {}
    const msg = Object.assign({}, data, { ts: Date.now(), id: Math.random().toString(36).slice(2,10) });
    session.messages.push(msg);
    if (session.messages.length > MSG_LIMIT) session.messages = session.messages.slice(-MSG_LIMIT);
    await kv.put(token, JSON.stringify(session), { expirationTtl: SESSION_TTL });
    return jsonResp({ ok: true });
  }

  // GET /acp/:token/poll
  if (method === "GET" && action === "poll") {
    const since = parseInt(url.searchParams.get("since") || "0");
    const newMsgs = session.messages.filter(function(msg) { return msg.ts > since; });
    return jsonResp({ messages: newMsgs });
  }

  // GET /acp/:token/status
  if (method === "GET" && (action === "status" || action === "")) {
    return jsonResp({
      agents: Object.keys(session.agents),
      message_count: session.messages.length,
      created: session.created,
    });
  }

  return jsonResp({ error: "unknown_action" }, 400);
}
