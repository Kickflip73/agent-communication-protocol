#!/usr/bin/env python3
"""
ACP P2P Relay — 真正的点对点通信，无需任何中间服务器
=======================================================

原理：
  发起方监听本地端口，生成包含 IP:Port/Token 的 acp:// 链接。
  接收方解析链接，直接 TCP (WebSocket) 连接到发起方。
  两端之间无任何中间人。

用法：
  # Agent A（发起方）— 生成链接：
  python3 acp_relay.py --name "Agent-A"

  # Agent B（接收方）— 粘贴链接：
  python3 acp_relay.py --name "Agent-B" --join acp://1.2.3.4:7801/tok_xxx

  # 通信（双方都用 localhost:7901）：
  curl -X POST http://localhost:7901/send -H "Content-Type: application/json" -d '{"text":"你好"}'
  curl http://localhost:7901/recv

端口约定：
  --port N  : WebSocket 监听端口（发起方用，默认 7801）
  HTTP 接口  : --port + 100（默认 7901），两端都用这个端口和本地 Relay 说话

依赖：pip install websockets
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
import socket
from collections import deque
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import urllib.request
import datetime

try:
    import websockets
    import websockets.exceptions
except ImportError:
    print("❌ 缺少依赖: pip install websockets")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [acp] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("acp-p2p")

# ── 全局状态 ──────────────────────────────────────────────────────────────────
_recv_queue: deque = deque(maxlen=1000)
_peer_ws = None
_loop    = None

_status: dict = {
    "connected": False,
    "role":      None,
    "link":      None,
    "agent_name": None,
    "peer_name":  None,
    "ws_port":    7801,
    "http_port":  7901,
    "messages_sent":     0,
    "messages_received": 0,
}
# ─────────────────────────────────────────────────────────────────────────────


def _now() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"

def _make_id() -> str:
    return "msg_" + uuid.uuid4().hex[:12]

def _make_token() -> str:
    return "tok_" + uuid.uuid4().hex[:16]


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_public_ip(timeout: float = 4.0) -> str | None:
    for url in ["https://api.ipify.org", "https://ifconfig.me/ip", "https://icanhazip.com"]:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "acp-p2p/0.1"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                ip = resp.read().decode().strip()
                if ip and "." in ip and len(ip) <= 45:
                    return ip
        except Exception:
            continue
    return None


def parse_link(link: str) -> tuple[str, int, str]:
    """acp://host:port/token  →  (host, port, token)"""
    parsed = urlparse(link.replace("acp://", "http://", 1))
    host  = parsed.hostname or "localhost"
    port  = parsed.port or 7801
    token = parsed.path.strip("/")
    return host, port, token


def _on_message(raw: str):
    try:
        msg = json.loads(raw)
        _recv_queue.append({
            "id": msg.get("id", _make_id()),
            "received_at": time.time(),
            "content": msg,
        })
        _status["messages_received"] += 1
        log.info(f"📨 收到: type={msg.get('type','?')} from={msg.get('from','?')}")
    except json.JSONDecodeError:
        log.warning("收到非 JSON 消息，忽略")


# ══════════════════════════════════════════════════════════════════════════════
# HOST 模式（发起方：监听 WebSocket，生成链接）
# ══════════════════════════════════════════════════════════════════════════════

async def host_mode(token: str, ws_port: int, http_port: int, agent_name: str):
    global _peer_ws, _status

    async def on_guest(websocket):
        global _peer_ws
        # 获取路径中的 token
        try:
            path = websocket.request.path
        except AttributeError:
            path = getattr(websocket, 'path', '/')

        incoming_token = path.strip("/")
        if incoming_token != token:
            await websocket.send(json.dumps({"type":"error","code":"invalid_token"}))
            await websocket.close()
            log.warning(f"拒绝：token 不匹配 ({incoming_token!r} != {token!r})")
            return

        _peer_ws = websocket
        _status["connected"] = True

        print(f"\n{'='*55}")
        print(f"✅ 对方已连接，开始 P2P 通信！")
        print(f"   发消息: curl -X POST http://localhost:{http_port}/send -H 'Content-Type: application/json' -d '{{\"text\":\"你好\"}}'")
        print(f"   收消息: curl http://localhost:{http_port}/recv")
        print(f"{'='*55}\n")

        try:
            async for raw in websocket:
                _on_message(raw)
        except websockets.exceptions.ConnectionClosed:
            log.info("对方已断开")
        finally:
            _peer_ws = None
            _status["connected"] = False

    # 先获取 IP，再绑定端口
    log.info("探测公网 IP...")
    public_ip = await asyncio.get_event_loop().run_in_executor(None, lambda: get_public_ip(4.0))
    local_ip  = get_local_ip()
    display_ip = public_ip or local_ip

    link = f"acp://{display_ip}:{ws_port}/{token}"
    _status["link"]       = link
    _status["role"]       = "host"
    _status["agent_name"] = agent_name
    _status["ws_port"]    = ws_port
    _status["http_port"]  = http_port

    async with websockets.serve(on_guest, "0.0.0.0", ws_port):
        print(f"\n{'='*60}")
        print(f"✅ ACP P2P 通信服务已启动")
        print(f"   IP 类型: {'公网' if public_ip else '局域网（对方需在同一局域网）'}")
        print(f"")
        print(f"🔗 你的通信链接（发给对方）:")
        print(f"   {link}")
        print(f"")
        print(f"📋 对方执行:")
        print(f"   python3 acp_relay.py --name \"对方名称\" --join {link}")
        print(f"")
        print(f"⏳ 等待对方连接中...")
        print(f"{'='*60}\n")

        await asyncio.Future()  # 永久等待


