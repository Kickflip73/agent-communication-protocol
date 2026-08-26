#!/usr/bin/env python3
"""
T6: 场景 A 回归测试 — 双 Agent 通信（A→B, B→A, 双向会话）

设计原则（BUG-042 修复后重构）:
  - Alpha relay: host mode（监听 incoming WS）
  - Beta relay:  --join acp://127.0.0.1:<alpha_ws>/<token>（直接 guest_mode，无 NAT 竞态）
  - 动态端口分配，避免全套并发测试端口冲突
  - 标准 pytest 格式（fixture + test 函数）
  - 所有断言通过 HTTP API 完成

BUG-042 说明:
  原测试依赖 POST /peers/connect → _connect_with_nat_traversal Level 1 + BUG-041 dedup 竞态。
  修复后 relay 层已正确将 Level-1 WS 移交给 guest_mode（无第二次握手），
  同时测试改为 --join 模式作为双重保障。

运行：
  pytest tests/test_dcutr_t6_scenario_a.py -v
  pytest tests/test_dcutr_t6_scenario_a.py -v --timeout=120
"""
import json
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RELAY_PY = os.path.join(BASE_DIR, "relay", "acp_relay.py")

_PROXY_VARS = (
    "http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY",
    "all_proxy", "ALL_PROXY", "ftp_proxy", "FTP_PROXY", "no_proxy", "NO_PROXY",
)
for _pv in _PROXY_VARS:
    os.environ.pop(_pv, None)


# ── 端口分配 ──────────────────────────────────────────────────────────────────

def _free_port() -> int:
    """Return WS port P such that both P and P+100 are available."""
    for _ in range(300):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            ws = s.getsockname()[1]
        try:
            with socket.socket() as s2:
                s2.bind(("127.0.0.1", ws + 100))
                return ws
        except OSError:
            continue
    raise RuntimeError("Cannot find a free port pair (ws + ws+100)")


# ── 环境变量 ──────────────────────────────────────────────────────────────────

def _clean_env() -> dict:
    env = os.environ.copy()
    for v in _PROXY_VARS:
        env.pop(v, None)
    env["PYTHONUNBUFFERED"] = "1"
    return env


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _http_get(url: str, timeout: float = 5) -> tuple:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read()), e.code
        except Exception:
            return {"_error": str(e)}, e.code
    except Exception as ex:
        return {"_error": str(ex)}, -1


def _http_post(url: str, body: dict, timeout: float = 8) -> tuple:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read()), e.code
        except Exception:
            return {"_error": str(e)}, e.code
    except Exception as ex:
        return {"_error": str(ex)}, -1


# ── Relay 生命周期 ─────────────────────────────────────────────────────────────

def _start_host_relay(ws_port: int, name: str = "T6-Alpha") -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-u", RELAY_PY,
         "--name", name,
         "--port", str(ws_port),
         "--http-host", "127.0.0.1"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
        env=_clean_env(),
    )


def _start_guest_relay(ws_port: int, name: str, join_link: str) -> subprocess.Popen:
    """Start relay in guest mode (--join), skipping NAT traversal directly."""
    return subprocess.Popen(
        [sys.executable, "-u", RELAY_PY,
         "--name", name,
         "--port", str(ws_port),
         "--http-host", "127.0.0.1",
         "--join", join_link],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=_clean_env(),
    )


def _wait_http_ready(http_port: int, timeout: float = 15) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{http_port}/status", timeout=2
            ) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def _wait_host_link(proc: subprocess.Popen, http_port: int, timeout: float = 50) -> str | None:
    """
    Wait for host relay to produce an acp:// link.
    Returns local link acp://127.0.0.1:<ws>/<token> or None.
    """
    token_holder: dict = {"link": None}
    lock = threading.Lock()

    def _stdout_reader():
        try:
            for line in proc.stdout:
                m = re.search(r"acp://[^\s/]+:(\d+)/(tok_[a-f0-9]+)", line)
                if m:
                    with lock:
                        if not token_holder["link"]:
                            token_holder["link"] = f"acp://127.0.0.1:{m.group(1)}/{m.group(2)}"
        except Exception:
            pass

    t = threading.Thread(target=_stdout_reader, daemon=True)
    t.start()

    deadline = time.time() + timeout
    while time.time() < deadline:
        with lock:
            if token_holder["link"]:
                return token_holder["link"]
        for endpoint in ("/link", "/status"):
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{http_port}{endpoint}", timeout=2
                ) as r:
                    d = json.loads(r.read())
                    raw = d.get("link", "") or ""
                    if raw:
                        local = re.sub(r"acp://[^:]+:", "acp://127.0.0.1:", raw)
                        with lock:
                            token_holder["link"] = local
                        return local
            except Exception:
                pass
        time.sleep(0.3)
    return None


def _wait_connected(http_port: int, timeout: float = 20) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        st, _ = _http_get(f"http://127.0.0.1:{http_port}/status")
        if st.get("connected") is True or st.get("peer_count", 0) >= 1:
            return True
        time.sleep(0.3)
    return False


