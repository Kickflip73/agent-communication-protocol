# ACP — Agent Communication Protocol

**2步让任意两个 Agent 建立直接 P2P 通信。人只需传递两样东西：一个 Skill 地址，一个链接。**

---

## 人需要做的（仅2步）

```
Step 1  把这个地址发给 Agent A：
        https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/relay/SKILL.md

        Agent A 会自动安装服务并返回一个链接，例如：
        acp://1.2.3.4:7801/tok_abc123def456

Step 2  把这个链接发给 Agent B
        Agent B 会自动连接，返回"连接成功"
```

之后两个 Agent 即可直接 P2P 通信，无任何中间服务器。

---

## Agent 做的（全自动）

**Agent A 收到 Skill 地址后自动执行：**
1. 安装依赖（`pip install websockets`）
2. 下载 `acp_relay.py`
3. 启动本地 P2P 服务（监听端口 7801）
4. 探测 IP，生成 `acp://` 链接
5. 把链接返回给用户

**Agent B 收到链接后自动执行：**
1. 安装依赖
2. 下载 `acp_relay.py`
3. 解析链接，直接 TCP 连接到 Agent A
4. 返回"连接成功"

---

## 架构

```
Agent A                                      Agent B
  │                                             │
  │  POST /send  ←→  /tmp/acp_relay.py  ←───────→  /tmp/acp_relay.py  ←→  POST /send
  │  GET  /recv      (本地守护进程)      WebSocket     (本地守护进程)      GET  /recv
  │                  localhost:7901      直连，无中间人  localhost:7920
```

链接格式：`acp://<host>:<port>/<token>`
- `host` = 发起方的公网/局域网 IP（自动探测）
- `port` = WebSocket 监听端口
- `token` = 一次性随机 token，防止误连

---

## Skill 地址（直接发给任意 Agent）

```
https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/relay/SKILL.md
```

---

## 本地接口参考

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/send` | 发消息（任意 JSON） |
| `GET`  | `/recv` | 取消息（轮询） |
| `GET`  | `/status` | 连接状态 |
| `GET`  | `/link` | 获取本端 acp:// 链接 |

---

## 文件结构

```
relay/
├── SKILL.md       ← 发给 Agent 的 Skill（人只需发这一个地址）
└── acp_relay.py   ← 本地守护进程（Agent 自动下载，~350行，仅需 websockets）
```

---

## License

Apache 2.0 — https://github.com/Kickflip73/agent-communication-protocol
