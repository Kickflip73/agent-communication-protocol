"""
tests/test_tasks_filtering.py
开发轮 — /tasks 过滤器扩展测试（created_after / updated_after）
2026-03-24

覆盖：
  TF1 — created_after 过滤：只返回指定时间之后创建的任务
  TF2 — updated_after 过滤：只返回指定时间之后更新的任务
  TF3 — created_after + state 组合过滤
  TF4 — updated_after 边界：未来时间戳 → 空列表
  TF5 — 无效时间戳格式 → 仍能返回（字符串比较，不崩溃）
  TF6 — 回归：旧有 state/peer_id/cursor 过滤不受影响
"""

import time
import requests
import subprocess
import threading
import sys
import os
import pytest
from conftest import clean_subprocess_env

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RELAY_WS_PORT  = 18870
RELAY_HTTP_PORT = RELAY_WS_PORT + 100   # HTTP port = ws + 100
BASE = f"http://127.0.0.1:{RELAY_HTTP_PORT}"
RELAY_BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "relay", "acp_relay.py")

_proc = None


def setup_module(module):
    global _proc
    _proc = subprocess.Popen(
        [sys.executable, RELAY_BIN, "--port", str(RELAY_WS_PORT)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=clean_subprocess_env(),
    )
    # 等待启动（HTTP port = ws + 100）
    for _ in range(40):
        try:
            r = requests.get(f"{BASE}/status", timeout=1)
            if r.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(0.3)
    else:
        raise RuntimeError("Relay failed to start")


def teardown_module(module):
    if _proc:
        _proc.terminate()
        _proc.kill()


def _create_task(peer_id="peer-tf", role="agent", content="test"):
    r = requests.post(f"{BASE}/tasks", json={
        "role": role,
        "peer_id": peer_id,
        "input": {"parts": [{"type": "text", "content": content}]}
    }, timeout=5)
    assert r.status_code == 201, f"Task create failed: {r.status_code} {r.text}"
    return r.json()["task"]


def _now_iso():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _past_iso(seconds=10):
    """返回 N 秒前的 ISO 时间戳"""
    from datetime import datetime, timezone, timedelta
    t = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    return t.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _future_iso(seconds=3600):
    """返回 N 秒后的 ISO 时间戳"""
    from datetime import datetime, timezone, timedelta
    t = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    return t.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


# ─────────────────────────────────────────────
# TF1: created_after 基本过滤
# ─────────────────────────────────────────────
def test_tf1_created_after_basic():
    """created_after 应只返回时间戳之后创建的任务"""
    before = _now_iso()
    time.sleep(0.05)  # 确保时间戳差异
    t1 = _create_task(content="after-filter-t1")
    t2 = _create_task(content="after-filter-t2")

    r = requests.get(f"{BASE}/tasks", params={"created_after": before}, timeout=5)
    assert r.status_code == 200
    data = r.json()
    task_ids = [t["id"] for t in data["tasks"]]
    assert t1["id"] in task_ids, f"t1 should be in results: {task_ids}"
    assert t2["id"] in task_ids, f"t2 should be in results: {task_ids}"
    # 过滤应有效（不返回全部）
    for t in data["tasks"]:
        assert t.get("created_at", "") > before, f"Task {t['id']} created_at {t.get('created_at')} <= filter {before}"
    print(f"  TF1 ✅ created_after返回 {len(task_ids)} 个任务")


# ─────────────────────────────────────────────
# TF2: updated_after 过滤
# ─────────────────────────────────────────────
def test_tf2_updated_after():
    """updated_after 只返回更新时间在指定时间之后的任务"""
    t1 = _create_task(content="update-before")
    before_update = _now_iso()
    time.sleep(0.05)
    # 更新 t1 的状态（正确端点：POST /tasks/{id}/update）
    upd = requests.post(f"{BASE}/tasks/{t1['id']}/update", json={"status": "working"}, timeout=5)
    assert upd.status_code == 200, f"Update failed: {upd.status_code} {upd.text}"
    t2 = _create_task(content="create-after")  # 新建的也算 updated_after = created_at

    r = requests.get(f"{BASE}/tasks", params={"updated_after": before_update}, timeout=5)
    assert r.status_code == 200
    data = r.json()
    task_ids = [t["id"] for t in data["tasks"]]
    assert t1["id"] in task_ids, f"t1 (updated after) should be in results"
    assert t2["id"] in task_ids, f"t2 (created after) should be in results"
    print(f"  TF2 ✅ updated_after返回 {len(task_ids)} 个任务")


# ─────────────────────────────────────────────
# TF3: created_after + state 组合
# ─────────────────────────────────────────────
def test_tf3_created_after_and_state():
    """created_after 与 state 组合过滤"""
    before = _now_iso()
    time.sleep(0.05)
    t_work = _create_task(content="combo-working")
    t_sub  = _create_task(content="combo-submitted")
    # 更新 t_work 为 working（正确端点：POST /tasks/{id}/update）
    requests.post(f"{BASE}/tasks/{t_work['id']}/update", json={"status": "working"}, timeout=5)

    r = requests.get(f"{BASE}/tasks", params={
        "created_after": before,
        "state": "working"
    }, timeout=5)
    assert r.status_code == 200
    data = r.json()
    task_ids = [t["id"] for t in data["tasks"]]
    assert t_work["id"] in task_ids, "working task should appear"
    assert t_sub["id"] not in task_ids, "submitted task should NOT appear (filtered by state)"
    print(f"  TF3 ✅ created_after+state 组合过滤正常")


# ─────────────────────────────────────────────
# TF4: 未来时间戳 → 空列表
# ─────────────────────────────────────────────
def test_tf4_future_timestamp_returns_empty():
    """created_after 为未来时间戳，应返回空列表"""
    _create_task(content="before-future")
    future = _future_iso(3600)

    r = requests.get(f"{BASE}/tasks", params={"created_after": future}, timeout=5)
    assert r.status_code == 200
    data = r.json()
    assert data["tasks"] == [], f"Expected empty list, got: {data['tasks']}"
    assert data["count"] == 0
    print(f"  TF4 ✅ 未来时间戳返回空列表")


# ─────────────────────────────────────────────
# TF5: 无效时间戳 — 不崩溃
# ─────────────────────────────────────────────
def test_tf5_invalid_timestamp_no_crash():
    """无效时间戳格式不应导致 500，返回 200（字符串比较退化）"""
    r = requests.get(f"{BASE}/tasks", params={"created_after": "not-a-timestamp"}, timeout=5)
    # 允许 200（字符串比较退化）或 400（参数校验拒绝）
    assert r.status_code in (200, 400), f"Should not 500: {r.status_code}"
    print(f"  TF5 ✅ 无效时间戳返回 {r.status_code}（非 500）")


# ─────────────────────────────────────────────
# TF6: 回归 — 旧 state/peer_id 过滤不受影响
# ─────────────────────────────────────────────
def test_tf6_regression_state_and_peer_filter():
    """旧有 state/peer_id 过滤在加入新参数后仍正常工作"""
    peer_a = "peer-tf6-a"
    peer_b = "peer-tf6-b"
    t_a = _create_task(peer_id=peer_a, content="regression-a")
    t_b = _create_task(peer_id=peer_b, content="regression-b")

    # 按 peer_id 过滤
    r = requests.get(f"{BASE}/tasks", params={"peer_id": peer_a}, timeout=5)
    assert r.status_code == 200
    task_ids = [t["id"] for t in r.json()["tasks"]]
    assert t_a["id"] in task_ids
    assert t_b["id"] not in task_ids, "peer_b task should NOT appear in peer_a filter"

    # 按 state 过滤（submitted 默认状态）
    r2 = requests.get(f"{BASE}/tasks", params={"state": "submitted"}, timeout=5)
    assert r2.status_code == 200
    all_submitted = [t["id"] for t in r2.json()["tasks"]]
    assert t_a["id"] in all_submitted
    assert t_b["id"] in all_submitted

    print(f"  TF6 ✅ 旧有 state/peer_id 过滤回归正常")


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "--tb=short"])
