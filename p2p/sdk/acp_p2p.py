"""
ACP-P2P SDK v0.3 — 轻量级去中心化 Agent 通信

设计原则：
  · 零强制依赖（纯标准库可运行）
  · 可不起服务器：send-only 模式直接发消息
  · 显式连接生命周期：connect / disconnect / join_group / leave_group
  · 服务器可选：需要接收消息时才启动，随时停止
"""
from __future__ import annotations

import asyncio
import json
import logging
import socket
import time
import uuid
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional
from urllib.parse import urlparse, parse_qs, urlencode

log = logging.getLogger("acp_p2p")

# ─── URI ─────────────────────────────────────────────────────────────────────

@dataclass
class ACPURI:
    host: str
    port: int
    name: str
    caps: list[str] = field(default_factory=list)
    psk:  str       = None

    @classmethod
    def parse(cls, uri: str) -> "ACPURI":
        if not uri.startswith("acp://"):
            raise ValueError(f"Not an ACP URI: {uri}")
        p  = urlparse(uri.replace("acp://", "http://", 1))
        qs = parse_qs(p.query)
        caps_raw = qs.get("caps", [""])[0]
        return cls(
            host = p.hostname or "localhost",
            port = p.port    or 7700,
            name = p.path.lstrip("/"),
            caps = [c for c in caps_raw.split(",") if c],
            psk  = qs.get("key", [None])[0],
        )

    def __str__(self) -> str:
        q = {}
        if self.caps: q["caps"] = ",".join(self.caps)
        if self.psk:  q["key"]  = self.psk
        base = f"acp://{self.host}:{self.port}/{self.name}"
        return base + (f"?{urlencode(q)}" if q else "")

    @property
    def receive_url(self) -> str:
        return f"http://{self.host}:{self.port}/acp/v1/receive"


def _local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80)); ip = s.getsockname()[0]; s.close(); return ip
    except Exception: return "127.0.0.1"


# ─── Message ─────────────────────────────────────────────────────────────────

def _msg(type_: str, from_: str, to_: str, body: dict, **kw) -> dict:
    m = {"acp":"0.1","id":"msg_"+uuid.uuid4().hex[:12],"type":type_,
         "from":from_,"to":to_,"ts":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
         "body":body}
    m.update({k:v for k,v in kw.items() if v is not None})
    return m


# ─── Lightweight HTTP send (stdlib only, no aiohttp required) ────────────────

def _http_post_sync(url: str, payload: dict, psk: str = None, timeout: float = 10) -> Optional[dict]:
    """同步 HTTP POST，纯标准库，send-only 场景不需要 aiohttp"""
    data = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if psk: headers["X-ACP-PSK"] = psk
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode()
            if r.status == 200:  return json.loads(body)
            if r.status == 202:  return None
    except urllib.error.HTTPError as e:
        if e.code == 202: return None
        log.warning(f"POST {url} → {e.code}")
    except Exception as e:
        log.warning(f"POST {url} failed: {e}")
    return None


async def _http_post_async(url: str, payload: dict, psk: str = None, timeout: float = 10) -> Optional[dict]:
    """异步 HTTP POST，优先 aiohttp，回退 stdlib"""
    try:
        import aiohttp
        headers = {"Content-Type": "application/json"}
        if psk: headers["X-ACP-PSK"] = psk
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json=payload, headers=headers,
                              timeout=aiohttp.ClientTimeout(total=timeout)) as r:
                if r.status == 200:  return await r.json()
                if r.status == 202:  return None
                log.warning(f"POST {url} → {r.status}")
                return None
    except ImportError:
        # 回退到 stdlib（在线程池里跑同步版本）
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _http_post_sync, url, payload, psk, timeout)
    except Exception as e:
        log.warning(f"POST {url} failed: {e}"); return None


# ─── Session ──────────────────────────────────────────────────────────────────

@dataclass
class Session:
    """
    两个 Agent 之间的有状态连接。
    通过 agent.connect(peer_uri) 建立，agent.disconnect(session) 关闭。
    """
    session_id: str
    local_uri:  str
    peer_uri:   str
    connected:  bool = True
    established_at: float = field(default_factory=time.time)

    def __repr__(self):
        state = "CONNECTED" if self.connected else "CLOSED"
        return f"Session({self.local_uri.split('/')[-1]} ↔ {self.peer_uri.split('/')[-1]}, {state})"


