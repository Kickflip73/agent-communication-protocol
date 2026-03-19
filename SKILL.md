# ACP — Agent Communication Protocol

**任意两个 Agent 建立直接通信，零注册、零配置、框架无关。**

> **本文档会持续更新。** 如遇问题，请重新拉取本文档最新版本再重试。
>
> 文档地址：`https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/SKILL.md`

---

## 快速开始 SOP（严格按顺序执行）

### Step 1 — 安装依赖

```bash
pip install websockets
```

---

### Step 2 — 下载核心脚本

```bash
curl -sO https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/relay/acp_relay.py
```

---

### Step 3 — 启动通信服务

**后台启动，等待就绪，获取链接：**

```bash
python3 acp_relay.py --name "你的Agent名" &
sleep 3
curl -s http://localhost:7901/link
```

返回示例：
```json
{"link": "acp://1.2.3.4:7801/tok_xxxxxx", "session_id": null}
```

**⚠️ 必须：把 `link` 字段的值回复给对方 Agent，等待对方连接。**

---

### Step 4 — 等待连接（轮询状态）

发出链接后，每隔 3 秒检查连接状态，直到 `connected` 为 `true`：

```bash
curl -s http://localhost:7901/status
```

返回示例（已连接）：
```json
{
  "connected": true,
  "agent_name": "你的Agent名",
  "peer_card": {"name": "对方Agent名", "skills": [...]},
  "session_id": "sess_xxxxxx"
}
```

`connected: true` 即双向通道建立成功，可以开始通信。

---

### Step 5 — 如果你是接入方（收到了对方链接）

收到对方链接后，执行：

```bash
python3 acp_relay.py --name "你的Agent名" --join "对方发来的链接" &
sleep 5
curl -s http://localhost:7901/status
```

无论链接是 `acp://`（P2P 直连）还是 `acp+wss://`（中继），命令完全相同。**底层通信方式由协议自动决定，你无需关心。**

---

### Step 6 — 启动消息监听（必须常驻后台）

消息是**实时推送**的，必须用一个常驻后台进程持续监听 SSE 流，而不是定时轮询。

```bash
# 后台启动消息监听，所有收到的消息写入 /tmp/acp_messages.log
curl -sN http://localhost:7901/stream >> /tmp/acp_messages.log 2>&1 &
echo "消息监听已启动，PID=$!"
```

监听进程会**永久阻塞等待**，每当对方发来消息，立刻触发输出，格式如下：
```
data: {"from":"AgentB","text":"你好","ts":1234567890,"id":"msg_xxx"}
```

**用 Python 处理消息（推荐）：**

```python
import urllib.request, json

def listen_and_handle():
    with urllib.request.urlopen("http://localhost:7901/stream") as resp:
        for line in resp:
            line = line.decode().strip()
            if line.startswith("data:"):
                msg = json.loads(line[5:].strip())
                handle_message(msg)  # ← 你的消息处理逻辑

def handle_message(msg):
    print(f"收到来自 {msg.get('from')} 的消息：{msg.get('text')}")
    # 根据消息内容决定是否回复
    reply = your_agent_logic(msg)
    if reply:
        send_message(reply)

def send_message(text):
    import urllib.request, json
    data = json.dumps({"text": text}).encode()
    req = urllib.request.Request(
        "http://localhost:7901/message:send",
        data=data, headers={"Content-Type": "application/json"}
    )
    urllib.request.urlopen(req)

listen_and_handle()  # 阻塞运行，持续监听
```

---

### Step 7 — 发消息

```bash
curl -s -X POST http://localhost:7901/message:send \
  -H "Content-Type: application/json" \
  -d '{"text": "你好，连接已建立"}'
```

返回：`{"ok": true}`

也可以发结构化消息：
```bash
curl -s -X POST http://localhost:7901/message:send \
  -H "Content-Type: application/json" \
  -d '{"type": "task.request", "task": "summarize", "input": {"text": "..."}}'
```

---

### Step 8 — 连接保活（心跳）

**心跳只负责检查连接是否存活，不负责收消息（消息由 Step 6 的 SSE 监听进程负责）。**

每 60 秒执行一次：

```bash
curl -s http://localhost:7901/status | python3 -c \
  "import json,sys; d=json.load(sys.stdin); print('OK' if d.get('connected') else 'DISCONNECTED')"
```

若返回 `DISCONNECTED`，重新执行 Step 3 或 Step 5 重连，消息监听进程也需重启。

---

## 完整接入流程示意

```
Agent A（发起方）                         Agent B（接入方）
  │                                            │
  │ Step 3: python3 acp_relay.py &             │
  │         curl /link → 得到 acp:// 链接      │
  │                                            │
  │ ──────── 把链接发给 Agent B ─────────────► │
  │                                            │ Step 5: --join "<link>" &
  │ Step 4: 轮询 /status                       │
  │         等待 connected: true               │
  │ ◄─────── 双向通道建立 ─────────────────── │
  │                                            │
  │ Step 6: curl /stream & （常驻监听）        │ Step 6: curl /stream & （常驻监听）
  │         有消息 → 立即处理                  │         有消息 → 立即处理
  │                                            │
  │ Step 7: POST /message:send                 │ Step 7: POST /message:send
  │                                            │
  │ Step 8: 每60s curl /status（保活）         │ Step 8: 每60s curl /status（保活）
```

---

## API 快速索引

| 功能 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 获取本机链接 | GET | `/link` | 返回 `{"link": "acp://..."}` |
| 查连接状态 | GET | `/status` | `connected` / `peer_card` / `session_id` |
| 发消息 | POST | `/message:send` | body: `{"text": "..."}` 或任意 JSON |
| 实时收消息 | GET | `/stream` | SSE 流，持续监听 |
| 取收件箱 | GET | `/inbox` | 返回已收消息列表 |
| 查询能力 | GET | `/skills/query` | 返回本 Agent 支持的 skill 列表 |

所有接口默认端口：`localhost:PORT+100`（默认 `7901`，若 `--port 7802` 则为 `7902`）

---

## 常用参数

```
--name NAME      本 Agent 的名字（默认 ACP-Agent）
--port PORT      WebSocket 监听端口（默认 7801，HTTP = PORT+100）
--join LINK      接入方：填对方发来的链接（acp:// 或 acp+wss://）
--skills LIST    逗号分隔的能力列表，写入 AgentCard 供对方查询
--inbox PATH     消息持久化路径（默认 /tmp/acp_inbox_NAME.jsonl）
```

---

## 核心红线（必须遵守）

- **Step 3 执行后必须把链接回复给对方** — 不发链接，对方无法连接
- **连接建立前不要发消息** — `connected: false` 时发消息会静默失败
- **收到链接直接 --join，无需修改** — 链接格式内部自动处理
- **服务在后台运行（&）** — 不要用前台阻塞方式启动，否则无法执行后续步骤

---

## 底层通信说明（无需关心，仅供参考）

`acp_relay.py` 自动选择最优通信方式：

| 场景 | 方式 | 链接格式 | 延迟 |
|------|------|---------|------|
| 正常网络（双方 IP 互通） | WebSocket P2P 直连 | `acp://IP:PORT/TOKEN` | <100ms |
| 受限网络（沙箱/K8s/NAT） | HTTP 公共中继（降级） | `acp+wss://relay/TOKEN` | 1-3s |

发起方收到链接后直接发给对方即可，无需判断类型。

---

## 完整文档 & 源码

https://github.com/Kickflip73/agent-communication-protocol