def _wait_peer_ready(http_port: int, peer_id: str, timeout: float = 15) -> bool:
    """Poll /peer/{id}/send until ok=True (WS is actually ready)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        r, code = _http_post(
            f"http://127.0.0.1:{http_port}/peer/{peer_id}/send",
            {"parts": [{"type": "text", "content": "_probe_"}], "role": "agent"},
        )
        if code == 200 and r.get("ok"):
            return True
        time.sleep(0.3)
    return False


def _kill_relay(proc: subprocess.Popen, wait_secs: float = 8) -> None:
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=wait_secs)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=2)
    except Exception:
        pass


# ── pytest fixture：启动 Alpha(host) + Beta(--join) ──────────────────────────

@pytest.fixture(scope="module")
def relay_pair():
    """
    Start Alpha (host) + Beta (guest --join Alpha).
    Alpha is in host mode; Beta uses --join to directly call guest_mode().
    This avoids BUG-042 (NAT traversal Level-1 + BUG-041 dedup race).

    Yields: (alpha_http, beta_http, alpha_link, beta_link, alpha_ws, beta_ws)
    """
    alpha_ws = _free_port()
    beta_ws  = _free_port()
    alpha_http = alpha_ws + 100
    beta_http  = beta_ws  + 100

    # Start Alpha (host mode)
    alpha_proc = _start_host_relay(alpha_ws, "T6-Alpha")
    assert _wait_http_ready(alpha_http, timeout=15), \
        "T6: Alpha relay HTTP did not start within 15s"

    # Wait for Alpha to produce a link (public IP detection ~31s in sandbox)
    alpha_link = _wait_host_link(alpha_proc, alpha_http, timeout=50)
    assert alpha_link is not None, \
        "T6: Alpha relay did not produce an acp:// link within 50s"

    # Start Beta (guest --join Alpha)
    beta_proc = _start_guest_relay(beta_ws, "T6-Beta", alpha_link)
    assert _wait_http_ready(beta_http, timeout=15), \
        "T6: Beta relay HTTP did not start within 15s"

    # Wait for connection to establish
    assert _wait_connected(alpha_http, timeout=20), \
        "T6: Alpha should detect Beta connection within 20s"
    assert _wait_connected(beta_http, timeout=20), \
        "T6: Beta should report connected=True within 20s"

    # Get peer IDs from each relay's perspective
    alpha_peers, _ = _http_get(f"http://127.0.0.1:{alpha_http}/peers")
    beta_peers,  _ = _http_get(f"http://127.0.0.1:{beta_http}/peers")

    alpha_connected = [p for p in alpha_peers.get("peers", []) if p.get("connected")]
    beta_connected  = [p for p in beta_peers.get("peers", []) if p.get("connected")]

    assert alpha_connected, "T6: Alpha should have at least one connected peer"
    assert beta_connected,  "T6: Beta should have at least one connected peer"

    alpha_peer_id = alpha_connected[0]["id"]  # from Alpha's POV, this is Beta's peer_id
    beta_peer_id  = beta_connected[0]["id"]   # from Beta's POV, this is Alpha's peer_id

    # Wait until peers are ready to send (ws fully established)
    assert _wait_peer_ready(alpha_http, alpha_peer_id, timeout=15), \
        f"T6: Alpha → Beta peer '{alpha_peer_id}' not ready within 15s"
    assert _wait_peer_ready(beta_http, beta_peer_id, timeout=15), \
        f"T6: Beta → Alpha peer '{beta_peer_id}' not ready within 15s"

    # Get Beta's own link (may be None in sandbox without public IP, that's OK)
    beta_link_resp, _ = _http_get(f"http://127.0.0.1:{beta_http}/link")
    beta_link = beta_link_resp.get("link")

    yield {
        "alpha_http": alpha_http,
        "beta_http":  beta_http,
        "alpha_link": alpha_link,
        "beta_link":  beta_link,
        "alpha_peer_id": alpha_peer_id,  # Beta's peer_id as seen by Alpha
        "beta_peer_id":  beta_peer_id,   # Alpha's peer_id as seen by Beta
        "alpha_proc":    alpha_proc,
        "beta_proc":     beta_proc,
    }

    # Teardown
    _kill_relay(beta_proc)
    _kill_relay(alpha_proc)


# ── T6 test functions ─────────────────────────────────────────────────────────

@pytest.mark.timeout(120)
def test_t6_1_relay_health(relay_pair):
    """T6.1: 两个 relay 实例均正常响应"""
    alpha_http = relay_pair["alpha_http"]
    beta_http  = relay_pair["beta_http"]

    st_a, code_a = _http_get(f"http://127.0.0.1:{alpha_http}/status")
    st_b, code_b = _http_get(f"http://127.0.0.1:{beta_http}/status")

    assert code_a == 200, f"T6.1: Alpha /status should return 200; got {code_a}"
    assert code_b == 200, f"T6.1: Beta /status should return 200; got {code_b}"
    assert "acp_version" in st_a, "T6.1: Alpha /status must include acp_version"
    assert "acp_version" in st_b, "T6.1: Beta /status must include acp_version"


@pytest.mark.timeout(120)
def test_t6_2_agent_card(relay_pair):
    """T6.2: AgentCard 端点正常"""
    alpha_http = relay_pair["alpha_http"]

    card, code = _http_get(f"http://127.0.0.1:{alpha_http}/.well-known/acp.json")
    assert code == 200, f"T6.2: AgentCard should return 200; got {code}"
    assert "self" in card, f"T6.2: AgentCard must have 'self' key; got {list(card.keys())}"
    assert "name" in card["self"], "T6.2: AgentCard.self must have 'name'"


@pytest.mark.timeout(120)
def test_t6_3_alpha_to_beta(relay_pair):
    """T6.3: Alpha→Beta 消息发送"""
    alpha_http   = relay_pair["alpha_http"]
    alpha_peer_id = relay_pair["alpha_peer_id"]

    resp, code = _http_post(
        f"http://127.0.0.1:{alpha_http}/peer/{alpha_peer_id}/send",
        {
            "role": "agent",
            "parts": [{"type": "text", "content": "Hello from Alpha! T6.3 DCUtR regression"}],
            "message_id": f"t6_3_{int(time.time())}",
        },
    )
    assert code in (200, 202), \
        f"T6.3: Alpha→Beta send should return 200/202; got {code}: {resp}"
    assert resp.get("ok"), \
        f"T6.3: Alpha→Beta send ok should be True; got {resp}"
    assert resp.get("message_id"), \
        "T6.3: response must include message_id"


@pytest.mark.timeout(120)
def test_t6_4_beta_receives(relay_pair):
    """T6.4: Beta 收到 Alpha 的消息"""
    beta_http = relay_pair["beta_http"]

    # Allow brief delivery time
    time.sleep(0.5)
    inbox, code = _http_get(f"http://127.0.0.1:{beta_http}/recv")
    assert code == 200, f"T6.4: Beta /recv should return 200; got {code}"

    count = inbox.get("count", 0)
    assert count > 0, \
        f"T6.4: Beta should have received at least 1 message; inbox count={count}"


@pytest.mark.timeout(120)
def test_t6_5_beta_to_alpha(relay_pair):
    """T6.5: Beta→Alpha 反向消息发送"""
    beta_http   = relay_pair["beta_http"]
    beta_peer_id = relay_pair["beta_peer_id"]

    resp, code = _http_post(
        f"http://127.0.0.1:{beta_http}/peer/{beta_peer_id}/send",
        {
            "role": "agent",
            "parts": [{"type": "text", "content": "Reply from Beta! T6.5 regression OK"}],
        },
    )
    assert code in (200, 202), \
        f"T6.5: Beta→Alpha send should return 200/202; got {code}: {resp}"
    assert resp.get("ok"), \
        f"T6.5: Beta→Alpha send ok should be True; got {resp}"


@pytest.mark.timeout(120)
def test_t6_6_alpha_receives(relay_pair):
    """T6.6: Alpha 收到 Beta 的回复"""
    alpha_http = relay_pair["alpha_http"]

    time.sleep(0.5)
    inbox, code = _http_get(f"http://127.0.0.1:{alpha_http}/recv")
    assert code == 200, f"T6.6: Alpha /recv should return 200; got {code}"

    count = inbox.get("count", 0)
    # Note: T6.3 probe message also lands in inbox; count ≥ 1 (could be 2 with probe)
    assert count > 0, \
        f"T6.6: Alpha should have received at least 1 message from Beta; count={count}"


@pytest.mark.timeout(120)
def test_t6_7_task_state_machine(relay_pair):
    """T6.7: Task 创建和状态机验证（BUG-031 回归：需 role 字段）"""
    alpha_http = relay_pair["alpha_http"]

    resp, code = _http_post(
        f"http://127.0.0.1:{alpha_http}/tasks",
        {
            "task_id": "regression_task_t6_001",
            "role": "agent",   # BUG-031 fix: role is required since BUG-010 fix
            "title": "T6 DCUtR Regression Test Task",
            "description": "Verifying task state machine after DCUtR commit",
            "input": {"parts": [{"type": "text", "content": "Regression test task"}]},
        },
    )
    assert code in (200, 201), \
        f"T6.7: Task creation should return 200/201; got {code}: {resp}"

    # BUG-031 fix: response is {"ok": true, "task": {...}}
    task_obj = resp.get("task", resp)
    status   = task_obj.get("status")
    assert status in ("submitted", "working"), \
        f"T6.7: Task initial status should be submitted/working; got '{status}'"


# ── Script entry point (backward compat) ─────────────────────────────────────

if __name__ == "__main__":
    import sys as _sys
    _sys.exit(
        subprocess.call(
            [_sys.executable, "-m", "pytest", __file__, "-v", "--timeout=120"]
        )
    )
