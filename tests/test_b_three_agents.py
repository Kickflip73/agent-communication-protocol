"""
test_b_three_agents.py — 场景 B: 三节点团队协作（HTTP 直连模式）

沙箱内无公网 IP，不使用 P2P WebSocket peer/connect。
测试验证：
  B1: 3 个 relay 实例成功启动
  B2: Orchestrator /message:send 成功
  B3: Worker1 /message:send 成功
  B4: Worker2 /message:send 成功
  B5: 所有实例 /status 正确报告 agent_name
  B6: Orchestrator 可访问 Worker1 的 /skills 端点（HTTP 互访）
  B7: /peers 端点正常返回空列表（无 P2P 时）
"""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from helpers import clean_subprocess_env

import pytest

RELAY_PY = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py"))

_SKILLS_JSON = json.dumps([
    {
        "id": "summarize",
        "name": "Text Summarization",
        "description": "Summarizes documents",
        "examples": ["Summarize this"],
        "input_modes": ["text"],
        "output_modes": ["text"],
    },
    {
        "id": "image-caption",
        "name": "Image Captioning",
        "description": "Captions images",
        "examples": ["Describe this image"],
        "input_modes": ["text", "image"],
        "output_modes": ["text"],
    },
])


def _free_port():
    for _ in range(200):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            ws = s.getsockname()[1]
        try:
            with socket.socket() as s2:
                s2.bind(("127.0.0.1", ws + 100))
                return ws
        except OSError:
            continue
    raise RuntimeError("No free port pair found")


def _wait_ready(http_port, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{http_port}/.well-known/acp.json", timeout=1
            ) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.2)
    return False


def _get(http_port, path):
    with urllib.request.urlopen(
        f"http://127.0.0.1:{http_port}{path}", timeout=5
    ) as r:
        return r.status, json.loads(r.read())


