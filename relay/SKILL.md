---
name: acp-protocol
description: 帮助两个 Agent 建立 P2P 直连通信会话，并完成可观测的消息收发验证。适用场景：用户要求建立 agent-to-agent 连接、发送 acp:// 链接、提到 ACP/agent直连/agent互联。触发词：ACP, agent-to-agent, 让两个agent通信, p2p agent, 建立agent连接, acp relay, agent互联, agent直连.
---

# ACP P2P Communication Skill v0.5

> **目标**：完成连接建立 + 发送一条测试消息 + 确认对方收到，形成可观测的闭环。
> 不只是"启动进程"——必须验证双方真的能互发消息。

---

## 快速流程图

```
没有 acp:// 链接？              有 acp:// 链接？
      ↓                               ↓
  [发起方]                         [加入方]
  启动服务                         连接服务
  获取链接 → 发给对方              确认已连接
      ↓                               ↓
  等待对方连接                    [双方都执行]
      ↓                         发送测试消息
  [双方都执行]                    读取收件箱
  确认通道可用                    ✅ 验证成功
```

---

## Step 1 — 安装依赖 & 下载

```bash
pip install websockets -q

curl -fsSL \
  https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/relay/acp_relay.py \
  -o /tmp/acp_relay.py
```

---

## Step 2A — 发起方（无 acp:// 链接时）

```bash
# 替换 MY_NAME 为你的 Agent 名称，MY_SKILLS 为能力列表（逗号分隔）
python3 /tmp/acp_relay.py --name "MY_NAME" --skills "MY_SKILLS" --port 7801 &
sleep 8

# 获取连接链接
ACP_LINK=$(curl -s --noproxy "*" http://localhost:7901/link \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['link'])")
echo "🔗 ACP_LINK=$ACP_LINK"
```

**必须回复用户**（填入实际链接）：
> ✅ 服务已启动。
> 🔗 连接链接：`<ACP_LINK>`
> 请将此链接发给对方 Agent，对方运行 Step 2B 即可完成连接。

---

## Step 2B — 加入方（有 acp:// 链接时）

```bash
# 将 <LINK> 替换为用户提供的 acp:// 链接
python3 /tmp/acp_relay.py --name "MY_NAME" --skills "MY_SKILLS" --join <LINK> --port 7820 &
sleep 6

# 检查是否已连接 + 获取对方信息
curl -s --noproxy "*" http://localhost:7920/status \
  | python3 -c "
import json,sys
d=json.load(sys.stdin)
print('connected=', d.get('connected'))
peer=d.get('peer_card') or {}
print('peer_name=', peer.get('name','(等待中...)'))
print('peer_skills=', [s['id'] for s in peer.get('skills',[])])
"
```

**必须回复用户**（填入实际值）：
> ✅ 已连接。
> 🤝 对方：`<PEER_NAME>` | 能力：`<PEER_SKILLS>`
> 双向通道就绪，正在发送测试消息验证...

---

## Step 3 — 验证通道（双方都要做，形成可观测闭环）

连接建立后，立即发一条测试消息并确认对方能收到。

### 3A. 发送测试消息

```bash
# HTTP_PORT: 发起方=7901, 加入方=7920
curl -s --noproxy "*" -X POST http://localhost:<HTTP_PORT>/message:send \
  -H "Content-Type: application/json" \
  -d '{
    "parts": [{"type": "text", "content": "ACP 通道验证 👋 来自 <MY_NAME>"}],
    "role": "user"
  }' \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print('sent:', d.get('ok'), '| msg_id:', d.get('message_id','')[:12])"
```

### 3B. 读取收件箱（确认对方消息到达）

```bash
curl -s --noproxy "*" "http://localhost:<HTTP_PORT>/recv?limit=5" \
  | python3 -c "
import json,sys
d=json.load(sys.stdin)
msgs=d.get('messages',[])
print('收到消息数:', len(msgs))
for m in msgs:
    parts=m.get('parts',[])
    for p in parts:
        if p.get('type')=='text':
            print('  >', p.get('content','')[:80])
"
```

**✅ 验证通过的标志**：双方都能在收件箱里看到对方发的消息。

**必须回复用户**（填入实际结果）：
> ✅ 通道验证完成。
> 📨 已发送：`<发送结果>`
> 📬 已收到：`<收件箱内容摘要>`
> P2P 双向通道正常工作。

---

## Step 4 — 日常收发消息

通道验证后，按需收发。

### 发消息

```bash
curl -s --noproxy "*" -X POST http://localhost:<HTTP_PORT>/message:send \
  -H "Content-Type: application/json" \
  -d '{"parts": [{"type": "text", "content": "你的消息内容"}]}'
```

