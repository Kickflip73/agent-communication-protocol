# ACP P2P Communication Skill v0.3

**You are an AI Agent. Upon receiving this Skill, execute the steps below immediately and report the result to the user.**

---

## Step 0 — Determine your role

- User message **contains** an `acp://` link → you are the **Receiver**. Follow the Receiver flow.
- User message **does not contain** an `acp://` link → you are the **Initiator**. Follow the Initiator flow.

---

## Initiator flow

```bash
pip install websockets -q

curl -fsSL \
  https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/relay/acp_relay.py \
  -o /tmp/acp_relay.py

# Replace MY_NAME with your actual agent name.
# Replace MY_SKILLS with your real capabilities (comma-separated).
python3 /tmp/acp_relay.py \
  --name "MY_NAME" \
  --skills "MY_SKILLS" \
  --port 7801 &

sleep 6
curl -s --noproxy "*" http://localhost:7901/link
```

Reply to the user **exactly** as follows (substitute the real link):

> ✅ ACP P2P service started (v0.3).
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

python3 /tmp/acp_relay.py \
  --name "MY_NAME" \
  --skills "MY_SKILLS" \
  --join <LINK> \
  --port 7820 &

sleep 4
curl -s --noproxy "*" http://localhost:7920/card
```

Reply to the user:

> ✅ P2P connection established (no intermediary server).
> Connected to: **[peer name]** | Skills: [peer skills]
> Supported modes: Sync · Async · Stream · Push

---

## Communication modes

### Mode 1 — Synchronous (request / response)

Send a message and **block until the peer replies** (or timeout):

```bash
# Caller blocks until reply arrives (timeout: 30s default)
curl -s --noproxy "*" -X POST http://localhost:<PORT>/send \
  -H "Content-Type: application/json" \
  -d '{"type":"query","content":"...","sync":true,"timeout":30}'

# Peer replies with:
curl -s --noproxy "*" -X POST http://localhost:<PEER_PORT>/reply \
  -H "Content-Type: application/json" \
  -d '{"correlation_id":"<original msg id>","content":"<reply>"}'
```

### Mode 2 — Asynchronous (task lifecycle)

Create a task, delegate to peer, poll for completion:

```bash
# Create + delegate task to peer
curl -s --noproxy "*" -X POST http://localhost:<PORT>/tasks/create \
  -H "Content-Type: application/json" \
  -d '{"payload":{"task":"..."},"delegate":true}'
# Returns: {"task": {"id": "task_xxx", "status": "submitted", ...}}

# Poll status
curl -s --noproxy "*" http://localhost:<PORT>/tasks/<task_id>

# Peer updates task status (working → completed)
curl -s --noproxy "*" -X POST http://localhost:<PORT>/tasks/<task_id>/update \
  -H "Content-Type: application/json" \
  -d '{"status":"completed","artifact":{"type":"text","content":"result"}}'

# Cancel a running task
curl -s --noproxy "*" -X DELETE http://localhost:<PORT>/tasks/<task_id>
```

Task states: `submitted` → `working` → `completed` | `failed` | `cancelled`

### Mode 3 — Streaming (SSE real-time events)

Subscribe to a live event stream (all messages, task updates, connection events):

```bash
curl -N --noproxy "*" http://localhost:<PORT>/stream
# Streams server-sent events:
# data: {"event":"message.received","message":{...}}
# data: {"event":"task.updated","task_id":"...","status":"working"}
# data: {"event":"peer.connected"}
```

### Mode 4 — Push (webhook callback)

Register a webhook URL; the daemon POSTs all events to it automatically:

```bash
# Register
curl -s --noproxy "*" -X POST http://localhost:<PORT>/webhooks/register \
  -H "Content-Type: application/json" \
  -d '{"url":"https://your-agent-host/acp-hook"}'

# Deregister
curl -s --noproxy "*" -X POST http://localhost:<PORT>/webhooks/deregister \
  -H "Content-Type: application/json" \
  -d '{"url":"https://your-agent-host/acp-hook"}'
```

---

## Full API reference (v0.3)

| Method | Path | Mode | Description |
|--------|------|------|-------------|
| `POST` | `/send` | Sync / Async | Send message. Add `"sync":true` to block for reply |
| `POST` | `/reply` | Sync | Reply to a received message by `correlation_id` |
| `GET`  | `/recv` | Async | Consume queued messages (`?limit=N`) |
| `GET`  | `/wait/<id>` | Sync | Block-wait for a correlated reply (`?timeout=30`) |
| `POST` | `/tasks/create` | Async | Create a task (`"delegate":true` sends to peer) |
| `GET`  | `/tasks` | Async | List tasks (`?status=working`) |
| `GET`  | `/tasks/<id>` | Async | Get task state + artifacts |
| `POST` | `/tasks/<id>/update` | Async | Update task status / add artifact |
| `DELETE` | `/tasks/<id>` | Async | Cancel a task |
| `GET`  | `/stream` | Stream | SSE real-time event feed |
| `POST` | `/webhooks/register` | Push | Register a push webhook URL |
| `POST` | `/webhooks/deregister` | Push | Remove a push webhook URL |
| `GET`  | `/status` | — | Connection state, statistics, version |
| `GET`  | `/link` | — | This agent's `acp://` connection link |
| `GET`  | `/card` | — | AgentCards (self + peer) |
| `GET`  | `/history` | — | Persisted message history (`?limit=N`) |

---

*ACP P2P v0.3 · https://github.com/Kickflip73/agent-communication-protocol*
