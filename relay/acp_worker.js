/**
 * ACP Public Relay — Cloudflare Worker
 * 零注册、零 token，任意 Agent 接入
 *
 * 接口：
 *   POST /acp/new              -> { token, link }   创建新会话
 *   POST /acp/:token/send      -> { ok }             发消息
 *   GET  /acp/:token/poll?since=<ts> -> { messages } 长轮询收消息（20s）
 *   GET  /acp/:token/status    -> { agents, count }  会话状态
 *
 * 存储：Cloudflare KV（TTL 1小时，消息自动过期）
 * 限制：每个 token 最多存 100 条消息
 */

const MSG_LIMIT = 100;
const SESSION_TTL = 3600; // 1小时

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;
    const method = request.method;

    // CORS
    const headers = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
      "Content-Type": "application/json",
    };

    if (method === "OPTIONS") {
      return new Response(null, { headers });
    }

    // POST /acp/new — 创建会话
    if (method === "POST" && path === "/acp/new") {
      const token = "tok_" + crypto.randomUUID().replace(/-/g, "").slice(0, 16);
      const session = { messages: [], agents: {}, created: Date.now() };
      await env.ACP_KV.put(token, JSON.stringify(session), { expirationTtl: SESSION_TTL });
      const link = `acp+wss://${url.host}/acp/${token}`;
      return new Response(JSON.stringify({ token, link }), { headers });
    }

    // 解析 /acp/:token/...
    const m = path.match(/^\/acp\/([^\/]+)\/?(.*)?$/);
    if (!m) {
      return new Response(JSON.stringify({ error: "not_found" }), { status: 404, headers });
    }
    const [, token, action] = m;

    // 读取会话
    const raw = await env.ACP_KV.get(token);
    if (!raw) {
      return new Response(JSON.stringify({ error: "invalid_token" }), { status: 403, headers });
    }
    const session = JSON.parse(raw);

    // POST /acp/:token/send
    if (method === "POST" && action === "send") {
      const data = await request.json().catch(() => ({}));
      const msg = { ...data, ts: Date.now(), id: crypto.randomUUID().slice(0, 8) };
      session.messages.push(msg);
      if (session.messages.length > MSG_LIMIT) {
        session.messages = session.messages.slice(-MSG_LIMIT);
      }
      await env.ACP_KV.put(token, JSON.stringify(session), { expirationTtl: SESSION_TTL });
      return new Response(JSON.stringify({ ok: true }), { headers });
    }

    // POST /acp/:token/join
    if (method === "POST" && action === "join") {
      const data = await request.json().catch(() => ({}));
      const name = data.name || "unknown";
      session.agents[name] = { joined: Date.now(), ...data };
      const msg = { type: "acp.agent_card", from: name, ts: Date.now(), data, id: crypto.randomUUID().slice(0, 8) };
      session.messages.push(msg);
      await env.ACP_KV.put(token, JSON.stringify(session), { expirationTtl: SESSION_TTL });
      return new Response(JSON.stringify({ ok: true, session_id: token }), { headers });
    }

    // GET /acp/:token/poll?since=<ts>
    if (method === "GET" && action === "poll") {
      const since = parseInt(url.searchParams.get("since") || "0");
      // Cloudflare Workers 不支持真正的长轮询（有 CPU 限制）
      // 返回 since 之后的所有消息
      const newMsgs = session.messages.filter(m => m.ts > since);
      return new Response(JSON.stringify({ messages: newMsgs }), { headers });
    }

    // GET /acp/:token/status
    if (method === "GET" && (action === "status" || action === "")) {
      return new Response(JSON.stringify({
        agents: Object.keys(session.agents),
        message_count: session.messages.length,
        created: session.created,
      }), { headers });
    }

    return new Response(JSON.stringify({ error: "unknown_action" }), { status: 400, headers });
  }
};
