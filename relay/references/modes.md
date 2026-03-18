# ACP Communication Modes

Four patterns. All work identically on both sides of the connection.

---

## Mode 1 — Synchronous (request / reply)

Send and **block until the peer replies** (or timeout).

```bash
# Side A: send with sync=true, blocks until reply arrives
curl -s --noproxy "*" -X POST http://localhost:<PORT>/send \
  -H "Content-Type: application/json" \
  -d '{"type":"query","content":"What is 2+2?","sync":true,"timeout":30}'
# Returns immediately when peer replies, or after timeout

# Side B: reply to the message
curl -s --noproxy "*" http://localhost:<PORT>/recv          # get msg id
curl -s --noproxy "*" -X POST http://localhost:<PORT>/reply \
  -H "Content-Type: application/json" \
  -d '{"correlation_id":"<msg id from recv>","content":"4"}'
```

---

## Mode 2 — Async task lifecycle

Create a task, delegate it to the peer, poll or receive push updates.

```bash
# Create task + send to peer (delegate:true)
curl -s --noproxy "*" -X POST http://localhost:<PORT>/tasks/create \
  -H "Content-Type: application/json" \
  -d '{"payload":{"task":"summarize doc"},"delegate":true}'
# → {"task": {"id": "task_xxx", "status": "submitted"}}

# Poll status
curl -s --noproxy "*" http://localhost:<PORT>/tasks/<task_id>

# Update task (working → completed)
curl -s --noproxy "*" -X POST http://localhost:<PORT>/tasks/<task_id>/update \
  -H "Content-Type: application/json" \
  -d '{"status":"completed","artifact":{"type":"text","content":"summary here"}}'

# Cancel
curl -s --noproxy "*" -X DELETE http://localhost:<PORT>/tasks/<task_id>
```

States: `submitted` → `working` → `completed` | `failed` | `cancelled`

---

## Mode 3 — Streaming (SSE)

Subscribe once; receive all events in real time.

```bash
curl -N --noproxy "*" http://localhost:<PORT>/stream
# data: {"event":"message.received","message":{...}}
# data: {"event":"task.updated","task_id":"...","status":"working"}
# data: {"event":"peer.connected"}
# : keepalive
```

---

## Mode 4 — Push (webhook)

Register a URL; the daemon delivers every event via HTTP POST automatically.

```bash
# Register
curl -s --noproxy "*" -X POST http://localhost:<PORT>/webhooks/register \
  -H "Content-Type: application/json" \
  -d '{"url":"https://your-host/hook"}'

# Deregister
curl -s --noproxy "*" -X POST http://localhost:<PORT>/webhooks/deregister \
  -H "Content-Type: application/json" \
  -d '{"url":"https://your-host/hook"}'
```

---

## Full API reference

| Method | Path | Mode | Description |
|--------|------|------|-------------|
| `POST` | `/send` | Sync/Async | Send message; add `"sync":true` to block for reply |
| `POST` | `/reply` | Sync | Reply by `correlation_id` |
| `GET`  | `/recv` | Async | Dequeue received messages (`?limit=N`) |
| `GET`  | `/wait/<id>` | Sync | Block-wait for correlated reply (`?timeout=30`) |
| `POST` | `/tasks/create` | Async | Create task; `"delegate":true` forwards to peer |
| `GET`  | `/tasks` | Async | List tasks (`?status=working`) |
| `GET`  | `/tasks/<id>` | Async | Get task + artifacts |
| `POST` | `/tasks/<id>/update` | Async | Update status / add artifact |
| `DELETE` | `/tasks/<id>` | Async | Cancel task |
| `GET`  | `/stream` | Stream | SSE event feed |
| `POST` | `/webhooks/register` | Push | Add webhook URL |
| `POST` | `/webhooks/deregister` | Push | Remove webhook URL |
| `GET`  | `/status` | — | Connection info + stats |
| `GET`  | `/link` | — | This agent's `acp://` link |
| `GET`  | `/card` | — | AgentCards (self + peer) |
| `GET`  | `/history` | — | Persisted message log (`?limit=N`) |
