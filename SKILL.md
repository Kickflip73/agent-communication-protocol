# ACP — Agent Communication Protocol

**任意两个 Agent 建立直接通信。零注册、零配置、框架无关。**

---

## 一、安装依赖

```bash
pip install websockets
```

---

## 二、下载

```bash
curl -sO https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/relay/acp_relay.py
```

---

## 三、建立连接

### 发起方

```bash
python3 acp_relay.py --name "AgentA"
```

打印一条链接，例如：
```
Your link: acp://1.2.3.4:7801/tok_xxxxx
```

把这条链接发给对方 Agent。

---

### 接入方

收到链接后，无论链接是 `acp://` 还是 `acp+wss://`，命令完全一样：

```bash
python3 acp_relay.py --name "AgentB" --join "<对方发来的链接>"
```

双方显示 `connected` 即成功。**不需要关心链接格式，通信层自动处理。**

---

## 四、收发消息

连接成功后，本地 HTTP 接口自动在 `PORT+100`（默认 7901）启动：

```bash
# 发消息
curl -X POST http://localhost:7901/message:send \
  -H "Content-Type: application/json" \
  -d '{"text": "你好"}'

# 实时收消息（SSE 流，推荐）
curl http://localhost:7901/stream

# 一次性取收件箱
curl http://localhost:7901/inbox

# 查连接状态
curl http://localhost:7901/status

# 查当前链接（转发给对方用）
curl http://localhost:7901/link
```

---

## 五、常用参数

```
--name NAME      本 Agent 的名字（默认 ACP-Agent）
--port PORT      本地端口（默认 7801，HTTP = PORT+100）
--join LINK      加入已有会话（填对方发来的链接）
--skills LIST    逗号分隔的能力列表，写入 AgentCard
--inbox PATH     消息持久化路径（默认 /tmp/acp_inbox_NAME.jsonl）
```

---

## 六、底层通信（Agent 无需关心）

`acp_relay.py` 内部自动选择最优通信方式：

- 正常网络 → **WebSocket P2P 直连**（零依赖，延迟 <100ms）
- 沙箱/K8s/NAT 等受限网络 → **自动降级到 HTTP 公共中继**（延迟 1-3s）

对 Agent 来说，接口完全一致，链接格式由发起方决定，接入方无需做任何判断。

---

## 完整文档 & 源码

https://github.com/Kickflip73/agent-communication-protocol
