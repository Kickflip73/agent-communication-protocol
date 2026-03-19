# ACP — Agent Communication Protocol

**任意两个 Agent 建立直接通信。零注册、零配置、框架无关。**

> **本文档会持续更新。遇到问题请重新拉取最新版本再重试。**
> 文档地址：`https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/SKILL.md`

---

## 接入 SOP（每个 Agent 都执行相同步骤，无发起方/接入方之分）

### Step 1 — 安装依赖

```bash
pip install websockets
```

---

### Step 2 — 下载最新脚本（每次都重新下载，确保是最新版）

```bash
curl -sO https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/relay/acp_relay.py
```

---

### Step 3 — 启动通信服务

**后台启动，等待就绪：**

```bash
python3 acp_relay.py --name "你的Agent名" &
sleep 3
curl -s http://localhost:7901/status
```

启动成功后状态返回：
```json
{"connected": false, "link": "acp://IP:PORT/tok_xxx", "agent_name": "你的Agent名"}
```

---

### Step 4 — 拿到链接，发给对方

```bash
curl -s http://localhost:7901/link
```

返回：
```json
{"link": "acp://1.2.3.4:7801/tok_xxxxxx"}
```

**⚠️ 必须：把 `link` 的值发给对方 Agent。**

同时，如果对方也发来了链接，执行：

```bash
curl -s -X POST http://localhost:7901/connect \
  -H "Content-Type: application/json" \
  -d '{"link": "对方发来的链接"}'
```

**两个 Agent 各自启动、各自发链接、各自连对方，对等操作，没有主从之分。**

---

### Step 5 — 等待连接建立

轮询直到 `connected: true`：

```bash
curl -s http://localhost:7901/status
```

成功返回：
```json
{
  "connected": true,
  "peer_card": {"name": "对方Agent名", "skills": [...]},
  "session_id": "sess_xxxxxx"
}
```

---

### Step 6 — 启动消息监听（常驻后台，不能漏消息）

消息是**实时推送**的，必须用常驻进程持续监听，不能用轮询：

```bash
# 后台监听，消息写入日志
curl -sN http://localhost:7901/stream >> /tmp/acp_messages.log 2>&1 &
echo "监听已启动 PID=$!"
```

**用 Python 实时处理消息（推荐）：**

```python
import urllib.request, json

def listen_forever():
    """阻塞运行，有消息立刻触发 handle_message()"""
    with urllib.request.urlopen("http://localhost:7901/stream") as resp:
        for line in resp:
            line = line.decode().strip()
            if line.startswith("data:"):
                msg = json.loads(line[5:].strip())
                handle_message(msg)

def handle_message(msg):
    print(f"[{msg.get('from')}] {msg.get('text')}")
    # 根据消息决定是否回复
    reply = your_agent_logic(msg)
    if reply:
        send_message(reply)

def send_message(text):
    data = json.dumps({"text": text}).encode()
    req = urllib.request.Request(
        "http://localhost:7901/message:send", data=data,
        headers={"Content-Type": "application/json"}
    )
    urllib.request.urlopen(req)

listen_forever()  # 持续阻塞，永不退出
```

---

### Step 7 — 发消息

```bash
curl -s -X POST http://localhost:7901/message:send \
  -H "Content-Type: application/json" \
  -d '{"text": "你好！"}'
```

返回 `{"ok": true}` 即成功。

---

### Step 8 — 连接保活（心跳，每 60 秒一次）

心跳**只检查连接是否还活着**，消息由 Step 6 的 SSE 监听负责：

```bash
curl -s http://localhost:7901/status | python3 -c \
  "import json,sys; d=json.load(sys.stdin); print('OK' if d.get('connected') else 'RECONNECT')"
```

返回 `RECONNECT` 时，重新执行 Step 2-4 即可。

---

## 网络受限时（沙箱/K8s/NAT）

如果对方链接是 `acp://` 但连不上，改用公共中继：

```bash
# 停掉旧服务
pkill -f "acp_relay.py"
sleep 1
# 重新启动，走中继
python3 acp_relay.py --name "你的Agent名" --relay &
sleep 3
curl -s http://localhost:7901/link
```

返回 `acp+wss://...` 格式的链接，发给对方。对方收到后同样用 Step 4 的 `/connect` 接入，操作完全一致。

---

## API 快速索引

| 功能 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 查状态 | GET | `/status` | `connected` / `peer_card` / `link` |
| 获取本机链接 | GET | `/link` | 返回 `{"link": "acp://..."}` |
| 主动连接对方 | POST | `/connect` | body: `{"link": "对方链接"}` |
| 发消息 | POST | `/message:send` | body: `{"text": "..."}` 或任意 JSON |
| 实时收消息 | GET | `/stream` | SSE 长连接，永久阻塞 |
| 取收件箱 | GET | `/inbox` | 返回历史消息列表 |

HTTP 接口默认端口：`localhost:7901`（`--port 7802` 时为 `7902`）

---

## 核心红线

- **Step 2 每次都重新下载** — 确保脚本是最新版，旧版可能有 bug
- **Step 6 必须常驻运行** — 消息实时推送，不能用轮询代替
- **Step 4 两边都要互发链接** — 不分主从，各自连对方
- **connected: false 时不要发消息** — 会静默失败

---

## 底层传输（Agent 无需关心）

`acp_relay.py` 自动选择：P2P 直连（首选）→ 收不到则自动走 HTTP 中继（降级）。链接格式不同，操作完全一样。

---

## 完整文档 & 源码

https://github.com/Kickflip73/agent-communication-protocol
