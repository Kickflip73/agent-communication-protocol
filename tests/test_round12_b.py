#!/usr/bin/env python3
"""
ACP Round 12 — 场景 B：团队协作（Orchestrator → Worker1 + Worker2）
=======================================================================
端口规划（HTTP = WS + 100）：
  Orchestrator: WS=8011, HTTP=8111
  Worker1:      WS=8012, HTTP=8112
  Worker2:      WS=8013, HTTP=8113

测试内容：
  1. Orchestrator 发任务给 Worker1
  2. Orchestrator 发任务给 Worker2
  3. Worker1 回复结果给 Orchestrator
  4. Worker2 回复结果给 Orchestrator
  5. 验证所有消息收到，server_seq 单调递增

运行: pytest tests/test_round12_b.py -v
"""

import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

# ── 路径配置 ──────────────────────────────────────────────────────────────────
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
RELAY_PY  = os.path.abspath(os.path.join(TESTS_DIR, "..", "relay", "acp_relay.py"))

# ── 代理绕过：在沙箱中 http_proxy 可能指向不可用地址，必须强制绕过 ──────────
# Python urllib 有时不正确处理 no_proxy，用空代理 opener 绕过所有代理
_NO_PROXY_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({})
)

# ── 端口配置 ──────────────────────────────────────────────────────────────────
ORCH_WS   = 8011;  ORCH_HTTP  = 8111
W1_WS     = 8012;  W1_HTTP    = 8112
W2_WS     = 8013;  W2_HTTP    = 8113


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def clean_env():
    """移除代理变量，防止干扰 relay 子进程。"""
    env = os.environ.copy()
    for var in ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY",
                "all_proxy", "ALL_PROXY", "ftp_proxy", "FTP_PROXY",
                "no_proxy", "NO_PROXY"):
        env.pop(var, None)
    return env


def start_relay(name, ws_port):
    """启动 relay 实例；HTTP 端口 = ws_port + 100"""
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
    """等待 relay HTTP 端口就绪。"""
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
    """等待 relay 获取到 link（IP 探测完成）。"""
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


def wait_peer_connected(http_port, peer_id, retries=80, interval=0.5):
    """等待 peer WS 握手完成（probe 发送成功）。"""
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
    """从 JSONL inbox 文件读取所有消息。"""
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
    """检查 inbox 中是否有包含指定文本的消息。"""
    for msg in inbox_messages(agent_name):
        for part in msg.get("parts", []):
            if part.get("content", "") == text:
                return True
    return False


def inbox_count(agent_name):
    return len(inbox_messages(agent_name))


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
def relay_cluster():
    """启动 3 个 relay 实例，结束时清理。"""
    # 清理旧 inbox 文件
    for name in ("Orchestrator", "Worker1", "Worker2"):
        p = f"/tmp/acp_inbox_{name}.jsonl"
        if os.path.exists(p):
            os.remove(p)

    procs = []
    procs.append(start_relay("Orchestrator", ORCH_WS))
    procs.append(start_relay("Worker1",      W1_WS))
    procs.append(start_relay("Worker2",      W2_WS))

    # 等待所有 HTTP 接口就绪
    assert wait_http_ready(ORCH_HTTP),  f"Orchestrator HTTP {ORCH_HTTP} not ready"
    assert wait_http_ready(W1_HTTP),    f"Worker1 HTTP {W1_HTTP} not ready"
    assert wait_http_ready(W2_HTTP),    f"Worker2 HTTP {W2_HTTP} not ready"

    # 等待 link（IP 探测）
    orch_link = wait_link(ORCH_HTTP)
    w1_link   = wait_link(W1_HTTP)
    w2_link   = wait_link(W2_HTTP)

    assert orch_link, f"Orchestrator link not ready (timeout)"
    assert w1_link,   f"Worker1 link not ready (timeout)"
    assert w2_link,   f"Worker2 link not ready (timeout)"

    yield {
        "orch_link": orch_link,
        "w1_link":   w1_link,
        "w2_link":   w2_link,
    }

    for p in procs:
        stop_proc(p)


# ── 测试用例 ──────────────────────────────────────────────────────────────────

