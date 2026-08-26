"""
test_offline_ttl_v299.py — ACP v2.99: --max-offline-ttl expiry policy tests

Scenarios:
  OT1: --max-offline-ttl not set → /offline-queue/sweep returns 400
  OT2: messages within TTL are retained after sweep
  OT3: messages older than TTL are evicted after sweep (drop policy)
  OT4: /offline-queue shows ttl_config when TTL is configured
  OT5: --offline-ttl-policy notify — eviction still happens (no crash)
  OT6: lazy sweep on enqueue — expired messages removed before new one added
  OT7: /offline-queue/sweep returns correct evicted_count > 0 when expired
  OT8: TTL=0 evicts all queued messages
  OT9: persist-queue + TTL — SQLite rows cleared on sweep
"""
import json, os, socket, sqlite3, subprocess, sys, tempfile, time, urllib.error, urllib.request

RELAY = os.path.join(os.path.dirname(__file__), "..", "relay", "acp_relay.py")


def _free_port():
    """Reserve a WS port whose HTTP companion (port+100) is also free."""
    for _ in range(20):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            p = s.getsockname()[1]
        try:
            with socket.socket() as s2:
                s2.bind(("127.0.0.1", p + 100))
            return p
        except OSError:
            continue
    raise RuntimeError("Could not find two consecutive free ports")


def _start_relay(ws_port, extra_args=None):
    """Start relay in test-mode; HTTP port = ws_port + 100."""
    cmd = [
        sys.executable, RELAY,
        "--port", str(ws_port),
        "--http-host", "127.0.0.1",
        "--local-only",
        "--test-mode",
        "--no-identity",
    ]
    if extra_args:
        cmd.extend(extra_args)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    hp = ws_port + 100
    deadline = time.time() + 10.0
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{hp}/status", timeout=0.5)
            return proc, hp
        except Exception:
            time.sleep(0.2)
    return proc, hp


def _stop(proc):
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()


def _get(hp, path):
    try:
        resp = urllib.request.urlopen(f"http://127.0.0.1:{hp}{path}", timeout=5)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _post(hp, path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{hp}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=5)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _enqueue_msg(hp, text="hello"):
    """Enqueue a message to the offline queue (no peer connected → 503)."""
    status, body = _post(hp, "/message:send", {
        "type": "message",
        "role": "user",
        "content": {"text": text},
        "message_id": f"msg-{time.time():.6f}",
        "to": "offline-peer",
    })
    # 503 = no peer, message buffered in offline queue — expected
    return status, body


# ── OT1: no TTL → sweep returns 400 ─────────────────────────────────────────
def test_OT1_sweep_requires_ttl_config():
    ws = _free_port()
    proc, hp = _start_relay(ws)
    try:
        status, body = _get(hp, "/offline-queue/sweep")
        assert status == 400, f"Expected 400, got {status}: {body}"
        assert "error" in body
    finally:
        _stop(proc)


# ── OT2: messages within TTL retained ────────────────────────────────────────
def test_OT2_messages_within_ttl_retained():
    ws = _free_port()
    proc, hp = _start_relay(ws, ["--max-offline-ttl", "3600"])
    try:
        _enqueue_msg(hp, "keep-me")
        time.sleep(0.3)
        status, body = _get(hp, "/offline-queue/sweep")
        assert status == 200
        assert body["evicted_count"] == 0, f"Should retain fresh msgs: {body}"
        _, q = _get(hp, "/offline-queue")
        assert q["total_queued"] >= 1
    finally:
        _stop(proc)


# ── OT3: messages older than TTL evicted (drop policy) ───────────────────────
def test_OT3_expired_messages_evicted_drop():
    ws = _free_port()
    proc, hp = _start_relay(ws, ["--max-offline-ttl", "1", "--offline-ttl-policy", "drop"])
    try:
        _enqueue_msg(hp, "expire-me")
        time.sleep(2.2)
        status, body = _get(hp, "/offline-queue/sweep")
        assert status == 200
        assert body["evicted_count"] >= 1, f"Expected eviction: {body}"
        assert body["policy"] == "drop"
        _, q = _get(hp, "/offline-queue")
        assert q["total_queued"] == 0, f"Queue should be empty: {q}"
    finally:
        _stop(proc)


