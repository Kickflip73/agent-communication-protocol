# ACP P2P 通信 Skill

**你是一个 AI Agent。收到这份 Skill 后，请立即按步骤执行，完成后向用户报告结果。**

---

## 第一步：判断角色

- 如果用户消息中**包含** `acp://` 开头的链接 → 你是**接收方**，执行「接收方流程」
- 如果用户消息中**不包含** `acp://` 链接 → 你是**发起方**，执行「发起方流程」

---

## 发起方流程

依次执行以下命令：

```bash
pip install websockets -q
```

```bash
curl -fsSL https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/relay/acp_relay.py -o /tmp/acp_relay.py
```

```bash
python3 /tmp/acp_relay.py --name "AgentA" --port 7801 &
```

```bash
sleep 6
```

```bash
curl -s --noproxy "*" http://localhost:7901/link
```

最后一条命令会返回类似：
```json
{"link": "acp://1.2.3.4:7801/tok_abc123"}
```

**向用户报告：** 把 `link` 字段的值原样回复给用户，格式如下：

> ACP 通信服务已启动。你的链接：`acp://1.2.3.4:7801/tok_abc123`
> 请将此链接发送给对方 Agent。

---

## 接收方流程

从用户消息中提取 `acp://` 链接，记为 `LINK`。

依次执行以下命令（将 `LINK` 替换为实际链接）：

```bash
pip install websockets -q
```

```bash
curl -fsSL https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/relay/acp_relay.py -o /tmp/acp_relay.py
```

```bash
python3 /tmp/acp_relay.py --name "AgentB" --join LINK --port 7820 &
```

```bash
sleep 4
```

```bash
curl -s --noproxy "*" http://localhost:7920/status
```

如果返回 `"connected": true`，**向用户报告：**

> P2P 连接成功！现在可以通过以下接口收发消息：
> - 发消息：`POST http://localhost:7920/send`（JSON body）
> - 收消息：`GET  http://localhost:7920/recv`

---

## 收发消息

连接建立后，通过本地 HTTP 接口通信：

```bash
# 发消息
curl -s --noproxy "*" -X POST http://localhost:<PORT>/send \
  -H "Content-Type: application/json" \
  -d '{"type": "chat", "text": "消息内容"}'

# 收消息
curl -s --noproxy "*" http://localhost:<PORT>/recv
```

- 发起方 PORT = `7901`
- 接收方 PORT = `7920`

---

*ACP — Agent Communication Protocol | https://github.com/Kickflip73/agent-communication-protocol*
