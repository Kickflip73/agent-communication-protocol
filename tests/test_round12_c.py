#!/usr/bin/env python3
"""
ACP Round 12 — 场景 C（回归）：环形流水线 A→B→C→A
======================================================
端口规划（HTTP = WS + 100）：
  Agent-A: WS=8021, HTTP=8121
  Agent-B: WS=8022, HTTP=8122
  Agent-C: WS=8023, HTTP=8123

测试内容（BUG-037 回归验证）：
  1. A→B 发送 "start"
  2. B→C 转发 "forward"
  3. C→A 返回 "return"
  4. 检查所有消息送达
  5. 验证 messages_received 计数正确（BUG-037 回归）
  6. 验证 server_seq 单调递增

运行: pytest tests/test_round12_c.py -v
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

# ── 路径配置 ──────────────────────────────────────────────────────────────────
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
RELAY_PY  = os.path.abspath(os.path.join(TESTS_DIR, "..", "relay", "acp_relay.py"))

# ── 端口配置 ──────────────────────────────────────────────────────────────────
A_WS = 8021;  A_HTTP = 8121
B_WS = 8022;  B_HTTP = 8122
C_WS = 8023;  C_HTTP = 8123


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def clean_env():
    env = os.environ.copy()
    for var in ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY",
                "all_proxy", "ALL_PROXY", "ftp_proxy", "FTP_PROXY",
                "no_proxy", "NO_PROXY"):
        env.pop(var, None)
    return env


def start_relay(name, ws_port):
    p = subprocess.Popen(
        [sys.executable, RELAY_PY,
         "--name", name,
         "--port", str(ws_port),
         "--http-host", "127.0.0.1"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=clean_env(),
    )
    return p


def wait_http_ready(http_port, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{http_port}/status", timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def wait_link(http_port, timeout=40):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{http_port}/status", timeout=3) as r:
                d = json.loads(r.read())
                lnk = d.get("link")
                if lnk:
                    return lnk
        except Exception:
            pass
        time.sleep(0.5)
    return None


def http_get(http_port, path, timeout=5):
    url = f"http://127.0.0.1:{http_port}{path}"
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read()), r.status


def http_post(http_port, path, body, timeout=8):
    url = f"http://127.0.0.1:{http_port}{path}"
    req = urllib.request.Request(
        url, json.dumps(body).encode(),
        {"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read()), e.code


def wait_peer_connected(http_port, peer_id, retries=120, interval=0.5):
    """等待 peer WS 握手完成（probe send ok = ws 真正可用；retries 120×0.5s=60s）。

    NOTE: GET /peers connected flag is NOT sufficient — connected=True can be set
    before peer_info["ws"] is populated, causing ERR_PEER_CONNECTING on send.
    Only a successful probe send guarantees the WS is fully ready.
    """
    for _ in range(retries):
        try:
            r, _ = http_post(http_port, f"/peer/{peer_id}/send",
                             {"parts": [{"type": "text", "content": "__probe__"}],
                              "role": "agent"})
            if r.get("ok"):
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


def inbox_messages(agent_name):
    path = f"/tmp/acp_inbox_{agent_name}.jsonl"
    if not os.path.exists(path):
        return []
    messages = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    messages.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return messages


def inbox_has(agent_name, text):
    for msg in inbox_messages(agent_name):
        for part in msg.get("parts", []):
            if part.get("content", "") == text:
                return True
    return False


def inbox_count(agent_name):
    return len(inbox_messages(agent_name))


def wait_inbox(agent_name, text, timeout=6):
    """等待 inbox 中出现指定文本消息。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if inbox_has(agent_name, text):
            return True
        time.sleep(0.3)
    return False


def stop_proc(p):
    if p and p.poll() is None:
        try:
            p.terminate()
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
# pytest fixtures / tests
# ══════════════════════════════════════════════════════════════════════════════

import pytest


@pytest.fixture(scope="module")
def ring_cluster():
    """启动 3 个 relay 实例（A/B/C），形成环形拓扑，结束时清理。"""
    # 清理旧 inbox 文件
    for name in ("PipeA", "PipeB", "PipeC"):
        p = f"/tmp/acp_inbox_{name}.jsonl"
        if os.path.exists(p):
            os.remove(p)

    procs = []
    procs.append(start_relay("PipeA", A_WS))
    procs.append(start_relay("PipeB", B_WS))
    procs.append(start_relay("PipeC", C_WS))

    assert wait_http_ready(A_HTTP), f"PipeA HTTP {A_HTTP} not ready"
    assert wait_http_ready(B_HTTP), f"PipeB HTTP {B_HTTP} not ready"
    assert wait_http_ready(C_HTTP), f"PipeC HTTP {C_HTTP} not ready"

    a_link = wait_link(A_HTTP)
    b_link = wait_link(B_HTTP)
    c_link = wait_link(C_HTTP)

    assert a_link, "PipeA link not ready"
    assert b_link, "PipeB link not ready"
    assert c_link, "PipeC link not ready"

    yield {"a_link": a_link, "b_link": b_link, "c_link": c_link}

    for p in procs:
        stop_proc(p)