class TestScenarioB:
    """场景 B：团队协作（Orchestrator → Worker1 + Worker2 任务分发）"""

    # 存储 peer_id 以便跨测试复用
    _w1_peer_id     = None
    _w2_peer_id     = None
    _orch_peer_from_w1 = None
    _orch_peer_from_w2 = None
    _seq_history    = []

    def test_B01_http_ready(self, relay_cluster):
        """B01: 3 个 relay HTTP 就绪"""
        status_orch, sc1 = http_get(ORCH_HTTP, "/status")
        status_w1,   sc2 = http_get(W1_HTTP,   "/status")
        status_w2,   sc3 = http_get(W2_HTTP,   "/status")

        assert sc1 == 200, f"Orchestrator status {sc1}"
        assert sc2 == 200, f"Worker1 status {sc2}"
        assert sc3 == 200, f"Worker2 status {sc3}"

        assert status_orch.get("agent_name") == "Orchestrator"
        assert status_w1.get("agent_name") == "Worker1"
        assert status_w2.get("agent_name") == "Worker2"

    def test_B02_agent_cards(self, relay_cluster):
        """B02: AgentCard 验证（3 个 relay）"""
        for http_port, name in [(ORCH_HTTP, "Orchestrator"),
                                 (W1_HTTP,   "Worker1"),
                                 (W2_HTTP,   "Worker2")]:
            card, sc = http_get(http_port, "/.well-known/acp.json")
            assert sc == 200, f"{name} AgentCard HTTP {sc}"
            assert "self" in card, f"{name} AgentCard missing 'self'"
            assert card["self"].get("name") == name, \
                f"{name} card name mismatch: {card['self'].get('name')}"

    def test_B03_orch_connects_worker1(self, relay_cluster):
        """B03: Orchestrator 连接 Worker1"""
        w1_link = relay_cluster["w1_link"]
        r, sc = http_post(ORCH_HTTP, "/peers/connect", {
            "link": w1_link, "name": "Worker1"
        })
        assert r.get("ok") and sc == 200, f"Connect failed: {sc} {r}"
        TestScenarioB._w1_peer_id = r.get("peer_id")
        assert TestScenarioB._w1_peer_id, "No peer_id returned"

        # 等待 WS 握手完成
        connected = wait_peer_connected(ORCH_HTTP, TestScenarioB._w1_peer_id)
        assert connected, f"Worker1 WS handshake timeout (peer_id={TestScenarioB._w1_peer_id})"

    def test_B04_orch_connects_worker2(self, relay_cluster):
        """B04: Orchestrator 连接 Worker2"""
        w2_link = relay_cluster["w2_link"]
        r, sc = http_post(ORCH_HTTP, "/peers/connect", {
            "link": w2_link, "name": "Worker2"
        })
        assert r.get("ok") and sc == 200, f"Connect failed: {sc} {r}"
        TestScenarioB._w2_peer_id = r.get("peer_id")
        assert TestScenarioB._w2_peer_id, "No peer_id returned"

        connected = wait_peer_connected(ORCH_HTTP, TestScenarioB._w2_peer_id)
        assert connected, f"Worker2 WS handshake timeout (peer_id={TestScenarioB._w2_peer_id})"

    def test_B05_orch_has_2_peers(self, relay_cluster):
        """B05: Orchestrator 有 2 个 connected peer"""
        peers, _ = http_get(ORCH_HTTP, "/peers")
        connected = [p for p in peers.get("peers", []) if p.get("connected")]
        assert len(connected) == 2, \
            f"Expected 2 connected peers, got {len(connected)}: {connected}"

    def test_B06_orch_send_task_to_worker1(self, relay_cluster):
        """B06: Orchestrator → Worker1 发送任务，验证 server_seq"""
        assert TestScenarioB._w1_peer_id, "w1_peer_id not set (B03 failed?)"
        r, sc = http_post(ORCH_HTTP, f"/peer/{TestScenarioB._w1_peer_id}/send", {
            "role":  "agent",
            "parts": [{"type": "text", "content": "TASK:W1:analyze_dataset"}],
        })
        assert r.get("ok"), f"Send failed: {sc} {r}"
        seq = r.get("server_seq")
        assert seq is not None and seq > 0, f"Invalid server_seq: {seq}"
        TestScenarioB._seq_history.append(seq)

    def test_B07_orch_send_task_to_worker2(self, relay_cluster):
        """B07: Orchestrator → Worker2 发送任务，server_seq 单调递增"""
        assert TestScenarioB._w2_peer_id, "w2_peer_id not set (B04 failed?)"
        r, sc = http_post(ORCH_HTTP, f"/peer/{TestScenarioB._w2_peer_id}/send", {
            "role":  "agent",
            "parts": [{"type": "text", "content": "TASK:W2:generate_report"}],
        })
        assert r.get("ok"), f"Send failed: {sc} {r}"
        seq = r.get("server_seq")
        assert seq is not None, "No server_seq in response"

        # 验证 server_seq 单调递增
        if TestScenarioB._seq_history:
            prev_seq = TestScenarioB._seq_history[-1]
            assert seq > prev_seq, \
                f"server_seq not monotonically increasing: {seq} <= {prev_seq}"
        TestScenarioB._seq_history.append(seq)

    def test_B08_worker1_received_task(self, relay_cluster):
        """B08: Worker1 收到 Orchestrator 任务消息"""
        # 等待消息传递
        deadline = time.time() + 5
        while time.time() < deadline:
            if inbox_has("Worker1", "TASK:W1:analyze_dataset"):
                break
            time.sleep(0.3)

        assert inbox_has("Worker1", "TASK:W1:analyze_dataset"), \
            f"Worker1 inbox missing task. inbox_count={inbox_count('Worker1')}"

    def test_B09_worker2_received_task(self, relay_cluster):
        """B09: Worker2 收到 Orchestrator 任务消息"""
        deadline = time.time() + 5
        while time.time() < deadline:
            if inbox_has("Worker2", "TASK:W2:generate_report"):
                break
            time.sleep(0.3)

        assert inbox_has("Worker2", "TASK:W2:generate_report"), \
            f"Worker2 inbox missing task. inbox_count={inbox_count('Worker2')}"

    def test_B10_worker1_connects_orch(self, relay_cluster):
        """B10: Worker1 连接 Orchestrator（回复通道）"""
        orch_link = relay_cluster["orch_link"]
        r, sc = http_post(W1_HTTP, "/peers/connect", {
            "link": orch_link, "name": "Orchestrator"
        })
        assert r.get("ok") and sc == 200, f"Worker1→Orch connect failed: {sc} {r}"
        TestScenarioB._orch_peer_from_w1 = r.get("peer_id")

        connected = wait_peer_connected(W1_HTTP, TestScenarioB._orch_peer_from_w1)
        assert connected, "Worker1→Orch WS handshake timeout"

    def test_B11_worker2_connects_orch(self, relay_cluster):
        """B11: Worker2 连接 Orchestrator（回复通道）"""
        orch_link = relay_cluster["orch_link"]
        r, sc = http_post(W2_HTTP, "/peers/connect", {
            "link": orch_link, "name": "Orchestrator"
        })
        assert r.get("ok") and sc == 200, f"Worker2→Orch connect failed: {sc} {r}"
        TestScenarioB._orch_peer_from_w2 = r.get("peer_id")

        connected = wait_peer_connected(W2_HTTP, TestScenarioB._orch_peer_from_w2)
        assert connected, "Worker2→Orch WS handshake timeout"

    def test_B12_worker1_reply_to_orch(self, relay_cluster):
        """B12: Worker1 回复结果给 Orchestrator，server_seq 单调递增"""
        assert TestScenarioB._orch_peer_from_w1, "orch_peer_from_w1 not set (B10 failed?)"
        r, sc = http_post(W1_HTTP, f"/peer/{TestScenarioB._orch_peer_from_w1}/send", {
            "role":  "agent",
            "parts": [{"type": "text", "content": "RESULT:W1:done"}],
        })
        assert r.get("ok"), f"Worker1 reply failed: {sc} {r}"
        # W1 has its own server_seq counter (different relay instance)
        seq = r.get("server_seq")
        assert seq is not None and seq > 0, f"Invalid server_seq from W1: {seq}"

    def test_B13_worker2_reply_to_orch(self, relay_cluster):
        """B13: Worker2 回复结果给 Orchestrator"""
        assert TestScenarioB._orch_peer_from_w2, "orch_peer_from_w2 not set (B11 failed?)"
        r, sc = http_post(W2_HTTP, f"/peer/{TestScenarioB._orch_peer_from_w2}/send", {
            "role":  "agent",
            "parts": [{"type": "text", "content": "RESULT:W2:done"}],
        })
        assert r.get("ok"), f"Worker2 reply failed: {sc} {r}"
        seq = r.get("server_seq")
        assert seq is not None and seq > 0, f"Invalid server_seq from W2: {seq}"

    def test_B14_orch_received_worker1_result(self, relay_cluster):
        """B14: Orchestrator 收到 Worker1 回复结果"""
        deadline = time.time() + 5
        while time.time() < deadline:
            if inbox_has("Orchestrator", "RESULT:W1:done"):
                break
            time.sleep(0.3)

        assert inbox_has("Orchestrator", "RESULT:W1:done"), \
            f"Orch missing Worker1 result. inbox_count={inbox_count('Orchestrator')}"

    def test_B15_orch_received_worker2_result(self, relay_cluster):
        """B15: Orchestrator 收到 Worker2 回复结果"""
        deadline = time.time() + 5
        while time.time() < deadline:
            if inbox_has("Orchestrator", "RESULT:W2:done"):
                break
            time.sleep(0.3)

        assert inbox_has("Orchestrator", "RESULT:W2:done"), \
            f"Orch missing Worker2 result. inbox_count={inbox_count('Orchestrator')}"

    def test_B16_orch_server_seq_monotonic(self, relay_cluster):
        """B16: Orchestrator server_seq 单调递增验证（发送 3 条额外消息）"""
        assert TestScenarioB._w1_peer_id, "w1_peer_id not set"
        seqs = list(TestScenarioB._seq_history)

        for i in range(3):
            r, sc = http_post(ORCH_HTTP, f"/peer/{TestScenarioB._w1_peer_id}/send", {
                "role":  "agent",
                "parts": [{"type": "text", "content": f"EXTRA:{i}"}],
            })
            assert r.get("ok"), f"Extra send {i} failed: {sc} {r}"
            seq = r.get("server_seq")
            assert seq is not None
            seqs.append(seq)

        # 验证单调递增
        for i in range(1, len(seqs)):
            assert seqs[i] > seqs[i-1], \
                f"server_seq not monotonic at index {i}: {seqs[i]} <= {seqs[i-1]}"

    def test_B17_messages_received_counters(self, relay_cluster):
        """B17: messages_received 计数正确（BUG-037 回归验证）"""
        # Worker1 应收到来自 Orchestrator 的消息（包括探针 + 任务 + 额外消息）
        peers_orch, _ = http_get(ORCH_HTTP, "/peers")
        all_peers = peers_orch.get("peers", [])

        # 每个 peer 的 messages_received 应 >= 0，不应负数
        for peer_info in all_peers:
            recv = peer_info.get("messages_received", 0)
            assert recv >= 0, \
                f"Negative messages_received for peer {peer_info.get('id')}: {recv}"

        # Orchestrator 全局 messages_received（Worker1/2 各回复了 1 条）
        status_orch, _ = http_get(ORCH_HTTP, "/status")
        total_recv = status_orch.get("messages_received", 0)
        # 应至少收到 Worker1 和 Worker2 各 1 条回复 (+ probe responses)
        assert total_recv >= 2, \
            f"Orchestrator messages_received={total_recv}, expected >= 2"

    def test_B18_messages_sent_counters(self, relay_cluster):
        """B18: messages_sent 计数验证"""
        status_orch, _ = http_get(ORCH_HTTP, "/status")
        sent = status_orch.get("messages_sent", 0)
        # 发了 2 任务 + 3 额外消息 + probes = 至少 2
        assert sent >= 2, f"Orchestrator messages_sent={sent}, expected >= 2"
