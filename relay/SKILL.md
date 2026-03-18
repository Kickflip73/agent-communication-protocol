---
name: acp-protocol
description: 让任意两个 Agent 建立直接 P2P 通信，无需中间服务器，无需修改任何代码。发起方运行后生成 acp:// 链接，接收方粘贴链接直连，2步完成。连接建立后双方全双工通信，互为发送方和接收方，支持同步、异步、流式、Push 四种通信模式。触发词: ACP, agent-to-agent, 让两个agent通信, p2p agent, 建立agent连接, 安装通信服务, acp relay, agent互联, agent直连.
---

# ACP P2P Communication Protocol

**Read this file entirely. Execute the steps for your role immediately. Report result to the user.**

---

## Step 1 — Determine your role (one-time, connection phase only)

| Situation | Role |
|-----------|------|
| User message has **no** `acp://` link | **Initiator** — start listening, generate link |
| User message **contains** an `acp://` link | **Joiner** — connect to peer using that link |

> Once connected, both sides are fully symmetric — each can send and receive freely.

---

## Step 2 — Install & start

```bash
pip install websockets -q

curl -fsSL \
  https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/relay/acp_relay.py \
  -o /tmp/acp_relay.py
```

**If Initiator:**
```bash
# Fill in MY_NAME and MY_SKILLS before running
python3 /tmp/acp_relay.py --name "MY_NAME" --skills "MY_SKILLS" --port 7801 &
sleep 8
ACP_LINK=$(curl -s --noproxy "*" http://localhost:7901/link \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['link'])")
echo "ACP_LINK=$ACP_LINK"
```

**Reply to user (required):**
> ✅ ACP service started. 🔗 Link: `<ACP_LINK value from output>`
> Forward this link to the other agent — that's all they need.

---

**If Joiner** (replace `<LINK>` with the actual acp:// link):
```bash
# Fill in MY_NAME and MY_SKILLS before running
python3 /tmp/acp_relay.py --name "MY_NAME" --skills "MY_SKILLS" --join <LINK> --port 7820 &
sleep 5
curl -s --noproxy "*" http://localhost:7920/card \
  | python3 -c "
import json,sys
d=json.load(sys.stdin)
p=d.get('peer') or {}
print('PEER_NAME=' + str(p.get('name','unknown')))
print('PEER_SKILLS=' + str(p.get('skills',[])))
"
```

**Reply to user (required):**
> ✅ Connected. 🤝 Peer: `<PEER_NAME>` | Skills: `<PEER_SKILLS>`
> Full-duplex channel ready. Both sides can send and receive.

---

## Step 3 — Send & receive (both sides, identical)

Default ports: Initiator HTTP=`7901`, Joiner HTTP=`7920` (rule: HTTP = WS port + 100).

```bash
# Send a message
curl -s --noproxy "*" -X POST http://localhost:<HTTP_PORT>/send \
  -H "Content-Type: application/json" \
  -d '{"type":"message","content":"Hello!"}'

# Receive queued messages
curl -s --noproxy "*" http://localhost:<HTTP_PORT>/recv
```

For advanced communication modes (sync request/reply, async tasks, SSE streaming, push webhooks), see [`references/modes.md`](references/modes.md).

---

## CLI options

| Flag | Default | Description |
|------|---------|-------------|
| `--name` | `ACP-Agent` | Agent display name |
| `--join` | — | `acp://` link to connect to (omit = Initiator) |
| `--port` | `7801` | WebSocket port; HTTP = this + 100 |
| `--skills` | — | Comma-separated capability list |
| `--inbox` | `/tmp/acp_inbox_<name>.jsonl` | Message persistence file |

---

*ACP P2P v0.3 · https://github.com/Kickflip73/agent-communication-protocol*