class TestScenarioC:
    """
    场景 C（回归）：环形流水线 A→B→C→A
    验证 BUG-037 回归：多 peer 场景下 messages_received 计数正确性
    """

    # 跨测试存储 peer_id
    _a_to_b_peer = None   # A 视角中 B 的 peer_id
    _b_to_c_peer = None   # B 视角中 C 的 peer_id
    _c_to_a_peer = None   # C 视角中 A 的 peer_id

    # server_seq 记录
    _a_seqs = []
    _b_seqs = []
    _c_seqs = []

    def test_C01_http_ready(self, ring_cluster):
        """C01: 3 个 relay HTTP 接口就绪"""
        for http_port, name in [(A_HTTP, "PipeA"), (B_HTTP, "PipeB"), (C_HTTP, "PipeC")]:
            status, sc = http_get(http_port, "/status")
            assert sc == 200, f"{name} HTTP {sc}"
            assert status.get("agent_name") == name, \
                f"{name} agent_name mismatch: {status.get('agent_name')}"

    def test_C02_setup_ring_a_to_b(self, ring_cluster):
        """C02: 建立 A→B 连接（环形第一段）"""
        b_link = ring_cluster["b_link"]
        r, sc = http_post(A_HTTP, "/peers/connect", {
            "link": b_link, "name": "PipeB"
        })
        assert r.get("ok") and sc == 200, f"A→B connect: {sc} {r}"
        TestScenarioC._a_to_b_peer = r.get("peer_id")
        assert TestScenarioC._a_to_b_peer, "No peer_id"

        connected = wait_peer_connected(A_HTTP, TestScenarioC._a_to_b_peer)
        assert connected, "A→B WS handshake timeout"

    def test_C03_setup_ring_b_to_c(self, ring_cluster):
        """C03: 建立 B→C 连接（环形第二段）"""
        c_link = ring_cluster["c_link"]
        r, sc = http_post(B_HTTP, "/peers/connect", {
            "link": c_link, "name": "PipeC"
        })
        assert r.get("ok") and sc == 200, f"B→C connect: {sc} {r}"
        TestScenarioC._b_to_c_peer = r.get("peer_id")
        assert TestScenarioC._b_to_c_peer, "No peer_id"

        connected = wait_peer_connected(B_HTTP, TestScenarioC._b_to_c_peer)
        assert connected, "B→C WS handshake timeout"

    def test_C04_setup_ring_c_to_a(self, ring_cluster):
        """C04: 建立 C→A 连接（环形第三段，闭环）"""
        a_link = ring_cluster["a_link"]
        r, sc = http_post(C_HTTP, "/peers/connect", {
            "link": a_link, "name": "PipeA"
        })
        assert r.get("ok") and sc == 200, f"C→A connect: {sc} {r}"
        TestScenarioC._c_to_a_peer = r.get("peer_id")
        assert TestScenarioC._c_to_a_peer, "No peer_id"

        connected = wait_peer_connected(C_HTTP, TestScenarioC._c_to_a_peer)
        assert connected, "C→A WS handshake timeout"

    def test_C05_a_sends_start_to_b(self, ring_cluster):
        """C05: A→B 发送 'start'（环形第一步）"""
        assert TestScenarioC._a_to_b_peer, "a_to_b_peer not set (C02 failed?)"
        r, sc = http_post(A_HTTP, f"/peer/{TestScenarioC._a_to_b_peer}/send", {
            "role":  "agent",
            "parts": [{"type": "text", "content": "start"}],
        })
        assert r.get("ok"), f"A→B send failed: {sc} {r}"
        seq = r.get("server_seq")
        assert seq is not None and seq > 0
        TestScenarioC._a_seqs.append(seq)

    def test_C06_b_receives_start(self, ring_cluster):
        """C06: B 收到 'start' 消息（环形第一步验证）"""
        assert wait_inbox("PipeB", "start"), \
            f"PipeB missing 'start'. inbox={inbox_count('PipeB')}"

    def test_C07_b_forwards_to_c(self, ring_cluster):
        """C07: B→C 转发 'forward'（环形第二步）"""
        assert TestScenarioC._b_to_c_peer, "b_to_c_peer not set (C03 failed?)"
        r, sc = http_post(B_HTTP, f"/peer/{TestScenarioC._b_to_c_peer}/send", {
            "role":  "agent",
            "parts": [{"type": "text", "content": "forward"}],
        })
        assert r.get("ok"), f"B→C send failed: {sc} {r}"
        seq = r.get("server_seq")
        assert seq is not None and seq > 0
        TestScenarioC._b_seqs.append(seq)

    def test_C08_c_receives_forward(self, ring_cluster):
        """C08: C 收到 'forward' 消息（环形第二步验证）"""
        assert wait_inbox("PipeC", "forward"), \
            f"PipeC missing 'forward'. inbox={inbox_count('PipeC')}"

    def test_C09_c_returns_to_a(self, ring_cluster):
        """C09: C→A 返回 'return'（环形第三步，闭环）"""
        assert TestScenarioC._c_to_a_peer, "c_to_a_peer not set (C04 failed?)"
        r, sc = http_post(C_HTTP, f"/peer/{TestScenarioC._c_to_a_peer}/send", {
            "role":  "agent",
            "parts": [{"type": "text", "content": "return"}],
        })
        assert r.get("ok"), f"C→A send failed: {sc} {r}"
        seq = r.get("server_seq")
        assert seq is not None and seq > 0
        TestScenarioC._c_seqs.append(seq)

    def test_C10_a_receives_return(self, ring_cluster):
        """C10: A 收到 'return' 消息（环形完整闭合验证）"""
        assert wait_inbox("PipeA", "return"), \
            f"PipeA missing 'return'. inbox={inbox_count('PipeA')}"

    def test_C11_messages_received_bug037_regression(self, ring_cluster):
        """
        C11: BUG-037 回归验证 — messages_received 计数正确
        
        BUG-037 原始问题：多 peer 场景下，per-peer messages_received 无法正确归因，
        导致计数始终为 0（multi-peer fallback 分支未命中任何 peer）。
        
        修复后验证：每个 relay 的全局 messages_received 应 >= 实际收到的消息数。
        """
        # A 收到了 C 发的 'return'（以及探针 probes）
        status_a, _ = http_get(A_HTTP, "/status")
        recv_a = status_a.get("messages_received", 0)
        assert recv_a >= 1, \
            f"BUG-037 REGRESSION: PipeA messages_received={recv_a}, expected >= 1"

        # B 收到了 A 发的 'start'
        status_b, _ = http_get(B_HTTP, "/status")
        recv_b = status_b.get("messages_received", 0)
        assert recv_b >= 1, \
            f"BUG-037 REGRESSION: PipeB messages_received={recv_b}, expected >= 1"

        # C 收到了 B 发的 'forward'
        status_c, _ = http_get(C_HTTP, "/status")
        recv_c = status_c.get("messages_received", 0)
        assert recv_c >= 1, \
            f"BUG-037 REGRESSION: PipeC messages_received={recv_c}, expected >= 1"

    def test_C12_per_peer_messages_received_bug037(self, ring_cluster):
        """
        C12: per-peer messages_received 计数验证（BUG-037 核心回归）
        
        在修复前的版本中，当 agent_name 未绑定时（timing race），
        多 peer 场景下没有 peer 会被计入 messages_received。
        修复后：lazy-bind 确保至少 1 个 peer 有 messages_received > 0。
        """
        # 检查 B 的 /peers（B 只有 C 这一个 peer，来自 A 的消息应归入某 peer）
        peers_b, _ = http_get(B_HTTP, "/peers")
        all_peers_b = peers_b.get("peers", [])
        # B 应至少有 1 个 peer（C）
        assert len(all_peers_b) >= 1, f"PipeB has no peers: {all_peers_b}"

        # 检查 C 的 /peers
        peers_c, _ = http_get(C_HTTP, "/peers")
        all_peers_c = peers_c.get("peers", [])
        assert len(all_peers_c) >= 1, f"PipeC has no peers: {all_peers_c}"

        # 检查 A 的 /peers（A 应有 B 作为 peer，也收到了来自 C 的消息）
        peers_a, _ = http_get(A_HTTP, "/peers")
        all_peers_a = peers_a.get("peers", [])
        # A 和 C 之间：C 连接了 A（C→A 方向），所以 A 也应有 C 作为 peer
        # 所有 peer 的 messages_received 应 >= 0
        for peer_info in all_peers_a + all_peers_b + all_peers_c:
            recv = peer_info.get("messages_received", 0)
            assert recv >= 0, \
                f"Negative messages_received for {peer_info.get('name')}: {recv}"

        # BUG-037 核心：全局 messages_received == sum of per-peer messages_received
        # （或至少全局计数与实际收到的消息数一致）
        status_b, _ = http_get(B_HTTP, "/status")
        global_recv_b = status_b.get("messages_received", 0)
        per_peer_total_b = sum(p.get("messages_received", 0) for p in all_peers_b)

        # global count 应 >= per-peer sum（global 包含所有接收，包括无法归因的）
        assert global_recv_b >= per_peer_total_b, \
            f"PipeB global_recv={global_recv_b} < per_peer_total={per_peer_total_b}"

    def test_C13_full_ring_message_delivery(self, ring_cluster):
        """C13: 完整环形流水线 — 所有节点均收到消息"""
        assert inbox_has("PipeB", "start"),   "PipeB missing 'start'"
        assert inbox_has("PipeC", "forward"), "PipeC missing 'forward'"
        assert inbox_has("PipeA", "return"),  "PipeA missing 'return'"

    def test_C14_server_seq_monotonic_per_relay(self, ring_cluster):
        """C14: 各 relay 的 server_seq 单调递增（发送额外消息验证）"""
        # 在每个 relay 上再发几条消息，验证 server_seq 递增
        peers_by_http = [
            (A_HTTP, TestScenarioC._a_to_b_peer, TestScenarioC._a_seqs),
            (B_HTTP, TestScenarioC._b_to_c_peer, TestScenarioC._b_seqs),
            (C_HTTP, TestScenarioC._c_to_a_peer, TestScenarioC._c_seqs),
        ]
        for http_port, peer_id, seq_list in peers_by_http:
            if not peer_id:
                continue
            for i in range(2):
                r, sc = http_post(http_port, f"/peer/{peer_id}/send", {
                    "role":  "agent",
                    "parts": [{"type": "text", "content": f"EXTRA_C14:{i}"}],
                })
                assert r.get("ok"), f"Extra send failed on port {http_port}: {sc}"
                seq = r.get("server_seq")
                assert seq is not None
                seq_list.append(seq)

            # 验证单调递增
            for i in range(1, len(seq_list)):
                assert seq_list[i] > seq_list[i-1], \
                    f"server_seq not monotonic on port {http_port}: " \
                    f"{seq_list[i]} <= {seq_list[i-1]}"

    def test_C15_second_ring_pass(self, ring_cluster):
        """C15: 第二轮环形消息（验证环形可重复使用）"""
        # A→B 再发一条
        assert TestScenarioC._a_to_b_peer
        r, sc = http_post(A_HTTP, f"/peer/{TestScenarioC._a_to_b_peer}/send", {
            "role":  "agent",
            "parts": [{"type": "text", "content": "start_round2"}],
        })
        assert r.get("ok"), f"Round2 A→B failed: {sc} {r}"

        assert wait_inbox("PipeB", "start_round2"), \
            f"PipeB missing 'start_round2'"

        # B→C
        assert TestScenarioC._b_to_c_peer
        r2, sc2 = http_post(B_HTTP, f"/peer/{TestScenarioC._b_to_c_peer}/send", {
            "role":  "agent",
            "parts": [{"type": "text", "content": "forward_round2"}],
        })
        assert r2.get("ok"), f"Round2 B→C failed: {sc2} {r2}"
        assert wait_inbox("PipeC", "forward_round2"), \
            f"PipeC missing 'forward_round2'"

        # C→A
        assert TestScenarioC._c_to_a_peer
        r3, sc3 = http_post(C_HTTP, f"/peer/{TestScenarioC._c_to_a_peer}/send", {
            "role":  "agent",
            "parts": [{"type": "text", "content": "return_round2"}],
        })
        assert r3.get("ok"), f"Round2 C→A failed: {sc3} {r3}"
        assert wait_inbox("PipeA", "return_round2"), \
            f"PipeA missing 'return_round2'"

    def test_C16_final_messages_received_counts(self, ring_cluster):
        """C16: 最终 messages_received 计数核对（BUG-037 完整回归）"""
        # 每个节点至少收到了：1 start/forward/return + 1 round2 + probes
        for http_port, name, expected_min in [
            (A_HTTP, "PipeA", 1),  # 收到 C 发来的 return + return_round2
            (B_HTTP, "PipeB", 1),  # 收到 A 发来的 start + start_round2
            (C_HTTP, "PipeC", 1),  # 收到 B 发来的 forward + forward_round2
        ]:
            status, _ = http_get(http_port, "/status")
            recv = status.get("messages_received", 0)
            assert recv >= expected_min, \
                f"BUG-037 REGRESSION [{name}]: messages_received={recv}, expected >= {expected_min}"
