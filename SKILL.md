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

### Step 6 — 收发消息

连接建立后，通过本地 HTTP 接口（默认 `localhost:7901`）收发消息：

```bash
# 发消息给对方
curl -s -X POST http://localhost:7901/message:send \
  -H "Content-Type: application/json" \
  -d '{"text": "你好，连接已建立"}'

# 实时收消息（SSE 流，阻塞监听）
curl -s http://localhost:7901/stream

# 一次性取收件箱（查所有已收消息）
curl -s http://localhost:7901/inbox

# 查询对方的 AgentCard（能力列表）
curl -s http://localhost:7901/status | python3 -c "import json,sys; print(json.load(sys.stdin).get('peer_card'))"
```

发消息成功返回：
```json
{"ok": true}
```

---

### Step 7 — 保持服务存活（心跳）

**每 30 秒执行一次，确保连接未断开：**

```bash
STATUS=$(curl -s http://localhost:7901/status)
CONNECTED=$(echo $STATUS | python3 -c "import json,sys; print(json.load(sys.stdin).get('connected', False))")

if [ "$CONNECTED" != "True" ]; then
  echo "连接断开，尝试重连..."
  # 如果有对方链接，重新 --join；否则重新启动
fi
```

若连接中断，直接重新执行 Step 3 或 Step 5 即可，`acp_relay.py` 会自动重试。

---

## 完整接入流程示意

```
Agent A（发起方）                     Agent B（接入方）
  │                                        │
  │ Step 3: python3 acp_relay.py           │
  │         &  →  得到 link               │
  │                                        │
  │ ──── 把 link 发给 Agent B ───────────► │
  │                                        │ Step 5: --join "<link>"
  │ Step 4: 轮询 /status                   │
  │         等待 connected: true           │
  │◄──────── 双向通道建立 ─────────────────│
  │                                        │
  │ Step 6: POST /message:send             │ Step 6: GET /stream 收消息
  │ Step 7: 心跳检查 /status               │ Step 7: 心跳检查 /status
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
