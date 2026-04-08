#!/usr/bin/env python3
"""
tests/test_scenario_b_team_round23.py
======================================
ACP 测试轮 #23 — 场景 B：团队协作
Orchestrator → Worker1 + Worker2 任务分发（HTTP /peer/{id}/send）

流程：
1. 启动 3 个独立 relay（Orchestrator, Worker1, Worker2）
2. Orchestrator 通过 /peers/connect 连接 Worker1 和 Worker2
3. Orchestrator 通过 POST /peer/{id}/send 向各 Worker 发送任务
4. 验证 Worker1 / Worker2 分别收到各自任务消息
5. Worker1 / Worker2 通过 /peer/{id}/send 回复 Orchestrator
6. 验证 Orchestrator 收到两份 RESULT 消息

测试矩阵（15 个断言）：
  B-01  三个 relay 均能就绪
  B-02  Orchestrator 成功连接 Worker1
  B-03  Orchestrator 成功连接 Worker2
  B-04  Orchestrator peer 列表含 2 个 peer
  B-05  向 Worker1 发送 TASK 返回 ok=True
  B-06  向 Worker2 发送 TASK 返回 ok=True
  B-07  Worker1 在 /messages 中收到含 "chunk_A" 的消息
  B-08  Worker2 在 /messages 中收到含 "chunk_B" 的消息
  B-09  Worker1 成功连接 Orchestrator（或已通过 incoming 连接）
  B-10  Worker2 成功连接 Orchestrator（或已通过 incoming 连接）
  B-11  Worker1 向 Orchestrator 发 RESULT 返回 ok=True
  B-12  Worker2 向 Orchestrator 发 RESULT 返回 ok=True
  B-13  Orchestrator /messages 收到 >=2 条 inbound 消息
  B-14  收到的消息中包含 "RESULT_W1"
  B-15  收到的消息中包含 "RESULT_W2"
"""

import os
import sys
import socket
import subprocess
import time
import pytest
import requests

RELAY = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")

# ── 端口分配 ──────────────────────────────────────────────────────────────────

def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


# ── fixture ────────────────────────────────────────────────────────────────────