# ─── Group ────────────────────────────────────────────────────────────────────

@dataclass
class Group:
    """
    去中心化群聊。无服务器，成员列表各自本地维护。
    """
    group_id: str
    members:  list[str] = field(default_factory=list)
    active:   bool      = True

    def add(self, uri: str):
        if uri not in self.members: self.members.append(uri)

    def remove(self, uri: str):
        self.members = [m for m in self.members if m != uri]

    def to_invite_uri(self) -> str:
        return f"acpgroup://{self.group_id}?members={','.join(self.members)}"

    @classmethod
    def from_invite_uri(cls, uri: str) -> "Group":
        p  = urlparse(uri.replace("acpgroup://", "http://", 1))
        qs = parse_qs(p.query)
        members_raw = qs.get("members", [""])[0]
        return cls(
            group_id = (p.netloc + p.path).lstrip("/"),
            members  = [m for m in members_raw.split(",") if m],
        )

    def __repr__(self):
        state = "ACTIVE" if self.active else "LEFT"
        return f"Group({self.group_id.split(':')[0]!r}, {len(self.members)} members, {state})"


# ─── P2PAgent ─────────────────────────────────────────────────────────────────

TaskHandler  = Callable[[str, dict], Awaitable[Optional[dict]]]
ChatHandler  = Callable[[str, str, dict], Awaitable[None]]


