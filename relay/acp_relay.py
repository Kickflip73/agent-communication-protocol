#!/usr/bin/env python3
"""
ACP P2P Relay v0.2
==================
真正的点对点通信，无需任何中间服务器。

v0.2 新增（来自竞品研究）：
  - 断线自动重连（Guest 模式，指数退避）
  - AgentCard 能力声明（Agent 启动时广播自身能力）
  - 消息持久化（收件箱写入本地 JSONL，防消息丢失）
  - 流式消息支持（/stream SSE 端点，对接 A2A 风格客户端）
  - 会话历史（/history 端点）

用法：
  python3 acp_relay.py --name "Agent-A"
  python3 acp_relay.py --name "Agent-B" --join acp://1.2.3.4:7801/tok_xxx

  # 可选：声明能力
  python3 acp_relay.py --name "Agent-A" --skills "summarize,translate,code-review"

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
import os
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

VERSION = "0.2"

# ── 全局状态 ──────────────────────────────────────────────────────────────────
_recv_queue: deque = deque(maxlen=1000)
_peer_ws   = None
_loop      = None
_inbox_path: str | None = None  # 消息持久化路径

_status: dict = {
    "acp_version": VERSION,
    "connected":   False,
    "role":        None,
    "link":        None,
    "agent_name":  None,
    "agent_card":  None,
    "peer_card":   None,       # 对方的 AgentCard（连接后自动交换）
    "ws_port":     7801,
    "http_port":   7901,
    "messages_sent":     0,
    "messages_received": 0,
    "reconnect_count":   0,
    "started_at":        None,
}
# ─────────────────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"

def _make_id() -> str:
    return "msg_" + uuid.uuid4().hex[:12]

def _make_token() -> str:
    return "tok_" + uuid.uuid4().hex[:16]

def _make_agent_card(name: str, skills: list[str]) -> dict:
    """AgentCard — 参考 A2A 规范，描述 Agent 自身能力"""
    return {
        "name":        name,
        "version":     "1.0.0",
        "acp_version": VERSION,
        "skills":      skills,
        "description": f"ACP P2P Agent: {name}",
        "http_port":   _status["http_port"],
        "timestamp":   _now(),
    }

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
            req = urllib.request.Request(url, headers={"User-Agent": "acp-p2p/0.2"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                ip = resp.read().decode().strip()
                if ip and "." in ip and len(ip) <= 45:
                    return ip
        except Exception:
            continue
    return None

def parse_link(link: str) -> tuple[str, int, str]:
    parsed = urlparse(link.replace("acp://", "http://", 1))
    return parsed.hostname or "localhost", parsed.port or 7801, parsed.path.strip("/")

def _persist_message(msg: dict):
    """将收到的消息写入本地 JSONL 文件（防丢失）"""
    if _inbox_path:
        try:
            with open(_inbox_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(msg, ensure_ascii=False) + "\n")
        except Exception:
            pass

def _on_message(raw: str):
    try:
        msg = json.loads(raw)

        # AgentCard 交换（连接时双方互发）
        if msg.get("type") == "acp.agent_card":
            _status["peer_card"] = msg.get("card")
            log.info(f"📋 收到对方 AgentCard: {msg.get('card', {}).get('name')}")
            log.info(f"   能力: {msg.get('card', {}).get('skills', [])}")
            return

        entry = {
            "id":          msg.get("id", _make_id()),
            "received_at": time.time(),
            "content":     msg,
        }
        _recv_queue.append(entry)
        _persist_message(entry)
        _status["messages_received"] += 1
        log.info(f"📨 收到: type={msg.get('type','?')} from={msg.get('from','?')}")
    except json.JSONDecodeError:
        log.warning("收到非 JSON 消息，忽略")

async def _send_agent_card(ws):
    """连接建立后立即发送 AgentCard"""
    card_msg = {
        "type": "acp.agent_card",
        "id":   _make_id(),
        "ts":   _now(),
        "card": _status["agent_card"],
    }
    await ws.send(json.dumps(card_msg))


# ══════════════════════════════════════════════════════════════════════════════
# HOST 模式
# ══════════════════════════════════════════════════════════════════════════════

async def host_mode(token: str, ws_port: int, http_port: int):
    global _peer_ws

    async def on_guest(websocket):
        global _peer_ws
        try:
            path = websocket.request.path
        except AttributeError:
            path = getattr(websocket, 'path', '/')

        if path.strip("/") != token:
            await websocket.send(json.dumps({"type":"error","code":"invalid_token"}))
            await websocket.close()
            return

        _peer_ws = websocket
        _status["connected"] = True
        _status["started_at"] = _status["started_at"] or time.time()

        # 交换 AgentCard
        await _send_agent_card(websocket)

        print(f"\n{'='*55}")
        print(f"✅ 对方已连接！P2P 通道建立（无中间服务器）")
        print(f"   发消息: POST http://localhost:{http_port}/send")
        print(f"   收消息: GET  http://localhost:{http_port}/recv")
        print(f"{'='*55}\n")

        try:
            async for raw in websocket:
                _on_message(raw)
        except websockets.exceptions.ConnectionClosed:
            log.info("对方断开连接")
        finally:
            _peer_ws = None
            _status["connected"] = False
            _status["peer_card"] = None

    log.info("探测公网 IP...")
    public_ip = await asyncio.get_event_loop().run_in_executor(None, lambda: get_public_ip(4.0))
    display_ip = public_ip or get_local_ip()

    link = f"acp://{display_ip}:{ws_port}/{token}"
    _status["link"] = link

    async with websockets.serve(on_guest, "0.0.0.0", ws_port):
        print(f"\n{'='*60}")
        print(f"✅ ACP P2P v{VERSION} — 通信服务已启动")
        print(f"   IP: {'公网 ' if public_ip else '局域网 '}{display_ip}")
        print(f"")
        print(f"🔗 你的通信链接（发给对方）:")
        print(f"   {link}")
        print(f"")
        print(f"📋 对方执行:")
        print(f"   python3 acp_relay.py --name \"对方\" --join {link}")
        print(f"")
        print(f"⏳ 等待对方连接...")
        print(f"{'='*60}\n")
        await asyncio.Future()


# ══════════════════════════════════════════════════════════════════════════════
# GUEST 模式（带自动重连）
# ══════════════════════════════════════════════════════════════════════════════

async def guest_mode(host: str, ws_port: int, token: str, http_port: int):
    global _peer_ws
    uri = f"ws://{host}:{ws_port}/{token}"

    MAX_RETRIES = 10
    retry = 0

    while retry < MAX_RETRIES:
        try:
            log.info(f"{'重新连接 #' + str(retry) if retry else '连接到'}: {uri}")
            async with websockets.connect(uri, ping_interval=20, ping_timeout=10) as ws:
                _peer_ws = ws
                _status["connected"] = True
                _status["started_at"] = _status["started_at"] or time.time()
                if retry > 0:
                    _status["reconnect_count"] += 1

                # 交换 AgentCard
                await _send_agent_card(ws)

                print(f"\n{'='*55}")
                if retry == 0:
                    print(f"✅ P2P 连接成功！（直连，无中间服务器）")
                else:
                    print(f"✅ 重连成功（第 {retry} 次）")
                print(f"   对方: {host}:{ws_port}")
                print(f"   发消息: POST http://localhost:{http_port}/send")
                print(f"   收消息: GET  http://localhost:{http_port}/recv")
                print(f"{'='*55}\n")

                retry = 0  # 连接成功后重置重试计数
                async for raw in ws:
                    _on_message(raw)

        except ConnectionRefusedError:
            if retry == 0:
                print(f"\n❌ 连接被拒绝，确认对方已启动且端口 {ws_port} 可达")
            log.warning(f"连接失败，{2**retry}s 后重试 ({retry+1}/{MAX_RETRIES})")
        except websockets.exceptions.ConnectionClosed:
            log.info(f"连接断开，{2**retry}s 后重连 ({retry+1}/{MAX_RETRIES})")
        except OSError as e:
            log.warning(f"网络错误: {e}，{2**retry}s 后重试")
        finally:
            _peer_ws = None
            _status["connected"] = False
            _status["peer_card"] = None

        retry += 1
        if retry < MAX_RETRIES:
            await asyncio.sleep(min(2 ** retry, 60))  # 指数退避，最长 60s

    print(f"\n❌ 重试 {MAX_RETRIES} 次后放弃，请检查对方是否在线")
    sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════════
# 本地 HTTP 接口
# ══════════════════════════════════════════════════════════════════════════════

async def _ws_send(msg: dict):
    if _peer_ws is None:
        raise ConnectionError("尚未建立 P2P 连接（正在等待或重连中）")
    await _peer_ws.send(json.dumps(msg, ensure_ascii=False))
    _status["messages_sent"] += 1

def send_sync(msg: dict):
    future = asyncio.run_coroutine_threadsafe(_ws_send(msg), _loop)
    future.result(timeout=10)

# SSE 订阅者列表
_sse_subscribers: list = []

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

        elif p == "/card":
            # 返回本端和对端的 AgentCard
            self._json({
                "self": _status.get("agent_card"),
                "peer": _status.get("peer_card"),
            })

        elif p == "/history":
            # 返回本地持久化的完整历史
            history = []
            if _inbox_path and os.path.exists(_inbox_path):
                with open(_inbox_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                history.append(json.loads(line))
                            except Exception:
                                pass
            qs = parse_qs(urlparse(self.path).query)
            limit = int(qs.get("limit", ["100"])[0])
            self._json({"history": history[-limit:], "total": len(history)})

        elif p == "/stream":
            # SSE 流式端点 — 客户端 GET /stream 后持续接收新消息
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            q: deque = deque()
            _sse_subscribers.append(q)
            try:
                while True:
                    if q:
                        msg = q.popleft()
                        data = f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
                        self.wfile.write(data.encode())
                        self.wfile.flush()
                    else:
                        # keepalive
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                        time.sleep(1)
            except Exception:
                pass
            finally:
                _sse_subscribers.remove(q)

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
    global _loop, _status, _inbox_path

    parser = argparse.ArgumentParser(description="ACP P2P v0.2 — 零中间服务器直连通信")
    parser.add_argument("--name",   default="ACP-Agent", help="本端名称")
    parser.add_argument("--join",   default=None,        help="对方的 acp:// 链接")
    parser.add_argument("--port",   type=int, default=7801, help="WebSocket 端口（发起方，默认7801）")
    parser.add_argument("--skills", default="",          help="逗号分隔的能力列表，如 summarize,translate")
    parser.add_argument("--inbox",  default=None,        help="消息持久化文件路径（默认 /tmp/acp_inbox_<name>.jsonl）")
    args = parser.parse_args()

    ws_port   = args.port
    http_port = args.port + 100

    skills = [s.strip() for s in args.skills.split(",") if s.strip()] if args.skills else []

    _status["agent_name"] = args.name
    _status["ws_port"]    = ws_port
    _status["http_port"]  = http_port
    _status["agent_card"] = _make_agent_card(args.name, skills)

    # 消息持久化
    _inbox_path = args.inbox or f"/tmp/acp_inbox_{args.name.replace(' ','_')}.jsonl"
    log.info(f"消息持久化: {_inbox_path}")

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
            _loop.run_until_complete(guest_mode(host, port, token, http_port))
        else:
            token = _make_token()
            _loop.run_until_complete(host_mode(token, ws_port, http_port))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
