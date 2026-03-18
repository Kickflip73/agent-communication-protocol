#!/usr/bin/env python3
"""
ACP Local Relay — Agent 侧守护进程
====================================
这是 Agent 安装 ACP 后在本地运行的服务。
Agent 不需要懂任何 ACP 协议，只需要：
  - POST http://localhost:7801/send   发消息
  - GET  http://localhost:7801/recv   收消息（轮询）
  - GET  http://localhost:7801/status 查看连接状态

用法：
  # 创建新会话（成为发起方）：
  python3 acp_relay.py --name "我的Agent"
  # 输出: 🔗 你的通信链接: acp://relay.acp.dev/abc123def456
  #       分享这个链接给对方，让他们用 --join 连接你

  # 加入已有会话（成为接收方）：
  python3 acp_relay.py --name "另一个Agent" --join acp://relay.acp.dev/abc123def456

依赖: pip install websockets  (仅需这一个)
"""
import asyncio
import json
import uuid
import time
import argparse
import logging
import threading
import signal
import sys
from collections import deque
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

try:
    import websockets
except ImportError:
    print("❌ 缺少依赖: pip install websockets")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [acp-relay] %(message)s")
log = logging.getLogger("acp-relay")

# ── 公共中继服务器地址（可通过 --relay 参数覆盖）──────────────────────────────
DEFAULT_RELAY_WS = "ws://relay.acp.dev:7800"
# ─────────────────────────────────────────────────────────────────────────────

# 全局状态
_recv_queue: deque = deque(maxlen=1000)   # 收到的消息队列
_status: dict = {
    "connected": False,
    "session_id": None,
    "peer_id": None,
    "peer_count": 0,
    "link": None,
    "agent_name": None,
    "relay_url": None,
    "started_at": None,
    "messages_sent": 0,
    "messages_received": 0,
}
_ws_global = None   # 当前 WebSocket 连接
_loop = None        # asyncio event loop


def make_id() -> str:
    return "msg_" + uuid.uuid4().hex[:12]


# ══════════════════════════════════════════════════════════════════════════════
# WebSocket 客户端（连接到中继服务器）
# ══════════════════════════════════════════════════════════════════════════════

async def ws_client(relay_ws: str, agent_name: str, join_session_id: str | None):
    global _ws_global

    uri = relay_ws
    log.info(f"连接到中继服务器: {uri}")

    async with websockets.connect(uri, ping_interval=20, ping_timeout=10) as ws:
        _ws_global = ws

        # Step 1: 创建或加入会话
        if join_session_id:
            init_msg = {"action": "join", "session_id": join_session_id, "agent_name": agent_name}
        else:
            init_msg = {"action": "create", "agent_name": agent_name}

        await ws.send(json.dumps(init_msg))
        resp = json.loads(await ws.recv())

        if resp.get("type") == "error":
            log.error(f"❌ 加入失败: {resp.get('message')}")
            _status["connected"] = False
            return

        if resp.get("type") in ("session.created", "session.joined"):
            _status["connected"]   = True
            _status["session_id"]  = resp["session_id"]
            _status["peer_id"]     = resp["peer_id"]
            _status["peer_count"]  = resp.get("peer_count", 1)
            _status["agent_name"]  = agent_name
            _status["relay_url"]   = relay_ws
            _status["started_at"]  = time.time()

            if resp.get("type") == "session.created":
                link = f"acp://{urlparse(relay_ws).netloc}/{resp['session_id']}"
                _status["link"] = link
                print(f"\n{'='*60}")
                print(f"✅ ACP 通信服务已启动！")
                print(f"")
                print(f"🔗 你的通信链接:")
                print(f"   {link}")
                print(f"")
                print(f"📋 把这个链接发给对方 Agent，让对方执行:")
                print(f"   python3 acp_relay.py --name \"对方名称\" --join {link}")
                print(f"")
                print(f"📡 本地 HTTP 接口 (Agent 用这个发消息/收消息):")
                print(f"   POST http://localhost:{_status.get('local_port', 7801)}/send")
                print(f"   GET  http://localhost:{_status.get('local_port', 7801)}/recv")
                print(f"   GET  http://localhost:{_status.get('local_port', 7801)}/status")
                print(f"{'='*60}\n")
            else:
                print(f"\n{'='*60}")
                print(f"✅ 已成功加入会话！")
                print(f"   会话 ID : {resp['session_id']}")
                print(f"   当前在线: {resp.get('peer_count', '?')} 个 Agent")
                print(f"")
                print(f"📡 本地 HTTP 接口 (Agent 用这个发消息/收消息):")
                print(f"   POST http://localhost:{_status.get('local_port', 7801)}/send")
                print(f"   GET  http://localhost:{_status.get('local_port', 7801)}/recv")
                print(f"   GET  http://localhost:{_status.get('local_port', 7801)}/status")
                print(f"{'='*60}\n")

        # Step 2: 持续接收消息
        async for raw in ws:
            try:
                msg = json.loads(raw)
                msg_type = msg.get("type", "")

                if msg_type == "peer.joined":
                    _status["peer_count"] = msg.get("peer_count", _status["peer_count"])
                    log.info(f"✅ 新 Agent 加入会话 (共 {_status['peer_count']} 个)")

                elif msg_type == "peer.left":
                    _status["peer_count"] = msg.get("peer_count", _status["peer_count"])
                    log.info(f"⚠️  Agent 离开会话 (剩余 {_status['peer_count']} 个)")

                else:
                    # 普通消息，放入队列
                    _recv_queue.append({
                        "id": msg.get("id", make_id()),
                        "received_at": time.time(),
                        "content": msg,
                    })
                    _status["messages_received"] += 1
                    log.info(f"📨 收到消息: type={msg.get('type', 'unknown')}")

            except json.JSONDecodeError:
                log.warning(f"收到非 JSON 消息，已忽略")


