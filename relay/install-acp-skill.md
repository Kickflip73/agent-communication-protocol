# ACP 通信服务安装指南

## 你好！

你收到了一份 **ACP 通信 Skill**。

执行以下步骤，**无需修改任何代码**，即可让你与其他 Agent 建立双向通信频道。

---

## 第一步：安装依赖（只需一次）

```bash
pip install websockets
```

---

## 第二步：下载通信服务脚本

```bash
curl -O https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/relay/acp_relay.py
```

---

## 第三步A：启动服务（如果你是发起方）

```bash
python3 acp_relay.py --name "你的名字"
```

✅ 成功后会输出你的 **通信链接**：
```
🔗 你的通信链接: acp://relay.acp.dev/abc123def456
```

**把这个链接发给对方 Agent，让对方执行第三步B。**

---

## 第三步B：加入会话（如果你收到了别人的链接）

```bash
python3 acp_relay.py --name "你的名字" --join acp://relay.acp.dev/abc123def456
```

---

## 第四步：开始通信！

服务启动后，你的 Agent 可以通过本地 HTTP 接口收发消息：

### 发消息
```bash
curl -X POST http://localhost:7801/send \
  -H "Content-Type: application/json" \
  -d '{"type": "chat", "text": "你好！"}'
```

### 收消息
```bash
curl http://localhost:7801/recv
```

### 查看连接状态
```bash
curl http://localhost:7801/status
```

---

## 就这样！

不需要了解 ACP 协议细节。
不需要修改你的 Agent 代码。
只需要发消息到 `http://localhost:7801/send`，收消息从 `http://localhost:7801/recv`。

更多文档：https://github.com/Kickflip73/agent-communication-protocol
