# ACP P2P Communication Skill v0.2

**You are an AI Agent. Upon receiving this Skill, execute the steps below immediately and report the result to the user.**

---

## Step 0 — Determine your role

- User message **contains** an `acp://` link → you are the **Receiver**. Follow the Receiver flow.
- User message **does not contain** an `acp://` link → you are the **Initiator**. Follow the Initiator flow.

---

## Initiator flow

Run the following commands in sequence:

```bash
pip install websockets -q

curl -fsSL \
  https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/relay/acp_relay.py \
  -o /tmp/acp_relay.py

# Replace MY_NAME with your agent's actual name.
# Replace MY_SKILLS with a comma-separated list of your real capabilities (e.g. summarize,code-review).
python3 /tmp/acp_relay.py \
  --name "MY_NAME" \
  --skills "MY_SKILLS" \
  --port 7801 &

sleep 6
curl -s --noproxy "*" http://localhost:7901/link
```

The last command returns:

```json
{"link": "acp://x.x.x.x:7801/tok_xxxxxxxxxxxxxxxx"}
```

Reply to the user **exactly** as follows (substitute the real link value):

> ✅ ACP P2P service started (v0.2).
> Your link: `acp://x.x.x.x:7801/tok_xxxxxxxxxxxxxxxx`
> Please forward this link to Agent B.

---

## Receiver flow

Substitute `<LINK>` with the `acp://` link provided by the user:

```bash
pip install websockets -q

curl -fsSL \
  https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/relay/acp_relay.py \
  -o /tmp/acp_relay.py

# Replace MY_NAME and MY_SKILLS as above.
python3 /tmp/acp_relay.py \
  --name "MY_NAME" \
  --skills "MY_SKILLS" \
  --join <LINK> \
  --port 7820 &

sleep 4
curl -s --noproxy "*" http://localhost:7920/status
curl -s --noproxy "*" http://localhost:7920/card
```

On success, `/card` returns both AgentCards. Reply to the user:

> ✅ P2P connection established (no intermediary server).
> Connected to: **[peer name]** | Skills: [peer skills]
>
> Communication endpoints:
> - Send: `POST http://localhost:7920/send`
> - Receive: `GET http://localhost:7920/recv`

---

## Sending and receiving messages

```bash
# Send (replace PORT with 7901 for initiator, 7920 for receiver)
curl -s --noproxy "*" -X POST http://localhost:<PORT>/send \
  -H "Content-Type: application/json" \
  -d '{"type": "task.delegate", "content": "Your message here"}'

# Receive
curl -s --noproxy "*" http://localhost:<PORT>/recv
```

---

## Full API reference (v0.2)

| Path | Method | Description |
|------|--------|-------------|
| `/send` | `POST` | Send a message (any JSON body) |
| `/recv` | `GET` | Consume queued incoming messages (`?limit=N`) |
| `/status` | `GET` | Connection state, statistics, version |
| `/link` | `GET` | This agent's `acp://` connection link |
| `/card` | `GET` | AgentCards for both this agent and its peer |
| `/history` | `GET` | Full persisted message history (`?limit=N`) |
| `/stream` | `GET` | SSE stream — real-time push of incoming messages |

---

*ACP P2P v0.2 · https://github.com/Kickflip73/agent-communication-protocol*
