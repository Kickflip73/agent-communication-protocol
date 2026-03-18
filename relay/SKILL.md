---
name: acp-protocol
description: 帮助两个 Agent 建立一次 P2P 直连通信会话。适用场景：用户明确要求建立 agent-to-agent 连接、发送 acp:// 链接、或提到 ACP/agent直连/agent互联。每次调用仅完成一次连接建立，不自动持续运行。触发词: ACP, agent-to-agent, 让两个agent通信, p2p agent, 建立agent连接, acp relay, agent互联, agent直连.
---

# ACP P2P Communication Skill

> **范围**：本 Skill 仅完成**一次**连接建立，并向用户确认结果。后续通信由用户/Agent 按需发起，不自动持续执行。

---

## Step 1 — 判断角色（仅影响连接建立方式）

| 情况 | 角色 |
|------|------|
| 用户消息**不含** `acp://` 链接 | **发起方**：启动本地服务，生成连接链接 |
| 用户消息**含有** `acp://` 链接 | **加入方**：使用该链接连接到对方 |

连接建立后双方角色完全对称，均可收发消息。

---

## Step 2 — 安装依赖并启动（执行前需用户确认）

> ⚠️ 以下命令将在本地启动一个后台进程（占用一个端口），**请确认后再执行**。

```bash
pip install websockets -q

curl -fsSL \
  https://raw.githubusercontent.com/Kickflip73/agent-communication-protocol/main/relay/acp_relay.py \
  -o /tmp/acp_relay.py
```

**如果是发起方**，执行后等待链接生成：
```bash
# MY_NAME 替换为本 Agent 名称，MY_SKILLS 替换为能力列表（逗号分隔）
python3 /tmp/acp_relay.py --name "MY_NAME" --skills "MY_SKILLS" --port 7801 &
sleep 8
ACP_LINK=$(curl -s --noproxy "*" http://localhost:7901/link \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['link'])")
echo "ACP_LINK=$ACP_LINK"
```

向用户回复（必须包含实际链接值）：
> ✅ 服务已启动。🔗 连接链接：`<ACP_LINK>`
> 请将此链接转发给对方 Agent 即可完成连接。

---

**如果是加入方**，将 `<LINK>` 替换为用户提供的 acp:// 链接：
```bash
# MY_NAME 替换为本 Agent 名称，MY_SKILLS 替换为能力列表（逗号分隔）
python3 /tmp/acp_relay.py --name "MY_NAME" --skills "MY_SKILLS" --join <LINK> --port 7820 &
sleep 5
curl -s --noproxy "*" http://localhost:7920/card \
  | python3 -c "
import json,sys
d=json.load(sys.stdin)
p=d.get('peer') or {}
print('PEER_NAME=' + str(p.get('name','unknown')))
print('PEER_SKILLS=' + str(p.get('skills',[])))
"
```

向用户回复（填入实际的 PEER_NAME 和 PEER_SKILLS）：
> ✅ 已连接。🤝 对方：`<PEER_NAME>` | 能力：`<PEER_SKILLS>`
> 双向通道已就绪，可按需收发消息。

---

## Step 3 — 按需收发消息（用户主动调用，非自动循环）

连接建立后，每次发送/接收均由用户或 Agent 显式触发，**不会自动轮询或持续运行**。

默认端口：发起方 HTTP=`7901`，加入方 HTTP=`7920`（规则：HTTP 端口 = WS 端口 + 100）。

```bash
# 发送一条消息（单次调用）
curl -s --noproxy "*" -X POST http://localhost:<HTTP_PORT>/send \
  -H "Content-Type: application/json" \
  -d '{"type":"message","content":"Hello!"}'

# 读取已收到的消息（单次调用，limit 控制最大条数）
curl -s --noproxy "*" "http://localhost:<HTTP_PORT>/recv?limit=10"
```

如需同步回复、异步任务、SSE 流式、Push Webhook 等高级模式，参见 [`references/modes.md`](references/modes.md)。

---

## 终止服务

完成通信后，可随时停止后台进程释放端口：

```bash
# 查找并终止 acp_relay.py 进程
pkill -f acp_relay.py
```

---

## CLI 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--name` | `ACP-Agent` | Agent 显示名称 |
| `--join` | — | 要连接的 `acp://` 链接（不填 = 发起方） |
| `--port` | `7801` | WebSocket 端口；HTTP 端口 = 此值 + 100 |
| `--skills` | — | 能力列表（逗号分隔） |
| `--inbox` | `/tmp/acp_inbox_<name>.jsonl` | 消息持久化文件路径 |

---

*ACP P2P v0.3 · https://github.com/Kickflip73/agent-communication-protocol*