### 收消息

```bash
# 读取并清空队列（每次调用返回新消息）
curl -s --noproxy "*" "http://localhost:<HTTP_PORT>/recv?limit=10" \
  | python3 -c "
import json,sys
d=json.load(sys.stdin)
for m in d.get('messages',[]):
    for p in m.get('parts',[]):
        if p.get('type')=='text': print('[收]', p['content'][:100])
print('剩余:', d.get('remaining',0))
"
```

### 实时流式监听（SSE）

```bash
# 保持连接，实时推送新消息/任务状态
curl -s --noproxy "*" -N http://localhost:<HTTP_PORT>/stream
```

---

## Step 5 — 查看连接状态 & 对方信息

```bash
# 查连接状态 + 对方 AgentCard
curl -s --noproxy "*" http://localhost:<HTTP_PORT>/.well-known/acp.json \
  | python3 -c "
import json,sys
d=json.load(sys.stdin)
me=d.get('self',{})
peer=d.get('peer') or {}
print('=== 本方 ===')
print('name:', me.get('name'))
print('skills:', [s['id'] for s in me.get('skills',[])])
print('=== 对方 ===')
print('name:', peer.get('name','(未连接)'))
print('skills:', [s['id'] for s in peer.get('skills',[])])
caps=peer.get('capabilities',{})
print('capabilities:', caps)
"
```

---

## 常见问题排查

| 现象 | 原因 | 解决方法 |
|------|------|---------|
| `connected: false`（加入方） | 对方未启动 / 链接错误 / 防火墙 | 确认发起方已运行且链接正确 |
| `/recv` 返回空 `messages: []` | 消息还未到达 / 已被读走 | 再等 2s 重试；消息读取后从队列移除 |
| `Connection refused` on port | 进程未启动 / 端口占用 | `ps aux | grep acp_relay`；换 `--port` |
| 发送返回 `503` | P2P 通道未就绪 | 等待 `connected: true` 后再发 |
| 加入方收不到消息 | HTTP 端口用错 | 加入方 HTTP = WS端口+100，默认 `7920` |

---

## 端口规则

| 角色 | WS 端口 | HTTP 端口 |
|------|---------|----------|
| 发起方（默认） | 7801 | 7901 |
| 加入方（默认） | 7820 | 7920 |
| 规则 | `--port P` | `P + 100` |

---

## 终止服务

```bash
pkill -f acp_relay.py
# 或精确终止特定端口
kill $(lsof -ti:7901) 2>/dev/null
kill $(lsof -ti:7920) 2>/dev/null
```

---

## CLI 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--name` | `ACP-Agent` | Agent 显示名称 |
| `--skills` | — | 能力列表（逗号分隔，展示在 AgentCard） |
| `--join` | — | 要连接的 `acp://` 链接（不填 = 发起方） |
| `--port` | `7801` | WebSocket 端口；HTTP 端口自动 = 此值 + 100 |
| `--inbox` | `/tmp/acp_inbox_<name>.jsonl` | 消息持久化路径 |
| `--max-msg-size` | `1048576` | 最大消息体积（字节） |

---

## HTTP API 快速索引

| 功能 | 方法 | 路径 |
|------|------|------|
| 发消息（主端点） | POST | `/message:send` |
| 读收件箱（并出队） | GET | `/recv?limit=N` |
| 实时流（SSE） | GET | `/stream` |
| AgentCard（本方+对方） | GET | `/.well-known/acp.json` |
| 连接状态 | GET | `/status` |
| 获取链接 | GET | `/link` |
| 任务列表 | GET | `/tasks` |
| 创建任务 | POST | `/tasks` |
| 更新任务 | POST | `/tasks/{id}/update` |
| 恢复中断任务 | POST | `/tasks/{id}/continue` |
| 取消任务 | POST | `/tasks/{id}:cancel` |
| 注册推送 Webhook | POST | `/webhooks/register` |
| 历史记录 | GET | `/history` |

---

## 消息格式（v0.5 Parts 模型）

```json
{
  "parts": [
    {"type": "text",  "content": "文字内容"},
    {"type": "file",  "url": "https://...", "media_type": "image/png", "filename": "图片.png"},
    {"type": "data",  "content": {"key": "任意JSON"}}
  ],
  "role": "user",
  "message_id": "可选，客户端生成用于去重",
  "task_id": "可选，关联到某个任务"
}
```

---

*ACP P2P v0.5 · [GitHub](https://github.com/Kickflip73/agent-communication-protocol)*
