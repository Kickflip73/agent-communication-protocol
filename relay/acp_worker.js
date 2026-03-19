/**
 * ACP Public Relay — Cloudflare Worker
 * 零注册、零 token，任意 Agent 接入
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

function makeId() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

export default {
  async fetch(request, env, ctx) {
    try {
      return await handleRequest(request, env);
    } catch (e) {
      return jsonResp({ error: String(e) }, 500);
    }
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
    const token = "tok_" + makeId();
    const session = { messages: [], agents: {}, created: Date.now() };
    await kv.put(token, JSON.stringify(session), { expirationTtl: SESSION_TTL });
    const link = "acp+wss://" + url.host + "/acp/" + token;
    return jsonResp({ token: token, link: link });
  }

  // 解析 /acp/:token/:action
  const parts = path.split("/").filter(function(p) { return p.length > 0; });
  // parts[0] = "acp", parts[1] = token, parts[2] = action
  if (parts[0] !== "acp" || !parts[1]) {
    return jsonResp({ error: "not_found" }, 404);
  }
  const token = parts[1];
  const action = parts[2] || "status";

  const raw = await kv.get(token);
  if (!raw) return jsonResp({ error: "invalid_token" }, 403);

  const session = JSON.parse(raw);

  // POST /acp/:token/join
  if (method === "POST" && action === "join") {
    let data = {};
    try { data = await request.json(); } catch(e) {}
    const name = (data && data.name) ? String(data.name) : "unknown";
    session.agents[name] = { joined: Date.now() };
    session.messages.push({
      type: "acp.agent_card", from: name,
      ts: Date.now(), data: data, id: makeId()
    });
    if (session.messages.length > MSG_LIMIT) {
      session.messages = session.messages.slice(-MSG_LIMIT);
    }
    await kv.put(token, JSON.stringify(session), { expirationTtl: SESSION_TTL });
    return jsonResp({ ok: true, session_id: token });
  }

  // POST /acp/:token/send
  if (method === "POST" && action === "send") {
    let data = {};
    try { data = await request.json(); } catch(e) {}
    const msg = Object.assign({}, data, { ts: Date.now(), id: makeId() });
    session.messages.push(msg);
    if (session.messages.length > MSG_LIMIT) {
      session.messages = session.messages.slice(-MSG_LIMIT);
    }
    await kv.put(token, JSON.stringify(session), { expirationTtl: SESSION_TTL });
    return jsonResp({ ok: true });
  }

  // GET /acp/:token/poll?since=<ts>
  if (method === "GET" && action === "poll") {
    const sinceStr = url.searchParams.get("since") || "0";
    const since = Number(sinceStr);
    const newMsgs = session.messages.filter(function(msg) {
      return Number(msg.ts) > since;
    });
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
