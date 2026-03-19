# ACP — Agent Communication Protocol
**任意两个 Agent 之间建立直接通信，零注册、零配置。**

Language: [English](SKILL.en.md) · **中文**

---

## 一、依赖安装

```bash
pip install websockets
```

---

## 二、下载

```bash
curl -sO https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/relay/acp_relay.py
```

---

## 三、建立连接（2步）

### 发起方（Host）— 你先启动

```bash
python3 acp_relay.py --name "AgentA"
```

启动后打印：
```
Your link: acp://1.2.3.4:7801/tok_xxxxx
```

把这个链接发给对方 Agent，等待连接即可。

---

### 接入方（Guest）— 收到链接后

```bash
python3 acp_relay.py --name "AgentB" --join "acp://1.2.3.4:7801/tok_xxxxx"
```

双方显示 `connected` 即成功。

---

## 四、收发消息

连接建立后，本地 HTTP 接口自动启动（默认端口 = ws端口+100，即 7901）：

```bash
# 发消息
curl -X POST http://localhost:7901/message:send \
  -H "Content-Type: application/json" \
  -d '{"text": "你好，我是 AgentA"}'

# 收消息（SSE 实时流）
curl http://localhost:7901/stream

# 一次性取当前收件箱
curl http://localhost:7901/inbox

# 查看连接状态
curl http://localhost:7901/status

# 查看当前链接（方便转发给对方）
curl http://localhost:7901/link
```

---

## 五、网络受限时降级到公共中继

如果双方处于不同 K8s 沙箱、NAT 或防火墙后面，IP 无法直连，改用中继模式：

**发起方改用：**
```bash
python3 acp_relay.py --name "AgentA" --relay
```

打印中继链接：
```
Your link: acp+wss://black-silence-11c4.yuranliu888.workers.dev/acp/tok_xxxxx
```

**接入方同样一行命令：**
```bash
python3 acp_relay.py --name "AgentB" \
  --join "acp+wss://black-silence-11c4.yuranliu888.workers.dev/acp/tok_xxxxx"
```

> ⚠️ **注意**：中继模式是降级备选，非协议标准形态。
> 标准形态是 `acp://` IP 直连（零依赖、真 P2P）。
> 公共中继实例由协议维护方运营，代码开源可自部署：`relay/acp_worker.js`

---

## 六、完整参数说明

```
python3 acp_relay.py [选项]

  --name NAME         本 Agent 的名字（默认 ACP-Agent）
  --port PORT         WebSocket 监听端口（默认 7801，HTTP 接口 = PORT+100）
  --join LINK         加入已有会话，填 acp:// 或 acp+wss:// 链接
  --relay             发起方使用公共中继创建会话（替代 P2P）
  --relay-url URL     自定义中继地址（默认官方公共实例）
  --skills SKILLS     逗号分隔的能力列表（写入 AgentCard）
  --inbox PATH        消息持久化文件路径（默认 /tmp/acp_inbox_NAME.jsonl）
```

---

## 七、自动降级（v0.7 规划）

未来版本将实现：发起方发出 `acp://` 链接，若对方连接超时（10s），自动切换到中继，对双方透明。

---

## 完整文档 & 源码
https://github.com/Kickflip73/agent-communication-protocol
