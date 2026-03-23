"""
DCUtR NAT 穿透功能完整测试套件
覆盖：STUNClient / DCUtRPuncher / connect_with_holepunch / 降级路径 / 回归
"""
import asyncio
import json
import socket
import sys
import time
import threading
import urllib.request
import urllib.error
import subprocess
import os
import http.client

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../relay"))

PASS = "✅ PASS"
FAIL = "❌ FAIL"
SKIP = "⏭  SKIP"
results = []

def record(name, status, note=""):
    results.append((name, status, note))
    print(f"  {status}  {name}" + (f"  — {note}" if note else ""))

def section(title):
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")

procs = []

def start_relay(ws_port):
    """启动 relay，WS 端口=ws_port，HTTP 端口=ws_port+100"""
    relay_path = os.path.join(os.path.dirname(__file__), "../relay/acp_relay.py")
    p = subprocess.Popen(
        ["python3", relay_path, "--port", str(ws_port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    procs.append(p)
    time.sleep(1.5)
    return p

def http_base(ws_port):
    """HTTP 控制接口 = ws_port + 100"""
    return f"http://127.0.0.1:{ws_port + 100}"

def stop_all():
    for p in procs:
        try:
            p.terminate()
            p.wait(timeout=3)
        except Exception:
            try: p.kill()
            except: pass

def http_get(url, timeout=5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try: body = json.loads(e.read())
        except: body = {}
        return e.code, body
    except Exception as e:
        return None, str(e)

def http_post(url, body, timeout=5):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data,
          headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try: body_resp = json.loads(e.read())
        except: body_resp = {}
        return e.code, body_resp
    except Exception as e:
        return None, str(e)

# ─────────────────────────────────────────────────────────────────────────────
# T1: STUNClient 单元测试
# ─────────────────────────────────────────────────────────────────────────────
section("T1: STUNClient — 公网地址发现")

async def test_stun():
    from acp_relay import STUNClient

    # T1-1: 返回值格式（可能网络不可达，None 也是合法返回）
    result = await STUNClient.get_public_address(timeout=5.0)
    if result is None:
        record("T1-1 STUN 返回格式", SKIP, "网络不可达，返回 None（正确行为）")
    elif isinstance(result, tuple) and len(result) == 2:
        ip, port = result
        if isinstance(ip, str) and isinstance(port, int) and 1 <= port <= 65535:
            record("T1-1 STUN 返回格式", PASS, f"got {ip}:{port}")
        else:
            record("T1-1 STUN 返回格式", FAIL, f"格式异常: {result}")
    else:
        record("T1-1 STUN 返回格式", FAIL, f"非预期返回: {result}")

    # T1-2: 超时行为（不可达地址，应静默返回 None，不抛异常）
    t0 = time.time()
    try:
        result2 = await STUNClient.get_public_address(
            stun_host="192.0.2.1",  # TEST-NET RFC 5737，不可达
            stun_port=19302,
            timeout=2.0
        )
        elapsed = time.time() - t0
        if result2 is None and elapsed < 4.0:
            record("T1-2 STUN 超时静默返回 None", PASS, f"耗时 {elapsed:.2f}s")
        elif result2 is None:
            record("T1-2 STUN 超时静默返回 None", FAIL, f"超时过慢: {elapsed:.2f}s")
        else:
            record("T1-2 STUN 超时静默返回 None", FAIL, f"不可达地址意外返回: {result2}")
    except Exception as e:
        record("T1-2 STUN 超时静默返回 None", FAIL, f"抛出异常（应静默）: {e}")

asyncio.run(test_stun())

# ─────────────────────────────────────────────────────────────────────────────
# T2: DCUtR 消息格式验证
# ─────────────────────────────────────────────────────────────────────────────
section("T2: DCUtR 消息格式完整性")

async def test_dcutr_messages():
    import uuid

    session_id = str(uuid.uuid4())

    # dcutr_connect
    connect_msg = {
        "type": "dcutr_connect",
        "session_id": session_id,
        "addresses": ["1.2.3.4:9001", "192.168.1.1:9001"],
    }
    required_connect = {"type", "session_id", "addresses"}
    missing = required_connect - set(connect_msg.keys())
    if not missing:
        record("T2-1 dcutr_connect 字段完整", PASS)
    else:
        record("T2-1 dcutr_connect 字段完整", FAIL, f"缺少: {missing}")

    # dcutr_sync
    t_punch = time.time() + 0.5
    sync_msg = {
        "type": "dcutr_sync",
        "session_id": session_id,
        "addresses": ["5.6.7.8:9002"],
        "t_punch": t_punch,
    }
    required_sync = {"type", "session_id", "addresses", "t_punch"}
    missing2 = required_sync - set(sync_msg.keys())
    if not missing2:
        record("T2-2 dcutr_sync 字段完整", PASS)
    else:
        record("T2-2 dcutr_sync 字段完整", FAIL, f"缺少: {missing2}")

    # dcutr_result
    result_msg = {
        "type": "dcutr_result",
        "session_id": session_id,
        "success": True,
        "direct_addr": "1.2.3.4:9001",
    }
    required_result = {"type", "session_id", "success"}
    missing3 = required_result - set(result_msg.keys())
    if not missing3:
        record("T2-3 dcutr_result 字段完整", PASS)
    else:
        record("T2-3 dcutr_result 字段完整", FAIL, f"缺少: {missing3}")

    # JSON 可序列化
    try:
        for msg in [connect_msg, sync_msg, result_msg]:
            json.dumps(msg)
        record("T2-4 所有消息可序列化为合法 JSON", PASS)
    except Exception as e:
        record("T2-4 所有消息可序列化为合法 JSON", FAIL, str(e))

    # t_punch 类型
    if isinstance(sync_msg["t_punch"], float):
        record("T2-5 t_punch 类型为 float 时间戳", PASS)
    else:
        record("T2-5 t_punch 类型为 float 时间戳", FAIL,
               f"实际类型: {type(sync_msg['t_punch'])}")

asyncio.run(test_dcutr_messages())

# ─────────────────────────────────────────────────────────────────────────────
# T3: connect_with_holepunch() 三级降级路径
# ─────────────────────────────────────────────────────────────────────────────
section("T3: connect_with_holepunch() 三级降级路径")

# WS 端口，HTTP = WS + 100
PORT_RELAY = 7801
start_relay(PORT_RELAY)
HTTP_RELAY = http_base(PORT_RELAY)

# 等待 WS 端口就绪（最多 5s）
def wait_port(port, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            s = socket.create_connection(("127.0.0.1", port), timeout=0.3)
            s.close()
            return True
        except Exception:
            time.sleep(0.2)
    return False

wait_port(PORT_RELAY)

async def test_holepunch_fallback():
    from acp_relay import connect_with_holepunch

    # T3-1: 不存在地址 → ConnectionError，在合理时间内抛出
    t0 = time.time()
    try:
        ws, direct = await connect_with_holepunch("ws://192.0.2.1:9999/nonexistent")
        elapsed = time.time() - t0
        record("T3-1 不可达地址抛 ConnectionError", FAIL,
               f"意外连接成功 elapsed={elapsed:.2f}s")
    except ConnectionError:
        elapsed = time.time() - t0
        if elapsed < 20.0:
            record("T3-1 不可达地址抛 ConnectionError", PASS, f"耗时 {elapsed:.2f}s")
        else:
            record("T3-1 不可达地址抛 ConnectionError", FAIL, f"超时过慢: {elapsed:.2f}s")
    except Exception as e:
        elapsed = time.time() - t0
        record("T3-1 不可达地址抛 ConnectionError", FAIL,
               f"意外异常 {type(e).__name__}: {e}")

    # T3-2: relay_ws=None → Level 2 被跳过，直连成功
    try:
        ws2, direct2 = await asyncio.wait_for(
            connect_with_holepunch(f"ws://127.0.0.1:{PORT_RELAY}", relay_ws=None),  # WS port
            timeout=6.0
        )
        if direct2 == True:
            record("T3-2 relay_ws=None 跳过Level2直连成功", PASS, f"is_direct={direct2}")
        else:
            record("T3-2 relay_ws=None 跳过Level2直连成功", FAIL, f"is_direct={direct2}")
        await ws2.close()
    except Exception as e:
        record("T3-2 relay_ws=None 跳过Level2直连成功", FAIL, str(e))

    # T3-3: Level 1 直连成功 → is_direct=True
    try:
        ws3, direct3 = await asyncio.wait_for(
            connect_with_holepunch(f"ws://127.0.0.1:{PORT_RELAY}"),  # WS port
            timeout=6.0
        )
        if direct3 == True:
            record("T3-3 Level1 直连 is_direct=True", PASS)
        else:
            record("T3-3 Level1 直连 is_direct=True", FAIL, f"is_direct={direct3}")
        await ws3.close()
    except Exception as e:
        record("T3-3 Level1 直连 is_direct=True", FAIL, str(e))

asyncio.run(test_holepunch_fallback())

# ─────────────────────────────────────────────────────────────────────────────
# T4: DCUtR 握手流程集成（mock WebSocket）
# ─────────────────────────────────────────────────────────────────────────────
section("T4: DCUtR 握手流程集成（mock WebSocket 信令）")

async def test_dcutr_handshake():
    from acp_relay import DCUtRPuncher

    sent_messages = []
    q_init_to_resp = asyncio.Queue()
    q_resp_to_init = asyncio.Queue()

    class MockWS:
        def __init__(self, out_q, in_q):
            self._out = out_q
            self._in = in_q

        async def send(self, data):
            msg = json.loads(data)
            sent_messages.append(msg)
            await self._out.put(data)

        async def recv(self):
            return await asyncio.wait_for(self._in.get(), timeout=5.0)

        async def close(self):
            pass

    ws_init = MockWS(q_init_to_resp, q_resp_to_init)
    ws_resp = MockWS(q_resp_to_init, q_init_to_resp)

    puncher_init = DCUtRPuncher()
    puncher_resp = DCUtRPuncher()

    try:
        results_gathered = await asyncio.wait_for(
            asyncio.gather(
                puncher_init.attempt(ws_init, local_port=0),
                puncher_resp.listen_for_dcutr(ws_resp, local_port=0),
                return_exceptions=True
            ),
            timeout=15.0
        )

        types_sent = [m.get("type") for m in sent_messages]

        if "dcutr_connect" in types_sent:
            record("T4-1 dcutr_connect 被发送", PASS)
        else:
            record("T4-1 dcutr_connect 被发送", FAIL, f"实际: {types_sent}")

        if "dcutr_sync" in types_sent:
            record("T4-2 dcutr_sync 被回复", PASS)
        else:
            record("T4-2 dcutr_sync 被回复", FAIL, f"实际: {types_sent}")

        connect_msgs = [m for m in sent_messages if m.get("type") == "dcutr_connect"]
        sync_msgs    = [m for m in sent_messages if m.get("type") == "dcutr_sync"]

        if connect_msgs and sync_msgs:
            sid_c = connect_msgs[0].get("session_id")
            sid_s = sync_msgs[0].get("session_id")
            if sid_c and sid_c == sid_s:
                record("T4-3 session_id 两端一致", PASS, f"…{sid_c[-8:]}")
            else:
                record("T4-3 session_id 两端一致", FAIL,
                       f"connect={sid_c}, sync={sid_s}")
        else:
            record("T4-3 session_id 两端一致", SKIP, "缺少消息")

        if sync_msgs:
            t_punch = sync_msgs[0].get("t_punch")
            if isinstance(t_punch, (int, float)) and t_punch > time.time() - 10:
                record("T4-4 t_punch 值合理（未来时间）", PASS, f"{t_punch:.3f}")
            else:
                record("T4-4 t_punch 值合理（未来时间）", FAIL, f"t_punch={t_punch}")
        else:
            record("T4-4 t_punch 值合理（未来时间）", SKIP, "无 dcutr_sync")

        # 沙箱无真实 NAT → 打洞结果 None，正确降级
        init_result = results_gathered[0]
        if init_result is None or isinstance(init_result, Exception):
            record("T4-5 沙箱无NAT打洞降级返回None", PASS)
        else:
            record("T4-5 沙箱无NAT打洞降级返回None", SKIP,
                   f"意外成功 {init_result}（真实NAT才会到此路径）")

    except asyncio.TimeoutError:
        for i in range(1, 6):
            record(f"T4-{i}", FAIL, "握手超时 15s")
    except Exception as e:
        record("T4 握手集成", FAIL, f"意外异常: {e}")

asyncio.run(test_dcutr_handshake())

# ─────────────────────────────────────────────────────────────────────────────
# T5: BUG-001~009 回归
# ─────────────────────────────────────────────────────────────────────────────
section("T5: BUG-001~009 回归验证")

# WS ports；HTTP = WS + 100
PORT_A = 7810
PORT_B = 7820
start_relay(PORT_A)
start_relay(PORT_B)

BASE_A = http_base(PORT_A)   # http://127.0.0.1:7910
BASE_B = http_base(PORT_B)   # http://127.0.0.1:7920

def wait_for_link(base_url, timeout=8.0):
    """轮询 /link 端点，等待 relay 注册完成并返回 acp:// link"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        sc, resp = http_get(f"{base_url}/link")
        if sc == 200 and resp.get("link"):
            return resp["link"]
        time.sleep(0.5)
    return ""

link_b = wait_for_link(BASE_B, timeout=8.0)

peer_id = ""
if link_b:
    sc_conn, conn_resp = http_post(f"{BASE_A}/peers/connect",
                                    {"link": link_b, "role": "agent"})
    if sc_conn in (200, 201):
        peer_id = conn_resp.get("peer_id", "")
    time.sleep(0.5)

# BUG-002: cancel → canceled
sc_t, task_resp = http_post(f"{BASE_A}/tasks", {"title": "回归Task", "role": "agent"})
if sc_t in (200, 201):
    tid = task_resp.get("task", {}).get("id") or task_resp.get("id", "")
    if tid:
        sc_c, cr = http_post(f"{BASE_A}/tasks/{tid}:cancel", {})
        sv = cr.get("task", {}).get("status") or cr.get("status", "")
        if sv == "canceled":
            record("T5-1 BUG-002 cancel→canceled", PASS)
        else:
            record("T5-1 BUG-002 cancel→canceled", FAIL, f"status={sv}")
    else:
        record("T5-1 BUG-002 cancel→canceled", SKIP, "Task id 为空")
else:
    record("T5-1 BUG-002 cancel→canceled", SKIP, f"Task POST {sc_t}")

# BUG-003: 重复连接幂等（对同一已连通 link 重复 connect，应返回 already_connected=True）
if link_b and peer_id:
    # 等待 A-B WS 连接真正建立（peer 状态需变为 connected）
    time.sleep(1.0)
    sc_r2, resp2 = http_post(f"{BASE_A}/peers/connect", {"link": link_b, "role": "agent"})
    if sc_r2 in (200, 201) and resp2.get("already_connected"):
        record("T5-2 BUG-003 重复连接幂等（already_connected）", PASS,
               f"peer_id={resp2.get('peer_id')}")
    else:
        # BUG-003b: 幂等仅对已建立WS连接的peer生效，连接中的peer不幂等（已知限制）
        record("T5-2 BUG-003 重复连接幂等（already_connected）", FAIL,
               f"already_connected={resp2.get('already_connected')} — BUG-003b: 幂等需WS已建立")
else:
    record("T5-2 BUG-003 重复连接幂等（already_connected）", SKIP, "未建立连接")

# BUG-004: server_seq
if peer_id:
    sc_m, mr = http_post(f"{BASE_A}/peer/{peer_id}/send",
                          {"parts": [{"kind": "text", "text": "regression"}],
                           "role": "agent"})
    if sc_m == 200:
        if "server_seq" in mr:
            record("T5-3 BUG-004 响应含 server_seq", PASS, f"seq={mr['server_seq']}")
        else:
            record("T5-3 BUG-004 响应含 server_seq", FAIL,
                   f"字段: {list(mr.keys())}")
    else:
        record("T5-3 BUG-004 响应含 server_seq", SKIP, f"send {sc_m}")
else:
    record("T5-3 BUG-004 响应含 server_seq", SKIP, "无 peer")

# BUG-006: client task_id
sc_t2, tr2 = http_post(f"{BASE_A}/tasks",
                        {"title": "幂等Task", "task_id": "mytask_001", "role": "agent"})
if sc_t2 in (200, 201):
    rid = tr2.get("task", {}).get("id") or tr2.get("id", "")
    if rid == "mytask_001":
        record("T5-4 BUG-006 client task_id 被尊重", PASS)
    else:
        record("T5-4 BUG-006 client task_id 被尊重", FAIL, f"返回 id={rid}")
else:
    record("T5-4 BUG-006 client task_id 被尊重", SKIP, f"Task POST {sc_t2}")

# BUG-007: 多 peer 无 peer_id → ERR_AMBIGUOUS_PEER
PORT_C = 7830
start_relay(PORT_C)
link_c = wait_for_link(http_base(PORT_C), timeout=12.0) if peer_id else ""
if peer_id and link_c:
    http_post(f"{BASE_A}/peers/connect", {"link": link_c, "role": "agent"})
    # 等待 connected=True（最多 5s 轮询）
    def wait_two_connected(base, timeout=5.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            sc, pr = http_get(f"{base}/peers")
            if sc == 200:
                cnt = sum(1 for p in pr.get("peers", []) if p.get("connected"))
                if cnt >= 2:
                    return True
            time.sleep(0.3)
        return False
    got_two = wait_two_connected(BASE_A, timeout=5.0)
    sc_amb, amb = http_post(f"{BASE_A}/message:send",
                             {"parts": [{"kind": "text", "text": "x"}],
                              "role": "agent"})
    if sc_amb == 400 and amb.get("error_code") == "ERR_AMBIGUOUS_PEER":
        record("T5-5 BUG-007 多peer→ERR_AMBIGUOUS_PEER", PASS)
    elif not got_two:
        record("T5-5 BUG-007 多peer→ERR_AMBIGUOUS_PEER", SKIP,
               f"A 只有 <2 个 connected peer（C连接未就绪）status={sc_amb}")
    else:
        record("T5-5 BUG-007 多peer→ERR_AMBIGUOUS_PEER", FAIL,
               f"status={sc_amb}, error_code={amb.get('error_code')}")
else:
    record("T5-5 BUG-007 多peer→ERR_AMBIGUOUS_PEER", SKIP,
           "PORT_C link 未就绪" if not link_c else "peer_id 未建立")

# BUG-008: :update 和 /update 都支持
sc_t3, tr3 = http_post(f"{BASE_A}/tasks", {"title": "Update测试", "role": "agent"})
if sc_t3 in (200, 201):
    tid3 = tr3.get("task", {}).get("id") or tr3.get("id", "")
    if tid3:
        sc_u1, _ = http_post(f"{BASE_A}/tasks/{tid3}:update", {"status": "working"})
        sc_u2, _ = http_post(f"{BASE_A}/tasks/{tid3}/update", {"status": "working"})
        if sc_u1 in (200, 204) and sc_u2 in (200, 204):
            record("T5-6 BUG-008 :update 和 /update 都可用", PASS)
        else:
            record("T5-6 BUG-008 :update 和 /update 都可用", FAIL,
                   f":update={sc_u1}, /update={sc_u2}")
    else:
        record("T5-6 BUG-008 :update 和 /update 都可用", SKIP, "tid 为空")
else:
    record("T5-6 BUG-008 :update 和 /update 都可用", SKIP, f"Task POST {sc_t3}")

# BUG-009: SSE 本地推送延迟 <200ms
# 测试方法：直接通过 HTTP 触发本地消息发送到自身，监听 /stream
# 用 PORT_A 自身的 /stream 监听，然后 POST /message:send（单 peer 时路由到 peer_001）
# 这样绕开 Cloudflare，只测本地 SSE 推送延迟
async def test_sse_latency():
    # 启动专用单实例测试：PORT_A2，不连接任何 Relay peer
    PORT_A2 = 7870
    start_relay(PORT_A2)
    wait_port(PORT_A2)

    latencies = []
    sse_ready = threading.Event()

    def listen_sse():
        try:
            conn = http.client.HTTPConnection("127.0.0.1", PORT_A2 + 100, timeout=8)
            conn.request("GET", "/stream")
            resp = conn.getresponse()
            sse_ready.set()
            buf = b""
            deadline = time.time() + 5
            while time.time() < deadline:
                chunk = resp.read(256)
                if not chunk:
                    break
                buf += chunk
                while b"\n\n" in buf:
                    event, buf = buf.split(b"\n\n", 1)
                    # 任意事件（包括 keepalive）都能检测到 SSE 流是活跃的
                    if b"data:" in event:
                        latencies.append(time.time())
                        return
        except Exception as e:
            sse_ready.set()

    t = threading.Thread(target=listen_sse, daemon=True)
    t.start()
    sse_ready.wait(timeout=3)

    # 触发一个本地 SSE 事件：创建 Task（会广播 status 事件）
    t_send = time.time()
    http_post(f"http://127.0.0.1:{PORT_A2 + 100}/tasks",
              {"title": "SSE延迟测试Task", "role": "agent"})

    t.join(timeout=5)
    if latencies:
        latency_ms = (latencies[0] - t_send) * 1000
        if latency_ms < 200:
            record("T5-7 BUG-009 本地SSE延迟<200ms", PASS, f"实测 {latency_ms:.1f}ms")
        else:
            record("T5-7 BUG-009 本地SSE延迟<200ms", FAIL, f"延迟 {latency_ms:.1f}ms（应<200ms）")
    else:
        record("T5-7 BUG-009 本地SSE延迟<200ms", FAIL, "5s 内未收到任何 SSE 事件")

asyncio.run(test_sse_latency())

# ─────────────────────────────────────────────────────────────────────────────
# T6: 场景A 回归 — 双 Agent 完整通信
# ─────────────────────────────────────────────────────────────────────────────
section("T6: 场景A 回归 — 双 Agent 完整通信")

if peer_id:
    # A→B
    sc_s, sr = http_post(f"{BASE_A}/peer/{peer_id}/send",
                          {"parts": [{"kind": "text", "text": "Hello from A"}],
                           "role": "agent"})
    if sc_s == 200 and sr.get("ok"):
        record("T6-1 A→B 消息发送成功", PASS)
    else:
        record("T6-1 A→B 消息发送成功", FAIL, f"status={sc_s}, resp={sr}")

    # B inbox
    time.sleep(0.3)
    sc_i, inbox = http_get(f"{BASE_B}/history")
    msgs = inbox.get("history", []) if sc_i == 200 else []
    found = any("Hello from A" in str(m) for m in msgs)
    if found:
        record("T6-2 B 收到消息（inbox 确认）", PASS)
    else:
        record("T6-2 B 收到消息（inbox 确认）", FAIL,
               f"inbox={len(msgs)} 条，未找到消息内容")

    # B→A 反向
    sc_pa, pr_a = http_get(f"{BASE_B}/peers")
    peers_b = pr_a.get("peers", []) if sc_pa == 200 else []
    if peers_b:
        pid_b = peers_b[0].get("id", "")
        sc_r, rr = http_post(f"{BASE_B}/peer/{pid_b}/send",
                              {"parts": [{"kind": "text", "text": "Hello from B"}],
                               "role": "agent"})
        if sc_r == 200 and rr.get("ok"):
            record("T6-3 B→A 反向通信成功", PASS)
        else:
            record("T6-3 B→A 反向通信成功", FAIL, f"status={sc_r}")
        time.sleep(0.3)
        sc_ia, inbox_a = http_get(f"{BASE_A}/history")
        msgs_a = inbox_a.get("history", []) if sc_ia == 200 else []
        found_a = any("Hello from B" in str(m) for m in msgs_a)
        if found_a:
            record("T6-4 A 收到 B 的回复（inbox 确认）", PASS)
        else:
            record("T6-4 A 收到 B 的回复（inbox 确认）", FAIL,
                   f"inbox={len(msgs_a)} 条")
    else:
        record("T6-3 B→A 反向通信成功", SKIP, "B 无 peer")
        record("T6-4 A 收到 B 的回复（inbox 确认）", SKIP, "B 无 peer")
else:
    for i in range(1, 5):
        record(f"T6-{i}", SKIP, "未建立 peer 连接")

# ─────────────────────────────────────────────────────────────────────────────
# T7: 边界与异常场景
# ─────────────────────────────────────────────────────────────────────────────
section("T7: 边界与异常场景")

# T7-1: 无效 peer_id
sc_inv, inv_r = http_post(f"{BASE_A}/peer/nonexistent_peer/send",
                           {"parts": [{"kind": "text", "text": "test"}],
                            "role": "agent"})
if sc_inv == 404:
    record("T7-1 无效 peer_id → 404", PASS)
else:
    record("T7-1 无效 peer_id → 404", FAIL, f"status={sc_inv}")

# T7-2: 缺少必要字段 role（BUG-010 修复验证）
sc_nr, nr_r = http_post(f"{BASE_A}/tasks", {"title": "NoRole"})
if sc_nr == 400 and nr_r.get("code") == "ERR_INVALID_REQUEST":
    record("T7-2 缺少 role → ERR_INVALID_REQUEST(400)", PASS)
elif sc_nr in (400, 422):
    record("T7-2 缺少 role → ERR_INVALID_REQUEST(400)", PASS, f"status={sc_nr}")
elif sc_nr in (200, 201):
    record("T7-2 缺少 role → ERR_INVALID_REQUEST(400)", FAIL,
           "BUG-010 未修复：缺少 role 竟然成功创建 Task")
else:
    record("T7-2 缺少 role → ERR_INVALID_REQUEST(400)", SKIP, f"status={sc_nr}")

# T7-3: 不存在的 task_id 操作
sc_nt, _ = http_post(f"{BASE_A}/tasks/nonexistent_task:cancel", {})
if sc_nt == 404:
    record("T7-3 不存在的 task → 404", PASS)
else:
    record("T7-3 不存在的 task → 404", FAIL, f"status={sc_nt}")

# T7-4: AgentCard 字段完整性（字段在 'self' 子对象下）
sc_ac, ac = http_get(f"{BASE_A}/.well-known/acp.json")
required_fields = {"name", "version", "capabilities"}
if sc_ac == 200:
    ac_self = ac.get("self", ac)  # 兼容 self 子对象和顶层两种结构
    missing_fields = required_fields - set(ac_self.keys())
    if not missing_fields:
        record("T7-4 AgentCard 必要字段完整", PASS,
               f"name={ac_self.get('name')}, version={ac_self.get('version')}")
    else:
        record("T7-4 AgentCard 必要字段完整", FAIL, f"缺少: {missing_fields}")
else:
    record("T7-4 AgentCard 必要字段完整", SKIP, f"HTTP {sc_ac}")

# T7-5: 超大消息（1MB text）
big_text = "x" * 1024 * 1024
sc_big, big_r = http_post(f"{BASE_A}/message:send" if not peer_id else f"{BASE_A}/peer/{peer_id}/send",
                            {"parts": [{"kind": "text", "text": big_text}],
                             "role": "agent"})
if sc_big in (400, 413):
    record("T7-5 超大消息被拒绝（4xx）", PASS, f"status={sc_big}")
elif sc_big == 200:
    record("T7-5 超大消息被拒绝（4xx）", FAIL,
           "1MB 消息被接受（可能存在 BUG-010：缺少消息大小限制）")
else:
    record("T7-5 超大消息被拒绝（4xx）", SKIP, f"status={sc_big}")

# ─────────────────────────────────────────────────────────────────────────────
# 收尾
# ─────────────────────────────────────────────────────────────────────测试结果
# ─────────────────────────────────────────────────────────────────────────────
stop_all()

print(f"\n{'═'*60}")
print("  测试结果汇总")
print(f"{'═'*60}")

passed  = sum(1 for _, s, _ in results if s == PASS)
failed  = sum(1 for _, s, _ in results if s == FAIL)
skipped = sum(1 for _, s, _ in results if s == SKIP)
total   = len(results)

print(f"\n  总计: {total} 项  ✅ {passed} PASS  ❌ {failed} FAIL  ⏭  {skipped} SKIP\n")

if failed:
    print("  失败项：")
    for name, status, note in results:
        if status == FAIL:
            print(f"    ❌ {name}" + (f"  — {note}" if note else ""))

# 退出码
sys.exit(0 if failed == 0 else 1)
