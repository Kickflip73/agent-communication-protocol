# ACP — Agent Communication Protocol

**任意两个 Agent 建立直接通信。零注册、零配置、框架无关。**

---

## 快速接入 SOP（Agent 必须严格按顺序执行）

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

### Step 3 — ⚡ 立即启动通信服务（最重要的一步）

**后台启动，并获取链接：**

```bash
python3 acp_relay.py --name "你的Agent名" &
sleep 3
curl -s http://localhost:7901/link
```

执行后会输出你的通信链接，例如：
```json
{"link": "acp://1.2.3.4:7801/tok_xxxxx"}
```

**⚠️ 必须：把这条链接回复给对方，等待对方连接。**

---

### Step 4 — 等待或加入连接

**如果你是被动接入方**（收到了对方的链接）：

```bash
python3 acp_relay.py --name "你的Agent名" --join "对方发来的链接" &
sleep 3
curl -s http://localhost:7901/status
```

状态返回 `"connected": true` 即连接成功。

---

### Step 5 — 收发消息

```bash
# 发消息给对方
curl -X POST http://localhost:7901/message:send \
  -H "Content-Type: application/json" \
  -d '{"text": "你好，连接已建立"}'

# 实时收消息（SSE 流）
curl http://localhost:7901/stream

# 一次性取收件箱（查看已收到的消息）
curl http://localhost:7901/inbox
```

---

## 完整接入流程示意

```
Agent A                          Agent B
  │                                │
  │ Step 3: 启动服务               │
  │ → 得到 acp://xxx/tok           │
  │                                │
  │ ──── 把链接发给 Agent B ──────► │
  │                                │ Step 4: --join "acp://xxx/tok"
  │                                │ → connected ✅
  │                                │
  │ ◄──────── 双向通信建立 ──────── │
  │                                │
  │ Step 5: send/stream            │ Step 5: send/stream
```

---

## 底层通信（Agent 无需关心）

`acp_relay.py` 自动选择最优方式：
- 正常网络 → **WebSocket P2P 直连**（零依赖，<100ms）
- 沙箱/K8s/NAT 受限 → **自动降级 HTTP 中继**（1-3s）

接口完全一致，Agent 无需感知底层。

---

## 常用参数

```
--name NAME      本 Agent 的名字（默认 ACP-Agent）
--port PORT      本地端口（默认 7801，HTTP 接口 = PORT+100 即 7901）
--join LINK      加入已有会话（填对方链接）
--relay          强制使用公共中继（仅在 P2P 无法连通时使用）
--skills LIST    逗号分隔的能力列表
```

---

## 完整文档 & 源码

https://github.com/Kickflip73/agent-communication-protocol
