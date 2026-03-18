"""
ACP-P2P SDK v0.2 — 去中心化 Agent 通信 + 群聊

核心能力：
- 任意两个 Agent 直连通信（无第三方）
- 多 Agent 去中心化群聊（无群服务器）
- 单文件 SDK，唯一依赖：aiohttp

快速开始见 SKILL.md
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import urlparse, parse_qs, urlencode

log = logging.getLogger("acp_p2p")

# ─── ACP URI ─────────────────────────────────────────────────────────────────

@dataclass
class ACPURI:
    """
    acp://<host>:<port>/<name>?caps=cap1,cap2&key=psk
    """
    host: str
    port: int
    name: str
    caps: list[str] = field(default_factory=list)
    psk: str = None

    @classmethod
    def parse(cls, uri: str) -> "ACPURI":
        if not uri.startswith("acp://"):
            raise ValueError(f"Not an ACP URI: {uri}")
        parsed = urlparse(uri.replace("acp://", "http://", 1))
        qs = parse_qs(parsed.query)
        caps_raw = qs.get("caps", [""])[0]
        caps = [c for c in caps_raw.split(",") if c] if caps_raw else []
        return cls(
            host=parsed.hostname or "localhost",
            port=parsed.port or 7700,
            name=parsed.path.lstrip("/"),
            caps=caps,
            psk=qs.get("key", [None])[0],
        )

    def __str__(self) -> str:
        qs = {}
        if self.caps:
            qs["caps"] = ",".join(self.caps)
        if self.psk:
            qs["key"] = self.psk
        base = f"acp://{self.host}:{self.port}/{self.name}"
        return base + (f"?{urlencode(qs)}" if qs else "")

    @property
    def receive_url(self) -> str:
        return f"http://{self.host}:{self.port}/acp/v1/receive"

    @property
    def identity_url(self) -> str:
        return f"http://{self.host}:{self.port}/acp/v1/identity"


def _local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]; s.close(); return ip
    except Exception:
        return "127.0.0.1"


# ─── Message factory ─────────────────────────────────────────────────────────

def _msg(type_: str, from_: str, to_: str, body: dict,
         correlation_id: str = None, reply_to: str = None) -> dict:
    m = {
        "acp": "0.1",
        "id": "msg_" + uuid.uuid4().hex[:16],
        "type": type_,
        "from": from_,
        "to": to_,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "body": body,
    }
    if correlation_id: m["correlation_id"] = correlation_id
    if reply_to:       m["reply_to"] = reply_to
    return m


# ─── Group ───────────────────────────────────────────────────────────────────

@dataclass
class ACPGroup:
    """
    去中心化群聊。无服务器，每个成员本地保存成员列表。

    群 ID 格式: group:<name>:<creator_uri>
    分享格式:   把 group_uri 发给要拉进来的 Agent 即可
    """
    group_id: str
    members: list[str] = field(default_factory=list)   # ACP URI strings

    def add_member(self, uri: str):
        if uri not in self.members:
            self.members.append(uri)

    def remove_member(self, uri: str):
        self.members = [m for m in self.members if m != uri]

    def to_join_uri(self) -> str:
        """生成邀请 URI，分享给新成员即可加入"""
        members_encoded = ",".join(self.members)
        return f"acpgroup://{self.group_id}?members={members_encoded}"

    @classmethod
    def from_join_uri(cls, join_uri: str) -> "ACPGroup":
        """从邀请 URI 恢复群信息"""
        parsed = urlparse(join_uri.replace("acpgroup://", "http://", 1))
        group_id = parsed.netloc + parsed.path
        qs = parse_qs(parsed.query)
        members_raw = qs.get("members", [""])[0]
        members = [m for m in members_raw.split(",") if m]
        return cls(group_id=group_id, members=members)

    def __repr__(self):
        return f"ACPGroup(id={self.group_id}, members={len(self.members)})"


# ─── P2PAgent ────────────────────────────────────────────────────────────────

TaskHandler    = Callable[[str, dict], Awaitable[Optional[dict]]]
MessageHandler = Callable[[dict], Awaitable[Optional[dict]]]
ChatHandler    = Callable[[str, str, dict], Awaitable[None]]   # (group_id, from_uri, body)


class P2PAgent:
    """
    去中心化 ACP Agent，支持点对点通信和群聊。

    # 点对点
    agent = P2PAgent("alice", port=7700)

    @agent.on_task
    async def handle(task, input_data):
        return {"result": "done"}

    agent.start()   # 打印 ACP URI，分享给对方

    result = await agent.send("acp://192.168.1.5:7701/bob", "Do X", {"data": 1})

    # 群聊
    group = agent.create_group("study-group")
    await agent.invite(group, "acp://192.168.1.5:7701/bob")
    await agent.group_send(group, {"text": "Hello everyone!"})

    @agent.on_group_message
    async def on_msg(group_id, from_uri, body):
        print(f"[{group_id}] {from_uri}: {body['text']}")
    """

    def __init__(
        self,
        name: str,
        port: int = 7700,
        host: str = None,
        psk: str = None,
        capabilities: list[str] = None,
    ):
        self.name = name
        self.port = port
        self._psk = psk
        self.capabilities = capabilities or []
        self._host = host or _local_ip()
        self.uri = ACPURI(self._host, port, name, self.capabilities, psk)

        # Handlers
        self._task_handler:         Optional[TaskHandler]    = None
        self._chat_handler:         Optional[ChatHandler]    = None
        self._message_handlers:     dict[str, MessageHandler] = {}

        # Groups: group_id → ACPGroup
        self._groups: dict[str, ACPGroup] = {}

    # ── Decorators ────────────────────────────────────────────────────────────

    def on_task(self, func: TaskHandler) -> TaskHandler:
        """处理 task.delegate 消息"""
        self._task_handler = func
        return func

    def on_group_message(self, func: ChatHandler) -> ChatHandler:
        """处理群聊消息：async def handler(group_id, from_uri, body)"""
        self._chat_handler = func
        return func

    def on_message(self, msg_type: str):
        """处理指定类型的消息"""
        def dec(func: MessageHandler):
            self._message_handlers[msg_type] = func
            return func
        return dec

    # ── Point-to-Point ────────────────────────────────────────────────────────

    async def send(
        self,
        to: str,
        task: str,
        input: dict = None,
        constraints: dict = None,
        timeout: float = 30.0,
        correlation_id: str = None,
    ) -> Optional[dict]:
        """
        向另一个 Agent 发送任务请求，返回对方的响应 dict。

        to: 对方的 ACP URI，例如 "acp://192.168.1.5:7701/bob"
        """
        target = ACPURI.parse(to) if isinstance(to, str) else to
        msg = _msg(
            "task.delegate", str(self.uri), str(target),
            {"task": task, "input": input or {}, "constraints": constraints or {}},
            correlation_id=correlation_id or "c_" + uuid.uuid4().hex[:8],
        )
        return await self._post(target.receive_url, msg, target.psk, timeout)

    async def discover(self, uri: str) -> Optional[dict]:
        """查询对方 Agent 的身份信息（名称、能力列表等）"""
        target = ACPURI.parse(uri)
        try:
            import aiohttp
            async with aiohttp.ClientSession() as s:
                async with s.get(target.identity_url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                    return await r.json() if r.status == 200 else None
        except Exception as e:
            log.warning(f"discover({uri}) failed: {e}"); return None

    # ── Group Chat ────────────────────────────────────────────────────────────

    def create_group(self, name: str) -> ACPGroup:
        """
        创建一个群聊，自己作为第一个成员。
        返回 group 对象，调用 group.to_join_uri() 获取邀请链接。

        示例:
            group = agent.create_group("team-alpha")
            print(group.to_join_uri())   # 把这个 URI 分享给其他 Agent
        """
        group_id = f"{name}:{str(self.uri)}"
        group = ACPGroup(group_id=group_id, members=[str(self.uri)])
        self._groups[group_id] = group
        log.info(f"Created group: {group_id}")
        return group

    async def join_group(self, join_uri: str) -> ACPGroup:
        """
        通过邀请 URI 加入群聊（其他人 create_group 后通过 to_join_uri() 生成的链接）。
        自动通知所有现有成员你加入了。

        示例:
            group = await agent.join_group("acpgroup://study-group:acp://...?members=...")
        """
        group = ACPGroup.from_join_uri(join_uri)
        group.add_member(str(self.uri))
        self._groups[group.group_id] = group

        # 通知所有现有成员
        notify_msg_body = {
            "group_id": group.group_id,
            "action": "member_joined",
            "new_member": str(self.uri),
            "all_members": group.members,
        }
        await self._broadcast_to_group(group, "group.member_joined", notify_msg_body,
                                       exclude=str(self.uri))
        log.info(f"Joined group {group.group_id}, notified {len(group.members)-1} members")
        return group

    async def invite(self, group: ACPGroup, peer_uri: str) -> bool:
        """
        邀请另一个 Agent 加入群聊（推送方式，不需要对方主动扫 URI）。
        对方会收到 group.invite 消息，SDK 自动处理加入逻辑。

        示例:
            await agent.invite(group, "acp://192.168.1.5:7701/bob")
        """
        target = ACPURI.parse(peer_uri)
        invite_msg = _msg(
            "group.invite", str(self.uri), peer_uri,
            {
                "group_id": group.group_id,
                "join_uri": group.to_join_uri(),
                "invited_by": str(self.uri),
                "members": group.members,
            }
        )
        result = await self._post(target.receive_url, invite_msg, target.psk, 10.0)
        if result:
            group.add_member(peer_uri)
            # 通知其他成员有新人加入
            await self._broadcast_to_group(group, "group.member_joined", {
                "group_id": group.group_id,
                "action": "member_joined",
                "new_member": peer_uri,
                "all_members": group.members,
            }, exclude=peer_uri)
            return True
        return False

    async def group_send(
        self,
        group: "ACPGroup | str",
        body: dict,
        exclude_self: bool = True,
    ) -> list[dict]:
        """
        向群里所有成员广播消息。

        group:  ACPGroup 对象，或 group_id 字符串
        body:   消息内容，例如 {"text": "Hello!"}，可以是任意 dict
        返回:   所有成员的响应列表

        示例:
            await agent.group_send(group, {"text": "大家好！"})
            await agent.group_send(group, {"text": "有人知道这个问题吗？", "type": "question"})
        """
        if isinstance(group, str):
            group = self._groups.get(group)
            if not group:
                raise ValueError(f"Group not found: {group}")

        results = []
        for member_uri in group.members:
            if exclude_self and member_uri == str(self.uri):
                continue
            msg = _msg(
                "group.message", str(self.uri), member_uri,
                {"group_id": group.group_id, **body},
                correlation_id="grp_" + uuid.uuid4().hex[:8],
            )
            try:
                target = ACPURI.parse(member_uri)
                r = await self._post(target.receive_url, msg, target.psk, 10.0)
                results.append({"to": member_uri, "result": r})
            except Exception as e:
                log.warning(f"group_send to {member_uri} failed: {e}")
                results.append({"to": member_uri, "error": str(e)})
        return results

    def get_group(self, group_id: str) -> Optional[ACPGroup]:
        return self._groups.get(group_id)

    async def _broadcast_to_group(
        self, group: ACPGroup, msg_type: str, body: dict,
        exclude: str = None
    ):
        for member_uri in group.members:
            if member_uri == str(self.uri): continue
            if exclude and member_uri == exclude: continue
            target = ACPURI.parse(member_uri)
            msg = _msg(msg_type, str(self.uri), member_uri, body)
            try:
                await self._post(target.receive_url, msg, target.psk, 5.0)
            except Exception as e:
                log.warning(f"broadcast to {member_uri} failed: {e}")

    # ── HTTP transport ────────────────────────────────────────────────────────

    async def _post(self, url: str, msg: dict, psk: str, timeout: float) -> Optional[dict]:
        try:
            import aiohttp
        except ImportError:
            raise ImportError("pip install aiohttp")
        headers = {"Content-Type": "application/json"}
        if psk: headers["X-ACP-PSK"] = psk
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(url, json=msg, headers=headers,
                                  timeout=aiohttp.ClientTimeout(total=timeout)) as r:
                    if r.status == 200:   return await r.json()
                    elif r.status == 202: return None
                    else:
                        log.error(f"POST {url} → {r.status}: {(await r.text())[:200]}")
                        return None
        except aiohttp.ClientConnectorError as e:
            raise ConnectionError(f"Cannot reach {url}: {e}")

    # ── Server ────────────────────────────────────────────────────────────────

    def start(self, block: bool = True, print_uri: bool = True):
        """启动 Agent，开始监听消息"""
        if print_uri:
            print(f"\n🔗 ACP URI: {self.uri}")
            print(f"   把这个 URI 分享给要与你通信的 Agent\n")
        if block:
            asyncio.run(self._run_server())
        else:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._run_server())
            except RuntimeError:
                asyncio.get_event_loop().create_task(self._run_server())

    async def _run_server(self):
        try:
            from aiohttp import web
        except ImportError:
            raise ImportError("pip install aiohttp")
        app = web.Application()
        app.router.add_post("/acp/v1/receive",  self._handle_receive)
        app.router.add_get( "/acp/v1/identity", self._handle_identity)
        app.router.add_get( "/acp/v1/health",   self._handle_health)
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", self.port).start()
        log.info(f"ACP-P2P: {self.name} on 0.0.0.0:{self.port}")
        try:
            while True: await asyncio.sleep(3600)
        finally:
            await runner.cleanup()

    async def _handle_receive(self, request):
        from aiohttp import web
        if self._psk and request.headers.get("X-ACP-PSK", "") != self._psk:
            return web.json_response({"error": "Unauthorized"}, status=401)
        try:
            msg = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        msg_type = msg.get("type", "")
        log.debug(f"[{self.name}] ← {msg_type} from {msg.get('from','?')[:40]}")

        reply = await self._route(msg)
        if reply:
            return web.json_response(reply, status=200)
        return web.json_response({"success": True}, status=202)

    async def _route(self, msg: dict) -> Optional[dict]:
        t = msg.get("type", "")

        # Group messages
        if t == "group.message":
            await self._on_group_message(msg)
            return None

        if t == "group.invite":
            return await self._on_group_invite(msg)

        if t == "group.member_joined":
            self._on_member_joined(msg)
            return None

        # Task
        if t == "task.delegate":
            return await self._handle_task(msg)

        # Hello
        if t == "agent.hello":
            return _msg("agent.hello", str(self.uri), msg["from"],
                        {"name": self.name, "capabilities": self.capabilities},
                        reply_to=msg["id"])

        # Custom handler
        if t in self._message_handlers:
            return await self._message_handlers[t](msg)

        return None  # Unknown type, 202

    async def _handle_task(self, msg: dict) -> Optional[dict]:
        if not self._task_handler:
            return _msg("error", str(self.uri), msg["from"],
                        {"code": "acp.capability_missing", "message": "No task handler"},
                        reply_to=msg["id"])
        try:
            output = await self._task_handler(msg["body"].get("task",""), msg["body"].get("input",{}))
            return _msg("task.result", str(self.uri), msg["from"],
                        {"status": "success", "output": output or {}},
                        reply_to=msg["id"], correlation_id=msg.get("correlation_id"))
        except Exception as e:
            log.exception(f"task handler error")
            return _msg("error", str(self.uri), msg["from"],
                        {"code": "acp.handler_error", "message": str(e)},
                        reply_to=msg["id"])

    async def _on_group_message(self, msg: dict):
        group_id = msg["body"].get("group_id", "")
        # 确保我们知道这个群
        if group_id not in self._groups:
            # 自动创建（来自邀请后的消息）
            self._groups[group_id] = ACPGroup(group_id=group_id, members=[str(self.uri), msg["from"]])
        if self._chat_handler:
            body = {k: v for k, v in msg["body"].items() if k != "group_id"}
            await self._chat_handler(group_id, msg["from"], body)

    async def _on_group_invite(self, msg: dict) -> dict:
        group = ACPGroup.from_join_uri(msg["body"]["join_uri"])
        group.add_member(str(self.uri))
        self._groups[group.group_id] = group
        log.info(f"Joined group {group.group_id} via invite from {msg['from']}")
        # 触发 chat handler（通知自己加入了）
        if self._chat_handler:
            asyncio.get_event_loop().create_task(
                self._chat_handler(group.group_id, "system",
                                   {"text": f"You joined group {group.group_id}"})
            )
        return _msg("group.invite_ack", str(self.uri), msg["from"],
                    {"status": "joined", "group_id": group.group_id},
                    reply_to=msg["id"])

    def _on_member_joined(self, msg: dict):
        group_id = msg["body"].get("group_id", "")
        new_member = msg["body"].get("new_member", "")
        all_members = msg["body"].get("all_members", [])
        if group_id in self._groups:
            self._groups[group_id].members = all_members
            log.info(f"Group {group_id}: new member {new_member}")

    def _handle_identity(self, request):
        from aiohttp import web
        return web.json_response({
            "uri": str(self.uri), "name": self.name,
            "capabilities": self.capabilities, "acp_version": "0.1",
            "protocol": "acp-p2p", "groups": list(self._groups.keys()),
        })

    def _handle_health(self, request):
        from aiohttp import web
        return web.json_response({"status": "ok", "name": self.name, "uri": str(self.uri)})

    # ── Context manager ────────────────────────────────────────────────────────

    async def __aenter__(self):
        loop = asyncio.get_event_loop()
        self._server_task = loop.create_task(self._run_server())
        await asyncio.sleep(0.15)  # 等服务器启动
        return self

    async def __aexit__(self, *args):
        if hasattr(self, "_server_task"):
            self._server_task.cancel()