class P2PAgent:
    """
    轻量级去中心化 ACP Agent。

    两种使用模式：

    【模式1：仅发送（最轻量，无需启动服务器）】
        agent = P2PAgent("alice")
        session = await agent.connect("acp://host:7700/bob")
        result  = await agent.send(session, "任务", {"data": 1})
        await agent.disconnect(session)

    【模式2：收发双向（需要启动服务器）】
        agent = P2PAgent("alice", port=7700)
        @agent.on_task
        async def handle(task, input): return {"ok": True}

        async with agent:           # 启动服务器
            session = await agent.connect("acp://host:7701/bob")
            await agent.send(session, "任务", {})
            await agent.disconnect(session)
            # 服务器在 with 块结束时自动停止
    """

    def __init__(
        self,
        name:         str,
        port:         int        = 7700,
        host:         str        = None,
        psk:          str        = None,
        capabilities: list[str]  = None,
    ):
        self.name         = name
        self.port         = port
        self._psk         = psk
        self.capabilities = capabilities or []
        self._host        = host or _local_ip()
        self.uri          = ACPURI(self._host, port, name, self.capabilities, psk)

        self._sessions:  dict[str, Session] = {}
        self._groups:    dict[str, Group]   = {}
        self._task_handler: Optional[TaskHandler] = None
        self._chat_handler: Optional[ChatHandler] = None
        self._msg_handlers: dict[str, Callable]   = {}
        self._server_task = None
        self._running     = False

    # ── Decorators ───────────────────────────────────────────────────────────

    def on_task(self, fn: TaskHandler) -> TaskHandler:
        """处理 task.delegate 消息"""
        self._task_handler = fn; return fn

    def on_group_message(self, fn: ChatHandler) -> ChatHandler:
        """处理群消息：async def fn(group_id, from_uri, body)"""
        self._chat_handler = fn; return fn

    def on_message(self, type_: str):
        """处理自定义消息类型"""
        def dec(fn): self._msg_handlers[type_] = fn; return fn
        return dec

    # ── Connection lifecycle ──────────────────────────────────────────────────

    async def connect(self, peer_uri: str) -> Session:
        """
        与另一个 Agent 建立连接会话。
        发送 agent.hello 握手，确认对方在线。
        返回 Session 对象，后续 send/disconnect 都用它。

        示例：
            session = await alice.connect("acp://192.168.1.5:7701/bob")
            print(session)  # Session(alice ↔ bob, CONNECTED)
        """
        target = ACPURI.parse(peer_uri)
        hello = _msg("agent.hello", str(self.uri), peer_uri,
                     {"name": self.name, "capabilities": self.capabilities})
        reply = await _http_post_async(target.receive_url, hello, target.psk, timeout=5)

        session = Session(
            session_id      = "sess_" + uuid.uuid4().hex[:8],
            local_uri       = str(self.uri),
            peer_uri        = peer_uri,
            connected       = reply is not None,
        )
        self._sessions[session.session_id] = session
        log.info(f"connect → {peer_uri}: {'OK' if session.connected else 'UNREACHABLE (send-only)'}")
        return session

    async def disconnect(self, session: Session):
        """
        关闭与对方的连接，通知对方。

        示例：
            await alice.disconnect(session)
        """
        if not session.connected:
            session.connected = False
            return
        target = ACPURI.parse(session.peer_uri)
        bye = _msg("agent.bye", str(self.uri), session.peer_uri,
                   {"session_id": session.session_id, "reason": "normal_close"})
        await _http_post_async(target.receive_url, bye, target.psk, timeout=3)
        session.connected = False
        self._sessions.pop(session.session_id, None)
        log.info(f"disconnected from {session.peer_uri}")

    # ── Point-to-point messaging ──────────────────────────────────────────────

    async def send(
        self,
        target:       "Session | str",
        task:         str,
        input:        dict         = None,
        timeout:      float        = 30.0,
        correlation_id: str        = None,
    ) -> Optional[dict]:
        """
        发送任务消息，返回对方响应。

        target 可以是：
          · Session 对象（connect() 返回的）
          · str（直接写 ACP URI，不需要先 connect）

        示例：
            # 方式1：通过 session
            result = await alice.send(session, "Summarize", {"text": "..."})

            # 方式2：直接写 URI（轻量，无握手）
            result = await alice.send("acp://host:7700/bob", "Summarize", {"text": "..."})
        """
        if isinstance(target, Session):
            if not target.connected:
                raise RuntimeError(f"Session {target.session_id} is closed")
            peer_uri = target.peer_uri
        else:
            peer_uri = target

        t   = ACPURI.parse(peer_uri)
        msg = _msg("task.delegate", str(self.uri), peer_uri,
                   {"task": task, "input": input or {}},
                   correlation_id=correlation_id or "c_" + uuid.uuid4().hex[:8])
        return await _http_post_async(t.receive_url, msg, t.psk, timeout)

    async def ping(self, uri: str, timeout: float = 5.0) -> bool:
        """检查对方是否在线"""
        t     = ACPURI.parse(uri)
        hello = _msg("agent.hello", str(self.uri), uri, {})
        r     = await _http_post_async(t.receive_url, hello, t.psk, timeout)
        return r is not None

    async def discover(self, uri: str) -> Optional[dict]:
        """查询对方 Agent 的身份和能力"""
        t = ACPURI.parse(uri)
        try:
            import aiohttp
            async with aiohttp.ClientSession() as s:
                async with s.get(f"http://{t.host}:{t.port}/acp/v1/identity",
                                 timeout=aiohttp.ClientTimeout(total=5)) as r:
                    return await r.json() if r.status == 200 else None
        except Exception:
            return None

    # ── Group chat ────────────────────────────────────────────────────────────

    def create_group(self, name: str) -> Group:
        """
        创建群聊，自己是第一个成员。
        调用 group.to_invite_uri() 获取邀请链接，发给其他 Agent。

        示例：
            group = alice.create_group("team")
            invite_link = group.to_invite_uri()
            # 把 invite_link 发给 Bob
        """
        gid   = f"{name}:{str(self.uri)}"
        group = Group(group_id=gid, members=[str(self.uri)])
        self._groups[gid] = group
        return group

    async def invite(self, group: Group, peer_uri: str) -> bool:
        """
        邀请对方加入群聊（推送模式）。
        对方 SDK 自动处理加入，不需要对方主动操作。

        示例：
            ok = await alice.invite(group, "acp://host:7701/bob")
        """
        t   = ACPURI.parse(peer_uri)
        msg = _msg("group.invite", str(self.uri), peer_uri, {
            "group_id":   group.group_id,
            "invite_uri": group.to_invite_uri(),
            "invited_by": str(self.uri),
        })
        r = await _http_post_async(t.receive_url, msg, t.psk, timeout=5)
        if r:
            group.add(peer_uri)
            await self._notify_group(group, "group.member_joined", {
                "group_id":   group.group_id,
                "new_member": peer_uri,
                "all_members": group.members,
            }, exclude=peer_uri)
            return True
        return False

    async def join_group(self, invite_uri: str) -> Group:
        """
        主动通过邀请链接加入群聊。

        示例：
            group = await bob.join_group("acpgroup://team:acp://...?members=...")
        """
        group = Group.from_invite_uri(invite_uri)
        group.add(str(self.uri))
        self._groups[group.group_id] = group
        await self._notify_group(group, "group.member_joined", {
            "group_id":    group.group_id,
            "new_member":  str(self.uri),
            "all_members": group.members,
        }, exclude=str(self.uri))
        return group

    async def leave_group(self, group: "Group | str"):
        """
        退出群聊，通知其他成员。

        示例：
            await bob.leave_group(group)
        """
        if isinstance(group, str):
            group = self._groups.get(group)
            if not group: return
        group.active = False
        await self._notify_group(group, "group.member_left", {
            "group_id":      group.group_id,
            "leaving_member": str(self.uri),
        })
        group.remove(str(self.uri))
        self._groups.pop(group.group_id, None)
        log.info(f"left group {group.group_id}")

    async def group_send(self, group: "Group | str", body: dict) -> list[dict]:
        """
        向群里所有其他成员广播消息。

        示例：
            await alice.group_send(group, {"text": "大家好！"})
            await alice.group_send(group, {"text": "有问题", "type": "question"})
        """
        if isinstance(group, str):
            group = self._groups.get(group)
            if not group: raise ValueError("Group not found")
        if not group.active:
            raise RuntimeError("You have left this group")
        results = []
        for peer in group.members:
            if peer == str(self.uri): continue
            t   = ACPURI.parse(peer)
            msg = _msg("group.message", str(self.uri), peer,
                       {"group_id": group.group_id, **body})
            try:
                r = await _http_post_async(t.receive_url, msg, t.psk, timeout=5)
                results.append({"to": peer, "ok": True})
            except Exception as e:
                log.warning(f"group_send → {peer}: {e}")
                results.append({"to": peer, "ok": False, "error": str(e)})
        return results

    def get_group(self, group_id: str) -> Optional[Group]:
        return self._groups.get(group_id)

    async def _notify_group(self, group: Group, type_: str, body: dict, exclude: str = None):
        for peer in group.members:
            if peer == str(self.uri) or peer == exclude: continue
            t   = ACPURI.parse(peer)
            msg = _msg(type_, str(self.uri), peer, body)
            try:
                await _http_post_async(t.receive_url, msg, t.psk, timeout=3)
            except Exception as e:
                log.warning(f"notify {peer}: {e}")

    # ── Server ────────────────────────────────────────────────────────────────

    def start(self, block: bool = True, print_uri: bool = True):
        """
        启动 Agent 服务器（开始监听入站消息）。
        block=True：阻塞运行直到 Ctrl+C（适合独立脚本）
        block=False：后台运行（适合嵌入其他 async 程序，推荐用 async with 替代）
        """
        if print_uri:
            print(f"\n🔗 ACP URI: {self.uri}")
            print(f"   分享给要与你通信的 Agent\n")
        if block:
            asyncio.run(self._run())
        else:
            loop = asyncio.get_event_loop()
            self._server_task = loop.create_task(self._run())

    async def stop(self):
        """停止服务器，关闭所有连接"""
        self._running = False
        if self._server_task:
            self._server_task.cancel()
            try: await self._server_task
            except asyncio.CancelledError: pass
        log.info(f"[{self.name}] server stopped")

    async def _run(self):
        try:
            from aiohttp import web
        except ImportError:
            raise ImportError("pip install aiohttp  # required to receive messages")
        self._running = True
        app = web.Application()
        app.router.add_post("/acp/v1/receive",  self._handle_receive)
        app.router.add_get( "/acp/v1/identity", self._handle_identity)
        app.router.add_get( "/acp/v1/health",   self._handle_health)
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", self.port).start()
        log.info(f"[{self.name}] listening on :{self.port}")
        try:
            while self._running: await asyncio.sleep(1)
        finally:
            await runner.cleanup()

    # ── Request handlers ─────────────────────────────────────────────────────

    async def _handle_receive(self, request):
        from aiohttp import web
        if self._psk and request.headers.get("X-ACP-PSK","") != self._psk:
            return web.json_response({"error":"Unauthorized"}, status=401)
        try:    msg = await request.json()
        except: return web.json_response({"error":"Bad JSON"}, status=400)

        log.debug(f"[{self.name}] ← {msg.get('type','?')} from {msg.get('from','?')[:35]}")
        reply = await self._dispatch(msg)
        if reply: return web.json_response(reply, status=200)
        return web.json_response({"ok":True}, status=202)

    async def _dispatch(self, msg: dict) -> Optional[dict]:
        t = msg.get("type","")

        if t == "task.delegate":
            if not self._task_handler:
                return _msg("error", str(self.uri), msg["from"],
                            {"code":"no_handler"}, reply_to=msg["id"])
            try:
                out = await self._task_handler(msg["body"].get("task",""), msg["body"].get("input",{}))
                return _msg("task.result", str(self.uri), msg["from"],
                            {"status":"success","output": out or {}},
                            reply_to=msg["id"],
                            correlation_id=msg.get("correlation_id"))
            except Exception as e:
                log.exception("task handler error")
                return _msg("error", str(self.uri), msg["from"],
                            {"code":"handler_error","message":str(e)}, reply_to=msg["id"])

        if t == "agent.hello":
            return _msg("agent.hello", str(self.uri), msg["from"],
                        {"name":self.name,"capabilities":self.capabilities},
                        reply_to=msg["id"])

        if t == "agent.bye":
            sid = msg["body"].get("session_id","")
            self._sessions.pop(sid, None)
            return None

        if t == "group.invite":
            group = Group.from_invite_uri(msg["body"]["invite_uri"])
            group.add(str(self.uri))
            self._groups[group.group_id] = group
            if self._chat_handler:
                asyncio.get_event_loop().create_task(
                    self._chat_handler(group.group_id, "system",
                                       {"event":"joined","invited_by":msg["from"]}))
            return _msg("group.invite_ack", str(self.uri), msg["from"],
                        {"status":"joined","group_id":group.group_id}, reply_to=msg["id"])

        if t == "group.message":
            gid   = msg["body"].get("group_id","")
            if gid not in self._groups:
                self._groups[gid] = Group(group_id=gid, members=[str(self.uri), msg["from"]])
            if self._chat_handler:
                body = {k:v for k,v in msg["body"].items() if k != "group_id"}
                asyncio.get_event_loop().create_task(
                    self._chat_handler(gid, msg["from"], body))
            return None

        if t == "group.member_joined":
            gid     = msg["body"].get("group_id","")
            members = msg["body"].get("all_members",[])
            if gid in self._groups:
                self._groups[gid].members = members
            return None

        if t == "group.member_left":
            gid    = msg["body"].get("group_id","")
            leaver = msg["body"].get("leaving_member","")
            if gid in self._groups:
                self._groups[gid].remove(leaver)
            return None

        if t in self._msg_handlers:
            return await self._msg_handlers[t](msg)

        return None

    def _handle_identity(self, request):
        from aiohttp import web
        return web.json_response({
            "uri":str(self.uri),"name":self.name,"capabilities":self.capabilities,
            "acp_version":"0.1","protocol":"acp-p2p",
            "active_sessions": len(self._sessions),
            "groups": list(self._groups.keys()),
        })

    def _handle_health(self, request):
        from aiohttp import web
        return web.json_response({"ok":True,"name":self.name,"uri":str(self.uri),
                                  "running":self._running})

    # ── Context manager ───────────────────────────────────────────────────────

    async def __aenter__(self):
        self._server_task = asyncio.get_event_loop().create_task(self._run())
        await asyncio.sleep(0.12)   # 等服务器就绪
        return self

    async def __aexit__(self, *_):
        await self.stop()
