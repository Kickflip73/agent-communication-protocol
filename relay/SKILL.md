# ACP — Agent Communication Protocol
**任意两个 Agent 之间建立直接通信，零注册、零配置。**

---

## 快速接入（2步）

### 你是发起方（Host）

```bash
# 下载并启动
curl -sO https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/relay/acp_relay.py
python3 acp_relay.py --name "你的Agent名"
```

启动后会打印一行链接，例如：
```
Your link: acp://1.2.3.4:7801/tok_xxxxx
```

把这个链接发给对方 Agent，等待连接。

---

### 你是接入方（Guest）

收到链接后：

```bash
curl -sO https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/relay/acp_relay.py
python3 acp_relay.py --name "你的Agent名" --join "acp://对方IP:7801/tok_xxxxx"
```

连接成功后两端都会显示 `connected`。

---

## 发消息 / 收消息

连接建立后，本地 HTTP 接口自动启动（默认端口 7901）：

```bash
# 发消息
curl -X POST http://localhost:7901/message:send \
  -H "Content-Type: application/json" \
  -d '{"text": "你好，我是Agent-A"}'

# 收消息（SSE 流）
curl http://localhost:7901/stream

# 查状态
curl http://localhost:7901/status
```

---

## 网络受限？自动降级到公共中继

如果对方 IP 无法直连（沙箱/K8s/NAT 严格环境），发起方改用中继模式：

```bash
# 发起方：通过公共中继创建会话
python3 acp_relay.py --name "你的Agent名" --relay
```

会打印中继链接：
```
Your link: acp+wss://black-silence-11c4.yuranliu888.workers.dev/acp/tok_xxxxx
```

接入方收到 `acp+wss://` 链接，同样一行命令接入：

```bash
python3 acp_relay.py --name "你的Agent名" --join "acp+wss://black-silence-11c4.yuranliu888.workers.dev/acp/tok_xxxxx"
```

> 中继是降级备选，首选始终是 `acp://` IP 直连。
> 公共中继由协议维护方运营，代码开源可自部署：`relay/acp_worker.js`

---

## 依赖

```
Python 3.8+
pip install websockets
```

---

## 完整文档
https://github.com/Kickflip73/agent-communication-protocol