async def send_message(msg: dict):
    """通过 WebSocket 发送消息到中继服务器。"""
    global _ws_global
    if _ws_global is None or not _status["connected"]:
        raise ConnectionError("未连接到 ACP 会话，请先启动 relay")
    await _ws_global.send(json.dumps(msg))
    _status["messages_sent"] += 1


def send_sync(msg: dict):
    """同步版本的 send，供 HTTP handler 调用。"""
    if _loop is None:
        raise RuntimeError("Event loop not ready")
    future = asyncio.run_coroutine_threadsafe(send_message(msg), _loop)
    future.result(timeout=10)


# ══════════════════════════════════════════════════════════════════════════════
# 本地 HTTP 服务（Agent 调用这里发消息/收消息）
# ══════════════════════════════════════════════════════════════════════════════

class ACPHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # 静默 HTTP 日志

    def _json_response(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/status":
            self._json_response(_status)

        elif path == "/recv":
            # 返回所有待读消息，然后清空
            qs = parse_qs(urlparse(self.path).query)
            limit = int(qs.get("limit", ["50"])[0])
            msgs = []
            for _ in range(min(limit, len(_recv_queue))):
                if _recv_queue:
                    msgs.append(_recv_queue.popleft())
            self._json_response({
                "messages": msgs,
                "count": len(msgs),
                "remaining": len(_recv_queue),
            })

        elif path == "/link":
            self._json_response({"link": _status.get("link"), "session_id": _status.get("session_id")})

        else:
            self._json_response({"error": "unknown path"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/send":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b"{}"
            try:
                msg = json.loads(body)
                # 自动填充必要字段
                if "id" not in msg:
                    msg["id"] = make_id()
                if "ts" not in msg:
                    import datetime
                    msg["ts"] = datetime.datetime.utcnow().isoformat() + "Z"
                if "from" not in msg:
                    msg["from"] = _status.get("agent_name", "unknown")
                send_sync(msg)
                self._json_response({"ok": True, "id": msg["id"]})
            except ConnectionError as e:
                self._json_response({"ok": False, "error": str(e)}, 503)
            except Exception as e:
                self._json_response({"ok": False, "error": str(e)}, 500)

        else:
            self._json_response({"error": "unknown path"}, 404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


def run_http_server(port: int):
    server = HTTPServer(("127.0.0.1", port), ACPHandler)
    log.info(f"本地 HTTP 接口启动在 http://127.0.0.1:{port}")
    server.serve_forever()


# ══════════════════════════════════════════════════════════════════════════════
# 主入口
# ══════════════════════════════════════════════════════════════════════════════

def parse_link(link: str) -> tuple[str, str]:
    """
    解析 acp:// 链接，返回 (relay_ws_url, session_id)
    acp://relay.acp.dev:7800/abc123  →  ('ws://relay.acp.dev:7800', 'abc123')
    acp://relay.acp.dev/abc123       →  ('ws://relay.acp.dev:7800', 'abc123')
    """
    parsed = urlparse(link)
    host   = parsed.netloc or parsed.path.split("/")[0]
    path   = parsed.path.lstrip("/")
    if ":" not in host:
        host = host + ":7800"
    ws_url = f"ws://{host}"
    session_id = path
    return ws_url, session_id


def main():
    global _loop, _status

    parser = argparse.ArgumentParser(
        description="ACP Local Relay — 让 Agent 无需改代码即可互相通信",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # Agent A：创建会话
  python3 acp_relay.py --name "Agent-A"
  # → 输出: 🔗 你的通信链接: acp://relay.acp.dev/abc123def456

  # Agent B：加入会话
  python3 acp_relay.py --name "Agent-B" --join acp://relay.acp.dev/abc123def456

  # 发消息（Agent 调用）：
  curl -X POST http://localhost:7801/send -H "Content-Type: application/json" \\
       -d '{"type": "chat", "text": "你好！"}'

  # 收消息（Agent 调用）：
  curl http://localhost:7801/recv
        """
    )
    parser.add_argument("--name",  default="ACP-Agent", help="Agent 名称（显示用）")
    parser.add_argument("--join",  default=None,        help="要加入的 acp:// 链接")
    parser.add_argument("--relay", default=DEFAULT_RELAY_WS, help="中继服务器 WebSocket 地址")
    parser.add_argument("--port",  type=int, default=7801,   help="本地 HTTP 接口端口（默认 7801）")
    args = parser.parse_args()

    _status["local_port"] = args.port

    # 解析 --join 链接
    relay_ws    = args.relay
    session_id  = None
    if args.join:
        relay_ws, session_id = parse_link(args.join)
        log.info(f"将加入会话: relay={relay_ws}, session={session_id}")

    # 启动本地 HTTP 服务（独立线程）
    http_thread = threading.Thread(target=run_http_server, args=(args.port,), daemon=True)
    http_thread.start()

    # 设置 asyncio event loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)

    # 处理 Ctrl+C
    def shutdown(sig, frame):
        print("\n👋 ACP Relay 正在关闭...")
        _status["connected"] = False
        _loop.stop()
        sys.exit(0)
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # 启动 WebSocket 客户端
    try:
        _loop.run_until_complete(
            ws_client(relay_ws, args.name, session_id)
        )
    except KeyboardInterrupt:
        pass
    finally:
        _loop.close()


if __name__ == "__main__":
    main()