# ── OT4: /offline-queue shows ttl_config when configured ─────────────────────
def test_OT4_offline_queue_shows_ttl_config():
    ws = _free_port()
    proc, hp = _start_relay(ws, ["--max-offline-ttl", "120", "--offline-ttl-policy", "notify"])
    try:
        status, body = _get(hp, "/offline-queue")
        assert status == 200
        assert "ttl_config" in body, f"ttl_config missing: {body}"
        assert body["ttl_config"]["max_seconds"] == 120
        assert body["ttl_config"]["policy"] == "notify"
    finally:
        _stop(proc)


# ── OT5: notify policy evicts without crash ──────────────────────────────────
def test_OT5_notify_policy_evicts_without_crash():
    ws = _free_port()
    proc, hp = _start_relay(ws, ["--max-offline-ttl", "1", "--offline-ttl-policy", "notify"])
    try:
        _enqueue_msg(hp, "notify-expire")
        time.sleep(2.2)
        status, body = _get(hp, "/offline-queue/sweep")
        assert status == 200
        assert body["evicted_count"] >= 1
        assert body["policy"] == "notify"
    finally:
        _stop(proc)


# ── OT6: lazy sweep on enqueue removes expired before adding new ──────────────
def test_OT6_lazy_sweep_on_enqueue():
    ws = _free_port()
    proc, hp = _start_relay(ws, ["--max-offline-ttl", "1"])
    try:
        _enqueue_msg(hp, "old-msg")
        time.sleep(2.2)
        _enqueue_msg(hp, "new-msg")
        time.sleep(0.3)
        _, q = _get(hp, "/offline-queue")
        assert q["total_queued"] <= 1, f"Lazy sweep should remove expired msg: {q}"
    finally:
        _stop(proc)


# ── OT7: evicted_count accurate across multiple messages ─────────────────────
def test_OT7_sweep_evicted_count_accurate():
    ws = _free_port()
    proc, hp = _start_relay(ws, ["--max-offline-ttl", "1"])
    try:
        for i in range(3):
            _enqueue_msg(hp, f"msg-{i}")
        time.sleep(2.2)
        status, body = _get(hp, "/offline-queue/sweep")
        assert status == 200
        assert body["evicted_count"] >= 3, f"Expected 3 evicted: {body}"
        assert body["peers_affected"] >= 1
    finally:
        _stop(proc)


# ── OT8: TTL=0 evicts everything ─────────────────────────────────────────────
def test_OT8_ttl_zero_evicts_all():
    ws = _free_port()
    proc, hp = _start_relay(ws, ["--max-offline-ttl", "0"])
    try:
        _enqueue_msg(hp, "gone-immediately")
        time.sleep(0.3)
        status, body = _get(hp, "/offline-queue/sweep")
        assert status == 200
        _, q = _get(hp, "/offline-queue")
        assert q["total_queued"] == 0
    finally:
        _stop(proc)


# ── OT9: persist-queue + TTL sweep clears SQLite rows ────────────────────────
def test_OT9_persist_queue_ttl_clears_sqlite():
    ws = _free_port()
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        proc, hp = _start_relay(ws, [
            "--max-offline-ttl", "1",
            "--persist-queue", db_path,
        ])
        try:
            _enqueue_msg(hp, "persist-expire")
            time.sleep(2.2)
            status, body = _get(hp, "/offline-queue/sweep")
            assert status == 200
            assert body["evicted_count"] >= 1
            conn = sqlite3.connect(db_path)
            count = conn.execute("SELECT COUNT(*) FROM offline_queue").fetchone()[0]
            conn.close()
            assert count == 0, f"SQLite should be empty after TTL sweep, got {count} rows"
        finally:
            _stop(proc)
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)
