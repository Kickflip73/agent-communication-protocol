#!/usr/bin/env python3
"""
Scenario B — Team Collaboration (Orchestrator → Worker1 + Worker2)

Flow:
1. Start one relay instance (--local mode)
2. Orchestrator, Worker1, Worker2 each connect via WebSocket
3. Orchestrator sends task assignments to Worker1 and Worker2 via POST /peer/{id}/send
4. Worker1 and Worker2 each reply "done" via POST /peer/{id}/send back to Orchestrator
5. Verify all messages are received correctly

Pass criteria:
- All 4 messages delivered (2 assignments + 2 replies)
- Message content matches
- No errors
"""

import sys
import os
import json
import time
import socket
import subprocess
import asyncio
import aiohttp

RELAY = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")


def free_port_pair() -> tuple[int, int]:
    """Return (ws_port, http_port) where both are free."""
    for _ in range(20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            ws = s.getsockname()[1]
        http = ws + 100
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s2:
                s2.bind(("", http))
            return ws, http
        except OSError:
            continue
    raise RuntimeError("Cannot find free port pair")


async def wait_relay(base: str, timeout: float = 15.0):
    deadline = time.time() + timeout
    async with aiohttp.ClientSession() as sess:
        while time.time() < deadline:
            try:
                async with sess.get(f"{base}/status", timeout=aiohttp.ClientTimeout(total=1)) as r:
                    if r.status == 200:
                        return
            except Exception:
                pass
            await asyncio.sleep(0.2)
    raise RuntimeError("Relay did not start")


async def get_ws_url(base: str, ws_port: int) -> str:
    """Fetch relay token from /status and build ws:// URL."""
    async with aiohttp.ClientSession() as sess:
        async with sess.get(f"{base}/status", timeout=aiohttp.ClientTimeout(total=5)) as r:
            data = await r.json()
    # token from relay_token field or from link
    token = data.get("relay_token") or ""
    if not token:
        link = data.get("link") or ""
        if link and "/" in link:
            token = link.rstrip("/").split("/")[-1]
    return f"ws://localhost:{ws_port}/{token}" if token else f"ws://localhost:{ws_port}"


async def get_peer_id_from_status(base: str) -> str:
    """Get our own peer_id from /status (we are the single connected peer on this relay)."""
    async with aiohttp.ClientSession() as sess:
        async with sess.get(f"{base}/status", timeout=aiohttp.ClientTimeout(total=5)) as r:
            data = await r.json()
    # After connection, peer_id might be in peers list or identity
    peers_ep = f"{base}/peers"
    async with aiohttp.ClientSession() as sess:
        async with sess.get(peers_ep, timeout=aiohttp.ClientTimeout(total=5)) as r:
            if r.status == 200:
                pdata = await r.json()
                peers = pdata.get("peers", [])
                if peers:
                    return peers[-1].get("peer_id", "")
    return ""


async def connect_peer(ws_url_with_token: str, name: str) -> tuple:
    """Connect a peer and return (session, ws, peer_id, token)."""
    session = aiohttp.ClientSession()
    ws = await session.ws_connect(ws_url_with_token)
    deadline = time.time() + 10
    peer_id = None
    token = ""
    while time.time() < deadline:
        try:
            msg = await asyncio.wait_for(ws.receive(), timeout=max(0.5, deadline - time.time()))
        except asyncio.TimeoutError:
            break
        if msg.type == aiohttp.WSMsgType.TEXT:
            data = json.loads(msg.data)
            t = data.get("type", "")
            if t == "hello":
                peer_id = data["peer_id"]
                token = data.get("relay_token", "")
                break
            elif t in ("acp.agent_card", "agent_card"):
                # Extract peer_id from identity if present
                ident = data.get("identity", {}) or {}
                pid = ident.get("peer_id") or data.get("peer_id", "")
                if pid:
                    peer_id = pid
                # continue to look for more messages or hello
                break  # agent_card IS the greeting in this relay version
            elif t == "ping":
                continue
    if not peer_id:
        # Last resort: try /peers endpoint
        raise RuntimeError(f"{name}: never received peer_id (last msg type={data.get('type') if 'data' in dir() else '?'})")
    print(f"  {name}: connected peer_id={peer_id[:8]}… token={token[:8] if token else '(none)'}…")
    return session, ws, peer_id, token


async def recv_message(ws, name: str, timeout: float = 8.0) -> dict:
    """Wait for a non-ping/non-system message."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        try:
            msg = await asyncio.wait_for(ws.receive(), timeout=min(remaining, 1.5))
        except asyncio.TimeoutError:
            continue
        if msg.type == aiohttp.WSMsgType.TEXT:
            data = json.loads(msg.data)
            mtype = data.get("type", "")
            if mtype not in ("ping", "pong", "acp.agent_card", "agent_card", "hello"):
                print(f"  {name} received: type={mtype} from={str(data.get('from',''))[:8]}…")
                return data
            # skip system messages
        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
            raise RuntimeError(f"{name}: WS closed/error")
    raise asyncio.TimeoutError(f"{name}: no message in {timeout}s")


async def http_send(base: str, to_peer_id: str, payload: dict, token: str = ""):
    """POST /peer/{id}/send"""
    headers = {}
    if token:
        headers["X-Relay-Token"] = token
    async with aiohttp.ClientSession() as sess:
        async with sess.post(
            f"{base}/peer/{to_peer_id}/send",
            json=payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=5),
        ) as r:
            try:
                resp = await r.json()
            except Exception:
                resp = {}
            return r.status, resp


async def run():
    ws_port, http_port = free_port_pair()
    base = f"http://localhost:{http_port}"

    proc = subprocess.Popen(
        [sys.executable, RELAY, "--port", str(ws_port), "--name", "ScenarioBTest", "--local"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    results = {
        "phase": "scenario_b",
        "checks": [],
        "passed": 0,
        "failed": 0,
    }

    def check(name: str, ok: bool, detail: str = ""):
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}" + (f": {detail}" if detail else ""))
        results["checks"].append({"name": name, "ok": ok, "detail": detail})
        if ok:
            results["passed"] += 1
        else:
            results["failed"] += 1

    try:
        await wait_relay(base)
        print("  Relay started OK")

        ws_url_tok = await get_ws_url(base, ws_port)
        print(f"  WS URL: {ws_url_tok}")

        # Connect 3 peers
        o_sess, o_ws, o_id, o_tok = await connect_peer(ws_url_tok, "Orchestrator")
        # Wait for relay to register the peer before next connect
        await asyncio.sleep(0.3)
        w1_sess, w1_ws, w1_id, w1_tok = await connect_peer(ws_url_tok, "Worker1")
        await asyncio.sleep(0.3)
        w2_sess, w2_ws, w2_id, w2_tok = await connect_peer(ws_url_tok, "Worker2")
        await asyncio.sleep(0.3)

        check("3 peers connected",
              all(p for p in [o_id, w1_id, w2_id]),
              f"Orch={o_id[:8]} W1={w1_id[:8]} W2={w2_id[:8]}")

        # use tokens from hello or from ws_url
        url_tok = ws_url_tok.rstrip("/").split("/")[-1] if "/" in ws_url_tok else ""
        tok_to_use = o_tok or url_tok

        # Orchestrator sends task to Worker1
        status1, resp1 = await http_send(base, w1_id, {
            "type": "message",
            "from": o_id,
            "content": "Task-A: process dataset alpha",
        }, tok_to_use)
        check("Orchestrator→Worker1 task sent", status1 == 200, f"status={status1} resp={resp1}")

        # Orchestrator sends task to Worker2
        status2, resp2 = await http_send(base, w2_id, {
            "type": "message",
            "from": o_id,
            "content": "Task-B: process dataset beta",
        }, tok_to_use)
        check("Orchestrator→Worker2 task sent", status2 == 200, f"status={status2} resp={resp2}")

        # Worker1 receives task
        w1_msg = await recv_message(w1_ws, "Worker1")
        check("Worker1 received task",
              "dataset alpha" in w1_msg.get("content", "") or "dataset alpha" in str(w1_msg),
              f"msg={str(w1_msg)[:100]}")

        # Worker2 receives task
        w2_msg = await recv_message(w2_ws, "Worker2")
        check("Worker2 received task",
              "dataset beta" in w2_msg.get("content", "") or "dataset beta" in str(w2_msg),
              f"msg={str(w2_msg)[:100]}")

        # Worker1 replies to Orchestrator
        r1_status, _ = await http_send(base, o_id, {
            "type": "message",
            "from": w1_id,
            "content": "Task-A: done",
        }, tok_to_use)
        check("Worker1→Orchestrator reply sent", r1_status == 200)

        # Worker2 replies to Orchestrator
        r2_status, _ = await http_send(base, o_id, {
            "type": "message",
            "from": w2_id,
            "content": "Task-B: done",
        }, tok_to_use)
        check("Worker2→Orchestrator reply sent", r2_status == 200)

        # Orchestrator receives both replies
        o_msg1 = await recv_message(o_ws, "Orchestrator-recv1")
        check("Orchestrator received reply1",
              "done" in str(o_msg1),
              f"msg={str(o_msg1)[:100]}")

        o_msg2 = await recv_message(o_ws, "Orchestrator-recv2")
        check("Orchestrator received reply2",
              "done" in str(o_msg2),
              f"msg={str(o_msg2)[:100]}")

        check("All 8 checks passed", results["failed"] == 0)

        # Close
        for ws in (o_ws, w1_ws, w2_ws):
            await ws.close()
        for sess in (o_sess, w1_sess, w2_sess):
            await sess.close()

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    return results


if __name__ == "__main__":
    print("\n=== Scenario B: Team Collaboration (Orchestrator → Worker1 + Worker2) ===\n")
    results = asyncio.run(run())
    print(f"\n{'='*60}")
    print(f"Scenario B: {results['passed']}/{results['passed']+results['failed']} PASS")
    if results["failed"] > 0:
        print("FAILED checks:")
        for c in results["checks"]:
            if not c["ok"]:
                print(f"  ✗ {c['name']}: {c['detail']}")
        sys.exit(1)
    else:
        print("All checks passed ✅")
        sys.exit(0)
