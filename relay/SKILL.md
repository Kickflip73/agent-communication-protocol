# ACP P2P 通信 Skill v0.2

**你是一个 AI Agent。收到这份 Skill 后，请立即按步骤执行，完成后向用户报告结果。**

---

## 第一步：判断角色

- 用户消息中**包含** `acp://` 链接 → **接收方**，执行接收方流程
- 用户消息中**不含** `acp://` 链接 → **发起方**，执行发起方流程

---

## 发起方流程

```bash
pip install websockets -q
curl -fsSL https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/relay/acp_relay.py -o /tmp/acp_relay.py
python3 /tmp/acp_relay.py --name "$(hostname)" --skills "your-skill-list" --port 7801 &
sleep 6
curl -s --noproxy "*" http://localhost:7901/link
```

返回 `{"link": "acp://x.x.x.x:7801/tok_xxx"}` → 把 `link` 值原样回复用户：

> ACP 通信服务已启动（v0.2）。
> 你的链接：`acp://x.x.x.x:7801/tok_xxx`
> 请将此链接发给对方 Agent。

---

## 接收方流程

将 `<LINK>` 替换为用户提供的 `acp://` 链接：

```bash
pip install websockets -q
curl -fsSL https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/relay/acp_relay.py -o /tmp/acp_relay.py
python3 /tmp/acp_relay.py --name "$(hostname)" --join <LINK> --port 7820 &
sleep 4
curl -s --noproxy "*" http://localhost:7920/status
curl -s --noproxy "*" http://localhost:7920/card
```

连接成功后回复用户：

> P2P 连接成功！对方信息：
> - 名称：[对方 AgentCard 中的 name]
> - 能力：[对方 AgentCard 中的 skills]
>
> 通信接口：
> - 发消息：`POST http://localhost:7920/send`
> - 收消息：`GET  http://localhost:7920/recv`

---

## 收发消息

```bash
# 发起方 port=7901，接收方 port=7920
curl -s --noproxy "*" -X POST http://localhost:<PORT>/send \
  -H "Content-Type: application/json" \
  -d '{"type": "task", "content": "消息内容"}'

curl -s --noproxy "*" http://localhost:<PORT>/recv
```

---

## 完整接口列表（v0.2 新增）

| 路径 | 说明 |
|------|------|
| `POST /send` | 发消息 |
| `GET /recv` | 取新消息 |
| `GET /status` | 连接状态 + 统计 |
| `GET /link` | 本端 acp:// 链接 |
| `GET /card` | 本端和对端 AgentCard（含能力列表）|
| `GET /history` | 完整消息历史 |
| `GET /stream` | SSE 流式消息订阅 |

---

*ACP P2P v0.2 | https://github.com/Kickflip73/agent-communication-protocol*
