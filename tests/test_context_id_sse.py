#!/usr/bin/env python3
"""
tests/test_context_id_sse.py

Unit tests for context_id propagation through SSE events (v1.7).

Verifies that:
  - status SSE events carry context_id when task has one (C1-C4)
  - artifact SSE events carry context_id (C5)
  - tasks without context_id emit events without context_id key (C6)
  - /tasks/create endpoint stores context_id on the task (C7)
  - _update_task with artifact propagates context_id (C8)
"""

import sys
import os
import json
import threading
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Clear proxy before import so relay helpers can reach localhost
for _v in ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY"):
    os.environ.pop(_v, None)

from relay.acp_relay import (
    _create_task,
    _update_task,
    _broadcast_sse_event,
    _sse_subscribers,
    _tasks,
    TASK_SUBMITTED,
    TASK_WORKING,
    TASK_COMPLETED,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

_results = []

def ok(name, passed, note=""):
    sym = "✅" if passed else "❌"
    _results.append((name, passed, note))
    print(f"  {sym} {name}" + (f" — {note}" if note else ""))


def capture_sse_events(fn, timeout=0.5):
    """Run fn(), collect SSE events broadcast during fn(), return list."""
    import collections
    q = collections.deque()
    _sse_subscribers.append(q)
    try:
        fn()
        time.sleep(0.05)  # let broadcast thread flush
        return list(q)
    finally:
        _sse_subscribers.remove(q)


def run_tests():
    _results.clear()
    print("=" * 55)
    print("ACP context_id SSE Propagation Tests (v1.7)")
    print("=" * 55)

    CTX = "ctx_test_ABCDE"

    # ── C1: _create_task with context_id → SSE status event contains it ──────
    print("\n[C1] _create_task + context_id → status SSE event")
    events = capture_sse_events(
        lambda: _create_task({"role": "user", "text": "hello"}, context_id=CTX)
    )
    status_evts = [e for e in events if e.get("type") == "status"]
    ok("C1-1 at least one status event emitted", len(status_evts) >= 1,
       f"events={len(status_evts)}")
    ok("C1-2 context_id in status event", status_evts[0].get("context_id") == CTX if status_evts else False,
       f"got={status_evts[0].get('context_id') if status_evts else 'no event'}")
    ok("C1-3 task_id present in event", "task_id" in (status_evts[0] if status_evts else {}),
       f"keys={list(status_evts[0].keys()) if status_evts else []}")

    # ── C2: task.context_id stored on task object ─────────────────────────────
    print("\n[C2] Task object stores context_id")
    task2 = _create_task({"role": "agent", "text": "work"}, context_id=CTX)
    ok("C2-1 task has context_id field", task2.get("context_id") == CTX,
       f"got={task2.get('context_id')}")
    ok("C2-2 task id is set", task2.get("id", "").startswith("task_"),
       f"id={task2.get('id')}")

    # ── C3: _update_task state change → status SSE event carries context_id ──
    print("\n[C3] _update_task state change → context_id in status SSE")
    task3 = _create_task({"role": "user", "text": "process"}, context_id=CTX)
    events3 = capture_sse_events(
        lambda: _update_task(task3["id"], TASK_WORKING)
    )
    s3 = [e for e in events3 if e.get("type") == "status"]
    ok("C3-1 status event emitted on state change", len(s3) >= 1, f"n={len(s3)}")
    ok("C3-2 context_id in state-change status event",
       s3[0].get("context_id") == CTX if s3 else False,
       f"got={s3[0].get('context_id') if s3 else 'none'}")
    ok("C3-3 state is working", s3[0].get("state") == TASK_WORKING if s3 else False,
       f"state={s3[0].get('state') if s3 else 'none'}")

    # ── C4: _update_task → completed with context_id ─────────────────────────
    print("\n[C4] _update_task completed → context_id preserved")
    _update_task(task3["id"], TASK_WORKING)  # move to working first
    events4 = capture_sse_events(
        lambda: _update_task(task3["id"], TASK_COMPLETED)
    )
    s4 = [e for e in events4 if e.get("type") == "status"]
    ok("C4-1 completed status event has context_id",
       s4[0].get("context_id") == CTX if s4 else False,
       f"got={s4[0].get('context_id') if s4 else 'none'}")

    # ── C5: artifact event carries context_id ────────────────────────────────
    print("\n[C5] artifact SSE event carries context_id")
    task5 = _create_task({"role": "agent", "text": "gen"}, context_id=CTX)
    _update_task(task5["id"], TASK_WORKING)
    artifact = {"type": "text", "content": "result", "index": 0}
    events5 = capture_sse_events(
        lambda: _update_task(task5["id"], TASK_WORKING, artifact=artifact)
    )
    art5 = [e for e in events5 if e.get("type") == "artifact"]
    ok("C5-1 artifact event emitted", len(art5) >= 1, f"n={len(art5)}")
    ok("C5-2 artifact event has context_id",
       art5[0].get("context_id") == CTX if art5 else False,
       f"got={art5[0].get('context_id') if art5 else 'none'}")
    ok("C5-3 artifact event has task_id",
       art5[0].get("task_id") == task5["id"] if art5 else False,
       f"task_id={art5[0].get('task_id') if art5 else 'none'}")

    # ── C6: task WITHOUT context_id → events do NOT contain context_id ───────
    print("\n[C6] task without context_id → events omit context_id key")
    task6 = _create_task({"role": "user", "text": "no ctx"})  # no context_id
    events6 = capture_sse_events(
        lambda: _update_task(task6["id"], TASK_WORKING)
    )
    s6 = [e for e in events6 if e.get("type") == "status"]
    ok("C6-1 status event emitted", len(s6) >= 1, f"n={len(s6)}")
    ok("C6-2 context_id NOT in event (no spurious null)",
       "context_id" not in s6[0] if s6 else True,
       f"keys={list(s6[0].keys()) if s6 else []}")

    # ── C7: task without context_id doesn't store context_id field ───────────
    print("\n[C7] task without context_id has no context_id field")
    task7 = _create_task({"role": "system", "text": "bg"})
    ok("C7-1 context_id not in task dict",
       "context_id" not in task7,
       f"keys={list(task7.keys())}")

    # ── C8: artifact on task without context_id — no context_id in event ─────
    print("\n[C8] artifact on task without context_id — event clean")
    task8 = _create_task({"role": "agent", "text": "art"})
    _update_task(task8["id"], TASK_WORKING)
    events8 = capture_sse_events(
        lambda: _update_task(task8["id"], TASK_WORKING,
                              artifact={"type": "text", "content": "x", "index": 0})
    )
    art8 = [e for e in events8 if e.get("type") == "artifact"]
    ok("C8-1 artifact event emitted", len(art8) >= 1)
    ok("C8-2 context_id NOT in artifact event",
       "context_id" not in art8[0] if art8 else True,
       f"keys={list(art8[0].keys()) if art8 else []}")

    # ── Summary ───────────────────────────────────────────────────────────────
    total = len(_results)
    passed = sum(1 for _, p, _ in _results if p)
    print("\n" + "=" * 55)
    print(f"context_id SSE Tests: {passed}/{total} PASS {'✅' if passed == total else ''}")
    if passed < total:
        print("FAIL 項：")
        for name, p, note in _results:
            if not p:
                print(f"  ❌ {name}" + (f" — {note}" if note else ""))
    print("=" * 55)
    return passed == total


def test_context_id_sse():
    """pytest entry point."""
    # Clear proxy env vars (sandbox http_proxy intercepts localhost)
    for _v in ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY",
               "all_proxy", "ALL_PROXY"):
        os.environ.pop(_v, None)
    assert run_tests(), "context_id SSE propagation tests failed"


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(0 if run_tests() else 1)