# ══════════════════════════════════════════════════════════════════════════════
# GUEST 模式（接收方：主动连接到 Host）
# ══════════════════════════════════════════════════════════════════════════════

async def guest_mode(host: str, ws_port: int, token: str, http_port: int, agent_name: str):
    global _peer_ws, _status

    uri = f"ws://{host}:{ws_port}/{token}"
    log.info(f"连接到: {uri}")

    _status["role"]       = "guest"
    _status["agent_name"] = agent_name
    _status["http_port"]  = http_port

    try:
        async with websockets.connect(uri, ping_interval=20, ping_timeout=10) as ws:
            _peer_ws = ws
            _status["connected"] = True

            print(f"\n{'='*55}")
            print(f"✅ P2P 连接成功！（直连，无中间服务器）")
            print(f"   对方: {host}:{ws_port}")
            print(f"")
            print(f"   发消息: curl -X POST http://localhost:{http_port}/send -H 'Content-Type: application/json' -d '{{\"text\":\"你好\"}}'")
            print(f"   收消息: curl http://localhost:{http_port}/recv")
            print(f"{'='*55}\n")

            async for raw in ws:
                _on_message(raw)

    except ConnectionRefusedError:
        print(f"\n❌ 连接被拒绝：确认对方已运行 acp_relay.py 且端口 {ws_port} 可达")
        sys.exit(1)
    except OSError as e:
        print(f"\n❌ 连接失败: {e}")
        sys.exit(1)
    finally:
        _peer_ws = None
        _status["connected"] = False


# ══════════════════════════════════════════════════════════════════════════════
# 本地 HTTP 接口
# ══════════════════════════════════════════════════════════════════════════════

async def _ws_send(msg: dict):
    if _peer_ws is None:
        raise ConnectionError("尚未建立 P2P 连接")
    await _peer_ws.send(json.dumps(msg, ensure_ascii=False))
    _status["messages_sent"] += 1


def send_sync(msg: dict):
    future = asyncio.run_coroutine_threadsafe(_ws_send(msg), _loop)
    future.result(timeout=10)


class LocalHTTP(BaseHTTPRequestHandler):
    def log_message(self, *_): pass

    def _json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        p = urlparse(self.path).path
        if p == "/status":
            self._json(_status)
        elif p == "/recv":
            qs    = parse_qs(urlparse(self.path).query)
            limit = int(qs.get("limit", ["50"])[0])
            msgs  = [_recv_queue.popleft() for _ in range(min(limit, len(_recv_queue)))]
            self._json({"messages": msgs, "count": len(msgs), "remaining": len(_recv_queue)})
        elif p == "/link":
            self._json({"link": _status.get("link")})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        p = urlparse(self.path).path
        if p == "/send":
            n   = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(n) if n else b"{}"
            try:
                msg = json.loads(raw)
                msg.setdefault("id",   _make_id())
                msg.setdefault("ts",   _now())
                msg.setdefault("from", _status.get("agent_name", "unknown"))
                send_sync(msg)
                self._json({"ok": True, "id": msg["id"]})
            except ConnectionError as e:
                self._json({"ok": False, "error": str(e)}, 503)
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)
        else:
            self._json({"error": "not found"}, 404)


def run_http(port: int):
    HTTPServer(("127.0.0.1", port), LocalHTTP).serve_forever()


# ══════════════════════════════════════════════════════════════════════════════
# 主入口
# ══════════════════════════════════════════════════════════════════════════════

def main():
    global _loop, _status

    parser = argparse.ArgumentParser(description="ACP P2P — 零中间服务器直连通信")
    parser.add_argument("--name",  default="ACP-Agent", help="本端 Agent 名称")
    parser.add_argument("--join",  default=None,        help="对方的 acp:// 链接（接收方用）")
    parser.add_argument("--port",  type=int, default=7801,
                        help="WebSocket 监听端口（发起方；默认7801）。HTTP 接口 = port+100")
    args = parser.parse_args()

    ws_port   = args.port
    http_port = args.port + 100
    _status["ws_port"]   = ws_port
    _status["http_port"] = http_port

    # 启动本地 HTTP
    threading.Thread(target=run_http, args=(http_port,), daemon=True).start()
    log.info(f"HTTP 接口: http://127.0.0.1:{http_port}")

    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)

    def _shutdown(sig, frame):
        print("\n👋 ACP P2P 关闭")
        _loop.stop()
        sys.exit(0)
    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        if args.join:
            host, port, token = parse_link(args.join)
            _loop.run_until_complete(
                guest_mode(host, port, token, http_port, args.name)
            )
        else:
            token = _make_token()
            _loop.run_until_complete(
                host_mode(token, ws_port, http_port, args.name)
            )
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