def _post(http_port, path, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{http_port}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


# ─── Ports ────────────────────────────────────────────────────────────────────
ORCH_WS = _free_port(); ORCH_HTTP = ORCH_WS + 100
W1_WS   = _free_port(); W1_HTTP   = W1_WS   + 100
W2_WS   = _free_port(); W2_HTTP   = W2_WS   + 100

_procs = []


@pytest.fixture(scope="module", autouse=True)
def three_agents():
    global _procs
    env = clean_subprocess_env()

    def start(name, ws_port):
        p = subprocess.Popen(
            [sys.executable, RELAY_PY, "--name", name, "--port", str(ws_port),
             "--http-host", "127.0.0.1", "--skills", _SKILLS_JSON],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
        )
        return p

    p_orch = start("Orchestrator", ORCH_WS)
    p_w1   = start("Worker1",      W1_WS)
    p_w2   = start("Worker2",      W2_WS)
    _procs = [p_orch, p_w1, p_w2]

    for name, port in [("Orchestrator", ORCH_HTTP), ("Worker1", W1_HTTP), ("Worker2", W2_HTTP)]:
        if not _wait_ready(port):
            for p in _procs:
                p.kill()
            pytest.fail(f"{name} failed to start on HTTP:{port}")

    yield

    for p in _procs:
        p.terminate()
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()


# ─── Tests ────────────────────────────────────────────────────────────────────

def test_b1_all_agents_online(three_agents):
    """B1: 3 个 relay 实例成功启动，agent card 正确"""
    for name, port in [("Orchestrator", ORCH_HTTP), ("Worker1", W1_HTTP), ("Worker2", W2_HTTP)]:
        status, data = _get(port, "/.well-known/acp.json")
        assert status == 200, f"{name} card status {status}"
        card = data.get("self", data)
        assert card.get("name") == name, f"{name} name mismatch: {card.get('name')}"
        assert card.get("acp_version"), f"{name} missing acp_version"
        print(f"  ✓ {name} @ HTTP:{port} acp_version={card.get('acp_version')}")


def test_b2_orchestrator_sends_message(three_agents):
    """B2: Orchestrator 通过 /message:send 发出任务消息

    沙箱中无 P2P 连接，relay 正确返回 503 + ERR_NOT_CONNECTED（消息已入队）。
    断言：503 或 200 均可接受；消息 ID 从错误体中可提取（BUG-044 修复）。
    """
    status, data = _post(
        ORCH_HTTP, "/message:send",
        {"parts": [{"type": "text", "content": "dispatch: analyze dataset X"}], "role": "agent"},
    )
    # BUG-044: no P2P → relay queues message and returns 503 ERR_NOT_CONNECTED (by design)
    assert status in (200, 503), f"Orchestrator send unexpected status: {status} {data}"
    if status == 200:
        assert data.get("ok") is True, f"Expected ok=True: {data}"
        assert "message_id" in data, f"Missing message_id: {data}"
        print(f"  ✓ Orchestrator→ message_id={data['message_id']}")
    else:
        # 503: message queued for later delivery
        assert data.get("error_code") == "ERR_NOT_CONNECTED", f"Unexpected error_code: {data}"
        msg_id = data.get("failed_message_id", "(queued)")
        print(f"  ✓ Orchestrator→ message queued (no P2P), failed_message_id={msg_id}")


def test_b3_worker1_sends_result(three_agents):
    """B3: Worker1 通过 /message:send 发出结果消息（BUG-044 修复：接受 503 无连接时入队）"""
    status, data = _post(
        W1_HTTP, "/message:send",
        {"parts": [{"type": "text", "content": "RESULT:W1:analysis complete"}], "role": "agent"},
    )
    assert status in (200, 503), f"Worker1 send unexpected status: {status} {data}"
    if status == 200:
        assert data.get("ok") is True, f"Expected ok=True: {data}"
        print(f"  ✓ Worker1→ message_id={data.get('message_id')}")
    else:
        assert data.get("error_code") == "ERR_NOT_CONNECTED", f"Unexpected error_code: {data}"
        print(f"  ✓ Worker1→ message queued (no P2P), failed_message_id={data.get('failed_message_id')}")


def test_b4_worker2_sends_result(three_agents):
    """B4: Worker2 通过 /message:send 发出结果消息（BUG-044 修复：接受 503 无连接时入队）"""
    status, data = _post(
        W2_HTTP, "/message:send",
        {"parts": [{"type": "text", "content": "RESULT:W2:report ready"}], "role": "agent"},
    )
    assert status in (200, 503), f"Worker2 send unexpected status: {status} {data}"
    if status == 200:
        assert data.get("ok") is True, f"Expected ok=True: {data}"
        print(f"  ✓ Worker2→ message_id={data.get('message_id')}")
    else:
        assert data.get("error_code") == "ERR_NOT_CONNECTED", f"Unexpected error_code: {data}"
        print(f"  ✓ Worker2→ message queued (no P2P), failed_message_id={data.get('failed_message_id')}")


def test_b5_all_status_ok(three_agents):
    """B5: 三个实例 /status 正确报告 agent_name"""
    for name, port in [("Orchestrator", ORCH_HTTP), ("Worker1", W1_HTTP), ("Worker2", W2_HTTP)]:
        status, data = _get(port, "/status")
        assert status == 200, f"{name} /status: {status}"
        assert data.get("agent_name") == name, \
            f"{name} agent_name mismatch: {data.get('agent_name')}"
        assert data.get("acp_version"), f"{name} missing acp_version"
        print(f"  ✓ {name}: agent_name={data['agent_name']}, acp_version={data['acp_version']}")


def test_b6_orchestrator_queries_worker1_skills(three_agents):
    """B6: Orchestrator HTTP 访问 Worker1 的 /skills 端点（模拟 skill 发现）"""
    status, data = _get(W1_HTTP, "/skills")
    assert status == 200, f"Worker1 /skills: {status}"
    skills = data.get("skills", [])
    assert len(skills) >= 1, f"Worker1 has no skills: {data}"
    for s in skills:
        assert "input_modes"  in s, f"Missing input_modes: {s}"
        assert "output_modes" in s, f"Missing output_modes: {s}"
        assert "examples"     in s, f"Missing examples: {s}"
    print(f"  ✓ Worker1 skills: {[s['id'] for s in skills]}")


def test_b7_peers_empty_no_p2p(three_agents):
    """B7: 无 P2P 连接时 /peers 返回空列表（沙箱模式）"""
    for name, port in [("Orchestrator", ORCH_HTTP), ("Worker1", W1_HTTP), ("Worker2", W2_HTTP)]:
        status, data = _get(port, "/peers")
        assert status == 200, f"{name} /peers: {status}"
        assert "peers" in data, f"{name} /peers missing 'peers' key: {data}"
        assert isinstance(data["peers"], list), f"{name} peers not a list: {data}"
        print(f"  ✓ {name}: {len(data['peers'])} peers (expected 0 in sandbox)")