class RelayHandle:
    """Lightweight wrapper around a running relay process."""

    def __init__(self, name: str, ws_port: int):
        self.name = name
        self.ws_port = ws_port
        self.http_port = ws_port + 100
        self.base = f"http://127.0.0.1:{self.http_port}"
        # BUG-055 fix (2026-04-08): use --local-only to skip public-IP detection
        # and Cloudflare relay pre-registration (~12s).  Without this, the WS server
        # starts only after those async operations complete, causing Level-1 direct
        # connect to fail with ConnectionRefused and fall back to the external relay.
        self.proc = subprocess.Popen(
            [sys.executable, RELAY, "--port", str(ws_port), "--name", name,
             "--http-host", "127.0.0.1", "--local-only"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def wait_ready(self, timeout: float = 30.0) -> bool:
        """Wait until both the HTTP API and the WebSocket port are accepting connections.

        BUG-055 fix (2026-04-08): host_mode() starts the WS server only after
        get_public_ip() + Cloudflare pre-registration (up to ~12s), while the HTTP
        server starts immediately.  We must wait for the WS port to be open before
        attempting to connect, otherwise Level-1 gets ConnectionRefused and falls
        through to L3 (Cloudflare relay), making the test indirectly depend on the
        external relay and fail when it is unreachable.
        """
        http_ready = False
        ws_ready = False
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not http_ready:
                try:
                    r = requests.get(f"{self.base}/status", timeout=1)
                    if r.status_code == 200:
                        http_ready = True
                except Exception:
                    pass
            if http_ready and not ws_ready:
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(1)
                    s.connect(("127.0.0.1", self.ws_port))
                    s.close()
                    ws_ready = True
                except Exception:
                    pass
            if http_ready and ws_ready:
                return True
            time.sleep(0.2)
        return False

    def relay_token(self) -> str:
        r = requests.get(f"{self.base}/status", timeout=5)
        d = r.json()
        return d.get("relay_token") or d.get("token") or ""

    def acp_link(self) -> str:
        tok = self.relay_token()
        return f"acp://127.0.0.1:{self.ws_port}/{tok}" if tok else ""

    def connect_peer(self, link: str) -> dict:
        r = requests.post(f"{self.base}/peers/connect",
                          json={"link": link}, timeout=10)
        return r.json()

    def peers(self) -> list:
        r = requests.get(f"{self.base}/peers", timeout=5)
        d = r.json()
        return d if isinstance(d, list) else d.get("peers", [])

    def send_to_peer(self, peer_id: str, text: str) -> dict:
        r = requests.post(f"{self.base}/peer/{peer_id}/send",
                          json={"text": text, "role": "agent"}, timeout=10)
        return r.json()

    def messages(self, direction: str = "inbound", timeout: float = 8.0) -> list:
        """Poll /messages until at least one arrives or timeout."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            r = requests.get(f"{self.base}/messages", timeout=5)
            d = r.json()
            msgs = d if isinstance(d, list) else d.get("messages", [])
            filtered = [m for m in msgs if m.get("direction", "inbound") == direction]
            if filtered:
                return filtered
            time.sleep(0.3)
        return []

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()


@pytest.fixture(scope="module")
def three_agents():
    """Start Orchestrator, Worker1, Worker2; yield handles; tear down after module."""
    orch = RelayHandle("orchestrator_r23", _free_port())
    w1   = RelayHandle("worker1_r23",      _free_port())
    w2   = RelayHandle("worker2_r23",      _free_port())

    try:
        # B-01: all three relays ready
        assert orch.wait_ready(), "Orchestrator relay did not start in time (B-01)"
        assert w1.wait_ready(),   "Worker1 relay did not start in time (B-01)"
        assert w2.wait_ready(),   "Worker2 relay did not start in time (B-01)"
        yield orch, w1, w2
    finally:
        orch.stop()
        w1.stop()
        w2.stop()


# ── helpers ────────────────────────────────────────────────────────────────────

def _extract_text(msg: dict) -> str:
    """Extract plain text content from a relay message dict."""
    raw = msg.get("raw", msg)
    parts = raw.get("parts", [])
    if parts:
        return " ".join(p.get("content", "") for p in parts if p.get("type") == "text")
    return raw.get("text", raw.get("content", str(raw)))


def _find_peer_id_for(agent: RelayHandle, target_name_hint: str) -> str | None:
    """Return peer_id from agent's peer list whose name contains target_name_hint."""
    for p in agent.peers():
        name = p.get("name", p.get("agent_name", ""))
        pid  = p.get("peer_id", p.get("id", ""))
        if target_name_hint.lower() in name.lower() or pid:
            return pid
    return None


# ── tests ──────────────────────────────────────────────────────────────────────

def test_b01_all_relays_ready(three_agents):
    """B-01: All three relays are up and responding to /status."""
    orch, w1, w2 = three_agents
    for agent in (orch, w1, w2):
        r = requests.get(f"{agent.base}/status", timeout=5)
        assert r.status_code == 200, f"{agent.name} /status returned {r.status_code}"
        assert r.json().get("acp_version"), f"{agent.name} missing acp_version in status"


def test_b02_orch_connects_worker1(three_agents):
    """B-02: Orchestrator successfully connects to Worker1."""
    orch, w1, _ = three_agents
    link = w1.acp_link()
    assert link, "Worker1 acp link is empty"
    result = orch.connect_peer(link)
    assert result.get("ok") or result.get("status") in ("connected", "already_connected"), \
        f"Connect W1 failed: {result}"


def test_b03_orch_connects_worker2(three_agents):
    """B-03: Orchestrator successfully connects to Worker2."""
    orch, _, w2 = three_agents
    link = w2.acp_link()
    assert link, "Worker2 acp link is empty"
    result = orch.connect_peer(link)
    assert result.get("ok") or result.get("status") in ("connected", "already_connected"), \
        f"Connect W2 failed: {result}"


def test_b04_orch_has_two_peers(three_agents):
    """B-04: Orchestrator peer list contains 2 peers after connecting both workers."""
    orch, _, _ = three_agents
    time.sleep(1.5)  # allow connection handshake
    peers = orch.peers()
    assert len(peers) >= 2, \
        f"Expected >=2 peers in Orchestrator, got {len(peers)}: {peers}"


def test_b05_b06_b07_b08_task_dispatch_and_recv(three_agents):
    """B-05/B-06/B-07/B-08: Orchestrator dispatches tasks; workers receive them."""
    orch, w1, w2 = three_agents
    time.sleep(1.0)

    peers = orch.peers()
    assert len(peers) >= 2, f"Not enough peers to dispatch tasks: {peers}"

    # Map peers by index (order may vary); send to both
    p1_id = peers[0].get("peer_id", peers[0].get("id"))
    p2_id = peers[1].get("peer_id", peers[1].get("id"))

    # BUG-055 fix: wait for peers to be fully WS-ready before sending.
    # connected=True means the peer entry exists; ws_ready=True means the WS
    # channel is established and can accept messages (ERR_PEER_CONNECTING guard).
    def _wait_peer_ws_ready(agent: RelayHandle, peer_id: str, timeout: float = 15.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            for p in agent.peers():
                pid = p.get("peer_id", p.get("id", ""))
                if pid == peer_id and p.get("connected") and p.get("ws_ready") is True:
                    return True
            time.sleep(0.3)
        return False

    assert _wait_peer_ws_ready(orch, p1_id), f"B-05: peer {p1_id} ws_ready not True within 15s"
    assert _wait_peer_ws_ready(orch, p2_id), f"B-06: peer {p2_id} ws_ready not True within 15s"

    # B-05: send TASK to peer0
    r1 = orch.send_to_peer(p1_id, "TASK: analyze data chunk_A")
    assert r1.get("ok"), f"B-05 send to peer0 failed: {r1}"

    # B-06: send TASK to peer1
    r2 = orch.send_to_peer(p2_id, "TASK: analyze data chunk_B")
    assert r2.get("ok"), f"B-06 send to peer1 failed: {r2}"

    # B-07 + B-08: poll both workers
    time.sleep(1.0)
    w1_msgs = w1.messages(timeout=8)
    w2_msgs = w2.messages(timeout=8)

    # One worker gets chunk_A, the other gets chunk_B — order depends on connect order
    all_texts = [_extract_text(m) for m in w1_msgs + w2_msgs]
    assert any("chunk_A" in t for t in all_texts), \
        f"B-07/B-08: chunk_A not found in any worker messages: {all_texts}"
    assert any("chunk_B" in t for t in all_texts), \
        f"B-07/B-08: chunk_B not found in any worker messages: {all_texts}"


def test_b09_b10_workers_connect_orch(three_agents):
    """B-09/B-10: Workers connect back to Orchestrator (for reply routing)."""
    orch, w1, w2 = three_agents
    orch_link = orch.acp_link()
    assert orch_link, "Orchestrator acp link is empty"

    r1 = w1.connect_peer(orch_link)
    r2 = w2.connect_peer(orch_link)

    # Accept ok=True OR already_connected (idempotent)
    ok1 = r1.get("ok") or r1.get("status") in ("connected", "already_connected")
    ok2 = r2.get("ok") or r2.get("status") in ("connected", "already_connected")
    assert ok1, f"B-09 Worker1→Orch connect failed: {r1}"
    assert ok2, f"B-10 Worker2→Orch connect failed: {r2}"
    time.sleep(1.0)


def test_b11_b12_b13_b14_b15_workers_reply(three_agents):
    """B-11..B-15: Workers reply; Orchestrator receives both RESULT messages."""
    orch, w1, w2 = three_agents
    time.sleep(0.5)

    # Find orchestrator's peer_id from each worker's perspective
    def get_orch_peer_id(worker: RelayHandle) -> str | None:
        for p in worker.peers():
            pid  = p.get("peer_id", p.get("id", ""))
            name = p.get("name", p.get("agent_name", ""))
            if "orchestrator" in name.lower() or pid:
                return pid
        return None

    # BUG-055 fix: wait for ws_ready before sending replies
    def _wait_ws_ready(worker: RelayHandle, peer_id: str, timeout: float = 15.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            for p in worker.peers():
                if p.get("peer_id", p.get("id", "")) == peer_id and p.get("ws_ready") is True:
                    return True
            time.sleep(0.3)
        return False

    orch_from_w1 = get_orch_peer_id(w1)
    orch_from_w2 = get_orch_peer_id(w2)

    assert orch_from_w1, "B-11: Worker1 cannot find Orchestrator in peer list"
    assert orch_from_w2, "B-12: Worker2 cannot find Orchestrator in peer list"

    assert _wait_ws_ready(w1, orch_from_w1), f"B-11: W1→Orch ws_ready not True within 15s"
    assert _wait_ws_ready(w2, orch_from_w2), f"B-12: W2→Orch ws_ready not True within 15s"

    # B-11: Worker1 sends result
    r1 = w1.send_to_peer(orch_from_w1, "RESULT_W1: chunk_A done, score=0.92")
    assert r1.get("ok"), f"B-11 Worker1 reply failed: {r1}"

    # B-12: Worker2 sends result
    r2 = w2.send_to_peer(orch_from_w2, "RESULT_W2: chunk_B done, score=0.87")
    assert r2.get("ok"), f"B-12 Worker2 reply failed: {r2}"

    # B-13: Orchestrator receives >=2 inbound messages
    time.sleep(1.5)
    orch_msgs = orch.messages(direction="inbound", timeout=8)
    assert len(orch_msgs) >= 2, \
        f"B-13: Orchestrator expected >=2 inbound msgs, got {len(orch_msgs)}"

    texts = [_extract_text(m) for m in orch_msgs]

    # B-14
    assert any("RESULT_W1" in t for t in texts), \
        f"B-14: RESULT_W1 not found in Orchestrator messages: {texts}"

    # B-15
    assert any("RESULT_W2" in t for t in texts), \
        f"B-15: RESULT_W2 not found in Orchestrator messages: {texts}"


# ── standalone runner ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
